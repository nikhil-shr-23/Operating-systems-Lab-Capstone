"""Unit tests for the Disk Scheduling Simulator (./run.sh test or python3 tests/test_disk.py -v)."""
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

import main as sim                                        # noqa: E402
from modules import bashtools, disk, reporting            # noqa: E402
from modules.validation import (ValidationError, load_json, parse_float,   # noqa: E402
                                parse_int_list, validate_disk)

Q = [98, 183, 37, 122, 14, 124, 65, 67]


class TestAlgorithms(unittest.TestCase):
    def total(self, algo, d="up", q=None, head=53, size=200):
        return disk.schedule_disk(algo, Q if q is None else q, head, size, d).total

    def test_textbook_totals(self):
        expected = {"FCFS": 640, "SSTF": 236, "SCAN": 331, "C-SCAN": 382, "LOOK": 299, "C-LOOK": 322}
        got = dict((r.algo, r.total) for r in disk.compare_disk(Q, 53, 200, "up"))
        self.assertEqual(got, expected)

    def test_paths(self):
        self.assertEqual(disk.schedule_disk("SSTF", Q, 53, 200).path, [53, 65, 67, 37, 14, 98, 122, 124, 183])
        self.assertEqual(disk.schedule_disk("C-SCAN", Q, 53, 200).path, [53, 65, 67, 98, 122, 124, 183, 199, 0, 14, 37])

    def test_service_order_excludes_turnaround_points(self):
        r = disk.schedule_disk("SCAN", Q, 53, 200)
        self.assertEqual(r.service_order, [65, 67, 98, 122, 124, 183, 37, 14])
        self.assertEqual(sorted(r.service_order), sorted(Q))
        self.assertEqual(disk.schedule_disk("FCFS", Q, 53, 200).service_order, Q)

    def test_every_algorithm_serves_every_request(self):
        for r in disk.compare_disk(Q, 53, 200):
            self.assertEqual(sorted(r.service_order), sorted(Q), r.algo)

    def test_metrics(self):
        r = disk.schedule_disk("FCFS", Q, 53, 200, seek_ms=0.5)
        self.assertEqual(r.avg_seek, 80.0)
        self.assertEqual(r.seek_time, 320.0)
        self.assertEqual(sum(r.steps), r.total)

    def test_direction_down(self):
        self.assertEqual(self.total("SCAN", "down"), 53 + 183)
        self.assertEqual(self.total("LOOK", "down"), (53 - 14) + (183 - 14))
        self.assertEqual(self.total("C-LOOK", "down"), (53 - 14) + (183 - 14) + (183 - 65))

    def test_boundaries(self):
        for a in disk.DISK_ALGORITHMS:
            self.assertGreaterEqual(disk.schedule_disk(a, [0, 199], 100, 200).total, 199, a)
        self.assertEqual(disk.schedule_disk("FCFS", [0, 199], 0, 200).total, 199)

    def test_empty_queue(self):
        for a in disk.DISK_ALGORITHMS:
            r = disk.schedule_disk(a, [], 50, 100)
            self.assertEqual((r.total, r.path, r.avg_seek), (0, [50], 0.0), a)

    def test_request_at_head_and_duplicates(self):
        self.assertEqual(self.total("FCFS", q=[53]), 0)
        self.assertEqual(self.total("LOOK", q=[53]), 0)
        r = disk.schedule_disk("SSTF", [60, 60, 70], 50, 200)
        self.assertEqual(r.total, 20)
        self.assertEqual(r.service_order, [60, 60, 70])

    def test_single_cylinder_disk(self):
        self.assertEqual(disk.schedule_disk("SCAN", [0], 0, 1).total, 0)

    def test_all_requests_one_side(self):
        self.assertEqual(self.total("LOOK", q=[60, 70], head=50), 20)
        self.assertEqual(self.total("C-LOOK", q=[10, 20], head=50), 40 + 10)

    def test_look_never_worse_than_scan(self):
        for seed in range(25):
            q = disk.random_queue(12, 200, seed)
            self.assertLessEqual(self.total("LOOK", q=q), self.total("SCAN", q=q))
            self.assertLessEqual(self.total("C-LOOK", q=q), self.total("C-SCAN", q=q))

    def test_algorithm_name_aliases(self):
        for alias, name in (("cscan", "C-SCAN"), ("c_look", "C-LOOK"), (" sstf ", "SSTF")):
            self.assertEqual(disk.normalise_algo(alias), name)

    def test_experiment_is_reproducible(self):
        a = disk.random_experiment(100, [5, 10], 20, 1)
        b = disk.random_experiment(100, [5, 10], 20, 1)
        self.assertEqual(a, b)
        self.assertLess(a["SSTF"][1], a["FCFS"][1])


