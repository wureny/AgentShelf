from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import html
import json
import re
import shutil
import sys
from importlib import resources
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from agentshelf.engine import ADAPTER_PROFILES, build_agent_contract, parse_input, render_markdown, scan_readiness
from agentshelf.geo import GeoSkillConfig, build_geo_audit, render_geo_json, render_geo_tasks_json, render_geo_tasks_jsonl


SUPPORTED_SUFFIXES = {".html", ".htm", ".txt"}
BAND_ORDER = {"not_ready": 0, "weak": 1, "workable": 2, "strong": 3}
DEFAULT_CONFIG = ".agentshelf.json"
USER_AGENT = "AgentShelf/0.30 (+https://github.com/wureny/AgentShelf)"
FIXTURE_PLATFORMS = ("shopify", "woocommerce", "headless")
FIXTURE_INPUT_FORMATS = ("auto", "agentshelf", "shopify", "woocommerce", "headless")
RENDER_EXTRA_MESSAGE = (
    "Rendered snapshots require the optional Playwright extra. "
    "Install it with `python3 -m pip install 'agentshelf[render]'` and then run "
    "`python3 -m playwright install chromium`."
)
CONTRACT_SCHEMA_FILES = {
    "agentshelf.geo_audit.v0": "schemas/agentshelf.geo_audit.v0.schema.json",
    "agentshelf.geo_task.v0": "schemas/agentshelf.geo_task.v0.schema.json",
    "agentshelf.geo_tasks.v0": "schemas/agentshelf.geo_task.v0.schema.json",
}
PACKAGED_GEO_SKILL_FILES = (
    "SKILL.md",
    "agents/openai.yaml",
    "references/agent-loop-example.md",
    "references/task-contract.md",
)
MERCHANT_REPO_TEMPLATE_FILES = (
    ("agentshelf.config.json", ".agentshelf.json"),
    ("workflows/agentshelf-geo.yml", ".github/workflows/agentshelf-geo.yml"),
    ("snapshots/agentshelf-demo-product.html", "snapshots/agentshelf-demo-product.html"),
    ("docs/agentshelf-onboarding.md", "docs/agentshelf-onboarding.md"),
)


def _packaged_geo_skill_root():
    return resources.files("agentshelf").joinpath("skills", "agentshelf-geo")


def _read_packaged_geo_skill_file(relative_path: str) -> str:
    path = _packaged_geo_skill_root().joinpath(relative_path)
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            "Bundled agentshelf-geo skill asset is missing from the installed package. "
            "Reinstall AgentShelf from a complete source checkout or wheel."
        ) from exc


def _packaged_merchant_template_root():
    return resources.files("agentshelf").joinpath("templates", "merchant-repo")


def _read_packaged_merchant_template_file(relative_path: str) -> str:
    path = _packaged_merchant_template_root().joinpath(relative_path)
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            "Bundled merchant repository template is missing from the installed package. "
            "Reinstall AgentShelf from a complete source checkout or wheel."
        ) from exc


def _build_skill_info() -> dict:
    skill_text = _read_packaged_geo_skill_file("SKILL.md")
    metadata_text = _read_packaged_geo_skill_file("agents/openai.yaml")
    agent_loop_text = _read_packaged_geo_skill_file("references/agent-loop-example.md")
    contract_text = _read_packaged_geo_skill_file("references/task-contract.md")
    issues: list[str] = []
    required_skill_snippets = (
        "name: agentshelf-geo",
        "agentshelf geo-run",
        "agentshelf dogfood",
        "agentshelf geo-audit",
        "agentshelf geo-tasks",
        "agentshelf validate-contract",
        "Do not fabricate reviews",
    )
    for snippet in required_skill_snippets:
        if snippet not in skill_text:
            issues.append(f"SKILL.md missing required snippet: {snippet}")
    if "$agentshelf-geo" not in metadata_text:
        issues.append("agents/openai.yaml missing $agentshelf-geo invocation hint.")
    if "examples/codex_agent_loop_after.html" not in agent_loop_text:
        issues.append("references/agent-loop-example.md missing Codex implementation loop example.")
    if "agentshelf.geo_task.v0" not in contract_text:
        issues.append("references/task-contract.md missing agentshelf.geo_task.v0 contract reference.")
    return {
        "contract": "agentshelf.skill_info.v0",
        "skill": "agentshelf-geo",
        "description": "Coding-agent workflow for AI-readable commerce GEO audits and remediation.",
        "bundled_files": list(PACKAGED_GEO_SKILL_FILES),
        "valid": not issues,
        "issues": issues,
        "default_export_command": "agentshelf export-skill --output-dir .codex/skills",
        "primary_workflow_command": "agentshelf geo-run <page-or-url> --brand <brand> --category <category> --output-dir agentshelf-geo-run",
        "safe_url_workflow_command": "agentshelf dogfood <url> --brand <brand> --category <category> --output-dir agentshelf-dogfood",
    }


def _render_skill_info(payload: dict, output_format: str) -> str:
    if output_format == "json":
        return json.dumps(payload, indent=2) + "\n"
    status = "valid" if payload["valid"] else "invalid"
    lines = [
        "# AgentShelf GEO Skill",
        "",
        f"- Skill: {payload['skill']}",
        f"- Status: {status}",
        f"- Purpose: {payload['description']}",
        f"- Export command: `{payload['default_export_command']}`",
        f"- Primary workflow: `{payload['primary_workflow_command']}`",
        f"- Safe URL workflow: `{payload['safe_url_workflow_command']}`",
        "- Bundled files:",
    ]
    lines.extend(f"  - {filename}" for filename in payload["bundled_files"])
    if payload["issues"]:
        lines.extend(["", "## Issues"])
        lines.extend(f"- {issue}" for issue in payload["issues"])
    return "\n".join(lines) + "\n"


def _render_merchant_template(text: str, *, brand: str, category: str, vertical: str) -> str:
    return (
        text.replace("{{BRAND}}", brand)
        .replace("{{CATEGORY}}", category)
        .replace("{{VERTICAL}}", vertical)
    )


def _init_merchant_repo(
    output_dir: Path,
    *,
    brand: str,
    category: str,
    vertical: str,
    include_skill: bool = True,
    force: bool = False,
) -> dict:
    destination = output_dir
    written: list[str] = []
    skipped: list[str] = []
    conflicts: list[str] = []
    for source, relative_target in MERCHANT_REPO_TEMPLATE_FILES:
        text = _render_merchant_template(
            _read_packaged_merchant_template_file(source),
            brand=brand,
            category=category,
            vertical=vertical,
        )
        target = destination / relative_target
        if target.exists() and target.read_text(encoding="utf-8") != text and not force:
            conflicts.append(str(target))
            continue
        if target.exists() and target.read_text(encoding="utf-8") == text:
            skipped.append(str(target))
            continue
        _write_text_atomic(target, text)
        written.append(str(target))
    skill_payload = None
    if include_skill:
        skill_payload = _export_geo_skill(destination / ".codex" / "skills", force=force)
        written.extend(skill_payload["written"])
        skipped.extend(skill_payload["skipped"])
        conflicts.extend(skill_payload["conflicts"])
    return {
        "contract": "agentshelf.merchant_repo_init.v0",
        "destination": str(destination),
        "brand": brand,
        "category": category,
        "vertical": vertical,
        "include_skill": include_skill,
        "template_files": [target for _, target in MERCHANT_REPO_TEMPLATE_FILES],
        "skill_export": skill_payload,
        "written": written,
        "skipped": skipped,
        "conflicts": conflicts,
        "valid": not conflicts,
        "next_steps": [
            "Replace snapshots/agentshelf-demo-product.html with generated storefront HTML before enforcing a production PR gate.",
            "Run `agentshelf geo-run snapshots/agentshelf-demo-product.html --brand <brand> --category <category> --output-dir artifacts/agentshelf/geo-run`.",
            "Run `agentshelf scan snapshots/agentshelf-demo-product.html --config .agentshelf.json`.",
            "Ask Codex to use `$agentshelf-geo` when implementation work should follow the exported AgentShelf task queue.",
        ],
    }


def _render_merchant_repo_init(payload: dict, output_format: str) -> str:
    if output_format == "json":
        return json.dumps(payload, indent=2) + "\n"
    status = "initialized" if payload["valid"] else "conflict"
    lines = [
        "# AgentShelf Merchant Repo Init",
        "",
        f"- Status: {status}",
        f"- Destination: {payload['destination']}",
        f"- Brand: {payload['brand']}",
        f"- Category: {payload['category']}",
        f"- Vertical: {payload['vertical']}",
        f"- Written: {len(payload['written'])}",
        f"- Unchanged: {len(payload['skipped'])}",
    ]
    if payload["conflicts"]:
        lines.extend(["", "## Conflicts"])
        lines.extend(f"- {path}" for path in payload["conflicts"])
        lines.append("")
        lines.append("Re-run with `--force` only after reviewing these files.")
    lines.extend(["", "## Next Steps"])
    lines.extend(f"- {item}" for item in payload["next_steps"])
    return "\n".join(lines) + "\n"


def _export_geo_skill(output_dir: Path, *, force: bool = False) -> dict:
    destination = output_dir / "agentshelf-geo"
    written: list[str] = []
    skipped: list[str] = []
    conflicts: list[str] = []
    for relative_path in PACKAGED_GEO_SKILL_FILES:
        text = _read_packaged_geo_skill_file(relative_path)
        target = destination / relative_path
        if target.exists() and target.read_text(encoding="utf-8") != text and not force:
            conflicts.append(str(target))
            continue
        if target.exists() and target.read_text(encoding="utf-8") == text:
            skipped.append(str(target))
            continue
        _write_text_atomic(target, text)
        written.append(str(target))
    return {
        "contract": "agentshelf.skill_export.v0",
        "skill": "agentshelf-geo",
        "destination": str(destination),
        "written": written,
        "skipped": skipped,
        "conflicts": conflicts,
        "valid": not conflicts,
        "next_steps": [
            "Commit the exported skill directory if this repository should carry the AgentShelf workflow.",
            "Run `agentshelf skill-info` to check the installed package assets.",
            "Run `agentshelf geo-run <page-or-url> --brand <brand> --category <category>` before editing commerce templates.",
        ],
    }


def _render_skill_export(payload: dict, output_format: str) -> str:
    if output_format == "json":
        return json.dumps(payload, indent=2) + "\n"
    status = "exported" if payload["valid"] else "conflict"
    lines = [
        "# AgentShelf Skill Export",
        "",
        f"- Status: {status}",
        f"- Skill: {payload['skill']}",
        f"- Destination: {payload['destination']}",
        f"- Written: {len(payload['written'])}",
        f"- Unchanged: {len(payload['skipped'])}",
    ]
    if payload["conflicts"]:
        lines.extend(["", "## Conflicts"])
        lines.extend(f"- {path}" for path in payload["conflicts"])
        lines.append("")
        lines.append("Re-run with `--force` to overwrite conflicting skill files.")
    else:
        lines.extend(["", "## Next Steps"])
        lines.extend(f"- {step}" for step in payload["next_steps"])
    return "\n".join(lines) + "\n"


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


