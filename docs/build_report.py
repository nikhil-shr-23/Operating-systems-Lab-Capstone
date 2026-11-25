"""Developer tool: build docs/REPORT.pdf from the REAL outputs of a run.

Reads outputs/*.csv, *.png, test_results.txt and demo_trace.txt, writes docs/REPORT.html and prints it
to PDF with headless Chrome.  Run `./run.sh test` and `./run.sh demo` first so every number is real.
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


def tbl(headers, body):
    h = "".join("<th>%s</th>" % e(str(x)) for x in headers)
    b = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % e(str(c)) for c in r) for r in body)
    return "<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (h, b)


def img(name, caption, width="92%"):
    with open(os.path.join(OUT, name), "rb") as fh:
        data = base64.b64encode(fh.read()).decode()
    return ('<figure><img src="data:image/png;base64,%s" style="width:%s"><figcaption>%s</figcaption></figure>'
            % (data, width, e(caption)))


def section(n, title, body):
    return "<section><h2>%s. %s</h2>%s</section>" % (n, e(title), body)


def main():
    for need in ("disk_head_movement.csv", "disk_head_movement.png", "disk_head_paths.png",
                 "random_experiment.csv", "movement_vs_queue_length.png", "test_results.txt", "demo_trace.txt"):
        if not os.path.exists(os.path.join(OUT, need)):
            sys.exit("Missing outputs/%s - run ./run.sh test and ./run.sh demo first." % need)

    cmp_h, cmp_b = rows("disk_head_movement.csv")
    cmp_rows = [[r[0], r[1], r[2], r[3], r[5]] for r in cmp_b]
    exp_h, exp_b = rows("random_experiment.csv")
    tests = read("test_results.txt")
    n_tests = re.search(r"Ran (\d+) tests", tests).group(1)
    ok = "OK" in tests.splitlines()[-1]
    notes = [l[2:] for l in read("analysis_report.md").splitlines() if l.startswith("- ") and "cylinders" in l]
    scan_trace = read("demo_trace.txt")
    m = re.search(r"Head movement: SCAN.*?\n(.*?)\n\n", scan_trace, re.S)
    visual = m.group(0).strip() if m else ""

    parts = []
    parts.append("""<header><h1>Disk Scheduling Simulator</h1>
      <p class="sub">Operating Systems Lab - design, implementation and analysis</p>
      <p class="auth">%s</p></header>""" % e(AUTHOR))

    parts.append(section(1, "Objective", """
      <p>The disk is the slowest part of a computer, and most of its access time is the <b>seek</b>: moving the
      read/write head to the right cylinder. A disk-scheduling algorithm chooses the order in which pending
      requests are served so that total head movement, and therefore waiting time, is reduced.</p>
      <p>This project simulates six classic algorithms in Python, visualises how the head moves, compares them on a
      given queue and on thousands of random queues, and reports the results automatically.</p>"""))

    parts.append(section(2, "Algorithms and conventions", tbl(["Algorithm", "Rule"], [
        ["FCFS", "Serve requests in arrival order. Fair, but ignores head position."],
        ["SSTF", "Always serve the nearest request. Low movement, but distant requests can starve."],
        ["SCAN", "Sweep to the disk edge, reverse, serving requests on the way (elevator)."],
        ["C-SCAN", "Sweep one way to the edge, jump to the other edge, sweep again in the same direction."],
        ["LOOK", "Like SCAN, but reverse at the last request instead of the disk edge."],
        ["C-LOOK", "Like C-SCAN, but jump back to the farthest pending request instead of the edge."]]) + """
      <p class="note">Conventions: total movement is the sum of |difference| between consecutive head positions.
      The C-SCAN / C-LOOK return jump <b>is counted</b>. A request exactly at the head belongs to the current
      direction.</p>"""))

    parts.append(section(3, "Design", """
      <p>Pure-logic core (<code>modules/disk.py</code>) with each algorithm producing the list of head positions it
      visits; everything else is built on that path.</p>
      <ul>
        <li><b>main.py / run.sh</b> - interactive menu and sub-commands (<code>simulate, visual, analyze, gen, demo</code>).</li>
        <li><b>disk.py</b> - algorithms, metrics (total, average seek, seek time, service order), random experiment.</li>
        <li><b>validation.py</b> - every input is checked; problems raise a clear <code>ValidationError</code>, shown as
            <code>Error: ...</code> with exit code 2, never a traceback.</li>
        <li><b>reporting.py</b> - tables, ASCII head-movement visualiser, CSV, matplotlib charts (ASCII fallback),
            automatic observations.</li>
        <li><b>logger.py</b> - <code>logs/osrm.log</code> in the format <code>time | LEVEL | module | message</code>.</li>
        <li><b>Bash</b> - <code>gen_requests.sh</code> (seeded random workload JSON), <code>sysinfo.sh</code>,
            <code>log_summary.sh</code>, called from Python with <code>subprocess</code> and a timeout.</li>
      </ul>"""))

    parts.append(section(4, "Results on the textbook queue", """
      <p>Queue <code>98 183 37 122 14 124 65 67</code>, head at 53, 200 cylinders (0-199), moving up,
      1 ms per cylinder.</p>""" + tbl(["Algorithm", "Total movement", "Avg seek", "Seek ms", "Head path"], cmp_rows)
        + img("disk_head_movement.png", "Figure 1 - Total head movement (lowest bar highlighted).", "70%")
        + img("disk_head_paths.png", "Figure 2 - Head paths. Square = start, filled = served, hollow = turn/edge visit.")))

    parts.append(section(5, "Step-by-step visualiser", """
      <p>The terminal visualiser (<code>python3 main.py simulate --algo scan --visual</code>) draws the head position
      for every move; <code>#</code> is a served request, <code>o</code> a turn-around or edge visit.</p>
      <pre>%s</pre>""" % e(visual)))

    parts.append(section(6, "Random-queue experiment", """
      <p>For queue lengths of 5 to 80 requests, 200 random queues (and random head positions) are generated per
      point with a fixed seed, and the mean total head movement is recorded for each algorithm.</p>"""
        + tbl(exp_h, exp_b)
        + img("movement_vs_queue_length.png", "Figure 3 - Mean head movement versus queue length.", "78%")))

    parts.append(section(7, "Observations", "<ul>%s</ul>" % "".join("<li>%s</li>" % e(n) for n in notes) + """
      <p>Overall: SSTF and LOOK give the lowest movement, but SSTF risks starvation; the circular variants cost more
      movement in exchange for more uniform waiting; FCFS does not scale.</p>"""))

    parts.append(section(8, "Testing", """
      <p>%s unit tests were run (<code>./run.sh test</code>): result <b>%s</b>. They cover the textbook totals for
      all six algorithms, exact head paths, service order, both directions, empty queues, boundary cylinders,
      duplicates, a single-cylinder disk, LOOK never worse than SCAN, reproducible random experiments, input
      validation, malformed JSON, CLI errors (no tracebacks), the Bash generator (same seed gives the same file),
      menu re-prompting and end-of-input handling.</p>""" % (n_tests, "ALL PASSED" if ok else "FAILURES - see test_results.txt")))

    parts.append(section(9, "Conclusion", """
      <p>The simulator reproduces the known textbook results, makes the behaviour of each algorithm visible, and shows
      the trade-off between total movement, fairness and starvation. Possible extensions: request arrival times,
      starvation / maximum-wait metrics, and a graphical front end.</p>"""))

    css = """
    @page { size: A4; margin: 16mm 15mm; }
    body { font: 10.5pt/1.45 -apple-system, "Helvetica Neue", Arial, sans-serif; color: #1c1c1a; }
    header { border-bottom: 2px solid #4C78A8; margin-bottom: 14px; padding-bottom: 8px; }
    h1 { font-size: 24pt; margin: 0; } .sub { color: #555; margin: 2px 0; } .auth { font-weight: 600; margin: 4px 0 0; }
    h2 { font-size: 13.5pt; color: #2b5a8a; margin: 16px 0 6px; border-bottom: 1px solid #ddd; }
    section { break-inside: auto; } figure { margin: 8px 0; text-align: center; break-inside: avoid; }
    figcaption { font-size: 9pt; color: #555; } img { max-width: 100%; }
    table { border-collapse: collapse; width: 100%; font-size: 9.2pt; margin: 6px 0; break-inside: avoid; }
    th, td { border: 1px solid #ccc; padding: 3px 6px; text-align: left; } th { background: #eef3f8; }
    pre { background: #f5f5f2; border: 1px solid #ddd; padding: 6px; font-size: 7.6pt; line-height: 1.25; overflow: hidden; }
    code { background: #f0f0ec; padding: 0 3px; font-size: 9pt; } .note { color: #444; font-size: 9.5pt; }
    """
    doc = "<!doctype html><html><head><meta charset='utf-8'><title>Disk Scheduling Simulator - Report</title><style>%s</style></head><body>%s</body></html>" % (css, "".join(parts))
    html_path = os.path.join(BASE, "docs", "REPORT.html")
    pdf_path = os.path.join(BASE, "docs", "REPORT.pdf")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    if not os.path.exists(CHROME):
        sys.exit("Chrome not found at %s; open docs/REPORT.html and print to PDF." % CHROME)
    subprocess.run([CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    "--print-to-pdf=" + pdf_path, "file://" + html_path],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120, check=True)
    print("Wrote", pdf_path)


if __name__ == "__main__":
    main()
