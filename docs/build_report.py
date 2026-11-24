"""Developer tool: build docs/REPORT.pdf from the REAL outputs of a run.

Reads outputs/*.csv, outputs/analysis_report.md, outputs/test_results.txt and logs/osrm.log,
writes docs/REPORT.html and prints it to PDF with headless Chrome.
Run `./run.sh test`, `./run.sh demo` first so every number comes from a real run.
"""
import base64
import csv
import html
import os
import re
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "outputs")
AUTHOR = "Nikhil Sharma | Roll No 2401010084 | B.Tech CSE (Core), Section C"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
e = html.escape


def read(name):
    with open(os.path.join(OUT, name), encoding="utf-8") as fh:
        return fh.read()


def rows(name):
    with open(os.path.join(OUT, name), newline="", encoding="utf-8") as fh:
        r = list(csv.reader(fh))
    return r[0], r[1:]


def tbl(headers, body, cls=""):
    h = "".join("<th>%s</th>" % e(str(x)) for x in headers)
    b = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % e(str(c)) for c in r) for r in body)
    return '<table class="%s"><thead><tr>%s</tr></thead><tbody>%s</tbody></table>' % (cls, h, b)


def img(name, width="82%"):
    with open(os.path.join(OUT, name), "rb") as fh:
        data = base64.b64encode(fh.read()).decode()
    return '<img style="width:%s" src="data:image/png;base64,%s">' % (width, data)


def observations(section_prefix):
    text = read("analysis_report.md")
    m = re.search(r"## %s.*?(?=\n## |\Z)" % re.escape(section_prefix), text, re.S)
    return [l[2:] for l in m.group(0).splitlines() if l.startswith("- ")]


def bullets(items):
    return "<ul>%s</ul>" % "".join("<li>%s</li>" % e(i) for i in items)


# ------------------------------------------------------------- real data
tests = read("test_results.txt")
ran = re.search(r"Ran (\d+) tests? in ([\d.]+)s", tests)
n_tests, secs = ran.group(1), ran.group(2)
status = "OK" if re.search(r"^OK", tests, re.M) else "FAILED"
if status != "OK":
    sys.exit("Tests did not pass - refusing to build the report.")
classes = {}
for m in re.finditer(r"\(__main__\.(\w+)\) \.\.\. ok", tests):
    classes[m.group(1)] = classes.get(m.group(1), 0) + 1
test_rows = [[k, v] for k, v in classes.items()]

sched_h, sched_b = rows("scheduling_summary.csv")
traces = read("scheduling_traces.txt")
fcfs_block = traces.split("Scheduling: ")[1].split("Scheduling: ")[0]
fcfs_block = "Scheduling: " + fcfs_block.strip()
fcfs_block = "\n".join(fcfs_block.split("\n")[2:14])
pp_h, pp_b = rows("scheduling_per_process.csv")
srtf_rows = [[r[1], r[2], r[3], r[5], r[6], r[7], r[8]] for r in pp_b if r[0] == "SRTF"]
sw_h, sw_b = rows("page_faults_sweep.csv")
bs_h, bs_b = rows("belady_sweep.csv")
part_h, part_b = rows("partition_allocation.csv")
part_sum = []
for strat in ("first", "best", "worst"):
    rs = [r for r in part_b if r[0] == strat]
    part_sum.append([strat + " fit", sum(int(r[5]) for r in rs), ", ".join(r[3] for r in rs if r[3] != "-")])
dl_h, dl_b = rows("deadlock_requests.csv")
dk_h, dk_b = rows("disk_head_movement.csv")
al_h, al_b = rows("allocation_comparison.csv")
log_lines = open(os.path.join(BASE, "logs", "osrm.log")).read().splitlines()
log_sample = [l for l in log_lines if "| scheduler |" in l][:2] + [l for l in log_lines if "WARNING" in l][:2] + \
             [l for l in log_lines if "ERROR" in l][:1]
n_log = len(log_lines)
summary = subprocess.run(["bash", os.path.join(BASE, "scripts", "log_summary.sh"), os.path.join(BASE, "logs", "osrm.log")],
                         stdout=subprocess.PIPE, universal_newlines=True).stdout