def _split_cli_values(values: list[str] | None) -> list[str]:
    if not values:
        return []
    items: list[str] = []
    for value in values:
        for part in value.split(","):
            stripped = part.strip()
            if stripped:
                items.append(stripped)
    return items


def _build_geo_config_from_args(target: str, args: argparse.Namespace) -> GeoSkillConfig:
    return GeoSkillConfig(
        targetUrl=target,
        brandName=args.brand_name,
        storeName=args.store_name,
        category=args.category,
        market=_split_cli_values(args.market),
        language=args.language,
        competitors=_split_cli_values(args.competitor),
        personas=_split_cli_values(args.persona),
        useCases=_split_cli_values(args.use_case),
        keyProducts=_split_cli_values(args.key_product),
        maxPages=args.max_pages,
        includePromptPanel=not args.no_prompt_panel,
        includePatchSuggestions=not args.no_patches,
        vertical=args.vertical,
        outputFormat=getattr(args, "format", "json"),
    )


def _load_geo_target(target: str, timeout: float = 10.0) -> tuple[str, dict]:
    if _is_url(target):
        metadata = {
            "source_type": "url",
            "robots_text": None,
            "robots_status": "not_checked",
            "sitemap_status": "not_checked",
            "llms_status": "not_checked",
            "fetch_warnings": [],
        }
        html = _fetch_url(target, timeout=timeout)
        parsed = urlparse(target)
        base = f"{parsed.scheme}://{parsed.netloc}"
        try:
            robots_text = _fetch_url(f"{base}/robots.txt", timeout=timeout)
            metadata["robots_text"] = robots_text
            metadata["robots_status"] = "found"
            metadata["sitemap_status"] = "found" if _sitemap_urls_from_robots(robots_text) else "not_declared_in_robots"
        except (OSError, ValueError) as exc:
            metadata["robots_status"] = "missing_or_unavailable"
            metadata["fetch_warnings"].append(f"robots.txt unavailable: {exc}")
        if metadata["sitemap_status"] != "found":
            try:
                sitemap_text = _fetch_url(f"{base}/sitemap.xml", timeout=timeout)
                metadata["sitemap_status"] = "found" if "<urlset" in sitemap_text or "<sitemapindex" in sitemap_text else "unexpected_response"
            except (OSError, ValueError) as exc:
                metadata["sitemap_status"] = "missing_or_unavailable"
                metadata["fetch_warnings"].append(f"sitemap.xml unavailable: {exc}")
        try:
            llms_text = _fetch_url(f"{base}/llms.txt", timeout=timeout)
            metadata["llms_status"] = "found" if llms_text.strip() else "empty"
        except (OSError, ValueError):
            metadata["llms_status"] = "missing_or_unavailable"
        return html, metadata

    path = Path(target)
    return path.read_text(encoding="utf-8"), {
        "source_type": "file",
        "robots_text": None,
        "robots_status": "not_checked",
        "sitemap_status": "not_checked",
        "llms_status": "not_checked",
        "fetch_warnings": [],
    }


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


def _validate_contract_file(path: Path, requested_contract: str = "auto") -> dict:
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    detected = "unknown"
    item_count = 0

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None

    if payload is not None:
        if not isinstance(payload, dict):
            errors.append("$: expected a JSON object or JSONL task rows.")
        else:
            detected = _detect_contract(payload)
            if requested_contract != "auto" and detected != requested_contract:
                errors.append(f"$.contract: expected {requested_contract}, detected {detected}.")
            if detected == "agentshelf.geo_audit.v0":
                errors.extend(_validate_geo_audit_payload(payload))
                item_count = 1
            elif detected == "agentshelf.geo_task.v0":
                errors.extend(_validate_geo_task_row(payload, "$"))
                item_count = 1
            elif detected == "agentshelf.geo_tasks.v0":
                errors.extend(_validate_geo_tasks_payload(payload))
                item_count = len(payload.get("tasks") or []) if isinstance(payload.get("tasks"), list) else 0
            else:
                errors.append("$.contract: unsupported or missing AgentShelf contract.")
    else:
        rows = []
        for index, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                errors.append(f"line {index}: invalid JSON: {exc.msg}.")
                continue
            rows.append((index, row))

        if not rows:
            errors.append("$: empty contract file.")
        detected = "agentshelf.geo_task.v0" if rows else "unknown"
        if requested_contract not in {"auto", "agentshelf.geo_task.v0"}:
            errors.append(f"$.contract: JSONL input only supports agentshelf.geo_task.v0 rows, not {requested_contract}.")
        for index, row in rows:
            if not isinstance(row, dict):
                errors.append(f"line {index}: expected a JSON object.")
                continue
            row_contract = _detect_contract(row)
            if row_contract != "agentshelf.geo_task.v0":
                errors.append(f"line {index}: expected agentshelf.geo_task.v0, detected {row_contract}.")
                continue
            errors.extend(_validate_geo_task_row(row, f"line {index}"))
        item_count = len(rows)

    schema_files = sorted(
        {
            CONTRACT_SCHEMA_FILES[contract]
            for contract in (detected, requested_contract)
            if contract in CONTRACT_SCHEMA_FILES
        }
    )
    return {
        "contract": detected,
        "path": str(path),
        "valid": not errors,
        "item_count": item_count,
        "errors": errors,
        "schemas": schema_files,
    }


def _detect_contract(payload: dict) -> str:
    if payload.get("contract") in CONTRACT_SCHEMA_FILES:
        return str(payload["contract"])
    metadata = payload.get("rawMetadata")
    if isinstance(metadata, dict) and metadata.get("contract") in CONTRACT_SCHEMA_FILES:
        return str(metadata["contract"])
    return "unknown"


def _validate_geo_audit_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    required = [
        "targetUrl",
        "generatedAt",
        "storeProfile",
        "pages",
        "overallScore",
        "categoryScores",
        "issues",
        "opportunities",
        "promptPanel",
        "patchSuggestions",
        "reportMarkdown",
        "rawMetadata",
    ]
    errors.extend(_required_keys(payload, required, "$"))
    metadata = payload.get("rawMetadata")
    if not isinstance(metadata, dict):
        errors.append("$.rawMetadata: expected object.")
    elif metadata.get("contract") != "agentshelf.geo_audit.v0":
        errors.append("$.rawMetadata.contract: expected agentshelf.geo_audit.v0.")
    if not isinstance(payload.get("overallScore"), int) or not 0 <= payload.get("overallScore", -1) <= 100:
        errors.append("$.overallScore: expected integer between 0 and 100.")
    categories = payload.get("categoryScores")
    if not isinstance(categories, dict):
        errors.append("$.categoryScores: expected object.")
    else:
        for category in (
            "crawlability",
            "indexability",
            "structured_data",
            "content_extractability",
            "entity_consistency",
            "commerce_attributes",
            "trust",
            "ai_intent_coverage",
            "external_authority",
            "gtm",
        ):
            value = categories.get(category)
            if not isinstance(value, int) or not 0 <= value <= 100:
                errors.append(f"$.categoryScores.{category}: expected integer between 0 and 100.")
    pages = payload.get("pages")
    if not isinstance(pages, list) or not pages:
        errors.append("$.pages: expected non-empty list.")
    issues = payload.get("issues")
    if not isinstance(issues, list):
        errors.append("$.issues: expected list.")
    else:
        for index, issue in enumerate(issues):
            if not isinstance(issue, dict):
                errors.append(f"$.issues[{index}]: expected object.")
                continue
            errors.extend(
                _required_keys(
                    issue,
                    ["id", "severity", "category", "title", "description", "whyItMatters", "recommendation", "confidence"],
                    f"$.issues[{index}]",
                )
            )
    for key in ("opportunities", "promptPanel", "patchSuggestions"):
        if not isinstance(payload.get(key), list):
            errors.append(f"$.{key}: expected list.")
    return errors


def _validate_geo_tasks_payload(payload: dict) -> list[str]:
    errors = _required_keys(payload, ["contract", "source", "task_count", "tasks"], "$")
    if payload.get("contract") != "agentshelf.geo_tasks.v0":
        errors.append("$.contract: expected agentshelf.geo_tasks.v0.")
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        errors.append("$.tasks: expected list.")
        return errors
    if payload.get("task_count") != len(tasks):
        errors.append("$.task_count: expected to equal len(tasks).")
    for index, row in enumerate(tasks):
        if not isinstance(row, dict):
            errors.append(f"$.tasks[{index}]: expected object.")
            continue
        errors.extend(_validate_geo_task_row(row, f"$.tasks[{index}]"))
    return errors


def _validate_geo_task_row(row: dict, prefix: str) -> list[str]:
    errors = _required_keys(row, ["contract", "source", "page_url", "task"], prefix)
    if row.get("contract") != "agentshelf.geo_task.v0":
        errors.append(f"{prefix}.contract: expected agentshelf.geo_task.v0.")
    task = row.get("task")
    if not isinstance(task, dict):
        errors.append(f"{prefix}.task: expected object.")
        return errors
    errors.extend(
        _required_keys(
            task,
            ["id", "title", "priority", "type", "reason", "files_or_page_area", "acceptance_check", "verification_command"],
            f"{prefix}.task",
        )
    )
    if task.get("priority") not in {"critical", "high", "medium", "low"}:
        errors.append(f"{prefix}.task.priority: expected critical, high, medium, or low.")
    if task.get("type") not in {"patch", "issue"}:
        errors.append(f"{prefix}.task.type: expected patch or issue.")
    if task.get("type") == "patch" and not task.get("patch_type"):
        errors.append(f"{prefix}.task.patch_type: required when task.type is patch.")
    if task.get("type") == "issue" and not task.get("category"):
        errors.append(f"{prefix}.task.category: required when task.type is issue.")
    for key in ("reason", "files_or_page_area", "acceptance_check", "verification_command"):
        if not isinstance(task.get(key), str) or not task.get(key, "").strip():
            errors.append(f"{prefix}.task.{key}: expected non-empty string.")
    return errors


def _required_keys(payload: dict, keys: list[str], prefix: str) -> list[str]:
    return [f"{prefix}.{key}: missing required field." for key in keys if key not in payload]


def _render_contract_validation(payload: dict, output_format: str) -> str:
    if output_format == "json":
        return json.dumps(payload, indent=2) + "\n"
    status = "valid" if payload["valid"] else "invalid"
    lines = [
        "# AgentShelf Contract Validation",
        "",
        f"- Status: {status}",
        f"- Contract: {payload['contract']}",
        f"- Path: {payload['path']}",
        f"- Items: {payload['item_count']}",
    ]
    if payload["schemas"]:
        lines.append(f"- Schemas: {', '.join(payload['schemas'])}")
    if payload["errors"]:
        lines.extend(["", "## Errors"])
        lines.extend(f"- {error}" for error in payload["errors"])
    return "\n".join(lines) + "\n"


