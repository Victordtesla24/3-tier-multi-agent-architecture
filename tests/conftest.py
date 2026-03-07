"""Pytest configuration — redirect CrewAI and appdirs storage before any imports."""
import os

# CrewAI's db_storage_path() runs at module-load time (class default param) and calls
# appdirs.user_data_dir() which on macOS resolves to ~/Library/Application Support/.
# On restricted filesystems, mkdir there fails. We monkey-patch appdirs BEFORE crewai
# loads to redirect all storage to /tmp.

_TMP_STORAGE = "/tmp/crewai_test_storage"
os.makedirs(_TMP_STORAGE, exist_ok=True)

os.environ["CREWAI_STORAGE_DIR"] = _TMP_STORAGE
os.environ["CREWAI_HOME"] = _TMP_STORAGE

# Monkey-patch appdirs before crewai import
try:
    import appdirs as _appdirs

    _orig_user_data_dir = _appdirs.user_data_dir

    def _patched_user_data_dir(appname=None, appauthor=None, version=None, roaming=False):
        base = os.path.join(_TMP_STORAGE, "appdirs_data")
        if appname:
            base = os.path.join(base, appname)
        os.makedirs(base, exist_ok=True)
        return base

    _appdirs.user_data_dir = _patched_user_data_dir
except ImportError:
    pass
