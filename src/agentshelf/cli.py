from __future__ import annotations

import argparse
import glob
import hashlib
import json
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from agentshelf.engine import build_agent_contract, parse_input, render_markdown, scan_readiness


SUPPORTED_SUFFIXES = {".html", ".htm", ".txt"}
BAND_ORDER = {"not_ready": 0, "weak": 1, "workable": 2, "strong": 3}
DEFAULT_CONFIG = ".agentshelf.json"
USER_AGENT = "AgentShelf/0.5 (+https://github.com/wureny/AgentShelf)"
RENDER_EXTRA_MESSAGE = (
    "Rendered snapshots require the optional Playwright extra. "
    "Install it with `python3 -m pip install 'agentshelf[render]'` and then run "
    "`python3 -m playwright install chromium`."
)


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


def _load_config(config_path: Path | None) -> dict:
    path = config_path or Path(DEFAULT_CONFIG)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid AgentShelf config {path}: {exc.msg}.") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Invalid AgentShelf config {path}: expected a JSON object.")
    return data


def _config_value(config: dict, key: str, current: object, default: object) -> object:
    if current != default:
        return current
    return config.get(key, current)


def _coerce_score(value: object) -> int | None:
    if value is None:
        return None
    try:
        score = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Score thresholds must be integers between 0 and 100.") from exc
    if not 0 <= score <= 100:
        raise ValueError("Score thresholds must be integers between 0 and 100.")
    return score


def _load_scan(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    parsed = parse_input(raw, fallback_title=path.stem.replace("_", " ").title(), source=str(path))
    return scan_readiness(parsed)


def _load_scan_as(path: Path, label: str) -> dict:
    raw = path.read_text(encoding="utf-8")
    parsed = parse_input(raw, fallback_title=path.stem.replace("_", " ").title(), source=f"{label}:{path}")
    return scan_readiness(parsed)


def _is_url(target: str) -> bool:
    parsed = urlparse(target)
    return parsed.scheme in {"http", "https"}


def _fetch_url(url: str, timeout: float = 10.0) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http and https URLs are supported.")
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("content-type", "")
            raw = response.read()
    except URLError as exc:
        raise OSError(f"Failed to fetch {url}: {exc}") from exc
    if not raw:
        raise ValueError(f"Empty response from {url}.")
    charset = "utf-8"
    if "charset=" in content_type:
        charset = content_type.split("charset=", 1)[1].split(";", 1)[0].strip()
    return raw.decode(charset or "utf-8", errors="replace")


def _fetch_rendered_url(url: str, timeout: float = 15.0, wait_until: str = "networkidle") -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http and https URLs are supported.")
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ValueError(RENDER_EXTRA_MESSAGE) from exc

    timeout_ms = int(timeout * 1000)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=USER_AGENT)
                page.goto(url, wait_until=wait_until, timeout=timeout_ms)
                html = page.content()
            finally:
                browser.close()
    except PlaywrightError as exc:
        message = str(exc)
        if "Executable doesn't exist" in message or "playwright install" in message.lower():
            raise OSError(f"{RENDER_EXTRA_MESSAGE} Playwright reported: {message}") from exc
        raise OSError(f"Rendered snapshot failed for {url}: {message}") from exc
    if not html.strip():
        raise ValueError(f"Empty rendered response from {url}.")
    return html


def _slug_for_url(url: str) -> str:
    parsed = urlparse(url)
    base = "-".join(part for part in [parsed.netloc, parsed.path.strip("/").replace("/", "-")] if part)
    base = "".join(char.lower() if char.isalnum() else "-" for char in base).strip("-")
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return f"{base[:80] or 'snapshot'}-{digest}.html"


def _read_url_file(path: Path) -> list[str]:
    urls: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        urls.append(stripped)
    if not urls:
        raise ValueError(f"No URLs found in {path}.")
    return urls


def _write_snapshot_manifest(entries: list[dict], manifest_path: Path) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({"snapshots": entries}, indent=2) + "\n", encoding="utf-8")


def _load_target(target: str) -> dict:
    if _is_url(target):
        raw = _fetch_url(target)
        parsed = parse_input(raw, fallback_title=urlparse(target).netloc or "Fetched Product Page", source=target)
        return scan_readiness(parsed)
    path = Path(target)
    raw = path.read_text(encoding="utf-8")
    parsed = parse_input(raw, fallback_title=path.stem.replace("_", " ").title(), source=str(path.resolve()))
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
    if output_format == "sarif":
        return json.dumps(_render_sarif(results), indent=2) + "\n"
    if output_format == "json":
        payload = results if batch else results[0]
        return json.dumps(payload, indent=2) + "\n"
    if output_format == "jsonl":
        return "".join(json.dumps(item) + "\n" for item in results)
    if batch:
        return _render_batch_markdown(results)
    return render_markdown(results[0])


