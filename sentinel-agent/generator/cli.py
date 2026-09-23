"""uv run python -m generator emit --all && uv run python -m generator load --all"""

import argparse
import sys

from generator.emit import emit, emit_all, list_scenarios
from generator.load import load_all, load_scenario


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit seeded Sentinel scenarios, then load Postgres.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    emit_p = sub.add_parser("emit", help="Write JSONL under data/generated/")
    emit_p.add_argument("--scenario", help="one id, e.g. checkout_db_pool")
    emit_p.add_argument("--all", action="store_true", help="every world/scenarios/*.yaml")
    load_p = sub.add_parser("load", help="Insert JSONL into Postgres events")
    load_p.add_argument("--scenario", help="one id, e.g. checkout_db_pool")
    load_p.add_argument("--all", action="store_true", help="every data/generated/*.jsonl")
    args = parser.parse_args(argv)

    if args.cmd == "emit":
        if args.all:
            paths = emit_all()
            for path in paths:
                print(path)
            return 0
        if not args.scenario:
            print("need --scenario ID or --all", file=sys.stderr)
            print("known:", ", ".join(list_scenarios()), file=sys.stderr)
            return 2
        print(emit(args.scenario))
        return 0

    if args.cmd == "load":
        if args.all or not args.scenario:
            n = load_all()
        else:
            n = load_scenario(args.scenario)
        print(f"ingested {n}")
        return 0
    return 2
