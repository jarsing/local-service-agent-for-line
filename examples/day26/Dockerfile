# syntax=docker/dockerfile:1
ARG BASE=python:3.13-slim
FROM ${BASE}

RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /work/repo

# Copy repository into container
COPY . /work/repo

ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
RUN python -m pip install -r examples/day25/requirements-core.txt && python -m pip check

# Default command: run all 155 unit tests
CMD ["python", "-m", "unittest", "examples.day25.test_ingestion", "examples.day24.test_evidence", "examples.day19.test_inbox_contract", "examples.day22.test_security", "-v"]
