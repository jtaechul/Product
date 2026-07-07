"""hook_intro_stage — 본문 영상을 '오프닝 훅 + 엔드카드 + 전환 + 임팩트 사운드' 시스템으로
   감싸는 파이프라인 연결 단계.

파이프라인에서의 위치: 본문 영상(합성·자막·오디오 완료) → apply() → 완성본.
설계 원칙: **절대 발행을 막지 않는다.** edge-tts/폰트/네트워크 등 어떤 전제라도 없으면
경고만 남기고 원본 본문 영상을 그대로 반환한다(안전 폴백).

구성(모두 hook_intro 모듈의 확정 디자인 사용):
  오프닝 훅(명조 대형 그라데이션 타이틀·어절 팝·셰이크·홀드)
  → 플래시 전환 → 본문 → 플래시 전환
  → 엔드카드(타자기 텍스트·타자음·피사체 중간밴드)
오디오: 강렬 훅 나레이션 + 딥 붐(어절) + 본문 오디오 + 엔드카드 타자음 (+선택 BGM).
"""
from __future__ import annotations

import logging
import re
import ssl
import subprocess
from pathlib import Path

from src.core import hook_intro as hi

log = logging.getLogger(__name__)
_PROXY_CA = "/root/.ccr/ca-bundle.crt"
_PUNCT = re.compile(r"[、。，．・「」『』（）\s]")


def _install_ca() -> None:
    # Path.exists()도 try 안: CI 러너(비 root)에선 /root/.ccr 접근 불가라
    # Python 3.11 exists()가 PermissionError를 되던진다 → 전부 감싸 삼킨다.
    try:
        if Path(_PROXY_CA).exists():
            import edge_tts.communicate as ec
            ec._SSL_CTX = ssl.create_default_context(cafile=_PROXY_CA)
    except Exception:  # noqa: BLE001
        pass


def _synth_hook(text: str, out_mp3: str, cfg: hi.HookIntroConfig) -> dict | None:
    """훅 문장 → edge-tts(강조 파라미터)로 합성. 단어 온셋(頭/目/骨 등 어절 첫 글자) 반환.
    실패(키/네트워크/모듈 없음) 시 None → 상위에서 폴백."""
    try:
        import asyncio
        import edge_tts
        _install_ca()

        async def _run():
            c = edge_tts.Communicate(text, "ja-JP-KeitaNeural", rate=cfg.hook_tts_rate,
                                     pitch=cfg.hook_tts_pitch, volume=cfg.hook_tts_volume,
                                     boundary="WordBoundary")
            audio = bytearray(); words = []
            async for ch in c.stream():
                if ch["type"] == "audio":
                    audio += ch["data"]
                elif ch["type"] == "WordBoundary":
                    words.append((ch["offset"] / 1e7, ch["duration"] / 1e7, ch["text"]))
            return bytes(audio), words

        audio, words = asyncio.run(_run())
        if not audio or not words:
            return None
        Path(out_mp3).write_bytes(audio)
        return {"mp3": out_mp3, "words": words}
    except Exception as e:  # noqa: BLE001
        log.warning("[hook_intro] 훅 나레이션 합성 실패 → 오프닝 생략: %s", e)
        return None


def _onsets_for_words(pop_words: list[str], words: list[tuple]) -> dict:
    """팝 어절 각각의 첫 글자를 실제 단어 온셋에 매핑(정합)."""
    onsets = {}
    wi = 0
    for w in pop_words:
        core = _PUNCT.sub("", w)
        if not core:
            continue
        first = core[0]
        # 남은 words에서 first를 포함하는 첫 단어의 시작
        found = None
        for j in range(wi, len(words)):
            if first in words[j][2]:
                found = words[j][0]; wi = j + 1; break
        onsets[first] = found if found is not None else (words[wi][0] if wi < len(words) else 0.0)
    return onsets


def _probe(path: str, entry: str) -> str:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", f"stream={entry}", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    return r.stdout.strip()


def _grab_frame(video: str, t: float, out_png: str, vf: str | None = None) -> bool:
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", video]
    if vf:
        cmd += ["-vf", vf]
    cmd += ["-frames:v", "1", out_png]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0 and Path(out_png).exists()


