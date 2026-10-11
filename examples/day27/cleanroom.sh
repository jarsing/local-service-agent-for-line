#!/usr/bin/env bash
set -euo pipefail
REV=f8267a84fc7456783b2229e42b580d705164fd8d
ROOT="$HOME/local-demo-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir "$ROOT"
git clone https://github.com/jarsing/local-service-agent-for-line.git "$ROOT/repo"
cd "$ROOT/repo"
git checkout --detach "$REV"
test "$(git rev-parse HEAD)" = "$REV"
RUN=out/day27/cleanroom-01
mkdir -p out/day27
mkdir "$RUN"
printf '%s\n' "$REV" > "$RUN/launcher-commit.txt"
set +e
REV="$REV" bash examples/day26/cleanroom.sh "$RUN" \
  > "$RUN/run.log" 2>&1
RC=$?
set -e
printf '%s\n' "$RC" > "$RUN/exit-code.txt"
cat "$RUN/run.log"
if [ "$RC" -ne 0 ]; then
  printf 'STOP: inspect %s/run.log\n' "$RUN" >&2
  exit "$RC"
fi
printf 'Reports: %s/%s\n' "$PWD" "$RUN"
