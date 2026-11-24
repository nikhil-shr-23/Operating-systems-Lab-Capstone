#!/usr/bin/env python3
"""OSRM - Operating System Resource Manager Simulator (entry point).

Usage:  python3 main.py [menu|demo|sched|memory|deadlock|storage|analyze] [options]
With no sub-command the interactive menu starts.
"""
import argparse
import contextlib
import os
import sys
import time

from modules import AUTHOR, BASE_DIR, DATA_DIR, OUTPUT_DIR, ensure_dirs
from modules import bashtools, deadlock, memory, reporting as rp, scheduler, storage
from modules.logger import get_logger, log_path
from modules.validation import (ValidationError, load_json, parse_int, parse_int_list,
                                validate_disk, validate_frames, validate_quantum,
                                validate_reference_string)

log = get_logger("main")

SAMPLE = {
    "processes": os.path.join(DATA_DIR, "processes.csv"),
    "memory": os.path.join(DATA_DIR, "memory.json"),
    "banker": os.path.join(DATA_DIR, "banker.json"),
    "disk": os.path.join(DATA_DIR, "disk.json"),
}


class UserAbort(Exception):
    """Raised when the input stream ends (EOF) while the program is waiting for input."""


def rel(path):
    """Path relative to the project folder, for friendly messages."""
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
    """Run a multi-line data-entry function until it produces valid data."""
    while True:
        try:
            return builder()
        except ValidationError as exc:
            print("  ! %s  Let's enter it again." % exc)
            log.warning("invalid custom data: %s", exc)


def ask_lines(prompt):
    """Read lines until a blank line."""
    lines = []
    print(prompt)
    while True:
        try:
            line = input("  > ").strip()
        except EOFError:
            raise UserAbort("end of input")
        if not line:
            return lines
        lines.append(line)


# ============================================================ data loading
def sample_memory(path=None):
    data = load_json(path or SAMPLE["memory"], ("reference_string", "frames"), "memory data file")
    return data


def sample_banker(path=None):
    return load_json(path or SAMPLE["banker"], ("available", "max", "allocation"), "banker data file")


def sample_disk(path=None):
    return load_json(path or SAMPLE["disk"], ("requests", "head", "disk_size"), "disk data file")


def banker_state(data):
    return deadlock.BankersState(data["available"], data["max"], data["allocation"])


def file_ops(data):
    ops = []
    for o in data.get("file_ops", []):
        if not isinstance(o, dict) or "name" not in o:
            raise ValidationError("Each file operation needs an 'op' and a 'name'.")
        ops.append(o)
    return ops


# ============================================================= section runs
def show_scheduling(procs, algo="all", quantum=4, detail=True):
    """Run and print scheduling for one algorithm or all; returns the result list."""
    quantum = validate_quantum(quantum)
    results = scheduler.run_all(procs, quantum) if str(algo).lower() == "all" else \
        [scheduler.run_algorithm(procs, algo, quantum)]
    if detail:
        for r in results:
            out(rp.format_schedule(r))
    if len(results) > 1:
        out(rp.format_schedule_comparison(results))
    return results


def show_pages(refs, frames, algos=None, trace=True):
    refs = validate_reference_string(refs)
    frames = validate_frames(frames)
    out("Reference string: %s   Frames: %d" % (" ".join(map(str, refs)), frames))
    results = []
    for a in algos or memory.PAGE_ALGORITHMS:
        r = memory.simulate_pages(a, refs, frames)
        results.append(r)
        if trace:
            out(rp.format_page_trace(r))
    out(rp.heading("Page replacement comparison"))
    out(rp.format_page_comparison(results))
    return results


