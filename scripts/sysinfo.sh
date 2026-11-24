#!/usr/bin/env bash
# sysinfo.sh - live system snapshot, portable across macOS and Linux.
OS="$(uname -s)"
echo "=== System snapshot ($(date '+%Y-%m-%d %H:%M:%S')) ==="
echo "OS            : $OS $(uname -r) ($(uname -m))"

case "$OS" in
  Darwin)
    CORES="$(sysctl -n hw.ncpu 2>/dev/null)"
    MEMB="$(sysctl -n hw.memsize 2>/dev/null)"
    MEM="$(( ${MEMB:-0} / 1024 / 1024 )) MB"
    ;;
  Linux)
    CORES="$(nproc 2>/dev/null || grep -c '^processor' /proc/cpuinfo)"
    MEMK="$(awk '/^MemTotal/ {print $2}' /proc/meminfo 2>/dev/null)"
    MEM="$(( ${MEMK:-0} / 1024 )) MB"
    ;;
  *)
    CORES="unknown"; MEM="unknown" ;;
esac
echo "CPU cores     : ${CORES:-unknown}"
echo "Total memory  : ${MEM:-unknown}"
echo "Disk (/)      : $(df -h / 2>/dev/null | awk 'NR==2 {print $2" total, "$3" used, "$4" free ("$5" used)"}')"
NPROC="$(ps -A 2>/dev/null | wc -l | tr -d ' ')"
echo "Process count : $(( NPROC - 1 ))"
echo "Top 5 processes by CPU%:"
printf "  %-8s %6s %6s  %s\n" PID "%CPU" "%MEM" COMMAND
ps -A -o pid=,pcpu=,pmem=,comm= 2>/dev/null | sort -k2,2 -nr | head -5 | \
  awk '{ cmd=$4; for (i=5;i<=NF;i++) cmd=cmd" "$i; n=split(cmd, parts, "/"); printf "  %-8s %6s %6s  %s\n", $1, $2, $3, parts[n] }'
