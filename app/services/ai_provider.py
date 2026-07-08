import os
import json
import re
import subprocess
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Protocol


@dataclass
class SalesAnswer:
    reply_thinking: str
    standard_reply: str
    references: list[dict[str, object]] = field(default_factory=list)
    recommended_materials: list[dict[str, object]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class SalesAIProvider(Protocol):
    def generate(self, question: str, context: dict[str, object]) -> SalesAnswer:
        pass


class FakeAIProvider:
    def __init__(self, standard_reply: str | None = None):
        self.standard_reply = standard_reply

    def generate(self, question: str, context: dict[str, object]) -> SalesAnswer:
        price_context = context.get("price_history", {})
        references = _collect_references(price_context)
        materials = list(context.get("materials", []))
        reply = self.standard_reply or _default_reply(question, references)
        return SalesAnswer(
            reply_thinking="已基于相关历史记录、素材和已确认话术生成回复。",
            standard_reply=reply,
            references=references,
            recommended_materials=materials,
            warnings=[],
        )


class OpenAICompatibleProvider:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        *,
        timeout: int = 60,
        transport: Callable[
            [str, str, dict[str, object], int], dict[str, object]
        ]
        | None = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.transport = transport or _curl_chat_completion

    def generate(self, question: str, context: dict[str, object]) -> SalesAnswer:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是外贸刹车片销售助手。只根据提供的上下文回答，"
                        "不要泄露报价公式、供应商成本、底价或利润空间。"
                        "必须输出 JSON，字段为 reply_thinking, standard_reply, "
                        "references, recommended_materials, warnings。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"客户问题：{question}\n\n"
                        f"上下文：{context.get('rendered_prompt') or json.dumps(context, ensure_ascii=False, default=str)}"
                    ),
                },
            ],
        }
        response_payload = self._post_chat_completion(payload)
        content = _extract_chat_content(response_payload)
        return _parse_sales_answer_json(content)

    def _post_chat_completion(self, payload: dict[str, object]) -> dict[str, object]:
        last_error: RuntimeError | None = None
        for attempt in range(3):
            try:
                return self.transport(
                    _chat_completions_url(self.base_url),
                    self.api_key,
                    payload,
                    self.timeout,
                )
            except RuntimeError as exc:
                last_error = exc
                if attempt == 2:
                    break
                time.sleep(0.5 * (attempt + 1))
        raise last_error or RuntimeError("AI provider request failed")


def generate_sales_answer(
    question: str,
    context: dict[str, object],
    provider: SalesAIProvider | None = None,
) -> SalesAnswer:
    active_provider = provider or _default_provider()
    answer = active_provider.generate(question, context)
    return _filter_sensitive_answer(answer)


def _default_provider() -> SalesAIProvider:
    provider_name = os.getenv("SALES_AI_PROVIDER", "fake").strip().lower()
    if provider_name in ("", "fake"):
        return FakeAIProvider()
    if provider_name in ("openai", "openai-compatible"):
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required when SALES_AI_PROVIDER=openai")
        return OpenAICompatibleProvider(
            api_key=api_key,
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com").strip(),
            model=os.getenv("OPENAI_MODEL", "gpt-5.5").strip(),
        )
    raise RuntimeError(f"Unsupported SALES_AI_PROVIDER: {provider_name}")


def _chat_completions_url(base_url: str) -> str:
    if base_url.endswith("/v1"):
        return f"{base_url}/chat/completions"
    return f"{base_url}/v1/chat/completions"


def _default_reply(question: str, references: list[dict[str, object]]) -> str:
    if references:
        return "已参考历史报价和成交记录，可以向客户提供正式报价并推荐相关素材。"
    return "暂未找到匹配的历史记录，建议先确认客户、型号和需求细节。"


def _collect_references(price_context: object) -> list[dict[str, object]]:
    if not isinstance(price_context, dict):
        return []

    references: list[dict[str, object]] = []
    for key in ("quotes", "contracts"):
        records = price_context.get(key, [])
        if isinstance(records, list):
            references.extend(record for record in records if isinstance(record, dict))
    return references


def _curl_chat_completion(
    url: str,
    api_key: str,
    payload: dict[str, object],
    timeout: int,
) -> dict[str, object]:
    command = [
        "curl",
        "-sS",
        "--fail-with-body",
        "--http2",
        "--max-time",
        str(timeout),
        url,
        "-H",
        f"Authorization: Bearer {api_key}",
        "-H",
        "Content-Type: application/json",
        "-H",
        "Accept: application/json",
        "--data-binary",
        "@-",
    ]
    try:
        result = subprocess.run(
            command,
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout + 5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"AI provider request failed: {exc}") from exc

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"AI provider request failed: {detail}")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("AI provider response is not valid JSON") from exc


def _extract_chat_content(payload: dict[str, object]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("AI provider response missing choices")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise RuntimeError("AI provider response has invalid choice")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("AI provider response missing message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("AI provider response missing content")
    return content


def _parse_sales_answer_json(content: str) -> SalesAnswer:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        return SalesAnswer(
            reply_thinking="模型返回了自然语言回复。",
            standard_reply=content.strip(),
        )

    return SalesAnswer(
        reply_thinking=str(payload.get("reply_thinking") or ""),
        standard_reply=str(payload.get("standard_reply") or ""),
        references=_list_of_dicts(payload.get("references")),
        recommended_materials=_list_of_dicts(payload.get("recommended_materials")),
        warnings=_list_of_strings(payload.get("warnings")),
    )


def _list_of_dicts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _list_of_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


SENSITIVE_TERMS = (
    "报价公式",
    "供应商成本",
    "底价",
    "最低价",
    "利润空间",
    "毛利",
    "利润率",
    "成本价",
    "supplier cost",
    "supplier costs",
    "suppliers cost",
    "bottom price",
    "floor price",
    "cost basis",
    "profit margin",
    "pricing formula",
)


def _filter_sensitive_answer(answer: SalesAnswer) -> SalesAnswer:
    if not _contains_sensitive_term(answer.standard_reply):
        return answer

    warnings = list(answer.warnings)
    warnings.append("标准回复包含敏感内部信息，已移除敏感内容并替换为安全表达。")
    return SalesAnswer(
        reply_thinking=answer.reply_thinking,
        standard_reply="已参考历史成交记录，可向客户提供正式报价；内部测算信息不对外披露。",
        references=answer.references,
        recommended_materials=answer.recommended_materials,
        warnings=warnings,
    )


def _contains_sensitive_term(text: str) -> bool:
    normalized = _normalize_for_sensitive_matching(text)
    return any(
        _normalize_for_sensitive_matching(term) in normalized for term in SENSITIVE_TERMS
    )


def _normalize_for_sensitive_matching(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)
