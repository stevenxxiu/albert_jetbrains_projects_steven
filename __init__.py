# -*- coding: utf-8 -*-

'''List and open JetBrains IDE projects.'''
import time
from pathlib import Path
from xml.etree import ElementTree

from albert import Item, ProcAction, iconLookup  # pylint: disable=import-error


__title__ = 'Jetbrains IDE Projects'
__version__ = '0.4.5'
__triggers__ = 'jb '
__authors__ = 'Markus Richter, Thomas Queste'

default_icon = str(Path(__file__).parent / 'icons/jetbrains.svg')

JETBRAINS_XDG_CONFIG_DIR = Path.home() / '.config/JetBrains'

IDE_CONFIGS = [  # <App name>, <Icon name>, <Desktop file name>
    ('CLion', 'clion', 'jetbrains-clion.desktop'),
    ('IntelliJIdea', 'idea', 'jetbrains-idea.desktop'),
    ('PyCharm', 'pycharm', 'pycharm-professional.desktop'),
]


def find_icons():
    return {app_name: iconLookup(icon_name) or default_icon for app_name, icon_name, desktop_file in IDE_CONFIGS}


# parse the xml at path, return all recent project paths and the time they were last open
def get_proj(path):
    root = ElementTree.parse(path).getroot()  # type:ElementTree.Element
    add_info = None
    path2timestamp = {}
    for option_tag in root[0]:  # type:ElementTree.Element
        if option_tag.attrib['name'] == 'recentPaths':
            for recent_path in option_tag[0]:
                path2timestamp[recent_path.attrib['value']] = 0
        elif option_tag.attrib['name'] == 'additionalInfo':
            add_info = option_tag[0]

    # for all additionalInfo entries, also add the real timestamp.
    if add_info is not None:
        for entry_tag in add_info:
            for option_tag in entry_tag[0][0]:
                if (
                    option_tag.tag == 'option'
                    and 'name' in option_tag.attrib
                    and option_tag.attrib['name'] == 'projectOpenTimestamp'
                ):
                    path2timestamp[entry_tag.attrib['key']] = int(option_tag.attrib['value'])

    return [(timestamp, path.replace('$USER_HOME$', str(Path.home()))) for path, timestamp in path2timestamp.items()]


# finds the actual path to the relevant xml file of the most recent configuration directory
def find_config_path(app_name: str):
    xdg_dir = JETBRAINS_XDG_CONFIG_DIR
    if not xdg_dir.is_dir():
        return None

    # dirs contains possibly multiple directories for a program (eg. .GoLand2018.1 and .GoLand2017.3)
    dirs = [f for f in xdg_dir.iterdir() if (xdg_dir / f).is_dir() and f.name.startswith(app_name)]
    # take the newest
    dirs.sort(reverse=True)
    if not dirs:
        return None
    return xdg_dir / dirs[0] / 'options/recentProjects.xml'


# The entry point for the plugin, will be called by albert.
def handleQuery(query):
    if not query.isTriggered:
        return None
    desktop_files = {app_name: desktop_file for app_name, icon_name, desktop_file in IDE_CONFIGS}
    icons = find_icons()
    # an array of tuples representing the project([timestamp,path,app name])
    projects = []

    for app_name, icon_name, _desktop_file in IDE_CONFIGS:
        # get configuration file path
        full_config_path = find_config_path(app_name)
        if full_config_path is None:
            continue
        # add all recently opened projects
        projects.extend([[e[0], e[1], app_name] for e in get_proj(full_config_path)])

    # List all projects or the one corresponding to the query
    if query.string:
        projects = [p for p in projects if p[1].lower().find(query.string.lower()) != -1]

    # disable automatic sorting
    query.disableSort()
    # sort by last modified, most recent first.
    projects.sort(key=lambda s: s[0], reverse=True)

    items = []
    now = int(time.time() * 1000.0)
    for last_update, project_path, app_name in projects:
        if not Path(project_path).exists():
            continue
        project_dir = Path(project_path).name
        desktop_file = desktop_files[app_name]
        if not desktop_file:
            continue

        output_entry = Item(
            id=f'{now - last_update:015d}-{project_path}-{app_name}',
            icon=icons[app_name],
            text=project_dir,
            subtext=project_path,
            completion=__triggers__ + project_dir,
            actions=[ProcAction(text=f'Open in {app_name}', commandline=['gtk-launch', desktop_file, project_path])],
        )
        items.append(output_entry)

    return items
