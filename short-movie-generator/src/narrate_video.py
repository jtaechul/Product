"""첨부 영상 나레이션 CLI(워크플로/로컬 실행용).

예)
  python -m src.narrate_video --url https://.../clip.mp4 --mode shorts \
      --title "深海の沈没船" --notes "NOAA ROVが撮影した潜水艦の残骸。..."
  python -m src.narrate_video --path in.mp4 --mode longform --title ... --notes ...
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path


def _download(url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "narrate-video/1.0"})
        with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
            while True:
                b = r.read(1 << 16)
                if not b:
                    break
                f.write(b)
        return dest.exists() and dest.stat().st_size > 10_000
    except Exception as e:  # noqa: BLE001
        print(f"[narrate] 다운로드 실패: {e}", file=sys.stderr)
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="첨부 영상에 일본어 나레이션·자막 입히기")
    ap.add_argument("--url", default="", help="영상 URL(첨부 릴리스 에셋 등)")
    ap.add_argument("--path", default="", help="로컬 영상 경로(--url 없을 때)")
    ap.add_argument("--mode", default="shorts", choices=["shorts", "longform"])
    ap.add_argument("--source-topic", default="", help="소싱 출처(커먼스/아카이브)의 설명 · 근거용(운영자 입력 아님)")
    ap.add_argument("--out-name", default="", help="출력 파일명(확장자 제외)")
    ap.add_argument("--base-dir", default=".")
    a = ap.parse_args()

    base = Path(a.base_dir)
    if a.url:
        src = base / "work" / "narrate" / "input.mp4"
        if not _download(a.url, src):
            print("ERROR: 영상 다운로드 실패", file=sys.stderr)
            return 2
        video = str(src)
    elif a.path:
        video = a.path
    else:
        print("ERROR: --url 또는 --path 필요", file=sys.stderr)
        return 2

    from src.core.narrate_attached import narrate_video
    try:
        res = narrate_video(video, mode=a.mode, source_topic=a.source_topic,
                            base_dir=a.base_dir, out_name=(a.out_name or None))
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    # 표준출력 = 완성본 경로(워크플로가 파싱). 메타(JSON)는 output/<name>.meta.json에 별도 기록됨.
    print(res["path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
