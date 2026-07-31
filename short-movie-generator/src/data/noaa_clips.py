"""NOAA 심해탐사 **검증 완료 심해생물 클립 풀**(운영자 지시 "심해 생물 영상을 추가 확보").

출처: oceanexplorer.noaa.gov — **미 연방정부 저작물 = 퍼블릭도메인**(프로젝트 허용 라이선스).
  전량(mp4 1,563개)을 열거 → 심해 생물 클립만 추림 → **실제로 내려받아** 아래를 실측했다.
    ① 재생·해상도  ② 길이 8초 이상  ③ 움직임(watermark_qc.motion_score — 정지화면 배제)
    ④ 로고/크레딧 슬레이트 초(watermark_qc.plan)
  `slate_s`가 큰 클립은 앞뒤에 크레딧 화면이 있다는 뜻 — 제작 단계의 슬레이트 회피가 처리한다.

★종(학명) 단정 금지: NOAA가 파일에 붙인 이름은 대개 **일반명 수준**(cuskeel·chimaera 등)이라,
  여기서 학명을 임의로 붙이지 않는다(사실 날조 금지 규칙). `tags`는 NOAA 파일명이 말하는
  일반명 낱말일 뿐이며, 종 확정은 기존 종 검증 절차가 담당한다.

측정일: 2026-07-31 (커밋 기준).
"""
from __future__ import annotations

import json
from pathlib import Path

# ★데이터 원본은 **JSON 한 곳**(noaa_clips.json)이다 — 파이썬과 대시보드가 같은 파일을 읽어야
#   목록 화면과 실제 제작이 어긋나지 않는다(운영자가 화면에서 본 것 = 제작이 쓰는 것).
_DATA = json.loads((Path(__file__).with_name("noaa_clips.json")).read_text(encoding="utf-8"))

LICENSE: str = _DATA["license"]
CREDIT: str = _DATA["credit"]
CLIPS: list[dict] = _DATA["clips"]


def find(*names: str) -> list[dict]:
    """일반명 낱말(예: "dumbo octopus", "hagfish")로 검증된 클립을 찾는다.

    ★일반적인 낱말은 매칭에서 제외한다(운영자 품질 규칙): "fish"·"coral" 같은 말은 거의 모든
      종 이름에 들어 있어, 그대로 두면 **무관한 종에 엉뚱한 영상**이 붙는다(실제로 테스트에서
      가상의 'test fish'가 NOAA의 일반 어류 클립을 물어 왔다). 구체적인 이름만 매칭한다.
    반환 순서: 움직임 큰 것 → 긴 것.
    """
    GENERIC = {"fish", "coral", "corals", "star", "video"}
    want = {w for n in names
            for w in str(n or "").lower().replace("-", " ").replace(".", " ").split()
            if w and w not in GENERIC and len(w) >= 4}
    if not want:
        return []

    def hit(tag: str) -> bool:
        if tag in GENERIC:
            return False
        return any(tag == w or (len(tag) >= 5 and len(w) >= 5 and (tag in w or w in tag))
                   for w in want)

    got = [c for c in CLIPS if any(hit(t) for t in c["tags"])]
    return sorted(got, key=lambda c: (-c["motion"], -c["dur"]))