levels = re.findall(r"^\s+(INFO|WARNING|ERROR)\s+(\d+)$", summary, re.M)
level_txt = ", ".join("%s %s" % (a, b) for a, b in levels)
sys_files = sorted(f for f in os.listdir(OUT) if not f.startswith("."))

ARCH = """
<svg viewBox="0 0 760 330" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Helvetica, Arial" font-size="12">
 <defs><marker id="a" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#555"/></marker></defs>
 <rect x="10" y="8" width="740" height="34" rx="6" fill="#e8eef7" stroke="#4C78A8"/>
 <text x="380" y="30" text-anchor="middle" font-weight="bold">run.sh (Bash launcher): menu | demo | test | gen-workload | sysinfo | logsummary | clean</text>
 <rect x="10" y="62" width="740" height="40" rx="6" fill="#fdf0e0" stroke="#F58518"/>
 <text x="380" y="80" text-anchor="middle" font-weight="bold">main.py - interactive menu + argparse sub-commands</text>
 <text x="380" y="95" text-anchor="middle" font-size="11">menu | demo | sched | memory | deadlock | storage | analyze</text>
 <g font-weight="bold" text-anchor="middle">
 <rect x="10" y="130" width="170" height="70" rx="6" fill="#e6f3e6" stroke="#54A24B"/><text x="95" y="155">scheduler.py</text><text x="95" y="172" font-size="10" font-weight="normal">FCFS SJF SRTF PRIO RR</text><text x="95" y="187" font-size="10" font-weight="normal">Gantt, WT/TAT/RT</text>
 <rect x="200" y="130" width="170" height="70" rx="6" fill="#e6f3e6" stroke="#54A24B"/><text x="285" y="155">memory.py</text><text x="285" y="172" font-size="10" font-weight="normal">FIFO LRU OPT Clock, Belady</text><text x="285" y="187" font-size="10" font-weight="normal">first/best/worst fit</text>
 <rect x="390" y="130" width="170" height="70" rx="6" fill="#e6f3e6" stroke="#54A24B"/><text x="475" y="155">deadlock.py</text><text x="475" y="172" font-size="10" font-weight="normal">Banker's safety + request</text><text x="475" y="187" font-size="10" font-weight="normal">deadlock detection</text>
 <rect x="580" y="130" width="170" height="70" rx="6" fill="#e6f3e6" stroke="#54A24B"/><text x="665" y="155">storage.py</text><text x="665" y="172" font-size="10" font-weight="normal">6 disk algorithms</text><text x="665" y="187" font-size="10" font-weight="normal">contiguous/linked/indexed</text>
 </g>
 <rect x="10" y="225" width="240" height="40" rx="6" fill="#f3e8f3" stroke="#B279A2"/><text x="130" y="242" text-anchor="middle" font-weight="bold">validation.py</text><text x="130" y="257" text-anchor="middle" font-size="10">ValidationError, loaders, range checks</text>
 <rect x="270" y="225" width="220" height="40" rx="6" fill="#f3e8f3" stroke="#B279A2"/><text x="380" y="242" text-anchor="middle" font-weight="bold">logger.py</text><text x="380" y="257" text-anchor="middle" font-size="10">logs/osrm.log  time | LEVEL | module | msg</text>
 <rect x="510" y="225" width="240" height="40" rx="6" fill="#e8f4f4" stroke="#72B7B2"/><text x="630" y="242" text-anchor="middle" font-weight="bold">reporting.py</text><text x="630" y="257" text-anchor="middle" font-size="10">tables, CSV, charts, observations</text>
 <rect x="10" y="285" width="370" height="36" rx="6" fill="#fdecec" stroke="#E45756"/><text x="195" y="301" text-anchor="middle" font-weight="bold">bashtools.py  (subprocess + timeout + error handling)</text><text x="195" y="315" text-anchor="middle" font-size="10">scripts/gen_workload.sh  sysinfo.sh  log_summary.sh</text>
 <rect x="400" y="285" width="350" height="36" rx="6" fill="#eee" stroke="#888"/><text x="575" y="301" text-anchor="middle" font-weight="bold">data/ (inputs)  ->  outputs/ (traces, CSV, PNG, report)</text><text x="575" y="315" text-anchor="middle" font-size="10">screenshots/  docs/  tests/test_osrm.py</text>
 <path d="M380 42 V62" stroke="#555" marker-end="url(#a)"/><path d="M380 102 V130" stroke="#555" marker-end="url(#a)"/>
 <path d="M95 200 V225" stroke="#555" marker-end="url(#a)"/><path d="M285 200 V225" stroke="#555" marker-end="url(#a)"/>
 <path d="M475 200 V225" stroke="#555" marker-end="url(#a)"/><path d="M665 200 V225" stroke="#555" marker-end="url(#a)"/>
 <path d="M130 265 V285" stroke="#555" marker-end="url(#a)"/><path d="M630 265 V285" stroke="#555" marker-end="url(#a)"/>
</svg>"""

