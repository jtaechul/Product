"""① 주제 → 대본 + 씬별 영상 프롬프트 → content/<id>.json 저장.

GitHub Actions에서 실행된다(관리자 페이지가 Run workflow로 호출).
결과 파일은 워크플로가 저장소에 커밋하고, 관리자 페이지가 그걸 읽어 보여준다.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import asdict
from pathlib import Path

from core import llm

CONTENT_DIR = Path(__file__).resolve().parent / "content"


def make_id(topic: str) -> str:
    """파일명·릴리스 태그·주소에 그대로 쓸 수 있는 아이디.

    한글을 넣지 않는다. 릴리스 태그와 자산 주소에 섞이면 인코딩이 달라져
    영상을 못 찾는 일이 생긴다. 사람이 읽을 제목은 레코드의 title 에 따로 있다.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:16].strip("-")
    stamp = time.strftime("%y%m%d-%H%M%S")
    return f"{stamp}-{slug}" if slug else stamp


def main() -> int:
    topic = os.environ.get("TOPIC", "").strip()
    if not topic:
        print("::error::주제(TOPIC)가 비었습니다.")
        return 1
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        print("::error::GEMINI_API_KEY 시크릿이 없습니다. 저장소 Settings > Secrets에 추가하세요.")
        return 1

    scenes = int(os.environ.get("SCENES", "4"))
    tool = os.environ.get("TOOL", "Runway (Gen-3/Gen-4)")
    if tool not in llm.TOOLS:
        print(f"::error::모르는 영상 툴입니다: {tool}")
        return 1

    print(f"대본 생성 시작 — 주제: {topic} / {scenes}컷 / {tool}")
    board = llm.generate_storyboard(key, topic, scenes, tool,
                                    os.environ.get("MODEL", "gemini-2.5-flash"))

    cid = make_id(topic)
    record = {
        "id": cid,
        "topic": topic,
        "title": board.title,
        "tool": tool,
        "tool_note": llm.TOOLS[tool]["ui_note"],
        "hashtags": board.hashtags,
        "character_name": board.character_name,
        "character_image_prompt": board.character_image_prompt,
        "scenes": [asdict(s) for s in board.scenes],
        "status": "scripted",          # scripted → uploaded → rendered
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "video": None,
    }
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    out = CONTENT_DIR / f"{cid}.json"
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장: {out}")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"## {board.title}\n\n아이디: `{cid}`\n\n")
            for i, s in enumerate(board.scenes, 1):
                f.write(f"**{i}번 씬** — {s.narration}\n\n```\n{s.prompt}\n```\n\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
