import json
import os
import subprocess
from typing import Callable

from app.services.ai_provider import OpenAICompatibleProvider, SalesAIProvider


DEFAULT_RUNTIME_BASE_URL = "http://175.27.141.107/dist/api/runtime/distributions"


RuntimeTransport = Callable[[str, int], dict[str, object]]


def fetch_runtime_distribution_config(
    distribution_id: str,
    *,
    base_url: str = DEFAULT_RUNTIME_BASE_URL,
    transport: RuntimeTransport | None = None,
    timeout: int = 10,
) -> dict[str, object]:
    runtime_url = f"{base_url.rstrip('/')}/{distribution_id}"
    active_transport = transport or _curl_json
    return active_transport(runtime_url, timeout)


def provider_from_distribution(distribution_id: str) -> SalesAIProvider:
    config = fetch_runtime_distribution_config(distribution_id)
    return build_provider_from_runtime_config(config)


def build_provider_from_runtime_config(
    config: dict[str, object],
    *,
    chat_transport=None,
) -> SalesAIProvider:
    model = config.get("model")
    if not isinstance(model, dict):
        raise RuntimeError("Distribution runtime config missing model")
    if model.get("enabled") is not True:
        raise RuntimeError("Distribution model config is disabled")

    provider_name = str(model.get("provider") or "").strip().lower()
    if provider_name not in {"openai", "openai-compatible", "token-gpt"}:
        raise RuntimeError(f"Unsupported distribution model provider: {provider_name}")

    api_key = str(model.get("apiKey") or "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Distribution runtime config missing model apiKey")

    parameters = model.get("parameters")
    return OpenAICompatibleProvider(
        api_key=api_key,
        base_url=str(model.get("apiBaseUrl") or "").strip(),
        model=str(model.get("model") or "").strip(),
        parameters=parameters if isinstance(parameters, dict) else {},
        transport=chat_transport,
    )


def _curl_json(url: str, timeout: int) -> dict[str, object]:
    command = [
        "curl",
        "-sS",
        "--fail-with-body",
        "--max-time",
        str(timeout),
        url,
        "-H",
        "Accept: application/json",
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout + 5,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Distribution runtime request failed: {detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Distribution runtime response is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Distribution runtime response is not an object")
    return payload