FLOW = """
<svg viewBox="0 0 760 150" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Helvetica, Arial" font-size="11">
 <defs><marker id="b" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#555"/></marker></defs>
 <g text-anchor="middle">
 <rect x="5" y="20" width="110" height="50" rx="6" fill="#eee" stroke="#888"/><text x="60" y="42">Input</text><text x="60" y="57" font-size="9">CSV / JSON / typed</text>
 <rect x="140" y="20" width="110" height="50" rx="6" fill="#f3e8f3" stroke="#B279A2"/><text x="195" y="42">validation</text><text x="195" y="57" font-size="9">ValidationError</text>
 <rect x="275" y="20" width="110" height="50" rx="6" fill="#e6f3e6" stroke="#54A24B"/><text x="330" y="42">simulation</text><text x="330" y="57" font-size="9">module logic</text>
 <rect x="410" y="20" width="110" height="50" rx="6" fill="#e8f4f4" stroke="#72B7B2"/><text x="465" y="42">result objects</text><text x="465" y="57" font-size="9">timeline / steps / path</text>
 <rect x="545" y="20" width="110" height="50" rx="6" fill="#fdf0e0" stroke="#F58518"/><text x="600" y="42">reporting</text><text x="600" y="57" font-size="9">tables, CSV, charts</text>
 <rect x="670" y="20" width="85" height="50" rx="6" fill="#eee" stroke="#888"/><text x="712" y="42">outputs/</text><text x="712" y="57" font-size="9">report.md</text>
 <rect x="140" y="100" width="380" height="36" rx="6" fill="#fdecec" stroke="#E45756"/><text x="330" y="116">Bash path: bashtools.py -> scripts/*.sh -> generated CSV / snapshot / log summary</text><text x="330" y="129" font-size="9">(subprocess, 20 s timeout, non-zero exit -> BashToolError)</text>
 <rect x="545" y="100" width="210" height="36" rx="6" fill="#eef" stroke="#77a"/><text x="650" y="116">logger -> logs/osrm.log</text><text x="650" y="129" font-size="9">every action, warning and error</text>
 </g>
 <g stroke="#555" fill="none" marker-end="url(#b)"><path d="M115 45 H140"/><path d="M250 45 H275"/><path d="M385 45 H410"/><path d="M520 45 H545"/><path d="M655 45 H670"/><path d="M330 100 V70"/><path d="M600 100 V70"/></g>
 <text x="380" y="12" text-anchor="middle" font-weight="bold" font-size="11">Errors raised at any stage are caught in main.py and shown as "Error: ..." (no traceback)</text>
</svg>"""

CSS = """
@page { size: A4; margin: 16mm 15mm 16mm 15mm;
  @bottom-center { content: "OSRM Technical Report - Nikhil Sharma | 2401010084 - page " counter(page); font-size: 8pt; color: #777; } }
body { font-family: Helvetica, Arial, sans-serif; font-size: 9.6pt; line-height: 1.38; color: #222; }
h1 { font-size: 22pt; margin: 0 0 4px; color: #1f3a5f; } h2 { font-size: 13.5pt; color: #1f3a5f; border-bottom: 2px solid #4C78A8; padding-bottom: 2px; margin: 14px 0 6px; }
h3 { font-size: 10.8pt; margin: 9px 0 3px; color: #333; } p { margin: 4px 0; } ul { margin: 3px 0 3px 18px; padding: 0; } li { margin: 1px 0; }
table { border-collapse: collapse; width: 100%; margin: 5px 0 8px; font-size: 8.6pt; } th { background: #1f3a5f; color: #fff; text-align: left; padding: 3px 6px; }
td { padding: 2.5px 6px; border-bottom: 1px solid #ddd; vertical-align: top; } tr:nth-child(even) td { background: #f5f7fa; }
pre { background: #f3f3f3; border: 1px solid #ddd; padding: 6px 8px; font-size: 7.6pt; line-height: 1.25; overflow: hidden; margin: 5px 0; }
.pb { page-break-before: always; } .meta { color: #555; margin-bottom: 8px; } .fig { text-align: center; margin: 4px 0; } .cap { font-size: 8pt; color: #555; text-align: center; margin-top: 0; }
.box { background: #eef4fb; border-left: 4px solid #4C78A8; padding: 5px 9px; margin: 6px 0; } img { max-width: 100%; }
.two { display: flex; gap: 10px; } .two > div { flex: 1; }
"""