def show_sweep(refs, max_frames, belady=None):
    sweep = memory.frame_sweep(refs, max_frames)
    out(rp.heading("Page faults vs number of frames (1..%d)" % max_frames))
    out(rp.format_sweep(sweep))
    bsweep = None
    if belady:
        bsweep = memory.frame_sweep(belady, max_frames)
        out(rp.heading("Belady's anomaly check: reference string %s" % " ".join(map(str, belady))))
        out(rp.format_sweep(bsweep))
        for f, f1, a, b in memory.find_belady(bsweep["FIFO"]):
            out("ANOMALY: FIFO has %d faults with %d frames but %d faults with %d frames." % (a, f, b, f1))
        for algo in ("LRU", "Optimal"):
            if not memory.find_belady(bsweep[algo]):
                out("%s: no anomaly (faults never increase with more frames)." % algo)
    return sweep, bsweep


def show_partitions(parts, procs):
    results = memory.compare_fits(parts, procs)
    for r in results:
        out(rp.format_partitions(r))
    out(rp.heading("Fit strategy comparison"))
    out(rp.table(["Strategy", "Internal frag", "Unallocated", "Utilisation %"],
                 [[r.strategy, r.internal_fragmentation, ", ".join(r.unallocated) or "none",
                   "%.1f" % r.memory_utilisation] for r in results], "lrlr"))
    return results


def show_banker(data, requests=None):
    state = banker_state(data)
    out(rp.heading("Banker's algorithm - current state"))
    out(rp.format_state(state))
    safety = state.safety_check()
    out(rp.format_safety(safety))
    results = []
    for item in (requests if requests is not None else data.get("requests", [])):
        out("\nRequest: %s asks for %s" % (item["pid"], item["request"]))
        res = state.request_resources(item["pid"], item["request"])
        out("  " + res.message)
        if res.safety and res.safety.safe:
            out("  new state is safe: " + ", ".join(res.safety.sequence))
        results.append(res)
    return safety, results


def show_detection(det):
    out(rp.heading("Deadlock detection"))
    outcome = {}
    for key, label in (("request_no_deadlock", "Scenario 1 (no outstanding blocking requests)"),
                       ("request_deadlock", "Scenario 2 (P2 requests one more unit of C)")):
        if key not in det:
            continue
        out(label)
        res = deadlock.detect_deadlock(det["available"], det["allocation"], det[key])
        for t in res.trace:
            out("  " + t)
        outcome[key] = res.deadlocked
    return outcome


def show_disk(requests, head, size, direction):
    results = storage.compare_disk(requests, head, size, direction)
    out(rp.format_disk(results, head, size))
    return results


def show_files(total_blocks, ops):
    summary = storage.compare_allocation(total_blocks, ops)
    out(rp.format_alloc(summary))
    return summary