def _duration_of(path: str) -> float:
    """영상 실제 길이(초) = duration − start_time.

    왜(실제 결함): NOAA/Commons webm은 타임스탬프가 0에서 시작하지 않는 파일이 있어
    (start_time≈141,024s) ffprobe duration이 '끝 타임스탬프'(141,113s)를 돌려준다.
    이 값을 길이로 쓰면 프레임 추출 시각이 영상 밖(수십 시간 뒤)을 가리켜 엔드카드
    피사체 프레임 추출이 전부 실패했다. start_time을 빼서 실제 구간 길이를 쓴다."""
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=start_time,duration",
                        "-of", "json", path], capture_output=True, text=True)
    try:
        import json as _json
        fmt = _json.loads(r.stdout or "{}").get("format", {})
        dur = float(fmt.get("duration") or 0)
        start = float(fmt.get("start_time") or 0)
        if dur > 0:
            return max(0.0, dur - max(0.0, start))
    except Exception:  # noqa: BLE001
        pass
    try:
        return float(_probe(path, "duration") or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def _best_subject_frame(video: str, out_png: str, wd: Path,
                        logo_box: tuple | None = None) -> bool:
    """영상에서 '피사체가 가장 뚜렷한' 프레임을 골라 out_png로 저장.

    왜: 고정 시각(55%) 프레임은 피사체가 흐릿하거나 비어 있을 수 있다.
    10~90% 구간 9개 샘플의 적색 피사체 점수(reframe.subject_score) 최대 프레임 선택.
    logo_box가 오면 워터마크를 delogo로 메워 엔드카드 배경에 로고가 남지 않게 한다.
    """
    from src.core import reframe
    dur = _duration_of(video)
    if dur <= 0:
        return False
    vf = None
    if logo_box:
        sw = _probe(video, "width") or 1920
        sh = _probe(video, "height") or 1080
        try:
            vf = reframe.delogo_vf(float(sw), float(sh), logo_box)
        except Exception:  # noqa: BLE001
            vf = None
    best, best_score = None, -1.0
    for i in range(9):
        t = dur * (0.1 + 0.8 * i / 8)
        cand = str(wd / f"ecs_{i}.png")
        if not _grab_frame(video, t, cand, vf=vf):
            continue
        s = reframe.subject_score(cand)
        # 번인 텍스트(인트로 자막판·아웃트로 URL) 프레임은 강한 감점 → 엔드카드 배경 배제
        if reframe.text_score(cand) >= 0.012:
            s *= 0.02
        if s > best_score:
            best, best_score = cand, s
    if not best:
        return False
    Path(out_png).write_bytes(Path(best).read_bytes())
    return True


def apply(body_video: str, spec: hi.SpeciesSpec, hook_text: str, work_dir: str,
          cfg: hi.HookIntroConfig | None = None, bgm: str | None = None,
          open_bg_video: str | None = None, subject_video: str | None = None,
          logo_box: tuple | None = None) -> str:
    """본문 영상을 오프닝/엔드카드/전환/사운드로 감싼 완성본 경로 반환.
    전제 미충족 시 원본 body_video를 그대로 반환(발행 불정지).

    배경 소스 규칙(재발 방지 — 실제 결함 2건의 근본 원인):
    - open_bg_video: 오프닝 배경 프레임 소스. **자막 번인 전 클린 영상**을 넘겨야
      본문 자막이 오프닝 뒤에 미리 노출되지 않는다(미지정 시 body_video 폴백).
    - subject_video: 엔드카드 피사체 프레임 소스. **크롭·줌 전 원본 광각 영상**을 넘겨야
      과확대로 생물을 식별 못 하는 문제가 없다(미지정 시 open_bg_video 폴백).
    """
    cfg = cfg or hi.HookIntroConfig()
    wd = Path(work_dir); wd.mkdir(parents=True, exist_ok=True)
    try:
        if not hi.fonts_available():
            log.warning("[hook_intro] 폰트 없음 → 오프닝/엔드카드 생략(본문 그대로)")
            return body_video
        dur = _duration_of(body_video)
        if dur <= 0:
            return body_video

        # 1) 훅 나레이션 + 온셋
        hook = _synth_hook(hook_text, str(wd / "hook.mp3"), cfg)
        if not hook:
            return body_video
        onsets = _onsets_for_words(spec.hook_pop_words, hook["words"])

        # 2) 배경 프레임 — 오프닝=클린 영상 초반, 엔드카드=원본 광각의 피사체 최적 프레임
        src_open = open_bg_video if open_bg_video and Path(open_bg_video).exists() else body_video
        src_subj = subject_video if subject_video and Path(subject_video).exists() else src_open
        open_bg = str(wd / "open_bg.png"); ec_frame = str(wd / "ec_frame.png")
        odur = _duration_of(src_open) or dur
        if not _grab_frame(src_open, min(0.5, odur * 0.1), open_bg):
            return body_video
        # 원본(subject_video)에서 뽑는 피사체 프레임은 워터마크 delogo 적용(엔드카드 로고 잔류 방지).
        # 리프레임된 body 계열 소스는 reframe 단계에서 이미 회피/제거됨 → 미적용.
        subj_logo = logo_box if (subject_video and src_subj == subject_video) else None
        if not _best_subject_frame(src_subj, ec_frame, wd, logo_box=subj_logo):
            _grab_frame(src_subj, (_duration_of(src_subj) or dur) * 0.55, ec_frame)
        ec_bg = str(wd / "ec_bg.png")
        hi.build_specimen_bg(ec_frame if Path(ec_frame).exists() else open_bg, ec_bg, cfg)

        # 3) 오프닝/엔드카드 렌더 → mp4
        of_dir = str(wd / "of"); ec_dir = str(wd / "ecf")
        hi.render_opening_frames(open_bg, onsets, spec, of_dir, cfg)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(cfg.FPS),
                        "-i", f"{of_dir}/of_%03d.png", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-crf", "18", str(wd / "opening.mp4")], check=True)
        _, clicks = hi.render_endcard_frames(ec_bg, spec, ec_dir, cfg)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(cfg.FPS),
                        "-i", f"{ec_dir}/ec_%03d.png", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-crf", "18", str(wd / "endcard.mp4")], check=True)

        # 4) SFX/플래시
        boom = hi.generate_boom(str(wd / "boom.wav"), cfg)
        tick = hi.generate_type_click(str(wd / "tick.wav"), cfg)
        flash = hi.build_flash_png(str(wd / "flash.png"), cfg)

        OPEN = cfg.opening_seg_s; END = cfg.endcard_dur_s
        BODY_END = OPEN + dur; TOTAL = OPEN + dur + END
        W, H = cfg.W, cfg.H

        # 5) 영상 concat + 전환 2곳(본문 해상도 정규화)
        vf = (
            f"[0:v]scale={W}:{H},setpts=PTS-STARTPTS[o];"
            f"[1:v]scale={W}:{H},setpts=PTS-STARTPTS[b];"
            f"[2:v]scale={W}:{H},setpts=PTS-STARTPTS[e];[o][b][e]concat=n=3:v=1:a=0[cat];"
            f"[3:v]format=yuva420p,colorchannelmixer=aa=0.55,fade=t=in:st={OPEN-0.25}:d=0.22:alpha=1,"
            f"fade=t=out:st={OPEN}:d=0.28:alpha=1[fl1];"
            f"[4:v]format=yuva420p,colorchannelmixer=aa=0.6,fade=t=in:st={BODY_END-0.25}:d=0.22:alpha=1,"
            f"fade=t=out:st={BODY_END}:d=0.30:alpha=1[fl2];"
            f"[cat][fl1]overlay=0:0[o1];[o1][fl2]overlay=0:0[v]"
        )
        vout = str(wd / "wrapped_video.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                        "-i", str(wd / "opening.mp4"), "-i", body_video, "-i", str(wd / "endcard.mp4"),
                        "-loop", "1", "-t", str(TOTAL), "-i", flash,
                        "-loop", "1", "-t", str(TOTAL), "-i", flash,
                        "-filter_complex", vf, "-map", "[v]", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-crf", "19", "-r", str(cfg.FPS), vout], check=True)

        # 6) 오디오: 훅@0.30 + 붐@온셋 + 본문오디오@OPEN + 엔드카드 타자@BODY_END + (BGM)
        NARR = cfg.narr_start_s
        inputs = ["-i", hook["mp3"], "-i", body_video, "-i", boom, "-i", tick]
        af = (f"[0:a]adelay={int(NARR*1000)}|{int(NARR*1000)},volume={cfg.mix_hook}[hk];"
              f"[1:a]adelay={int(OPEN*1000)}|{int(OPEN*1000)},volume={cfg.mix_body}[bd];")
        labels = ["[hk]", "[bd]"]
        for i, (first, on) in enumerate(onsets.items()):
            at = int((NARR + on) * 1000)
            af += f"[2:a]adelay={at}|{at},volume={cfg.mix_boom}[bm{i}];"
            labels.append(f"[bm{i}]")
        for i, ct in enumerate(clicks):
            at = int((BODY_END + ct) * 1000)
            af += f"[3:a]adelay={at}|{at},volume=0.5[tk{i}];"
            labels.append(f"[tk{i}]")
        ninp = len(labels)
        if bgm and Path(bgm).exists():
            inputs += ["-i", bgm]
            af += (f"[4:a]atrim=0:{TOTAL},volume={cfg.mix_bgm},afade=t=in:st=0:d=1.5,"
                   f"afade=t=out:st={TOTAL-2}:d=2.0[bed];")
            labels.append("[bed]"); ninp += 1
        af += (f"{''.join(labels)}amix=inputs={ninp}:duration=longest:normalize=0,"
               f"alimiter=limit={cfg.limiter},atrim=0:{TOTAL},aresample=44100[a]")
        aout = str(wd / "wrapped_audio.m4a")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + inputs +
                       ["-filter_complex", af, "-map", "[a]", "-c:a", "aac", "-b:a", "192k", aout],
                       check=True)

        final = str(wd / "final_wrapped.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", vout, "-i", aout,
                        "-c:v", "copy", "-c:a", "copy", "-shortest", final], check=True)
        log.info("[hook_intro] 오프닝/엔드카드 적용 완료: %s (%.1fs)", final, TOTAL)
        return final
    except Exception as e:  # noqa: BLE001
        log.warning("[hook_intro] 적용 실패 → 본문 그대로 발행: %s", e)
        return body_video
