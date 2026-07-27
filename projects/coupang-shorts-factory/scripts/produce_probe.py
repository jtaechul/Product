"""소싱 ⑤ 제작 CI 검증 — produce()가 홍보 클립 2개(다운로드 목)를 9:16으로 이어붙이고
그 위에 (무음 트랙 기반) 카라오케 자막 + 상단 브랜드바 + 하단 스크림을 얹어 video.mp4를
만드는지 프레임 규격(1080x1920)·길이·오디오 트랙 유무·poster.jpg 생성으로 확인한다.

로컬엔 moviepy/ffmpeg가 없어 produce를 못 돌리므로, 이 프로브로 CI에서 produce의 moviepy 합성
(_stitched_base 루프·_build_subtitles·_brand_bar_clip·_scrim·CompositeVideoClip·build_poster)이
실제로 동작하는지 검증한다. narrate=False라 TTS 키 없이 화면 조립만 본다. 항상 exit 0(정보성).
잡 로그의 'VERDICT:'를 본다 (moviepy 2.2.1, GitHub Actions에서 실행)."""
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.sourcing.compose import H, W          # noqa: E402
from src.sourcing.models import SourceVideo     # noqa: E402
from src.sourcing.produce import produce        # noqa: E402


def make_clip(path, w, h, dur, color):
    """단색 테스트 클립 생성(무음) — 홍보 원본 클립 대역."""
    from moviepy import ColorClip
    (ColorClip(size=(w, h), color=color, duration=dur).with_fps(30)
     .write_videofile(str(path), fps=30, codec="libx264", audio=False,
                      ffmpeg_params=["-pix_fmt", "yuv420p"], logger=None))


class FakeAdapter:
    """produce가 부르는 download(sv, dest_dir)만 구현 — 미리 만든 클립을 복사해 '다운로드'를 흉내낸다."""

    def __init__(self, clips):
        self._clips = clips
        self._i = 0

    def download(self, sv, dest_dir):
        src = self._clips[self._i % len(self._clips)]
        self._i += 1
        out = Path(dest_dir) / f"{sv.id}.mp4"
        shutil.copy(src, out)
        return out