# ============================================================ full analysis
def run_full_analysis(paths=None, detail=False, out_dir=OUTPUT_DIR):
    """Run all modules on the given (or sample) data; write tables, CSVs, charts and the report."""
    paths = dict(SAMPLE, **(paths or {}))
    log.info("full analysis started")
    produced = []
    sections = []

    def p(name):
        return os.path.join(out_dir, name)

    # ---- scheduling
    out(rp.heading("[1/4] CPU SCHEDULING"))
    procs = scheduler.load_processes(paths["processes"])
    out("Workload: %s (%d processes)" % (rel(paths["processes"]), len(procs)))
    results = show_scheduling(procs, "all", 4, detail)
    trace_txt = "\n".join(rp.format_schedule(r) for r in results)
    with open(p("scheduling_traces.txt"), "w") as fh:
        fh.write(trace_txt + "\n")
    produced.append(p("scheduling_traces.txt"))
    produced.append(rp.write_csv(p("scheduling_summary.csv"), rp.SCHED_HEADERS, rp.schedule_summary_rows(results)))
    rows = []
    for r in results:
        for pid in r.order:
            m = r.metrics[pid]
            rows.append([r.algo, pid, m["arrival"], m["burst"], m["priority"], m["completion"], m["tat"], m["wt"], m["rt"]])
    produced.append(rp.write_csv(p("scheduling_per_process.csv"),
                                 ["algorithm", "pid", "arrival", "burst", "priority", "completion", "tat", "wt", "rt"], rows))
    cats = [r.algo for r in results]
    chart = rp.grouped_bar_chart(p("scheduling_comparison.png"), "Scheduling: average WT / TAT / RT by algorithm",
                                 cats, {"Avg WT": [round(r.avg_wt, 2) for r in results],
                                        "Avg TAT": [round(r.avg_tat, 2) for r in results],
                                        "Avg RT": [round(r.avg_rt, 2) for r in results]},
                                 "Time units", "Algorithm")
    produced.append(chart)
    sections.append(("1. CPU Scheduling", [(rp.SCHED_HEADERS, rp.schedule_summary_rows(results))] +
                     rp.scheduling_observations(results)))

    # ---- memory
    out(rp.heading("[2/4] MEMORY MANAGEMENT"))
    mem = sample_memory(paths["memory"])
    refs = validate_reference_string(mem["reference_string"])
    frames = validate_frames(mem["frames"])
    maxf = validate_frames(mem.get("max_frames", 7))
    compare = show_pages(refs, frames, trace=detail)
    sweep, bsweep = show_sweep(refs, maxf, mem.get("belady_string", memory.BELADY_STRING))
    produced.append(rp.write_csv(p("page_faults_sweep.csv"), ["algorithm"] + ["frames_%d" % f for f in range(1, maxf + 1)],
                                 [[a] + v for a, v in sweep.items()]))
    produced.append(rp.write_csv(p("belady_sweep.csv"), ["algorithm"] + ["frames_%d" % f for f in range(1, maxf + 1)],
                                 [[a] + v for a, v in bsweep.items()]))
    xs = list(range(1, maxf + 1))
    produced.append(rp.line_chart(p("page_faults_vs_frames.png"), "Page faults vs number of frames", xs, sweep,
                                  "Page faults", "Number of frames"))
    fifo_b = bsweep["FIFO"]
    anomalies = memory.find_belady(fifo_b)
    mark = (anomalies[0][1], anomalies[0][3], "Belady's anomaly") if anomalies else None
    produced.append(rp.line_chart(p("belady_anomaly.png"), "Belady's anomaly (1 2 3 4 1 2 5 1 2 3 4 5)", xs, bsweep,
                                  "Page faults", "Number of frames", mark))
    fits = show_partitions(mem.get("partitions", [100, 500, 200]), [tuple(x) for x in mem.get("processes", [("P1", 50)])])
    produced.append(rp.write_csv(p("partition_allocation.csv"), ["strategy", "partition", "size", "process", "used", "internal_frag"],
                                 [[r.strategy, x["index"], x["size"], x["process"] or "-", x["used"], x["internal_frag"]]
                                  for r in fits for x in r.partitions]))
    sections.append(("2. Memory Management", [(["Algorithm", "Frames", "Faults", "Hits", "Hit ratio"],
                     [[r.algo, r.num_frames, r.faults, r.hits, "%.1f%%" % (100 * r.hit_ratio)] for r in compare])] +
                     [(["Algorithm"] + ["%d fr" % f for f in xs], [[a] + v for a, v in sweep.items()])] +
                     rp.memory_observations(compare, sweep, bsweep, fits)))

    # ---- deadlock
    out(rp.heading("[3/4] DEADLOCK HANDLING"))
    bk = sample_banker(paths["banker"])
    safety, req_results = show_banker(bk)
    det = bk.get("detection")
    dead = {}
    if det:
        dead = show_detection(det)
    produced.append(rp.write_csv(p("deadlock_requests.csv"), ["pid", "request", "status", "granted"],
                                 [[r.pid, " ".join(map(str, r.request)), r.status, r.granted] for r in req_results]))
    sections.append(("3. Deadlock Handling", rp.deadlock_observations(
        safety, req_results, dead.get("request_no_deadlock", []), dead.get("request_deadlock") if dead else None)))

    # ---- storage
    out(rp.heading("[4/4] STORAGE MANAGEMENT"))
    dk = sample_disk(paths["disk"])
    dres = show_disk(dk["requests"], dk["head"], dk["disk_size"], dk.get("direction", "up"))
    produced.append(rp.write_csv(p("disk_head_movement.csv"), ["algorithm", "total_movement", "path"],
                                 [[r.algo, r.total, " ".join(map(str, r.path))] for r in dres]))
    produced.append(rp.bar_chart(p("disk_head_movement.png"), "Disk scheduling: total head movement",
                                 [r.algo for r in dres], [r.total for r in dres], "Cylinders moved", "Algorithm"))
    alloc = show_files(dk.get("total_blocks", 64), file_ops(dk))
    metrics = ["avg_access_cost", "worst_access_cost", "free_fragments", "external_frag_pct", "overhead_entries", "extra_blocks"]
    produced.append(rp.write_csv(p("allocation_comparison.csv"), ["method"] + metrics + ["rejected_ops"],
                                 [[m] + [alloc[m][k] for k in metrics] + [len(alloc[m]["rejected"])] for m in alloc]))
    produced.append(rp.grouped_bar_chart(
        p("allocation_comparison.png"), "File allocation comparison", list(alloc),
        {"Avg access cost": [alloc[m]["avg_access_cost"] for m in alloc],
         "Worst access cost": [alloc[m]["worst_access_cost"] for m in alloc],
         "Free fragments": [alloc[m]["free_fragments"] for m in alloc],
         "Rejected ops": [len(alloc[m]["rejected"]) for m in alloc]}, "Count / block reads", "Allocation method"))
    sections.append(("4. Storage Management", [(["Algorithm", "Total head movement"], [[r.algo, r.total] for r in dres])] +
                     rp.storage_observations(dres, alloc)))

    produced.append(rp.write_analysis_report(p("analysis_report.md"), sections))
    produced = [x for x in produced if x]
    out(rp.heading("Technical observations"))
    for _, items in sections:
        for it in items:
            if isinstance(it, str):
                out(" * " + it)
    out("\nFiles written:")
    for x in produced:
        out("  " + rel(x))
    log.info("full analysis finished: %d files", len(produced))
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
        out(rp.heading("Textbook check: FCFS on bursts 24,3,3 (expected avg WT 17)"))
        t = scheduler.make_processes([("P1", 0, 24, 0), ("P2", 0, 3, 0), ("P3", 0, 3, 0)])
        out(rp.format_schedule(scheduler.run_algorithm(t, "FCFS")))
        out(rp.heading("Bash integration: generate workload (gen_workload.sh 8 2024) and schedule it"))
        gen = bashtools.gen_workload(8, 2024)
        out("Generated: " + rel(gen))
        with open(gen) as g:
            out(g.read().rstrip())
        show_scheduling(scheduler.load_processes(gen), "all", 4, detail=False)
        run_full_analysis(detail=True)
        out(rp.heading("Bash integration: system snapshot (sysinfo.sh)"))
        out(bashtools.sysinfo().rstrip())
        out(rp.heading("Bash integration: log summary (log_summary.sh)"))
        out(bashtools.log_summary().rstrip())
        out("\nDemo finished OK. Trace saved to %s" % rel(trace_path))
    print("Demo trace saved to %s" % rel(trace_path))
    return trace_path


