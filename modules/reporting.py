"""Reporting: text tables, ASCII head-movement visualiser, CSV, charts, analysis report.

Charts use matplotlib when it is installed; otherwise an ASCII fallback is
printed instead (set OSRM_NO_MATPLOTLIB=1 to force the fallback).
"""
import csv
import os

from modules import AUTHOR, APP_NAME
from modules.disk import DESCRIPTIONS
from modules.logger import get_logger

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
    return "\n".join([sep, fmt(headers), sep] + [fmt(r) for r in rows] + [sep])


def banner():
    line = "=" * 74
    return "\n".join([line, " " + APP_NAME, " " + AUTHOR, line])


def heading(text):
    return "\n%s\n%s\n" % (text, "-" * len(text))


# --------------------------------------------------------- disk text output
def format_disk(results, head, size):
    """Comparison table for all algorithms run on the same input."""
    best = min(results, key=lambda r: r.total)
    rows = [[r.algo + (" *" if r.total == best.total else ""), r.total, "%.2f" % r.avg_seek,
             "%g" % r.seek_time, " -> ".join(map(str, r.path))] for r in results]
    return "\n".join([
        heading("Disk scheduling (head=%d, disk size=%d, direction=%s, %d requests)" % (
            head, size, results[0].direction, results[0].n_requests)),
        table(["Algorithm", "Total movement", "Avg seek", "Seek ms", "Head path"], rows, "lrrrl"),
        "* lowest movement: %s (%d cylinders). C-SCAN/C-LOOK return jumps are counted." % (best.algo, best.total)])


def ascii_path(res, size, width=60):
    """Step-by-step terminal visualisation of the head moving across the disk.

    '#' marks a served request, 'o' a turn-around / edge visit, 'H' the start.
    """
    scale = (width - 1) / float(max(size - 1, 1))
    served = list(res.service_order)
    lines = [heading("Head movement: %s  (total %d cylinders)" % (res.algo, res.total)),
             "      cylinder  0%s%d" % (" " * (width - len(str(size - 1)) - 1), size - 1)]
    lines.append("      %s" % ("-" * (width + 2)))
    for i, pos in enumerate(res.path):
        if i == 0:
            mark, note = "H", "start"
        elif pos in served:
            served.remove(pos)
            mark, note = "#", "+%d" % abs(pos - res.path[i - 1])
        else:
            mark, note = "o", "+%d (turn/edge)" % abs(pos - res.path[i - 1])
        row = ["."] * width
        row[int(round(pos * scale))] = mark
        lines.append("%3d %5d |%s| %s" % (i, pos, "".join(row), note))
    return "\n".join(lines)


def describe(results):
    return "\n".join("  %-7s %s" % (a, DESCRIPTIONS[a]) for a in [r.algo for r in results])


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