PHASES = [
    ["1. System Design and Planning", "Problem analysis; split into four resource-management modules plus validation, logging, reporting and Bash layers; "
     "designed data structures, input formats (CSV/JSON) and the menu/CLI flow; chose stdlib-only core with optional matplotlib.",
     "Sections 2-4; data/*.csv|json; README architecture"],
    ["2. Core Resource-Management Modules", "Implemented 5 CPU schedulers, 4 page-replacement algorithms + 3 partition strategies, Banker's algorithm + detection, "
     "6 disk-scheduling algorithms + 3 file-allocation methods with bitmap; 3 Bash scripts bridged through subprocess.",
     "modules/scheduler|memory|deadlock|storage|bashtools.py; scripts/*.sh"],
    ["3. Analysis and Comparison", "Comparative tables, frame sweeps, Belady's anomaly, head-movement and allocation comparison; CSV export, labelled charts and "
     "auto-generated technical observations.", "Section 5-6; modules/reporting.py; outputs/*.csv|png; analysis_report.md"],
    ["4. Testing and Reliability", "%s unittest cases (valid, invalid, boundary, textbook values, menu/EOF/Ctrl+C, Bash tools); ValidationError with meaningful messages; "
     "central logging; failed operations never change state." % n_tests, "tests/test_osrm.py; validation.py; logger.py; outputs/test_results.txt"],
    ["5. Documentation and Demonstration", "README, this report, saved demo trace, charts, screenshots guide and a one-command demo.",
     "README.md; docs/REPORT.pdf; screenshots/; outputs/demo_trace.txt"],
]

