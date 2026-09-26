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

from core import llm, seal

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
    # 관리자 페이지가 봉해 보낸 사용자 개인 키를 먼저 쓰고, 없으면 저장소 기본 키.
    try:
        key = seal.gemini_key()
    except seal.SealError as e:
        print(f"::error::{e}")
        return 1
    if not key:
        print("::error::쓸 수 있는 Gemini API 키가 없습니다. 관리자 페이지 설정에서 "
              "내 API 키를 넣거나, 저장소 시크릿 GEMINI_API_KEY 를 등록하세요.")
        return 1

    mode = os.environ.get("MODE", "").strip() or llm.DEFAULT_MODE
    md = llm.get_mode(mode)
    scenes = max(len(md["acts"]),
                 min(llm.MAX_SCENES,
                     int(os.environ.get("SCENES", "") or md["default_scenes"])))
    tool = os.environ.get("TOOL", "Runway (Gen-3/Gen-4)")
    if tool not in llm.TOOLS:
        print(f"::error::모르는 영상 툴입니다: {tool}")
        return 1

    print(f"대본 생성 시작 — [{mode}] 주제: {topic} / {scenes}컷 / {tool}")
    board = llm.generate_storyboard(key, topic, scenes, tool,
                                    os.environ.get("MODEL", ""), mode)

    cid = make_id(topic)
    record = {
        "id": cid,
        "owner": os.environ.get("OWNER", "admin").strip() or "admin",
        "topic": topic,
        "title": board.title,
        "tool": tool,
        "tool_note": llm.TOOLS[tool]["ui_note"],
        "mode": board.mode,               # 태담용 / 어른용
        "channel": board.channel,         # 업로드할 채널 구분
        "opening_hook": board.opening_hook,
        # 모드에 맞는 성우·자막색. 영상 만들 때 "자동"이면 이 값을 쓴다.
        "voice": board.voice,
        "highlight": board.highlight,
        "hashtags": board.hashtags,
        "logline": board.logline,
        "characters": [asdict(c) for c in board.characters],
        "cover_prompt": board.cover_prompt,
        "style_lock": board.style_lock,
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
            f.write(f"## {board.title}\n\n아이디: `{cid}` · **{board.mode}** "
                    f"({board.channel} 채널)\n\n{board.logline}\n\n")
            if board.opening_hook:
                f.write(f"**후킹 질문** — {board.opening_hook}\n\n")
            if board.cover_prompt:
                f.write(f"**표지**\n\n```\n{board.cover_prompt}\n```\n\n")
            for c in board.characters:
                f.write(f"**인물 · {c.name}** ({c.role})\n\n```\n{c.image_prompt}\n```\n\n")
            for i, s in enumerate(board.scenes, 1):
                f.write(f"**{i}번 씬** — {s.narration}\n\n```\n{s.prompt}\n```\n\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
