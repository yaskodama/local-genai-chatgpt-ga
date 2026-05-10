#!/usr/bin/env bash
# Run SPIN on a generated Promela (.pml) file.  Generates pan.c,
# compiles it, and runs the verifier with weak fairness against
# the LTL property declared inside the .pml.
#
# Usage:
#   bash aipl_spin.sh out_promela/PhilosophersNaive.pml
#   bash aipl_spin.sh out_promela/Philosophers5Ordered          # extension auto-added
#   bash aipl_spin.sh out_promela/PhilosophersNaive.pml progress
#
# The second argument is the LTL property name (default: progress),
# matching the `ltl <name> { ... }` clause emitted by aipl_to_promela.
set -u

if [ $# -lt 1 ]; then
  echo "usage: $0 <file.pml-or-basename> [<ltl-property>]"
  exit 2
fi

PML="$1"
PROP="${2:-progress}"

if [ ! -f "$PML" ]; then
  if [ -f "${PML}.pml" ]; then
    PML="${PML}.pml"
  else
    echo "error: no .pml file at $PML or ${PML}.pml"
    exit 1
  fi
fi

SPIN="${SPIN:-$(command -v spin || true)}"
CC="${CC:-cc}"

if [ -z "$SPIN" ]; then
  echo "spin not found.  Install via 'brew install spin'."
  exit 1
fi

# Run in the .pml directory: pan.c, pan, *.trail all land there.
cd "$(dirname "$PML")"
NAME=$(basename "$PML" .pml)

echo "=== generating pan.c from ${NAME}.pml ==="
"$SPIN" -a "${NAME}.pml"

echo "=== compiling pan ==="
# -O0: pan generated for these models trips an optimizer issue with
#      -O2 (segfault on large state vectors) — keep optimizations off.
# -DVECTORSZ=2048: our state vector exceeds the default 1024 bytes
#      because each fork carries an 8-slot queue array.
"$CC" -O0 -DVECTORSZ=2048 -o pan pan.c

echo "=== verifying LTL '${PROP}' ==="
# We don't pass -f (weak fairness): pan with -f and our model size
# segfaults inside its acceptance-cycle search.  For our philosopher
# model SPIN's default scheduling already catches the deadlock as a
# stuttering counter-example to <> all_phils_done.
./pan -a
RC=$?

# Print counter-example if a trail was produced.
TRAIL=""
for cand in "${NAME}.pml.trail" "${NAME}.trail" "pan.trail"; do
  if [ -f "$cand" ]; then TRAIL="$cand"; break; fi
done

if [ -n "$TRAIL" ]; then
  echo
  echo "=== counter-example trail: $TRAIL ==="
  "$SPIN" -t -p -g -l "${NAME}.pml" 2>&1 | head -200
fi

exit "$RC"
