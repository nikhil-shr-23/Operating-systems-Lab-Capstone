"""Reporting: text tables, Gantt charts, CSV export, charts and analysis report.

Charts use matplotlib when it is installed; otherwise an ASCII bar chart is
printed instead (set OSRM_NO_MATPLOTLIB=1 to force the fallback).
"""
import csv
import os

from modules import AUTHOR, APP_NAME
from modules.logger import get_logger
from modules.scheduler import IDLE

log = get_logger("reporting")

PALETTE = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2", "#B279A2"]


# ------------------------------------------------------------------ tables
def table(headers, rows, align=None):
    """Render a boxed plain-text table.  ``align`` is a string of 'l'/'r' per column."""
    rows = [[str(c) for c in r] for r in rows]
    headers = [str(h) for h in headers]
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(headers)]
    align = align or "l" * len(headers)

    def fmt(cells):
        out = []
        for c, w, a in zip(cells, widths, align):
            out.append(c.rjust(w) if a == "r" else c.ljust(w))
        return "| " + " | ".join(out) + " |"
    sep = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    lines = [sep, fmt(headers), sep] + [fmt(r) for r in rows] + [sep]
    return "\n".join(lines)


def banner():
    """Application banner shown at start-up and in the report."""
    line = "=" * 74
    return "\n".join([line, " " + APP_NAME, " " + AUTHOR, line])


def heading(text):
    return "\n%s\n%s\n" % (text, "-" * len(text))


def f2(x):
    return "%.2f" % x


# ------------------------------------------------------------------- Gantt
def gantt(timeline, max_width=100):
    """Text Gantt chart (proportional when it fits) with a time axis underneath."""
    total = timeline[-1][2] - timeline[0][1]
    scale = 1.0 if total <= max_width - len(timeline) else (max_width - len(timeline)) / float(total)
    bar, axis, pos = "|", "", 0
    ticks = []
    for pid, s, e in timeline:
        label = "idle" if pid == IDLE else pid
        width = max(len(label) + 2, int(round((e - s) * scale)))
        ticks.append((pos, s))
        cell = label.center(width)
        bar += cell + "|"
        pos += width + 1
    ticks.append((pos - 1, timeline[-1][2]))
    axis = ""
    for p, t in ticks:
        axis = axis.ljust(p) + str(t)
    return "  " + bar + "\n  " + axis


def format_schedule(res):
    """Gantt + per-process table + aggregate figures for one ScheduleResult."""
    title = "%s%s" % (res.algo, " (quantum=%d)" % res.quantum if res.algo == "RR" else "")
    rows = []
    for pid in res.order:
        m = res.metrics[pid]
        rows.append([pid, m["arrival"], m["burst"], m["priority"], m["completion"], m["tat"], m["wt"], m["rt"]])
    out = [heading("Scheduling: " + title), "Gantt chart:", gantt(res.timeline), "",
           table(["PID", "Arrival", "Burst", "Prio", "Completion", "TAT", "WT", "RT"], rows, "lrrrrrrr"), "",
           "Average WT  = %s   Average TAT = %s   Average RT = %s" % (f2(res.avg_wt), f2(res.avg_tat), f2(res.avg_rt)),
           "CPU utilisation = %s%%   Throughput = %.3f proc/unit   Context switches = %d   Idle time = %d" % (
               f2(res.utilisation), res.throughput, res.context_switches, res.idle_time)]
    return "\n".join(out)


def schedule_summary_rows(results):
    return [[r.algo, f2(r.avg_wt), f2(r.avg_tat), f2(r.avg_rt), f2(r.utilisation), "%.3f" % r.throughput,
             r.context_switches] for r in results]


SCHED_HEADERS = ["Algorithm", "Avg WT", "Avg TAT", "Avg RT", "CPU util %", "Throughput", "Ctx switches"]


def format_schedule_comparison(results):
    return heading("Scheduling comparison") + table(SCHED_HEADERS, schedule_summary_rows(results), "lrrrrrr")