# ================================================================== menus
def pick_processes():
    """Sample CSV, other CSV, or manual entry."""
    if yes_no("Use sample data (%s)?" % rel(SAMPLE["processes"])):
        return scheduler.load_processes(SAMPLE["processes"])
    mode = choose("  1) Load a CSV file  2) Enter processes manually: ", 1, 2)
    if mode == 1:
        return collect(lambda: scheduler.load_processes(ask("  CSV path: ")))

    def build():
        lines = ask_lines("Enter one process per line: pid arrival burst [priority]   (blank line to finish)")
        rows = []
        for ln in lines:
            parts = ln.replace(",", " ").split()
            if len(parts) not in (3, 4):
                raise ValidationError("Line %r needs 3 or 4 fields: pid arrival burst [priority]." % ln)
            rows.append((parts[0], parts[1], parts[2], parts[3] if len(parts) == 4 else 0))
        return scheduler.make_processes(rows)
    return collect(build)


def menu_scheduling():
    procs = pick_processes()
    names = scheduler.ALGORITHMS + ["All (compare)"]
    for i, n in enumerate(names, 1):
        out("  %d) %s" % (i, n))
    pick = choose("Algorithm: ", 1, len(names))
    algo = "all" if pick == len(names) else names[pick - 1]
    quantum = 4
    if algo in ("RR", "all"):
        quantum = ask("Time quantum [4]: ", validate_quantum, 4)
    show_scheduling(procs, algo, quantum)


