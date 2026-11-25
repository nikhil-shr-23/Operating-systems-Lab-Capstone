#!/usr/bin/env bash
# gen_requests.sh N [seed] [outfile] [disk_size]
# Generates a random disk-scheduling workload as JSON (same format as data/disk.json):
#   {"requests":[...],"head":H,"disk_size":S,"direction":"up"}
# Works on macOS (bash 3.2) and Linux.  With a seed the output is reproducible.
# Writes to outfile if given, otherwise to stdout.
usage() { echo "Usage: $0 N [seed] [outfile] [disk_size]   (N = integer 1..1000, disk_size 2..100000)" >&2; }

if [ $# -lt 1 ]; then usage; exit 2; fi
N="$1"; SEED="$2"; OUT="$3"; SIZE="${4:-200}"

case "$N" in ''|*[!0-9]*) echo "Error: N must be a positive integer, got '$N'" >&2; usage; exit 2;; esac
if [ "$N" -lt 1 ] || [ "$N" -gt 1000 ]; then
  echo "Error: N must be between 1 and 1000, got $N" >&2; exit 2
fi
case "$SIZE" in ''|*[!0-9]*) echo "Error: disk_size must be a positive integer, got '$SIZE'" >&2; usage; exit 2;; esac
N=$(( 10#$N )); SIZE=$(( 10#$SIZE ))
if [ "$SIZE" -lt 2 ] || [ "$SIZE" -gt 100000 ]; then
  echo "Error: disk_size must be between 2 and 100000, got $SIZE" >&2; exit 2
fi
if [ -n "$SEED" ]; then
  case "$SEED" in ''|*[!0-9]*) echo "Error: seed must be a non-negative integer, got '$SEED'" >&2; usage; exit 2;; esac
  RANDOM=$(( 10#$SEED ))          # seeds bash's generator -> reproducible output
fi

# bash RANDOM is 0..32767; combine two draws so large disks are covered too
# (sets R instead of using $(...) so the seeded RANDOM state is not lost in a subshell)
rnd() { R=$(( (RANDOM * 32768 + RANDOM) % SIZE )); }

generate() {
  list=""
  i=1
  while [ "$i" -le "$N" ]; do
    rnd; list="$list$R"
    [ "$i" -lt "$N" ] && list="$list, "
    i=$(( i + 1 ))
  done
  echo "{"
  echo "  \"requests\": [$list],"
  rnd; echo "  \"head\": $R,"
  echo "  \"disk_size\": $SIZE,"
  echo "  \"direction\": \"up\""
  echo "}"
}

if [ -n "$OUT" ]; then
  mkdir -p "$(dirname "$OUT")" && generate > "$OUT" || { echo "Error: cannot write $OUT" >&2; exit 1; }
  echo "Wrote $N random requests to $OUT"
else
  generate
fi
