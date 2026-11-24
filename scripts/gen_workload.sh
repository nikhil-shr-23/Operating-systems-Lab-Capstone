#!/usr/bin/env bash
# gen_workload.sh N [seed] [outfile]
# Generates a random workload CSV (pid,arrival,burst,priority) with N processes.
# Works on macOS (bash 3.2) and Linux.  With a seed the output is reproducible.
# Writes to outfile if given, otherwise to stdout.
usage() { echo "Usage: $0 N [seed] [outfile]   (N = integer 1..1000)" >&2; }

if [ $# -lt 1 ]; then usage; exit 2; fi
N="$1"; SEED="$2"; OUT="$3"

case "$N" in ''|*[!0-9]*) echo "Error: N must be a positive integer, got '$N'" >&2; usage; exit 2;; esac
if [ "$N" -lt 1 ] || [ "$N" -gt 1000 ]; then
  echo "Error: N must be between 1 and 1000, got $N" >&2; exit 2
fi
N=$(( 10#$N ))        # normalise (e.g. 007 -> 7), avoids octal surprises
if [ -n "$SEED" ]; then
  case "$SEED" in ''|*[!0-9]*) echo "Error: seed must be a non-negative integer, got '$SEED'" >&2; exit 2;; esac
  RANDOM=$(( 10#$SEED ))          # seeds bash's generator -> reproducible output
fi

generate() {
  echo "pid,arrival,burst,priority"
  i=1
  while [ "$i" -le "$N" ]; do
    arrival=$(( RANDOM % (N * 2 + 1) ))
    burst=$(( RANDOM % 20 + 1 ))
    prio=$(( RANDOM % 5 + 1 ))
    echo "P$i,$arrival,$burst,$prio"
    i=$(( i + 1 ))
  done
}

if [ -n "$OUT" ]; then
  mkdir -p "$(dirname "$OUT")" 2>/dev/null
  generate > "$OUT" || { echo "Error: cannot write $OUT" >&2; exit 1; }
  echo "Generated $N processes -> $OUT"
else
  generate
fi
