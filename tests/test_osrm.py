"""Unit tests for OSRM (run with ./run.sh test or python3 tests/test_osrm.py -v)."""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("OSRM_LOG_FILE", os.path.join(ROOT, "logs", "test.log"))

import main as osrm_main                                   # noqa: E402
from modules import bashtools, deadlock, memory, reporting, scheduler, storage  # noqa: E402
from modules.validation import (ValidationError, load_json, load_processes_csv,   # noqa: E402
                                validate_banker, validate_disk, validate_frames,
                                validate_quantum, validate_reference_string)

TEXTBOOK_REFS = [7, 0, 1, 2, 0, 3, 0, 4, 2, 3, 0, 3, 2, 1, 2, 0, 1, 7, 0, 1]
BELADY = [1, 2, 3, 4, 1, 2, 5, 1, 2, 3, 4, 5]
AVAIL = [3, 3, 2]
MAX = [[7, 5, 3], [3, 2, 2], [9, 0, 2], [2, 2, 2], [4, 3, 3]]
ALLOC = [[0, 1, 0], [2, 0, 0], [3, 0, 2], [2, 1, 1], [0, 0, 2]]
DISK_Q = [98, 183, 37, 122, 14, 124, 65, 67]


def procs(bursts, arrivals=None, prios=None):
    arrivals = arrivals or [0] * len(bursts)
    prios = prios or [0] * len(bursts)
    return scheduler.make_processes([("P%d" % (i + 1), arrivals[i], b, prios[i]) for i, b in enumerate(bursts)])


def write_tmp(text, suffix=".csv"):
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    return path


