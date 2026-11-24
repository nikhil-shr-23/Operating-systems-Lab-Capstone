"""Central logging setup.

Every module obtains its logger with ``get_logger("<module>")``.  Records go to
``logs/osrm.log`` (override with the OSRM_LOG_FILE environment variable) in the
format ``time | LEVEL | module | message``.  If the log file cannot be opened the
application keeps working (a NullHandler is used) - logging never crashes it.
"""
import logging
import os

from modules import LOG_DIR

_FORMAT = "%(asctime)s | %(levelname)s | %(modname)s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"
_configured = False


def log_path():
    """Return the path of the active log file."""
    return os.environ.get("OSRM_LOG_FILE") or os.path.join(LOG_DIR, "osrm.log")


class _ModuleFilter(logging.Filter):
    """Adds a short ``modname`` attribute ("scheduler" instead of "osrm.scheduler")."""

    def filter(self, record):
        record.modname = record.name.split(".", 1)[-1]
        return True


def _configure():
    global _configured
    if _configured:
        return
    root = logging.getLogger("osrm")
    root.setLevel(logging.DEBUG)
    root.propagate = False
    try:
        path = log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(logging.Formatter(_FORMAT, _DATEFMT))
        handler.addFilter(_ModuleFilter())
    except OSError:
        handler = logging.NullHandler()
    root.addHandler(handler)
    _configured = True


def get_logger(name):
    """Return the logger for module ``name`` (e.g. "scheduler")."""
    _configure()
    return logging.getLogger("osrm." + name)
