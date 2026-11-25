"""Disk Scheduling Simulator: reusable modules."""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
LOG_DIR = os.path.join(BASE_DIR, "logs")
SCRIPT_DIR = os.path.join(BASE_DIR, "scripts")

APP_NAME = "Disk Scheduling Simulator"
AUTHOR = "Nikhil Sharma | Roll No 2401010084 | B.Tech CSE (Core), Section C"


def ensure_dirs():
    """Create the output and log directories if they do not exist."""
    for d in (OUTPUT_DIR, LOG_DIR):
        os.makedirs(d, exist_ok=True)