# ============================================================== scheduler
class TestScheduler(unittest.TestCase):
    def test_fcfs_textbook(self):
        r = scheduler.run_algorithm(procs([24, 3, 3]), "FCFS")
        self.assertAlmostEqual(r.avg_wt, 17.0)
        self.assertEqual([r.metrics[p]["wt"] for p in ("P1", "P2", "P3")], [0, 24, 27])

    def test_sjf_textbook(self):
        self.assertAlmostEqual(scheduler.run_algorithm(procs([6, 8, 7, 3]), "SJF").avg_wt, 7.0)

    def test_rr_textbook(self):
        r = scheduler.run_algorithm(procs([24, 3, 3]), "RR", 4)
        self.assertAlmostEqual(r.avg_wt, 17.0 / 3, places=2)
        self.assertEqual(round(r.avg_wt, 2), 5.67)

    def test_srtf_preempts(self):
        r = scheduler.run_algorithm(procs([8, 4, 9, 5], [0, 1, 2, 3]), "SRTF")
        self.assertAlmostEqual(r.avg_wt, 6.5)    # classic example: WT 9,0,15,2
        self.assertEqual(r.metrics["P2"]["wt"], 0)

    def test_priority_lower_number_first(self):
        r = scheduler.run_algorithm(procs([5, 5, 5], prios=[3, 1, 2]), "Priority")
        self.assertEqual([s[0] for s in r.timeline], ["P2", "P3", "P1"])

    def test_idle_gap_handled(self):
        r = scheduler.run_algorithm(procs([2, 2], [0, 10]), "FCFS")
        self.assertEqual(r.timeline, [("P1", 0, 2), ("IDLE", 2, 10), ("P2", 10, 12)])
        self.assertEqual(r.idle_time, 8)
        self.assertAlmostEqual(r.utilisation, 4 / 12.0 * 100)

    def test_idle_gap_every_algorithm(self):
        for algo in scheduler.ALGORITHMS:
            r = scheduler.run_algorithm(procs([3, 3], [0, 20]), algo, 2)
            self.assertEqual(r.metrics["P2"]["completion"], 23, algo)
            self.assertEqual(r.metrics["P2"]["wt"], 0, algo)

    def test_metrics_identity(self):
        for r in scheduler.run_all(procs([5, 3, 8, 2], [0, 1, 2, 3], [2, 1, 3, 1]), 3):
            for m in r.metrics.values():
                self.assertEqual(m["tat"], m["wt"] + m["burst"])
                self.assertEqual(m["tat"], m["completion"] - m["arrival"])

    def test_context_switches_rr(self):
        r = scheduler.run_algorithm(procs([24, 3, 3]), "RR", 4)
        # timeline P1 P2 P3 P1 (the P1 slices at 10-30 merge): 3 hand-offs
        self.assertEqual([seg[0] for seg in r.timeline], ["P1", "P2", "P3", "P1"])
        self.assertEqual(r.context_switches, 3)

    def test_boundary_single_process_burst_one(self):
        for algo in scheduler.ALGORITHMS:
            r = scheduler.run_algorithm(procs([1]), algo, 1)
            self.assertEqual(r.avg_wt, 0)
            self.assertEqual(r.avg_tat, 1)
            self.assertEqual(r.context_switches, 0)
            self.assertAlmostEqual(r.utilisation, 100.0)

    def test_quantum_larger_than_bursts_equals_fcfs(self):
        a = scheduler.run_algorithm(procs([5, 3, 2]), "RR", 100)
        b = scheduler.run_algorithm(procs([5, 3, 2]), "FCFS")
        self.assertEqual(a.avg_wt, b.avg_wt)

    def test_invalid_quantum(self):
        for q in (0, -3, "abc", 2.5):
            with self.assertRaises(ValidationError):
                scheduler.run_algorithm(procs([3]), "RR", q)

    def test_unknown_algorithm_and_empty(self):
        with self.assertRaises(ValidationError):
            scheduler.run_algorithm(procs([3]), "LOTTERY")
        with self.assertRaises(ValidationError):
            scheduler.run_algorithm([], "FCFS")

    def test_invalid_processes(self):
        bad = [
            [("P1", 0, 0, 1)],                    # zero burst
            [("P1", 0, -2, 1)],                   # negative burst
            [("P1", -1, 2, 1)],                   # negative arrival
            [("P1", 0, 2, 1), ("P1", 1, 2, 1)],   # duplicate pid
            [("P1", 0, 2, -1)],                   # negative priority
            [("P1", "x", 2, 1)],                  # non-integer
            [("", 0, 2, 1)],                      # empty pid
            [],                                   # empty list
        ]
        for rows in bad:
            with self.assertRaises(ValidationError, msg=str(rows)):
                scheduler.make_processes(rows)

    def test_csv_loading_valid_and_sample(self):
        ps = scheduler.load_processes(os.path.join(ROOT, "data", "processes.csv"))
        self.assertEqual(len(ps), 6)

    def test_csv_errors(self):
        with self.assertRaises(ValidationError):
            load_processes_csv("/no/such/file.csv")
        empty = write_tmp("")
        with self.assertRaises(ValidationError):
            load_processes_csv(empty)
        for text in ("pid,arrival\nP1,0\n",                      # missing column
                     "pid,arrival,burst,priority\nP1,0,5\n",       # short row
                     "pid,arrival,burst,priority\nP1,0,abc,1\n",   # non numeric
                     "pid,arrival,burst,priority\nP1,0,5,1\nP1,1,2,1\n",  # duplicate
                     "pid,arrival,burst,priority\nP1,0,0,1\n",     # zero burst
                     "pid,arrival,burst,priority\n"):              # header only
            with self.assertRaises(ValidationError, msg=text):
                load_processes_csv(write_tmp(text))

    def test_directory_as_file(self):
        with self.assertRaises(ValidationError):
            load_processes_csv(tempfile.gettempdir())