doc = """<!doctype html><html><head><meta charset="utf-8"><title>OSRM Report</title><style>%(css)s</style></head><body>
<h1>OSRM - Operating System Resource Manager Simulator</h1>
<div class="meta"><b>Capstone technical report</b> &nbsp;|&nbsp; %(author)s</div>

<h2>1. Problem Statement</h2>
<p>An operating system must share a few scarce resources - the CPU, main memory, and secondary storage - among many competing processes while avoiding deadlock.
Studying the policies involved in isolation (a scheduling lab here, a paging lab there) hides how they interact and makes comparison hard.
<b>OSRM</b> is one integrated Python + Bash application that simulates the major resource-management functions behind a single menu/CLI, validates all input,
logs every action, and produces comparable results (tables, CSV, charts and an auto-written analysis) from real runs.</p>
<div class="box"><b>Objectives.</b> (1) Implement CPU scheduling, memory management, deadlock handling and storage management as reusable classes/functions.
(2) Reproduce textbook results exactly (FCFS WT 17, FIFO/LRU/Optimal 15/12/9 faults, Banker's safe sequence P1,P3,P4,P0,P2, disk totals 640/236/331/382/299/322).
(3) Never crash on bad input. (4) Integrate Bash tooling through subprocess. (5) Present analytical results with justified observations.</div>
<p><b>Environment:</b> macOS, /usr/bin/python3 3.9, bash 3.2; core uses only the standard library, matplotlib is optional (ASCII charts are the fallback).</p>

<h2>2. Modular Architecture</h2>
%(arch)s
<p class="cap">Figure 1 - Module architecture. Simulation modules contain only logic; validation, logging and reporting are shared services.</p>

<h2>3. Data Structures</h2>
%(ds)s

<h2>4. Workflow / Input-Output Flow</h2>
%(flow)s
<p class="cap">Figure 2 - Data flow for one operation.</p>
<ul>
<li><b>Input:</b> sample files in <code>data/</code> (processes.csv, memory.json, banker.json, disk.json), user-typed data in the menu, or a workload produced by <code>gen_workload.sh</code>.</li>
<li><b>Processing:</b> validation raises <code>ValidationError</code>; the menu re-prompts, the CLI prints <code>Error: ...</code> and exits with code 2.</li>
<li><b>Output:</b> console tables and traces, <code>outputs/*.csv</code>, <code>outputs/*.png</code>, <code>outputs/analysis_report.md</code>, <code>outputs/demo_trace.txt</code> and <code>logs/osrm.log</code>.</li>
</ul>
<h3>Implementation plan (as executed)</h3>
%(plan)s

<h2>5. Module Descriptions</h2>
<h3>5.1 Scheduler (<code>scheduler.py</code>)</h3>
<p>FCFS, non-preemptive SJF and Priority share one engine that picks the ready process with the minimum key (ties: arrival, then input order); SRTF advances to the next arrival or completion and re-evaluates;
Round Robin uses a deque (new arrivals are queued before the pre-empted process). Idle gaps appear as <code>IDLE</code> segments. Metrics: completion, TAT = completion - arrival, WT = TAT - burst, RT = first start - arrival;
CPU utilisation = busy / (last completion - first arrival); throughput = processes / that span; a context switch is a hand-off to a different process.</p>
<h3>5.2 Memory (<code>memory.py</code>)</h3>
<p>FIFO (circular victim pointer), LRU (last-use timestamps), Optimal (farthest next use), Clock (second chance with reference bits and a hand). Each run returns faults, hits, hit ratio and a frame-by-frame trace.
<code>frame_sweep</code> runs 1..7 frames; <code>find_belady</code> detects increases. Fixed-partition allocation implements first/best/worst fit with per-partition internal fragmentation and a list of unallocated processes.</p>
<h3>5.3 Deadlock (<code>deadlock.py</code>)</h3>
<p><code>BankersState</code> computes Need = Max - Allocation and runs the safety algorithm (passes over P0..Pn-1, producing a traced safe sequence). <code>request_resources</code> checks request &le; need, request &le; available,
then <i>tentatively grants</i>, re-runs safety and <b>rolls back</b> if unsafe. <code>detect_deadlock</code> implements the detection algorithm and returns the deadlocked processes.</p>
<h3>5.4 Storage (<code>storage.py</code>)</h3>
<p>Each disk algorithm builds the list of head positions visited; total movement is the sum of absolute differences. SCAN/C-SCAN travel to the disk edge, LOOK/C-LOOK to the last request;
<b>the C-SCAN/C-LOOK return jump is counted</b>. <code>SimDisk</code> keeps a bitmap and directory; <code>create_file</code> plans the allocation first and only then mutates, so duplicate names, invalid sizes,
oversize files and insufficient (or insufficiently contiguous) space are rejected <i>without changing the disk</i>.</p>
<h3>5.5 Reporting and Bash integration</h3>
<p><code>reporting.py</code> renders boxed tables, Gantt charts, CSV files, matplotlib charts (ASCII fallback) and rule-based observations computed from the results.
<code>bashtools.py</code> runs <code>gen_workload.sh</code> (validates N, optional seed, reproducible), <code>sysinfo.sh</code> (portable via <code>uname -s</code>) and <code>log_summary.sh</code> (awk/grep) with a timeout and error mapping to <code>BashToolError</code>.</p>

<h2 class="pb">6. Results (from a real run)</h2>
<h3>6.1 CPU scheduling - sample workload data/processes.csv (6 processes, idle gap before P6, RR q=4)</h3>
%(sched_tbl)s
<div class="fig">%(sched_img)s</div><p class="cap">Figure 3 - Average WT / TAT / RT per algorithm (outputs/scheduling_comparison.png).</p>
<p><b>FCFS Gantt chart and per-process table</b> (excerpt of outputs/scheduling_traces.txt):</p><pre>%(fcfs)s</pre>
<p><b>SRTF per-process metrics:</b></p>
%(srtf_tbl)s

<h3 class="pb">6.2 Memory management</h3>
<p>Reference string 7 0 1 2 0 3 0 4 2 3 0 3 2 1 2 0 1 7 0 1, faults versus frames:</p>
%(sweep_tbl)s
<div class="fig">%(sweep_img)s</div><p class="cap">Figure 4 - Page faults vs number of frames.</p>
<p><b>Belady's anomaly</b> (reference string 1 2 3 4 1 2 5 1 2 3 4 5):</p>
%(belady_tbl)s
<div class="fig">%(belady_img)s</div><p class="cap">Figure 5 - FIFO rises from 9 faults (3 frames) to 10 (4 frames); LRU and Optimal never rise.</p>
<p><b>Fixed-partition allocation</b> (partitions 100, 500, 200, 300, 600; processes 212, 417, 112, 426, 650):</p>
%(part_tbl)s

<h3>6.3 Deadlock handling</h3>
<p>Silberschatz example, available 3 3 2, five processes. The initial state is safe; requests are applied in order to the same state:</p>
%(dl_tbl)s
<p>Deadlock detection (textbook scenario): with no blocking requests there is no deadlock; after P2 requests one more unit of C the deadlocked set is {P1, P2, P3, P4}.</p>

<h3>6.4 Storage management</h3>
<div class="two"><div>%(dk_tbl)s</div><div class="fig">%(dk_img)s<p class="cap">Figure 6 - Head movement (queue 98 183 37 122 14 124 65 67, head 53, 200 cylinders).</p></div></div>
<p><b>File allocation</b> on a 70-block disk with 12 create/delete operations (including a duplicate name and an oversize request):</p>
%(al_tbl)s
<div class="fig">%(al_img)s</div><p class="cap">Figure 7 - Allocation method comparison.</p>

<h2>7. Technical Observations (auto-generated by reporting.py)</h2>
<h3>CPU scheduling</h3>%(o_sched)s
<h3>Memory management</h3>%(o_mem)s
<h3>Deadlock handling</h3>%(o_dl)s
<h3>Storage management</h3>%(o_st)s

<h2>8. Testing Summary</h2>
<div class="box"><b>Real result: Ran %(n)s tests in %(secs)ss - %(status)s</b> (outputs/test_results.txt, run with <code>./run.sh test</code>).</div>
%(test_tbl)s
<p>The suite asserts: FCFS WT 17, SJF WT 7, RR q=4 WT 5.67; FIFO/LRU/Optimal = 15/12/9 faults; Belady 9 &rarr; 10; Banker's sequence P1,P3,P4,P0,P2 and the three request outcomes (granted, denied: not available, denied: unsafe with rollback verified);
disk totals 640/236/331/382/299/322. Invalid cases: missing/empty/malformed files, duplicate pid, zero/negative burst, quantum &le; 0, frames &le; 0, empty or non-integer reference string, disk request/head out of range,
mismatched matrices, allocation &gt; max, negative values. Boundary cases: single process with burst 1, frames = 1, frames &gt; unique pages, requests at 0 and size-1, empty request list, filling the disk exactly. The menu is tested with bad input, EOF and Ctrl+C.</p>

<h2>9. Logging and Error Handling</h2>
<p>All modules log through Python's <code>logging</code> to <code>logs/osrm.log</code> as <code>time | LEVEL | module | message</code>. After the demo run the log holds %(nlog)s records (%(levels)s).
User errors become <code>ValidationError</code> (shown as <code>Error: ...</code>, exit code 2); script failures become <code>BashToolError</code>; Ctrl+C and EOF end the menu cleanly; an unexpected exception is logged with its traceback to the file only.</p>
<pre>%(logs)s</pre>

<h2>10. Limitations and Future Work</h2>
<ul><li>Single-CPU, integer-time simulation; no multi-level feedback queues, no aging for Priority scheduling.</li>
<li>Disk scheduling treats all requests as present at time zero; no rotational latency model. Flat directory, no real file I/O.</li>
<li>Partition allocation is static (no compaction, no dynamic partitions); Clock uses a simple reference-bit model; overhead is counted in entries, not bytes.</li>
<li>Banker's algorithm assumes the maximum claims are known in advance; detection returns the deadlocked set but implements no recovery.</li>
<li>Future work: MLFQ, paging with a TLB model, resource-allocation-graph visualisation, real-time deadline scheduling.</li></ul>

<h2>11. Mapping of Work to Project Phases</h2>
%(phase_tbl)s
</body></html>"""

