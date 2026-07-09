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
        references = _collect_references(context)
        materials = list(context.get("materials", []))
        agent_plan = context.get("agent_plan", {})
        reply = self.standard_reply or _default_reply(question, references, materials, agent_plan)
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
        parameters: dict[str, object] | None = None,
        timeout: int = 60,
        transport: Callable[
            [str, str, dict[str, object], int], dict[str, object]
        ]
        | None = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.parameters = _normalize_generation_parameters(parameters or {})
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
        payload.update(self.parameters)
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


def _normalize_generation_parameters(parameters: dict[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in parameters.items():
        if value is None:
            continue
        normalized_key = "max_tokens" if key == "maxTokens" else key
        normalized[normalized_key] = value
    return normalized


def _default_reply(
    question: str,
    references: list[dict[str, object]],
    materials: list[object],
    agent_plan: object,
) -> str:
    if isinstance(agent_plan, dict):
        intents = agent_plan.get("intents", [])
        if isinstance(intents, list) and "missing_information" in intents:
            missing_fields = [
                str(field)
                for field in agent_plan.get("missing_fields", [])
                if field is not None
            ]
            fields_text = "、".join(missing_fields) or "型号/OE号、数量、包装要求、目的港/国家、贸易条款"
            return (
                "为了给客户准确报价，请先确认"
                f"{fields_text}。可以回复客户：Please send the part number/OE number, "
                "quantity, packing requirement, destination country or port, and trade terms, "
                "then we will check and offer the accurate price."
            )
        if (
            isinstance(intents, list)
            and "material_recommendation" in intents
            and materials
        ):
            first_material = materials[0] if isinstance(materials[0], dict) else {}
            brand = first_material.get("brand") or first_material.get("name") or "the requested"
            material_type = "视频" if first_material.get("material_type") == "video" else "图片"
            if agent_plan.get("language") != "en":
                return (
                    f"已匹配到 {brand} 的相关{material_type}素材。可以回复客户："
                    f"我把 {brand} 的{material_type}素材发给您参考，里面可以看到包装/产品细节。"
                    "如果您有具体型号或包装要求，也可以发给我，我再帮您匹配对应资料。"
                )
            return (
                f"Sure, I will send you the {brand} packaging material for your reference. "
                "You can check the packing style, product appearance, and details in the video. "
                "If you have a specific part number, please send it to me and I will match the exact material."
            )
    if isinstance(agent_plan, dict):
        intents = agent_plan.get("intents", [])
        if isinstance(intents, list) and "order_compare" in intents:
            return "已对比该客户历史订单。相同型号可参考历史配置；新增型号或配置变化需要重新核价后再回复客户。"
    if references:
        return "已参考历史报价和成交记录，可以向客户提供正式报价并推荐相关素材。"
    return "暂未找到匹配的历史记录，建议先确认客户、型号和需求细节。"


def _collect_references(context: object) -> list[dict[str, object]]:
    if not isinstance(context, dict):
        return []

    references: list[dict[str, object]] = []
    price_context = context.get("price_history", {})
    for key in ("quotes", "contracts"):
        records = price_context.get(key, []) if isinstance(price_context, dict) else []
        if isinstance(records, list):
            references.extend(record for record in records if isinstance(record, dict))
    order_comparison = context.get("order_comparison", {})
    order_items = order_comparison.get("items", []) if isinstance(order_comparison, dict) else []
    if isinstance(order_items, list):
        references.extend(
            {
                "source": "order_compare",
                "part_number": item.get("part_number"),
                "status": item.get("status"),
                "needs_requote": item.get("needs_requote"),
            }
            for item in order_items
            if isinstance(item, dict)
        )
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
