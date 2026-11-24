# OSRM - Operating System Resource Manager Simulator

**Author:** Nikhil Sharma | Roll No 2401010084 | B.Tech CSE (Core), Section C

OSRM is one integrated Python + Bash application that simulates the major resource-management
functions of an operating system and presents the results as tables, charts and an automatically
generated technical analysis. The Python core uses only the standard library (matplotlib is optional);
three Bash scripts are called from Python through `subprocess`.

## Overview

| Area | What is simulated |
|---|---|
| CPU scheduling | FCFS, SJF (non-preemptive), SRTF, Priority (non-preemptive, lower number = higher priority), Round Robin; Gantt chart, completion/TAT/WT/RT, averages, CPU utilisation, throughput, context switches, idle gaps |
| Memory | Page replacement FIFO / LRU / Optimal / Clock with frame-by-frame traces, frames sweep 1..7, Belady's anomaly; fixed-partition first/best/worst fit with internal fragmentation |
| Deadlock | Banker's algorithm (safety trace, requests with rollback) and deadlock detection |
| Storage | Disk scheduling FCFS, SSTF, SCAN, C-SCAN, LOOK, C-LOOK; file allocation (contiguous / linked / indexed) on a bitmap-managed simulated disk |
| Reporting | Text tables, CSV export, labelled charts, auto-generated observations in `outputs/analysis_report.md` |
| Bash integration | `gen_workload.sh`, `sysinfo.sh`, `log_summary.sh` |

## Architecture

```
                         run.sh  (Bash launcher)
                            |
                         main.py  (menu + argparse: menu/demo/sched/memory/deadlock/storage/analyze)
                            |
   +-------------+----------+----------+-------------+
   | scheduler   |  memory  | deadlock |   storage   |   <- core simulation modules (pure logic)
   +------+------+----+-----+----+-----+------+------+
          |           |          |            |
          +-----------+----+-----+------------+
                           |
        validation.py (ValidationError)   logger.py (logs/osrm.log)
                           |
        reporting.py (tables, CSV, charts, observations)   bashtools.py --subprocess--> scripts/*.sh
```

```
osrm/
  main.py  run.sh  README.md
  modules/  scheduler.py memory.py deadlock.py storage.py validation.py logger.py reporting.py bashtools.py
  scripts/  sysinfo.sh gen_workload.sh log_summary.sh
  data/     processes.csv memory.json banker.json disk.json
  tests/    test_osrm.py
  outputs/  traces, CSVs, charts, analysis_report.md, demo_trace.txt, test_results.txt
  logs/     osrm.log
  screenshots/  docs/ (REPORT.pdf)
```

## Requirements

* macOS (or Linux) with `/usr/bin/python3` 3.7+ (developed on macOS, Python 3.9, bash 3.2). Nothing to install for core features.
* Optional: `matplotlib` for PNG charts (`/usr/bin/python3 -m pip install --user matplotlib`). Without it OSRM prints ASCII bar charts and says so.

## Install and run (macOS)

```bash
unzip osrm.zip && cd osrm
chmod +x run.sh scripts/*.sh        # only needed if the zip lost permissions
./run.sh menu                       # interactive menu (default)
./run.sh demo                       # everything, non-interactive -> outputs/demo_trace.txt
./run.sh test                       # unit tests -> outputs/test_results.txt
./run.sh gen-workload 12 42         # random workload CSV (12 processes, seed 42) -> outputs/generated_workload.csv
./run.sh sysinfo                    # live system snapshot
./run.sh logsummary                 # awk/grep summary of logs/osrm.log
./run.sh clean                      # delete generated outputs, logs, caches
```

### Example commands

