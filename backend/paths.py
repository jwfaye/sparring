"""Where Sparring finds its shipped files and keeps the user's data, in a clone or once installed (SP-PACKAGING).

Shipped files (the web page `app/` and the banks `bank/`):
- in a clone, the directories next to `server.py` (`ROOT`), exactly as before packaging;
- once installed with pip or pipx, the copies shipped inside the `sparring_data` package.

Data directory (interview answers, `theory[/<profile>]/answers.sqlite3`):
- `SPARRING_DATA_DIR` when set and non-empty;
- else `<root>/data` in a clone, so nothing changes for a checkout;
- else the per-user data directory: `$XDG_DATA_HOME/sparring` or `~/.local/share/sparring` on Linux,
  `~/Library/Application Support/sparring` on macOS, `%LOCALAPPDATA%\\sparring` on Windows.
"""

import importlib.resources
import os
import pathlib
import sys

APP_NAME = "sparring"
DATA_PACKAGE = "sparring_data"
DATA_ENV_VAR = "SPARRING_DATA_DIR"

ROOT: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def is_clone() -> bool:
    """True when `server.py` sits next to `app/` and `bank/`: a checkout or an editable install."""
    return all(os.path.isdir(os.path.join(ROOT, name)) for name in ("app", "bank"))


def _packaged_dir(name: str) -> str | None:
    """The directory `name` inside the installed `sparring_data` package, or None when it is not there."""
    try:
        candidate = importlib.resources.files(DATA_PACKAGE).joinpath(name)
    except ModuleNotFoundError:
        return None
    if isinstance(candidate, pathlib.Path) and candidate.is_dir():
        return str(candidate)
    return None


def resource_dir(name: str) -> str:
    """The directory of a shipped resource (`app` or `bank`): next to `server.py` in a clone, else in the package."""
    local = os.path.join(ROOT, name)
    if is_clone():
        return local
    packaged = _packaged_dir(name)
    if packaged is not None:
        return packaged
    raise FileNotFoundError(f"{name}/ not found next to server.py ({ROOT}) nor in the {DATA_PACKAGE} package")


def user_data_home() -> str:
    """The platform's per-user data directory, without the application name."""
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return xdg
    if sys.platform == "win32":
        return os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    return os.path.join(os.path.expanduser("~"), ".local", "share")


def data_dir() -> str:
    """Where the user's data lives: `SPARRING_DATA_DIR`, else `<root>/data` in a clone, else the per-user directory."""
    override = os.environ.get(DATA_ENV_VAR)
    if override:
        return override
    if is_clone():
        return os.path.join(ROOT, "data")
    return os.path.join(user_data_home(), APP_NAME)
