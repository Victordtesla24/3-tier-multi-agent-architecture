from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"

if TYPE_CHECKING:
    from engine.runtime_env import ConfiguredProviderInventory


def _bootstrap_src_path() -> None:
    src_root = str(SRC_ROOT)
    if src_root not in sys.path:
        sys.path.insert(0, src_root)


def probe_configured_providers(workspace: Path, project_root: Path):
    _bootstrap_src_path()
    from engine.provider_healthchecks import (
        probe_configured_providers as _probe_configured_providers,
    )

    return _probe_configured_providers(workspace, project_root)


def _is_placeholder(value: str | None) -> bool:
    if value is None:
        return True
    cleaned = value.strip().lower()
    return not cleaned or cleaned.startswith("your_") or cleaned in {"none", "null"}


def _provider_status_lines(keys: tuple[str, ...]) -> list[str]:
    lines: list[str] = []
    for key in keys:
        value = None
        if key == "GOOGLE_API_KEY":
            for alias in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
                value = os.environ.get(alias)
                if value:
                    break
        else:
            value = os.environ.get(key)

        status = (
            "configured" if not _is_placeholder(value) else "missing_or_placeholder"
        )
        lines.append(f"- {key}: {status}")
    return lines


def _configured_provider_inventory_lines(
    providers: tuple["ConfiguredProviderInventory", ...],
) -> list[str]:
    lines: list[str] = []
    for provider in providers:
        api_sources = ", ".join(provider.configured_api_key_keys) or "not_present"
        base_sources = ", ".join(provider.configured_base_url_keys) or "default"
        api_status = (
            "not_required"
            if provider.api_key_env is None
            else (
                "configured"
                if provider.api_key_configured
                else "missing_or_placeholder"
            )
        )
        base_url = provider.resolved_base_url or "n/a"
        lines.append(
            f"- {provider.provider_group}: api_key_env={provider.api_key_env or 'not_required'} "
            f"api_key_sources={api_sources} api_key_status={api_status} "
            f"base_url_env={provider.base_url_env or 'n/a'} "
            f"base_url_sources={base_sources} resolved_base_url={base_url}"
        )
    return lines


def _print_structural_audit(workspace: Path, project_root: Path) -> tuple[int, object]:
    _bootstrap_src_path()
    from engine.runtime_env import EnvConfigError, resolve_runtime_env

    try:
        runtime_env = resolve_runtime_env(workspace, project_root=project_root)
    except EnvConfigError as exc:
        print(f"CONFIG_ERROR: {exc}")
        return 1, None

    print("EFFECTIVE_TIER_MATRIX")
    for tier_name, logical_id in runtime_env.tier_primary_logical_ids().items():
        print(f"- {tier_name}: {logical_id}")

    print("FALLBACK_TOPOLOGY")
    for tier_name, logical_id in runtime_env.tier_fallback_logical_ids().items():
        print(f"- {tier_name}: {logical_id}")

    print("SWARM_CAPS")
    print(f"- level2: {runtime_env.swarm.level2}")
    print(f"- level3: {runtime_env.swarm.level3}")

    print("ACTIVE_PROVIDER_ENV_KEYS")
    for key in runtime_env.active_provider_env_keys:
        print(f"- {key}")

    print("PROVIDER_STATUS")
    for line in _provider_status_lines(runtime_env.active_provider_env_keys):
        print(line)

    print("CONFIGURED_PROVIDER_INVENTORY")
    for line in _configured_provider_inventory_lines(runtime_env.configured_providers):
        print(line)

    print("WARNINGS")
    if runtime_env.warnings:
        for warning in runtime_env.warnings:
            print(f"- {warning}")
    else:
        print("- none")

    return 0, runtime_env