def main() -> int:
    try:
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            # 1) 소스 클립 2개(가로·세로 — cover-fit 크롭 검증)
            c1, c2 = td / "src_a.mp4", td / "src_b.mp4"
            make_clip(c1, 1280, 720, 2.0, (200, 60, 60))     # 가로
            make_clip(c2, 720, 1280, 2.0, (60, 120, 200))    # 세로

            # 2) 임시 프로젝트 루트: promo/plan/폰트 배치
            root = td / "proj"
            (root / "assets" / "fonts").mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / "assets" / "fonts" / "GmarketSansBold.ttf",
                        root / "assets" / "fonts" / "GmarketSansBold.ttf")
            if (ROOT / "assets" / "sfx").exists():   # ⑤ 효과음 원본 복사(SFX 믹싱 실검증)
                shutil.copytree(ROOT / "assets" / "sfx", root / "assets" / "sfx")
            h = "probehash"
            sources = root / "data" / "sources"
            (sources / "promo").mkdir(parents=True, exist_ok=True)
            (sources / "plan").mkdir(parents=True, exist_ok=True)
            (sources / "segments").mkdir(parents=True, exist_ok=True)
            vids = [SourceVideo(platform="tiktok", source_url=f"https://x/{i}",
                                download_url=f"https://x/{i}.mp4", id=f"vid{i}").to_dict()
                    for i in range(2)]
            (sources / "promo" / f"{h}.json").write_text(
                json.dumps({"videos": vids}, ensure_ascii=False), encoding="utf-8")
            # ④ 구간 지정 검증: vid0은 앞 0~1초만, vid1은 지정 없음(전체) — 둘 다 정상 합성돼야 한다.
            (sources / "segments" / f"{h}.json").write_text(
                json.dumps({"segments": {"vid0": [[0.0, 1.0]]}}, ensure_ascii=False), encoding="utf-8")
            # ⑤ 삽입물 검증: 라인1=이미지 컷어웨이, 라인2=영상(움짤) 컷어웨이 — 풀프레임 오버레이 합성 확인.
            ins_dir = sources / "inserts" / h
            ins_dir.mkdir(parents=True, exist_ok=True)
            ins_img, ins_vid = ins_dir / "l1_0.jpg", ins_dir / "l2_0.mp4"
            from PIL import Image
            Image.new("RGB", (900, 900), (240, 200, 40)).save(ins_img, "JPEG")
            make_clip(ins_vid, 640, 640, 1.5, (40, 200, 120))
            (sources / "inserts" / f"{h}.json").write_text(json.dumps({"inserts": {
                "1": [f"data/sources/inserts/{h}/l1_0.jpg"],
                "2": [f"data/sources/inserts/{h}/l2_0.mp4"]}}, ensure_ascii=False), encoding="utf-8")
            # 존댓말 대본 + stage(효과음·reveal 매핑용) + is_hook(훅 카드) + punch(펀치 SFX).
            lines = [
                {"text": "이거 하나면 끝나요", "subs": ["이거", "하나면", "끝나요"], "is_hook": True, "stage": 1, "punch": True},
                {"text": "매일 쓰던 그 물건이었는데요", "subs": ["매일", "쓰던", "그", "물건이었는데요"], "stage": 2},
                {"text": "이렇게 편할 수가 있더라고요", "subs": ["이렇게", "편할", "수가", "있더라고요"], "stage": 4},
                {"text": "이제 고민 끝났어요", "subs": ["이제", "고민", "끝났어요"], "stage": 6},
            ]
            (sources / "plan" / f"{h}.json").write_text(
                json.dumps({"title": "프로브 상품", "product": "프로브 상품",
                            "thumb_hook": "이거 하나면 끝나요", "lines": lines}, ensure_ascii=False),
                encoding="utf-8")

            settings = {"channel": {"name": "미래에서 온 만물상", "handle": "@miraemarket"},
                        "subtitle": {"font": "assets/fonts/GmarketSansBold.ttf"},
                        "sfx": {"enabled": True, "reveal": "assets/sfx/reveal.mp3", "reveal_volume": 0.9,
                                "sub_pop_mode": "off", "line_sfx_volume": 0.35,
                                "line_sfx": {"stage1": "assets/sfx/line_hook.mp3",
                                             "stage2": "assets/sfx/line_empathy.mp3",
                                             "stage3": "assets/sfx/line_suspect.mp3",
                                             "stage5": "assets/sfx/line_proof.mp3",
                                             "punch": "assets/sfx/line_punch.mp3"}}}
            # 삽입물 로더가 이미지·영상 2라인을 정상 인식하는지(경로 해석) 먼저 확인.
            from src.sourcing.produce import load_inserts
            ins_map = load_inserts(h, root)
            ins_ok = set(ins_map.keys()) == {1, 2}
            print(f"INSERT_LOAD: lines={sorted(ins_map.keys())} ok={ins_ok}")
            import contextlib
            import io
            job = td / "job"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):   # produce 로그를 잡아 훅카드·효과음 실행 여부 확인
                out = produce(h, job, settings, project_root=root,
                              adapter=FakeAdapter([c1, c2]), narrate=False)
            plog = buf.getvalue()
            print(plog, end="")
            hook_ok = "훅 카드" in plog       # ④ 오프닝 훅 카드 렌더됨
            sfx_ok = "효과음 반영" in plog     # ⑤ 효과음(SFX) 믹싱됨

            from moviepy import VideoFileClip
            v = VideoFileClip(str(out))
            sz = tuple(v.size)
            has_audio = v.audio is not None
            n = out.stat().st_size
            poster = (job / "poster.jpg").exists()
            ok = (sz == (W, H) and has_audio and v.duration > 2.5 and n > 5000
                  and ins_ok and hook_ok and sfx_ok)
            print(f"PRODUCE_PROBE: size={sz} dur={v.duration:.2f}s audio={has_audio} "
                  f"bytes={n} poster={poster} inserts={sorted(ins_map.keys())} hook={hook_ok} sfx={sfx_ok}")
            print(f"VERDICT: produce={'OK' if ok else 'FAIL'} "
                  f"(기대 {W}x{H} · 오디오 有 · 자막/브랜드/삽입물/훅카드/효과음 합성 · poster 생성)")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"VERDICT: produce=ERROR ({type(e).__name__}: {str(e)[:200]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