# ================================================================= memory
class TestMemory(unittest.TestCase):
    def faults(self, algo, refs, frames):
        return memory.simulate_pages(algo, refs, frames).faults

    def test_textbook_three_frames(self):
        self.assertEqual(self.faults("FIFO", TEXTBOOK_REFS, 3), 15)
        self.assertEqual(self.faults("LRU", TEXTBOOK_REFS, 3), 12)
        self.assertEqual(self.faults("Optimal", TEXTBOOK_REFS, 3), 9)

    def test_clock_between_bounds(self):
        c = self.faults("Clock", TEXTBOOK_REFS, 3)
        self.assertTrue(9 <= c <= 20)

    def test_belady_anomaly(self):
        self.assertEqual(self.faults("FIFO", BELADY, 3), 9)
        self.assertEqual(self.faults("FIFO", BELADY, 4), 10)
        sweep = memory.frame_sweep(BELADY, 7)
        self.assertEqual(memory.find_belady(sweep["FIFO"]), [(3, 4, 9, 10)])
        self.assertEqual(memory.find_belady(sweep["LRU"]), [])
        self.assertEqual(memory.find_belady(sweep["Optimal"]), [])

    def test_optimal_never_worse(self):
        for f in range(1, 8):
            opt = self.faults("Optimal", TEXTBOOK_REFS, f)
            for a in ("FIFO", "LRU", "Clock"):
                self.assertLessEqual(opt, self.faults(a, TEXTBOOK_REFS, f))

    def test_sweep_shape(self):
        sweep = memory.frame_sweep(TEXTBOOK_REFS, 7)
        self.assertEqual(set(sweep), set(memory.PAGE_ALGORITHMS))
        self.assertTrue(all(len(v) == 7 for v in sweep.values()))

    def test_boundary_one_frame(self):
        r = memory.simulate_pages("LRU", [1, 2, 1, 2], 1)
        self.assertEqual(r.faults, 4)
        r = memory.simulate_pages("FIFO", [5, 5, 5], 1)
        self.assertEqual((r.faults, r.hits), (1, 2))

    def test_boundary_frames_exceed_unique_pages(self):
        for a in memory.PAGE_ALGORITHMS:
            r = memory.simulate_pages(a, [1, 2, 3, 1, 2, 3], 10)
            self.assertEqual(r.faults, 3, a)
            self.assertAlmostEqual(r.hit_ratio, 0.5)

    def test_single_reference(self):
        self.assertEqual(self.faults("Optimal", [4], 1), 1)

    def test_trace_and_hit_ratio(self):
        r = memory.simulate_pages("FIFO", TEXTBOOK_REFS, 3)
        self.assertEqual(len(r.steps), 20)
        self.assertEqual(r.hits + r.faults, 20)
        self.assertEqual(r.steps[0].frames, [7, None, None])
        self.assertAlmostEqual(r.hit_ratio, 5 / 20.0)

    def test_invalid_inputs(self):
        for refs in ([], "", "a b c", "1 -2 3", [1, "x"]):
            with self.assertRaises(ValidationError, msg=repr(refs)):
                memory.simulate_pages("FIFO", refs, 3)
        for fr in (0, -1, "two", None):
            with self.assertRaises(ValidationError, msg=repr(fr)):
                memory.simulate_pages("FIFO", [1, 2], fr)
        with self.assertRaises(ValidationError):
            memory.simulate_pages("MRU", [1], 1)

    def test_reference_string_parsing(self):
        self.assertEqual(validate_reference_string("1, 2 3"), [1, 2, 3])

    def test_partition_fits(self):
        parts, ps = [100, 500, 200, 300, 600], [("P1", 212), ("P2", 417), ("P3", 112), ("P4", 426)]
        first = memory.allocate_partitions(parts, ps, "first")
        best = memory.allocate_partitions(parts, ps, "best")
        worst = memory.allocate_partitions(parts, ps, "worst")
        self.assertEqual([r["process"] for r in first.partitions], [None, "P1", "P3", None, "P2"])
        self.assertEqual(first.unallocated, ["P4"])
        self.assertEqual(best.unallocated, [])
        self.assertEqual(best.internal_fragmentation, 88 + 83 + 88 + 174)
        self.assertEqual(sum(r["used"] for r in best.partitions), 212 + 417 + 112 + 426)
        self.assertEqual(worst.partitions[4]["process"], "P1")      # worst fit takes the 600 partition first

    def test_partition_unallocated_and_internal_frag(self):
        r = memory.allocate_partitions([10, 20], [("A", 15), ("B", 25)], "first")
        self.assertEqual(r.unallocated, ["B"])
        self.assertEqual(r.internal_fragmentation, 5)

    def test_partition_invalid(self):
        with self.assertRaises(ValidationError):
            memory.allocate_partitions([], [("A", 1)], "first")
        with self.assertRaises(ValidationError):
            memory.allocate_partitions([10], [("A", 0)], "first")
        with self.assertRaises(ValidationError):
            memory.allocate_partitions([10], [("A", 5), ("A", 5)], "first")
        with self.assertRaises(ValidationError):
            memory.allocate_partitions([10], [("A", 5)], "random")


