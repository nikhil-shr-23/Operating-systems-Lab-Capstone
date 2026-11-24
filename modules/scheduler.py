"""CPU scheduling simulator: FCFS, SJF, SRTF, Priority and Round Robin.

Conventions
-----------
* Priority scheduling is non-preemptive and a *lower number means higher priority*.
* SJF is non-preemptive; SRTF is its preemptive version (preempts on arrival).
* Ties are always broken by arrival time, then by input order.
* Round Robin: a process arriving during/at the end of a time slice is queued
  *before* the pre-empted process is re-queued.
* Response time = first CPU start - arrival.
* CPU utilisation = busy time / (last completion - first arrival); idle gaps in
  that window reduce it.  Throughput = processes / that same window.
* A context switch is counted whenever the CPU is handed to a different process
  than the one that ran last (the very first dispatch is not a switch).
"""
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from modules.logger import get_logger
from modules.validation import (ValidationError, load_processes_csv,
                                validate_processes, validate_quantum)

log = get_logger("scheduler")

IDLE = "IDLE"
ALGORITHMS = ["FCFS", "SJF", "SRTF", "Priority", "RR"]


@dataclass
class Process:
    """A process: id, arrival time, CPU burst and priority (lower = more urgent)."""
    pid: str
    arrival: int
    burst: int
    priority: int = 0


@dataclass
class ScheduleResult:
    """Everything produced by one scheduling run."""
    algo: str
    quantum: int
    timeline: List[Tuple[str, int, int]]
    metrics: Dict[str, Dict[str, int]]
    avg_wt: float = 0.0
    avg_tat: float = 0.0
    avg_rt: float = 0.0
    utilisation: float = 0.0
    throughput: float = 0.0
    context_switches: int = 0
    makespan: int = 0
    idle_time: int = 0
    order: List[str] = field(default_factory=list)


def make_processes(rows):
    """Build :class:`Process` objects from (pid, arrival, burst, priority) rows."""
    return [Process(*r) for r in validate_processes(rows)]


def load_processes(path):
    """Load processes from a CSV file (pid,arrival,burst,priority)."""
    procs = make_processes(load_processes_csv(path))
    log.info("loaded %d processes from %s", len(procs), path)
    return procs


def _merge(timeline):
    """Merge back-to-back segments that belong to the same process."""
    out = []
    for pid, s, e in timeline:
        if e <= s:
            continue
        if out and out[-1][0] == pid and out[-1][2] == s:
            out[-1] = (pid, out[-1][1], e)
        else:
            out.append((pid, s, e))
    return out


def _nonpreemptive(procs, keyfn):
    """Generic non-preemptive scheduler: pick the ready process with min keyfn."""
    pending = list(enumerate(procs))
    t = 0
    timeline = []
    while pending:
        ready = [(i, p) for i, p in pending if p.arrival <= t]
        if not ready:
            nxt = min(p.arrival for _, p in pending)
            timeline.append((IDLE, t, nxt))
            t = nxt
            continue
        i, p = min(ready, key=lambda ip: keyfn(ip[0], ip[1]))
        timeline.append((p.pid, t, t + p.burst))
        t += p.burst
        pending.remove((i, p))
    return timeline


def _srtf(procs):
    """Shortest Remaining Time First (preemptive SJF)."""
    rem = dict((p.pid, p.burst) for p in procs)
    idx = dict((p.pid, i) for i, p in enumerate(procs))
    t = 0
    timeline = []
    while any(v > 0 for v in rem.values()):
        ready = [p for p in procs if p.arrival <= t and rem[p.pid] > 0]
        if not ready:
            nxt = min(p.arrival for p in procs if rem[p.pid] > 0)
            timeline.append((IDLE, t, nxt))
            t = nxt
            continue
        p = min(ready, key=lambda q: (rem[q.pid], q.arrival, idx[q.pid]))
        later = [q.arrival for q in procs if q.arrival > t and rem[q.pid] > 0]
        run = rem[p.pid] if not later else min(rem[p.pid], min(later) - t)
        timeline.append((p.pid, t, t + run))
        rem[p.pid] -= run
        t += run
    return timeline


