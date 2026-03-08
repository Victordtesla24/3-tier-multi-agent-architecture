from __future__ import annotations

import json
import os
import socket
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib import error, parse, request

from engine.runtime_env import (
    ConfiguredProviderInventory,
    resolve_runtime_env,
)


@dataclass(frozen=True)
class ProviderProbeTarget:
    provider_id: str
    provider_group: str
    probe_name: str
    method: str
    endpoint: str
    model: str | None = None


@dataclass(frozen=True)
class ProviderProbeResult:
    target: ProviderProbeTarget
    api_key_env: str | None
    configured_api_key_keys: tuple[str, ...]
    base_url_env: str | None
    configured_base_url_keys: tuple[str, ...]
    resolved_base_url: str | None
    canonical_base_url: str | None
    success: bool
    failure_classification: str | None
    http_status: int | None
    latency_ms: int
    response_preview: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_OPENAI_PROMPT = {
    "messages": [{"role": "user", "content": "Return exactly ACK."}],
    "max_tokens": 8,
}

_GEMINI_PROMPT = {
    "contents": [{"parts": [{"text": "Return exactly ACK."}]}],
}

_PROVIDER_ID_BY_GROUP = {
    "OpenAI": "openai",
    "Google AI": "google",
    "DeepSeek": "deepseek",
    "Ollama": "ollama",
}

_CANONICAL_BASE_URL_BY_PROVIDER_ID = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
}


def _mask_preview(payload: str, secrets: tuple[str, ...]) -> str:
    preview = " ".join(payload.split())[:240]
    for secret in secrets:
        if secret:
            preview = preview.replace(secret, "[REDACTED]")
    return preview


def _canonical_openai_compatible_endpoint(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/chat/completions"


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout_s: float,
) -> tuple[int | None, str, int]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, headers=headers, method="POST")
    started = perf_counter()
    try:
        with request.urlopen(req, timeout=timeout_s) as response:
            raw_body = response.read().decode("utf-8", "replace")
            return response.status, raw_body, int((perf_counter() - started) * 1000)
    except error.HTTPError as exc:
        raw_body = exc.read().decode("utf-8", "replace")
        return exc.code, raw_body, int((perf_counter() - started) * 1000)


def _get(
    url: str,
    *,
    headers: dict[str, str],
    timeout_s: float,
) -> tuple[int | None, str, int]:
    req = request.Request(url, headers=headers, method="GET")
    started = perf_counter()
    try:
        with request.urlopen(req, timeout=timeout_s) as response:
            raw_body = response.read().decode("utf-8", "replace")
            return response.status, raw_body, int((perf_counter() - started) * 1000)
    except error.HTTPError as exc:
        raw_body = exc.read().decode("utf-8", "replace")
        return exc.code, raw_body, int((perf_counter() - started) * 1000)


def _classify_failure(http_status: int | None, payload: str) -> str:
    lowered = payload.lower()
    if "timed out" in lowered:
        return "timeout"
    if any(
        marker in lowered
        for marker in (
            "connection refused",
            "failed to establish a new connection",
            "nodename nor servname provided",
            "name or service not known",
        )
    ):
        return "endpoint_unreachable"
    if (
        "model" in lowered
        and "not found" in lowered
        or "not supported for generatecontent" in lowered
        or "unsupported model" in lowered
    ):
        return "model_unavailable"
    if http_status in (401, 403) or any(
        marker in lowered
        for marker in (
            "authentication failed",
            "invalid authentication",
            "invalid api key",
            "unauthorized",
            "forbidden",
            "authorized_error",
        )
    ):
        return "auth_invalid"
    if http_status == 404 or any(
        marker in lowered
        for marker in (
            "no route matched",
            "route not found",
            "invalid url",
            "unsupported path",
            "unknown path",
        )
    ):
        return "endpoint_misconfigured"
    return "unknown"


def _timeout_result(
    inventory: ConfiguredProviderInventory,
    target: ProviderProbeTarget,
    *,
    preview: str,
    latency_ms: int,
) -> ProviderProbeResult:
    return ProviderProbeResult(
        target=target,
        api_key_env=inventory.api_key_env,
        configured_api_key_keys=inventory.configured_api_key_keys,
        base_url_env=inventory.base_url_env,
        configured_base_url_keys=inventory.configured_base_url_keys,
        resolved_base_url=inventory.resolved_base_url,
        canonical_base_url=inventory.canonical_base_url,
        success=False,
        failure_classification="timeout",
        http_status=None,
        latency_ms=latency_ms,
        response_preview=preview,
    )


