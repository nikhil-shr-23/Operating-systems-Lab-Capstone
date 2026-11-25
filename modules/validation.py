"""Input validation helpers shared by every module.

All problems with user supplied data are reported by raising
:class:`ValidationError` with a meaningful message - callers (the CLI and the
menu) catch it and print a friendly error instead of a traceback.
"""
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


def parse_float(value, name, minimum=None):
    """Convert ``value`` to float and enforce an optional lower bound."""
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        raise ValidationError("%s must be a number, got %r." % (name, value))
    if number != number or number in (float("inf"), float("-inf")):
        raise ValidationError("%s must be a finite number, got %r." % (name, value))
    if minimum is not None and number < minimum:
        raise ValidationError("%s must be >= %g, got %g." % (name, minimum, number))
    return number


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
