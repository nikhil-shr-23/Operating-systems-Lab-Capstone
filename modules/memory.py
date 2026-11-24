"""Memory management: page replacement and fixed-partition allocation."""
from dataclasses import dataclass, field
from typing import List, Optional

from modules.logger import get_logger
from modules.validation import (ValidationError, validate_frames,
                                validate_partitions, validate_reference_string)

log = get_logger("memory")

PAGE_ALGORITHMS = ["FIFO", "LRU", "Optimal", "Clock"]
FIT_STRATEGIES = ["first", "best", "worst"]
BELADY_STRING = [1, 2, 3, 4, 1, 2, 5, 1, 2, 3, 4, 5]


@dataclass
class Step:
    """One reference: page, frame contents afterwards, fault flag, evicted page."""
    page: int
    frames: List[Optional[int]]
    fault: bool
    evicted: Optional[int] = None


@dataclass
class PageResult:
    """Outcome of one page-replacement run."""
    algo: str
    num_frames: int
    faults: int
    hits: int
    hit_ratio: float
    steps: List[Step] = field(default_factory=list)


def _first_empty(frames):
    for i, f in enumerate(frames):
        if f is None:
            return i
    return None


def _fifo(refs, n):
    frames, ptr, steps = [None] * n, 0, []
    for page in refs:
        if page in frames:
            steps.append(Step(page, list(frames), False))
            continue
        victim = frames[ptr]
        frames[ptr] = page
        ptr = (ptr + 1) % n
        steps.append(Step(page, list(frames), True, victim))
    return steps


def _lru(refs, n):
    frames, last, steps = [None] * n, {}, []
    for t, page in enumerate(refs):
        if page in frames:
            last[page] = t
            steps.append(Step(page, list(frames), False))
            continue
        slot = _first_empty(frames)
        victim = None
        if slot is None:
            slot = min(range(n), key=lambda i: last[frames[i]])
            victim = frames[slot]
        frames[slot] = page
        last[page] = t
        steps.append(Step(page, list(frames), True, victim))
    return steps


def _optimal(refs, n):
    frames, steps = [None] * n, []
    for t, page in enumerate(refs):
        if page in frames:
            steps.append(Step(page, list(frames), False))
            continue
        slot = _first_empty(frames)
        victim = None
        if slot is None:
            def next_use(i):
                future = refs[t + 1:]
                return future.index(frames[i]) if frames[i] in future else len(refs) + 1
            slot = max(range(n), key=lambda i: (next_use(i), -i))
            victim = frames[slot]
        frames[slot] = page
        steps.append(Step(page, list(frames), True, victim))
    return steps


def _clock(refs, n):
    """Second-chance (clock): hand sweeps, clearing reference bits until it finds a 0."""
    frames, ref, hand, steps = [None] * n, [0] * n, 0, []
    for page in refs:
        if page in frames:
            ref[frames.index(page)] = 1
            steps.append(Step(page, list(frames), False))
            continue
        while frames[hand] is not None and ref[hand] == 1:
            ref[hand] = 0
            hand = (hand + 1) % n
        victim = frames[hand]
        frames[hand] = page
        ref[hand] = 1
        hand = (hand + 1) % n
        steps.append(Step(page, list(frames), True, victim))
    return steps


_IMPL = {"FIFO": _fifo, "LRU": _lru, "OPTIMAL": _optimal, "CLOCK": _clock}


def simulate_pages(algo, refs, num_frames):
    """Simulate page replacement; returns a PageResult with a frame-by-frame trace."""
    refs = validate_reference_string(refs)
    n = validate_frames(num_frames)
    key = str(algo).strip().upper()
    if key not in _IMPL:
        raise ValidationError("Unknown page-replacement algorithm %r (choose from %s)." % (
            algo, ", ".join(PAGE_ALGORITHMS)))
    steps = _IMPL[key](refs, n)
    faults = sum(1 for s in steps if s.fault)
    name = dict((a.upper(), a) for a in PAGE_ALGORITHMS)[key]
    res = PageResult(name, n, faults, len(refs) - faults, (len(refs) - faults) / float(len(refs)), steps)
    log.info("%s frames=%d refs=%d faults=%d hit_ratio=%.3f", name, n, len(refs), faults, res.hit_ratio)
    return res


def compare_pages(refs, num_frames):
    """Run all four algorithms with the same frame count."""
    return [simulate_pages(a, refs, num_frames) for a in PAGE_ALGORITHMS]


def frame_sweep(refs, max_frames=7):
    """Faults for each algorithm with 1..max_frames frames: {algo: [faults...]}."""
    refs = validate_reference_string(refs)
    max_frames = validate_frames(max_frames)
    return dict((a, [simulate_pages(a, refs, f).faults for f in range(1, max_frames + 1)])
                for a in PAGE_ALGORITHMS)


def find_belady(faults_by_frames):
    """Return [(f, f+1, faults_f, faults_f+1)] where MORE frames gave MORE faults."""
    out = []
    for i in range(len(faults_by_frames) - 1):
        if faults_by_frames[i + 1] > faults_by_frames[i]:
            out.append((i + 1, i + 2, faults_by_frames[i], faults_by_frames[i + 1]))
    return out


# ------------------------------------------------- fixed partition allocation
@dataclass
class PartitionResult:
    """Outcome of fixed-partition allocation with one strategy."""
    strategy: str
    partitions: List[dict]
    unallocated: List[str]
    internal_fragmentation: int
    memory_utilisation: float


def allocate_partitions(partition_sizes, procs, strategy):
    """Allocate processes (name, size) to fixed partitions (one process each)."""
    parts, procs = validate_partitions(partition_sizes, procs)
    strategy = str(strategy).strip().lower()
    if strategy not in FIT_STRATEGIES:
        raise ValidationError("Unknown fit strategy %r (choose first/best/worst)." % strategy)
    rows = [{"index": i, "size": s, "process": None, "used": 0, "internal_frag": 0}
            for i, s in enumerate(parts)]
    unalloc = []
    for name, size in procs:
        free = [r for r in rows if r["process"] is None and r["size"] >= size]
        if not free:
            unalloc.append(name)
            continue
        if strategy == "first":
            pick = free[0]
        elif strategy == "best":
            pick = min(free, key=lambda r: (r["size"], r["index"]))
        else:
            pick = max(free, key=lambda r: (r["size"], -r["index"]))
        pick.update(process=name, used=size, internal_frag=pick["size"] - size)
    frag = sum(r["internal_frag"] for r in rows)
    used = sum(r["used"] for r in rows)
    res = PartitionResult(strategy, rows, unalloc, frag, 100.0 * used / sum(parts))
    log.info("%s-fit: allocated=%d unallocated=%d internal_frag=%d", strategy, len(procs) - len(unalloc),
             len(unalloc), frag)
    return res


def compare_fits(partition_sizes, procs):
    """Run first/best/worst fit on the same input."""
    return [allocate_partitions(partition_sizes, procs, s) for s in FIT_STRATEGIES]