def _result_from_response(
    inventory: ConfiguredProviderInventory,
    target: ProviderProbeTarget,
    *,
    http_status: int | None,
    raw_payload: str,
    latency_ms: int,
    secrets: tuple[str, ...],
) -> ProviderProbeResult:
    success = http_status is not None and 200 <= http_status < 300
    return ProviderProbeResult(
        target=target,
        api_key_env=inventory.api_key_env,
        configured_api_key_keys=inventory.configured_api_key_keys,
        base_url_env=inventory.base_url_env,
        configured_base_url_keys=inventory.configured_base_url_keys,
        resolved_base_url=inventory.resolved_base_url,
        canonical_base_url=inventory.canonical_base_url,
        success=success,
        failure_classification=(
            None if success else _classify_failure(http_status, raw_payload)
        ),
        http_status=http_status,
        latency_ms=latency_ms,
        response_preview=_mask_preview(raw_payload, secrets),
    )


def _probe_openai_compatible_provider(
    inventory: ConfiguredProviderInventory,
    *,
    model: str,
    timeout_s: float,
) -> ProviderProbeResult:
    if inventory.api_key_env is None:
        raise RuntimeError(
            f"{inventory.provider_group} is not an API-key provider and cannot use the "
            "OpenAI-compatible probe path."
        )
    api_key = os.environ.get(inventory.api_key_env, "").strip()
    provider_id = _PROVIDER_ID_BY_GROUP[inventory.provider_group]
    target = ProviderProbeTarget(
        provider_id=provider_id,
        provider_group=inventory.provider_group,
        probe_name="chat_completions",
        method="POST",
        endpoint=_canonical_openai_compatible_endpoint(
            inventory.resolved_base_url
            or inventory.canonical_base_url
            or _CANONICAL_BASE_URL_BY_PROVIDER_ID.get(provider_id, "")
        ),
        model=model,
    )
    if not inventory.api_key_configured or not api_key:
        return _result_from_response(
            inventory,
            target,
            http_status=None,
            raw_payload="Credential missing or placeholder.",
            latency_ms=0,
            secrets=(),
        )

    payload = dict(_OPENAI_PROMPT)
    payload["model"] = model
    try:
        http_status, raw_body, latency_ms = _post_json(
            target.endpoint,
            payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            timeout_s=timeout_s,
        )
    except (TimeoutError, socket.timeout) as exc:
        return _timeout_result(
            inventory,
            target,
            preview=_mask_preview(str(exc), (api_key,)),
            latency_ms=int(timeout_s * 1000),
        )
    except error.URLError as exc:
        reason = str(exc.reason)
        if "timed out" in reason.lower():
            return _timeout_result(
                inventory,
                target,
                preview=_mask_preview(reason, (api_key,)),
                latency_ms=int(timeout_s * 1000),
            )
        return _result_from_response(
            inventory,
            target,
            http_status=None,
            raw_payload=reason,
            latency_ms=int(timeout_s * 1000),
            secrets=(api_key,),
        )

    return _result_from_response(
        inventory,
        target,
        http_status=http_status,
        raw_payload=raw_body,
        latency_ms=latency_ms,
        secrets=(api_key,),
    )