def _build_geo_run_summary(
    *,
    target: str,
    output_dir: Path,
    geo_report: dict,
    task_validation: dict,
    report_validation: dict,
    scan_bundle: dict | None,
) -> dict:
    summary = {
        "contract": "agentshelf.geo_run.v0",
        "target": target,
        "output_dir": str(output_dir),
        "geo_report": str(output_dir / "geo-report.json"),
        "geo_report_markdown": str(output_dir / "geo-report.md"),
        "geo_tasks": str(output_dir / "geo-tasks.jsonl"),
        "geo_report_validation": report_validation,
        "geo_tasks_validation": task_validation,
        "overallScore": geo_report.get("overallScore"),
        "issue_count": len(geo_report.get("issues") or []),
        "high_impact_issue_count": len(
            [
                issue
                for issue in geo_report.get("issues") or []
                if isinstance(issue, dict) and issue.get("severity") in {"critical", "high"}
            ]
        ),
        "task_count": task_validation.get("item_count", 0),
        "top_task_ids": [],
        "scan": None,
        "next_actions": [
            f"Open {output_dir / 'geo-tasks.jsonl'} and implement high-priority tasks first.",
            "Do not fabricate reviews, ratings, press, stock, price, shipping, return, or external-authority claims.",
            "Re-run `agentshelf geo-run ...` after edits and compare issue/task counts.",
        ],
    }
    task_rows = _load_geo_task_rows(output_dir / "geo-tasks.jsonl")
    summary["top_task_ids"] = [row["task"]["id"] for row in task_rows[:5] if isinstance(row.get("task"), dict)]
    if scan_bundle:
        summary["scan"] = {
            "score": scan_bundle["score"],
            "band": scan_bundle["band"],
            "top_fixes": scan_bundle.get("top_fixes", [])[:5],
            "report": str(output_dir / "scan-report.md"),
        }
    return summary


def _load_geo_task_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            row = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _render_geo_run_summary(payload: dict, output_format: str) -> str:
    if output_format == "json":
        return json.dumps(payload, indent=2) + "\n"
    lines = [
        "# AgentShelf GEO Run",
        "",
        "## Summary",
        f"- Target: {payload['target']}",
        f"- Output directory: `{payload['output_dir']}`",
        f"- GEO score: {payload['overallScore']}/100",
        f"- Issues: {payload['issue_count']} ({payload['high_impact_issue_count']} high-impact)",
        f"- Tasks: {payload['task_count']}",
        f"- Report contract valid: {payload['geo_report_validation']['valid']}",
        f"- Task contract valid: {payload['geo_tasks_validation']['valid']}",
    ]
    if payload.get("scan"):
        lines.extend(
            [
                f"- Scan score: {payload['scan']['score']}/100",
                f"- Scan band: {payload['scan']['band']}",
            ]
        )
    lines.extend(["", "## Artifacts"])
    for key in ("geo_report", "geo_report_markdown", "geo_tasks"):
        lines.append(f"- {key}: `{payload[key]}`")
    if payload.get("scan"):
        lines.append(f"- scan_report: `{payload['scan']['report']}`")
    lines.extend(["", "## Top Task IDs"])
    if payload["top_task_ids"]:
        lines.extend(f"- `{task_id}`" for task_id in payload["top_task_ids"])
    else:
        lines.append("- None")
    lines.extend(["", "## Next Actions"])
    lines.extend(f"- {action}" for action in payload["next_actions"])
    return "\n".join(lines) + "\n"


def _build_dogfood_summary(
    *,
    url: str,
    output_dir: Path,
    geo_report: dict,
    task_validation: dict,
    report_validation: dict,
    scan_bundle: dict,
    fetch_metadata: dict,
) -> dict:
    summary = _build_geo_run_summary(
        target=url,
        output_dir=output_dir,
        geo_report=geo_report,
        task_validation=task_validation,
        report_validation=report_validation,
        scan_bundle=scan_bundle,
    )
    summary["contract"] = "agentshelf.dogfood_run.v0"
    summary["url"] = url
    summary["raw_html_persisted"] = False
    summary["source_policy"] = "Fetched HTML was used in memory only. Do not commit third-party raw HTML unless you own the page or have permission."
    summary["fetch_metadata"] = {
        "source_type": fetch_metadata.get("source_type"),
        "robots_status": fetch_metadata.get("robots_status"),
        "sitemap_status": fetch_metadata.get("sitemap_status"),
        "llms_status": fetch_metadata.get("llms_status"),
        "fetch_warnings": fetch_metadata.get("fetch_warnings", []),
    }
    summary["dogfood_notes"] = str(output_dir / "dogfood-notes.md")
    summary["next_actions"] = [
        f"Review {output_dir / 'dogfood-notes.md'} and {output_dir / 'geo-tasks.jsonl'} before changing rules.",
        "If a finding looks wrong, create an anonymized or synthetic fixture; do not commit third-party raw HTML.",
        "Promote confirmed false positives or true positives into calibration labels before tightening CI gates.",
    ]
    return summary


def _render_dogfood_notes(summary: dict) -> str:
    scan = summary.get("scan") or {}
    lines = [
        "# AgentShelf Real-Page Dogfood Notes",
        "",
        "## Source Policy",
        f"- URL: {summary['url']}",
        f"- Raw HTML persisted: {str(summary['raw_html_persisted']).lower()}",
        f"- Policy: {summary['source_policy']}",
        "",
        "## Generated Artifacts",
        f"- GEO report: `{summary['geo_report']}`",
        f"- GEO Markdown: `{summary['geo_report_markdown']}`",
        f"- GEO tasks: `{summary['geo_tasks']}`",
        f"- GEO report validation: valid={str(summary['geo_report_validation']['valid']).lower()}",
        f"- GEO tasks validation: valid={str(summary['geo_tasks_validation']['valid']).lower()}",
        f"- Scan report: `{scan.get('report', 'not generated')}`",
        "",
        "## Snapshot-Level Findings",
        f"- GEO score: {summary['overallScore']}",
        f"- GEO issues: {summary['issue_count']}",
        f"- High-impact GEO issues: {summary['high_impact_issue_count']}",
        f"- Task count: {summary['task_count']}",
    ]
    if scan:
        lines.extend(
            [
                f"- Product readiness score: {scan['score']}",
                f"- Product readiness band: {scan['band']}",
            ]
        )
    lines.extend(["", "## Top Task IDs"])
    if summary["top_task_ids"]:
        lines.extend(f"- `{task_id}`" for task_id in summary["top_task_ids"])
    else:
        lines.append("- None")
    lines.extend(["", "## Calibration Follow-Up"])
    lines.extend(f"- {action}" for action in summary["next_actions"])
    return "\n".join(lines) + "\n"


def _slugify(value: str, fallback: str = "product") -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-")
    slug = re.sub(r"-+", "-", slug)
    return slug[:80] or fallback


def _load_fixture_products(path: Path, input_format: str = "auto") -> tuple[list[dict], str]:
    requested_format = input_format.lower()
    if requested_format not in FIXTURE_INPUT_FORMATS:
        raise ValueError(f"Unsupported fixture input format: {input_format}.")
    detected_format = _detect_fixture_input_format(path, requested_format)
    if detected_format == "woocommerce":
        raw_products = _load_woocommerce_products(path)
    else:
        raw_products = _load_json_fixture_products(path, detected_format)
    return [_normalize_fixture_product(item, index) for index, item in enumerate(raw_products, start=1)], detected_format


def _detect_fixture_input_format(path: Path, requested_format: str) -> str:
    if requested_format != "auto":
        return requested_format
    if path.suffix.lower() == ".csv":
        return "woocommerce"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid product export JSON {path}: {exc.msg}.") from exc
    if isinstance(payload, dict):
        if "shopify_product_export" in payload or "product" in payload and _looks_like_shopify_product(payload["product"]):
            return "shopify"
        if "data" in payload or "catalog" in payload or "items" in payload:
            return "headless"
        products = payload.get("products")
        if isinstance(products, list) and any(_looks_like_shopify_product(item) for item in products if isinstance(item, dict)):
            return "shopify"
    return "agentshelf"


def _load_json_fixture_products(path: Path, input_format: str) -> list[dict]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid product export JSON {path}: {exc.msg}.") from exc
    if input_format == "shopify":
        products = _extract_shopify_products(payload)
    elif input_format == "headless":
        products = _extract_headless_products(payload)
    else:
        products = payload.get("products") if isinstance(payload, dict) else payload
    if not isinstance(products, list) or not products:
        raise ValueError("Product export must be a non-empty JSON list or an object with a non-empty `products` list.")
    return products


def _normalize_fixture_product(item: dict, index: int) -> dict:
    if not isinstance(item, dict):
        raise ValueError(f"Product #{index} must be a JSON object.")
    title = str(item.get("title") or item.get("name") or "").strip()
    if not title:
        raise ValueError(f"Product #{index} is missing `title`.")
    product = dict(item)
    product["title"] = title
    product["handle"] = _slugify(str(product.get("handle") or product.get("slug") or title), fallback=f"product-{index}")
    product["currency"] = str(product.get("currency") or product.get("currencyCode") or "USD").upper()
    product["price"] = str(
        _price_value(product.get("price"))
        or _price_value(product.get("regular_price"))
        or _price_value(product.get("sale_price"))
        or _first_variant_value(product, "price")
        or "0.00"
    )
    product["availability"] = str(product.get("availability") or _availability_from_variants(product) or "in_stock")
    product["variants"] = _normalize_variants(product)
    product["_source_fields"] = _source_field_flags(item)
    return product


def _source_field_flags(item: dict) -> dict[str, bool]:
    variants = item.get("variants")
    has_variants = isinstance(variants, list) and bool(variants)
    return {
        "title": bool(item.get("title") or item.get("name")),
        "price": any(item.get(key) not in (None, "") for key in ("price", "regular_price", "sale_price", "pricing", "priceRange"))
        or _first_variant_value(item, "price") not in (None, ""),
        "currency": any(item.get(key) not in (None, "") for key in ("currency", "currencyCode")),
        "availability": any(item.get(key) not in (None, "") for key in ("availability", "available", "availableForSale")),
        "variants": has_variants,
        "shipping": any(item.get(key) not in (None, "") for key in ("shipping", "shippingPolicy")),
        "returns": any(item.get(key) not in (None, "") for key in ("returns", "returnPolicy")),
        "specs": bool(item.get("specs") or item.get("metafields")),
    }


def _looks_like_shopify_product(item: object) -> bool:
    return isinstance(item, dict) and (
        "body_html" in item
        or "vendor" in item
        or any(isinstance(variant, dict) and any(key.startswith("option") for key in variant) for variant in item.get("variants", []))
    )


