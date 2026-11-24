"""Storage management: disk-head scheduling and file allocation.

Disk scheduling
---------------
Each algorithm builds the *path* of head positions it visits; total head
movement is the sum of absolute differences along that path.

* SCAN / C-SCAN always travel to the physical end of the disk (0 or size-1) in
  the current direction before turning, as in the textbook definition.
* C-SCAN's return jump (e.g. size-1 -> 0) IS counted as head movement.
* LOOK / C-LOOK only travel as far as the last request; C-LOOK's jump back to
  the farthest pending request is counted.
* A request exactly at the head position belongs to the current direction.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from modules.logger import get_logger
from modules.validation import ValidationError, parse_int, validate_disk

log = get_logger("storage")

DISK_ALGORITHMS = ["FCFS", "SSTF", "SCAN", "C-SCAN", "LOOK", "C-LOOK"]
ALLOC_METHODS = ["contiguous", "linked", "indexed"]


@dataclass
class DiskResult:
    """Head path and total movement for one disk-scheduling algorithm."""
    algo: str
    path: List[int]
    total: int
    direction: str = "up"


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


def schedule_disk(algo, requests, head, size, direction="up"):
    """Compute head path and total movement for one algorithm."""
    reqs, head, size, direction = validate_disk(requests, head, size, direction)
    key = str(algo).strip().upper().replace("_", "-")
    if key == "CSCAN":
        key = "C-SCAN"
    if key == "CLOOK":
        key = "C-LOOK"
    if key not in DISK_ALGORITHMS:
        raise ValidationError("Unknown disk algorithm %r (choose from %s)." % (algo, ", ".join(DISK_ALGORITHMS)))
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
    res = DiskResult(key, clean, _total(clean), direction)
    log.info("%s head=%d size=%d dir=%s requests=%d total_movement=%d", key, head, size, direction,
             len(reqs), res.total)
    return res


def compare_disk(requests, head, size, direction="up"):
    """Run all six disk-scheduling algorithms on the same input."""
    return [schedule_disk(a, requests, head, size, direction) for a in DISK_ALGORITHMS]


# ------------------------------------------------------------ file allocation
@dataclass
class FileEntry:
    """Directory entry of a file on the simulated disk."""
    name: str
    size: int
    method: str
    blocks: List[int]
    index_block: Optional[int] = None


class SimDisk:
    """A simulated disk with a bitmap (0 = free, 1 = used) and a flat directory."""

    def __init__(self, total_blocks):
        self.total = parse_int(total_blocks, "Total disk blocks", 1)
        self.bitmap = [0] * self.total
        self.files = {}          # type: Dict[str, FileEntry]

    # --- free-space queries
    def free_count(self):
        return self.bitmap.count(0)

    def free_runs(self):
        """List of (start, length) of contiguous free extents."""
        runs, start = [], None
        for i, b in enumerate(self.bitmap + [1]):
            if b == 0 and start is None:
                start = i
            elif b == 1 and start is not None:
                runs.append((start, i - start))
                start = None
        return runs

    def largest_free_run(self):
        return max([l for _, l in self.free_runs()] or [0])

    def external_fragmentation(self):
        """Percent of free space NOT in the largest free extent (0 if no free space)."""
        free = self.free_count()
        return 0.0 if free == 0 else 100.0 * (free - self.largest_free_run()) / free

    # --- allocation
    def _plan(self, size, method):
        """Pick blocks without touching the disk; raise ValidationError if impossible."""
        free = [i for i, b in enumerate(self.bitmap) if b == 0]
        if method == "contiguous":
            for start, length in self.free_runs():
                if length >= size:
                    return list(range(start, start + size)), None
            if len(free) >= size:
                raise ValidationError("Insufficient contiguous space for %d blocks (free=%d, largest run=%d)." % (
                    size, len(free), self.largest_free_run()))
            raise ValidationError("Insufficient space: need %d blocks, only %d free." % (size, len(free)))
        needed = size + (1 if method == "indexed" else 0)
        if len(free) < needed:
            raise ValidationError("Insufficient space: need %d blocks, only %d free." % (needed, len(free)))
        if method == "linked":
            return free[:size], None
        return free[1:size + 1], free[0]

    def create_file(self, name, size, method):
        """Allocate a file.  On ANY error the disk state is left untouched."""
        name = str(name).strip() if name is not None else ""
        if not name:
            raise ValidationError("File name must not be empty.")
        size = parse_int(size, "File size", 1)
        method = str(method).strip().lower()
        if method not in ALLOC_METHODS:
            raise ValidationError("Unknown allocation method %r (choose from %s)." % (method, ", ".join(ALLOC_METHODS)))
        if name in self.files:
            raise ValidationError("Duplicate file name: %s" % name)
        if size > self.total:
            raise ValidationError("File size %d exceeds the disk capacity of %d blocks." % (size, self.total))
        blocks, idx = self._plan(size, method)        # may raise - nothing mutated yet
        for b in blocks + ([idx] if idx is not None else []):
            self.bitmap[b] = 1
        entry = FileEntry(name, size, method, blocks, idx)
        self.files[name] = entry
        log.info("created %s (%d blocks, %s) at %s", name, size, method, blocks[:8])
        return entry

    def delete_file(self, name):
        """Free a file's blocks."""
        if name not in self.files:
            raise ValidationError("File not found: %s" % name)
        e = self.files.pop(name)
        for b in e.blocks + ([e.index_block] if e.index_block is not None else []):
            self.bitmap[b] = 0
        log.info("deleted %s", name)

    def snapshot(self):
        """Hashable copy of the state, used to prove failed operations change nothing."""
        return (tuple(self.bitmap), tuple(sorted(self.files)))

    def render(self, width=50):
        """ASCII bitmap: '#' used, '.' free."""
        s = "".join("#" if b else "." for b in self.bitmap)
        return "\n".join(s[i:i + width] for i in range(0, len(s), width))