def menu_memory():
    out("  1) Page replacement  2) Frames sweep + Belady's anomaly  3) Partition allocation")
    mode = choose("Choice: ", 1, 3)
    mem = sample_memory()
    if mode in (1, 2):
        if yes_no("Use sample reference string?"):
            refs, frames = mem["reference_string"], mem["frames"]
        else:
            refs = ask("Reference string (integers separated by spaces): ", validate_reference_string)
            frames = ask("Number of frames: ", validate_frames)
        if mode == 1:
            show_pages(refs, frames)
        else:
            maxf = ask("Maximum frames to sweep [7]: ", validate_frames, 7)
            show_sweep(refs, maxf, mem.get("belady_string", memory.BELADY_STRING))
    else:
        if yes_no("Use sample partitions and processes?"):
            parts, procs = mem["partitions"], [tuple(x) for x in mem["processes"]]
        else:
            def build():
                ps = parse_int_list(ask("Partition sizes (space separated): "), "Partition size", 1)
                lines = ask_lines("Enter processes as: name size   (blank line to finish)")
                pr = []
                for ln in lines:
                    f = ln.split()
                    if len(f) != 2:
                        raise ValidationError("Line %r needs: name size." % ln)
                    pr.append((f[0], f[1]))
                memory.compare_fits(ps, pr)   # validate now
                return ps, pr
            parts, procs = collect(build)
        show_partitions(parts, procs)


def _banker_manual():
    n = ask("Number of processes: ", lambda r: parse_int(r, "Processes", 1, 20))
    m = ask("Number of resource types: ", lambda r: parse_int(r, "Resource types", 1, 10))

    def build():
        avail = parse_int_list(ask("Available vector (%d values): " % m), "Available", 0)
        mx = [parse_int_list(ask("Max for P%d (%d values): " % (i, m)), "Max", 0) for i in range(n)]
        al = [parse_int_list(ask("Allocation for P%d (%d values): " % (i, m)), "Allocation", 0) for i in range(n)]
        deadlock.BankersState(avail, mx, al)   # validates dimensions
        return {"available": avail, "max": mx, "allocation": al}
    return collect(build)


def menu_deadlock():
    out("  1) Banker's safety check + requests  2) Deadlock detection")
    mode = choose("Choice: ", 1, 2)
    bk = sample_banker()
    if mode == 1:
        data = bk if yes_no("Use sample (Silberschatz) data?") else _banker_manual()
        reqs = None
        if yes_no("Make resource requests?", default=not (data is not bk)):
            reqs = []
            while True:
                pid = ask("  Process (e.g. P1, blank to stop): ")
                if not pid:
                    break
                try:
                    req = parse_int_list(ask("  Request vector: "), "Request", 0)
                    st = banker_state(data)
                    st.pid_index(pid)
                    reqs.append({"pid": pid, "request": req})
                except ValidationError as exc:
                    print("  ! %s" % exc)
            if data is bk and not reqs:
                reqs = None
        show_banker(data, reqs if reqs is not None else ([] if data is not bk else None))
    else:
        if yes_no("Use sample detection scenarios?"):
            show_detection(bk["detection"])
        else:
            def build():
                avail = parse_int_list(ask("Available vector: "), "Available", 0)
                n = ask("Number of processes: ", lambda r: parse_int(r, "Processes", 1, 20))
                al = [parse_int_list(ask("Allocation P%d: " % i), "Allocation", 0) for i in range(n)]
                rq = [parse_int_list(ask("Request P%d: " % i), "Request", 0) for i in range(n)]
                deadlock.detect_deadlock(avail, al, rq)
                return {"available": avail, "allocation": al, "request_deadlock": rq}
            show_detection(collect(build))


