import argparse
import sys

from .publish import update
from .source import SourceError


def main():
    parser = argparse.ArgumentParser(description="Bygg daglig oppdaterte UKM-kalendere")
    parser.add_argument("--output", default="generated", help="Egen mappe for generert nettsted og datagrunnlag")
    parser.add_argument("--base-url", default="", help="Offentlig HTTPS-adresse til nettstedet")
    parser.add_argument("--workers", type=int, default=4, choices=range(1, 9))
    parser.add_argument("--allow-empty", action="store_true", help="Tillat en bekreftet, komplett tom kilde etter manuell kontroll")
    args = parser.parse_args()
    try:
        status = update(args.output, args.base_url, workers=args.workers, allow_empty=args.allow_empty)
    except (SourceError, ValueError, KeyError, OSError) as error:
        print(f"Oppdateringen feilet. Forrige vellykkede versjon er beholdt.\n{error}", file=sys.stderr)
        return 1
    print(f"Ferdig: {status['event_count']} arrangementer og {status['deadline_count']} påmeldingsfrister bak scenen "
          f"i {status['calendar_count']} kalendere. Utmappe: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
