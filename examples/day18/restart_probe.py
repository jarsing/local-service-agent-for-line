"""Read the original persisted task in a separate process; do not reseed it."""
import argparse
import os
from pathlib import Path
from .local_adapter import FixtureClock, dump


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    if not args.database.is_file() or args.out.exists():
        raise ValueError('EXISTING_DB_AND_FRESH_OUTPUT_REQUIRED')
    from examples.day12.testing import settings, RAW_USER
    from examples.day12.identity import make_actor
    from examples.day12.inherit import SQLiteTestStore
    from examples.day12.tasks import LineTasks
    from examples.day12.catalog_view import CatalogView
    from examples.day13.messages import render_result
    config = settings(args.database)
    store = SQLiteTestStore(args.database)
    try:
        task = LineTasks(store, CatalogView(), clock=FixtureClock())
        actor = make_actor(config, RAW_USER)
        if args.prepare:
            offer = task.offer(actor, '需要手語志工支援', 'synthetic-restart-create', new_intent=True)
            result = task.decide(actor, offer['args']['confirmation_id'], True)
        else:
            result = task.status(actor)
        dump(args.out, {'pid':os.getpid(), 'plan':{'result':result, 'messages':[render_result(result)]}})
    finally:
        close = getattr(store, 'close', None)
        if close:
            close()


if __name__ == '__main__':
    main()
