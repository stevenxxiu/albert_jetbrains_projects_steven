import time
from pathlib import Path
from typing import NamedTuple
from xml.etree import ElementTree

from albert import Action, Item, Query, QueryHandler, runDetachedProcess  # pylint: disable=import-error


md_iid = '0.5'
md_version = '1.0'
md_name = 'JetBrains Projects Steven'
md_description = 'List and open JetBrains IDE projects'
md_url = 'https://github.com/stevenxxiu/albert_jetbrains_projects_steven'
md_maintainers = '@stevenxxiu'

ICON_PATH = str(Path(__file__).parent / 'icons/jetbrains.svg')
JETBRAINS_XDG_CONFIG_DIR = Path.home() / '.config/JetBrains'


class IdeConfig(NamedTuple):
    icon_name: str
    desktop_file: str


IDE_CONFIGS: dict[str, IdeConfig] = {
    'CLion': IdeConfig(icon_name='xdg:clion', desktop_file='jetbrains-clion.desktop'),
    'IntelliJIdea': IdeConfig(icon_name='xdg:intellij-idea-ultimate-edition', desktop_file='jetbrains-idea.desktop'),
    'PyCharm': IdeConfig(icon_name='xdg:pycharm', desktop_file='pycharm-professional.desktop'),
}


class IdeProject(NamedTuple):
    name: str
    path: Path
    app_name: str
    timestamp: int


def get_recent_projects(path: Path) -> list[(int, Path)]:
    '''
    :param path: Parse the xml at `path`.
    :return: All recent project paths and the time they were last open.
    '''
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


def find_config_path(app_name: str) -> Path | None:
    '''
    :param app_name:
    :return: The actual path to the relevant xml file, of the most recent configuration directory.
    '''
    xdg_dir: Path = JETBRAINS_XDG_CONFIG_DIR
    if not xdg_dir.is_dir():
        return None

    # Dirs contains possibly multiple directories for a program, e.g.
    #
    # - `~/.config/JetBrains/PyCharm2021.3/`
    # - `~/.config/JetBrains/PyCharm2022.1/`
    #
    # Take the newest.
    dir_name: Path = max(f for f in xdg_dir.iterdir() if (xdg_dir / f).is_dir() and f.name.startswith(app_name))
    return xdg_dir / dir_name / 'options/recentProjects.xml'


def get_project_name(path: Path) -> str:
    try:
        with (path / '.idea/.name').open('r') as sr:
            return sr.read()
    except IOError:
        return path.name


class Plugin(QueryHandler):
    def id(self) -> str:
        return __name__

    def name(self) -> str:
        return md_name

    def description(self) -> str:
        return md_description

    def defaultTrigger(self) -> str:
        return 'jb '

    def handleQuery(self, query: Query) -> None:
        query_str = query.string.strip()

        projects: list[IdeProject] = []

        for app_name in IDE_CONFIGS:
            config_path = find_config_path(app_name)
            if config_path is None:
                continue
            projects.extend(
                [
                    IdeProject(get_project_name(path), path, app_name, timestamp)
                    for timestamp, path in get_recent_projects(config_path)
                ]
            )

        # List all projects or the one corresponding to the query
        projects = [project for project in projects if query_str.lower() in str(project.path).lower()]
        if not projects:
            return

        # The projects accessed the most recently comes first
        timestamp_ranks = sorted(range(len(projects)), key=lambda i: -projects[i].timestamp)
        path_to_timestamp_rank = {
            project.path: timestamp_rank for project, timestamp_rank in zip(projects, timestamp_ranks)
        }

        # Rank projects
        projects.sort(
            key=lambda project: (
                (1 - path_to_timestamp_rank[project.path] / len(path_to_timestamp_rank))
                + 2.0 * int(query_str in project.name)
                + 1.0 * int(f'/{query_str}' in str(project.path.parent))
            ),
            reverse=True,
        )

        now = int(time.time() * 1000.0)

        last_update: int
        project_path: Path
        app_name: str
        for project_name, project_path, app_name, last_update in projects:
            if not project_path.exists():
                continue
            desktop_file = IDE_CONFIGS[app_name].desktop_file
            if not desktop_file:
                continue

            item = Item(
                id=f'{md_name}/{now - last_update:015d}/{project_path}/{app_name}',
                text=project_name,
                subtext=str(project_path),
                icon=[IDE_CONFIGS[app_name].icon_name, ICON_PATH],
                completion=f'{query.trigger}{project_name}',
                actions=[
                    Action(
                        f'{md_name}/{now - last_update:015d}/{project_path}/{app_name}',
                        f'Open in {app_name}',
                        lambda desktop_file_=desktop_file, project_path_=project_path: runDetachedProcess(
                            ['gtk-launch', desktop_file_, str(project_path_)]
                        ),
                    )
                ],
            )
            query.add(item)
