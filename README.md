# Disk Scheduling Simulator

**Author:** Nikhil Sharma | Roll No 2401010084 | B.Tech CSE (Core), Section C

A Python (standard library only; matplotlib optional) simulator and visualiser for disk-head
scheduling algorithms: **FCFS, SSTF, SCAN, C-SCAN, LOOK, C-LOOK**. Two Bash helper scripts are
called from Python through `subprocess`.

## What it does

| Feature | Detail |
|---|---|
| Algorithms | FCFS, SSTF, SCAN, C-SCAN, LOOK, C-LOOK, with a configurable start direction |
| Metrics | Total head movement, average seek per request, total seek time (ms/cylinder), service order |
| Visualiser | Step-by-step ASCII head movement in the terminal; PNG panel of all six head paths |
| Analysis | Comparison table and bar chart, random-queue experiment (mean movement vs queue length), auto-generated observations in `outputs/analysis_report.md` |
| Input | Sample file, JSON workloads, command-line flags, or interactive prompts, all validated |
| Bash integration | `gen_requests.sh` (seeded random workload), `sysinfo.sh`, `log_summary.sh` |

Conventions: SCAN/C-SCAN go to the physical disk edge before turning, LOOK/C-LOOK only to the last
request, and the C-SCAN/C-LOOK return jump **is counted** as head movement.

## Layout

```
main.py  run.sh  README.md
modules/  disk.py (algorithms)  validation.py  reporting.py  logger.py  bashtools.py
scripts/  gen_requests.sh  sysinfo.sh  log_summary.sh
data/     disk.json            (sample: queue 98 183 37 122 14 124 65 67, head 53, 200 cylinders)
tests/    test_disk.py
outputs/  generated tables, CSVs, charts, analysis_report.md, demo_trace.txt
logs/     osrm.log
```

## Run (macOS or Linux, Python 3.7+)

```bash
./run.sh menu                 # interactive menu (default)
./run.sh demo                 # everything, non-interactive -> outputs/demo_trace.txt
./run.sh analyze              # tables, CSVs, charts, experiment, report -> outputs/
./run.sh test                 # unit tests -> outputs/test_results.txt
./run.sh gen 12 42            # 12 random requests, seed 42 -> outputs/generated_requests.json
./run.sh sysinfo | logsummary | clean
```

Optional charts: `python3 -m pip install --user matplotlib`. Without it ASCII charts are printed.

### Examples

```bash
python3 main.py simulate                                   # all six algorithms, sample data
python3 main.py simulate --algo cscan --visual             # watch the head move, step by step
python3 main.py simulate --queue "98 183 37 122 14 124 65 67" --head 53 --size 200 --direction down
python3 main.py simulate --explain --seek-ms 0.2
python3 main.py gen 20 --seed 1 --size 500 --out outputs/w.json && python3 main.py simulate --file outputs/w.json
python3 main.py analyze --trials 500
```

Expected totals for the sample: FCFS 640, SSTF 236, SCAN 331, C-SCAN 382, LOOK 299, C-LOOK 322.

## Errors

Bad input (head outside the disk, non-numeric requests, unknown algorithm, missing or malformed
file...) prints `Error: <message>` and exits with code 2. No tracebacks. Everything is logged to
`logs/osrm.log` as `time | LEVEL | module | message`.
