import time
from pathlib import Path
from typing import Dict, NamedTuple
from xml.etree import ElementTree

from albert import Action, Item, Query, QueryHandler, runDetachedProcess  # pylint: disable=import-error


md_iid = '0.5'
md_version = '1.0'
md_name = 'JetBrains Projects User'
md_description = 'List and open JetBrains IDE projects.'
md_url = 'https://github.com/stevenxxiu/albert_jetbrains_projects_user'
md_maintainers = '@stevenxxiu'

ICON_PATH = str(Path(__file__).parent / 'icons/jetbrains.svg')
JETBRAINS_XDG_CONFIG_DIR = Path.home() / '.config/JetBrains'


class IdeConfig(NamedTuple):
    icon_name: str
    desktop_file: str


IDE_CONFIGS: Dict[str, IdeConfig] = {
    'CLion': IdeConfig(icon_name='/usr/share/pixmaps/clion.svg', desktop_file='jetbrains-clion.desktop'),
    'IntelliJIdea': IdeConfig(
        icon_name='/usr/share/pixmaps/intellij-idea-ultimate-edition.svg', desktop_file='jetbrains-idea.desktop'
    ),
    'PyCharm': IdeConfig(icon_name='xdg:pycharm', desktop_file='pycharm-professional.desktop'),
}


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


class Plugin(QueryHandler):
    @staticmethod
    def id() -> str:
        return __name__

    @staticmethod
    def name() -> str:
        return md_name

    @staticmethod
    def description() -> str:
        return md_description

    @staticmethod
    def defaultTrigger() -> str:
        return 'jb'

    @staticmethod
    def handleQuery(query: Query) -> None:
        query_str = query.string.strip()

        # `[(project_timestamp, project_path, app_name)]`
        projects: list[(int, Path, str)] = []

        for app_name in IDE_CONFIGS:
            config_path = find_config_path(app_name)
            if config_path is None:
                continue
            projects.extend([(timestamp, path, app_name) for timestamp, path in get_recent_projects(config_path)])

        # List all projects or the one corresponding to the query
        projects = [project for project in projects if query_str.lower() in str(project[1]).lower()]

        # Sort by last modified. Most recent first.
        projects.sort(key=lambda s: s[0], reverse=True)

        now = int(time.time() * 1000.0)

        last_update: int
        project_path: Path
        app_name: str
        for last_update, project_path, app_name in projects:
            if not project_path.exists():
                continue
            project_dir = project_path.name
            desktop_file = IDE_CONFIGS[app_name].desktop_file
            if not desktop_file:
                continue

            item = Item(
                id=f'{md_name}/{now - last_update:015d}/{project_path}/{app_name}',
                text=project_dir,
                subtext=str(project_path),
                icon=[IDE_CONFIGS[app_name].icon_name, ICON_PATH],
                completion=project_dir,
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
