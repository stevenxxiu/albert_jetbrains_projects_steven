# Albert Launcher JetBrains Extension
List and open *JetBrains* IDE projects.

## Install
To install, copy or symlink this directory to `~/.local/share/albert/org.albert.extension.python/modules/jetbrains_projects_steven/`.

## Development Setup
To setup the project for development, run:

    $ cd jetbrains_projects_steven/
    $ pre-commit install --hook-type pre-commit --hook-type commit-msg

To lint and format files, run:

    $ pre-commit run --all-files
