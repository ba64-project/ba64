#!/usr/bin/env bash
# Run every language's conformance suite against the one shared corpus.
# Phase 4 capstone: all six implementations must agree, byte-for-byte, on the
# committed vectors (including the 4000-case differential vs the Python reference)
# and on every taxonomy error code (modulo the documented decoder-dependent
# case, see CAVEATS.md).
#
# Toolchains are optional: a language with a missing toolchain is SKIPPED with a
# notice, never a silent pass. Exit non-zero if any present language fails.
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)
export PATH="/opt/homebrew/opt/openjdk/bin:/opt/homebrew/opt/dotnet/bin:$PATH"
export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1

fail=0
run() {  # name, availability-check-cmd, run-cmd
  local name=$1 check=$2 cmd=$3
  if ! eval "$check" >/dev/null 2>&1; then
    printf '  %-11s SKIPPED (toolchain missing)\n' "$name"
    return
  fi
  if eval "$cmd" >/tmp/ba64_$name.log 2>&1; then
    printf '  %-11s OK\n' "$name"
  else
    printf '  %-11s FAILED (see /tmp/ba64_%s.log)\n' "$name" "$name"
    tail -5 "/tmp/ba64_$name.log" | sed 's/^/      /'
    fail=1
  fi
}

echo "ba64 cross-language conformance (shared corpus in vectors/)"
run python "python3 --version"      "python3 conformance/run_reference.py"
run typescript "node --version"     "cd $ROOT/js && node conformance.ts"
run go "go version"                 "cd $ROOT/go && go test ./..."
run rust "cargo --version"          "cd $ROOT/rust && cargo test -q"
run java "javac -version"           "cd $ROOT/java && javac Ba64.java Ba64Test.java && java Ba64Test"
run csharp "dotnet --version"       "cd $ROOT/csharp && dotnet run -c Release"

if [ "$fail" -eq 0 ]; then
  echo "ALL PRESENT IMPLEMENTATIONS AGREE."
else
  echo "DIVERGENCE DETECTED."
fi
exit $fail
