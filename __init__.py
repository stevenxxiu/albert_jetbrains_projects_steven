import time
from pathlib import Path
from typing import Callable, NamedTuple, override
from xml.etree import ElementTree

from albert import (
    Action,
    Icon,
    Item,
    Matcher,
    PluginInstance,
    Query,
    StandardItem,
    TriggerQueryHandler,
    makeImageIcon,
    runDetachedProcess,
)

md_iid = '4.0'
md_version = '1.4'
md_name = 'JetBrains Projects Steven'
md_description = 'List and open JetBrains IDE projects'
md_license = 'MIT'
md_url = 'https://github.com/stevenxxiu/albert_jetbrains_projects_steven'
md_authors = ['@stevenxxiu']

ANDROID_STUDIO_ICON_PATH = Path(__file__).parent / 'icons/studio.svg'
GOOGLE_XDG_CONFIG_DIR = Path.home() / '.config/Google'


class IdeConfig(NamedTuple):
    icon_factory: Callable[[], Icon]
    desktop_file: str
    parent_config_dir: Path


IDE_CONFIGS: dict[str, IdeConfig] = {
    'AndroidStudio': IdeConfig(
        icon_factory=lambda: makeImageIcon(ANDROID_STUDIO_ICON_PATH),
        desktop_file='android-studio.desktop',
        parent_config_dir=GOOGLE_XDG_CONFIG_DIR,
    ),
}


class IdeProject(NamedTuple):
    name: str
    path: Path
    app_name: str
    timestamp: int


def get_recent_projects(path: Path) -> list[tuple[int, Path]]:
    """
    :param path: Parse the XML at `path`.
    :return: All recent project paths and the time they were last open.
    """
    root: ElementTree.Element = ElementTree.parse(path).getroot()
    additional_info: ElementTree.Element | None = None
    path_to_timestamp: dict[str, int] = {}
    for option_tag in root[0]:
        match option_tag.attrib['name']:
            case 'recentPaths':
                for recent_path in option_tag[0]:
                    path_to_timestamp[recent_path.attrib['value']] = 0
            case 'additionalInfo':
                additional_info = option_tag[0]  # `<map>`
            case _:
                pass

    # For all `additionalInfo` entries, also add the real timestamp
    if additional_info is not None:
        for entry_tag in additional_info:
            for option_tag in entry_tag[0][0]:
                if option_tag.tag == 'option' and option_tag.attrib.get('name', None) == 'projectOpenTimestamp':
                    path_to_timestamp[entry_tag.attrib['key']] = int(option_tag.attrib['value'])

    return [
        (timestamp, Path(path.replace('$USER_HOME$', str(Path.home()))))
        for path, timestamp in path_to_timestamp.items()
    ]


def find_config_path(parent_xdg_config_dir: Path, app_name: str) -> Path | None:
    """
    :param app_name:
    :return: The actual path to the relevant xml file, of the most recent configuration directory.
    """
    xdg_dir: Path = parent_xdg_config_dir
    if not xdg_dir.is_dir():
        return None

    # Dirs contains possibly multiple directories for a program, e.g.
    #
    # - `~/.config/JetBrains/PyCharm2021.3/`
    # - `~/.config/JetBrains/PyCharm2022.1/`
    #
    # Take the newest.
    try:
        dir_name: Path = max(f for f in xdg_dir.iterdir() if (xdg_dir / f).is_dir() and f.name.startswith(app_name))
    except ValueError:
        return None
    return xdg_dir / dir_name / 'options/recentProjects.xml'


def get_project_name(path: Path) -> str:
    try:
        with (path / '.idea/.name').open('r') as sr:
            return sr.read()
    except IOError:
        return path.name


class Plugin(PluginInstance, TriggerQueryHandler):
    def __init__(self):
        PluginInstance.__init__(self)
        TriggerQueryHandler.__init__(self)

    @override
    def defaultTrigger(self):
        return 'jb '

    @override
    def handleTriggerQuery(self, query: Query) -> None:
        matcher = Matcher(query.string)

        projects: list[IdeProject] = []

        for app_name, config in IDE_CONFIGS.items():
            config_path = find_config_path(config.parent_config_dir, app_name)
            if config_path is None:
                continue
            projects.extend(
                [
                    IdeProject(get_project_name(path), path, app_name, timestamp)
                    for timestamp, path in get_recent_projects(config_path)
                ]
            )

        # List all projects or the one corresponding to the query
        projects = [project for project in projects if matcher.match(str(project.path))]

        # The projects accessed the most recently comes first
        projects.sort(key=lambda project: -project.timestamp)

        projects_with_score: list[tuple[IdeProject, float]] = []
        for i, project in enumerate(projects):
            score = (1 - i) / len(projects)
            if matcher.match(project.name):
                score += 2.0
            if matcher.match(str(project.path.parent)):
                score += 1.0
            projects_with_score.append((project, score))
        projects_with_score.sort(key=lambda t: t[1], reverse=True)

        now = int(time.time() * 1000.0)

        items: list[Item] = []
        last_update: int
        project_path: Path
        app_name: str
        for (project_name, project_path, app_name, last_update), _ in projects_with_score:
            if not project_path.exists():
                continue
            desktop_file = IDE_CONFIGS[app_name].desktop_file
            if not desktop_file:
                continue

            launch_call: Callable[[str, Path], int] = (  # noqa: E731
                lambda desktop_file_=desktop_file, project_path_=project_path: runDetachedProcess(
                    ['gtk-launch', desktop_file_, str(project_path_)]
                )
            )
            item = StandardItem(
                id=self.id(),
                text=project_name,
                subtext=str(project_path),
                icon_factory=IDE_CONFIGS[app_name].icon_factory,
                actions=[
                    Action(
                        f'{md_name}/{now - last_update:015d}/{project_path}/{app_name}',
                        f'Open in {app_name}',
                        launch_call,
                    )
                ],
            )
            items.append(item)
        query.add(items)  # pyright: ignore[reportUnknownMemberType]
