from __future__ import annotations

import argparse
import glob
import hashlib
import html
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from agentshelf.engine import ADAPTER_PROFILES, build_agent_contract, parse_input, render_markdown, scan_readiness


SUPPORTED_SUFFIXES = {".html", ".htm", ".txt"}
BAND_ORDER = {"not_ready": 0, "weak": 1, "workable": 2, "strong": 3}
DEFAULT_CONFIG = ".agentshelf.json"
USER_AGENT = "AgentShelf/0.16 (+https://github.com/wureny/AgentShelf)"
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


def _load_scan(path: Path, adapter_profile: str = "auto") -> dict:
    raw = path.read_text(encoding="utf-8")
    parsed = parse_input(raw, fallback_title=path.stem.replace("_", " ").title(), source=str(path))
    return scan_readiness(parsed, adapter_profile=adapter_profile)


def _load_scan_as(path: Path, label: str, adapter_profile: str = "auto") -> dict:
    raw = path.read_text(encoding="utf-8")
    parsed = parse_input(raw, fallback_title=path.stem.replace("_", " ").title(), source=f"{label}:{path}")
    return scan_readiness(parsed, adapter_profile=adapter_profile)


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


def _robots_url(site: str) -> str:
    parsed = urlparse(site)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Site must be an http(s) URL.")
    return f"{parsed.scheme}://{parsed.netloc}/robots.txt"


def _sitemap_urls_from_robots(robots_text: str) -> list[str]:
    urls = []
    for line in robots_text.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip().lower() == "sitemap":
            candidate = value.strip()
            if candidate:
                urls.append(candidate)
    return urls


def _extract_sitemap_locs(xml_text: str) -> tuple[list[str], list[str]]:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        raise ValueError(f"Invalid sitemap XML: {exc}.") from exc
    tag = root.tag.rsplit("}", 1)[-1].lower()
    locs = [
        (loc.text or "").strip()
        for loc in root.iter()
        if loc.tag.rsplit("}", 1)[-1].lower() == "loc" and (loc.text or "").strip()
    ]
    if tag == "sitemapindex":
        return locs, []
    return [], locs


def _discover_urls(
    site: str | None,
    sitemap: str | None,
    timeout: float,
    include: str,
    exclude: str | None,
    limit: int,
) -> dict:
    if bool(site) == bool(sitemap):
        raise ValueError("Provide exactly one of --site or --sitemap.")
    if limit < 1:
        raise ValueError("--limit must be at least 1.")

    warnings = []
    sitemap_queue: list[str]
    robots_source = None
    if site:
        robots_source = _robots_url(site)
        robots_text = _fetch_url(robots_source, timeout=timeout)
        sitemap_queue = _sitemap_urls_from_robots(robots_text)
        if not sitemap_queue:
            sitemap_queue = [urljoin(robots_source, "/sitemap.xml")]
            warnings.append("robots_missing_sitemap: falling back to /sitemap.xml")
    else:
        sitemap_queue = [sitemap or ""]

    seen_sitemaps = set()
    discovered: list[str] = []
    include_re = _compile_regex(include)
    exclude_re = _compile_regex(exclude) if exclude else None

    while sitemap_queue and len(discovered) < limit:
        current = sitemap_queue.pop(0)
        if current in seen_sitemaps:
            continue
        seen_sitemaps.add(current)
        xml_text = _fetch_url(current, timeout=timeout)
        child_sitemaps, urls = _extract_sitemap_locs(xml_text)
        sitemap_queue.extend(item for item in child_sitemaps if item not in seen_sitemaps)
        for url in urls:
            if include_re.search(url) and not (exclude_re and exclude_re.search(url)):
                discovered.append(url)
                if len(discovered) >= limit:
                    break

    return {
        "source": {"site": site, "robots": robots_source, "sitemaps_checked": sorted(seen_sitemaps)},
        "filters": {"include": include, "exclude": exclude, "limit": limit},
        "urls": discovered,
        "count": len(discovered),
        "warnings": warnings,
    }


def _compile_regex(pattern: str):
    import re

    try:
        return re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"Invalid regex {pattern!r}: {exc}") from exc


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


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)


def _load_target(target: str, adapter_profile: str = "auto") -> dict:
    if _is_url(target):
        raw = _fetch_url(target)
        parsed = parse_input(raw, fallback_title=urlparse(target).netloc or "Fetched Product Page", source=target)
        return scan_readiness(parsed, adapter_profile=adapter_profile)
    path = Path(target)
    raw = path.read_text(encoding="utf-8")
    parsed = parse_input(raw, fallback_title=path.stem.replace("_", " ").title(), source=str(path.resolve()))
    return scan_readiness(parsed, adapter_profile=adapter_profile)


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
        elif (
            raw_check.get("applicable", True)
            and rendered_check.get("applicable", True)
            and raw_check["passed"]
            and not rendered_check["passed"]
        ):
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


