"""LOCAL Day 23: declared architecture screening, not a cloud benchmark.

No Google/LINE client, secrets, deployment, live model calls, or remote writes.
--probe measures THIS stdlib module in fresh local Python child processes only.
Candidate fields describe proposed configurations; no deployment is certified.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
METRICS = (
    'image_mib', 'cold_start_p95_ms', 'container_peak_rss_mib',
    'model_request_p95_ms', 'network_rtt_p95_ms', 'webhook_ack_p95_ms',
)
REQUIREMENTS = {
    'community': {'model_perimeter': False, 'relational_joins': False},
    'governed': {'model_perimeter': True, 'relational_joins': False},
    'reporting': {'model_perimeter': False, 'relational_joins': True},
}


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def number(value: Any, name: str, *, positive: bool = False) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('INVALID_NUMBER:' + name)
    if value < 0 or (positive and value == 0):
        raise ValueError('INVALID_NUMBER:' + name)
    return float(value)


def latency_check(value: float | None, limit_ms: float = 2000) -> str:
    """Threshold arithmetic only. A PASS is not proof of measurement origin."""
    number(limit_ms, 'limit_ms', positive=True)
    if value is None:
        return 'NEEDS_MEASUREMENT'
    return 'PASS' if number(value, 'latency_ms') <= limit_ms else 'FAIL'


def read_options(path: Path = ROOT / 'stack_options.json') -> tuple[list[dict], str]:
    raw = path.read_bytes()
    document = json.loads(raw)
    if document.get('schema_version') != 'local-stack-matrix-v1':
        raise ValueError('UNSUPPORTED_SCHEMA')
    options = document.get('options')
    if not isinstance(options, list) or not options:
        raise ValueError('OPTIONS_REQUIRED')
    seen: set[str] = set()
    required = {'id', 'model_access', 'orchestrator', 'hosting', 'database',
                'min_instances', 'durable_state', 'atomic_changes',
                'model_perimeter', 'relational_joins'}
    for option in options:
        if not isinstance(option, dict) or set(option) != required:
            raise ValueError('OPTION_FIELDS_MISMATCH')
        key = option['id']
        if not isinstance(key, str) or not key or key in seen:
            raise ValueError('UNIQUE_OPTION_ID_REQUIRED')
        seen.add(key)
        for flag in ('durable_state', 'atomic_changes', 'model_perimeter', 'relational_joins'):
            if type(option[flag]) is not bool:
                raise ValueError('BOOLEAN_REQUIRED:' + flag)
        if type(option['min_instances']) is not int or option['min_instances'] < 0:
            raise ValueError('MIN_INSTANCES_REQUIRED')
        for label in ('model_access', 'orchestrator', 'hosting', 'database'):
            if not isinstance(option[label], str) or not option[label].strip():
                raise ValueError('LABEL_REQUIRED:' + label)
    return options, digest_bytes(raw)


def assess(option: dict, needs: dict, *, require_scale_zero: bool = False) -> dict:
    """Evaluate declared design suitability, not IAM, safety, or performance."""
    reasons = []
    if option['orchestrator'] != 'adk':
        reasons.append('RUNTIME_CHANGE_REQUIRES_REGRESSION')
    if not option['durable_state'] or not option['atomic_changes']:
        reasons.append('STATE_CONTRACT_UNSUPPORTED')
    for name in ('model_perimeter', 'relational_joins'):
        if needs[name] and not option[name]:
            reasons.append('REQUIREMENT_UNMET:' + name)
    # This is the proposed Cloud Run autoscaling configuration, not observed state.
    scale_zero = option['hosting'] == 'cloud_run' and option['min_instances'] == 0
    if require_scale_zero and not scale_zero:
        reasons.append('SCALE_ZERO_REQUIREMENT_UNMET')
    notes = []
    if not scale_zero:
        notes.append('WARM_INSTANCE_HAS_IDLE_COST')
    if option['database'] == 'cloud_sql':
        notes.append('DATABASE_IDLE_COST_REVIEW')
    if option['model_access'] == 'vertex_ai':
        notes.append('MODEL_REGION_IAM_AND_PERIMETER_REVIEW')
    measurements = dict.fromkeys(METRICS)
    return {
        'option_id': option['id'],
        'decision': 'EXCLUDED' if reasons else 'CANDIDATE',
        'reasons': reasons, 'tradeoffs': notes,
        'declared_design': copy.deepcopy(option),
        'measurements': measurements,
        'latency_status': latency_check(measurements['webhook_ack_p95_ms']),
        'deployment_status': 'NOT_VERIFIED',
        'measured_cost': None,
    }


def evaluate(profile: str = 'community', *, path: Path | None = None,
             require_scale_zero: bool = False) -> dict:
    if profile not in REQUIREMENTS:
        raise ValueError('UNKNOWN_PROFILE')
    if type(require_scale_zero) is not bool:
        raise ValueError('BOOLEAN_REQUIRED:require_scale_zero')
    options, options_hash = read_options(path or ROOT / 'stack_options.json')
    return {
        'schema_version': 'local-stack-matrix-report-v1',
        'origin': 'offline_design_evaluation',
        'scope': 'DECLARED_CONFIGURATION_ONLY',
        'profile': profile, 'requirements': REQUIREMENTS[profile].copy(),
        'require_scale_zero': require_scale_zero,
        'source_sha256': digest_bytes(Path(__file__).read_bytes()),
        'options_sha256': options_hash,
        'network_calls': 0,
        'rows': [assess(o, REQUIREMENTS[profile], require_scale_zero=require_scale_zero)
                 for o in options],
        'performance_winner': None,
    }


def measure_local(runs: int = 5) -> dict:
    if type(runs) is not int or not 1 <= runs <= 20:
        raise ValueError('RUN_COUNT_1_TO_20_REQUIRED')
    # Import this actual file in a fresh interpreter. Import never invokes main().
    child = '''import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("local_day23_probe", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
peak = None
if sys.platform in ("linux", "darwin"):
    import resource
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak = raw / (1024 * 1024 if sys.platform == "darwin" else 1024)
print(json.dumps({"process_peak_rss_mib": peak}))
'''
    samples = []
    for _ in range(runs):
        start = time.perf_counter_ns()
        done = subprocess.run([sys.executable, '-I', '-c', child, str(Path(__file__).resolve())],
                              check=True, capture_output=True, text=True, timeout=30)
        elapsed = (time.perf_counter_ns() - start) / 1_000_000
        payload = json.loads(done.stdout)
        peak = payload['process_peak_rss_mib']
        if peak is not None:
            number(peak, 'process_peak_rss_mib')
        samples.append({'fresh_process_wall_ms': round(elapsed, 3),
                        'process_peak_rss_mib': peak})
    return {
        'schema_version': 'local-stack-probe-v1',
        'origin': 'local_process_measurement',
        'measurement_scope': 'fresh_python_import_stack_matrix_including_spawn_and_exit',
        'measured_at_utc': datetime.now(timezone.utc).isoformat(),
        'system': platform.system(), 'python_version': platform.python_version(),
        'source_sha256': digest_bytes(Path(__file__).read_bytes()),
        'source_size_bytes': Path(__file__).stat().st_size,
        'samples': samples,
        'median_fresh_process_wall_ms': round(statistics.median(
            s['fresh_process_wall_ms'] for s in samples), 3),
        'cloud_run_cold_start_p95_ms': None,
        'model_latency_ms': None, 'network_calls': 0,
        'warning': 'Not a container startup, network, SDK inference, or four-stack benchmark.',
    }


def write_report(report: dict, out: Path, filename: str) -> None:
    out.mkdir(parents=True, exist_ok=False)
    with (out / filename).open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--eval', action='store_true')
    mode.add_argument('--probe', action='store_true')
    parser.add_argument('--profile', choices=tuple(REQUIREMENTS), default='community')
    parser.add_argument('--require-scale-zero', action='store_true')
    parser.add_argument('--options', type=Path)
    parser.add_argument('--runs', type=int, default=5)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    if args.probe and (args.options or args.require_scale_zero or args.profile != 'community'):
        parser.error('--probe does not evaluate profiles or cloud options')
    try:
        report = (measure_local(args.runs) if args.probe else
                  evaluate(args.profile, path=args.options, require_scale_zero=args.require_scale_zero))
        if args.out:
            write_report(report, args.out, 'probe.json' if args.probe else 'decisions.json')
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.exit(2, f'{type(exc).__name__}: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
