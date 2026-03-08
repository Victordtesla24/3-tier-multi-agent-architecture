#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

# Override sandbox paths to avoid PermissionError on macOS
os.environ["HOME"] = "/tmp/sandbox_home"
os.environ["XDG_DATA_HOME"] = "/tmp/sandbox_home"
os.environ["XDG_CACHE_HOME"] = "/tmp/sandbox_home"
os.environ["XDG_CONFIG_HOME"] = "/tmp/sandbox_home"


def load_env(env_path: Path) -> dict[str, str]:
    env_vars: dict[str, str] = {}
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env_vars[key.strip()] = value.strip().strip("'\"")
    return env_vars


def print_result(success: bool, details: str = "") -> None:
    marker = "✅ SUCCESS" if success else "❌ FAIL"
    print(f"  {marker} {details}".rstrip())


def prompt_for_value(label: str, env_key: str, env_vars: dict[str, str]) -> str | None:
    existing = env_vars.get(env_key)
    if existing:
        masked = existing[:6] + "..." + existing[-4:] if len(existing) > 10 else "***"
        print(f"\n[{label}] Found `{env_key}` in .env: {masked}")
    else:
        print(f"\n[{label}] No `{env_key}` found in .env.")

    value = input("Enter new value (or press Enter to use existing/skip): ").strip()
    return value or existing


def test_openai_compatible(
    provider_name: str,
    base_url: str,
    api_key: str,
    model_name: str,
) -> None:
    print(f"Testing {provider_name} model: '{model_name}'")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(
            {
                "model": model_name,
                "messages": [{"role": "user", "content": "Return exactly ACK."}],
                "max_completion_tokens": 16,
            }
        ).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
            preview = json.dumps(payload)[:160]
            print_result(True, preview)
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        print_result(False, f"(HTTP {exc.code}) {error_body[:200]}")
    except Exception as exc:
        print_result(False, f"({type(exc).__name__}: {exc})")


def test_gemini(api_key: str, model_name: str) -> None:
    print(f"Testing Google Gemini model: '{model_name}'")
    request = urllib.request.Request(
        (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model_name}:generateContent?key={api_key}"
        ),
        data=json.dumps(
            {"contents": [{"parts": [{"text": "Return exactly ACK."}]}]}
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
            preview = json.dumps(payload)[:160]
            print_result(True, preview)
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        print_result(False, f"(HTTP {exc.code}) {error_body[:200]}")
    except Exception as exc:
        print_result(False, f"({type(exc).__name__}: {exc})")


def test_ollama(base_url: str, model_name: str) -> None:
    print(f"Testing Ollama model: '{model_name}'")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/generate",
        data=json.dumps(
            {
                "model": model_name,
                "prompt": "Return exactly ACK.",
                "stream": False,
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
            preview = str(payload.get("response", "")).strip()[:120]
            print_result(True, preview)
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        print_result(False, f"(HTTP {exc.code}) {error_body[:200]}")
    except Exception as exc:
        print_result(False, f"({type(exc).__name__}: {exc})")


def main() -> None:
    print("=" * 60)
    print("Interactive Runtime Provider Verifier")
    print("Verifies the active OpenAI, Google, DeepSeek, and Ollama runtime surfaces")
    print("=" * 60)

    env_path = Path(
        "/Users/Shared/antigravity/3-tier-multi-agent-architecture-work/.env"
    )
    env_vars = load_env(env_path)

    openai_key = prompt_for_value("OpenAI", "OPENAI_API_KEY", env_vars)
    if openai_key:
        test_openai_compatible(
            "OpenAI", "https://api.openai.com/v1", openai_key, "gpt-5.4"
        )
        test_openai_compatible(
            "OpenAI", "https://api.openai.com/v1", openai_key, "gpt-5.2-codex"
        )

    google_key = prompt_for_value("Google Gemini", "GOOGLE_API_KEY", env_vars)
    if google_key:
        test_gemini(google_key, "gemini-3.1-pro-preview")
        test_gemini(google_key, "gemini-2.5-flash")

    deepseek_key = prompt_for_value("DeepSeek", "DEEPSEEK_API_KEY", env_vars)
    if deepseek_key:
        deepseek_base_url = (
            prompt_for_value("DeepSeek Base URL", "DEEPSEEK_BASE_URL", env_vars)
            or "https://api.deepseek.com/v1"
        )
        test_openai_compatible(
            "DeepSeek",
            deepseek_base_url,
            deepseek_key,
            "deepseek-chat",
        )

    ollama_base_url = (
        prompt_for_value("Ollama", "OLLAMA_BASE_URL", env_vars)
        or "http://127.0.0.1:11434"
    )
    for model_name in (
        "qwen3:14b",
        "qwen3:8b",
        "qwen2.5-coder:14b",
        "qwen2.5-coder:7b",
    ):
        test_ollama(ollama_base_url, model_name)

    print("\nVerification process completed.")


if __name__ == "__main__":
    main()