# ================================================================ deadlock
class TestDeadlock(unittest.TestCase):
    def state(self):
        return deadlock.BankersState(AVAIL, MAX, ALLOC)

    def test_need_matrix(self):
        self.assertEqual(self.state().need[0], [7, 4, 3])
        self.assertEqual(self.state().need[1], [1, 2, 2])

    def test_safe_sequence(self):
        res = self.state().safety_check()
        self.assertTrue(res.safe)
        self.assertEqual(res.sequence, ["P1", "P3", "P4", "P0", "P2"])
        self.assertTrue(len(res.trace) > 5)

    def test_textbook_request_chain(self):
        st = self.state()
        r1 = st.request_resources("P1", [1, 0, 2])
        self.assertTrue(r1.granted)
        self.assertEqual(st.available, [2, 3, 0])
        r2 = st.request_resources("P4", [3, 3, 0])
        self.assertFalse(r2.granted)
        self.assertEqual(r2.status, "not_available")
        r3 = st.request_resources("P0", [0, 2, 0])
        self.assertFalse(r3.granted)
        self.assertEqual(r3.status, "unsafe")

    def test_rollback_restores_state(self):
        st = self.state()
        st.request_resources("P1", [1, 0, 2])
        avail, alloc = list(st.available), [list(r) for r in st.allocation]
        st.request_resources("P0", [0, 2, 0])          # unsafe -> rolled back
        self.assertEqual(st.available, avail)
        self.assertEqual(st.allocation, alloc)

    def test_request_exceeds_need(self):
        res = self.state().request_resources("P1", [4, 0, 0])
        self.assertEqual(res.status, "exceeds_need")

    def test_request_validation(self):
        st = self.state()
        for pid, req in (("P9", [0, 0, 0]), ("P1", [1, 0]), ("P1", [-1, 0, 0]), ("Px", [0, 0, 0])):
            with self.assertRaises(ValidationError, msg=str((pid, req))):
                st.request_resources(pid, req)

    def test_zero_request_is_granted(self):
        self.assertTrue(self.state().request_resources(2, [0, 0, 0]).granted)

    def test_unsafe_initial_state(self):
        st = deadlock.BankersState([0, 0, 0], MAX, ALLOC)
        self.assertFalse(st.safety_check().safe)

    def test_matrix_validation(self):
        with self.assertRaises(ValidationError):
            validate_banker([1, 1], MAX, ALLOC)                      # width mismatch
        with self.assertRaises(ValidationError):
            validate_banker(AVAIL, MAX, ALLOC[:3])                   # row count mismatch
        with self.assertRaises(ValidationError):
            validate_banker(AVAIL, MAX, [[8, 1, 0]] + ALLOC[1:])     # allocation > max
        with self.assertRaises(ValidationError):
            validate_banker([-1, 0, 0], MAX, ALLOC)                  # negative
        with self.assertRaises(ValidationError):
            validate_banker(AVAIL, [[1, 2], [3]], [[0, 0], [0, 0]])  # ragged
        with self.assertRaises(ValidationError):
            validate_banker(AVAIL, [], [])

    def test_detection_textbook(self):
        alloc = [[0, 1, 0], [2, 0, 0], [3, 0, 3], [2, 1, 1], [0, 0, 2]]
        ok = deadlock.detect_deadlock([0, 0, 0], alloc, [[0, 0, 0], [2, 0, 2], [0, 0, 0], [1, 0, 0], [0, 0, 2]])
        self.assertEqual(ok.deadlocked, [])
        bad = deadlock.detect_deadlock([0, 0, 0], alloc, [[0, 0, 0], [2, 0, 2], [0, 0, 1], [1, 0, 0], [0, 0, 2]])
        self.assertEqual(bad.deadlocked, ["P1", "P2", "P3", "P4"])

    def test_detection_validation(self):
        with self.assertRaises(ValidationError):
            deadlock.detect_deadlock([0, 0], [[0, 0]], [[0, 0], [0, 0]])
        with self.assertRaises(ValidationError):
            deadlock.detect_deadlock([0, 0], [[0, 0]], [[0]])

    def test_sample_file_matches_textbook(self):
        d = load_json(os.path.join(ROOT, "data", "banker.json"), ("available", "max", "allocation"))
        st = osrm_main.banker_state(d)
        self.assertEqual(st.safety_check().sequence, ["P1", "P3", "P4", "P0", "P2"])