def _render_sarif(results: list[dict]) -> dict:
    rules: dict[str, dict] = {}
    sarif_results: list[dict] = []
    for bundle in results:
        source = bundle["page"]["source"]
        for check in bundle["checks"]:
            rule_id = f"agentshelf.{check['id']}"
            rules[rule_id] = {
                "id": rule_id,
                "name": check["label"],
                "shortDescription": {"text": check["label"]},
                "fullDescription": {"text": check["agent_impact"]},
                "help": {"text": check["recommendation"] or check["notes"]},
                "properties": {"dimension": check["dimension"], "weight": check["weight"]},
            }
            if check["passed"]:
                continue
            sarif_results.append(
                {
                    "ruleId": rule_id,
                    "level": "error" if check["weight"] >= 12 else "warning",
                    "message": {"text": check["recommendation"]},
                    "locations": [{"physicalLocation": {"artifactLocation": {"uri": source}}}],
                    "properties": {
                        "score": bundle["score"],
                        "band": bundle["band"],
                        "dimension": check["dimension"],
                        "agent_impact": check["agent_impact"],
                    },
                }
            )
        for issue in bundle["contradictions"]:
            rule_id = f"agentshelf.{issue['id']}"
            rules[rule_id] = {
                "id": rule_id,
                "name": issue["id"].replace("_", " ").title(),
                "shortDescription": {"text": issue["id"]},
                "fullDescription": {"text": issue["message"]},
                "help": {"text": issue["message"]},
            }
            sarif_results.append(
                {
                    "ruleId": rule_id,
                    "level": "error",
                    "message": {"text": issue["message"]},
                    "locations": [{"physicalLocation": {"artifactLocation": {"uri": source}}}],
                    "properties": {"score": bundle["score"], "band": bundle["band"]},
                }
            )
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "AgentShelf",
                        "informationUri": "https://github.com/wureny/AgentShelf",
                        "rules": list(rules.values()),
                    }
                },
                "results": sarif_results,
            }
        ],
    }


def _render_agent_tasks(results: list[dict]) -> str:
    lines: list[str] = []
    for bundle in results:
        contract = build_agent_contract(bundle)
        for task in contract["agent_tasks"]:
            lines.append(
                json.dumps(
                    {
                        "source": contract["target"]["source"],
                        "target_title": contract["target"]["title"],
                        "score": contract["score"],
                        "band": contract["band"],
                        "task": task,
                        "blocking_issues": contract["blocking_issues"],
                    }
                )
            )
    return "\n".join(lines) + ("\n" if lines else "")


def _check_map(bundle: dict) -> dict[str, dict]:
    return {check["id"]: check for check in bundle["checks"]}


def _build_compare(raw_bundle: dict, rendered_bundle: dict) -> dict:
    raw_checks = _check_map(raw_bundle)
    rendered_checks = _check_map(rendered_bundle)
    unlocked_signals = []
    regressions = []
    evidence_changes = []

    for check_id, rendered_check in rendered_checks.items():
        raw_check = raw_checks[check_id]
        if not raw_check["passed"] and rendered_check["passed"]:
            unlocked_signals.append(
                {
                    "check_id": check_id,
                    "dimension": rendered_check["dimension"],
                    "evidence": rendered_check["evidence"],
                    "agent_impact": rendered_check["agent_impact"],
                }
            )
        elif raw_check["passed"] and not rendered_check["passed"]:
            regressions.append(
                {
                    "check_id": check_id,
                    "dimension": rendered_check["dimension"],
                    "recommendation": rendered_check["recommendation"],
                }
            )
        if raw_check.get("evidence") != rendered_check.get("evidence") and rendered_check.get("evidence"):
            evidence_changes.append(
                {
                    "check_id": check_id,
                    "raw_evidence": raw_check.get("evidence"),
                    "rendered_evidence": rendered_check.get("evidence"),
                }
            )

    raw_issue_ids = {issue["id"] for issue in build_agent_contract(raw_bundle)["blocking_issues"]}
    rendered_contract = build_agent_contract(rendered_bundle)
    rendered_issue_ids = {issue["id"] for issue in rendered_contract["blocking_issues"]}
    resolved_issue_ids = sorted(raw_issue_ids - rendered_issue_ids)
    new_issue_ids = sorted(rendered_issue_ids - raw_issue_ids)

    dimension_delta = {
        key: rendered_bundle["dimensions"][key] - raw_bundle["dimensions"][key]
        for key in rendered_bundle["dimensions"]
    }
    return {
        "raw": {
            "source": raw_bundle["page"]["source"],
            "score": raw_bundle["score"],
            "band": raw_bundle["band"],
            "dimensions": raw_bundle["dimensions"],
            "confidence": raw_bundle["confidence"],
            "warnings": raw_bundle["warnings"],
        },
        "rendered": {
            "source": rendered_bundle["page"]["source"],
            "score": rendered_bundle["score"],
            "band": rendered_bundle["band"],
            "dimensions": rendered_bundle["dimensions"],
            "confidence": rendered_bundle["confidence"],
            "warnings": rendered_bundle["warnings"],
        },
        "delta": {
            "score": rendered_bundle["score"] - raw_bundle["score"],
            "dimensions": dimension_delta,
            "band_changed": raw_bundle["band"] != rendered_bundle["band"],
        },
        "unlocked_signals": unlocked_signals,
        "regressions": regressions,
        "evidence_changes": evidence_changes,
        "resolved_blocking_issues": resolved_issue_ids,
        "new_blocking_issues": new_issue_ids,
        "next_actions": rendered_contract["next_actions"],
        "agent_recommendation": _compare_recommendation(raw_bundle, rendered_bundle, unlocked_signals, regressions),
    }


