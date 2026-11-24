"""Input validation helpers shared by every module.

All problems with user supplied data are reported by raising
:class:`ValidationError` with a meaningful message - callers (the CLI and the
menu) catch it and print a friendly error instead of a traceback.
"""
import csv
import io
import json
import os

from modules.logger import get_logger

log = get_logger("validation")


class ValidationError(Exception):
    """Raised when user supplied data is missing, malformed or out of range."""


# ----------------------------------------------------------------- file I/O
def read_text_file(path, what="file"):
    """Read a text file, rejecting missing, unreadable or empty files."""
    if not path or not isinstance(path, str):
        raise ValidationError("No %s path given." % what)
    if not os.path.exists(path):
        raise ValidationError("%s not found: %s" % (what.capitalize(), path))
    if os.path.isdir(path):
        raise ValidationError("%s is a directory, not a file: %s" % (what.capitalize(), path))
    try:
        with io.open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        raise ValidationError("Cannot read %s %s: %s" % (what, path, exc))
    if not text.strip():
        raise ValidationError("%s is empty: %s" % (what.capitalize(), path))
    return text


def load_json(path, required_keys=(), what="JSON file"):
    """Load a JSON object from ``path`` and check that ``required_keys`` exist."""
    text = read_text_file(path, what)
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ValidationError("Malformed JSON in %s: %s" % (path, exc))
    if not isinstance(data, dict):
        raise ValidationError("%s must contain a JSON object at top level." % path)
    for key in required_keys:
        if key not in data:
            raise ValidationError("%s is missing required key '%s'." % (path, key))
    return data


# ------------------------------------------------------------------ numbers
def parse_int(value, name, minimum=None, maximum=None):
    """Convert ``value`` to int and enforce optional bounds."""
    if isinstance(value, bool):
        raise ValidationError("%s must be an integer, got %r." % (name, value))
    if isinstance(value, float):
        if value != int(value):
            raise ValidationError("%s must be an integer, got %r." % (name, value))
        value = int(value)
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValidationError("%s must be an integer, got %r." % (name, value))
    if minimum is not None and number < minimum:
        raise ValidationError("%s must be >= %d, got %d." % (name, minimum, number))
    if maximum is not None and number > maximum:
        raise ValidationError("%s must be <= %d, got %d." % (name, maximum, number))
    return number


def parse_int_list(value, name, minimum=None):
    """Parse '1 2 3' / '1,2,3' / [1, 2, 3] into a list of ints."""
    if isinstance(value, str):
        parts = [p for p in value.replace(",", " ").split() if p]
    elif isinstance(value, (list, tuple)):
        parts = list(value)
    else:
        raise ValidationError("%s must be a list of integers." % name)
    return [parse_int(p, "%s item" % name, minimum) for p in parts]


def validate_quantum(quantum):
    """Time quantum must be an integer > 0."""
    return parse_int(quantum, "Time quantum", 1)


def validate_frames(frames):
    """Number of frames must be an integer > 0."""
    return parse_int(frames, "Number of frames", 1)


def validate_reference_string(refs):
    """Reference string must be a non-empty list of non-negative integers."""
    pages = parse_int_list(refs, "Reference string", 0)
    if not pages:
        raise ValidationError("Reference string is empty.")
    return pages


# -------------------------------------------------------------- processes
def validate_processes(rows):
    """Validate (pid, arrival, burst, priority) rows; return normalised tuples."""
    if not rows:
        raise ValidationError("Process list is empty.")
    seen = set()
    result = []
    for row in rows:
        pid, arrival, burst, priority = row
        pid = str(pid).strip()
        if not pid:
            raise ValidationError("Process id must not be empty.")
        if pid in seen:
            raise ValidationError("Duplicate process id: %s" % pid)
        seen.add(pid)
        arrival = parse_int(arrival, "Arrival time of %s" % pid)
        burst = parse_int(burst, "Burst time of %s" % pid)
        priority = parse_int(priority, "Priority of %s" % pid)
        if arrival < 0:
            raise ValidationError("Arrival time of %s must not be negative (got %d)." % (pid, arrival))
        if burst <= 0:
            raise ValidationError("Burst time of %s must be greater than 0 (got %d)." % (pid, burst))
        if priority < 0:
            raise ValidationError("Priority of %s must not be negative (got %d)." % (pid, priority))
        result.append((pid, arrival, burst, priority))
    return result


