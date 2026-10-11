"""Bounded, read-only aggregation of Git numstat history."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from fnmatch import fnmatchcase
import json
import subprocess
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True, slots=True)
class Hotspot:
    path: str
    touches: int
    additions: int
    deletions: int

    @property
    def churn(self) -> int:
        return self.additions + self.deletions


def _decode(value: bytes) -> str:
    return value.decode("utf-8", errors="surrogateescape")


def _safe_display(value: str) -> str:
    """Render invisible/control characters visibly in human-readable reports."""
    out: list[str] = []
    for char in value:
        code = ord(char)
        if char == "\\":
            out.append("\\\\")
        elif char == "\t":
            out.append("\\t")
        elif char == "\n":
            out.append("\\n")
        elif char == "\r":
            out.append("\\r")
        elif code < 32 or 0x7F <= code < 0xA0 or char in "\u2028\u2029":
            out.append(f"\\u{code:04x}")
        else:
            out.append(char)
    return "".join(out)


def parse_numstat_fields(fields: Iterable[bytes]) -> list[tuple[str, int, int]]:
    """Parse `git log --numstat -z --no-renames` NUL-separated records.

    Binary files (`-\t-`) have no line counts and are omitted. Filenames are
    separated from the two numeric fields by tabs, so tabs/newlines in names
    are preserved by Git's NUL-delimited output.
    """
    parsed: list[tuple[str, int, int]] = []
    for raw in fields:
        raw = raw.lstrip(b"\n")
        if not raw:
            continue
        first = raw.find(b"\t")
        second = raw.find(b"\t", first + 1) if first >= 0 else -1
        if first < 0 or second < 0:
            continue
        added_raw, deleted_raw = raw[:first], raw[first + 1:second]
        if added_raw == b"-" or deleted_raw == b"-":
            continue
        try:
            added, deleted = int(added_raw), int(deleted_raw)
        except ValueError:
            continue
        if added < 0 or deleted < 0:
            continue
        parsed.append((_decode(raw[second + 1:]), added, deleted))
    return parsed


def _run_git(args: list[str], *, cwd: Path, timeout: int = 60) -> bytes:
    try:
        completed = subprocess.run(
            ["git", *args], cwd=cwd, check=True, capture_output=True,
            timeout=timeout, shell=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Git executable was not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Git command exceeded the {timeout}s time limit") from exc
    except subprocess.CalledProcessError as exc:
        message = _decode(exc.stderr or b"").strip()
        raise RuntimeError(message or "Git command failed") from exc
    return completed.stdout


def collect_hotspots(
    repository: str | Path,
    *,
    limit: int = 20,
    max_commits: int = 5000,
    since: str | None = None,
    until: str | None = None,
    exclude: Iterable[str] = (),
) -> tuple[list[Hotspot], int]:
    """Read local non-merge commit numstat and return deterministic hotspots."""
    if not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200")
    if not 1 <= max_commits <= 50_000:
        raise ValueError("max_commits must be between 1 and 50000")
    repo = Path(repository).expanduser().resolve()
    if not repo.is_dir():
        raise ValueError(f"repository path is not a directory: {repo}")
    top = Path(_decode(_run_git(["rev-parse", "--show-toplevel"], cwd=repo)).strip())
    patterns = tuple(exclude)
    args = ["log", "--no-merges", "--no-renames", "--numstat", "-z",
            f"--max-count={max_commits}", "--format=%x1e%H%x00%cI%x00"]
    if since:
        args.append(f"--since={since}")
    if until:
        args.append(f"--until={until}")
    args.append("--")
    raw = _run_git(args, cwd=top)
    stats: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    commits_seen = 0
    for record in raw.split(b"\x1e"):
        if not record:
            continue
        header, separator, body = record.partition(b"\x00")
        if not separator:
            continue
        _commit_hash, _commit_date, remainder = (header + b"\x00" + body).split(b"\x00", 2)
        commits_seen += 1
        for path_bytes, additions, deletions in parse_numstat_fields(remainder.split(b"\x00")):
            path = path_bytes.replace("\\", "/")
            if any(fnmatchcase(path, pattern) for pattern in patterns):
                continue
            counts = stats[path]
            counts[0] += 1
            counts[1] += additions
            counts[2] += deletions
    results = [Hotspot(path, touches, additions, deletions)
               for path, (touches, additions, deletions) in stats.items()]
    results.sort(key=lambda item: (-item.churn, -item.touches, item.path.casefold(), item.path))
    return results[:limit], commits_seen


def to_json(hotspots: list[Hotspot], commits_scanned: int) -> str:
    return json.dumps({
        "commits_scanned": commits_scanned,
        "metric": "line churn = additions + deletions; binary files excluded",
        "hotspots": [{**asdict(item), "churn": item.churn} for item in hotspots],
    }, ensure_ascii=True, indent=2) + "\n"


def to_markdown(hotspots: list[Hotspot], commits_scanned: int) -> str:
    lines = ["# Git Churn Map", "", f"Commits scanned: **{commits_scanned}**",
             "", "Churn is added + deleted lines; binary files are excluded. This is a review aid, not a quality score.",
             "", "| File | Commits touched | Added | Deleted | Churn |", "|:--|--:|--:|--:|--:|"]
    for item in hotspots:
        path = _safe_display(item.path)
        path = path.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        path = path.replace("|", "&#124;").replace("`", "&#96;")
        lines.append(f"| {path} | {item.touches} | {item.additions} | {item.deletions} | {item.churn} |")
    if not hotspots:
        lines.append("| *(no text-file changes in the selected history)* | 0 | 0 | 0 | 0 |")
    lines.extend(["", "Only paths and aggregate line counts are included; source contents are never read into the report.", ""])
    return "\n".join(lines)
