"""소싱 ⑤ 합성 CI 검증 — 합성용 클립 2개(가로·세로)를 만들어 stitch_vertical로 9:16 이어붙이고
결과 크기·길이·바이트를 확인한다(moviepy 2.2.1, GitHub Actions에서 실행). 항상 exit 0(정보성).

로컬엔 moviepy/ffmpeg가 없어 합성을 못 돌리므로, 이 프로브로 CI에서 stitch_vertical의 moviepy API·
cover-fit(9:16)·concat이 실제로 동작하는지 프레임 규격으로 확인한다. 잡 로그의 'VERDICT:'를 본다.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.sourcing.compose import H, W, stitch_vertical   # noqa: E402


def make_clip(path, w, h, dur, color):
    """단색 테스트 클립 생성(무음)."""
    from moviepy import ColorClip
    (ColorClip(size=(w, h), color=color, duration=dur).with_fps(30)
     .write_videofile(str(path), fps=30, codec="libx264", audio=False,
                      ffmpeg_params=["-pix_fmt", "yuv420p"], logger=None))


def main() -> int:
    try:
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            c1, c2 = td / "a.mp4", td / "b.mp4"
            make_clip(c1, 1280, 720, 1.0, (200, 60, 60))     # 가로(landscape) 소스
            make_clip(c2, 720, 1280, 1.0, (60, 120, 200))    # 세로(portrait) 소스
            out = td / "stitched.mp4"
            stitch_vertical([c1, c2], out)
            from moviepy import VideoFileClip
            v = VideoFileClip(str(out))
            sz = tuple(v.size)
            n = out.stat().st_size
            # 단색 테스트 클립은 극도로 잘 압축돼 수 KB — 규격(9:16·길이·유효 mp4)만 본다.
            ok = sz == (W, H) and n > 2000 and v.duration > 1.5
            print(f"COMPOSE_PROBE: size={sz} dur={v.duration:.2f}s bytes={n}")
            print(f"VERDICT: compose={'OK' if ok else 'FAIL'} (기대 {W}x{H} · 두 클립 ≈2초)")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"VERDICT: compose=ERROR ({type(e).__name__}: {str(e)[:160]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
