#!/usr/bin/env python3
"""Disk Scheduling Simulator (entry point).

Usage:  python3 main.py [menu|simulate|visual|analyze|gen|demo] [options]
With no sub-command the interactive menu starts.
"""
import argparse
import contextlib
import os
import sys
import time

from modules import AUTHOR, BASE_DIR, DATA_DIR, OUTPUT_DIR, ensure_dirs
from modules import bashtools, disk, reporting as rp
from modules.logger import get_logger, log_path
from modules.validation import (ValidationError, load_json, parse_float, parse_int,
                                validate_disk)

log = get_logger("main")

SAMPLE_FILE = os.path.join(DATA_DIR, "disk.json")
QUEUE_LENGTHS = [5, 10, 20, 40, 80]


class UserAbort(Exception):
    """Raised when the input stream ends (EOF) while the program is waiting for input."""


def rel(path):
    return os.path.relpath(path, BASE_DIR) if path else path


def out(text=""):
    print(text)


# ===================================================================== input
def ask(prompt, validator=None, default=None):
    """Prompt until the validator accepts the answer (re-prompts on bad input)."""
    while True:
        try:
            raw = input(prompt)
        except EOFError:
            raise UserAbort("end of input")
        raw = raw.strip()
        if raw == "" and default is not None:
            raw = str(default)
        try:
            return validator(raw) if validator else raw
        except ValidationError as exc:
            print("  ! %s  Please try again." % exc)
            log.warning("invalid input %r: %s", raw, exc)


def yes_no(prompt, default=True):
    def check(raw):
        v = raw.lower()
        if v in ("y", "yes"):
            return True
        if v in ("n", "no"):
            return False
        raise ValidationError("Answer y or n.")
    return ask("%s [%s] " % (prompt, "Y/n" if default else "y/N"), check, "y" if default else "n")


def choose(prompt, lo, hi):
    return ask(prompt, lambda r: parse_int(r, "Choice", lo, hi))


def collect(builder):
    """Run a multi-prompt data-entry function until it produces valid data."""
    while True:
        try:
            return builder()
        except ValidationError as exc:
            print("  ! %s  Let's enter it again." % exc)
            log.warning("invalid custom data: %s", exc)


# ============================================================ data loading
def load_problem(path=None):
    """Load a disk workload JSON file into a dict (requests, head, disk_size, direction)."""
    data = load_json(path or SAMPLE_FILE, ("requests", "head", "disk_size"), "disk data file")
    data.setdefault("direction", "up")
    return data


def resolve_problem(a):
    """Merge a JSON file with command-line overrides and validate the result."""
    dk = load_problem(a.file)
    queue = a.queue if a.queue is not None else dk["requests"]
    head = a.head if a.head is not None else dk["head"]
    size = a.size if a.size is not None else dk["disk_size"]
    direction = a.direction or dk["direction"]
    reqs, head, size, direction = validate_disk(queue, head, size, direction)
    return reqs, head, size, direction


# ============================================================== show helpers
def show_disk(requests, head, size, direction, algo="all", seek_ms=1.0, visual=False, explain=False):
    """Print the comparison table (and optionally the step-by-step head visualisation)."""
    if str(algo).lower() == "all":
        results = disk.compare_disk(requests, head, size, direction, seek_ms)
    else:
        results = [disk.schedule_disk(algo, requests, head, size, direction, seek_ms)]
    out(rp.format_disk(results, head, size))
    if explain:
        out(rp.heading("How each algorithm works"))
        out(rp.describe(results))
    if visual:
        for r in results:
            out(rp.ascii_path(r, size))
    return results


def run_analysis(problem, out_dir=OUTPUT_DIR, seek_ms=1.0, trials=200):
    """Run every algorithm; write tables, CSVs, charts and analysis_report.md."""
    requests, head, size, direction = problem
    p = lambda name: os.path.join(out_dir, name)
    produced = []
    results = show_disk(requests, head, size, direction, seek_ms=seek_ms)
    produced.append(rp.write_csv(p("disk_head_movement.csv"),
                                 ["algorithm", "total_movement", "avg_seek", "seek_ms", "service_order", "path"],
                                 [[r.algo, r.total, "%.2f" % r.avg_seek, "%g" % r.seek_time,
                                   " ".join(map(str, r.service_order)), " ".join(map(str, r.path))] for r in results]))
    produced.append(rp.bar_chart(p("disk_head_movement.png"), "Disk scheduling: total head movement",
                                 [r.algo for r in results], [r.total for r in results], "Cylinders moved"))
    produced.append(rp.path_grid_chart(p("disk_head_paths.png"), results, size, head))

    out(rp.heading("Random-queue experiment (%d trials per point, seed 2024)" % trials))
    series = disk.random_experiment(size, QUEUE_LENGTHS, trials, 2024, direction)
    out(rp.table(["Algorithm"] + ["n=%d" % n for n in QUEUE_LENGTHS],
                 [[a] + ["%g" % v for v in series[a]] for a in disk.DISK_ALGORITHMS], "l" + "r" * len(QUEUE_LENGTHS)))
    produced.append(rp.write_csv(p("random_experiment.csv"), ["algorithm"] + ["n=%d" % n for n in QUEUE_LENGTHS],
                                 [[a] + series[a] for a in disk.DISK_ALGORITHMS]))
    produced.append(rp.line_chart(p("movement_vs_queue_length.png"), "Mean head movement vs queue length",
                                  QUEUE_LENGTHS, series, "Mean cylinders moved", "Queue length"))

    notes = rp.observations(results, (QUEUE_LENGTHS, series))
    out(rp.heading("Observations"))
    for n in notes:
        out("  - " + n)
    rows = [[r.algo, r.total, "%.2f" % r.avg_seek, "%g" % r.seek_time] for r in results]
    produced.append(rp.write_analysis_report(p("analysis_report.md"), [
        ("Problem", ["Head %d, disk size %d cylinders (0..%d), direction %s." % (head, size, size - 1, direction),
                     "Request queue: %s" % " ".join(map(str, requests))]),
        ("Algorithm comparison", [(["Algorithm", "Total movement", "Avg seek", "Seek ms"], rows)]),
        ("Random-queue experiment (mean cylinders moved)",
         [(["Algorithm"] + ["n=%d" % n for n in QUEUE_LENGTHS], [[a] + series[a] for a in disk.DISK_ALGORITHMS])]),
        ("Observations", notes)]))
    produced = [x for x in produced if x]
    out(rp.heading("Files written"))
    for f in produced:
        out("  " + rel(f))
    return produced