def _probe_google_provider(
    inventory: ConfiguredProviderInventory,
    *,
    timeout_s: float,
) -> tuple[ProviderProbeResult, ...]:
    api_key = (
        os.environ.get(inventory.api_key_env, "").strip()
        if inventory.api_key_env is not None
        else ""
    )
    provider_id = _PROVIDER_ID_BY_GROUP[inventory.provider_group]
    if not inventory.api_key_configured or not api_key:
        missing_targets = (
            ProviderProbeTarget(
                provider_id=provider_id,
                provider_group=inventory.provider_group,
                probe_name="models_list",
                method="GET",
                endpoint="https://generativelanguage.googleapis.com/v1beta/models",
            ),
            ProviderProbeTarget(
                provider_id=provider_id,
                provider_group=inventory.provider_group,
                probe_name="generate_content",
                method="POST",
                endpoint=(
                    "https://generativelanguage.googleapis.com/v1beta/models/"
                    "gemini-3.1-pro-preview:generateContent"
                ),
                model="gemini-3.1-pro-preview",
            ),
        )
        return tuple(
            _result_from_response(
                inventory,
                target,
                http_status=None,
                raw_payload="Credential missing or placeholder.",
                latency_ms=0,
                secrets=(),
            )
            for target in missing_targets
        )

    list_target = ProviderProbeTarget(
        provider_id=provider_id,
        provider_group=inventory.provider_group,
        probe_name="models_list",
        method="GET",
        endpoint="https://generativelanguage.googleapis.com/v1beta/models",
    )
    generate_target = ProviderProbeTarget(
        provider_id=provider_id,
        provider_group=inventory.provider_group,
        probe_name="generate_content",
        method="POST",
        endpoint=(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-3.1-pro-preview:generateContent"
        ),
        model="gemini-3.1-pro-preview",
    )
    query_key = parse.quote(api_key, safe="")

    results: list[ProviderProbeResult] = []
    try:
        status, body, latency_ms = _get(
            f"{list_target.endpoint}?key={query_key}",
            headers={},
            timeout_s=timeout_s,
        )
        results.append(
            _result_from_response(
                inventory,
                list_target,
                http_status=status,
                raw_payload=body,
                latency_ms=latency_ms,
                secrets=(api_key,),
            )
        )
    except (TimeoutError, socket.timeout) as exc:
        results.append(
            _timeout_result(
                inventory,
                list_target,
                preview=_mask_preview(str(exc), (api_key,)),
                latency_ms=int(timeout_s * 1000),
            )
        )
    except error.URLError as exc:
        reason = str(exc.reason)
        results.append(
            _result_from_response(
                inventory,
                list_target,
                http_status=None,
                raw_payload=reason,
                latency_ms=int(timeout_s * 1000),
                secrets=(api_key,),
            )
        )

    try:
        status, body, latency_ms = _post_json(
            f"{generate_target.endpoint}?key={query_key}",
            _GEMINI_PROMPT,
            headers={"Content-Type": "application/json"},
            timeout_s=timeout_s,
        )
        results.append(
            _result_from_response(
                inventory,
                generate_target,
                http_status=status,
                raw_payload=body,
                latency_ms=latency_ms,
                secrets=(api_key,),
            )
        )
    except (TimeoutError, socket.timeout) as exc:
        results.append(
            _timeout_result(
                inventory,
                generate_target,
                preview=_mask_preview(str(exc), (api_key,)),
                latency_ms=int(timeout_s * 1000),
            )
        )
    except error.URLError as exc:
        reason = str(exc.reason)
        results.append(
            _result_from_response(
                inventory,
                generate_target,
                http_status=None,
                raw_payload=reason,
                latency_ms=int(timeout_s * 1000),
                secrets=(api_key,),
            )
        )
    return tuple(results)


def _probe_ollama_provider(
    inventory: ConfiguredProviderInventory,
    *,
    timeout_s: float,
) -> ProviderProbeResult:
    base_url = (inventory.resolved_base_url or inventory.canonical_base_url or "").rstrip(
        "/"
    )
    endpoint = f"{base_url}/api/tags"
    target = ProviderProbeTarget(
        provider_id="ollama",
        provider_group=inventory.provider_group,
        probe_name="tags",
        method="GET",
        endpoint=endpoint,
    )

    try:
        status, body, latency_ms = _get(endpoint, headers={}, timeout_s=timeout_s)
    except (TimeoutError, socket.timeout) as exc:
        return _timeout_result(
            inventory,
            target,
            preview=_mask_preview(str(exc), ()),
            latency_ms=int(timeout_s * 1000),
        )
    except error.URLError as exc:
        return _result_from_response(
            inventory,
            target,
            http_status=None,
            raw_payload=str(exc.reason),
            latency_ms=int(timeout_s * 1000),
            secrets=(),
        )

    return _result_from_response(
        inventory,
        target,
        http_status=status,
        raw_payload=body,
        latency_ms=latency_ms,
        secrets=(),
    )


def probe_configured_providers(
    workspace_dir: Path,
    project_root: Path,
    timeout_s: float = 20.0,
) -> tuple[ProviderProbeResult, ...]:
    runtime_env = resolve_runtime_env(workspace_dir, project_root=project_root)
    results: list[ProviderProbeResult] = []

    for inventory in runtime_env.configured_providers:
        if inventory.provider_group == "OpenAI":
            results.append(
                _probe_openai_compatible_provider(
                    inventory,
                    model="gpt-4o-mini",
                    timeout_s=timeout_s,
                )
            )
        elif inventory.provider_group == "Google AI":
            results.extend(_probe_google_provider(inventory, timeout_s=timeout_s))
        elif inventory.provider_group == "DeepSeek":
            results.append(
                _probe_openai_compatible_provider(
                    inventory,
                    model="deepseek-chat",
                    timeout_s=timeout_s,
                )
            )
        elif inventory.provider_group == "Ollama":
            results.append(_probe_ollama_provider(inventory, timeout_s=timeout_s))

    return tuple(results)
