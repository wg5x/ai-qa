import base64
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.config import PROJECT_ROOT
from app.services.ai_provider import _chat_completions_url
from app.services.distribution_runtime import fetch_runtime_distribution_config


@dataclass
class MediaAnalysis:
    visual_summary: str = ""
    ocr_text: str = ""
    transcript_text: str = ""
    tags: list[str] = field(default_factory=list)
    confidence: str = "low"
    frame_paths: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


ChatTransport = Callable[[str, str, dict[str, object], int], dict[str, object]]

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi"}
SIDECAR_SUFFIXES = (".txt", ".srt", ".vtt")
DEFAULT_VIDEO_MODEL = "gemini-3.1-pro"


def analyze_media(
    file_path: Path,
    *,
    material_type: str,
    distribution_id: str | None = None,
    chat_transport: ChatTransport | None = None,
) -> MediaAnalysis:
    transcript_text = read_sidecar_text(file_path)
    frame_paths: list[Path] = []
    visual_inputs = [file_path]
    if material_type == "video":
        frame_paths = extract_video_frames(file_path)
        visual_inputs = frame_paths

    visual = _call_visual_model(
        visual_inputs,
        material_type=material_type,
        transcript_text=transcript_text,
        distribution_id=distribution_id,
        chat_transport=chat_transport,
    )
    visual.transcript_text = transcript_text
    visual.frame_paths = frame_paths
    if transcript_text and "transcript" not in visual.tags:
        visual.tags.append("transcript")
    if frame_paths and "视频抽帧" not in visual.tags:
        visual.tags.append("视频抽帧")
    return visual


def extract_video_frames(
    file_path: Path,
    *,
    output_dir: Path | None = None,
    max_frames: int = 3,
) -> list[Path]:
    output = output_dir or _default_frame_output_dir(file_path)
    output.mkdir(parents=True, exist_ok=True)
    pattern = output / "frame_%02d.jpg"
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(file_path),
        "-vf",
        f"fps={max_frames}/1",
        "-frames:v",
        str(max_frames),
        str(pattern),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    return sorted(output.glob("frame_*.jpg"))[:max_frames]


def _default_frame_output_dir(file_path: Path) -> Path:
    digest = hashlib.sha1(str(file_path.resolve()).encode("utf-8")).hexdigest()[:12]
    return PROJECT_ROOT / "data" / "media_frames" / f"{file_path.stem}-{digest}"


def read_sidecar_text(file_path: Path) -> str:
    for suffix in SIDECAR_SUFFIXES:
        sidecar = file_path.with_suffix(suffix)
        if sidecar.exists():
            return _clean_transcript_text(sidecar.read_text(encoding="utf-8", errors="ignore"))[:1000]
    return ""


def _call_visual_model(
    image_paths: list[Path],
    *,
    material_type: str,
    transcript_text: str,
    distribution_id: str | None,
    chat_transport: ChatTransport | None,
) -> MediaAnalysis:
    if not image_paths:
        return MediaAnalysis(transcript_text=transcript_text, warnings=["未能提取可分析画面"])
    try:
        model_config = _model_config(distribution_id, material_type=material_type)
        payload = _visual_payload(model_config["model"], image_paths, transcript_text)
        transport = chat_transport or _curl_chat_completion
        response = transport(
            _chat_completions_url(model_config["base_url"]),
            model_config["api_key"],
            payload,
            60,
        )
        content = _extract_chat_content(response)
        parsed = _parse_media_analysis_json(content)
        parsed.transcript_text = transcript_text
        return parsed
    except RuntimeError as exc:
        return MediaAnalysis(
            transcript_text=transcript_text,
            warnings=[str(exc)],
        )


def _model_config(distribution_id: str | None, *, material_type: str) -> dict[str, str]:
    if distribution_id:
        config = fetch_runtime_distribution_config(distribution_id)
        model = config.get("model") if isinstance(config.get("model"), dict) else {}
        api_key = str(model.get("apiKey") or "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("视觉模型缺少 apiKey")
        return {
            "api_key": api_key,
            "base_url": str(model.get("apiBaseUrl") or "").strip(),
            "model": str(model.get("model") or "").strip(),
        }

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("未配置视觉模型，已使用本地文件名打标")
    return {
        "api_key": api_key,
        "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com").strip(),
        "model": _default_media_model(material_type),
    }


def _default_media_model(material_type: str) -> str:
    if material_type == "video":
        return os.getenv("OPENAI_VIDEO_MODEL", DEFAULT_VIDEO_MODEL).strip()
    return os.getenv("OPENAI_VISION_MODEL", os.getenv("OPENAI_MODEL", "gpt-5.5")).strip()


def _visual_payload(model: str, image_paths: list[Path], transcript_text: str) -> dict[str, object]:
    content: list[dict[str, object]] = [
        {
            "type": "text",
            "text": (
                "请分析这个外贸刹车片图片/视频关键帧，输出 JSON："
                "visual_summary, ocr_text, tags, recommended_script, scenario, brand, material_grade, confidence。"
                "tags 使用中文短标签数组；confidence 为 high/medium/low。"
                f"字幕或转写文本：{transcript_text or '无'}"
            ),
        }
    ]
    for image_path in image_paths[:3]:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": _data_url(image_path)},
            }
        )
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": content,
            }
        ],
    }


def _data_url(image_path: Path) -> str:
    suffix = image_path.suffix.lower().lstrip(".") or "jpeg"
    mime = "jpeg" if suffix == "jpg" else suffix
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:image/{mime};base64,{encoded}"


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
        "--max-time",
        str(timeout),
        url,
        "-H",
        f"Authorization: Bearer {api_key}",
        "-H",
        "Content-Type: application/json",
        "--data-binary",
        "@-",
    ]
    result = subprocess.run(
        command,
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout + 5,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"视觉模型请求失败: {detail}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("视觉模型响应不是 JSON") from exc


def _extract_chat_content(payload: dict[str, object]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("视觉模型响应缺少 choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise RuntimeError("视觉模型响应缺少 message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("视觉模型响应缺少 content")
    return content


def _parse_media_analysis_json(content: str) -> MediaAnalysis:
    try:
        payload = json.loads(_strip_code_fence(content))
    except json.JSONDecodeError as exc:
        raise RuntimeError("视觉模型没有返回可解析的 JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("视觉模型返回内容不是对象")
    return MediaAnalysis(
        visual_summary=str(payload.get("visual_summary") or ""),
        ocr_text=str(payload.get("ocr_text") or ""),
        tags=[str(tag) for tag in payload.get("tags", []) if tag],
        confidence=str(payload.get("confidence") or "medium"),
    )


def _strip_code_fence(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`").strip()
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    return stripped


def _clean_transcript_text(value: str) -> str:
    lines = []
    for line in value.splitlines():
        stripped = line.strip()
        if not stripped or stripped.isdigit() or "-->" in stripped:
            continue
        lines.append(stripped)
    return " ".join(lines)