def _compare_recommendation(raw_bundle: dict, rendered_bundle: dict, unlocked: list[dict], regressions: list[dict]) -> str:
    if regressions:
        return "Rendered snapshot removed or changed signals that raw HTML had; inspect hydration, geolocation, consent, or bot handling before trusting automation."
    if unlocked and rendered_bundle["score"] > raw_bundle["score"]:
        return "Use rendered snapshots for this page class; JavaScript hydration exposes commerce signals that raw HTML misses."
    if raw_bundle["score"] == rendered_bundle["score"] and not unlocked:
        return "Raw snapshot appears sufficient for this page class; rendered capture did not unlock additional readiness signals."
    return "Rendered and raw snapshots differ; inspect evidence_changes before choosing the cheaper capture mode."


def _render_compare_markdown(payload: dict) -> str:
    lines = [
        "# AgentShelf Snapshot Compare",
        "",
        "## Summary",
        f"- Raw score: {payload['raw']['score']} ({payload['raw']['band']})",
        f"- Rendered score: {payload['rendered']['score']} ({payload['rendered']['band']})",
        f"- Score delta: {payload['delta']['score']:+d}",
        f"- Recommendation: {payload['agent_recommendation']}",
        "",
        "## Dimension Delta",
    ]
    for dimension, delta in payload["delta"]["dimensions"].items():
        lines.append(f"- {dimension}: {delta:+d}")
    lines.extend(["", "## Unlocked Signals"])
    if payload["unlocked_signals"]:
        for item in payload["unlocked_signals"]:
            lines.append(f"- {item['check_id']}: {item['evidence'] or 'evidence present'}")
    else:
        lines.append("- None")
    lines.extend(["", "## Regressions"])
    if payload["regressions"]:
        for item in payload["regressions"]:
            lines.append(f"- {item['check_id']}: {item['recommendation']}")
    else:
        lines.append("- None")
    lines.extend(["", "## Next Actions"])
    if payload["next_actions"]:
        for item in payload["next_actions"]:
            lines.append(f"- {item}")
    else:
        lines.append("- No urgent rendered-snapshot fixes.")
    return "\n".join(lines) + "\n"


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
    scan.add_argument("--config", type=Path, help=f"Optional JSON config file. Defaults to {DEFAULT_CONFIG} when present.")
    scan.add_argument("--batch", action="store_true", help="Allow directory or glob batch scanning.")
    scan.add_argument(
        "--format",
        choices=("markdown", "json", "jsonl", "sarif"),
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

    agent = subcommands.add_parser("agent-audit", help="Emit a stable JSON contract for coding agents.")
    agent.add_argument("target", help="HTML/text file or http(s) URL to audit.")
    agent.add_argument("--format", choices=("json",), default="json", help="Output format. Defaults to JSON.")
    agent.add_argument("--contract", choices=("v1",), default="v1", help="Agent contract version.")
    agent.add_argument("--output", type=Path, help="Optional output file path.")
    agent.add_argument(
        "--fail-on-blockers",
        action="store_true",
        help="Return non-zero when high-severity blocking issues are present.",
    )

    tasks = subcommands.add_parser("agent-tasks", help="Emit JSONL remediation tasks for coding agents.")
    tasks.add_argument("path", help="HTML/text file, directory, or glob to scan.")
    tasks.add_argument("--batch", action="store_true", help="Allow directory or glob batch scanning.")
    tasks.add_argument("--output", type=Path, help="Optional output file path.")

    compare = subcommands.add_parser("compare", help="Compare raw and rendered snapshots for unlocked agent-readiness signals.")
    compare.add_argument("raw", type=Path, help="Raw HTML snapshot path.")
    compare.add_argument("rendered", type=Path, help="Rendered HTML snapshot path.")
    compare.add_argument("--format", choices=("markdown", "json"), default="markdown", help="Output format.")
    compare.add_argument("--output", type=Path, help="Optional output file path.")

    snapshot = subcommands.add_parser("snapshot", help="Fetch raw or rendered HTML for a product page URL.")
    snapshot.add_argument("url", nargs="?", help="http(s) URL to fetch.")
    snapshot.add_argument("--url-file", type=Path, help="Text file of URLs to snapshot, one per line.")
    snapshot.add_argument("--output", type=Path, help="Path to write a single fetched HTML file.")
    snapshot.add_argument("--output-dir", type=Path, help="Directory for --url-file batch snapshots.")
    snapshot.add_argument("--manifest", type=Path, help="Optional JSON manifest for batch snapshot output.")
    snapshot.add_argument("--timeout", type=float, default=10.0, help="Fetch timeout in seconds.")
    snapshot.add_argument(
        "--rendered",
        action="store_true",
        help="Use optional Playwright rendering. Requires `agentshelf[render]` and Chromium installed.",
    )
    snapshot.add_argument(
        "--wait-until",
        choices=("domcontentloaded", "load", "networkidle"),
        default="networkidle",
        help="Playwright page load state for --rendered snapshots.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return 2

    try:
        if args.command == "scan":
            config = _load_config(args.config)
            args.format = _config_value(config, "format", args.format, "markdown")
            args.min_score = _config_value(config, "min_score", args.min_score, None)
            args.fail_on = _config_value(config, "fail_on", args.fail_on, None)
            args.output = _config_value(config, "output", args.output, None)
            args.min_score = _coerce_score(args.min_score)
            if args.format not in {"markdown", "json", "jsonl", "sarif"}:
                raise ValueError("Config key `format` must be markdown, json, jsonl, or sarif.")
            if args.fail_on is not None and args.fail_on not in {"weak", "not_ready"}:
                raise ValueError("Config key `fail_on` must be weak or not_ready.")
            if args.output is not None and not isinstance(args.output, Path):
                args.output = Path(str(args.output))
            paths = _resolve_inputs(args.path, args.batch)
            batch = args.batch or len(paths) > 1
            results = [_load_scan(path) for path in paths]
            rendered = _render_results(results, args.format, batch)
            exit_code = 1 if any(_fails_threshold(item, args.min_score, args.fail_on) for item in results) else 0
        elif args.command == "agent-audit":
            bundle = _load_target(args.target)
            contract = build_agent_contract(bundle, contract=args.contract)
            rendered = json.dumps(contract, indent=2) + "\n"
            exit_code = 1 if args.fail_on_blockers and any(issue["severity"] == "high" for issue in contract["blocking_issues"]) else 0
        elif args.command == "agent-tasks":
            paths = _resolve_inputs(args.path, args.batch)
            if len(paths) > 1 and not args.batch:
                raise ValueError("Multiple inputs found. Re-run with --batch.")
            results = [_load_scan(path) for path in paths]
            rendered = _render_agent_tasks(results)
            exit_code = 0
        elif args.command == "compare":
            raw_bundle = _load_scan_as(args.raw, "raw")
            rendered_bundle = _load_scan_as(args.rendered, "rendered")
            payload = _build_compare(raw_bundle, rendered_bundle)
            rendered = json.dumps(payload, indent=2) + "\n" if args.format == "json" else _render_compare_markdown(payload)
            exit_code = 0
        elif args.command == "snapshot":
            if bool(args.url) == bool(args.url_file):
                raise ValueError("Provide exactly one of URL or --url-file.")
            if args.url_file:
                if args.output:
                    raise ValueError("Use --output-dir instead of --output with --url-file.")
                output_dir = args.output_dir or Path("snapshots")
                output_dir.mkdir(parents=True, exist_ok=True)
                entries = []
                for url in _read_url_file(args.url_file):
                    html = (
                        _fetch_rendered_url(url, timeout=args.timeout, wait_until=args.wait_until)
                        if args.rendered
                        else _fetch_url(url, timeout=args.timeout)
                    )
                    if not html.strip():
                        raise ValueError(f"Empty response from {url}.")
                    output_path = output_dir / _slug_for_url(url)
                    output_path.write_text(html, encoding="utf-8")
                    entries.append({"url": url, "path": str(output_path), "rendered": bool(args.rendered)})
                if args.manifest:
                    _write_snapshot_manifest(entries, args.manifest)
                return 0
            if args.output is None:
                raise ValueError("--output is required for single URL snapshots.")
            if args.rendered:
                html = _fetch_rendered_url(args.url, timeout=args.timeout, wait_until=args.wait_until)
            else:
                html = _fetch_url(args.url, timeout=args.timeout)
            if not html.strip():
                raise ValueError(f"Empty response from {args.url}.")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(html, encoding="utf-8")
            return 0
        else:
            parser.error(f"Unsupported command: {args.command}")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
