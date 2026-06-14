from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Iterable

from agentshelf.engine import parse_input, render_json, render_markdown, scan_readiness


SUPPORTED_SUFFIXES = {".html", ".htm", ".txt"}
BAND_ORDER = {"not_ready": 0, "weak": 1, "workable": 2, "strong": 3}


def _resolve_inputs(target: str, batch: bool) -> list[Path]:
    path = Path(target)
    if path.is_dir():
        paths = [
            item
            for item in path.rglob("*")
            if item.is_file() and item.suffix.lower() in SUPPORTED_SUFFIXES
        ]
    elif any(char in target for char in "*?[]"):
        paths = [
            Path(item)
            for item in glob.glob(target, recursive=True)
            if Path(item).is_file() and Path(item).suffix.lower() in SUPPORTED_SUFFIXES
        ]
    else:
        paths = [path]

    resolved = sorted(dict.fromkeys(item.resolve() for item in paths))
    if not resolved:
        raise FileNotFoundError(f"No scan inputs found for {target!r}.")
    if len(resolved) > 1 and not batch:
        raise ValueError("Multiple inputs found. Re-run with --batch.")
    return resolved


def _load_scan(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    parsed = parse_input(raw, fallback_title=path.stem.replace("_", " ").title(), source=str(path))
    return scan_readiness(parsed)


def _render_batch_markdown(results: Iterable[dict]) -> str:
    rows = list(results)
    lines = [
        "# AgentShelf Batch Report",
        "",
        "| Score | Band | Source | Top fixes |",
        "| ---: | --- | --- | --- |",
    ]
    for item in rows:
        fixes = "; ".join(fix["recommendation"] for fix in item["top_fixes"][:3]) or "None"
        lines.append(f"| {item['score']} | {item['band']} | `{item['page']['source']}` | {fixes} |")
    return "\n".join(lines) + "\n"


def _render_results(results: list[dict], output_format: str, batch: bool) -> str:
    if output_format == "json":
        payload = results if batch else results[0]
        return json.dumps(payload, indent=2) + "\n"
    if output_format == "jsonl":
        return "".join(json.dumps(item) + "\n" for item in results)
    if batch:
        return _render_batch_markdown(results)
    return render_markdown(results[0])


def _fails_threshold(result: dict, min_score: int | None, fail_on: str | None) -> bool:
    if min_score is not None and result["score"] < min_score:
        return True
    if fail_on is not None and BAND_ORDER[result["band"]] <= BAND_ORDER[fail_on]:
        return True
    return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentshelf",
        description="Audit product pages for AI shopping-agent readiness.",
    )
    subcommands = parser.add_subparsers(dest="command")
    scan = subcommands.add_parser("scan", help="Scan one product page or a batch of page snapshots.")
    scan.add_argument("path", help="HTML/text file, directory, or glob to scan.")
    scan.add_argument("--batch", action="store_true", help="Allow directory or glob batch scanning.")
    scan.add_argument(
        "--format",
        choices=("markdown", "json", "jsonl"),
        default="markdown",
        help="Output format. Use jsonl for batch-friendly machine output.",
    )
    scan.add_argument("--output", type=Path, help="Optional output file path.")
    scan.add_argument("--min-score", type=int, help="Return non-zero when any page scores below this value.")
    scan.add_argument(
        "--fail-on",
        choices=("weak", "not_ready"),
        help="Return non-zero when any page is at or below this readiness band.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return 2

    try:
        paths = _resolve_inputs(args.path, args.batch)
        batch = args.batch or len(paths) > 1
        results = [_load_scan(path) for path in paths]
        rendered = _render_results(results, args.format, batch)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")

    return 1 if any(_fails_threshold(item, args.min_score, args.fail_on) for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())

