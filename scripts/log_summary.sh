#!/usr/bin/env bash
# log_summary.sh [logfile] - summarise an OSRM log by level and by module.
# Log format: time | LEVEL | module | message
LOG="${1:-$(cd "$(dirname "$0")/.." && pwd)/logs/osrm.log}"
if [ ! -f "$LOG" ]; then echo "Error: log file not found: $LOG" >&2; exit 1; fi
if [ ! -s "$LOG" ]; then echo "Error: log file is empty: $LOG" >&2; exit 1; fi

echo "=== Log summary: $LOG ==="
echo "Total records : $(grep -c ' | ' "$LOG")"
echo
echo "By level:"
awk -F'|' 'NF>=4 { gsub(/ /,"",$2); c[$2]++ } END { for (l in c) printf "  %-10s %d\n", l, c[l] }' "$LOG" | sort
echo
echo "By module:"
awk -F'|' 'NF>=4 { gsub(/ /,"",$3); c[$3]++ } END { for (m in c) printf "  %-12s %d\n", m, c[m] }' "$LOG" | sort
echo
echo "Level x module:"
awk -F'|' 'NF>=4 { gsub(/ /,"",$2); gsub(/ /,"",$3); c[$3" "$2]++ } END { for (k in c) printf "  %-22s %d\n", k, c[k] }' "$LOG" | sort
echo
echo "Last 5 WARNING/ERROR records:"
grep -E '\| (WARNING|ERROR|CRITICAL) +\|' "$LOG" | tail -5 | sed 's/^/  /'
exit 0