def _probe_live_tiers(runtime_env) -> int:
    _bootstrap_src_path()
    try:
        from engine.llm_config import build_llm, resolved_model_specs
    except ModuleNotFoundError as exc:
        print("LIVE_PROBES")
        print(
            f"- skipped: {type(exc).__name__}: {exc}. Install optional runtime "
            "dependencies to enable live tier probes."
        )
        return 0

    print("LIVE_PROBES")
    specs = resolved_model_specs(runtime_env)
    tier_specs = {
        "orchestration": specs[0],
        "level1": specs[2],
        "level2": specs[4],
        "level3": specs[6],
    }

    exit_code = 0
    for tier_name, spec in tier_specs.items():
        try:
            llm = build_llm(spec)
            response = llm.call([{"role": "user", "content": "Return exactly OK."}])
            preview = str(response).strip().replace("\n", " ")[:80]
            print(f"- {tier_name}: ok [{spec.logical_id}] response={preview!r}")
        except Exception as exc:
            exit_code = 1
            print(
                f"- {tier_name}: error [{spec.logical_id}] {type(exc).__name__}: {exc}"
            )
    return exit_code


def _probe_configured_provider_inventory(workspace: Path, project_root: Path):
    print("CONFIGURED_PROVIDER_PROBES")
    results = probe_configured_providers(workspace, project_root)
    exit_code = 0
    for result in results:
        target = result.target
        status_text = "ok" if result.success else "error"
        line = (
            f"- {target.provider_id}.{target.probe_name}: {status_text} "
            f"[{target.model or target.provider_group}] "
            f"http_status={result.http_status} latency_ms={result.latency_ms} "
            f"classification={result.failure_classification or 'none'} "
            f"endpoint={target.endpoint} preview={result.response_preview!r}"
        )
        print(line)
        if not result.success:
            exit_code = 1
    return exit_code, results


def _write_report(
    report_path: Path,
    *,
    workspace: Path,
    project_root: Path,
    runtime_env,
    provider_probe_results,
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "workspace": str(workspace),
        "project_root": str(project_root),
        "effective_tier_matrix": runtime_env.tier_primary_logical_ids(),
        "fallback_topology": runtime_env.tier_fallback_logical_ids(),
        "swarm_caps": {
            "level2": runtime_env.swarm.level2,
            "level3": runtime_env.swarm.level3,
        },
        "active_provider_env_keys": list(runtime_env.active_provider_env_keys),
        "warnings": list(runtime_env.warnings),
        "configured_providers": [
            asdict(provider) for provider in runtime_env.configured_providers
        ],
        "provider_probe_results": [
            result.to_dict() for result in provider_probe_results
        ],
    }
    report_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit the effective Antigravity runtime env."
    )
    parser.add_argument(
        "--workspace", default=".", help="Workspace directory containing .env"
    )
    parser.add_argument(
        "--project-root",
        default=str(Path(__file__).resolve().parent.parent),
        help="Project root used for fallback .env loading",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Probe the active primary tiers with a minimal live LLM call.",
    )
    parser.add_argument(
        "--probe-configured-providers",
        action="store_true",
        help="Probe every configured provider credential discovered in .env, including inactive providers.",
    )
    parser.add_argument(
        "--report-path",
        help="Optional JSON output path for the structural audit and configured-provider probe results.",
    )
    args = parser.parse_args(argv)

    workspace = Path(args.workspace).resolve()
    project_root = Path(args.project_root).resolve()

    status, runtime_env = _print_structural_audit(workspace, project_root)
    if status != 0 or runtime_env is None:
        return status

    live_status = _probe_live_tiers(runtime_env) if args.live else 0
    provider_probe_status = 0
    provider_probe_results = ()
    if args.probe_configured_providers:
        provider_probe_status, provider_probe_results = (
            _probe_configured_provider_inventory(
                workspace,
                project_root,
            )
        )

    if args.report_path:
        _write_report(
            Path(args.report_path).resolve(),
            workspace=workspace,
            project_root=project_root,
            runtime_env=runtime_env,
            provider_probe_results=provider_probe_results,
        )

    return 1 if any((status, live_status, provider_probe_status)) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