class TestValidation(unittest.TestCase):
    def test_bad_problems(self):
        bad = [dict(requests=[200], head=0, size=200), dict(requests=[-1], head=0, size=200),
               dict(requests=[1], head=200, size=200), dict(requests=[1], head=-1, size=200),
               dict(requests=[1], head=0, size=0), dict(requests=["x"], head=0, size=10),
               dict(requests=[1], head=0, size=10, direction="left")]
        for kw in bad:
            with self.assertRaises(ValidationError, msg=str(kw)):
                validate_disk(kw["requests"], kw["head"], kw["size"], kw.get("direction", "up"))
        with self.assertRaises(ValidationError):
            disk.schedule_disk("ELEVATOR", [1], 0, 10)

    def test_parsing(self):
        self.assertEqual(parse_int_list("1, 2  3", "x"), [1, 2, 3])
        for bad in ("abc", "nan", "inf", "-1"):
            with self.assertRaises(ValidationError):
                parse_float(bad, "x", 0)

    def test_json_loading(self):
        self.assertEqual(load_json(sim.SAMPLE_FILE, ("requests",))["head"], 53)
        for content in ("", "{bad", "[1]", '{"head": 1}'):
            fd, path = tempfile.mkstemp(suffix=".json")
            with os.fdopen(fd, "w") as fh:
                fh.write(content)
            with self.assertRaises(ValidationError, msg=content):
                load_json(path, ("requests",))
        with self.assertRaises(ValidationError):
            load_json("/no/such/file.json")


class TestReporting(unittest.TestCase):
    def test_table(self):
        self.assertIn("| 333 |", reporting.table(["a", "bb"], [[1, 2], [333, 4]], "rr"))

    def test_ascii_path_marks_start_served_and_edge(self):
        text = reporting.ascii_path(disk.schedule_disk("SCAN", Q, 53, 200), 200)
        self.assertEqual(text.count("H"), 1 + text.count("Head"))      # one start marker (plus word 'Head')
        self.assertIn("(turn/edge)", text)
        self.assertEqual(text.count("| +"), 9)

    def test_ascii_fallback_without_matplotlib(self):
        with mock.patch.dict(os.environ, {"OSRM_NO_MATPLOTLIB": "1"}):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                res = reporting.bar_chart(os.path.join(tempfile.gettempdir(), "x.png"), "T", ["A", "B"], [3, 6], "y")
            self.assertIsNone(res)
            self.assertIn("matplotlib not available", buf.getvalue())

    def test_charts_written_when_matplotlib_present(self):
        if not reporting.have_matplotlib():
            self.skipTest("matplotlib not installed")
        d = tempfile.mkdtemp()
        res = disk.compare_disk(Q, 53, 200)
        p = reporting.path_grid_chart(os.path.join(d, "g.png"), res, 200, 53)
        self.assertTrue(os.path.getsize(p) > 1000)


