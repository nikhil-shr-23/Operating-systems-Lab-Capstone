"""Developer tool: render REAL captured command output into terminal-style PNGs.

Each command is actually executed; its stdout is drawn on a dark terminal canvas.
Usage: python3 docs/make_screenshots.py   (from anywhere)
"""
import os
import subprocess
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = [
    ("01_tests", "./run.sh test", 36, "tail"),
    ("02_scheduling_rr", "/usr/bin/python3 main.py sched --algo rr", 40, "head"),
    ("03_memory_belady", "/usr/bin/python3 main.py memory --belady --no-trace", 44, "head"),
    ("04_deadlock_banker", "/usr/bin/python3 main.py deadlock", 46, "head"),
    ("05_storage_disk", "/usr/bin/python3 main.py storage --disk-only", 22, "head"),
    ("06_demo", "./run.sh demo", 34, "tail"),
]


def render(name, cmd, text, note):
    lines = ["$ " + cmd] + text.rstrip("\n").split("\n")
    if note:
        lines.append(note)
    width = max(len(l) for l in lines)
    fig_w = max(8, min(15, width * 0.092 + 0.8))
    fig_h = len(lines) * 0.2 + 0.9
    fig = plt.figure(figsize=(fig_w, fig_h), facecolor="#1e1e1e")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    for i, c in enumerate(("#ff5f56", "#ffbd2e", "#27c93f")):
        ax.add_patch(plt.Circle((0.012 + i * 0.016, 1 - 0.28 / fig_h), 0.005 * 8 / fig_w, color=c, transform=ax.transAxes))
    ax.text(0.5, 1 - 0.28 / fig_h, "osrm - bash", color="#aaa", ha="center", va="center", fontsize=8)
    for i, l in enumerate(lines):
        ax.text(0.012, 1 - (0.62 + i * 0.2) / fig_h, l, family="Menlo" if sys.platform == "darwin" else "DejaVu Sans Mono",
                fontsize=7.4, color="#d4d4d4" if i else "#7ee787", va="center", ha="left")
    path = os.path.join(BASE, "screenshots", name + ".png")
    fig.savefig(path, dpi=140, facecolor=fig.get_facecolor())
    plt.close(fig)
    print("wrote", path)


for name, cmd, n, where in SHOTS:
    proc = subprocess.run(cmd, shell=True, cwd=BASE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True)
    all_lines = proc.stdout.rstrip("\n").split("\n")
    if len(all_lines) > n:
        keep = all_lines[:n] if where == "head" else all_lines[-n:]
        note = "... (%d more lines not shown in this image)" % (len(all_lines) - n) if where == "head" else None
        if where == "tail":
            keep = ["... (first %d lines not shown in this image)" % (len(all_lines) - n)] + keep
    else:
        keep, note = all_lines, None
    render(name, cmd, "\n".join(keep), note)
