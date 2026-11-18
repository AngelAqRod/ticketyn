"""python -m ticketyn.incoming [--once | --recover]."""
import argparse
import json
import logging
import time

from sqlalchemy.orm import Session

from ticketyn.db.session import get_engine
from ticketyn.incoming.config import IncomingSettings
from ticketyn.incoming.receiver import poll
from ticketyn.incoming.storage import recover_storage


def main():
    parser = argparse.ArgumentParser(description='Receive installation requests without creating orders')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--once', action='store_true', help='Poll once and exit')
    mode.add_argument('--recover', action='store_true', help='Report missing originals and clean orphans older than 24 hours')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    settings = IncomingSettings.from_env()
    if not args.recover and not settings.enabled:
        print(json.dumps({'enabled': False, 'message': 'IMAP not configured; manual orders remain available'}))
        return 0
    while True:
        with Session(get_engine()) as session:
            result = recover_storage(session) if args.recover else poll(session)
        print(json.dumps(result), flush=True)
        if args.once or args.recover:
            return 1 if result.get('errors') or result.get('missing_document_ids') else 0
        time.sleep(settings.interval)


if __name__ == '__main__':
    raise SystemExit(main())
