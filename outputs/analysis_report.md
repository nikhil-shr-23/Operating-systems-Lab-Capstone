# Disk Scheduling Simulator - Analysis Report

Author: Nikhil Sharma | Roll No 2401010084 | B.Tech CSE (Core), Section C

_Generated automatically from the simulation results of this run._

## Problem

- Head 53, disk size 200 cylinders (0..199), direction up.
- Request queue: 98 183 37 122 14 124 65 67

## Algorithm comparison

| Algorithm | Total movement | Avg seek | Seek ms |
|---|---|---|---|
| FCFS | 640 | 80.00 | 640 |
| SSTF | 236 | 29.50 | 236 |
| SCAN | 331 | 41.38 | 331 |
| C-SCAN | 382 | 47.75 | 382 |
| LOOK | 299 | 37.38 | 299 |
| C-LOOK | 322 | 40.25 | 322 |


## Random-queue experiment (mean cylinders moved)

| Algorithm | n=5 | n=10 | n=20 | n=40 | n=80 |
|---|---|---|---|---|---|
| FCFS | 345.0 | 674.4 | 1320.6 | 2655.6 | 5404.1 |
| SSTF | 171.0 | 225.8 | 255.0 | 280.4 | 286.2 |
| SCAN | 234.7 | 272.6 | 282.3 | 280.7 | 294.0 |
| C-SCAN | 335.5 | 359.7 | 383.2 | 387.7 | 393.1 |
| LOOK | 188.9 | 241.0 | 266.5 | 272.5 | 289.7 |
| C-LOOK | 235.4 | 301.8 | 349.4 | 370.9 | 385.1 |


## Observations

- SSTF moves the head least (236 cylinders); FCFS is the worst (640), 171% more.
- LOOK saves 32 cylinders over SCAN (299 vs 331) by turning at the last request instead of the disk edge; C-LOOK saves 60 over C-SCAN.
- FCFS is fair but ignores head position (avg seek 80.0 vs 29.5 for SSTF).
- SSTF has low movement but can starve distant requests; C-SCAN/C-LOOK trade extra movement (the return jump is counted) for more uniform waiting time.
- Over random queues, SSTF has the lowest mean movement at the longest queue (80 requests): 286.2 cylinders vs 5404.1 for FCFS.
- FCFS grows almost linearly with queue length, while the SCAN family flattens because each sweep serves more requests per pass.