def menu_storage():
    out("  1) Disk scheduling  2) File allocation")
    mode = choose("Choice: ", 1, 2)
    dk = sample_disk()
    if mode == 1:
        if yes_no("Use sample disk queue?"):
            q, h, s, d = dk["requests"], dk["head"], dk["disk_size"], dk.get("direction", "up")
        else:
            def build():
                s = ask("Disk size (cylinders): ", lambda r: parse_int(r, "Disk size", 1))
                q = ask("Request queue (space separated, blank = none): ")
                h = ask("Head position: ")
                d = ask("Direction (up/down) [up]: ", None, "up")
                validate_disk(q, h, s, d)
                return q, h, s, d
            q, h, s, d = collect(build)
        show_disk(q, h, s, d)
    else:
        if yes_no("Use sample file workload?"):
            total, ops = dk.get("total_blocks", 64), file_ops(dk)
        else:
            def build():
                total = ask("Total disk blocks: ", lambda r: parse_int(r, "Total blocks", 1))
                lines = ask_lines("Operations: 'create NAME SIZE' or 'delete NAME'   (blank line to finish)")
                ops = []
                for ln in lines:
                    f = ln.split()
                    if f and f[0] == "create" and len(f) == 3:
                        ops.append({"op": "create", "name": f[1], "size": f[2]})
                    elif f and f[0] == "delete" and len(f) == 2:
                        ops.append({"op": "delete", "name": f[1]})
                    else:
                        raise ValidationError("Bad operation %r." % ln)
                return total, ops
            total, ops = collect(build)
        show_files(total, ops)