def _round_robin(procs, quantum):
    """Round Robin with the given time quantum."""
    order = sorted(enumerate(procs), key=lambda ip: (ip[1].arrival, ip[0]))
    order = [p for _, p in order]
    rem = dict((p.pid, p.burst) for p in procs)
    queue = deque()
    timeline = []
    t = 0
    nxt = 0
    done = 0
    n = len(procs)
    while done < n:
        if not queue:
            if t < order[nxt].arrival:
                timeline.append((IDLE, t, order[nxt].arrival))
                t = order[nxt].arrival
            while nxt < n and order[nxt].arrival <= t:
                queue.append(order[nxt])
                nxt += 1
        p = queue.popleft()
        run = min(quantum, rem[p.pid])
        timeline.append((p.pid, t, t + run))
        t += run
        rem[p.pid] -= run
        while nxt < n and order[nxt].arrival <= t:
            queue.append(order[nxt])
            nxt += 1
        if rem[p.pid] > 0:
            queue.append(p)
        else:
            done += 1
    return timeline


def _finalise(algo, procs, timeline, quantum):
    """Compute per-process metrics and aggregate statistics from a timeline."""
    timeline = _merge(timeline)
    metrics = {}
    for p in procs:
        segs = [(s, e) for pid, s, e in timeline if pid == p.pid]
        completion = max(e for _, e in segs)
        first = min(s for s, _ in segs)
        tat = completion - p.arrival
        metrics[p.pid] = {
            "arrival": p.arrival, "burst": p.burst, "priority": p.priority,
            "completion": completion, "tat": tat, "wt": tat - p.burst, "rt": first - p.arrival,
        }
    n = len(procs)
    span = max(m["completion"] for m in metrics.values()) - min(p.arrival for p in procs)
    busy = sum(p.burst for p in procs)
    runs = [pid for pid, _, _ in timeline if pid != IDLE]
    switches = sum(1 for a, b in zip(runs, runs[1:]) if a != b)
    res = ScheduleResult(
        algo=algo, quantum=quantum, timeline=timeline, metrics=metrics,
        avg_wt=sum(m["wt"] for m in metrics.values()) / n,
        avg_tat=sum(m["tat"] for m in metrics.values()) / n,
        avg_rt=sum(m["rt"] for m in metrics.values()) / n,
        utilisation=100.0 * busy / span if span else 100.0,
        throughput=n / float(span) if span else float(n),
        context_switches=switches,
        makespan=max(m["completion"] for m in metrics.values()),
        idle_time=sum(e - s for pid, s, e in timeline if pid == IDLE),
        order=[p.pid for p in procs],
    )
    return res


def run_algorithm(procs, algo, quantum=4):
    """Run one algorithm (name is case-insensitive) and return a ScheduleResult."""
    if not procs:
        raise ValidationError("Process list is empty.")
    names = dict((a.lower(), a) for a in ALGORITHMS)
    key = str(algo).strip().lower()
    if key in ("rr", "roundrobin", "round robin"):
        key = "rr"
    if key not in names:
        raise ValidationError("Unknown scheduling algorithm %r (choose from %s)." % (algo, ", ".join(ALGORITHMS)))
    algo = names[key]
    q = 0
    if algo == "FCFS":
        timeline = _nonpreemptive(procs, lambda i, p: (p.arrival, i))
    elif algo == "SJF":
        timeline = _nonpreemptive(procs, lambda i, p: (p.burst, p.arrival, i))
    elif algo == "Priority":
        timeline = _nonpreemptive(procs, lambda i, p: (p.priority, p.arrival, i))
    elif algo == "SRTF":
        timeline = _srtf(procs)
    else:
        q = validate_quantum(quantum)
        timeline = _round_robin(procs, q)
    res = _finalise(algo, procs, timeline, q)
    log.info("%s%s on %d processes: avgWT=%.2f avgTAT=%.2f avgRT=%.2f switches=%d",
             algo, " (q=%d)" % q if q else "", len(procs), res.avg_wt, res.avg_tat, res.avg_rt,
             res.context_switches)
    return res


def run_all(procs, quantum=4):
    """Run every algorithm; returns an ordered list of ScheduleResult."""
    return [run_algorithm(procs, a, quantum) for a in ALGORITHMS]
