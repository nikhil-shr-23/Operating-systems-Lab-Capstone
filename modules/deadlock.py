"""Deadlock handling: Banker's algorithm (avoidance) and deadlock detection."""
from dataclasses import dataclass, field
from typing import List, Optional

from modules.logger import get_logger
from modules.validation import (ValidationError, matrix, parse_int, parse_int_list,
                                validate_banker, validate_request)

log = get_logger("deadlock")


def _le(a, b):
    return all(x <= y for x, y in zip(a, b))


@dataclass
class SafetyResult:
    """Result of the safety algorithm."""
    safe: bool
    sequence: List[str]
    trace: List[str] = field(default_factory=list)


@dataclass
class RequestResult:
    """Result of a resource request: granted flag, status code and message."""
    pid: str
    request: List[int]
    granted: bool
    status: str          # granted | exceeds_need | not_available | unsafe
    message: str
    safety: Optional[SafetyResult] = None


class BankersState:
    """System state for Banker's algorithm (processes are named P0..Pn-1)."""

    def __init__(self, available, maximum, allocation):
        self.available, self.maximum, self.allocation = validate_banker(available, maximum, allocation)
        self.n = len(self.maximum)
        self.m = len(self.available)

    @property
    def need(self):
        """Need = Max - Allocation."""
        return [[self.maximum[i][j] - self.allocation[i][j] for j in range(self.m)] for i in range(self.n)]

    def pid_index(self, pid):
        """Accept 1, '1' or 'P1' and return the process index."""
        text = str(pid).strip().upper()
        if text.startswith("P"):
            text = text[1:]
        idx = parse_int(text, "Process id")
        if not 0 <= idx < self.n:
            raise ValidationError("Process P%d does not exist (valid: P0..P%d)." % (idx, self.n - 1))
        return idx

    def safety_check(self):
        """Run the safety algorithm; scans P0..Pn-1 repeatedly (textbook order)."""
        need = self.need
        work = list(self.available)
        finish = [False] * self.n
        seq, trace = [], ["Work = %s" % work]
        progress = True
        while progress:
            progress = False
            for i in range(self.n):
                if not finish[i] and _le(need[i], work):
                    trace.append("P%d: Need %s <= Work %s -> runs to completion, Work = %s" % (
                        i, need[i], work, [w + a for w, a in zip(work, self.allocation[i])]))
                    work = [w + a for w, a in zip(work, self.allocation[i])]
                    finish[i] = True
                    seq.append("P%d" % i)
                    progress = True
        safe = all(finish)
        if not safe:
            stuck = ["P%d" % i for i in range(self.n) if not finish[i]]
            trace.append("No remaining process can finish: %s stuck -> UNSAFE" % ", ".join(stuck))
        log.info("safety check: safe=%s sequence=%s", safe, seq)
        return SafetyResult(safe, seq, trace)

    def request_resources(self, pid, request):
        """Handle a request: validate, check availability, tentatively grant, roll back if unsafe."""
        i = self.pid_index(pid)
        req = validate_request(request, self.m)
        name = "P%d" % i
        need = self.need[i]
        if not _le(req, need):
            msg = "%s requested %s which exceeds its remaining need %s -> DENIED (error)" % (name, req, need)
            log.warning(msg)
            return RequestResult(name, req, False, "exceeds_need", msg)
        if not _le(req, self.available):
            msg = "%s requested %s but only %s available -> DENIED (must wait)" % (name, req, self.available)
            log.info(msg)
            return RequestResult(name, req, False, "not_available", msg)
        saved = (list(self.available), [list(r) for r in self.allocation])
        self.available = [a - r for a, r in zip(self.available, req)]
        self.allocation[i] = [a + r for a, r in zip(self.allocation[i], req)]
        safety = self.safety_check()
        if safety.safe:
            msg = "%s request %s GRANTED; safe sequence %s" % (name, req, ", ".join(safety.sequence))
            log.info(msg)
            return RequestResult(name, req, True, "granted", msg, safety)
        self.available, self.allocation = saved
        msg = "%s request %s would leave the system UNSAFE -> DENIED, state rolled back" % (name, req)
        log.info(msg)
        return RequestResult(name, req, False, "unsafe", msg, safety)


@dataclass
class DetectionResult:
    """Result of deadlock detection."""
    deadlocked: List[str]
    finish_order: List[str]
    trace: List[str]


def detect_deadlock(available, allocation, request):
    """Deadlock detection (textbook 8.6.2); returns the deadlocked processes."""
    avail = parse_int_list(available, "Available vector", 0)
    if not avail:
        raise ValidationError("Available vector is empty.")
    alloc = matrix(allocation, "Allocation matrix")
    req = matrix(request, "Request matrix")
    for i, row in enumerate(alloc):
        if len(row) != len(avail):
            raise ValidationError("Matrix dimensions mismatch: Allocation row %d has %d columns, expected %d." % (
                i, len(row), len(avail)))
        if any(v < 0 for v in row):
            raise ValidationError("Allocation matrix row %d contains a negative value." % i)
    if len(req) != len(alloc):
        raise ValidationError("Matrix dimensions mismatch: Request has %d rows but Allocation has %d." % (
            len(req), len(alloc)))
    for i, row in enumerate(req):
        if len(row) != len(avail):
            raise ValidationError("Matrix dimensions mismatch: Request row %d has %d columns, expected %d." % (
                i, len(row), len(avail)))
        if any(v < 0 for v in row):
            raise ValidationError("Request matrix row %d contains a negative value." % i)
    n = len(alloc)
    work = list(avail)
    finish = [all(v == 0 for v in alloc[i]) for i in range(n)]
    order, trace = [], ["Work = %s" % work]
    progress = True
    while progress:
        progress = False
        for i in range(n):
            if not finish[i] and _le(req[i], work):
                work = [w + a for w, a in zip(work, alloc[i])]
                finish[i] = True
                order.append("P%d" % i)
                trace.append("P%d can finish (Request %s <= Work) -> Work = %s" % (i, req[i], work))
                progress = True
    dead = ["P%d" % i for i in range(n) if not finish[i]]
    trace.append("Deadlocked: %s" % (", ".join(dead) if dead else "none"))
    log.info("deadlock detection: deadlocked=%s", dead)
    return DetectionResult(dead, order, trace)