def load_processes_csv(path):
    """Read a ``pid,arrival,burst,priority`` CSV into validated tuples."""
    text = read_text_file(path, "process CSV file")
    try:
        reader = csv.DictReader(io.StringIO(text))
        header = [h.strip().lower() for h in (reader.fieldnames or [])]
        for col in ("pid", "arrival", "burst"):
            if col not in header:
                raise ValidationError(
                    "Malformed CSV %s: missing column '%s' (expected pid,arrival,burst,priority)." % (path, col))
        rows = []
        for line_no, raw in enumerate(reader, start=2):
            rec = dict((k.strip().lower(), v) for k, v in raw.items() if k is not None)
            if all((v is None or not str(v).strip()) for v in rec.values()):
                continue  # blank line
            if None in raw.values() or None in raw or any(rec.get(c) is None for c in ("pid", "arrival", "burst")):
                raise ValidationError("Malformed CSV %s line %d: wrong number of fields." % (path, line_no))
            prio = rec.get("priority")
            prio = 0 if prio is None or not str(prio).strip() else prio
            rows.append((rec["pid"], rec["arrival"], rec["burst"], prio))
    except csv.Error as exc:
        raise ValidationError("Malformed CSV %s: %s" % (path, exc))
    return validate_processes(rows)


# ------------------------------------------------------------------- disk
def validate_disk(requests, head, size, direction="up"):
    """Validate a disk-scheduling problem; an empty request list is allowed."""
    size = parse_int(size, "Disk size", 1)
    head = parse_int(head, "Head position")
    if not 0 <= head <= size - 1:
        raise ValidationError("Head position %d is outside the disk range 0..%d." % (head, size - 1))
    reqs = parse_int_list(requests, "Disk request") if requests is not None else []
    for r in reqs:
        if not 0 <= r <= size - 1:
            raise ValidationError("Disk request %d is outside the disk range 0..%d." % (r, size - 1))
    direction = str(direction).strip().lower()
    if direction not in ("up", "down"):
        raise ValidationError("Direction must be 'up' or 'down', got %r." % direction)
    return reqs, head, size, direction


# ----------------------------------------------------------------- banker
def matrix(value, name):
    if not isinstance(value, (list, tuple)) or not value:
        raise ValidationError("%s must be a non-empty matrix (list of rows)." % name)
    rows = []
    for i, row in enumerate(value):
        if not isinstance(row, (list, tuple)):
            raise ValidationError("%s row %d is not a list." % (name, i))
        rows.append([parse_int(x, "%s[%d]" % (name, i)) for x in row])
    return rows


def validate_banker(available, maximum, allocation):
    """Check dimensions, signs and allocation <= max for Banker's algorithm."""
    avail = parse_int_list(available, "Available vector")
    if not avail:
        raise ValidationError("Available vector is empty.")
    mx = matrix(maximum, "Max matrix")
    al = matrix(allocation, "Allocation matrix")
    m = len(avail)
    if len(mx) != len(al):
        raise ValidationError("Matrix dimensions mismatch: Max has %d rows but Allocation has %d." % (len(mx), len(al)))
    for name, mat in (("Max", mx), ("Allocation", al)):
        for i, row in enumerate(mat):
            if len(row) != m:
                raise ValidationError("Matrix dimensions mismatch: %s row %d has %d columns, expected %d." % (
                    name, i, len(row), m))
    if any(v < 0 for v in avail):
        raise ValidationError("Available vector contains a negative value.")
    for name, mat in (("Max", mx), ("Allocation", al)):
        for i, row in enumerate(mat):
            if any(v < 0 for v in row):
                raise ValidationError("%s matrix row %d contains a negative value." % (name, i))
    for i in range(len(mx)):
        for j in range(m):
            if al[i][j] > mx[i][j]:
                raise ValidationError("Allocation exceeds Max for P%d, resource %d (%d > %d)." % (
                    i, j, al[i][j], mx[i][j]))
    return avail, mx, al


def validate_request(request, num_resources):
    """A resource request vector must have the right length and no negatives."""
    req = parse_int_list(request, "Request vector")
    if len(req) != num_resources:
        raise ValidationError("Request vector has %d entries, expected %d." % (len(req), num_resources))
    if any(v < 0 for v in req):
        raise ValidationError("Request vector contains a negative value.")
    return req


# ----------------------------------------------------------------- memory
def validate_partitions(sizes, procs):
    """Validate fixed partition sizes and (name, size) process requests."""
    parts = parse_int_list(sizes, "Partition size", 1)
    if not parts:
        raise ValidationError("Partition list is empty.")
    out = []
    seen = set()
    for item in procs or []:
        name, size = item
        name = str(name).strip()
        if not name or name in seen:
            raise ValidationError("Process name %r is empty or duplicated." % name)
        seen.add(name)
        out.append((name, parse_int(size, "Size of %s" % name, 1)))
    if not out:
        raise ValidationError("Process list for partition allocation is empty.")
    return parts, out
