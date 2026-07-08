#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from app.config import PROJECT_ROOT
from app.database import SessionLocal, init_db
from app.services.raw_material_seed import import_manual_knowledge, import_media_directory


DEFAULT_MANUAL = PROJECT_ROOT / "raw" / "260706业务员谈单手册_v4.0.docx"
DEFAULT_MEDIA_DIR = PROJECT_ROOT / "raw" / "2026.7.7刹车片" / "小片"


def main() -> None:
    parser = argparse.ArgumentParser(description="导入谈单手册和本地素材目录")
    parser.add_argument(
        "--manual",
        type=Path,
        default=DEFAULT_MANUAL,
        help="谈单手册 docx 路径",
    )
    parser.add_argument(
        "--media-dir",
        type=Path,
        default=DEFAULT_MEDIA_DIR,
        help="刹车片素材目录",
    )
    parser.add_argument(
        "--skip-manual",
        action="store_true",
        help="跳过谈单手册导入",
    )
    parser.add_argument(
        "--skip-media",
        action="store_true",
        help="跳过素材目录导入",
    )
    args = parser.parse_args()

    init_db()
    with SessionLocal() as db:
        if not args.skip_manual:
            if not args.manual.exists():
                raise SystemExit(f"谈单手册不存在: {args.manual}")
            manual_result = import_manual_knowledge(db, args.manual)
            print("谈单手册导入完成:", manual_result)

        if not args.skip_media:
            media_result = import_media_directory(db, args.media_dir)
            print("素材目录导入完成:", media_result)


if __name__ == "__main__":
    main()
