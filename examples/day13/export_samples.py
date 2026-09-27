"""Export synthetic Flex JSON for review/Simulator; not a LINE screenshot."""
import argparse
import json
from pathlib import Path
from .messages import render_result
from .sample_data import examples


def export(out: Path):
    out.mkdir(parents=True, exist_ok=False)
    counts = {}
    for name, result in examples().items():
        msg = render_result(result)
        (out / (name + '.json')).write_text(json.dumps(msg, ensure_ascii=False, indent=2), encoding='utf-8')
        (out / (name + '.text.json')).write_text(json.dumps(render_result(result, text_only=True), ensure_ascii=False, indent=2), encoding='utf-8')
        counts[name] = {'altText': msg['altText'], 'synthetic': True}
    (out / 'SOURCE.json').write_text(json.dumps({'origin': 'synthetic_fixture', 'results': counts}, ensure_ascii=False, indent=2), encoding='utf-8')
    return counts

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--out', type=Path, required=True)
    print(json.dumps(export(p.parse_args().out), ensure_ascii=False, indent=2))