def _extract_shopify_products(payload: object) -> list[dict]:
    if isinstance(payload, dict) and isinstance(payload.get("product"), dict):
        raw_products = [payload["product"]]
    elif isinstance(payload, dict) and isinstance(payload.get("products"), list):
        raw_products = payload["products"]
    elif isinstance(payload, list):
        raw_products = payload
    else:
        raise ValueError("Shopify input must be a product object, a {product: ...} object, a {products: [...]} object, or a list.")
    normalized = []
    for index, item in enumerate(raw_products, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Shopify product #{index} must be a JSON object.")
        variants = []
        for variant_index, variant in enumerate(item.get("variants") or [], start=1):
            if not isinstance(variant, dict):
                continue
            options = {}
            for option_index in range(1, 4):
                value = variant.get(f"option{option_index}")
                if value not in (None, ""):
                    option_name = _shopify_option_name(item, option_index)
                    options[option_name] = value
            variants.append(
                {
                    "id": variant.get("id") or f"{item.get('handle') or item.get('title')}-{variant_index}",
                    "title": variant.get("title") or " / ".join(str(value) for value in options.values()) or f"Variant {variant_index}",
                    "sku": variant.get("sku") or f"{item.get('handle') or 'product'}-{variant_index}",
                    "price": _price_value(variant.get("price")) or "0.00",
                    "available": _shopify_variant_available(variant),
                    "options": options,
                }
            )
        normalized.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "handle": item.get("handle"),
                "brand": item.get("vendor"),
                "seller": item.get("vendor"),
                "description": _strip_html(str(item.get("body_html") or item.get("description") or "")),
                "price": _first_variant_price(variants) or "0.00",
                "currency": item.get("currency") or "USD",
                "availability": "in_stock" if any(variant["available"] for variant in variants) else "out_of_stock",
                "variants": variants,
                "specs": item.get("metafields") if isinstance(item.get("metafields"), dict) else {},
                "metafields": item.get("metafields") if isinstance(item.get("metafields"), dict) else {},
                "shipping": item.get("shipping") or "Ships in 3-5 business days.",
                "returns": item.get("returns") or "30-day returns accepted for unused items.",
                "_source_fields": {
                    "title": bool(item.get("title")),
                    "price": _first_variant_price(variants) is not None,
                    "currency": bool(item.get("currency")),
                    "availability": any(variant.get("available") is not None for variant in item.get("variants") or []),
                    "variants": bool(variants),
                    "shipping": bool(item.get("shipping")),
                    "returns": bool(item.get("returns")),
                    "specs": bool(item.get("metafields")),
                },
            }
        )
    return normalized


def _shopify_option_name(product: dict, index: int) -> str:
    options = product.get("options")
    if isinstance(options, list) and len(options) >= index:
        option = options[index - 1]
        if isinstance(option, dict) and option.get("name"):
            return str(option["name"])
        if isinstance(option, str):
            return option
    return f"Option {index}"


def _shopify_variant_available(variant: dict) -> bool:
    if variant.get("available") is not None:
        return bool(variant["available"])
    if variant.get("inventory_quantity") is not None:
        try:
            return int(variant["inventory_quantity"]) > 0 or str(variant.get("inventory_policy", "")).lower() == "continue"
        except (TypeError, ValueError):
            return True
    return True


def _first_variant_price(variants: list[dict]) -> str | None:
    for variant in variants:
        if variant.get("price") not in (None, "", "0.00"):
            return str(variant["price"])
    return None


def _load_woocommerce_products(path: Path) -> list[dict]:
    rows = list(csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines()))
    if not rows:
        raise ValueError("WooCommerce CSV input has no rows.")
    by_id = {str(row.get("ID") or row.get("id") or "").strip(): row for row in rows if str(row.get("ID") or row.get("id") or "").strip()}
    variation_rows_by_parent: dict[str, list[dict]] = {}
    products = []
    for row in rows:
        row_type = _csv_value(row, "Type", "type").lower()
        parent = _csv_value(row, "Parent", "parent")
        if row_type == "variation" or parent:
            variation_rows_by_parent.setdefault(parent, []).append(row)
            continue
        products.append(row)
    normalized = []
    for index, row in enumerate(products, start=1):
        product_id = _csv_value(row, "ID", "id")
        variations = variation_rows_by_parent.get(product_id, [])
        if not variations and _csv_value(row, "Type", "type").lower() == "simple":
            variations = [row]
        normalized.append(_normalize_woocommerce_product(row, variations, by_id, index))
    if not normalized and variation_rows_by_parent:
        for index, (parent, variations) in enumerate(variation_rows_by_parent.items(), start=1):
            parent_row = by_id.get(parent) or variations[0]
            normalized.append(_normalize_woocommerce_product(parent_row, variations, by_id, index))
    return normalized


def _normalize_woocommerce_product(row: dict, variations: list[dict], by_id: dict[str, dict], index: int) -> dict:
    title = _csv_value(row, "Name", "name") or f"WooCommerce Product {index}"
    handle = _csv_value(row, "Slug", "slug") or title
    currency = _csv_value(row, "Currency", "currency") or "USD"
    variant_payloads = []
    source_rows = variations or [row]
    for variant_index, variant in enumerate(source_rows, start=1):
        parent_id = _csv_value(variant, "Parent", "parent")
        parent_row = by_id.get(parent_id, row)
        options = _woocommerce_options(variant or parent_row)
        variant_payloads.append(
            {
                "id": _csv_value(variant, "ID", "id") or f"{handle}-{variant_index}",
                "title": _csv_value(variant, "Name", "name") or " / ".join(options.values()) or title,
                "sku": _csv_value(variant, "SKU", "sku") or f"{_slugify(handle)}-{variant_index}",
                "price": _price_value(_csv_value(variant, "Regular price", "Sale price", "Price", "regular_price", "sale_price", "price")) or _price_value(_csv_value(row, "Regular price", "Sale price", "Price")) or "0.00",
                "available": _woocommerce_in_stock(variant),
                "options": options,
            }
        )
    return {
        "title": title,
        "handle": handle,
        "brand": _csv_value(row, "Brands", "Brand", "brand") or "Store",
        "seller": _csv_value(row, "Brands", "Brand", "brand") or "Store",
        "description": _strip_html(_csv_value(row, "Description", "Short description", "description", "short_description")),
        "price": _first_variant_price(variant_payloads) or "0.00",
        "currency": currency,
        "availability": "in_stock" if any(variant["available"] for variant in variant_payloads) else "out_of_stock",
        "variants": variant_payloads,
        "shipping": _csv_value(row, "Shipping", "shipping") or "Ships in 3-5 business days.",
        "returns": _csv_value(row, "Returns", "returns") or "30-day returns accepted for unused items.",
        "specs": _woocommerce_options(row),
        "_source_fields": {
            "title": bool(_csv_value(row, "Name", "name")),
            "price": any(_price_value(_csv_value(source, "Regular price", "Sale price", "Price", "regular_price", "sale_price", "price")) for source in source_rows),
            "currency": bool(_csv_value(row, "Currency", "currency")),
            "availability": any(_csv_value(source, "In stock?", "Stock", "stock_status", "in_stock") for source in source_rows),
            "variants": bool(variations) or _csv_value(row, "Type", "type").lower() == "simple",
            "shipping": bool(_csv_value(row, "Shipping", "shipping")),
            "returns": bool(_csv_value(row, "Returns", "returns")),
            "specs": bool(_woocommerce_options(row)),
        },
    }


def _woocommerce_options(row: dict) -> dict:
    options = {}
    for index in range(1, 8):
        name = _csv_value(row, f"Attribute {index} name", f"attribute_{index}_name")
        values = _csv_value(row, f"Attribute {index} value(s)", f"Attribute {index} values", f"attribute_{index}_values")
        if name and values:
            options[name] = values.split("|")[0].strip()
    return options


def _woocommerce_in_stock(row: dict) -> bool:
    value = _csv_value(row, "In stock?", "Stock", "stock_status", "in_stock").strip().lower()
    if value in {"0", "no", "false", "outofstock", "out of stock"}:
        return False
    return True


def _csv_value(row: dict, *keys: str) -> str:
    lower_map = {str(key).strip().lower(): value for key, value in row.items()}
    for key in keys:
        value = lower_map.get(key.strip().lower())
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _extract_headless_products(payload: object) -> list[dict]:
    candidates = _headless_candidate_lists(payload)
    for candidate in candidates:
        if candidate:
            return [_normalize_headless_product(item, index) for index, item in enumerate(candidate, start=1) if isinstance(item, dict)]
    raise ValueError("Headless input must include a product list under products, items, nodes, edges, catalog.products, or data.products.")


def _headless_candidate_lists(payload: object) -> list[list[dict]]:
    candidates: list[list[dict]] = []
    if isinstance(payload, list):
        candidates.append(payload)
    if isinstance(payload, dict):
        for key in ("products", "items", "nodes"):
            value = payload.get(key)
            if isinstance(value, list):
                candidates.append([_edge_node(item) for item in value])
            elif isinstance(value, dict):
                candidates.extend(_headless_candidate_lists(value))
        for key in ("edges",):
            value = payload.get(key)
            if isinstance(value, list):
                candidates.append([_edge_node(item) for item in value])
        for key in ("data", "catalog"):
            value = payload.get(key)
            if isinstance(value, dict):
                candidates.extend(_headless_candidate_lists(value))
    return candidates


def _edge_node(item: object) -> dict:
    if isinstance(item, dict) and isinstance(item.get("node"), dict):
        return item["node"]
    return item if isinstance(item, dict) else {}


def _normalize_headless_product(item: dict, index: int) -> dict:
    price = item.get("price") or item.get("priceRange") or item.get("pricing") or {}
    variants = item.get("variants") or item.get("variantNodes") or []
    if isinstance(variants, dict):
        variants = variants.get("nodes") or variants.get("edges") or []
    normalized_variants = []
    for variant_index, raw_variant in enumerate(variants if isinstance(variants, list) else [], start=1):
        variant = _edge_node(raw_variant)
        options = variant.get("options") if isinstance(variant.get("options"), dict) else _selected_options(variant)
        variant_price = variant.get("price") or variant.get("priceV2") or price
        normalized_variants.append(
            {
                "id": variant.get("id") or f"{item.get('slug') or item.get('handle') or item.get('title')}-{variant_index}",
                "title": variant.get("title") or " / ".join(str(value) for value in options.values()) or f"Variant {variant_index}",
                "sku": variant.get("sku") or f"{item.get('slug') or item.get('handle') or 'product'}-{variant_index}",
                "price": _price_value(variant_price) or _price_value(price) or "0.00",
                "available": bool(variant.get("availableForSale", variant.get("available", True))),
                "options": options,
            }
        )
    return {
        "title": item.get("title") or item.get("name"),
        "handle": item.get("handle") or item.get("slug"),
        "brand": item.get("brand") or item.get("vendor"),
        "seller": item.get("seller") or item.get("vendor") or item.get("brand"),
        "description": _strip_html(str(item.get("description") or item.get("descriptionHtml") or "")),
        "price": _price_value(price) or _first_variant_price(normalized_variants) or "0.00",
        "currency": _currency_value(price) or item.get("currency") or item.get("currencyCode") or "USD",
        "availability": "in_stock" if item.get("availableForSale", item.get("available", True)) else "out_of_stock",
        "variants": normalized_variants,
        "shipping": item.get("shipping") or item.get("shippingPolicy") or "Ships in 3-5 business days.",
        "returns": item.get("returns") or item.get("returnPolicy") or "30-day returns accepted for unused items.",
        "specs": item.get("specs") if isinstance(item.get("specs"), dict) else {},
        "_source_fields": {
            "title": bool(item.get("title") or item.get("name")),
            "price": _price_value(price) is not None or _first_variant_price(normalized_variants) is not None,
            "currency": bool(_currency_value(price) or item.get("currency") or item.get("currencyCode")),
            "availability": any(key in item for key in ("availableForSale", "available")),
            "variants": bool(normalized_variants),
            "shipping": bool(item.get("shipping") or item.get("shippingPolicy")),
            "returns": bool(item.get("returns") or item.get("returnPolicy")),
            "specs": isinstance(item.get("specs"), dict) and bool(item.get("specs")),
        },
    }


