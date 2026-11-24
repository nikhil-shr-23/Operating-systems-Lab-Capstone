# OSRM - Analysis Report

Author: Nikhil Sharma | Roll No 2401010084 | B.Tech CSE (Core), Section C

_Generated automatically from the simulation results of this run._

## 1. CPU Scheduling

| Algorithm | Avg WT | Avg TAT | Avg RT | CPU util % | Throughput | Ctx switches |
|---|---|---|---|---|---|---|
| FCFS | 9.50 | 14.67 | 9.50 | 93.94 | 0.182 | 5 |
| SJF | 6.83 | 12.00 | 6.83 | 93.94 | 0.182 | 5 |
| SRTF | 5.50 | 10.67 | 3.67 | 93.94 | 0.182 | 6 |
| Priority | 8.83 | 14.00 | 8.83 | 93.94 | 0.182 | 5 |
| RR | 10.83 | 16.00 | 5.00 | 93.94 | 0.182 | 9 |

- Lowest average waiting time: SRTF (5.50) versus RR (10.83), a 49% reduction - it always runs the job with the least remaining work and preempts on arrival, which minimises the time other jobs spend queued.
- Best average response time: SRTF (3.67).
- Round Robin (q=4) performed 9 context switches against 5 for FCFS; its avg TAT is 16.00 vs 14.67 for FCFS, showing the fairness/overhead trade-off.
- FCFS shows the convoy effect: P5 waits 22 units because earlier arrivals run to completion first.
- Priority scheduling makes P5 (priority 5) wait 22 units - low-priority work can starve; aging would be needed in a real OS.
- The workload contains an idle gap (2 units); CPU utilisation is 93.9% for every algorithm because total work is fixed and only ordering changes.

## 2. Memory Management

| Algorithm | Frames | Faults | Hits | Hit ratio |
|---|---|---|---|---|
| FIFO | 3 | 15 | 5 | 25.0% |
| LRU | 3 | 12 | 8 | 40.0% |
| Optimal | 3 | 9 | 11 | 55.0% |
| Clock | 3 | 14 | 6 | 30.0% |

| Algorithm | 1 fr | 2 fr | 3 fr | 4 fr | 5 fr | 6 fr | 7 fr |
|---|---|---|---|---|---|---|---|
| FIFO | 20 | 15 | 15 | 10 | 9 | 6 | 6 |
| LRU | 20 | 17 | 12 | 8 | 7 | 6 | 6 |
| Optimal | 20 | 13 | 9 | 8 | 7 | 6 | 6 |
| Clock | 20 | 15 | 14 | 9 | 9 | 6 | 6 |

- With 3 frames the ranking by page faults is Optimal=9 < LRU=12 < Clock=14 < FIFO=15. Optimal (9) is the theoretical lower bound; LRU (12) approximates it by using the past as a predictor of the future, while FIFO (15) ignores usage and evicts hot pages.
- Clock (second chance) gave 14 faults - between FIFO and LRU - at the cost of one reference bit per frame instead of full timestamps.
- Increasing frames reduces faults until every distinct page fits; in the sweep all algorithms converge to the same minimum (6 faults) once frames >= distinct pages.
- Belady's anomaly reproduced: FIFO on 1 2 3 4 1 2 5 1 2 3 4 5 incurs 9 faults with 3 frames but 10 faults with 4 frames (more memory, more faults).
- LRU and Optimal never showed the anomaly: they are stack algorithms, so the set of pages in memory with n frames is always a subset of the set with n+1 frames.
- Fixed-partition allocation: best fit gave the best result (1 unallocated, internal fragmentation 433); first fit: 2 unallocated, frag 559; best fit: 1 unallocated, frag 433; worst fit: 2 unallocated, frag 659.

## 3. Deadlock Handling

- Initial state is SAFE with safe sequence <P1, P3, P4, P0, P2>.
- Request: P1 request [1, 0, 2] GRANTED; safe sequence P1, P3, P4, P0, P2.
- Request: P4 requested [3, 3, 0] but only [2, 3, 0] available -> DENIED (must wait).
- Request: P0 request [0, 2, 0] would leave the system UNSAFE -> DENIED, state rolled back.
- Banker's algorithm denies requests that would lead to an unsafe state, even though resources are available - avoidance trades some utilisation for a guarantee of freedom from deadlock.
- Detection: the first scenario has no deadlock; after P2 asks for one more resource the deadlocked set is P1, P2, P3, P4. Detection must be paired with a recovery policy (kill or roll back).

## 4. Storage Management

| Algorithm | Total head movement |
|---|---|
| FCFS | 640 |
| SSTF | 236 |
| SCAN | 331 |
| C-SCAN | 382 |
| LOOK | 299 |
| C-LOOK | 322 |

- Disk scheduling: SSTF moves the head least (236 cylinders); FCFS is the worst (640), 171% more.
- LOOK saves 32 cylinders over SCAN (299 vs 331) by turning at the last request instead of the disk edge; C-LOOK saves 60 over C-SCAN.
- SSTF has low movement but can starve distant requests; C-SCAN/C-LOOK trade extra movement (the return jump is counted) for more uniform waiting time.
- File allocation: contiguous allocation gives the cheapest access (avg 1.00 block reads) but left 3 free fragments (external fragmentation 35.0%) and rejected 2 operation(s); linked and indexed use any free block so they rejected 1 and 2.
- Linked allocation has the worst direct-access cost (avg 6.60, worst 20 reads, since blocks are reached by following pointers); indexed costs a constant 2 reads but spends 6 extra index block(s).
