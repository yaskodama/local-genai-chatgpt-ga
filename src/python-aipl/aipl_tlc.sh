#!/usr/bin/env bash
# Run TLC on a generated TLA+ module.  Auto-locates Java (via Homebrew
# openjdk) and tla2tools.jar (via $TLA_JAR or ~/.local/lib/tla/tla2tools.jar).
#
# Usage:
#   bash aipl_tlc.sh out_tla/PhilosophersNaive
#   bash aipl_tlc.sh out_tla/Philosophers5Ordered
#
# The argument is the .tla / .cfg basename (without extension).
set -u

if [ $# -ne 1 ]; then
  echo "usage: $0 <basename>"
  echo "  basename is path-without-extension (.tla and .cfg are expected)"
  exit 2
fi

BASE="$1"
[ -f "${BASE}.tla" ] || { echo "missing ${BASE}.tla"; exit 1; }
[ -f "${BASE}.cfg" ] || { echo "missing ${BASE}.cfg"; exit 1; }

# Locate Java.
JAVA="${JAVA:-/opt/homebrew/opt/openjdk/bin/java}"
if [ ! -x "$JAVA" ]; then
  JAVA="$(command -v java || true)"
fi
[ -x "$JAVA" ] || { echo "Java not found.  Install via 'brew install openjdk'."; exit 1; }

# Locate tla2tools.jar.
TLA_JAR="${TLA_JAR:-$HOME/.local/lib/tla/tla2tools.jar}"
if [ ! -f "$TLA_JAR" ]; then
  echo "tla2tools.jar not found at $TLA_JAR.  Download from"
  echo "  https://github.com/tlaplus/tlaplus/releases/latest"
  echo "and set TLA_JAR=path/to/tla2tools.jar"
  exit 1
fi

cd "$(dirname "$BASE")"
NAME=$(basename "$BASE")
"$JAVA" -XX:+UseParallelGC -cp "$TLA_JAR" tlc2.TLC \
  -config "${NAME}.cfg" "${NAME}.tla"