def _selected_options(variant: dict) -> dict:
    selected = variant.get("selectedOptions")
    if isinstance(selected, list):
        return {
            str(item.get("name")): item.get("value")
            for item in selected
            if isinstance(item, dict) and item.get("name") and item.get("value") is not None
        }
    return {}


def _price_value(value: object) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return f"{value:.2f}"
    if isinstance(value, str):
        cleaned = value.strip().replace("$", "").replace(",", "")
        return cleaned or None
    if isinstance(value, dict):
        for key in ("amount", "value", "price", "minVariantPrice", "regular_price", "sale_price"):
            nested = value.get(key)
            if isinstance(nested, dict):
                nested_price = _price_value(nested)
                if nested_price:
                    return nested_price
            elif nested not in (None, ""):
                return _price_value(nested)
    return None


def _currency_value(value: object) -> str | None:
    if isinstance(value, dict):
        for key in ("currencyCode", "currency", "currency_code"):
            if value.get(key):
                return str(value[key]).upper()
        for nested in value.values():
            currency = _currency_value(nested)
            if currency:
                return currency
    return None


def _strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value).strip()


def _first_variant_value(product: dict, key: str) -> object | None:
    variants = product.get("variants")
    if isinstance(variants, list):
        for variant in variants:
            if isinstance(variant, dict) and variant.get(key) not in (None, ""):
                return variant[key]
    return None


def _availability_from_variants(product: dict) -> str | None:
    variants = product.get("variants")
    if not isinstance(variants, list):
        return None
    for variant in variants:
        if isinstance(variant, dict) and variant.get("available") is True:
            return "in_stock"
    return "out_of_stock" if variants else None


def _normalize_variants(product: dict) -> list[dict]:
    variants = product.get("variants")
    if not isinstance(variants, list) or not variants:
        variants = [
            {
                "id": f"{product['handle']}-default",
                "title": "Default",
                "sku": str(product.get("sku") or product["handle"]).upper(),
                "price": product["price"],
                "available": product["availability"] not in {"out_of_stock", "sold_out", "unavailable"},
                "options": product.get("options") if isinstance(product.get("options"), dict) else {},
            }
        ]
    normalized = []
    for index, variant in enumerate(variants, start=1):
        if not isinstance(variant, dict):
            raise ValueError(f"Variant #{index} for {product['title']} must be a JSON object.")
        options = variant.get("options") if isinstance(variant.get("options"), dict) else {}
        normalized.append(
            {
                "id": variant.get("id") or f"{product['handle']}-{index}",
                "title": variant.get("title") or " / ".join(str(value) for value in options.values()) or f"Variant {index}",
                "sku": variant.get("sku") or f"{product['handle']}-{index}",
                "price": str(variant.get("price") or product["price"]),
                "available": bool(variant.get("available", product["availability"] not in {"out_of_stock", "sold_out", "unavailable"})),
                "options": options,
            }
        )
    return normalized


def _option_definitions(product: dict) -> list[dict]:
    values: dict[str, set[str]] = {}
    for variant in product["variants"]:
        for key, value in variant["options"].items():
            values.setdefault(str(key), set()).add(str(value))
    return [{"name": key, "values": sorted(items)} for key, items in sorted(values.items())]


def _variant_with_option_fields(variant: dict) -> dict:
    payload = {key: value for key, value in variant.items() if not str(key).startswith("_")}
    for key, value in variant["options"].items():
        normalized_key = _slugify(str(key)).replace("-", "_")
        if normalized_key:
            payload[normalized_key] = value
    return payload


def _schema_availability(product: dict) -> str:
    value = str(product.get("availability") or "").lower()
    if value in {"out_of_stock", "sold_out", "unavailable"}:
        return "https://schema.org/OutOfStock"
    if value in {"preorder", "pre_order"}:
        return "https://schema.org/PreOrder"
    return "https://schema.org/InStock"


def _json_script(data: object, *, script_id: str | None = None, script_type: str = "application/json") -> str:
    attrs = [f'type="{script_type}"']
    if script_id:
        attrs.append(f'id="{html.escape(script_id, quote=True)}"')
    return f"<script {' '.join(attrs)}>\n{json.dumps(data, indent=2)}\n</script>"


def _product_jsonld(product: dict) -> dict:
    offers = []
    for variant in product["variants"]:
        offers.append(
            {
                "@type": "Offer",
                "sku": variant["sku"],
                "price": variant["price"],
                "priceCurrency": product["currency"],
                "availability": "https://schema.org/InStock" if variant["available"] else "https://schema.org/OutOfStock",
                "seller": {"@type": "Organization", "name": product.get("seller") or "Store"},
            }
        )
    payload: dict[str, object] = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": product["title"],
        "description": product.get("description") or product["title"],
        "sku": product.get("sku") or product["handle"],
        "brand": {"@type": "Brand", "name": product.get("brand") or product.get("seller") or "Store"},
        "offers": offers[0] if len(offers) == 1 else offers,
    }
    reviews = product.get("reviews")
    if isinstance(reviews, dict) and reviews.get("rating") and reviews.get("count"):
        payload["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": reviews["rating"],
            "reviewCount": reviews["count"],
        }
    if product.get("returns"):
        payload["hasMerchantReturnPolicy"] = {
            "@type": "MerchantReturnPolicy",
            "applicableCountry": product.get("return_country") or "US",
            "returnPolicyCategory": "https://schema.org/MerchantReturnFiniteReturnWindow",
            "merchantReturnDays": product.get("return_days") or 30,
        }
    return payload


def _render_visible_product_sections(product: dict) -> str:
    specs = product.get("specs") if isinstance(product.get("specs"), dict) else {}
    faq = product.get("faq") if isinstance(product.get("faq"), list) else []
    specs_html = "\n".join(
        f"<li><strong>{html.escape(str(key))}:</strong> {html.escape(str(value))}</li>"
        for key, value in specs.items()
    )
    faq_html = "\n".join(
        f"<dt>{html.escape(str(item.get('question', 'Question')))}</dt><dd>{html.escape(str(item.get('answer', 'Answer')))}</dd>"
        for item in faq
        if isinstance(item, dict)
    )
    variants_html = "\n".join(
        "<li>"
        f"{html.escape(str(variant['title']))}: {html.escape(product['currency'])} {html.escape(str(variant['price']))} "
        f"({'in stock' if variant['available'] else 'out of stock'})"
        "</li>"
        for variant in product["variants"]
    )
    return f"""
<main>
  <h1>{html.escape(product["title"])}</h1>
  <p class="price">{html.escape(product["currency"])} {html.escape(str(product["price"]))}</p>
  <p class="availability">{'In stock' if product["availability"] != "out_of_stock" else "Out of stock"}</p>
  <p class="description">{html.escape(str(product.get("description") or product["title"]))}</p>
  <section class="variants"><h2>Options and variants</h2><ul>{variants_html}</ul></section>
  <section class="shipping"><h2>Shipping</h2><p>{html.escape(str(product.get("shipping") or "Ships in 3-5 business days."))}</p></section>
  <section class="returns"><h2>Returns</h2><p>{html.escape(str(product.get("returns") or "30-day returns accepted for unused items."))}</p></section>
  <section class="specs"><h2>Specifications</h2><ul>{specs_html}</ul></section>
  <section class="reviews"><h2>Reviews</h2><p>{html.escape(_review_copy(product))}</p></section>
  <section class="faq"><h2>FAQ</h2><dl>{faq_html}</dl></section>
</main>"""


def _review_copy(product: dict) -> str:
    reviews = product.get("reviews")
    if isinstance(reviews, dict) and reviews.get("rating") and reviews.get("count"):
        return f"Rated {reviews['rating']} from {reviews['count']} customer reviews."
    return "Customer reviews are available on the product page."


def _render_shopify_fixture(product: dict) -> str:
    shopify_product = {
        "id": product.get("id") or product["handle"],
        "handle": product["handle"],
        "title": product["title"],
        "vendor": product.get("seller") or product.get("brand") or "Store",
        "options": _option_definitions(product),
        "variants": [
            _variant_with_option_fields(
                {
                    "id": variant["id"],
                    "title": variant["title"],
                    "sku": variant["sku"],
                    "price": variant["price"],
                    "available": variant["available"],
                    "options": variant["options"],
                }
            )
            for variant in product["variants"]
        ],
        "selling_plan_groups": product.get("selling_plan_groups") or [],
        "metafields": product.get("metafields") or product.get("specs") or {},
    }
    return _fixture_document(
        product,
        body=f"""
<body data-platform="shopify" class="template-product">
  {_render_visible_product_sections(product)}
  {_json_script(shopify_product, script_id="ProductJson-template")}
</body>""",
    )


def _render_woocommerce_fixture(product: dict) -> str:
    variations = [
        {
            "variation_id": variant["id"],
            "sku": variant["sku"],
            "display_price": variant["price"],
            "is_in_stock": variant["available"],
            "attributes": {f"attribute_{_slugify(str(key))}": value for key, value in variant["options"].items()},
        }
        for variant in product["variants"]
    ]
    return _fixture_document(
        product,
        body=f"""
<body data-platform="woocommerce" class="single-product woocommerce">
  {_render_visible_product_sections(product)}
  <form class="variations_form cart" data-product_variations="{html.escape(json.dumps(variations), quote=True)}"></form>
</body>""",
    )


def _render_headless_fixture(product: dict) -> str:
    next_data = {
        "props": {
            "pageProps": {
                "product": {
                    "handle": product["handle"],
                    "title": product["title"],
                    "price": {"amount": product["price"], "currencyCode": product["currency"]},
                    "availableForSale": product["availability"] != "out_of_stock",
                    "options": _option_definitions(product),
                    "variants": [_variant_with_option_fields(variant) for variant in product["variants"]],
                    "shipping": product.get("shipping"),
                    "returns": product.get("returns"),
                }
            }
        }
    }
    return _fixture_document(
        product,
        body=f"""
<body data-platform="headless">
  <div id="__next">{_render_visible_product_sections(product)}</div>
  {_json_script(next_data, script_id="__NEXT_DATA__")}
</body>""",
    )


def _fixture_document(product: dict, body: str) -> str:
    jsonld = _json_script(_product_jsonld(product), script_type="application/ld+json")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(product["title"])}</title>
  <meta name="description" content="{html.escape(str(product.get("description") or product["title"]), quote=True)}">
  {jsonld}
