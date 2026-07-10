from pathlib import Path
import subprocess

import pytest

from app.services.material_review import analyze_material_file
from app.services.media_analysis import MediaAnalysis, analyze_media, extract_video_frames


def _create_test_image(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=160x120:d=1",
            "-frames:v",
            "1",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def _create_test_video(path: Path, image_path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-t",
            "1",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def test_material_analysis_uses_visual_ocr_and_transcript_summary(tmp_path):
    image_path = tmp_path / "HIQ-包装实物图.jpg"
    _create_test_image(image_path)
    analyzer = lambda file_path, material_type: MediaAnalysis(
        visual_summary="画面展示 HIQ 彩盒包装和刹车片正面。",
        ocr_text="HIQ BRAKE PADS",
        transcript_text="",
        tags=["包装", "彩盒", "HIQ", "视觉识别"],
        confidence="high",
        frame_paths=[],
    )

    payload = analyze_material_file(
        image_path,
        product_type="brake_pad",
        analyzer=analyzer,
    )

    assert "画面展示 HIQ 彩盒包装" in payload["description"]
    assert "可见文字：HIQ BRAKE PADS" in payload["description"]
    assert "视觉识别" in payload["tags"]
    assert "ocr" in payload["tags"]
    assert "high_confidence" in payload["tags"]


def test_video_analysis_extracts_frames_and_uses_transcript_text(tmp_path):
    image_path = tmp_path / "frame.jpg"
    video_path = tmp_path / "HIQ-普通半金属-包装视频.mp4"
    video_path.with_suffix(".txt").write_text(
        "视频中介绍 HIQ 普通半金属刹车片包装和摩擦面颗粒。",
        encoding="utf-8",
    )
    _create_test_image(image_path)
    _create_test_video(video_path, image_path)

    frame_paths = extract_video_frames(video_path, output_dir=tmp_path / "frames", max_frames=2)
    assert frame_paths
    assert all(path.exists() for path in frame_paths)

    payload = analyze_material_file(video_path, product_type="brake_pad")

    assert "视频中介绍 HIQ 普通半金属刹车片包装" in payload["description"]
    assert "视频抽帧" in payload["tags"]
    assert "transcript" in payload["tags"]
    assert "普通半金属" in payload["tags"]


def test_extract_video_frames_returns_empty_when_ffmpeg_cannot_read_file(tmp_path):
    broken_video = tmp_path / "broken.mp4"
    broken_video.write_bytes(b"not a real video")

    assert extract_video_frames(broken_video, output_dir=tmp_path / "frames") == []


def test_extract_video_frames_defaults_to_cache_directory(tmp_path):
    source_dir = tmp_path / "raw"
    source_dir.mkdir()
    image_path = tmp_path / "frame.jpg"
    video_path = source_dir / "demo.mp4"
    _create_test_image(image_path)
    _create_test_video(video_path, image_path)

    frame_paths = extract_video_frames(video_path, max_frames=1)

    assert frame_paths
    assert all(source_dir not in path.parents for path in frame_paths)


def test_video_analysis_defaults_to_gemini_pro_model(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    frame_path = tmp_path / "frame.jpg"
    frame_path.write_bytes(b"fake image bytes")
    video_path = tmp_path / "demo.mp4"
    video_path.write_bytes(b"fake video bytes")
    monkeypatch.setattr(
        "app.services.media_analysis.extract_video_frames",
        lambda file_path: [frame_path],
    )
    requests = []

    def fake_transport(url, api_key, payload, timeout):
        requests.append(payload)
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"visual_summary":"包装视频",'
                            '"ocr_text":"",'
                            '"tags":["包装"],'
                            '"confidence":"high"}'
                        )
                    }
                }
            ]
        }

    analysis = analyze_media(video_path, material_type="video", chat_transport=fake_transport)

    assert analysis.visual_summary == "包装视频"
    assert requests[0]["model"] == "gemini-3.1-pro"