# ------------------------------------------------------------------ memory
def format_page_trace(res, refs=None):
    """Frame-by-frame trace of a page replacement run."""
    n = res.num_frames
    head = ["Step", "Page"] + ["F%d" % (i + 1) for i in range(n)] + ["Result", "Evicted"]
    rows = []
    for i, s in enumerate(res.steps, 1):
        rows.append([i, s.page] + ["-" if f is None else f for f in s.frames] +
                    ["FAULT" if s.fault else "hit", "" if s.evicted is None else s.evicted])
    return "\n".join([
        heading("Page replacement: %s, %d frame(s)" % (res.algo, n)),
        table(head, rows, "r" * (n + 2) + "ll"),
        "Faults = %d   Hits = %d   Hit ratio = %.1f%%" % (res.faults, res.hits, 100 * res.hit_ratio)])


def format_page_comparison(results):
    rows = [[r.algo, r.num_frames, r.faults, r.hits, "%.1f%%" % (100 * r.hit_ratio)] for r in results]
    return table(["Algorithm", "Frames", "Faults", "Hits", "Hit ratio"], rows, "lrrrr")


def format_sweep(sweep):
    maxf = len(next(iter(sweep.values())))
    rows = [[a] + v for a, v in sweep.items()]
    return table(["Algorithm"] + ["%d fr" % f for f in range(1, maxf + 1)], rows, "l" + "r" * maxf)


def format_partitions(res):
    rows = [[r["index"], r["size"], r["process"] or "-", r["used"], r["internal_frag"]] for r in res.partitions]
    out = [heading("Partition allocation: %s fit" % res.strategy), table(
        ["Partition", "Size", "Process", "Used", "Internal frag"], rows, "rrlrr"),
        "Total internal fragmentation = %d   Memory utilisation = %.1f%%   Unallocated = %s" % (
            res.internal_fragmentation, res.memory_utilisation, ", ".join(res.unallocated) or "none")]
    return "\n".join(out)


# ---------------------------------------------------------------- deadlock
def format_state(state):
    need = state.need
    rows = [["P%d" % i, " ".join(map(str, state.maximum[i])), " ".join(map(str, state.allocation[i])),
             " ".join(map(str, need[i]))] for i in range(state.n)]
    return table(["Process", "Max", "Allocation", "Need"], rows) + "\nAvailable = %s" % state.available


def format_safety(res):
    lines = [heading("Safety algorithm")] + ["  " + t for t in res.trace]
    lines.append("Result: %s" % ("SAFE, sequence <%s>" % ", ".join(res.sequence) if res.safe else "UNSAFE"))
    return "\n".join(lines)


# ----------------------------------------------------------------- storage
def format_disk(results, head, size):
    rows = [[r.algo, r.total, " -> ".join(map(str, r.path))] for r in results]
    best = min(results, key=lambda r: r.total)
    return "\n".join([heading("Disk scheduling (head=%d, disk size=%d, direction=%s)" % (
        head, size, results[0].direction)), table(["Algorithm", "Total movement", "Head path"], rows, "lrl"),
        "Lowest movement: %s (%d cylinders). C-SCAN/C-LOOK return jumps are counted." % (best.algo, best.total)])


def format_alloc(summary):
    keys = ["created", "used_blocks", "free_blocks", "free_fragments", "largest_free_run",
            "external_frag_pct", "avg_access_cost", "worst_access_cost", "overhead_entries", "extra_blocks"]
    names = ["Files created", "Blocks used", "Blocks free", "Free fragments", "Largest free run",
             "External frag %", "Avg access cost", "Worst access cost", "Metadata entries", "Index blocks"]
    rows = [[n] + [summary[m][k] for m in summary] for n, k in zip(names, keys)]
    rows.append(["Rejected ops"] + [len(summary[m]["rejected"]) for m in summary])
    out = [heading("File allocation comparison"), table(["Metric"] + list(summary), rows, "lrrr")]
    for m, s in summary.items():
        out.append("\n%s disk map ('#' used, '.' free):\n%s" % (m, s["map"]))
        for op, why in s["rejected"]:
            out.append("  rejected [%s]: %s" % (op, why))
    return "\n".join(out)