# ================================================================ storage
class TestDisk(unittest.TestCase):
    def total(self, algo, d="up", q=None, head=53, size=200):
        return storage.schedule_disk(algo, DISK_Q if q is None else q, head, size, d).total

    def test_textbook_totals(self):
        expected = {"FCFS": 640, "SSTF": 236, "SCAN": 331, "C-SCAN": 382, "LOOK": 299, "C-LOOK": 322}
        got = dict((r.algo, r.total) for r in storage.compare_disk(DISK_Q, 53, 200, "up"))
        self.assertEqual(got, expected)

    def test_cscan_jump_is_counted(self):
        path = storage.schedule_disk("C-SCAN", DISK_Q, 53, 200).path
        self.assertEqual(path, [53, 65, 67, 98, 122, 124, 183, 199, 0, 14, 37])

    def test_direction_down(self):
        self.assertEqual(self.total("SCAN", "down"), 53 + 183)       # to 0, back to 183
        self.assertEqual(self.total("LOOK", "down"), (53 - 14) + (183 - 14))
        self.assertEqual(self.total("C-LOOK", "down"), (53 - 14) + (183 - 14) + (183 - 65))

    def test_boundaries_zero_and_last_cylinder(self):
        for a in storage.DISK_ALGORITHMS:
            r = storage.schedule_disk(a, [0, 199], 100, 200)
            self.assertGreaterEqual(r.total, 199, a)
        self.assertEqual(storage.schedule_disk("FCFS", [0, 199], 0, 200).total, 199)
        self.assertEqual(storage.schedule_disk("SSTF", [199, 0], 0, 200).total, 199)

    def test_empty_queue(self):
        for a in storage.DISK_ALGORITHMS:
            r = storage.schedule_disk(a, [], 50, 100)
            self.assertEqual((r.total, r.path), (0, [50]), a)

    def test_request_at_head(self):
        self.assertEqual(self.total("FCFS", q=[53]), 0)
        self.assertEqual(self.total("LOOK", q=[53]), 0)

    def test_single_cylinder_disk(self):
        self.assertEqual(storage.schedule_disk("SCAN", [0], 0, 1).total, 0)

    def test_all_requests_one_side(self):
        self.assertEqual(self.total("LOOK", q=[60, 70], head=50), 20)
        self.assertEqual(self.total("C-LOOK", q=[10, 20], head=50), 40 + 10)

    def test_validation(self):
        bad = [dict(requests=[200], head=0, size=200),        # request outside
               dict(requests=[-1], head=0, size=200),
               dict(requests=[1], head=200, size=200),        # head outside
               dict(requests=[1], head=-1, size=200),
               dict(requests=[1], head=0, size=0),            # bad size
               dict(requests=["x"], head=0, size=10),
               dict(requests=[1], head=0, size=10, direction="left")]
        for kw in bad:
            with self.assertRaises(ValidationError, msg=str(kw)):
                validate_disk(kw["requests"], kw["head"], kw["size"], kw.get("direction", "up"))
        with self.assertRaises(ValidationError):
            storage.schedule_disk("ELEVATOR", [1], 0, 10)


