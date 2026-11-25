"""Bridge to the Bash helper scripts (subprocess with timeout and error handling)."""
import os
import subprocess

from modules import OUTPUT_DIR, SCRIPT_DIR
from modules.logger import get_logger, log_path
from modules.validation import ValidationError, parse_int

log = get_logger("bashtools")

DEFAULT_TIMEOUT = 20


class BashToolError(Exception):
    """A helper script failed, timed out or could not be started."""


def run_script(name, args=(), timeout=DEFAULT_TIMEOUT):
    """Run scripts/<name> with args; return its stdout or raise BashToolError."""
    path = os.path.join(SCRIPT_DIR, name)
    if not os.path.isfile(path):
        raise BashToolError("Script not found: %s" % path)
    cmd = ["bash", path] + [str(a) for a in args]
    log.info("running %s", " ".join(cmd))
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        log.error("%s timed out after %ss", name, timeout)
        raise BashToolError("%s timed out after %s seconds." % (name, timeout))
    except OSError as exc:
        log.error("cannot start %s: %s", name, exc)
        raise BashToolError("Cannot start %s: %s" % (name, exc))
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout).strip() or "exit status %d" % proc.returncode
        log.error("%s failed (rc=%d): %s", name, proc.returncode, msg)
        raise BashToolError("%s failed: %s" % (name, msg))
    return proc.stdout


def gen_requests(n, seed=None, out_path=None, disk_size=200):
    """Generate a random disk workload JSON via gen_requests.sh; returns the JSON path."""
    n = parse_int(n, "Number of requests", 1, 1000)
    disk_size = parse_int(disk_size, "Disk size", 2, 100000)
    seed = parse_int(seed, "Seed", 0) if seed not in (None, "") else ""
    out_path = out_path or os.path.join(OUTPUT_DIR, "generated_requests.json")
    try:
        run_script("gen_requests.sh", [n, seed, out_path, disk_size])
    except BashToolError as exc:
        raise ValidationError(str(exc))
    return out_path


def sysinfo():
    """Return the live system snapshot text."""
    return run_script("sysinfo.sh")


def log_summary(path=None):
    """Return the log summary text."""
    return run_script("log_summary.sh", [path or log_path()])