# -------------------------------------------------------------------- CSV
def write_csv(path, headers, rows):
    """Write rows to CSV (creating the directory); returns the path."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(headers)
        w.writerows(rows)
    log.info("wrote CSV %s (%d rows)", path, len(rows))
    return path


# ----------------------------------------------------------------- charts
def have_matplotlib():
    """True when matplotlib can be imported and is not disabled."""
    if os.environ.get("OSRM_NO_MATPLOTLIB"):
        return False
    try:
        import matplotlib  # noqa: F401
        return True
    except ImportError:
        return False


def ascii_bars(title, labels, values, width=40, unit=""):
    """Horizontal ASCII bar chart (text)."""
    top = max(values) if values and max(values) > 0 else 1
    lw = max(len(str(l)) for l in labels)
    lines = [title]
    for l, v in zip(labels, values):
        bar = "#" * max(1, int(round(width * v / float(top)))) if v > 0 else ""
        lines.append("  %s | %s %s%s" % (str(l).ljust(lw), bar, ("%g" % round(v, 2)), unit))
    return "\n".join(lines)


def _fallback(title, series, categories):
    print("[matplotlib not available - showing ASCII chart for: %s]" % title)
    for name, vals in series.items():
        print(ascii_bars("%s - %s" % (title, name), categories, vals))
    return None


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    return plt


def grouped_bar_chart(path, title, categories, series, ylabel, xlabel=""):
    """Grouped bars: one group per category, one bar per series name."""
    if not have_matplotlib():
        return _fallback(title, series, categories)
    plt = _plt()
    fig, ax = plt.subplots(figsize=(9, 4.8))
    names = list(series)
    w = 0.8 / len(names)
    for k, name in enumerate(names):
        xs = [i + (k - (len(names) - 1) / 2.0) * w for i in range(len(categories))]
        bars = ax.bar(xs, series[name], w, label=name, color=PALETTE[k % len(PALETTE)])
        for b, v in zip(bars, series[name]):
            ax.annotate("%.1f" % v if isinstance(v, float) else str(v), (b.get_x() + b.get_width() / 2, v),
                        ha="center", va="bottom", fontsize=7, xytext=(0, 2), textcoords="offset points")
    ax.set_xticks(range(len(categories)))
    ax.set_xticklabels(categories)
    ax.set_ylabel(ylabel)
    ax.set_xlabel(xlabel)
    ax.set_title(title, fontweight="bold")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.3)
    fig.text(0.99, 0.01, AUTHOR, ha="right", fontsize=6, color="#777")
    return _save(fig, plt, path)


def bar_chart(path, title, categories, values, ylabel, xlabel="", highlight_min=True):
    """Single-series bar chart; the lowest bar is highlighted."""
    if not have_matplotlib():
        return _fallback(title, {ylabel: values}, categories)
    plt = _plt()
    fig, ax = plt.subplots(figsize=(8, 4.6))
    low = min(values)
    colors = [PALETTE[2] if (highlight_min and v == low) else PALETTE[0] for v in values]
    bars = ax.bar(categories, values, color=colors)
    for b, v in zip(bars, values):
        ax.annotate(str(v), (b.get_x() + b.get_width() / 2, v), ha="center", va="bottom", fontsize=9,
                    xytext=(0, 2), textcoords="offset points")
    ax.set_ylabel(ylabel)
    ax.set_xlabel(xlabel)
    ax.set_title(title, fontweight="bold")
    ax.grid(axis="y", alpha=0.3)
    fig.text(0.99, 0.01, AUTHOR, ha="right", fontsize=6, color="#777")
    return _save(fig, plt, path)


def line_chart(path, title, xs, series, ylabel, xlabel, mark=None):
    """Line chart with markers; ``mark`` = (x, y, text) annotates a point."""
    if not have_matplotlib():
        return _fallback(title, series, ["%s=%s" % (xlabel, x) for x in xs])
    plt = _plt()
    fig, ax = plt.subplots(figsize=(8, 4.8))
    for k, (name, ys) in enumerate(series.items()):
        # distinct dash styles / marker sizes keep identical (overlapping) series visible
        ax.plot(xs, ys, marker="o", label=name, color=PALETTE[k % len(PALETTE)], linewidth=2.2,
                linestyle=["-", "--", "-.", ":"][k % 4], markersize=9 - 2 * (k % 4))
    if mark:
        ax.annotate(mark[2], (mark[0], mark[1]), xytext=(mark[0] + 0.3, mark[1] + 1.2),
                    arrowprops={"arrowstyle": "->"}, fontsize=9)
    ax.set_xticks(xs)
    ax.set_ylabel(ylabel)
    ax.set_xlabel(xlabel)
    ax.set_title(title, fontweight="bold")
    ax.legend(frameon=False)
    ax.grid(alpha=0.3)
    fig.text(0.99, 0.01, AUTHOR, ha="right", fontsize=6, color="#777")
    return _save(fig, plt, path)


def _save(fig, plt, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(path, dpi=130)
    plt.close(fig)
    log.info("saved chart %s", path)
    return path


# ------------------------------------------------------------ observations
def _pct(a, b):
    return 100.0 * (a - b) / a if a else 0.0


def scheduling_observations(results):
    """Technical observations derived from a list of ScheduleResult."""
    by = dict((r.algo, r) for r in results)
    out = []
    best = min(results, key=lambda r: r.avg_wt)
    worst = max(results, key=lambda r: r.avg_wt)
    why = {
        "SRTF": "it always runs the job with the least remaining work and preempts on arrival, which minimises the "
                "time other jobs spend queued",
        "SJF": "running short jobs first lets many jobs finish early, so the long job's delay is charged to few "
               "processes (SJF is provably optimal for average WT among non-preemptive schedules)",
        "FCFS": "for this arrival pattern the arrival order already happens to be close to shortest-first",
        "Priority": "the priority numbers in this data happen to favour short jobs",
        "RR": "frequent switching lets short jobs finish within a few quanta",
    }
    out.append("Lowest average waiting time: %s (%.2f) versus %s (%.2f), a %.0f%% reduction - %s." % (
        best.algo, best.avg_wt, worst.algo, worst.avg_wt, _pct(worst.avg_wt, best.avg_wt), why[best.algo]))
    best_rt = min(results, key=lambda r: r.avg_rt)
    out.append("Best average response time: %s (%.2f)%s." % (best_rt.algo, best_rt.avg_rt,
               " - time-slicing gives every process the CPU early at the price of more context switches"
               if best_rt.algo == "RR" else ""))
    fc, rr = by.get("FCFS"), by.get("RR")
    if fc and rr:
        out.append("Round Robin (q=%d) performed %d context switches against %d for FCFS; its avg TAT is %.2f vs %.2f "
                   "for FCFS, showing the fairness/overhead trade-off." % (
                       rr.quantum, rr.context_switches, fc.context_switches, rr.avg_tat, fc.avg_tat))
    if fc:
        longest = max(fc.metrics.items(), key=lambda kv: kv[1]["wt"])
        out.append("FCFS shows the convoy effect: %s waits %d units because earlier arrivals run to completion first." % (
            longest[0], longest[1]["wt"]))
    pr = by.get("Priority")
    if pr:
        starved = max(pr.metrics.items(), key=lambda kv: kv[1]["wt"])
        out.append("Priority scheduling makes %s (priority %d) wait %d units - low-priority work can starve; aging "
                   "would be needed in a real OS." % (starved[0], starved[1]["priority"], starved[1]["wt"]))
    if any(r.idle_time for r in results):
        r0 = results[0]
        out.append("The workload contains an idle gap (%d units); CPU utilisation is %.1f%% for every algorithm "
                   "because total work is fixed and only ordering changes." % (r0.idle_time, r0.utilisation))
    return out


def memory_observations(compare, sweep, belady_sweep, partitions):
    out = []
    ranked = sorted(compare, key=lambda r: r.faults)
    out.append("With %d frames the ranking by page faults is %s. Optimal (%d) is the theoretical lower bound; "
               "LRU (%d) approximates it by using the past as a predictor of the future, while FIFO (%d) ignores "
               "usage and evicts hot pages." % (
                   compare[0].num_frames, " < ".join("%s=%d" % (r.algo, r.faults) for r in ranked),
                   next(r.faults for r in compare if r.algo == "Optimal"),
                   next(r.faults for r in compare if r.algo == "LRU"),
                   next(r.faults for r in compare if r.algo == "FIFO")))
    clock = next(r for r in compare if r.algo == "Clock")
    out.append("Clock (second chance) gave %d faults - between FIFO and LRU - at the cost of one reference bit per "
               "frame instead of full timestamps." % clock.faults)
    out.append("Increasing frames reduces faults until every distinct page fits; in the sweep all algorithms "
               "converge to the same minimum (%d faults) once frames >= distinct pages." % min(
                   v[-1] for v in sweep.values()))
    from modules.memory import find_belady
    anomalies = find_belady(belady_sweep["FIFO"])
    if anomalies:
        a = anomalies[0]
        out.append("Belady's anomaly reproduced: FIFO on 1 2 3 4 1 2 5 1 2 3 4 5 incurs %d faults with %d frames but "
                   "%d faults with %d frames (more memory, more faults)." % (a[2], a[0], a[3], a[1]))
    stack = [a for a in ("LRU", "Optimal") if not find_belady(belady_sweep[a])]
    if stack:
        out.append("%s never showed the anomaly: they are stack algorithms, so the set of pages in memory with n "
                   "frames is always a subset of the set with n+1 frames." % " and ".join(stack))
    if partitions:
        best = min(partitions, key=lambda r: (len(r.unallocated), r.internal_fragmentation))
        out.append("Fixed-partition allocation: %s fit gave the best result (%d unallocated, internal fragmentation "
                   "%d); " % (best.strategy, len(best.unallocated), best.internal_fragmentation) +
                   "; ".join("%s fit: %d unallocated, frag %d" % (r.strategy, len(r.unallocated),
                             r.internal_fragmentation) for r in partitions) + ".")
    return out


def deadlock_observations(safety, request_results, detection_ok, detection_dead):
    out = []
    if safety:
        out.append("Initial state is %s%s." % ("SAFE" if safety.safe else "UNSAFE",
                   " with safe sequence <%s>" % ", ".join(safety.sequence) if safety.safe else ""))
    for r in request_results:
        out.append("Request: " + r.message + ".")
    out.append("Banker's algorithm denies requests that would lead to an unsafe state, even though resources are "
               "available - avoidance trades some utilisation for a guarantee of freedom from deadlock.")
    if detection_dead is not None:
        out.append("Detection: the first scenario has %s; after P2 asks for one more resource the deadlocked set is "
                   "%s. Detection must be paired with a recovery policy (kill or roll back)." % (
                       "no deadlock" if not detection_ok else "deadlock: " + ", ".join(detection_ok),
                       ", ".join(detection_dead) or "none"))
    return out


def storage_observations(disk, alloc):
    out = []
    best = min(disk, key=lambda r: r.total)
    worst = max(disk, key=lambda r: r.total)
    by = dict((r.algo, r) for r in disk)
    out.append("Disk scheduling: %s moves the head least (%d cylinders); %s is the worst (%d), %.0f%% more." % (
        best.algo, best.total, worst.algo, worst.total, 100.0 * (worst.total - best.total) / best.total
        if best.total else 0))
    if "SCAN" in by and "LOOK" in by:
        out.append("LOOK saves %d cylinders over SCAN (%d vs %d) by turning at the last request instead of the disk "
                   "edge; C-LOOK saves %d over C-SCAN." % (by["SCAN"].total - by["LOOK"].total, by["LOOK"].total,
                   by["SCAN"].total, by["C-SCAN"].total - by["C-LOOK"].total))
    out.append("SSTF has low movement but can starve distant requests; C-SCAN/C-LOOK trade extra movement (the return "
               "jump is counted) for more uniform waiting time.")
    c, l, i = alloc["contiguous"], alloc["linked"], alloc["indexed"]
    out.append("File allocation: contiguous allocation gives the cheapest access (avg %.2f block reads) but left %d free "
               "fragments (external fragmentation %.1f%%) and rejected %d operation(s); linked and indexed use any free "
               "block so they rejected %d and %d." % (c["avg_access_cost"], c["free_fragments"], c["external_frag_pct"],
               len(c["rejected"]), len(l["rejected"]), len(i["rejected"])))
    out.append("Linked allocation has the worst direct-access cost (avg %.2f, worst %d reads, since blocks are reached by "
               "following pointers); indexed costs a constant %d reads but spends %d extra index block(s)." % (
                   l["avg_access_cost"], l["worst_access_cost"], i["worst_access_cost"], i["extra_blocks"]))
    return out


def write_analysis_report(path, sections):
    """Write outputs/analysis_report.md.  ``sections`` is [(title, [str|table-rows...])]."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = ["# OSRM - Analysis Report", "", "Author: %s" % AUTHOR, "",
             "_Generated automatically from the simulation results of this run._", ""]
    for title, items in sections:
        lines += ["## " + title, ""]
        for it in items:
            if isinstance(it, tuple):
                headers, rows = it
                lines.append("| " + " | ".join(map(str, headers)) + " |")
                lines.append("|" + "|".join(["---"] * len(headers)) + "|")
                for r in rows:
                    lines.append("| " + " | ".join(map(str, r)) + " |")
                lines.append("")
            else:
                lines.append("- " + it)
        lines.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    log.info("wrote analysis report %s", path)
    return path