class TestFileAllocation(unittest.TestCase):
    def test_contiguous_allocation_and_bitmap(self):
        d = storage.SimDisk(20)
        e = d.create_file("a", 5, "contiguous")
        self.assertEqual(e.blocks, [0, 1, 2, 3, 4])
        self.assertEqual(d.bitmap[:6], [1, 1, 1, 1, 1, 0])
        self.assertEqual(storage.access_cost(e), [1] * 5)

    def test_linked_and_indexed_costs(self):
        d = storage.SimDisk(30)
        linked = d.create_file("l", 6, "linked")
        indexed = d.create_file("i", 6, "indexed")
        self.assertEqual(storage.access_cost(linked), [1, 2, 3, 4, 5, 6])
        self.assertEqual(storage.access_cost(indexed), [2] * 6)
        self.assertIsNotNone(indexed.index_block)
        self.assertEqual(d.bitmap.count(1), 6 + 7)

    def test_rejections_do_not_change_state(self):
        d = storage.SimDisk(10)
        d.create_file("a", 4, "contiguous")
        before = d.snapshot()
        bad = [("a", 2, "contiguous"),      # duplicate
               ("", 2, "linked"),           # invalid name
               ("b", 0, "linked"),          # invalid size
               ("b", -3, "indexed"),
               ("b", "x", "indexed"),
               ("b", 11, "linked"),         # larger than disk
               ("b", 7, "linked"),          # insufficient free (6 left)
               ("b", 6, "indexed"),         # needs 7 incl. index block
               ("b", 2, "magnetic")]        # unknown method
        for name, size, method in bad:
            with self.assertRaises(ValidationError, msg=str((name, size, method))):
                d.create_file(name, size, method)
            self.assertEqual(d.snapshot(), before)
        self.assertEqual(sorted(d.files), ["a"])

    def test_external_fragmentation_blocks_contiguous_only(self):
        d = storage.SimDisk(12)
        for n in "abcd":
            d.create_file(n, 3, "contiguous")
        d.delete_file("a")
        d.delete_file("c")                                   # free runs: [0-2], [6-8]
        self.assertEqual(d.free_runs(), [(0, 3), (6, 3)])
        before = d.snapshot()
        with self.assertRaises(ValidationError):
            d.create_file("big", 5, "contiguous")
        self.assertEqual(d.snapshot(), before)
        d.create_file("big", 5, "linked")                    # works: any free blocks
        self.assertEqual(d.free_count(), 1)

    def test_delete_frees_blocks(self):
        d = storage.SimDisk(10)
        d.create_file("a", 4, "indexed")
        d.delete_file("a")
        self.assertEqual(d.free_count(), 10)
        with self.assertRaises(ValidationError):
            d.delete_file("a")

    def test_boundary_fill_disk_exactly(self):
        d = storage.SimDisk(5)
        d.create_file("a", 5, "contiguous")
        self.assertEqual(d.free_count(), 0)
        self.assertEqual(d.external_fragmentation(), 0.0)
        with self.assertRaises(ValidationError):
            d.create_file("b", 1, "linked")

    def test_indexed_needs_extra_block(self):
        d = storage.SimDisk(5)
        with self.assertRaises(ValidationError):
            d.create_file("a", 5, "indexed")
        d.create_file("a", 4, "indexed")

    def test_invalid_disk_size(self):
        for n in (0, -1, "x"):
            with self.assertRaises(ValidationError):
                storage.SimDisk(n)

    def test_comparison_on_sample_workload(self):
        d = load_json(os.path.join(ROOT, "data", "disk.json"), ("requests", "head", "disk_size"))
        s = storage.compare_allocation(d["total_blocks"], d["file_ops"])
        self.assertEqual(s["contiguous"]["avg_access_cost"], 1.0)
        self.assertGreater(s["linked"]["avg_access_cost"], s["indexed"]["avg_access_cost"])
        self.assertGreater(s["contiguous"]["external_frag_pct"], 0)
        self.assertEqual(s["indexed"]["extra_blocks"], s["indexed"]["created"])


# =============================================================== validation
class TestValidation(unittest.TestCase):
    def test_missing_and_malformed_json(self):
        with self.assertRaises(ValidationError):
            load_json("/no/such.json")
        with self.assertRaises(ValidationError):
            load_json(write_tmp("{ not json", ".json"))
        with self.assertRaises(ValidationError):
            load_json(write_tmp("[1,2]", ".json"))
        with self.assertRaises(ValidationError):
            load_json(write_tmp("{}", ".json"), ("need",))
        with self.assertRaises(ValidationError):
            load_json(write_tmp("   \n", ".json"))

    def test_frames_and_quantum(self):
        self.assertEqual(validate_frames("3"), 3)
        self.assertEqual(validate_quantum(1), 1)
        for bad in (0, -1, "", "1.5x", True):
            with self.assertRaises(ValidationError):
                validate_frames(bad)
            with self.assertRaises(ValidationError):
                validate_quantum(bad)

    def test_messages_are_meaningful(self):
        try:
            scheduler.make_processes([("P1", 0, 0, 1)])
        except ValidationError as exc:
            self.assertIn("Burst time of P1", str(exc))


