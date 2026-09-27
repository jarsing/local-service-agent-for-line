"""Add Day 13 to the existing allowlisted build context, without modifying Day 12."""
import argparse
import hashlib
import json
from pathlib import Path
from examples.day12.build_context import export as export_day12

HERE = Path(__file__).resolve().parent
RUNTIME = ('__init__.py', 'messages.py', 'bridge.py', 'main.py')

def export(out: Path):
    # Check new sources before any output is created.
    for name in RUNTIME + ('Dockerfile',):
        if not (HERE / name).is_file() or (HERE / name).is_symlink():
            raise ValueError('缺少 Day 13 來源或包含符號連結。')
    report = export_day12(out)
    for name in RUNTIME:
        target = out / 'examples/day13' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((HERE / name).read_bytes())
        report['files']['examples/day13/' + name] = hashlib.sha256(target.read_bytes()).hexdigest()
    (out / 'Dockerfile').write_bytes((HERE / 'Dockerfile').read_bytes())
    report['day13_entrypoint'] = 'examples.day13.main:app'
    report['files']['Dockerfile'] = hashlib.sha256((out / 'Dockerfile').read_bytes()).hexdigest()
    report['files']['.dockerignore'] = hashlib.sha256((out / '.dockerignore').read_bytes()).hexdigest()
    (out / 'SOURCE_MANIFEST.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--out', type=Path, required=True)
    print(json.dumps(export(p.parse_args().out), ensure_ascii=False, indent=2))
