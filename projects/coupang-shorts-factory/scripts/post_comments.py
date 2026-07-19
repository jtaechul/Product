"""비공개→공개(예약공개 포함)된 영상에 고지·링크 댓글을 자동 등록.

shorts-comments 워크플로가 주기적으로 실행. 무거운 파이프라인(렌더·TTS)을 임포트하지 않고
youtube 모듈만 써서 빠르게 돈다(구글 API 클라이언트만 필요). 대기열: data/pending_comments.json.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.upload import youtube  # noqa: E402


def main() -> int:
    if not youtube.is_configured():
        print(f"[comments] 유튜브 인증 미설정 — {youtube.missing_hint()} (정상 종료)")
        return 0
    res = youtube.process_pending_comments()
    print(f"[comments] 완료: 등록 {res['posted']} · 대기 {res['waiting']} · 정리 {res['dropped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