# ============================================================ reporting/CLI
class TestReportingAndCLI(unittest.TestCase):
    def run_main(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = osrm_main.main(argv)
        return code, buf.getvalue()

    def test_table_and_gantt(self):
        t = reporting.table(["a", "bb"], [[1, 2], [333, 4]], "rr")
        self.assertIn("| 333 |", t)
        g = reporting.gantt(scheduler.run_algorithm(procs([3, 2]), "FCFS").timeline)
        self.assertIn("P1", g)
        self.assertIn("5", g)

    def test_ascii_bar_fallback_when_matplotlib_missing(self):
        with mock.patch.dict(os.environ, {"OSRM_NO_MATPLOTLIB": "1"}):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                res = reporting.bar_chart(os.path.join(tempfile.gettempdir(), "x.png"), "T", ["A", "B"], [3, 6], "y")
            self.assertIsNone(res)
            self.assertIn("matplotlib not available", buf.getvalue())
            self.assertIn("#", buf.getvalue())

    def test_charts_written_when_matplotlib_present(self):
        if not reporting.have_matplotlib():
            self.skipTest("matplotlib not installed")
        d = tempfile.mkdtemp()
        p = reporting.line_chart(os.path.join(d, "l.png"), "t", [1, 2, 3], {"a": [3, 2, 1]}, "y", "x")
        self.assertTrue(os.path.getsize(p) > 1000)

    def test_cli_valid_commands(self):
        code, text = self.run_main(["sched", "--algo", "fcfs"])
        self.assertEqual(code, 0)
        self.assertIn("Nikhil Sharma", text)
        code, text = self.run_main(["storage", "--disk-only"])
        self.assertIn("640", text)
        code, text = self.run_main(["memory", "--algo", "lru", "--no-trace", "--frames", "3"])
        self.assertEqual(code, 0)

    def test_cli_errors_do_not_traceback(self):
        for argv in (["sched", "--file", "/nope.csv"], ["sched", "--algo", "rr", "--quantum", "0"],
                     ["memory", "--frames", "0"], ["memory", "--refs", "a b"],
                     ["storage", "--head", "999"], ["deadlock", "--request", "P1:1,0"],
                     ["deadlock", "--request", "oops"]):
            code, text = self.run_main(argv)
            self.assertEqual(code, 2, argv)
            self.assertIn("Error:", text)
            self.assertNotIn("Traceback", text)

    def test_full_analysis_writes_outputs(self):
        d = tempfile.mkdtemp()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            files = osrm_main.run_full_analysis(out_dir=d)
        names = [os.path.basename(f) for f in files]
        for need in ("analysis_report.md", "scheduling_summary.csv", "disk_head_movement.csv", "page_faults_sweep.csv"):
            self.assertIn(need, names)
        report = open(os.path.join(d, "analysis_report.md")).read()
        self.assertIn("Lowest average waiting time", report)
        self.assertIn("Belady", report)

    def test_logging_format(self):
        scheduler.run_algorithm(procs([3]), "FCFS")
        from modules.logger import log_path
        line = [l for l in open(log_path()).read().splitlines() if "| scheduler |" in l][-1]
        parts = [p.strip() for p in line.split("|")]
        self.assertEqual(len(parts) >= 4, True)
        self.assertEqual(parts[1], "INFO")
        self.assertEqual(parts[2], "scheduler")


class TestMenuRobustness(unittest.TestCase):
    def run_menu(self, inputs):
        buf = io.StringIO()
        it = iter(inputs)

        def fake_input(prompt=""):
            try:
                return next(it)
            except StopIteration:
                raise EOFError
        with mock.patch("builtins.input", fake_input), contextlib.redirect_stdout(buf):
            code = osrm_main.main(["menu"])
        return code, buf.getvalue()

    def test_exit_immediately(self):
        code, text = self.run_menu(["0"])
        self.assertEqual(code, 0)
        self.assertIn("Goodbye", text)

    def test_bad_input_reprompts(self):
        code, text = self.run_menu(["abc", "99", "-1", "", "0"])
        self.assertEqual(code, 0)
        self.assertEqual(text.count("Please try again"), 4)

    def test_eof_is_clean(self):
        code, text = self.run_menu([])
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", text)

    def test_eof_midway(self):
        code, text = self.run_menu(["1", "y", "5"])        # EOF at the quantum prompt
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", text)

    def test_keyboard_interrupt_is_clean(self):
        buf = io.StringIO()
        with mock.patch("builtins.input", side_effect=KeyboardInterrupt), contextlib.redirect_stdout(buf):
            code = osrm_main.main(["menu"])
        self.assertEqual(code, 130)
        self.assertNotIn("Traceback", buf.getvalue())

    def test_scheduling_via_menu_sample_data(self):
        code, text = self.run_menu(["1", "y", "6", "", "0"])
        self.assertIn("Scheduling comparison", text)

    def test_custom_data_with_retry(self):
        # bad line (burst 0) -> re-entered; then FCFS
        inputs = ["1", "n", "2", "P1 0 0", "", "P1 0 5", "P2 1 3", "", "1", "0"]
        code, text = self.run_menu(inputs)
        self.assertIn("Burst time of P1", text)
        self.assertIn("Average WT", text)

    def test_memory_custom_reference_string(self):
        code, text = self.run_menu(["2", "1", "n", "1 x", "1 2 3 1", "0", "2", "0"])
        self.assertIn("Faults = 3", text)

    def test_full_analysis_option_exists_in_menu(self):
        self.assertIn("5) Run full analysis", osrm_main.MENU)


# =========================================================== bash scripts
class TestBashTools(unittest.TestCase):
    def test_gen_workload_roundtrip(self):
        path = os.path.join(tempfile.mkdtemp(), "w.csv")
        bashtools.gen_workload(12, 7, path)
        ps = scheduler.load_processes(path)
        self.assertEqual(len(ps), 12)
        results = scheduler.run_all(ps, 4)
        self.assertEqual(len(results), 5)

    def test_gen_workload_reproducible_with_seed(self):
        d = tempfile.mkdtemp()
        a, b = os.path.join(d, "a.csv"), os.path.join(d, "b.csv")
        bashtools.gen_workload(10, 99, a)
        bashtools.gen_workload(10, 99, b)
        self.assertEqual(open(a).read(), open(b).read())

    def test_gen_workload_invalid_n(self):
        for n in (0, -5, "abc", 1001, ""):
            with self.assertRaises(ValidationError, msg=repr(n)):
                bashtools.gen_workload(n, 1, os.path.join(tempfile.mkdtemp(), "x.csv"))

    def test_script_rejects_bad_args_directly(self):
        for args in (["x"], ["0"], ["5", "notanumber"], []):
            with self.assertRaises(bashtools.BashToolError):
                bashtools.run_script("gen_workload.sh", args)

    def test_sysinfo_content(self):
        text = bashtools.sysinfo()
        for key in ("OS", "CPU cores", "Total memory", "Disk", "Process count", "Top 5"):
            self.assertIn(key, text)

    def test_log_summary(self):
        log = write_tmp("2026-01-01 10:00:00 | INFO | scheduler | a\n2026-01-01 10:00:01 | ERROR | memory | b\n"
                        "2026-01-01 10:00:02 | INFO | scheduler | c\n", ".log")
        text = bashtools.log_summary(log)
        self.assertRegex(text, r"INFO\s+2")
        self.assertRegex(text, r"ERROR\s+1")
        self.assertRegex(text, r"scheduler\s+2")

    def test_log_summary_missing_file(self):
        with self.assertRaises(bashtools.BashToolError):
            bashtools.log_summary("/no/such/file.log")

    def test_missing_script_and_timeout(self):
        with self.assertRaises(bashtools.BashToolError):
            bashtools.run_script("nope.sh")
        slow = os.path.join(osrm_main.BASE_DIR, "scripts", "_slow_test.sh")
        with open(slow, "w") as fh:
            fh.write("sleep 5\n")
        try:
            with self.assertRaises(bashtools.BashToolError) as cm:
                bashtools.run_script("_slow_test.sh", timeout=1)
            self.assertIn("timed out", str(cm.exception))
        finally:
            os.remove(slow)


if __name__ == "__main__":
    unittest.main()