def _save(fig, plt, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.text(0.99, 0.01, AUTHOR, ha="right", fontsize=6, color="#777")
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(path, dpi=130)
    plt.close(fig)
    log.info("saved chart %s", path)
    return path


def bar_chart(path, title, categories, values, ylabel, xlabel=""):
    """Single-series bar chart; the lowest bar is highlighted."""
    if not have_matplotlib():
        return _fallback(title, {ylabel: values}, categories)
    plt = _plt()
    fig, ax = plt.subplots(figsize=(8, 4.6))
    low = min(values)
    bars = ax.bar(categories, values, color=[PALETTE[2] if v == low else PALETTE[0] for v in values])
    for b, v in zip(bars, values):
        ax.annotate(str(v), (b.get_x() + b.get_width() / 2, v), ha="center", va="bottom", fontsize=9,
                    xytext=(0, 2), textcoords="offset points")
    ax.set_ylabel(ylabel)
    ax.set_xlabel(xlabel)
    ax.set_title(title, fontweight="bold")
    ax.grid(axis="y", alpha=0.3)
    return _save(fig, plt, path)


def line_chart(path, title, xs, series, ylabel, xlabel):
    """Line chart with markers, one line per series."""
    if not have_matplotlib():
        return _fallback(title, series, ["%s=%s" % (xlabel, x) for x in xs])
    plt = _plt()
    fig, ax = plt.subplots(figsize=(8, 4.8))
    for k, (name, ys) in enumerate(series.items()):
        ax.plot(xs, ys, marker="o", label=name, color=PALETTE[k % len(PALETTE)], linewidth=2,
                linestyle=["-", "--", "-.", ":"][k % 4])
    ax.set_xticks(xs)
    ax.set_ylabel(ylabel)
    ax.set_xlabel(xlabel)
    ax.set_title(title, fontweight="bold")
    ax.legend(frameon=False)
    ax.grid(alpha=0.3)
    return _save(fig, plt, path)


def path_grid_chart(path, results, size, head):
    """One panel per algorithm: cylinder on x, time (step) running downward - the classic head-path plot."""
    if not have_matplotlib():
        print("[matplotlib not available - use --visual for the ASCII head-movement view]")
        return None
    plt = _plt()
    fig, axes = plt.subplots(2, 3, figsize=(13, 7.5), sharex=True)
    for ax, res, color in zip(axes.flat, results, PALETTE):
        ys = list(range(len(res.path)))
        ax.plot(res.path, ys, "-", color=color, linewidth=1.8)
        served = list(res.service_order)
        for i, p in enumerate(res.path):
            if i and p in served:
                served.remove(p)
                ax.plot(p, i, "o", color=color, markersize=6)
            elif i:
                ax.plot(p, i, "o", markerfacecolor="white", color=color, markersize=6)
        ax.plot(head, 0, "s", color="#222", markersize=7)
        ax.set_ylim(len(res.path) - 0.5, -0.5)
        ax.set_xlim(-0.03 * size, 1.03 * size)
        ax.xaxis.tick_top()
        ax.set_yticks([])
        ax.set_title("%s - %d cylinders" % (res.algo, res.total), fontsize=10, fontweight="bold", pad=22)
        ax.grid(axis="x", alpha=0.25)
    fig.suptitle("Head movement paths (square = start, filled = served, hollow = turn/edge)", y=0.995)
    return _save(fig, plt, path)


# ------------------------------------------------------------ observations
def observations(results, experiment=None):
    """Plain-English conclusions generated from the numbers of this run."""
    out = []
    by = dict((r.algo, r) for r in results)
    best = min(results, key=lambda r: r.total)
    worst = max(results, key=lambda r: r.total)
    pct = 100.0 * (worst.total - best.total) / best.total if best.total else 0.0
    out.append("%s moves the head least (%d cylinders); %s is the worst (%d), %.0f%% more." % (
        best.algo, best.total, worst.algo, worst.total, pct))
    out.append("LOOK saves %d cylinders over SCAN (%d vs %d) by turning at the last request instead of the disk "
               "edge; C-LOOK saves %d over C-SCAN." % (by["SCAN"].total - by["LOOK"].total, by["LOOK"].total,
               by["SCAN"].total, by["C-SCAN"].total - by["C-LOOK"].total))
    out.append("FCFS is fair but ignores head position (avg seek %.1f vs %.1f for SSTF)." % (
        by["FCFS"].avg_seek, by["SSTF"].avg_seek))
    out.append("SSTF has low movement but can starve distant requests; C-SCAN/C-LOOK trade extra movement (the "
               "return jump is counted) for more uniform waiting time.")
    if experiment:
        xs, series = experiment
        winner = min(series, key=lambda a: series[a][-1])
        out.append("Over random queues, %s has the lowest mean movement at the longest queue (%d requests): %g "
                   "cylinders vs %g for FCFS." % (winner, xs[-1], series[winner][-1], series["FCFS"][-1]))
        out.append("FCFS grows almost linearly with queue length, while the SCAN family flattens because each sweep "
                   "serves more requests per pass.")
    return out


def write_analysis_report(path, sections):
    """Write analysis_report.md.  ``sections`` is [(title, [str | (headers, rows)])]."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = ["# %s - Analysis Report" % APP_NAME, "", "Author: %s" % AUTHOR, "",
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
