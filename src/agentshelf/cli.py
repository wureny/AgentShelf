from __future__ import annotations

import argparse
import glob
import hashlib
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
USER_AGENT = "AgentShelf/0.13 (+https://github.com/wureny/AgentShelf)"
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
