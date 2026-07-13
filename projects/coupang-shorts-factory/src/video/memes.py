"""AI 밈 이미지 라이브러리 선택기 (자체 생성물 = 스펙 §3.2 화이트리스트).

상황별 위트 짤을 한 번 생성해 `assets/memes/`에 저장 → 펀치라인 순간에 상황이 맞는
이미지를 꺼내 **밈 카드 배경**으로 재사용한다. 이미지에는 글자를 굽지 않고(한글 왜곡 회피)
텍스트는 렌더 파이프라인이 하단 클린존에 얹는다.

핵심규칙 준수: 밈 이미지는 '화면 텍스트'가 아니라 punch 밈 카드 1회의 '배경'으로만 쓴다
(화면 텍스트는 하단 자막 + 펀치 카드 딱 둘 — react 추임새 금지 유지).
"""

from __future__ import annotations

import json
from pathlib import Path


def _manifest_path(project_root: Path) -> Path:
    return Path(project_root) / "assets" / "memes" / "memes.json"


def load_library(project_root: Path) -> list:
    """memes.json의 등록 항목 중 실제 파일이 존재하는 것만 반환. 없으면 빈 리스트."""
    mp = _manifest_path(project_root)
    if not mp.exists():
        return []
    try:
        data = json.loads(mp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"[memes] 매니페스트 읽기 실패({type(e).__name__}: {e}) → 밈 이미지 없이 진행")
        return []
    lib = []
    base = mp.parent
    for m in data.get("memes", []):
        f = base / str(m.get("file", ""))
        if m.get("file") and f.exists():
            m = dict(m)
            m["_path"] = f
            lib.append(m)
    return lib


def select_meme(project_root: Path, punch_text: str = "", meme_tag: str = "") -> Path | None:
    """펀치라인 상황에 맞는 밈 이미지 경로 선택.
    우선순위: ① meme_tag 명시(정확/부분 일치) ② situations 키워드가 펀치 텍스트에 포함
              ③ 라이브러리 첫 항목(기본). 라이브러리가 비면 None(→ 렌더는 텍스트 카드로 폴백).
    """
    lib = load_library(project_root)
    if not lib:
        return None

    tag = (meme_tag or "").strip()
    if tag:
        for m in lib:
            if tag == m.get("id") or tag in (m.get("situations") or []):
                return m["_path"]

    text = punch_text or ""
    if text:
        best, best_hits = None, 0
        for m in lib:
            hits = sum(1 for kw in (m.get("situations") or []) if kw and kw in text)
            if hits > best_hits:
                best, best_hits = m, hits
        if best is not None:
            return best["_path"]

    return lib[0]["_path"]  # 기본: 첫 항목(항상 하나는 뜨게 — 펀치 순간 밋밋함 방지)