class TestCLI(unittest.TestCase):
    def run_main(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = sim.main(argv)
        return code, buf.getvalue()

    def test_simulate(self):
        code, text = self.run_main(["simulate"])
        self.assertEqual(code, 0)
        for token in ("Nikhil Sharma", "640", "236", "331", "382", "299", "322"):
            self.assertIn(token, text)

    def test_single_algo_and_visual(self):
        code, text = self.run_main(["simulate", "--algo", "cscan", "--visual"])
        self.assertEqual(code, 0)
        self.assertIn("Head movement: C-SCAN", text)
        self.assertNotIn("| FCFS", text)

    def test_errors_do_not_traceback(self):
        for argv in (["simulate", "--file", "/nope.json"], ["simulate", "--head", "999"],
                     ["simulate", "--algo", "elevator"], ["simulate", "--queue", "a b"],
                     ["simulate", "--seek-ms", "-3"], ["simulate", "--direction", "left"],
                     ["analyze", "--trials", "0"], ["gen", "0"], ["gen", "5", "--seed", "x"]):
            code, text = self.run_main(argv)
            self.assertEqual(code, 2, argv)
            self.assertIn("Error:", text)
            self.assertNotIn("Traceback", text)

    def test_gen_script(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "w.json")
        code, _ = self.run_main(["gen", "15", "--seed", "3", "--size", "500", "--out", path])
        self.assertEqual(code, 0)
        data = load_json(path, ("requests", "head", "disk_size"))
        self.assertEqual(len(data["requests"]), 15)
        validate_disk(data["requests"], data["head"], data["disk_size"], data["direction"])
        _, first = self.run_main(["gen", "15", "--seed", "3", "--size", "500", "--out", path + "2"])
        self.assertEqual(open(path).read(), open(path + "2").read())     # same seed -> same file

    def test_analysis_writes_outputs(self):
        d = tempfile.mkdtemp()
        dk = sim.load_problem()
        with contextlib.redirect_stdout(io.StringIO()):
            files = sim.run_analysis(validate_disk(dk["requests"], dk["head"], dk["disk_size"], "up"),
                                     out_dir=d, trials=20)
        names = [os.path.basename(f) for f in files]
        for need in ("analysis_report.md", "disk_head_movement.csv", "random_experiment.csv"):
            self.assertIn(need, names)
        report = open(os.path.join(d, "analysis_report.md")).read()
        self.assertIn("moves the head least", report)
        self.assertIn("SSTF", report)

    def test_logging_format(self):
        disk.schedule_disk("FCFS", [1], 0, 10)
        from modules.logger import log_path
        line = [l for l in open(log_path()).read().splitlines() if "| disk |" in l][-1]
        parts = [p.strip() for p in line.split("|")]
        self.assertEqual((parts[1], parts[2]), ("INFO", "disk"))


class TestMenu(unittest.TestCase):
    def run_menu(self, inputs):
        buf, it = io.StringIO(), iter(inputs)

        def fake_input(prompt=""):
            try:
                return next(it)
            except StopIteration:
                raise EOFError
        with mock.patch("builtins.input", fake_input), contextlib.redirect_stdout(buf):
            code = sim.main(["menu"])
        return code, buf.getvalue()

    def test_exit_immediately(self):
        code, text = self.run_menu(["0"])
        self.assertEqual(code, 0)
        self.assertIn("Goodbye", text)

    def test_bad_input_reprompts(self):
        code, text = self.run_menu(["abc", "99", "-1", "", "0"])
        self.assertEqual(code, 0)
        self.assertEqual(text.count("Please try again"), 4)

    def test_eof_is_graceful(self):
        code, text = self.run_menu([])
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", text)

    def test_simulate_custom_input_with_retry(self):
        code, text = self.run_menu(["1", "n", "100", "10 20 500", "50", "up",        # 500 invalid -> re-enter
                                    "100", "10 60 30", "50", "down", "scan", "n", "0"])
        self.assertEqual(code, 0)
        self.assertIn("Let's enter it again", text)
        self.assertIn("SCAN", text)

    def test_visualiser_option(self):
        code, text = self.run_menu(["2", "y", "0"])
        self.assertEqual(code, 0)
        self.assertIn("Head movement: C-LOOK", text)


if __name__ == "__main__":
    unittest.main()