ds_rows = [
    ["Process / ScheduleResult", "dataclasses: pid, arrival, burst, priority; result holds timeline [(pid,start,end)], per-pid metrics dict, averages", "Gantt + metrics from one timeline"],
    ["deque of Process", "Round Robin ready queue; list of pending processes for the other algorithms", "O(1) queue ops"],
    ["Step / PageResult", "page, frame list (None = empty), fault flag, evicted page; faults, hits, hit ratio", "frame-by-frame trace"],
    ["frames list, last-use dict, ref-bit list", "FIFO pointer / LRU timestamps / Clock hand and reference bits", "replacement state"],
    ["Partition rows (dict)", "index, size, process, used, internal_frag; PartitionResult with unallocated list", "fit comparison"],
    ["BankersState", "available vector; Max, Allocation, Need matrices (lists of lists); SafetyResult(sequence, trace)", "safety + rollback"],
    ["DiskResult", "path = ordered list of head positions; total = sum of |differences|", "all 6 algorithms"],
    ["SimDisk", "bitmap list (0 free / 1 used), directory dict name -> FileEntry(blocks, index_block)", "free-space tracking"],
]
plan = tbl(["Step", "Work"], [
    ["1", "Study textbook algorithms and fix expected results; design module boundaries and input formats"],
    ["2", "Shared services first: validation.py (ValidationError), logger.py, package paths"],
    ["3", "Core modules: scheduler, memory, deadlock, storage - each verified against the textbook values"],
    ["4", "Reporting layer (tables, Gantt, CSV, charts, observations) and Bash scripts with bashtools.py"],
    ["5", "main.py menu + argparse, demo mode, run.sh launcher"],
    ["6", "Unit tests (valid/invalid/boundary), robustness checks, README, this report, screenshots"]])