# ==================================================================== demo
class _Tee(object):
    """Write to several streams at once (console + trace file)."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            st.write(s)

    def flush(self):
        for st in self.streams:
            st.flush()


def run_demo(trace_path=None):
    """Non-interactive demo of everything; the full trace is saved to outputs/demo_trace.txt."""
    trace_path = trace_path or os.path.join(OUTPUT_DIR, "demo_trace.txt")
    with open(trace_path, "w", encoding="utf-8") as fh, contextlib.redirect_stdout(_Tee(sys.stdout, fh)):
        out(rp.banner())
        out("Demo run started %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
        dk = load_problem()
        problem = validate_disk(dk["requests"], dk["head"], dk["disk_size"], dk["direction"])
        out(rp.heading("Textbook check: queue 98 183 37 122 14 124 65 67, head 53 (expected SCAN = 331)"))
        show_disk(*problem, explain=True, visual=True)
        out(rp.heading("Same queue, head moving down"))
        show_disk(problem[0], problem[1], problem[2], "down")
        out(rp.heading("Bash integration: generate random requests (gen_requests.sh 12 2024)"))
        gen = bashtools.gen_requests(12, 2024)
        out("Generated: " + rel(gen))
        with open(gen) as g:
            out(g.read().rstrip())
        g = load_problem(gen)
        show_disk(*validate_disk(g["requests"], g["head"], g["disk_size"], g["direction"]))
        run_analysis(problem)
        out(rp.heading("Bash integration: system snapshot (sysinfo.sh)"))
        out(bashtools.sysinfo().rstrip())
        out(rp.heading("Bash integration: log summary (log_summary.sh)"))
        out(bashtools.log_summary().rstrip())
        out("\nDemo finished OK. Trace saved to %s" % rel(trace_path))
    print("Demo trace saved to %s" % rel(trace_path))
    return trace_path


# ================================================================== menus
def read_problem_interactively():
    if yes_no("Use sample queue (98 183 37 122 14 124 65 67, head 53, 200 cylinders)?"):
        dk = load_problem()
        return validate_disk(dk["requests"], dk["head"], dk["disk_size"], dk["direction"])

    def build():
        s = ask("Disk size (cylinders): ", lambda r: parse_int(r, "Disk size", 1))
        q = ask("Request queue (space/comma separated, blank = none): ")
        h = ask("Initial head position: ")
        d = ask("Direction (up/down) [up]: ", None, "up")
        return validate_disk(q, h, s, d)
    return collect(build)


def menu_simulate(visual=False):
    problem = read_problem_interactively()
    algo = "all"
    if not visual:
        algo = ask("Algorithm (%s or all) [all]: " % ", ".join(disk.DISK_ALGORITHMS),
                   lambda r: r if r.lower() == "all" else disk.normalise_algo(r), "all")
    show_disk(*problem, algo=algo, visual=visual or yes_no("Show step-by-step head movement?", False),
              explain=True)


def menu_gen():
    n = ask("Number of requests (1-1000): ", lambda r: parse_int(r, "Number of requests", 1, 1000))
    size = ask("Disk size [200]: ", lambda r: parse_int(r, "Disk size", 2, 100000), 200)
    seed = ask("Seed (blank = random): ", lambda r: r if r == "" else str(parse_int(r, "Seed", 0)))
    path = bashtools.gen_requests(n, seed, None, size)
    out("Workload saved to %s" % rel(path))
    if yes_no("Run all algorithms on it?"):
        dk = load_problem(path)
        show_disk(*validate_disk(dk["requests"], dk["head"], dk["disk_size"], dk["direction"]))


def view_log(lines=40):
    path = log_path()
    if not os.path.isfile(path):
        print("No log file yet (%s)." % rel(path))
        return
    with open(path, encoding="utf-8", errors="replace") as fh:
        tail = fh.readlines()[-lines:]
    out("--- last %d log lines (%s) ---" % (len(tail), rel(path)))
    out("".join(tail).rstrip())


MENU = """
Main menu
  1) Simulate / compare algorithms
  2) Step-by-step head movement (visualiser)
  3) Full analysis (tables, charts, random-queue experiment, report)
  4) Generate random request queue (Bash)
  5) System snapshot (Bash)
  6) Log summary (Bash)
  7) View log
  0) Exit"""


def menu_loop():
    out(rp.banner())
    log.info("menu started")
    actions = {1: menu_simulate, 2: lambda: menu_simulate(True),
               3: lambda: run_analysis(read_problem_interactively()), 4: menu_gen,
               5: lambda: out(bashtools.sysinfo()), 6: lambda: out(bashtools.log_summary()), 7: view_log}
    while True:
        out(MENU)
        choice = choose("Select an option: ", 0, 7)
        if choice == 0:
            out("Goodbye.")
            log.info("menu exit")
            return 0
        log.info("menu option %d", choice)
        try:
            actions[choice]()
        except (ValidationError, bashtools.BashToolError) as exc:
            print("Error: %s" % exc)
            log.error("menu action failed: %s", exc)


# ================================================================== CLI
def add_problem_args(sp):
    sp.add_argument("--file", default=SAMPLE_FILE, help="workload JSON (requests, head, disk_size, direction)")
    sp.add_argument("--queue", help="request queue, e.g. '98 183 37'")
    sp.add_argument("--head", help="initial head position")
    sp.add_argument("--size", help="disk size in cylinders")
    sp.add_argument("--direction", default=None, help="up|down (SCAN family start direction)")


def build_parser():
    ap = argparse.ArgumentParser(prog="main.py", description="Disk Scheduling Simulator\n" + AUTHOR,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command")
    sub.add_parser("menu", help="interactive menu (default)")
    sub.add_parser("demo", help="run everything non-interactively, save outputs/demo_trace.txt")
    s = sub.add_parser("simulate", help="run one or all algorithms and compare")
    add_problem_args(s)
    s.add_argument("--algo", default="all", help="fcfs|sstf|scan|cscan|look|clook|all")
    s.add_argument("--seek-ms", default="1", help="milliseconds per cylinder (default 1)")
    s.add_argument("--visual", action="store_true", help="show step-by-step head movement")
    s.add_argument("--explain", action="store_true", help="describe each algorithm")
    v = sub.add_parser("visual", help="step-by-step ASCII head-movement view (same as simulate --visual)")
    add_problem_args(v)
    v.add_argument("--algo", default="all")
    a = sub.add_parser("analyze", help="tables, CSVs, charts, random experiment, analysis_report.md")
    add_problem_args(a)
    a.add_argument("--seek-ms", default="1")
    a.add_argument("--trials", default="200", help="random trials per point (default 200)")
    g = sub.add_parser("gen", help="generate a random request queue with the Bash script")
    g.add_argument("count", help="number of requests (1-1000)")
    g.add_argument("--seed")
    g.add_argument("--size", default="200", help="disk size (default 200)")
    g.add_argument("--out", help="output JSON path")
    return ap


def dispatch(args):
    cmd = args.command or "menu"
    log.info("command: %s", cmd)
    if cmd == "menu":
        return menu_loop()
    out(rp.banner())
    if cmd == "demo":
        run_demo()
    elif cmd in ("simulate", "visual"):
        seek = parse_float(getattr(args, "seek_ms", 1), "Seek ms per cylinder", 0)
        show_disk(*resolve_problem(args), algo=args.algo, seek_ms=seek,
                  visual=cmd == "visual" or args.visual, explain=getattr(args, "explain", False))
    elif cmd == "analyze":
        seek = parse_float(args.seek_ms, "Seek ms per cylinder", 0)
        run_analysis(resolve_problem(args), seek_ms=seek, trials=parse_int(args.trials, "Trials", 1, 100000))
    elif cmd == "gen":
        path = bashtools.gen_requests(args.count, args.seed, args.out, args.size)
        out("Workload saved to %s" % rel(path))
        out("Run it with:  python3 main.py simulate --file %s" % rel(path))
    return 0


def main(argv=None):
    ensure_dirs()
    args = build_parser().parse_args(argv)
    try:
        return dispatch(args)
    except ValidationError as exc:
        print("Error: %s" % exc)
        log.error("validation error: %s", exc)
        return 2
    except bashtools.BashToolError as exc:
        print("Error: %s" % exc)
        log.error("bash tool error: %s", exc)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted (Ctrl+C). Goodbye.")
        log.info("interrupted by user")
        return 130
    except (EOFError, UserAbort):
        print("\nInput closed. Goodbye.")
        log.info("input stream closed")
        return 0
    except Exception as exc:  # last-resort guard: never show a raw traceback to the user
        log.exception("unexpected error")
        print("Unexpected error: %s (details in %s)" % (exc, rel(log_path())))
        return 1


if __name__ == "__main__":
    sys.exit(main())
