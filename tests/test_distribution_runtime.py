from app.services.distribution_runtime import (
    build_provider_from_runtime_config,
    fetch_runtime_distribution_config,
)


def test_fetch_runtime_distribution_config_reads_distribution_endpoint():
    calls = []

    def fake_transport(url, timeout):
        calls.append((url, timeout))
        return {
            "distributionId": "dist_123",
            "status": "enabled",
            "app": {"name": "AI QA", "url": "http://example.test/qa"},
            "model": {
                "provider": "openai",
                "model": "gpt-5.5",
                "apiBaseUrl": "https://token-gpt.top/v1",
                "apiKey": "sk-runtime",
                "enabled": True,
                "parameters": {"temperature": 0.3, "maxTokens": 1024},
            },
        }

    config = fetch_runtime_distribution_config(
        "dist_123",
        base_url="http://runtime.test/api/runtime/distributions",
        transport=fake_transport,
        timeout=7,
    )

    assert calls == [("http://runtime.test/api/runtime/distributions/dist_123", 7)]
    assert config["distributionId"] == "dist_123"
    assert config["model"]["parameters"]["maxTokens"] == 1024


def test_build_provider_from_runtime_config_uses_model_and_parameters():
    requests = []

    def fake_chat_transport(url, api_key, payload, timeout):
        requests.append((url, api_key, payload, timeout))
        return {"choices": [{"message": {"content": '{"standard_reply":"ok"}'}}]}

    provider = build_provider_from_runtime_config(
        {
            "distributionId": "dist_123",
            "status": "enabled",
            "app": {"name": "AI QA", "url": "http://example.test/qa"},
            "model": {
                "provider": "openai",
                "model": "gpt-5.5",
                "apiBaseUrl": "https://token-gpt.top/v1",
                "apiKey": "sk-runtime",
                "enabled": True,
                "parameters": {"temperature": 0.3, "maxTokens": 1024},
            },
        },
        chat_transport=fake_chat_transport,
    )

    answer = provider.generate("客户问价格怎么回复？", {"rendered_prompt": "prompt"})

    assert answer.standard_reply == "ok"
    url, api_key, payload, timeout = requests[0]
    assert url == "https://token-gpt.top/v1/chat/completions"
    assert api_key == "sk-runtime"
    assert timeout == 60
    assert payload["model"] == "gpt-5.5"
    assert payload["temperature"] == 0.3
    assert payload["max_tokens"] == 1024


def test_build_provider_accepts_token_gpt_and_falls_back_to_env_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    requests = []

    def fake_chat_transport(url, api_key, payload, timeout):
        requests.append((url, api_key, payload, timeout))
        return {"choices": [{"message": {"content": '{"standard_reply":"ok"}'}}]}

    provider = build_provider_from_runtime_config(
        {
            "distributionId": "dist_123",
            "status": "enabled",
            "app": {"name": "AI QA", "url": "http://example.test/qa"},
            "model": {
                "provider": "token-gpt",
                "model": "gpt-5.5",
                "apiBaseUrl": "https://token-gpt.top/v1",
                "apiKey": "",
                "enabled": True,
                "parameters": {"maxTokens": 4096},
            },
        },
        chat_transport=fake_chat_transport,
    )

    provider.generate("客户问价格怎么回复？", {"rendered_prompt": "prompt"})

    url, api_key, payload, timeout = requests[0]
    assert url == "https://token-gpt.top/v1/chat/completions"
    assert api_key == "sk-env"
    assert payload["model"] == "gpt-5.5"
    assert payload["max_tokens"] == 4096