```bash
python3 main.py sched --algo rr --quantum 3
python3 main.py sched --file outputs/generated_workload.csv --algo all
python3 main.py memory --refs "7 0 1 2 0 3 0 4 2 3 0 3 2 1 2 0 1 7 0 1" --frames 3
python3 main.py memory --belady --no-trace --sweep
python3 main.py memory --partitions --no-trace
python3 main.py deadlock                       # sample data + requests + detection
python3 main.py deadlock --request P1:1,0,2 --request P0:0,2,0
python3 main.py storage --queue "98 183 37 122 14 124 65 67" --head 53 --size 200 --direction up
python3 main.py analyze                        # all modules, charts, report
```

The menu offers: 1 Scheduling, 2 Memory, 3 Deadlock, 4 Storage, 5 Full analysis, 6 Bash tools, 7 View log, 0 Exit.
Each module lets you use the sample data or type your own; bad input re-prompts, and EOF / Ctrl+C exit cleanly.

## Sample input formats

`data/processes.csv` (priority optional, lower number = higher priority):
```
pid,arrival,burst,priority
P1,0,8,3
P2,1,4,1
```
`data/memory.json` - `reference_string`, `frames`, `max_frames`, `belady_string`, `partitions`, `processes` (`[name, size]`).
`data/banker.json` - `available`, `max`, `allocation`, `requests` (`{pid, request}`) and a `detection` block. The default data is the Silberschatz textbook example.
`data/disk.json` - `requests`, `head`, `disk_size`, `direction`, `total_blocks`, `file_ops` (`{op: create|delete, name, size}`).

## Design decisions worth knowing

* **Disk scheduling:** SCAN and C-SCAN go to the physical disk edge; LOOK / C-LOOK stop at the last request. **The C-SCAN return jump (e.g. 199 -> 0) is counted as head movement** (that is why the textbook result is 382). C-LOOK's jump is counted too.
* **Round Robin:** a process arriving during a slice is queued before the pre-empted process is re-queued.
* **Context switch** = CPU handed to a different process than the previous one (first dispatch is not counted).
* **CPU utilisation** = busy time / (last completion - first arrival).
* **File allocation overhead** = metadata entries (contiguous: start+length; linked: one pointer per block; indexed: one entry per block + an index block). Failed allocations never modify the disk.

## Running the tests

```bash
./run.sh test          # or: /usr/bin/python3 tests/test_osrm.py -v
```
The suite (unittest) covers valid, invalid and boundary inputs and asserts the textbook values
(FCFS 17, SJF 7, RR 5.67; FIFO 15 / LRU 12 / Optimal 9 faults; Belady 9 -> 10; Banker's sequence
P1,P3,P4,P0,P2 with the three request outcomes; disk totals 640/236/331/382/299/322). Tests log to
`logs/test.log`, so `logs/osrm.log` only holds application runs.

## Logging

Every action and error is written by the `logging` module to `logs/osrm.log` as
`time | LEVEL | module | message`. `./run.sh logsummary` summarises it by level and module.

## Project-phase mapping

| Phase | Where it lives |
|---|---|
| 1. System Design and Planning | Architecture + data-structure design (this README, `docs/REPORT.pdf`), module split, input formats in `data/` |
| 2. Core Resource-Management Modules | `modules/scheduler.py`, `memory.py`, `deadlock.py`, `storage.py`, `scripts/*.sh`, `bashtools.py` |
| 3. Analysis and Comparison | `modules/reporting.py`, `main.py analyze`, `outputs/*.csv`, charts, `outputs/analysis_report.md` |
| 4. Testing and Reliability | `tests/test_osrm.py`, `modules/validation.py`, `modules/logger.py`, `outputs/test_results.txt` |
| 5. Documentation and Demonstration | `README.md`, `docs/REPORT.pdf`, `screenshots/`, `./run.sh demo`, `outputs/demo_trace.txt` |

## Limitations

Single-CPU, single-threaded simulation with integer time units; flat directory and no real I/O;
disk scheduling treats all requests as present at time 0; partition allocation is static (no compaction);
Clock uses a simple reference-bit model; file-allocation overhead is counted in entries, not bytes.
