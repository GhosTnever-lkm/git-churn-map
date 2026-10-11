"""Command-line interface for Git Churn Map."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from . import __version__
from .core import collect_hotspots, to_json, to_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="git-churn-map",
        description="Map frequently changed files in local Git history (read-only).",
    )
    parser.add_argument("repository", nargs="?", default=".", help="repository path (default: current directory)")
    parser.add_argument("--limit", type=int, default=20, help="number of hotspots, 1–200 (default: 20)")
    parser.add_argument("--max-commits", type=int, default=5000, help="maximum non-merge commits to scan (default: 5000; max: 50000)")
    parser.add_argument("--since", help="Git date/revision expression to start the history window")
    parser.add_argument("--until", help="Git date/revision expression to end the history window")
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB", help="exclude matching repo-relative paths; repeatable")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown", help="report format")
    parser.add_argument("--output", type=Path, help="write report to this path (default: stdout)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        hotspots, commits = collect_hotspots(
            args.repository, limit=args.limit, max_commits=args.max_commits,
            since=args.since, until=args.until, exclude=args.exclude,
        )
        report = to_json(hotspots, commits) if args.format == "json" else to_markdown(hotspots, commits)
        if args.output:
            args.output.expanduser().write_text(report, encoding="utf-8")
        else:
            sys.stdout.write(report)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"git-churn-map: error: {exc}", file=sys.stderr)
        return 2
    return 0