fmt = dict(
    css=CSS, author=e(AUTHOR), arch=ARCH, flow=FLOW,
    ds=tbl(["Structure", "Contents", "Purpose"], ds_rows), plan=plan,
    sched_tbl=tbl(sched_h, sched_b), sched_img=img("scheduling_comparison.png", "70%"), fcfs=e(fcfs_block),
    srtf_tbl=tbl(["PID", "Arrival", "Burst", "Completion", "TAT", "WT", "RT"], srtf_rows),
    sweep_tbl=tbl(["Algorithm"] + ["%s frames" % h.split("_")[1] for h in sw_h[1:]], sw_b), sweep_img=img("page_faults_vs_frames.png", "56%"),
    belady_tbl=tbl(["Algorithm"] + ["%s fr" % h.split("_")[1] for h in bs_h[1:]], bs_b), belady_img=img("belady_anomaly.png", "56%"),
    part_tbl=tbl(["Strategy", "Total internal fragmentation", "Processes allocated"], part_sum),
    dl_tbl=tbl(["Process", "Request", "Outcome", "Granted"], dl_b),
    dk_tbl=tbl(["Algorithm", "Total movement"], [[r[0], r[1]] for r in dk_b]), dk_img=img("disk_head_movement.png", "100%"),
    al_tbl=tbl(["Method"] + [h.replace("_", " ") for h in al_h[1:]], al_b), al_img=img("allocation_comparison.png", "50%"),
    o_sched=bullets(observations("1.")), o_mem=bullets(observations("2.")), o_dl=bullets(observations("3.")), o_st=bullets(observations("4.")),
    n=n_tests, secs=secs, status=status, test_tbl=tbl(["Test class", "Passing tests"], test_rows),
    nlog=n_log, levels=e(level_txt), logs=e("\n".join(log_sample)),
    phase_tbl=tbl(["Phase", "My work", "Evidence"], PHASES),
)
html_path = os.path.join(BASE, "docs", "REPORT.html")
with open(html_path, "w", encoding="utf-8") as fh:
    fh.write(doc % fmt)
pdf = os.path.join(BASE, "docs", "REPORT.pdf")
subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--print-to-pdf=" + pdf, "file://" + html_path],
               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
pages = len(re.findall(rb"/Type\s*/Page[^s]", open(pdf, "rb").read()))
print("wrote", pdf, "pages:", pages)
