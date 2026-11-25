#!/usr/bin/env bash
# Disk Scheduling Simulator launcher.  Usage: ./run.sh {menu|demo|test|gen N [seed]|sysinfo|logsummary|clean}
# Works with macOS bash 3.2 and Linux bash.
cd "$(dirname "$0")" || exit 1
ROOT="$(pwd)"
mkdir -p outputs logs

if [ -x /usr/bin/python3 ] && /usr/bin/python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,7) else 1)' 2>/dev/null; then
  PY=/usr/bin/python3
elif command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  echo "Error: python3 not found. Install Python 3.7+ (macOS: xcode-select --install)." >&2
  exit 1
fi

usage() {
  cat <<USAGE
Disk Scheduling Simulator
Usage: ./run.sh <command>
  menu                      interactive menu (default)
  demo                      run everything non-interactively (saves outputs/demo_trace.txt)
  test                      run the unit tests (saves outputs/test_results.txt)
  analyze                   tables, CSVs, charts and analysis report -> outputs/
  gen N [seed]              generate N random disk requests (Bash) -> outputs/generated_requests.json
  sysinfo                   live system snapshot
  logsummary                summarise logs/osrm.log by level and module
  clean                     remove generated outputs, logs and caches
USAGE
}

cmd="${1:-menu}"
[ $# -gt 0 ] && shift
case "$cmd" in
  menu)  exec "$PY" main.py menu ;;
  demo)  exec "$PY" main.py demo ;;
  test)
    # tests log to a separate file so logs/osrm.log only holds application runs
    OSRM_LOG_FILE="$ROOT/logs/test.log" "$PY" tests/test_disk.py -v 2>&1 | tee outputs/test_results.txt
    exit "${PIPESTATUS[0]}" ;;
  analyze) exec "$PY" main.py analyze "$@" ;;
  gen)
    if [ $# -lt 1 ]; then echo "Usage: ./run.sh gen N [seed]" >&2; exit 2; fi
    "$PY" main.py gen "$1" ${2:+--seed "$2"} --out outputs/generated_requests.json || exit $?
    echo "Run it with:  $PY main.py simulate --file outputs/generated_requests.json" ;;
  sysinfo)    exec bash scripts/sysinfo.sh ;;
  logsummary) exec bash scripts/log_summary.sh "$ROOT/logs/osrm.log" ;;
  clean)
    find outputs -type f ! -name '.gitkeep' -delete 2>/dev/null
    rm -f logs/*.log
    find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null
    echo "Cleaned outputs/, logs/ and caches." ;;
  -h|--help|help) usage ;;
  *) echo "Unknown command: $cmd" >&2; usage >&2; exit 2 ;;
esac