def access_cost(entry):
    """Disk reads needed to reach each block of a file (direct access)."""
    n = entry.size
    if entry.method == "contiguous":
        costs = [1] * n
    elif entry.method == "linked":
        costs = [k + 1 for k in range(n)]
    else:
        costs = [2] * n
    return costs


def overhead_entries(entry):
    """Metadata entries needed: start+length / pointers / index entries."""
    if entry.method == "contiguous":
        return 2
    return entry.size + 1


def apply_operations(disk, ops):
    """Apply ('create'|'delete', name, size) operations; collect rejections.

    Returns a list of (op_text, error_message) for rejected operations.
    """
    rejected = []
    for op in ops:
        kind, name, size, method = op
        try:
            if kind == "create":
                disk.create_file(name, size, method)
            elif kind == "delete":
                disk.delete_file(name)
            else:
                raise ValidationError("Unknown operation %r." % kind)
        except ValidationError as exc:
            rejected.append(("%s %s" % (kind, name), str(exc)))
            log.warning("rejected %s %s: %s", kind, name, exc)
    return rejected


def compare_allocation(total_blocks, ops):
    """Run the same workload under each allocation method on a fresh disk.

    ``ops`` is a list of dicts: {op: create|delete, name, size}.
    """
    summary = {}
    for method in ALLOC_METHODS:
        disk = SimDisk(total_blocks)
        planned = [(o.get("op", "create"), o.get("name"), o.get("size", 0), method) for o in ops]
        rejected = apply_operations(disk, planned)
        files = list(disk.files.values())
        costs = [c for f in files for c in access_cost(f)]
        summary[method] = {
            "created": len(files),
            "rejected": rejected,
            "used_blocks": disk.total - disk.free_count(),
            "free_blocks": disk.free_count(),
            "free_fragments": len(disk.free_runs()),
            "largest_free_run": disk.largest_free_run(),
            "external_frag_pct": round(disk.external_fragmentation(), 1),
            "avg_access_cost": round(sum(costs) / float(len(costs)), 2) if costs else 0.0,
            "worst_access_cost": max(costs) if costs else 0,
            "overhead_entries": sum(overhead_entries(f) for f in files),
            "extra_blocks": sum(1 for f in files if f.index_block is not None),
            "map": disk.render(),
            "disk": disk,
        }
    return summary
