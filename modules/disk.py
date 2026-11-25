"""Disk-head scheduling algorithms.

Each algorithm builds the *path* of head positions it visits; total head
movement is the sum of absolute differences along that path.

* SCAN / C-SCAN always travel to the physical end of the disk (0 or size-1) in
  the current direction before turning, as in the textbook definition.
* C-SCAN's return jump (e.g. size-1 -> 0) IS counted as head movement.
* LOOK / C-LOOK only travel as far as the last request; C-LOOK's jump back to
  the farthest pending request is counted.
* A request exactly at the head position belongs to the current direction.
"""
import random
from collections import Counter
from dataclasses import dataclass, field
from typing import List

from modules.logger import get_logger
from modules.validation import ValidationError, validate_disk

log = get_logger("disk")

DISK_ALGORITHMS = ["FCFS", "SSTF", "SCAN", "C-SCAN", "LOOK", "C-LOOK"]

DESCRIPTIONS = {
    "FCFS": "First-Come First-Served: serve requests in arrival order (fair, but long seeks).",
    "SSTF": "Shortest Seek Time First: always go to the nearest request (low movement, may starve).",
    "SCAN": "Elevator: sweep to the disk edge, then reverse, serving requests on the way.",
    "C-SCAN": "Circular SCAN: sweep one way only; jump back to the other edge and sweep again.",
    "LOOK": "Like SCAN, but reverse at the last request instead of the disk edge.",
    "C-LOOK": "Like C-SCAN, but jump back to the farthest pending request, not the edge.",
}


@dataclass
class DiskResult:
    """Head path, service order and cost of one disk-scheduling run."""
    algo: str
    path: List[int]
    total: int
    direction: str = "up"
    service_order: List[int] = field(default_factory=list)
    seek_ms: float = 1.0

    @property
    def n_requests(self):
        return len(self.service_order)

    @property
    def avg_seek(self):
        """Average head movement per serviced request (cylinders)."""
        return self.total / float(self.n_requests) if self.n_requests else 0.0

    @property
    def seek_time(self):
        """Total seek time in ms at ``seek_ms`` per cylinder."""
        return self.total * self.seek_ms

    @property
    def steps(self):
        """Per-move head movement (cylinders) along the path."""
        return [abs(b - a) for a, b in zip(self.path, self.path[1:])]


def _total(path):
    return sum(abs(b - a) for a, b in zip(path, path[1:]))


def _sstf(reqs, head):
    remaining, path, pos = list(reqs), [head], head
    while remaining:
        nxt = min(remaining, key=lambda r: abs(r - pos))
        remaining.remove(nxt)
        path.append(nxt)
        pos = nxt
    return path


def _groups(reqs, head, direction):
    """Split requests into (ahead in travel order, behind in return order)."""
    if direction == "up":
        ahead = sorted(r for r in reqs if r >= head)
        behind = sorted((r for r in reqs if r < head), reverse=True)
    else:
        ahead = sorted((r for r in reqs if r <= head), reverse=True)
        behind = sorted(r for r in reqs if r > head)
    return ahead, behind


def normalise_algo(algo):
    """Map 'cscan', 'c_scan', 'C-Scan' ... to the canonical name."""
    key = str(algo).strip().upper().replace("_", "-")
    key = {"CSCAN": "C-SCAN", "CLOOK": "C-LOOK"}.get(key, key)
    if key not in DISK_ALGORITHMS:
        raise ValidationError("Unknown disk algorithm %r (choose from %s)." % (algo, ", ".join(DISK_ALGORITHMS)))
    return key


def _service_order(key, reqs, path):
    """Order in which requests are actually served (turn-around points excluded)."""
    if key == "FCFS":
        return list(reqs)
    pending, order = Counter(reqs), []
    for p in path:
        if pending.get(p):
            order += [p] * pending.pop(p)
    return order


def schedule_disk(algo, requests, head, size, direction="up", seek_ms=1.0, quiet=False):
    """Compute head path and cost for one algorithm (``quiet`` skips the log line)."""
    reqs, head, size, direction = validate_disk(requests, head, size, direction)
    key = normalise_algo(algo)
    end = size - 1 if direction == "up" else 0
    other_end = 0 if direction == "up" else size - 1
    path = [head]
    if reqs:
        ahead, behind = _groups(reqs, head, direction)
        if key == "FCFS":
            path += reqs
        elif key == "SSTF":
            path = _sstf(reqs, head)
        elif key == "SCAN":
            path += ahead + [end] + behind
        elif key == "C-SCAN":
            path += ahead + [end]
            if behind:
                path += [other_end] + behind[::-1]
        elif key == "LOOK":
            path += ahead + behind
        elif key == "C-LOOK":
            path += ahead + behind[::-1]
    # drop zero-length repeats (e.g. a request already at the disk end)
    clean = [path[0]]
    for p in path[1:]:
        if p != clean[-1]:
            clean.append(p)
    res = DiskResult(key, clean, _total(clean), direction, _service_order(key, reqs, clean), float(seek_ms))
    if not quiet:
        log.info("%s head=%d size=%d dir=%s requests=%d total_movement=%d", key, head, size, direction,
                 len(reqs), res.total)
    return res


def compare_disk(requests, head, size, direction="up", seek_ms=1.0, quiet=False):
    """Run all six disk-scheduling algorithms on the same input."""
    return [schedule_disk(a, requests, head, size, direction, seek_ms, quiet) for a in DISK_ALGORITHMS]


def random_experiment(size, queue_lengths, trials=200, seed=2024, direction="up"):
    """Mean total head movement per algorithm over random queues.

    Returns {algo: [mean for each queue length]}.  Seeded, so it is reproducible.
    """
    rng = random.Random(seed)
    sums = dict((a, [0.0] * len(queue_lengths)) for a in DISK_ALGORITHMS)
    for i, n in enumerate(queue_lengths):
        for _ in range(trials):
            reqs = [rng.randrange(size) for _ in range(n)]
            head = rng.randrange(size)
            for r in compare_disk(reqs, head, size, direction, quiet=True):
                sums[r.algo][i] += r.total
    log.info("random experiment: size=%d lengths=%s trials=%d seed=%d", size, queue_lengths, trials, seed)
    return dict((a, [round(v / trials, 1) for v in vals]) for a, vals in sums.items())


def random_queue(n, size, seed=None):
    """n random cylinders in 0..size-1 (reproducible with a seed)."""
    rng = random.Random(seed)
    return [rng.randrange(size) for _ in range(n)]
