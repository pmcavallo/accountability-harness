"""Command line: accountability-harness report LOG | verify LOG | compare A B.

Also runs as python -m accountability_harness. verify exits 0 if the hash
chain is intact, 1 if it is broken and 2 if the log is not chained.
"""

from __future__ import annotations

import argparse

from .audit import verify
from .compare import compare
from .report import chain_status, render_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="accountability-harness", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("report", help="print the report for one audit log").add_argument("log")
    commands.add_parser("verify", help="check one audit log's hash chain").add_argument("log")
    pair = commands.add_parser("compare", help="compare two folders of audit logs")
    pair.add_argument("a")
    pair.add_argument("b")
    args = parser.parse_args(argv)
    if args.command == "report":
        print(render_report(args.log))
    elif args.command == "verify":
        print(chain_status(args.log))
        return {"intact": 0, "broken": 1, "not chained": 2}[verify(args.log)[0]]
    else:
        print(compare(args.a, args.b))
    return 0
