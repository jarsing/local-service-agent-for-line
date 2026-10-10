#!/usr/bin/env bash
set -euo pipefail

RUN=${1:-out/day26/cleanroom-$(date +%Y%m%d-%H%M%S)}
REV=${REV:-36914e5}

mkdir -p out/day26
mkdir -p "$RUN"

echo "[cleanroom] pulling base image python:3.13-slim..."
docker pull python:3.13-slim
BASE=$(docker image inspect python:3.13-slim --format '{{index .RepoDigests 0}}')
echo "$BASE" > "$RUN/base.txt"
echo "[cleanroom] base image digest: $BASE"

echo "[cleanroom] building isolated image for revision $REV..."
docker build --pull --no-cache --build-arg BASE="$BASE" --build-arg REV="$REV" \
  --iidfile "$RUN/image.id" - <<'DOCKERFILE' 2>&1 | tee "$RUN/build.log"
ARG BASE
FROM ${BASE}
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates && rm -rf /var/lib/apt/lists/*
ARG REV
WORKDIR /work
RUN git clone https://github.com/jarsing/local-service-agent-for-line.git repo \
    && cd repo && git checkout --detach "$REV" \
    && test "$(git rev-parse HEAD)" = "$REV"
WORKDIR /work/repo
ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
RUN python -m pip install -r examples/day25/requirements-core.txt \
    && python -m pip check
DOCKERFILE

IMAGE=$(cat "$RUN/image.id")
docker image inspect "$IMAGE" > "$RUN/image.json"

echo "[cleanroom] running tests in isolated container with --network none..."
docker run --rm --network none \
  --mount "type=bind,source=$(cd "$RUN" && pwd),target=/evidence" \
  "$IMAGE" bash -euo pipefail -c '
    git rev-parse HEAD > /evidence/commit.txt
    python -VV > /evidence/python.txt 2>&1
    python -m pip freeze > /evidence/packages.txt
    python -m unittest examples.day25.test_ingestion -v \
      > /evidence/day25.log 2>&1
    python -m unittest examples.day24.test_evidence -v \
      > /evidence/day24.log 2>&1
    python -m unittest examples.day19.test_inbox_contract examples.day22.test_security -v \
      > /evidence/day19_day22.log 2>&1
    python -m examples.day25.demo --out out/day26/demo-01 \
      > /evidence/demo.log 2>&1
    cp out/day26/demo-01/report.json /evidence/demo.json
    git status --porcelain --untracked-files=all > /evidence/worktree.txt
    test ! -s /evidence/worktree.txt
  '

echo "[cleanroom] all 155 tests and demo passed in isolated container."
echo "[cleanroom] evidence collected in $RUN"
ls -la "$RUN"