</head>
{body}
</html>
"""


def _render_fixture_for_platform(product: dict, platform: str) -> str:
    if platform == "shopify":
        return _render_shopify_fixture(product)
    if platform == "woocommerce":
        return _render_woocommerce_fixture(product)
    if platform == "headless":
        return _render_headless_fixture(product)
    raise ValueError(f"Unsupported fixture platform: {platform}.")


def _render_storefront_fixtures(
    products_path: Path,
    output_dir: Path,
    platforms: list[str],
    manifest_path: Path | None,
    input_format: str = "auto",
) -> dict:
    products, detected_format = _load_fixture_products(products_path, input_format=input_format)
    validation = _validate_fixture_products(products)
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshots = []
    for product in products:
        for platform in platforms:
            filename = f"{product['handle']}.{platform}.html"
            path = output_dir / filename
            path.write_text(_render_fixture_for_platform(product, platform), encoding="utf-8")
            snapshots.append(
                {
                    "product": product["title"],
                    "handle": product["handle"],
                    "platform": platform,
                    "path": str(path),
                    "profile": platform,
                    "scan_command": f"agentshelf scan {path} --profile {platform} --format markdown",
                }
            )
    manifest = {
        "contract": "agentshelf.storefront_fixtures.v1",
        "source": str(products_path),
        "input_format": detected_format,
        "output_dir": str(output_dir),
        "platforms": platforms,
        "count": len(snapshots),
        "validation": validation,
        "snapshots": snapshots,
        "batch_scan_command": f"agentshelf scan {output_dir} --batch --format jsonl",
    }
    if manifest_path:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def _render_import_remediation_tasks(manifest: dict) -> str:
    lines = []
    for warning in manifest["validation"]["warnings"]:
        task = _import_warning_to_task(warning, manifest)
        lines.append(json.dumps(task))
    return "\n".join(lines) + ("\n" if lines else "")


def _import_warning_to_task(warning: dict, manifest: dict) -> dict:
    field = warning["field"]
    task_id = f"fix_import_{field.replace('.', '_')}"
    return {
        "source": manifest["source"],
        "input_format": manifest["input_format"],
        "product": warning["product"],
        "task": {
            "id": task_id,
            "reason": warning["message"],
            "files_or_page_area": _import_task_area(field, manifest["input_format"]),
            "acceptance_check": _import_task_acceptance(field),
            "priority": _import_task_priority(field),
            "field": field,
            "action": warning["action"],
        },
    }


def _import_task_area(field: str, input_format: str) -> str:
    if input_format == "woocommerce":
        mapping = {
            "price": "WooCommerce CSV price columns: Regular price, Sale price, or Price.",
            "currency": "WooCommerce CSV export or upstream export job currency column.",
            "availability": "WooCommerce CSV stock columns: In stock?, Stock, or stock_status.",
            "variants": "WooCommerce CSV variable product rows and variation rows linked by Parent.",
            "variant.price": "WooCommerce variation row price columns.",
            "variant.options": "WooCommerce Attribute N name/value(s) columns on variation rows.",
            "variant.available": "WooCommerce variation row stock columns.",
        }
    elif input_format == "shopify":
        mapping = {
            "price": "Shopify product JSON variants[].price.",
            "currency": "Shopify product export currency field or export wrapper metadata.",
            "availability": "Shopify variant available, inventory_quantity, or inventory_policy fields.",
            "variants": "Shopify product JSON variants array.",
            "variant.price": "Shopify variants[].price.",
            "variant.options": "Shopify variants[].option1/option2/option3 and product options[].name.",
            "variant.available": "Shopify variants[].available or inventory_quantity.",
        }
    elif input_format == "headless":
        mapping = {
            "price": "Headless catalog price, priceRange, pricing, or variants[].price fields.",
            "currency": "Headless catalog currencyCode or price.currencyCode fields.",
            "availability": "Headless catalog availableForSale or available fields.",
            "variants": "Headless catalog variants nodes, edges, or variantNodes.",
            "variant.price": "Headless variant price or priceV2 fields.",
            "variant.options": "Headless variant selectedOptions or options fields.",
            "variant.available": "Headless variant availableForSale or available fields.",
        }
    else:
        mapping = {
            "price": "Normalized AgentShelf product price or variants[].price.",
            "currency": "Normalized AgentShelf product currency.",
            "availability": "Normalized AgentShelf product availability or variants[].available.",
            "variants": "Normalized AgentShelf variants array.",
            "variant.price": "Normalized AgentShelf variants[].price.",
            "variant.options": "Normalized AgentShelf variants[].options.",
            "variant.available": "Normalized AgentShelf variants[].available.",
        }
    shared = {
        "shipping": "Product export shipping or shippingPolicy field.",
        "returns": "Product export returns or returnPolicy field.",
        "specs": "Product export specs, metafields, attributes, or product facts.",
    }
    return {**mapping, **shared}.get(field, f"Product export field `{field}`.")


def _import_task_acceptance(field: str) -> str:
    return (
        f"Re-run `agentshelf render-fixtures ... --format json --fail-on-warnings` and confirm no validation warning remains for `{field}`."
    )


def _import_task_priority(field: str) -> str:
    return "high" if field in {"price", "availability", "variants", "variant.price", "variant.available"} else "medium"


def _render_fixture_summary(manifest: dict, output_format: str) -> str:
    if output_format == "json":
        return json.dumps(manifest, indent=2) + "\n"
    lines = [
        "# AgentShelf Storefront Fixtures",
        "",
        f"- Source: `{manifest['source']}`",
        f"- Output dir: `{manifest['output_dir']}`",
        f"- Snapshots: {manifest['count']}",
        f"- Validation warnings: {manifest['validation']['warning_count']}",
        f"- Batch scan: `{manifest['batch_scan_command']}`",
        "",
        "| Platform | Product | Path |",
        "| --- | --- | --- |",
    ]
    for item in manifest["snapshots"]:
        lines.append(f"| {item['platform']} | {item['product']} | `{item['path']}` |")
    if manifest["validation"]["warnings"]:
        lines.extend(["", "## Import Warnings"])
        for warning in manifest["validation"]["warnings"]:
            lines.append(
                f"- `{warning['severity']}` {warning['product']}: {warning['message']} "
                f"({warning['field']}; action: {warning['action']})"
            )
    return "\n".join(lines) + "\n"


def _validate_fixture_products(products: list[dict]) -> dict:
    warnings = []
    for product in products:
        fields = product.get("_source_fields") if isinstance(product.get("_source_fields"), dict) else {}
        product_name = product.get("title") or product.get("handle") or "unknown product"
        checks = [
            ("price", "Product export did not include an explicit price; fixture generation used a fallback price.", "Add product or variant price to the export."),
            ("currency", "Product export did not include currency; fixture generation used USD.", "Add currency or currencyCode to the export."),
            ("availability", "Product export did not include stock or availability state; fixture generation inferred availability.", "Export available, availableForSale, stock, or inventory fields."),
            ("shipping", "Product export did not include shipping policy text; fixture generation used generic shipping copy.", "Add shipping or shippingPolicy to the export."),
            ("returns", "Product export did not include return policy text; fixture generation used generic return copy.", "Add returns or returnPolicy to the export."),
            ("specs", "Product export did not include specs or metafields; generated pages may be thin for fit questions.", "Add specs, metafields, attributes, or product facts."),
        ]
        for field, message, action in checks:
            if not fields.get(field):
                warnings.append(_validation_warning(product_name, field, message, action))
        variants = product.get("variants") if isinstance(product.get("variants"), list) else []
        if not fields.get("variants") or not variants:
            warnings.append(
                _validation_warning(
                    product_name,
                    "variants",
                    "Product export did not include variants; fixture generation created a default variant.",
                    "Export variant rows or nodes with option, price, and stock context.",
                )
            )
        for index, variant in enumerate(variants, start=1):
            label = f"{product_name} variant {index}"
            if variant.get("price") in (None, "", "0.00"):
                warnings.append(_validation_warning(label, "variant.price", "Variant is missing price.", "Add variant price."))
            if not variant.get("options"):
                warnings.append(
                    _validation_warning(
                        label,
                        "variant.options",
                        "Variant has no option labels; agents may not know size, color, or configuration.",
                        "Add variant option names and values.",
                    )
                )
            if variant.get("available") is None:
                warnings.append(_validation_warning(label, "variant.available", "Variant is missing stock state.", "Add available or stock fields."))
    return {
        "warning_count": len(warnings),
        "warnings": warnings,
        "status": "warning" if warnings else "ok",
    }


def _validation_warning(product: object, field: str, message: str, action: str) -> dict:
    return {
        "severity": "warning",
        "product": str(product),
        "field": field,
        "message": message,
        "action": action,
    }


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
    muted_none = '<span class="muted">None</span>'
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
            f"<div class='section'><h3>Review categories</h3><div>{categories or muted_none}</div></div>"
            f"<div class='section'><h3>Blocking issues</h3><div>{blockers or muted_none}</div></div>"
            f"<div class='section'><h3>Agent tasks</h3><div>{tasks or muted_none}</div></div>"
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


def _fix_text(fix: object) -> str:
    if isinstance(fix, dict):
        return str(fix.get("recommendation") or fix.get("id") or fix)
    return str(fix)


def _format_scan_gate_failure(results: list[dict], min_score: int | None, fail_on: str | None) -> str:
    failed = [item for item in results if _fails_threshold(item, min_score, fail_on)]
    if not failed:
        return ""
    lines = [
        "AgentShelf gate failed.",
        f"Failed pages: {len(failed)} of {len(results)}",
    ]
    if min_score is not None:
        lines.append(f"Minimum score: {min_score}")
    if fail_on is not None:
        lines.append(f"Fail-on band: {fail_on}")
    lines.append("")
    lines.append("Pages to fix:")
    for item in failed[:5]:
        page = item.get("page", {})
        title = page.get("title") or "Untitled page"
        source = page.get("source") or "unknown source"
        lines.append(f"- {title} ({source}): score {item['score']}/100, band {item['band']}")
        for fix in item.get("top_fixes", [])[:3]:
            lines.append(f"  - {_fix_text(fix)}")
    if len(failed) > 5:
        lines.append(f"- ...and {len(failed) - 5} more page(s).")
    lines.extend(
        [
            "",
            "Next steps:",
            "- Read the report output for evidence and exact failed checks.",
            "- Run `agentshelf agent-tasks <path> --batch --output agentshelf-tasks.jsonl` for coding-agent remediation tasks.",
            "- Re-run the same scan after fixing product data, templates, or generated snapshots.",
        ]
    )
    return "\n".join(lines) + "\n"


def _format_agent_blocker_failure(contract: dict) -> str:
    blockers = [issue for issue in contract.get("blocking_issues", []) if issue.get("severity") == "high"]
    if not blockers:
        return ""
    lines = [
        "AgentShelf agent-audit blocker gate failed.",
        f"High-severity blockers: {len(blockers)}",
        "",
        "Top blockers:",
    ]
    for issue in blockers[:5]:
        lines.append(f"- {issue.get('id', 'unknown')}: {issue.get('reason', 'No reason provided.')}")
    lines.extend(
        [
            "",
            "Next steps:",
            "- Use the `agent_tasks` JSON array as the implementation queue.",
            "- Re-run `agentshelf agent-audit <path> --fail-on-blockers` after fixes.",
        ]
    )
    return "\n".join(lines) + "\n"


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

    geo_audit = subcommands.add_parser("geo-audit", help="Run a GEO Skill audit for AI-readable commerce.")
    geo_audit.add_argument("target", nargs="?", help="HTML file or http(s) URL to audit.")
    geo_audit.add_argument("--url", help="http(s) URL to audit. Use instead of the positional target.")
    geo_audit.add_argument("--brand", dest="brand_name", help="Brand or artist name.")
    geo_audit.add_argument("--store", dest="store_name", help="Store name if different from the brand.")
    geo_audit.add_argument("--category", help="Commerce category, for example custom gifts or handmade teacups.")
    geo_audit.add_argument("--market", action="append", help="Target market. Repeat or comma-separate values.")
    geo_audit.add_argument("--language", default="en", help="Primary report/prompt language. v0 is optimized for English.")
    geo_audit.add_argument("--competitor", action="append", help="Competitor or alternative brand. Repeat or comma-separate values.")
    geo_audit.add_argument("--persona", action="append", help="Buyer persona. Repeat or comma-separate values.")
    geo_audit.add_argument("--use-case", action="append", help="Buyer use case. Repeat or comma-separate values.")
    geo_audit.add_argument("--key-product", action="append", help="Key product or product family. Repeat or comma-separate values.")
    geo_audit.add_argument(
        "--vertical",
        choices=("commerce", "creator_commerce", "artist_store", "local_service", "generic"),
        default="commerce",
        help="GEO vertical profile.",
    )
    geo_audit.add_argument("--max-pages", type=int, default=1, help="Reserved for future multi-page audits; v0 audits one page.")
    geo_audit.add_argument("--no-prompt-panel", action="store_true", help="Do not include deterministic prompt panel output.")
    geo_audit.add_argument("--no-patches", action="store_true", help="Do not include page patch suggestions.")
    geo_audit.add_argument("--format", choices=("markdown", "json", "both"), default="markdown", help="Report output format.")
    geo_audit.add_argument("--output", "--out", type=Path, help="Output file path or prefix. With --format both, writes .md and .json.")
    geo_audit.add_argument("--timeout", type=float, default=10.0, help="URL fetch timeout in seconds.")

    geo_tasks = subcommands.add_parser("geo-tasks", help="Emit JSONL remediation tasks from a geo-audit JSON report.")
    geo_tasks.add_argument("report", type=Path, help="JSON output from `agentshelf geo-audit --format json`.")
    geo_tasks.add_argument("--format", choices=("jsonl", "json"), default="jsonl", help="Task output format.")
    geo_tasks.add_argument("--output", type=Path, help="Optional task output path.")

    geo_run = subcommands.add_parser("geo-run", help="Run the full GEO audit, contract validation, task export, and optional local scan workflow.")
    geo_run.add_argument("target", nargs="?", help="HTML file or http(s) URL to audit.")
    geo_run.add_argument("--url", help="http(s) URL to audit. Use instead of the positional target.")
    geo_run.add_argument("--brand", dest="brand_name", help="Brand or artist name.")
    geo_run.add_argument("--store", dest="store_name", help="Store name if different from the brand.")
    geo_run.add_argument("--category", help="Commerce category, for example custom gifts or handmade teacups.")
    geo_run.add_argument("--market", action="append", help="Target market. Repeat or comma-separate values.")
    geo_run.add_argument("--language", default="en", help="Primary report/prompt language. v0 is optimized for English.")
    geo_run.add_argument("--competitor", action="append", help="Competitor or alternative brand. Repeat or comma-separate values.")
    geo_run.add_argument("--persona", action="append", help="Buyer persona. Repeat or comma-separate values.")
    geo_run.add_argument("--use-case", action="append", help="Buyer use case. Repeat or comma-separate values.")
    geo_run.add_argument("--key-product", action="append", help="Key product or product family. Repeat or comma-separate values.")
    geo_run.add_argument(
        "--vertical",
        choices=("commerce", "creator_commerce", "artist_store", "local_service", "generic"),
        default="commerce",
        help="GEO vertical profile.",
    )
    geo_run.add_argument("--max-pages", type=int, default=1, help="Reserved for future multi-page audits; v0 audits one page.")
    geo_run.add_argument("--no-prompt-panel", action="store_true", help="Do not include deterministic prompt panel output.")
    geo_run.add_argument("--no-patches", action="store_true", help="Do not include page patch suggestions.")
    geo_run.add_argument("--timeout", type=float, default=10.0, help="URL fetch timeout in seconds.")
    geo_run.add_argument("--output-dir", type=Path, default=Path("agentshelf-geo-run"), help="Directory for generated GEO artifacts.")
    geo_run.add_argument("--format", choices=("markdown", "json"), default="markdown", help="Summary output format.")
    geo_run.add_argument("--output", type=Path, help="Optional summary output path.")

    dogfood = subcommands.add_parser("dogfood", help="Run a safe real-URL dogfood audit without persisting third-party raw HTML.")
    dogfood.add_argument("url", nargs="?", help="http(s) product or storefront URL to audit.")
    dogfood.add_argument("--url", dest="url_option", help="http(s) product or storefront URL to audit. Use instead of the positional URL.")
    dogfood.add_argument("--brand", dest="brand_name", help="Brand or artist name.")
    dogfood.add_argument("--store", dest="store_name", help="Store name if different from the brand.")
    dogfood.add_argument("--category", help="Commerce category, for example custom gifts or handmade teacups.")
    dogfood.add_argument("--market", action="append", help="Target market. Repeat or comma-separate values.")
    dogfood.add_argument("--language", default="en", help="Primary report/prompt language. v0 is optimized for English.")
    dogfood.add_argument("--competitor", action="append", help="Competitor or alternative brand. Repeat or comma-separate values.")
    dogfood.add_argument("--persona", action="append", help="Buyer persona. Repeat or comma-separate values.")
    dogfood.add_argument("--use-case", action="append", help="Buyer use case. Repeat or comma-separate values.")
    dogfood.add_argument("--key-product", action="append", help="Key product or product family. Repeat or comma-separate values.")
    dogfood.add_argument(
        "--vertical",
        choices=("commerce", "creator_commerce", "artist_store", "local_service", "generic"),
        default="commerce",
        help="GEO vertical profile.",
    )
    dogfood.add_argument("--profile", choices=ADAPTER_PROFILES, default="auto", help="Storefront adapter profile for the product-readiness scan.")
    dogfood.add_argument("--max-pages", type=int, default=1, help="Reserved for future multi-page audits; v0 audits one URL.")
    dogfood.add_argument("--no-prompt-panel", action="store_true", help="Do not include deterministic prompt panel output.")
    dogfood.add_argument("--no-patches", action="store_true", help="Do not include page patch suggestions.")
    dogfood.add_argument("--timeout", type=float, default=10.0, help="URL fetch timeout in seconds.")
    dogfood.add_argument("--output-dir", type=Path, default=Path("agentshelf-dogfood"), help="Directory for safe dogfood artifacts.")
    dogfood.add_argument("--format", choices=("markdown", "json"), default="markdown", help="Summary output format.")
    dogfood.add_argument("--output", type=Path, help="Optional summary output path.")

    validate_contract = subcommands.add_parser("validate-contract", help="Validate AgentShelf JSON or JSONL contract artifacts.")
    validate_contract.add_argument("path", type=Path, help="AgentShelf JSON or JSONL artifact to validate.")
    validate_contract.add_argument(
        "--contract",
        choices=("auto", "agentshelf.geo_audit.v0", "agentshelf.geo_task.v0", "agentshelf.geo_tasks.v0"),
        default="auto",
        help="Expected contract. Defaults to auto-detect.",
    )
    validate_contract.add_argument("--format", choices=("markdown", "json"), default="markdown", help="Validation output format.")
    validate_contract.add_argument("--output", type=Path, help="Optional validation report path.")

    skill_info = subcommands.add_parser("skill-info", help="Show the bundled AgentShelf GEO skill status and install guidance.")
    skill_info.add_argument("--format", choices=("markdown", "json"), default="markdown", help="Output format.")
    skill_info.add_argument("--output", type=Path, help="Optional output path.")

    export_skill = subcommands.add_parser("export-skill", help="Export the bundled agentshelf-geo skill into a coding-agent repository.")
    export_skill.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".codex/skills"),
        help="Parent directory that should receive agentshelf-geo/. Defaults to .codex/skills.",
    )
    export_skill.add_argument("--force", action="store_true", help="Overwrite conflicting exported skill files.")
    export_skill.add_argument("--format", choices=("markdown", "json"), default="markdown", help="Output format.")
    export_skill.add_argument("--output", type=Path, help="Optional output path.")

    init_merchant_repo = subcommands.add_parser(
        "init-merchant-repo",
        help="Initialize a storefront repository with AgentShelf GEO workflow, config, demo snapshot, and optional Codex skill.",
    )
    init_merchant_repo.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Merchant repository root to initialize. Defaults to the current directory.",
    )
    init_merchant_repo.add_argument("--brand", default="Example Studio", help="Merchant, brand, artist, or store name for template defaults.")
    init_merchant_repo.add_argument("--category", default="commerce products", help="Commerce category for template defaults.")
    init_merchant_repo.add_argument(
        "--vertical",
        choices=("commerce", "creator_commerce", "artist_store", "local_service", "generic"),
        default="commerce",
        help="GEO vertical profile for the generated workflow.",
    )
    init_merchant_repo.add_argument("--no-skill", action="store_true", help="Do not export the bundled agentshelf-geo Codex skill.")
    init_merchant_repo.add_argument("--force", action="store_true", help="Overwrite conflicting template or skill files.")
    init_merchant_repo.add_argument("--format", choices=("markdown", "json"), default="markdown", help="Output format.")
    init_merchant_repo.add_argument("--output", type=Path, help="Optional output path.")

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

    render_fixtures = subcommands.add_parser("render-fixtures", help="Render stable storefront HTML fixtures from a product JSON export.")
    render_fixtures.add_argument("products", type=Path, help="JSON list or {products: [...]} catalog export.")
    render_fixtures.add_argument("--output-dir", type=Path, default=Path("snapshots"), help="Directory for generated HTML snapshots.")
    render_fixtures.add_argument("--manifest", type=Path, help="Optional JSON manifest path.")
    render_fixtures.add_argument(
        "--input-format",
        choices=FIXTURE_INPUT_FORMATS,
        default="auto",
        help="Catalog export shape to import before rendering fixtures.",
    )
    render_fixtures.add_argument(
        "--platform",
        choices=(*FIXTURE_PLATFORMS, "all"),
        default="all",
        help="Storefront fixture shape to render.",
    )
    render_fixtures.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Return non-zero when import validation warnings are present.",
    )
    render_fixtures.add_argument("--tasks-output", type=Path, help="Optional JSONL output for import remediation tasks.")
    render_fixtures.add_argument("--format", choices=("markdown", "json"), default="markdown", help="Summary output format.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return 2

    failure_summary = ""
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
            if exit_code:
                failure_summary = _format_scan_gate_failure(results, args.min_score, args.fail_on)
        elif args.command == "agent-audit":
            bundle = _load_target(args.target, adapter_profile=args.profile)
            contract = build_agent_contract(bundle, contract=args.contract)
            rendered = json.dumps(contract, indent=2) + "\n"
            exit_code = 1 if args.fail_on_blockers and any(issue["severity"] == "high" for issue in contract["blocking_issues"]) else 0
            if exit_code:
                failure_summary = _format_agent_blocker_failure(contract)
        elif args.command == "agent-tasks":
            paths = _resolve_inputs(args.path, args.batch)
            if len(paths) > 1 and not args.batch:
                raise ValueError("Multiple inputs found. Re-run with --batch.")
            results = [_load_scan(path, adapter_profile=args.profile) for path in paths]
            rendered = _render_agent_tasks(results)
            exit_code = 0
        elif args.command == "geo-audit":
            target = args.url or args.target
            if not target:
                raise ValueError("Provide a target file/URL or --url.")
            if args.url and args.target:
                raise ValueError("Provide either positional target or --url, not both.")
            if args.max_pages < 1:
                raise ValueError("--max-pages must be at least 1.")
            html, fetch_metadata = _load_geo_target(target, timeout=args.timeout)
            config = GeoSkillConfig(
                targetUrl=target,
                brandName=args.brand_name,
                storeName=args.store_name,
                category=args.category,
                market=_split_cli_values(args.market),
                language=args.language,
                competitors=_split_cli_values(args.competitor),
                personas=_split_cli_values(args.persona),
                useCases=_split_cli_values(args.use_case),
                keyProducts=_split_cli_values(args.key_product),
                maxPages=args.max_pages,
                includePromptPanel=not args.no_prompt_panel,
                includePatchSuggestions=not args.no_patches,
                vertical=args.vertical,
                outputFormat=args.format,
            )
            result = build_geo_audit(
                config,
                html,
                robots_text=fetch_metadata["robots_text"],
                robots_status=fetch_metadata["robots_status"],
                sitemap_status=fetch_metadata["sitemap_status"],
                llms_status=fetch_metadata["llms_status"],
                raw_metadata={
                    "source_type": fetch_metadata["source_type"],
                    "fetch_warnings": fetch_metadata["fetch_warnings"],
                },
            )
            if args.format == "json":
                rendered = render_geo_json(result)
            elif args.format == "both":
                if args.output:
                    output_base = args.output.with_suffix("") if args.output.suffix in {".md", ".json"} else args.output
                    markdown_path = output_base.with_suffix(".md")
                    json_path = output_base.with_suffix(".json")
                    _write_text_atomic(markdown_path, result.reportMarkdown)
                    _write_text_atomic(json_path, render_geo_json(result))
                    args.output = None
                    rendered = f"Wrote GEO audit reports: {markdown_path} and {json_path}\n"
                else:
                    rendered = render_geo_json(result) + "\n" + result.reportMarkdown
            else:
                rendered = result.reportMarkdown
            exit_code = 0
        elif args.command == "geo-tasks":
            try:
                report = json.loads(args.report.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid geo-audit JSON report {args.report}: {exc.msg}.") from exc
            if not isinstance(report, dict) or report.get("rawMetadata", {}).get("contract") != "agentshelf.geo_audit.v0":
                raise ValueError("Expected a JSON report from `agentshelf geo-audit --format json`.")
            rendered = render_geo_tasks_json(report) if args.format == "json" else render_geo_tasks_jsonl(report)
            exit_code = 0
        elif args.command == "geo-run":
            target = args.url or args.target
            if not target:
                raise ValueError("Provide a target file/URL or --url.")
            if args.url and args.target:
                raise ValueError("Provide either positional target or --url, not both.")
            if args.max_pages < 1:
                raise ValueError("--max-pages must be at least 1.")
            output_dir = args.output_dir
            output_dir.mkdir(parents=True, exist_ok=True)
            html, fetch_metadata = _load_geo_target(target, timeout=args.timeout)
            result = build_geo_audit(
                _build_geo_config_from_args(target, args),
                html,
                robots_text=fetch_metadata["robots_text"],
                robots_status=fetch_metadata["robots_status"],
                sitemap_status=fetch_metadata["sitemap_status"],
                llms_status=fetch_metadata["llms_status"],
                raw_metadata={
                    "source_type": fetch_metadata["source_type"],
                    "fetch_warnings": fetch_metadata["fetch_warnings"],
                },
            )
            report_json = render_geo_json(result)
            report_path = output_dir / "geo-report.json"
            report_md_path = output_dir / "geo-report.md"
            tasks_path = output_dir / "geo-tasks.jsonl"
            _write_text_atomic(report_path, report_json)
            _write_text_atomic(report_md_path, result.reportMarkdown)
            _write_text_atomic(tasks_path, render_geo_tasks_jsonl(json.loads(report_json)))
            report_validation = _validate_contract_file(report_path, requested_contract="agentshelf.geo_audit.v0")
            task_validation = _validate_contract_file(tasks_path, requested_contract="agentshelf.geo_task.v0")
            _write_text_atomic(output_dir / "geo-report-validation.json", json.dumps(report_validation, indent=2) + "\n")
            _write_text_atomic(output_dir / "geo-tasks-validation.json", json.dumps(task_validation, indent=2) + "\n")
            scan_bundle = None
            if not _is_url(target):
                target_path = Path(target)
                if target_path.exists() and target_path.is_file():
                    scan_bundle = _load_scan(target_path)
                    _write_text_atomic(output_dir / "scan-report.md", render_markdown(scan_bundle))
            summary = _build_geo_run_summary(
                target=target,
                output_dir=output_dir,
                geo_report=json.loads(report_json),
                task_validation=task_validation,
                report_validation=report_validation,
                scan_bundle=scan_bundle,
            )
            _write_text_atomic(output_dir / "summary.json", json.dumps(summary, indent=2) + "\n")
            rendered = _render_geo_run_summary(summary, args.format)
            exit_code = 0 if report_validation["valid"] and task_validation["valid"] else 1
        elif args.command == "dogfood":
            target = args.url_option or args.url
            if not target:
                raise ValueError("Provide a URL or --url.")
            if args.url_option and args.url:
                raise ValueError("Provide either positional URL or --url, not both.")
            if not _is_url(target):
                raise ValueError("`agentshelf dogfood` only accepts http(s) URLs. Use `geo-run` for local files.")
            if args.max_pages < 1:
                raise ValueError("--max-pages must be at least 1.")
            output_dir = args.output_dir
            output_dir.mkdir(parents=True, exist_ok=True)
            html, fetch_metadata = _load_geo_target(target, timeout=args.timeout)
            result = build_geo_audit(
                _build_geo_config_from_args(target, args),
                html,
                robots_text=fetch_metadata["robots_text"],
                robots_status=fetch_metadata["robots_status"],
                sitemap_status=fetch_metadata["sitemap_status"],
                llms_status=fetch_metadata["llms_status"],
                raw_metadata={
                    "source_type": fetch_metadata["source_type"],
                    "fetch_warnings": fetch_metadata["fetch_warnings"],
                    "raw_html_persisted": False,
                },
            )
            report_json = render_geo_json(result)
            report_path = output_dir / "geo-report.json"
            report_md_path = output_dir / "geo-report.md"
            tasks_path = output_dir / "geo-tasks.jsonl"
            _write_text_atomic(report_path, report_json)
            _write_text_atomic(report_md_path, result.reportMarkdown)
            _write_text_atomic(tasks_path, render_geo_tasks_jsonl(json.loads(report_json)))
            report_validation = _validate_contract_file(report_path, requested_contract="agentshelf.geo_audit.v0")
            task_validation = _validate_contract_file(tasks_path, requested_contract="agentshelf.geo_task.v0")
            _write_text_atomic(output_dir / "geo-report-validation.json", json.dumps(report_validation, indent=2) + "\n")
            _write_text_atomic(output_dir / "geo-tasks-validation.json", json.dumps(task_validation, indent=2) + "\n")
            parsed = parse_input(html, fallback_title=urlparse(target).netloc or "Fetched Product Page", source=target)
            scan_bundle = scan_readiness(parsed, adapter_profile=args.profile)
            _write_text_atomic(output_dir / "scan-report.md", render_markdown(scan_bundle))
            _write_text_atomic(output_dir / "scan-report.json", json.dumps(scan_bundle, indent=2) + "\n")
            summary = _build_dogfood_summary(
                url=target,
                output_dir=output_dir,
                geo_report=json.loads(report_json),
                task_validation=task_validation,
                report_validation=report_validation,
                scan_bundle=scan_bundle,
                fetch_metadata=fetch_metadata,
            )
            _write_text_atomic(output_dir / "dogfood-notes.md", _render_dogfood_notes(summary))
            _write_text_atomic(output_dir / "summary.json", json.dumps(summary, indent=2) + "\n")
            rendered = _render_geo_run_summary(summary, args.format)
            exit_code = 0 if report_validation["valid"] and task_validation["valid"] else 1
        elif args.command == "validate-contract":
            payload = _validate_contract_file(args.path, requested_contract=args.contract)
            rendered = _render_contract_validation(payload, args.format)
            exit_code = 0 if payload["valid"] else 1
        elif args.command == "skill-info":
            payload = _build_skill_info()
            rendered = _render_skill_info(payload, args.format)
            exit_code = 0 if payload["valid"] else 1
        elif args.command == "export-skill":
            payload = _export_geo_skill(args.output_dir, force=args.force)
            rendered = _render_skill_export(payload, args.format)
            exit_code = 0 if payload["valid"] else 1
        elif args.command == "init-merchant-repo":
            payload = _init_merchant_repo(
                args.output_dir,
                brand=args.brand,
                category=args.category,
                vertical=args.vertical,
                include_skill=not args.no_skill,
                force=args.force,
            )
            rendered = _render_merchant_repo_init(payload, args.format)
            exit_code = 0 if payload["valid"] else 1
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
            if exit_code:
                failure_summary = (
                    "AgentShelf scheduled audit gate failed.\n"
                    f"Current results: {payload['current_results']}\n"
                    f"Diff report: {payload['diff_report']}\n"
                    f"Tasks output: {payload['tasks_output'] or 'not requested'}\n"
                    "Next step: inspect the diff report and run `agentshelf agent-tasks` for remediation tasks.\n"
                )
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
        elif args.command == "render-fixtures":
            platforms = list(FIXTURE_PLATFORMS) if args.platform == "all" else [args.platform]
            payload = _render_storefront_fixtures(
                products_path=args.products,
                output_dir=args.output_dir,
                platforms=platforms,
                manifest_path=args.manifest,
                input_format=args.input_format,
            )
            if args.tasks_output:
                _write_text_atomic(args.tasks_output, _render_import_remediation_tasks(payload))
            rendered = _render_fixture_summary(payload, args.format)
            exit_code = 1 if args.fail_on_warnings and payload["validation"]["warning_count"] else 0
        else:
            parser.error(f"Unsupported command: {args.command}")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    output = getattr(args, "output", None)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    if failure_summary:
        sys.stderr.write(failure_summary)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