def _load_scan_results(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        raise ValueError(f"Empty scan result file: {path}.")
    if path.suffix.lower() == ".jsonl":
        rows = []
        for line_number, line in enumerate(raw.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL in {path} line {line_number}: {exc.msg}.") from exc
        return _validate_scan_results(rows, path)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc.msg}.") from exc
    rows = payload if isinstance(payload, list) else [payload]
    return _validate_scan_results(rows, path)


def _validate_scan_results(rows: list[dict], path: Path) -> list[dict]:
    if not rows:
        raise ValueError(f"No scan results found in {path}.")
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or not {"page", "score", "band", "checks"}.issubset(row):
            raise ValueError(
                f"{path} result {index} is not an AgentShelf scan result. "
                "Use `agentshelf scan ... --format json` or `--format jsonl`."
            )
    return rows


def _result_key(bundle: dict, key: str) -> str:
    page = bundle.get("page", {})
    value = page.get(key)
    if not value:
        raise ValueError(f"Scan result is missing page.{key}; cannot match audit runs.")
    return str(value)


def _blocking_issue_map(bundle: dict) -> dict[str, dict]:
    return {issue["id"]: issue for issue in build_agent_contract(bundle)["blocking_issues"]}


def _warning_set(bundle: dict) -> set[str]:
    return {str(item) for item in bundle.get("warnings", [])}


def _dimension_delta(baseline: dict, current: dict) -> dict[str, int]:
    keys = sorted(set(baseline.get("dimensions", {})) | set(current.get("dimensions", {})))
    return {
        key: int(current.get("dimensions", {}).get(key, 0)) - int(baseline.get("dimensions", {}).get(key, 0))
        for key in keys
    }


def _page_diff(source_key: str, baseline: dict, current: dict) -> dict:
    baseline_issues = _blocking_issue_map(baseline)
    current_issues = _blocking_issue_map(current)
    baseline_warnings = _warning_set(baseline)
    current_warnings = _warning_set(current)
    score_delta = int(current["score"]) - int(baseline["score"])
    band_delta = BAND_ORDER[current["band"]] - BAND_ORDER[baseline["band"]]
    new_issue_ids = sorted(set(current_issues) - set(baseline_issues))
    resolved_issue_ids = sorted(set(baseline_issues) - set(current_issues))
    current_contract = build_agent_contract(current)
    return {
        "key": source_key,
        "title": current.get("page", {}).get("title") or baseline.get("page", {}).get("title"),
        "baseline": {
            "score": baseline["score"],
            "band": baseline["band"],
            "dimensions": baseline.get("dimensions", {}),
        },
        "current": {
            "score": current["score"],
            "band": current["band"],
            "dimensions": current.get("dimensions", {}),
        },
        "delta": {
            "score": score_delta,
            "band_changed": baseline["band"] != current["band"],
            "band_direction": "improved" if band_delta > 0 else "regressed" if band_delta < 0 else "unchanged",
            "dimensions": _dimension_delta(baseline, current),
        },
        "new_blocking_issues": [current_issues[issue_id] for issue_id in new_issue_ids],
        "resolved_blocking_issues": [baseline_issues[issue_id] for issue_id in resolved_issue_ids],
        "new_warnings": sorted(current_warnings - baseline_warnings),
        "resolved_warnings": sorted(baseline_warnings - current_warnings),
        "next_actions": current_contract["next_actions"],
        "agent_tasks": current_contract["agent_tasks"][:3],
    }


def _is_regression(item: dict) -> bool:
    return (
        item["delta"]["score"] < 0
        or item["delta"]["band_direction"] == "regressed"
        or any(issue.get("severity") == "high" for issue in item["new_blocking_issues"])
    )


def _is_improvement(item: dict) -> bool:
    return (
        item["delta"]["score"] > 0
        or item["delta"]["band_direction"] == "improved"
        or bool(item["resolved_blocking_issues"])
    )


def _index_results(rows: list[dict], key: str, label: str) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for row in rows:
        row_key = _result_key(row, key)
        if row_key in indexed:
            raise ValueError(f"Duplicate {key} {row_key!r} in {label} results.")
        indexed[row_key] = row
    return indexed


def _build_audit_diff(baseline_rows: list[dict], current_rows: list[dict], key: str = "source") -> dict:
    baseline = _index_results(baseline_rows, key, "baseline")
    current = _index_results(current_rows, key, "current")
    common_keys = sorted(set(baseline) & set(current))
    page_diffs = [_page_diff(item, baseline[item], current[item]) for item in common_keys]
    regressions = sorted(
        [item for item in page_diffs if _is_regression(item)],
        key=lambda item: (
            item["delta"]["score"],
            -len([issue for issue in item["new_blocking_issues"] if issue.get("severity") == "high"]),
            item["key"],
        ),
    )
    improvements = sorted(
        [item for item in page_diffs if _is_improvement(item) and not _is_regression(item)],
        key=lambda item: (-item["delta"]["score"], item["key"]),
    )
    new_pages = [
        {
            "key": item,
            "title": current[item]["page"].get("title"),
            "score": current[item]["score"],
            "band": current[item]["band"],
        }
        for item in sorted(set(current) - set(baseline))
    ]
    removed_pages = [
        {
            "key": item,
            "title": baseline[item]["page"].get("title"),
            "score": baseline[item]["score"],
            "band": baseline[item]["band"],
        }
        for item in sorted(set(baseline) - set(current))
    ]
    unchanged_count = len(page_diffs) - len(regressions) - len(improvements)
    summary = {
        "baseline_count": len(baseline_rows),
        "current_count": len(current_rows),
        "matched_count": len(common_keys),
        "regressed_count": len(regressions),
        "improved_count": len(improvements),
        "unchanged_count": max(unchanged_count, 0),
        "new_page_count": len(new_pages),
        "removed_page_count": len(removed_pages),
    }
    return {
        "contract": "agentshelf.audit_diff.v1",
        "match_key": key,
        "summary": summary,
        "regressions": regressions,
        "improvements": improvements,
        "new_pages": new_pages,
        "removed_pages": removed_pages,
        "agent_recommendation": _audit_diff_recommendation(summary, regressions, new_pages, removed_pages),
    }


def _audit_diff_recommendation(summary: dict, regressions: list[dict], new_pages: list[dict], removed_pages: list[dict]) -> str:
    if regressions:
        first = regressions[0]
        return (
            f"Prioritize {first['key']}: score changed {first['delta']['score']:+d} "
            f"and {len(first['new_blocking_issues'])} blocking issue(s) are newly present."
        )
    if summary["improved_count"] and not summary["regressed_count"]:
        return "No regressions detected; review improved pages and keep the current publishing workflow."
    if new_pages or removed_pages:
        return "No matched-page regressions detected; review new or removed pages for catalog coverage changes."
    return "No material audit changes detected between these runs."


def _render_audit_diff_markdown(payload: dict) -> str:
    summary = payload["summary"]
    lines = [
        "# AgentShelf Audit Diff",
        "",
        "## Summary",
        f"- Baseline pages: {summary['baseline_count']}",
        f"- Current pages: {summary['current_count']}",
        f"- Matched pages: {summary['matched_count']}",
        f"- Regressed pages: {summary['regressed_count']}",
        f"- Improved pages: {summary['improved_count']}",
        f"- New pages: {summary['new_page_count']}",
        f"- Removed pages: {summary['removed_page_count']}",
        f"- Recommendation: {payload['agent_recommendation']}",
        "",
        "## Regressions",
    ]
    if payload["regressions"]:
        for item in payload["regressions"]:
            issues = ", ".join(issue["id"] for issue in item["new_blocking_issues"]) or "no new blockers"
            lines.append(
                f"- `{item['key']}`: {item['baseline']['score']} -> {item['current']['score']} "
                f"({item['delta']['score']:+d}), band {item['baseline']['band']} -> {item['current']['band']}; "
                f"new blockers: {issues}"
            )
    else:
        lines.append("- None")
    lines.extend(["", "## Improvements"])
    if payload["improvements"]:
        for item in payload["improvements"]:
            resolved = ", ".join(issue["id"] for issue in item["resolved_blocking_issues"]) or "score/band improved"
            lines.append(
                f"- `{item['key']}`: {item['baseline']['score']} -> {item['current']['score']} "
                f"({item['delta']['score']:+d}); resolved: {resolved}"
            )
    else:
        lines.append("- None")
    lines.extend(["", "## Catalog Changes"])
    if payload["new_pages"]:
        for item in payload["new_pages"]:
            lines.append(f"- New `{item['key']}`: {item['score']} ({item['band']})")
    if payload["removed_pages"]:
        for item in payload["removed_pages"]:
            lines.append(f"- Removed `{item['key']}`: {item['score']} ({item['band']})")
    if not payload["new_pages"] and not payload["removed_pages"]:
        lines.append("- None")
    lines.extend(["", "## Next Actions"])
    if payload["regressions"]:
        for item in payload["regressions"][:5]:
            if item["agent_tasks"]:
                task = item["agent_tasks"][0]
                lines.append(f"- `{item['key']}`: {task['id']} - {task['acceptance_check']}")
            elif item["next_actions"]:
                lines.append(f"- `{item['key']}`: {item['next_actions'][0]}")
    else:
        lines.append("- No regression remediation needed.")
    return "\n".join(lines) + "\n"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _unique_archive_path(history_dir: Path, timestamp: str) -> Path:
    path = history_dir / f"results-{timestamp}.jsonl"
    counter = 2
    while path.exists():
        path = history_dir / f"results-{timestamp}-{counter}.jsonl"
        counter += 1
    return path


def _build_audit_run(
    target: str,
    batch: bool,
    history_dir: Path,
    report_path: Path | None,
    tasks_path: Path | None,
    min_score: int | None,
    fail_on: str | None,
    key: str,
    adapter_profile: str,
) -> tuple[dict, str]:
    paths = _resolve_inputs(target, batch)
    if len(paths) > 1 and not batch:
        raise ValueError("Multiple inputs found. Re-run with --batch.")
    results = [_load_scan(path, adapter_profile=adapter_profile) for path in paths]
    timestamp = _utc_timestamp()
    history_dir.mkdir(parents=True, exist_ok=True)

    current_results = _render_results(results, "jsonl", batch=True)
    current_path = history_dir / "current-results.jsonl"
    previous_path = history_dir / "previous-results.jsonl"
    archive_path = _unique_archive_path(history_dir, timestamp)
    latest_report_path = report_path or history_dir / "audit-diff.md"
    tasks_written = None

    previous_rows = _load_scan_results(current_path) if current_path.exists() else None
    diff_payload = _build_audit_diff(previous_rows, results, key=key) if previous_rows else None
    report_text = (
        _render_audit_diff_markdown(diff_payload)
        if diff_payload
        else _render_first_audit_run_markdown(results, current_path, archive_path)
    )

    _write_text_atomic(archive_path, current_results)
    if current_path.exists():
        previous_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(current_path, previous_path)
    _write_text_atomic(current_path, current_results)
    _write_text_atomic(latest_report_path, report_text)
    if tasks_path:
        _write_text_atomic(tasks_path, _render_agent_tasks(results))
        tasks_written = str(tasks_path)

    exit_code = 1 if any(_fails_threshold(item, min_score, fail_on) for item in results) else 0
    payload = {
        "contract": "agentshelf.audit_run.v1",
        "target": target,
        "scanned_at": timestamp,
        "input_count": len(paths),
        "result_count": len(results),
        "history_dir": str(history_dir),
        "current_results": str(current_path),
        "previous_results": str(previous_path) if previous_path.exists() else None,
        "archive_results": str(archive_path),
        "diff_report": str(latest_report_path),
        "tasks_output": tasks_written,
        "diff": diff_payload["summary"] if diff_payload else None,
        "threshold_failed": bool(exit_code),
        "min_score": min_score,
        "fail_on": fail_on,
        "adapter_profile": adapter_profile,
    }
    return payload, _render_audit_run_markdown(payload)


def _render_first_audit_run_markdown(results: list[dict], current_path: Path, archive_path: Path) -> str:
    lines = [
        "# AgentShelf Audit Run",
        "",
        "## Summary",
        f"- Baseline created: {current_path}",
        f"- Archive written: {archive_path}",
        f"- Pages scanned: {len(results)}",
        "- Diff report: unavailable until the next run",
        "",
        "## Current Scores",
        "| Score | Band | Source |",
        "| ---: | --- | --- |",
    ]
    for item in results:
        lines.append(f"| {item['score']} | {item['band']} | `{item['page']['source']}` |")
    return "\n".join(lines) + "\n"


def _render_audit_run_markdown(payload: dict) -> str:
    lines = [
        "# AgentShelf Audit Run",
        "",
        f"- Target: `{payload['target']}`",
        f"- Results: `{payload['current_results']}`",
        f"- Previous: `{payload['previous_results'] or 'not available yet'}`",
        f"- Archive: `{payload['archive_results']}`",
        f"- Diff report: `{payload['diff_report']}`",
        f"- Threshold failed: {str(payload['threshold_failed']).lower()}",
    ]
    if payload["tasks_output"]:
        lines.append(f"- Agent tasks: `{payload['tasks_output']}`")
    if payload["diff"]:
        summary = payload["diff"]
        lines.extend(
            [
                "",
                "## Diff Summary",
                f"- Regressed pages: {summary['regressed_count']}",
                f"- Improved pages: {summary['improved_count']}",
                f"- New pages: {summary['new_page_count']}",
                f"- Removed pages: {summary['removed_page_count']}",
            ]
        )
    else:
        lines.extend(["", "## Diff Summary", "- Baseline created; run again to produce a regression diff."])
    return "\n".join(lines) + "\n"


def _calibration_category(bundle: dict, check: dict | None = None, warning: str | None = None, issue: dict | None = None) -> dict:
    source = bundle["page"]["source"]
    if warning and "dynamic_rendering_likely" in warning:
        return {
            "category": "rendered_capture_review",
            "source": source,
            "reason": "Static snapshot looks JS-rendered; raw HTML may create false negatives for price, inventory, variants, or reviews.",
            "suggested_label": "needs_rendered_snapshot",
        }
    if issue:
        return {
            "category": "contradiction_review",
            "source": source,
            "reason": issue["message"],
            "suggested_label": "verify_visible_vs_schema_truth",
        }
    if check is None:
        return {
            "category": "low_confidence_review",
            "source": source,
            "reason": bundle["confidence"]["basis"],
            "suggested_label": "needs_human_calibration",
        }
    if check["id"] in {"subscription_terms", "bundle_components", "regional_shipping_promises"}:
        return {
            "category": "profile_rule_review",
            "source": source,
            "reason": check["evidence"] or check["recommendation"],
            "suggested_label": f"verify_{check['id']}",
        }
    if check["id"] == "return_policy_schema":
        return {
            "category": "policy_schema_review",
            "source": source,
            "reason": check["evidence"] or check["recommendation"],
            "suggested_label": "verify_return_policy_schema_gap",
        }
    if check["id"] in {"price", "availability", "variant_readiness", "offer_completeness"}:
        return {
            "category": "offer_extraction_review",
            "source": source,
            "reason": check["evidence"] or check["recommendation"],
            "suggested_label": f"verify_{check['id']}_extraction",
        }
    return {
        "category": "content_gap_review",
        "source": source,
        "reason": check["evidence"] or check["recommendation"],
        "suggested_label": f"verify_{check['id']}",
    }


def _calibration_priority(bundle: dict) -> int:
    band_weight = {"not_ready": 4, "weak": 3, "workable": 2, "strong": 1}
    contract = build_agent_contract(bundle)
    return (
        band_weight.get(bundle["band"], 0) * 100
        + len(contract["blocking_issues"]) * 10
        + len(bundle.get("warnings", [])) * 5
        + len(bundle.get("contradictions", [])) * 15
    )


def _build_calibration(results: list[dict], source_label: str, max_fixtures: int) -> dict:
    pages = []
    category_counts: dict[str, int] = {}
    fixture_candidates = []
    for bundle in results:
        contract = build_agent_contract(bundle)
        categories = []
        for warning in bundle.get("warnings", []):
            categories.append(_calibration_category(bundle, warning=warning))
        for issue in bundle.get("contradictions", []):
            categories.append(_calibration_category(bundle, issue=issue))
        for check in bundle["checks"]:
            if not check.get("applicable", True) or check["passed"]:
                continue
            categories.append(_calibration_category(bundle, check=check))
        if bundle["confidence"]["level"] == "low":
            categories.append(_calibration_category(bundle))

        deduped = []
        seen = set()
        for item in categories:
            key = (item["category"], item["suggested_label"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
            category_counts[item["category"]] = category_counts.get(item["category"], 0) + 1

        page_item = {
            "source": bundle["page"]["source"],
            "title": bundle["page"]["title"],
            "score": bundle["score"],
            "band": bundle["band"],
            "confidence": bundle["confidence"],
            "adapter_profile": bundle["commerce_signals"]["adapter_profile"],
            "review_categories": deduped,
            "blocking_issue_ids": [issue["id"] for issue in contract["blocking_issues"]],
            "agent_task_ids": [task["id"] for task in contract["agent_tasks"]],
            "priority": _calibration_priority(bundle),
        }
        pages.append(page_item)
        if deduped:
            fixture_candidates.append(page_item)

    fixture_candidates = sorted(fixture_candidates, key=lambda item: (-item["priority"], item["source"]))[:max_fixtures]
    return {
        "contract": "agentshelf.calibration.v1",
        "source": source_label,
        "summary": {
            "pages": len(results),
            "review_pages": len([page for page in pages if page["review_categories"]]),
            "category_counts": dict(sorted(category_counts.items())),
            "bands": {band: sum(1 for item in results if item["band"] == band) for band in BAND_ORDER},
            "confidence": {
                level: sum(1 for item in results if item["confidence"]["level"] == level)
                for level in ("high", "medium", "low")
            },
        },
        "pages": sorted(pages, key=lambda item: (-item["priority"], item["source"])),
        "fixture_candidates": fixture_candidates,
        "agent_next_actions": _calibration_next_actions(category_counts),
    }


def _calibration_next_actions(category_counts: dict[str, int]) -> list[str]:
    actions = []
    if category_counts.get("rendered_capture_review"):
        actions.append("Run `agentshelf compare` on representative raw/rendered pairs before changing scoring rules.")
    if category_counts.get("profile_rule_review"):
        actions.append("Review subscription, bundle, and regional-shipping pages for intentional false positives, then add fixtures for confirmed patterns.")
    if category_counts.get("policy_schema_review"):
        actions.append("Check whether return policy schema is absent or just nested in a storefront-specific structure AgentShelf should parse.")
    if category_counts.get("offer_extraction_review"):
        actions.append("Inspect page source for platform-specific price, inventory, or variant data that should become adapter evidence.")
    if not actions:
        actions.append("No calibration hotspots detected; keep the current rules and add fixtures only for new merchant patterns.")
    return actions


def _render_calibration_markdown(payload: dict) -> str:
    summary = payload["summary"]
    lines = [
        "# AgentShelf Calibration Report",
        "",
        "## Summary",
        f"- Source: `{payload['source']}`",
        f"- Pages: {summary['pages']}",
        f"- Pages needing review: {summary['review_pages']}",
        f"- Bands: {', '.join(f'{key}={value}' for key, value in summary['bands'].items())}",
        f"- Confidence: {', '.join(f'{key}={value}' for key, value in summary['confidence'].items())}",
        "",
        "## Review Categories",
    ]
    if summary["category_counts"]:
        for category, count in summary["category_counts"].items():
            lines.append(f"- {category}: {count}")
    else:
        lines.append("- None")
    lines.extend(["", "## Fixture Candidates"])
    if payload["fixture_candidates"]:
        for item in payload["fixture_candidates"]:
            category_names = sorted({category["category"] for category in item["review_categories"]})
            categories = ", ".join(category_names)
            lines.append(f"- `{item['source']}`: {item['score']} ({item['band']}), {categories}")
    else:
        lines.append("- None")
    lines.extend(["", "## Agent Next Actions"])
    for action in payload["agent_next_actions"]:
        lines.append(f"- {action}")
    return "\n".join(lines) + "\n"


def _anonymize_html(text: str) -> str:
    text = re.sub(r"https?://[^\s\"'<>]+", "https://example.com/product", text)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "merchant@example.com", text)
    text = re.sub(r"\+?\d[\d\s().-]{7,}\d", "000-000-0000", text)
    text = re.sub(r"\b[A-Z0-9._%+-]+\.myshopify\.com\b", "demo-store.myshopify.com", text, flags=re.IGNORECASE)
    return text


def _safe_fixture_name(source: str, index: int) -> str:
    parsed = urlparse(source)
    base = parsed.path if parsed.scheme else source
    name = Path(base).stem or "fixture"
    slug = "".join(char.lower() if char.isalnum() else "-" for char in name).strip("-")[:48] or "fixture"
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:8]
    return f"{index:02d}-{slug}-{digest}.html"


def _export_calibration_fixtures(payload: dict, output_dir: Path) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    exported = []
    for index, candidate in enumerate(payload["fixture_candidates"], start=1):
        source = candidate["source"]
        source_path = Path(source)
        if not source_path.exists() or not source_path.is_file():
            exported.append({"source": source, "status": "skipped", "reason": "source is not a local file"})
            continue
        fixture_path = output_dir / _safe_fixture_name(source, index)
        metadata_path = fixture_path.with_suffix(".json")
        fixture_path.write_text(_anonymize_html(source_path.read_text(encoding="utf-8")), encoding="utf-8")
        metadata_path.write_text(
            json.dumps(
                {
                    "source": source,
                    "fixture": str(fixture_path),
                    "score": candidate["score"],
                    "band": candidate["band"],
                    "review_categories": candidate["review_categories"],
                    "agent_task_ids": candidate["agent_task_ids"],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        exported.append({"source": source, "status": "exported", "fixture": str(fixture_path), "metadata": str(metadata_path)})
    return exported


def _load_calibration_labels(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid calibration labels {path}: {exc.msg}.") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid calibration labels {path}: expected a JSON object.")
    labels = payload.get("labels")
    if not isinstance(labels, list) or not labels:
        raise ValueError(f"Invalid calibration labels {path}: expected a non-empty labels array.")
    normalized = []
    for index, label in enumerate(labels, start=1):
        if not isinstance(label, dict):
            raise ValueError(f"Invalid label {index}: expected an object.")
        if not (label.get("source") or label.get("title")):
            raise ValueError(f"Invalid label {index}: source or title is required.")
        kind = str(label.get("kind", "check"))
        if kind not in {"check", "blocking_issue", "agent_task", "category", "warning"}:
            raise ValueError(f"Invalid label {index}: kind must be check, blocking_issue, agent_task, category, or warning.")
        label_id = label.get("id")
        if not isinstance(label_id, str) or not label_id:
            raise ValueError(f"Invalid label {index}: id is required.")
        expected = label.get("expected")
        verdict = label.get("verdict")
        if verdict == "needs_review":
            expected = expected or "present"
        if expected is None and verdict == "true_positive":
            expected = "present"
        if expected is None and verdict == "false_positive":
            expected = "absent"
        if expected not in {"present", "absent"}:
            raise ValueError(f"Invalid label {index}: expected must be present or absent.")
        normalized.append(
            {
                "source": label.get("source"),
                "title": label.get("title"),
                "kind": kind,
                "id": label_id,
                "expected": expected,
                "verdict": verdict,
                "status": label.get("status"),
                "note": label.get("note"),
            }
        )
    return {
        "contract": payload.get("contract", "agentshelf.calibration_labels.v1"),
        "match_key": payload.get("match_key"),
        "labels": normalized,
    }


def _evaluation_observations(bundle: dict) -> dict[str, set[str]]:
    contract = build_agent_contract(bundle)
    failed_checks = {
        check["id"]
        for check in bundle["checks"]
        if check.get("applicable", True) and not check["passed"]
    }
    warnings = set()
    for warning in bundle.get("warnings", []):
        warnings.add(str(warning))
        warnings.add(str(warning).split(":", 1)[0])
    return {
        "check": failed_checks,
        "blocking_issue": {issue["id"] for issue in contract["blocking_issues"]},
        "agent_task": {task["id"] for task in contract["agent_tasks"]},
        "category": {category["category"] for category in _build_calibration([bundle], bundle["page"]["source"], max_fixtures=1)["pages"][0]["review_categories"]},
        "warning": warnings,
    }


def _label_key(label: dict, default_key: str) -> tuple[str, str]:
    if label.get("source"):
        return "source", str(label["source"])
    if label.get("title"):
        return "title", str(label["title"])
    return default_key, ""


def _bundle_key(bundle: dict, key: str) -> str:
    page = bundle.get("page", {})
    value = page.get(key)
    if not value:
        raise ValueError(f"Scan result is missing page.{key}; cannot evaluate labels.")
    return str(value)


def _build_calibration_evaluation(results: list[dict], labels_payload: dict, key: str = "source") -> dict:
    indexes = {
        "source": _index_results(results, "source", "evaluation"),
        "title": _index_results(results, "title", "evaluation"),
    }
    evaluated = []
    missing_pages = []
    for label in labels_payload["labels"]:
        if label.get("verdict") == "needs_review" or label.get("status") == "draft":
            evaluated.append({**label, "actual": "skipped", "passed": True, "skipped": True})
            continue
        match_key, match_value = _label_key(label, key)
        bundle = indexes[match_key].get(match_value)
        if bundle is None and match_key == "source":
            source_path = Path(match_value)
            if source_path.exists():
                bundle = indexes[match_key].get(str(source_path.resolve()))
        if bundle is None:
            missing_pages.append(label)
            evaluated.append({**label, "actual": "missing_page", "passed": False})
            continue
        observed = _evaluation_observations(bundle)
        present = label["id"] in observed[label["kind"]]
        actual = "present" if present else "absent"
        evaluated.append(
            {
                **label,
                "actual": actual,
                "passed": actual == label["expected"],
                "page": {
                    "source": bundle["page"]["source"],
                    "title": bundle["page"]["title"],
                    "score": bundle["score"],
                    "band": bundle["band"],
                },
            }
        )
    scored = [item for item in evaluated if not item.get("skipped")]
    failures = [item for item in scored if not item["passed"]]
    false_positive_regressions = [
        item
        for item in failures
        if item.get("verdict") == "false_positive" or item.get("expected") == "absent"
    ]
    true_positive_regressions = [
        item
        for item in failures
        if item.get("verdict") == "true_positive" or item.get("expected") == "present"
    ]
    passed = len(scored) - len(failures)
    total = len(scored)
    return {
        "contract": "agentshelf.calibration_evaluation.v1",
        "labels_contract": labels_payload["contract"],
        "summary": {
            "labels": len(evaluated),
            "scored_labels": total,
            "skipped_labels": len(evaluated) - total,
            "passed": passed,
            "failed": len(failures),
            "accuracy": round(passed / total, 4) if total else 0,
            "missing_pages": len(missing_pages),
            "false_positive_regressions": len(false_positive_regressions),
            "true_positive_regressions": len(true_positive_regressions),
        },
        "failures": failures,
        "results": evaluated,
        "agent_next_actions": _evaluation_next_actions(failures, skipped_count=len(evaluated) - total, scored_count=total),
    }


def _evaluation_next_actions(failures: list[dict], skipped_count: int = 0, scored_count: int = 0) -> list[str]:
    if skipped_count and not scored_count:
        return ["All labels are still draft needs_review labels; review them and mark useful labels true_positive or false_positive before using this as a CI gate."]
    if not failures:
        return ["All labeled calibration expectations passed; this rule set is safe against the current labeled fixtures."]
    actions = []
    absent_failures = [item for item in failures if item["expected"] == "absent" and item["actual"] == "present"]
    present_failures = [item for item in failures if item["expected"] == "present" and item["actual"] == "absent"]
    missing_pages = [item for item in failures if item["actual"] == "missing_page"]
    if absent_failures:
        actions.append("Review false-positive labels that are still present before tightening CI thresholds.")
    if present_failures:
        actions.append("Review true-positive labels that disappeared; a rule may have become too lenient.")
    if missing_pages:
        actions.append("Update label source/title keys or regenerate scan artifacts for missing labeled pages.")
    return actions


def _render_calibration_evaluation_markdown(payload: dict) -> str:
    summary = payload["summary"]
    lines = [
        "# AgentShelf Calibration Evaluation",
        "",
        "## Summary",
        f"- Labels: {summary['labels']}",
        f"- Scored labels: {summary['scored_labels']}",
        f"- Skipped draft labels: {summary['skipped_labels']}",
        f"- Passed: {summary['passed']}",
        f"- Failed: {summary['failed']}",
        f"- Accuracy: {summary['accuracy']:.2%}",
        f"- Missing pages: {summary['missing_pages']}",
        f"- False-positive regressions: {summary['false_positive_regressions']}",
        f"- True-positive regressions: {summary['true_positive_regressions']}",
        "",
        "## Failures",
    ]
    if payload["failures"]:
        for item in payload["failures"]:
            target = item.get("source") or item.get("title")
            lines.append(
                f"- `{target}` {item['kind']} `{item['id']}` expected {item['expected']} "
                f"but was {item['actual']}"
            )
    else:
        lines.append("- None")
    lines.extend(["", "## Agent Next Actions"])
    for action in payload["agent_next_actions"]:
        lines.append(f"- {action}")
    return "\n".join(lines) + "\n"


def _load_calibration_report(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid calibration report {path}: {exc.msg}.") from exc
    if not isinstance(payload, dict) or payload.get("contract") != "agentshelf.calibration.v1":
        raise ValueError(f"{path} is not an AgentShelf calibration JSON report. Use `agentshelf calibrate --format json`.")
    pages = payload.get("pages")
    if not isinstance(pages, list):
        raise ValueError(f"Invalid calibration report {path}: pages must be an array.")
    return payload


def _draft_label(source: str, kind: str, label_id: str, note: str, title: str | None = None) -> dict:
    label = {
        "source": source,
        "kind": kind,
        "id": label_id,
        "verdict": "needs_review",
        "expected": "present",
        "status": "draft",
        "note": note,
    }
    if title:
        label["title"] = title
    return label


def _build_draft_labels(calibration: dict, max_pages: int, max_labels: int, include_tasks: bool) -> dict:
    labels = []
    for page in calibration.get("pages", [])[:max_pages]:
        source = page["source"]
        title = page.get("title")
        for category in page.get("review_categories", []):
            labels.append(
                _draft_label(
                    source,
                    "category",
                    category["category"],
                    f"Review suggested label `{category['suggested_label']}`: {category['reason']}",
                    title=title,
                )
            )
        for issue_id in page.get("blocking_issue_ids", []):
            labels.append(
                _draft_label(
                    source,
                    "blocking_issue",
                    issue_id,
                    "Confirm whether this blocking issue is a true positive or false positive for this merchant page.",
                    title=title,
                )
            )
        if include_tasks:
            for task_id in page.get("agent_task_ids", []):
                labels.append(
                    _draft_label(
                        source,
                        "agent_task",
                        task_id,
                        "Confirm whether this agent remediation task should remain actionable for this page.",
                        title=title,
                    )
                )
        if len(labels) >= max_labels:
            break
    deduped = []
    seen = set()
    for label in labels:
        key = (label["source"], label["kind"], label["id"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(label)
        if len(deduped) >= max_labels:
            break
    return {
        "contract": "agentshelf.calibration_labels.v1",
        "source_calibration": calibration.get("source"),
        "status": "draft",
        "instructions": [
            "Review each draft label against the source page or anonymized fixture.",
            "Change verdict to true_positive when the finding should remain present.",
            "Change verdict to false_positive when the finding should be absent after a rule fix.",
            "Remove labels that are not useful for future regression checks.",
        ],
        "labels": deduped,
    }


def _dashboard_category_names(page: dict) -> list[str]:
    return sorted({category["category"] for category in page.get("review_categories", [])})


def _render_dashboard_markdown(calibration: dict) -> str:
    summary = calibration["summary"]
    lines = [
        "# AgentShelf Calibration Dashboard",
        "",
        "## Summary",
        f"- Source: `{calibration['source']}`",
        f"- Pages: {summary['pages']}",
        f"- Pages needing review: {summary['review_pages']}",
        f"- Bands: {', '.join(f'{key}={value}' for key, value in summary['bands'].items())}",
        f"- Confidence: {', '.join(f'{key}={value}' for key, value in summary['confidence'].items())}",
        "",
        "## Category Counts",
    ]
    if summary["category_counts"]:
        for category, count in summary["category_counts"].items():
            lines.append(f"- {category}: {count}")
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Review Queue",
            "| Priority | Score | Band | Title | Categories | Blocking issues | Agent tasks |",
            "| ---: | ---: | --- | --- | --- | --- | --- |",
        ]
    )
    for page in calibration.get("pages", []):
        categories = ", ".join(_dashboard_category_names(page)) or "None"
        blockers = ", ".join(page.get("blocking_issue_ids", [])) or "None"
        tasks = ", ".join(page.get("agent_task_ids", [])) or "None"
        lines.append(
            f"| {page['priority']} | {page['score']} | {page['band']} | "
            f"{page['title']} | {categories} | {blockers} | {tasks} |"
        )
    lines.extend(["", "## Next Actions"])
    for action in calibration.get("agent_next_actions", []):
        lines.append(f"- {action}")
    return "\n".join(lines) + "\n"


def _html_escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _render_dashboard_html(calibration: dict) -> str:
    summary = calibration["summary"]
    category_cards = "\n".join(
        f"<div class='metric'><span>{_html_escape(category)}</span><strong>{count}</strong></div>"
        for category, count in summary["category_counts"].items()
    ) or "<div class='metric'><span>No review categories</span><strong>0</strong></div>"
    rows = []
    for page in calibration.get("pages", []):
        categories = "".join(f"<span class='tag'>{_html_escape(category)}</span>" for category in _dashboard_category_names(page))
        blockers = "".join(f"<span class='pill danger'>{_html_escape(item)}</span>" for item in page.get("blocking_issue_ids", []))
        tasks = "".join(f"<span class='pill'>{_html_escape(item)}</span>" for item in page.get("agent_task_ids", []))
        source = _html_escape(page["source"])
        rows.append(
            "<article class='page-card'>"
            f"<div class='page-head'><div><h2>{_html_escape(page['title'])}</h2><p>{source}</p></div>"
            f"<div class='score'><strong>{page['score']}</strong><span>{_html_escape(page['band'])}</span></div></div>"
            f"<div class='meta'><span>Priority {_html_escape(page['priority'])}</span>"
            f"<span>Confidence {_html_escape(page['confidence']['level'])}</span>"
            f"<span>Profile {_html_escape(page['adapter_profile']['active'])}</span></div>"
            f"<div class='section'><h3>Review categories</h3><div>{categories or '<span class=\"muted\">None</span>'}</div></div>"
            f"<div class='section'><h3>Blocking issues</h3><div>{blockers or '<span class=\"muted\">None</span>'}</div></div>"
            f"<div class='section'><h3>Agent tasks</h3><div>{tasks or '<span class=\"muted\">None</span>'}</div></div>"
            "</article>"
        )
    actions = "\n".join(f"<li>{_html_escape(action)}</li>" for action in calibration.get("agent_next_actions", []))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentShelf Calibration Dashboard</title>
  <style>
    :root {{
      --ink: #171512;
      --muted: #6c655d;
      --paper: #f7f0e4;
      --card: #fffaf2;
      --line: #dfd0bc;
      --accent: #0f766e;
      --danger: #b42318;
    }}
    body {{
      margin: 0;
      font-family: Georgia, 'Times New Roman', serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(15, 118, 110, .16), transparent 34rem),
        linear-gradient(135deg, #fbf5ea, var(--paper));
    }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 48px 24px; }}
    header {{ border-bottom: 2px solid var(--ink); padding-bottom: 24px; margin-bottom: 28px; }}
    h1 {{ font-size: clamp(2.2rem, 6vw, 5rem); line-height: .92; margin: 0 0 14px; letter-spacing: -.05em; }}
    h2 {{ margin: 0; font-size: 1.35rem; }}
    h3 {{ margin: 0 0 8px; color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .08em; font-family: ui-sans-serif, system-ui, sans-serif; }}
    p {{ color: var(--muted); }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 22px 0; }}
    .metric {{ background: var(--card); border: 1px solid var(--line); padding: 14px; box-shadow: 4px 4px 0 rgba(23,21,18,.08); }}
    .metric span {{ display: block; color: var(--muted); font-family: ui-sans-serif, system-ui, sans-serif; font-size: .82rem; }}
    .metric strong {{ font-size: 1.9rem; }}
    .grid {{ display: grid; gap: 18px; }}
    .page-card {{ background: rgba(255,250,242,.88); border: 1px solid var(--line); padding: 18px; }}
    .page-head {{ display: flex; justify-content: space-between; gap: 16px; border-bottom: 1px solid var(--line); padding-bottom: 12px; }}
    .page-head p {{ margin: 6px 0 0; overflow-wrap: anywhere; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .78rem; }}
    .score {{ min-width: 82px; text-align: center; background: var(--ink); color: var(--paper); padding: 10px; }}
    .score strong {{ display: block; font-size: 1.8rem; }}
    .score span {{ font-family: ui-sans-serif, system-ui, sans-serif; font-size: .78rem; text-transform: uppercase; }}
    .meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }}
    .meta span, .tag, .pill {{ display: inline-block; border: 1px solid var(--line); border-radius: 999px; padding: 5px 9px; margin: 2px; font-family: ui-sans-serif, system-ui, sans-serif; font-size: .78rem; background: white; }}
    .tag {{ border-color: rgba(15,118,110,.35); color: var(--accent); }}
    .pill.danger {{ color: var(--danger); border-color: rgba(180,35,24,.35); }}
    .section {{ margin-top: 12px; }}
    .muted {{ color: var(--muted); }}
    .actions {{ background: var(--ink); color: var(--paper); padding: 18px; margin-top: 24px; }}
    .actions h2, .actions p {{ color: var(--paper); }}
    @media (max-width: 700px) {{ .page-head {{ flex-direction: column; }} .score {{ width: fit-content; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>AgentShelf Calibration Dashboard</h1>
      <p>Source: <code>{_html_escape(calibration['source'])}</code></p>
    </header>
    <section class="summary">
      <div class="metric"><span>Pages</span><strong>{summary['pages']}</strong></div>
      <div class="metric"><span>Needs review</span><strong>{summary['review_pages']}</strong></div>
      <div class="metric"><span>Strong</span><strong>{summary['bands'].get('strong', 0)}</strong></div>
      <div class="metric"><span>Weak or not ready</span><strong>{summary['bands'].get('weak', 0) + summary['bands'].get('not_ready', 0)}</strong></div>
      {category_cards}
    </section>
    <section class="grid">
      {''.join(rows)}
    </section>
    <section class="actions">
      <h2>Agent Next Actions</h2>
      <ul>{actions}</ul>
    </section>
  </main>
</body>
</html>
"""


def _render_discovery(payload: dict, output_format: str) -> str:
    if output_format == "json":
        return json.dumps(payload, indent=2) + "\n"
    if output_format == "jsonl":
        return "".join(json.dumps({"url": url}) + "\n" for url in payload["urls"])
    return "\n".join(payload["urls"]) + ("\n" if payload["urls"] else "")


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
    scan.add_argument("--profile", choices=ADAPTER_PROFILES, default="auto", help="Storefront adapter profile for commerce extraction.")
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
    agent.add_argument("--profile", choices=ADAPTER_PROFILES, default="auto", help="Storefront adapter profile for commerce extraction.")
    agent.add_argument(
        "--fail-on-blockers",
        action="store_true",
        help="Return non-zero when high-severity blocking issues are present.",
    )

    tasks = subcommands.add_parser("agent-tasks", help="Emit JSONL remediation tasks for coding agents.")
    tasks.add_argument("path", help="HTML/text file, directory, or glob to scan.")
    tasks.add_argument("--batch", action="store_true", help="Allow directory or glob batch scanning.")
    tasks.add_argument("--output", type=Path, help="Optional output file path.")
    tasks.add_argument("--profile", choices=ADAPTER_PROFILES, default="auto", help="Storefront adapter profile for commerce extraction.")

    compare = subcommands.add_parser("compare", help="Compare raw and rendered snapshots for unlocked agent-readiness signals.")
    compare.add_argument("raw", type=Path, help="Raw HTML snapshot path.")
    compare.add_argument("rendered", type=Path, help="Rendered HTML snapshot path.")
    compare.add_argument("--format", choices=("markdown", "json"), default="markdown", help="Output format.")
    compare.add_argument("--output", type=Path, help="Optional output file path.")
    compare.add_argument("--profile", choices=ADAPTER_PROFILES, default="auto", help="Storefront adapter profile for commerce extraction.")

    diff = subcommands.add_parser("diff", help="Compare two AgentShelf scan result files for regressions.")
    diff.add_argument("baseline", type=Path, help="Baseline JSON or JSONL output from `agentshelf scan`.")
    diff.add_argument("current", type=Path, help="Current JSON or JSONL output from `agentshelf scan`.")
    diff.add_argument("--key", choices=("source", "title"), default="source", help="Page field used to match audit runs.")
    diff.add_argument("--format", choices=("markdown", "json"), default="markdown", help="Output format.")
    diff.add_argument("--output", type=Path, help="Optional output file path.")

    audit_run = subcommands.add_parser("audit-run", help="Run a scheduled scan and maintain local previous/current history.")
    audit_run.add_argument("path", help="HTML/text file, directory, or glob to scan.")
    audit_run.add_argument("--batch", action="store_true", help="Allow directory or glob scanning.")
    audit_run.add_argument(
        "--history-dir",
        type=Path,
        default=Path(".agentshelf/runs"),
        help="Directory for current-results.jsonl, previous-results.jsonl, archives, and the diff report.",
    )
    audit_run.add_argument("--report", type=Path, help="Optional Markdown diff report path. Defaults to <history-dir>/audit-diff.md.")
    audit_run.add_argument("--tasks-output", type=Path, help="Optional JSONL task output for coding agents.")
    audit_run.add_argument("--key", choices=("source", "title"), default="source", help="Page field used to match audit runs.")
    audit_run.add_argument("--profile", choices=ADAPTER_PROFILES, default="auto", help="Storefront adapter profile for commerce extraction.")
    audit_run.add_argument("--format", choices=("markdown", "json"), default="markdown", help="Summary output format.")
    audit_run.add_argument("--output", type=Path, help="Optional path for the audit-run summary.")
    audit_run.add_argument("--min-score", type=int, help="Return non-zero when any page scores below this value.")
    audit_run.add_argument(
        "--fail-on",
        choices=("weak", "not_ready"),
        help="Return non-zero when any page is at or below this readiness band.",
    )

    calibrate = subcommands.add_parser("calibrate", help="Summarize real-page calibration hotspots and export anonymized fixture candidates.")
    calibrate.add_argument("target", help="HTML/text file, directory, glob, or scan result file.")
    calibrate.add_argument("--from-results", action="store_true", help="Read target as AgentShelf JSON/JSONL scan output instead of HTML snapshots.")
    calibrate.add_argument("--batch", action="store_true", help="Allow directory or glob scanning when target is HTML snapshots.")
    calibrate.add_argument("--profile", choices=ADAPTER_PROFILES, default="auto", help="Storefront adapter profile for scanning HTML snapshots.")
    calibrate.add_argument("--format", choices=("markdown", "json"), default="markdown", help="Output format.")
    calibrate.add_argument("--output", type=Path, help="Optional output file path.")
    calibrate.add_argument("--export-fixtures", type=Path, help="Optional directory for anonymized local HTML fixture candidates.")
    calibrate.add_argument("--max-fixtures", type=int, default=10, help="Maximum fixture candidates to include or export.")

    evaluate = subcommands.add_parser("evaluate", help="Evaluate scan results against labeled calibration expectations.")
    evaluate.add_argument("results", type=Path, help="AgentShelf JSON or JSONL scan output.")
    evaluate.add_argument("--labels", type=Path, required=True, help="Calibration labels JSON file.")
    evaluate.add_argument("--key", choices=("source", "title"), default="source", help="Default page field used when labels omit source/title.")
    evaluate.add_argument("--format", choices=("markdown", "json"), default="markdown", help="Output format.")
    evaluate.add_argument("--output", type=Path, help="Optional output file path.")
    evaluate.add_argument("--fail-on-regressions", action="store_true", help="Return non-zero when any labeled expectation fails.")

    draft_labels = subcommands.add_parser("draft-labels", help="Create draft calibration labels from a calibration JSON report.")
    draft_labels.add_argument("calibration", type=Path, help="JSON output from `agentshelf calibrate --format json`.")
    draft_labels.add_argument("--output", type=Path, help="Optional label JSON output path.")
    draft_labels.add_argument("--max-pages", type=int, default=10, help="Maximum calibration pages to convert into labels.")
    draft_labels.add_argument("--max-labels", type=int, default=100, help="Maximum draft labels to emit.")
    draft_labels.add_argument("--include-tasks", action="store_true", help="Also draft labels for agent task ids.")

    dashboard = subcommands.add_parser("dashboard", help="Render a calibration report as an operator-friendly dashboard.")
    dashboard.add_argument("calibration", type=Path, help="JSON output from `agentshelf calibrate --format json`.")
    dashboard.add_argument("--format", choices=("html", "markdown"), default="html", help="Dashboard output format.")
    dashboard.add_argument("--output", type=Path, help="Optional dashboard output path.")

    discover = subcommands.add_parser("discover", help="Discover product-like URLs from robots.txt sitemap hints or a sitemap URL.")
    discover.add_argument("--site", help="Storefront root URL. AgentShelf reads robots.txt for Sitemap hints.")
    discover.add_argument("--sitemap", help="Explicit sitemap or sitemap index URL.")
    discover.add_argument("--include", default=r"/products?/|/collections/.+/products?/", help="Regex URL include filter.")
    discover.add_argument("--exclude", help="Optional regex URL exclude filter.")
    discover.add_argument("--limit", type=int, default=100, help="Maximum URLs to emit.")
    discover.add_argument("--timeout", type=float, default=10.0, help="Fetch timeout in seconds.")
    discover.add_argument("--format", choices=("text", "json", "jsonl"), default="text", help="Output format.")
    discover.add_argument("--output", type=Path, help="Optional output file path.")

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
            args.profile = _config_value(config, "profile", args.profile, "auto")
            args.min_score = _coerce_score(args.min_score)
            if args.format not in {"markdown", "json", "jsonl", "sarif"}:
                raise ValueError("Config key `format` must be markdown, json, jsonl, or sarif.")
            if args.fail_on is not None and args.fail_on not in {"weak", "not_ready"}:
                raise ValueError("Config key `fail_on` must be weak or not_ready.")
            if args.profile not in ADAPTER_PROFILES:
                raise ValueError(f"Config key `profile` must be one of: {', '.join(ADAPTER_PROFILES)}.")
            if args.output is not None and not isinstance(args.output, Path):
                args.output = Path(str(args.output))
            paths = _resolve_inputs(args.path, args.batch)
            batch = args.batch or len(paths) > 1
            results = [_load_scan(path, adapter_profile=args.profile) for path in paths]
            rendered = _render_results(results, args.format, batch)
            exit_code = 1 if any(_fails_threshold(item, args.min_score, args.fail_on) for item in results) else 0
        elif args.command == "agent-audit":
            bundle = _load_target(args.target, adapter_profile=args.profile)
            contract = build_agent_contract(bundle, contract=args.contract)
            rendered = json.dumps(contract, indent=2) + "\n"
            exit_code = 1 if args.fail_on_blockers and any(issue["severity"] == "high" for issue in contract["blocking_issues"]) else 0
        elif args.command == "agent-tasks":
            paths = _resolve_inputs(args.path, args.batch)
            if len(paths) > 1 and not args.batch:
                raise ValueError("Multiple inputs found. Re-run with --batch.")
            results = [_load_scan(path, adapter_profile=args.profile) for path in paths]
            rendered = _render_agent_tasks(results)
            exit_code = 0
        elif args.command == "compare":
            raw_bundle = _load_scan_as(args.raw, "raw", adapter_profile=args.profile)
            rendered_bundle = _load_scan_as(args.rendered, "rendered", adapter_profile=args.profile)
            payload = _build_compare(raw_bundle, rendered_bundle)
            rendered = json.dumps(payload, indent=2) + "\n" if args.format == "json" else _render_compare_markdown(payload)
            exit_code = 0
        elif args.command == "diff":
            baseline_rows = _load_scan_results(args.baseline)
            current_rows = _load_scan_results(args.current)
            payload = _build_audit_diff(baseline_rows, current_rows, key=args.key)
            rendered = json.dumps(payload, indent=2) + "\n" if args.format == "json" else _render_audit_diff_markdown(payload)
            exit_code = 0
        elif args.command == "audit-run":
            args.min_score = _coerce_score(args.min_score)
            payload, markdown = _build_audit_run(
                target=args.path,
                batch=args.batch,
                history_dir=args.history_dir,
                report_path=args.report,
                tasks_path=args.tasks_output,
                min_score=args.min_score,
                fail_on=args.fail_on,
                key=args.key,
                adapter_profile=args.profile,
            )
            rendered = json.dumps(payload, indent=2) + "\n" if args.format == "json" else markdown
            exit_code = 1 if payload["threshold_failed"] else 0
        elif args.command == "calibrate":
            if args.max_fixtures < 1:
                raise ValueError("--max-fixtures must be at least 1.")
            if args.from_results:
                results = _load_scan_results(Path(args.target))
                source_label = str(Path(args.target))
            else:
                paths = _resolve_inputs(args.target, args.batch)
                if len(paths) > 1 and not args.batch:
                    raise ValueError("Multiple inputs found. Re-run with --batch.")
                results = [_load_scan(path, adapter_profile=args.profile) for path in paths]
                source_label = args.target
            payload = _build_calibration(results, source_label=source_label, max_fixtures=args.max_fixtures)
            if args.export_fixtures:
                payload["fixture_export"] = _export_calibration_fixtures(payload, args.export_fixtures)
            rendered = json.dumps(payload, indent=2) + "\n" if args.format == "json" else _render_calibration_markdown(payload)
            exit_code = 0
        elif args.command == "evaluate":
            results = _load_scan_results(args.results)
            labels = _load_calibration_labels(args.labels)
            payload = _build_calibration_evaluation(results, labels, key=args.key)
            rendered = json.dumps(payload, indent=2) + "\n" if args.format == "json" else _render_calibration_evaluation_markdown(payload)
            exit_code = 1 if args.fail_on_regressions and payload["summary"]["failed"] else 0
        elif args.command == "draft-labels":
            if args.max_pages < 1:
                raise ValueError("--max-pages must be at least 1.")
            if args.max_labels < 1:
                raise ValueError("--max-labels must be at least 1.")
            calibration = _load_calibration_report(args.calibration)
            payload = _build_draft_labels(
                calibration,
                max_pages=args.max_pages,
                max_labels=args.max_labels,
                include_tasks=args.include_tasks,
            )
            rendered = json.dumps(payload, indent=2) + "\n"
            exit_code = 0
        elif args.command == "dashboard":
            calibration = _load_calibration_report(args.calibration)
            rendered = (
                _render_dashboard_html(calibration)
                if args.format == "html"
                else _render_dashboard_markdown(calibration)
            )
            exit_code = 0
        elif args.command == "discover":
            payload = _discover_urls(
                site=args.site,
                sitemap=args.sitemap,
                timeout=args.timeout,
                include=args.include,
                exclude=args.exclude,
                limit=args.limit,
            )
            rendered = _render_discovery(payload, args.format)
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