def menu_bash():
    out("  1) System snapshot  2) Generate workload and schedule it  3) Log summary")
    mode = choose("Choice: ", 1, 3)
    try:
        if mode == 1:
            out(bashtools.sysinfo())
        elif mode == 2:
            n = ask("Number of processes (1-1000): ", lambda r: parse_int(r, "Number of processes", 1, 1000))
            seed = ask("Seed (blank = random): ", lambda r: r if r == "" else str(parse_int(r, "Seed", 0)))
            path = bashtools.gen_workload(n, seed)
            out("Workload saved to %s" % rel(path))
            if yes_no("Run all schedulers on it?"):
                show_scheduling(scheduler.load_processes(path), "all", 4, detail=False)
        else:
            out(bashtools.log_summary())
    except (bashtools.BashToolError, ValidationError) as exc:
        print("Error: %s" % exc)
        log.error("bash tool failed: %s", exc)


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
  1) Scheduling
  2) Memory management
  3) Deadlock handling
  4) Storage management
  5) Run full analysis (all modules, tables, charts, report)
  6) Bash tools
  7) View log
  0) Exit"""


def menu_loop():
    out(rp.banner())
    log.info("menu started")
    actions = {1: menu_scheduling, 2: menu_memory, 3: menu_deadlock, 4: menu_storage,
               5: lambda: run_full_analysis(), 6: menu_bash, 7: view_log}
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
def build_parser():
    ap = argparse.ArgumentParser(prog="main.py", description="OSRM - Operating System Resource Manager Simulator\n" + AUTHOR,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command")
    sub.add_parser("menu", help="interactive menu (default)")
    sub.add_parser("demo", help="run everything non-interactively, save outputs/demo_trace.txt")
    s = sub.add_parser("sched", help="CPU scheduling")
    s.add_argument("--file", default=SAMPLE["processes"], help="process CSV (pid,arrival,burst,priority)")
    s.add_argument("--algo", default="all", help="fcfs|sjf|srtf|priority|rr|all")
    s.add_argument("--quantum", default=4, help="Round Robin quantum (default 4)")
    m = sub.add_parser("memory", help="page replacement and partition allocation")
    m.add_argument("--file", default=SAMPLE["memory"])
    m.add_argument("--refs", help="reference string, e.g. '7 0 1 2 0 3'")
    m.add_argument("--frames", help="number of frames")
    m.add_argument("--algo", default="all", help="fifo|lru|optimal|clock|all")
    m.add_argument("--no-trace", action="store_true", help="hide frame-by-frame trace")
    m.add_argument("--sweep", action="store_true", help="faults for 1..max frames")
    m.add_argument("--max-frames", default=None)
    m.add_argument("--belady", action="store_true", help="demonstrate Belady's anomaly")
    m.add_argument("--partitions", action="store_true", help="first/best/worst fit partition allocation")
    d = sub.add_parser("deadlock", help="Banker's algorithm and deadlock detection")
    d.add_argument("--file", default=SAMPLE["banker"])
    d.add_argument("--request", action="append", metavar="PID:R1,R2,..", help="e.g. P1:1,0,2 (repeatable)")
    d.add_argument("--detect", action="store_true", help="only run deadlock detection")
    t = sub.add_parser("storage", help="disk scheduling and file allocation")
    t.add_argument("--file", default=SAMPLE["disk"])
    t.add_argument("--queue", help="request queue, e.g. '98 183 37'")
    t.add_argument("--head")
    t.add_argument("--size", help="disk size in cylinders")
    t.add_argument("--direction", default=None, help="up|down")
    t.add_argument("--disk-only", action="store_true")
    t.add_argument("--files-only", action="store_true")
    a = sub.add_parser("analyze", help="full analysis: tables, CSVs, charts, analysis_report.md")
    a.add_argument("--processes", help="alternative process CSV")
    return ap


def cmd_sched(a):
    procs = scheduler.load_processes(a.file)
    show_scheduling(procs, a.algo, a.quantum)


def cmd_memory(a):
    mem = sample_memory(a.file)
    refs = a.refs if a.refs else mem["reference_string"]
    frames = a.frames if a.frames else mem["frames"]
    algos = None if a.algo.lower() == "all" else [a.algo]
    show_pages(refs, frames, algos, trace=not a.no_trace)
    if a.sweep or a.belady:
        show_sweep(refs, a.max_frames or mem.get("max_frames", 7), mem.get("belady_string", memory.BELADY_STRING) if a.belady else None)
    if a.partitions:
        show_partitions(mem["partitions"], [tuple(x) for x in mem["processes"]])


def cmd_deadlock(a):
    bk = sample_banker(a.file)
    if a.detect:
        if "detection" not in bk:
            raise ValidationError("%s has no 'detection' section." % a.file)
        show_detection(bk["detection"])
        return
    reqs = None
    if a.request:
        reqs = []
        for item in a.request:
            if ":" not in item:
                raise ValidationError("--request must look like P1:1,0,2 (got %r)." % item)
            pid, vec = item.split(":", 1)
            reqs.append({"pid": pid, "request": parse_int_list(vec, "Request", 0)})
    show_banker(bk, reqs)
    if reqs is None and "detection" in bk:
        show_detection(bk["detection"])


def cmd_storage(a):
    dk = sample_disk(a.file)
    queue = a.queue if a.queue is not None else dk["requests"]
    head = a.head if a.head is not None else dk["head"]
    size = a.size if a.size is not None else dk["disk_size"]
    direction = a.direction or dk.get("direction", "up")
    if not a.files_only:
        show_disk(queue, head, size, direction)
    if not a.disk_only:
        show_files(dk.get("total_blocks", 64), file_ops(dk))


def dispatch(args):
    cmd = args.command or "menu"
    log.info("command: %s", cmd)
    if cmd == "menu":
        return menu_loop()
    out(rp.banner())
    if cmd == "demo":
        run_demo()
    elif cmd == "sched":
        cmd_sched(args)
    elif cmd == "memory":
        cmd_memory(args)
    elif cmd == "deadlock":
        cmd_deadlock(args)
    elif cmd == "storage":
        cmd_storage(args)
    elif cmd == "analyze":
        run_full_analysis({"processes": args.processes} if args.processes else None)
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
