#!/usr/bin/env python3
"""보이스 샘플 발송 — 같은 대사를 여러 TTS 목소리로 합성해 텔레그램으로 보낸다(task #21).

운영자가 텔레그램에서 들어보고 마음에 드는 번호를 알려주면, 그 목소리로 settings.yaml을 고정한다.
CI(shorts-produce, mode=voice_samples)에서 GEMINI/TELEGRAM 시크릿으로 실행된다. 로컬은 키가 없어 no-op.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import notify                     # noqa: E402
from src.audio import tts                  # noqa: E402

# 페르소나(미래 큐레이터·시크한데 위트) 대표 대사 — 목소리 톤 비교용
SAMPLE = "자, 여름만 되면 손선풍기 붙잡고 산 당신. 이거 하나면 그 고생, 오늘부로 끝입니다."

# Gemini TTS 프리빌트 보이스 후보(한국어는 텍스트로 자동 발화). 다양한 성별·톤을 섞었다.
GEMINI_VOICES = [
    ("Charon", "현재 톤 · 시크하고 무심한 남성"),
    ("Puck", "경쾌하고 업비트한 남성"),
    ("Orus", "단호하고 묵직한 남성"),
    ("Fenrir", "촐싹이고 에너지 넘치는 남성"),
    ("Kore", "차분하고 또렷한 여성"),
    ("Aoede", "밝고 친근한 여성"),
]


def _to_mp3(raw: bytes, ext: str, dst: Path) -> Path:
    """합성 오디오(wav/mp3)를 텔레그램 재생용 mp3로 변환. mp3면 그대로 저장."""
    if ext == "mp3":
        dst.write_bytes(raw)
        return dst
    src = dst.with_suffix("." + ext)
    src.write_bytes(raw)
    try:
        import imageio_ffmpeg
        ff = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        ff = "ffmpeg"
    subprocess.run([ff, "-y", "-i", str(src), "-b:a", "128k", str(dst)],
                   check=True, capture_output=True)
    return dst


def main() -> int:
    settings = yaml.safe_load(open(ROOT / "config/settings.yaml", encoding="utf-8")) or {}
    tcfg = settings.get("tts", {}) or {}
    gcfg = tcfg.get("gemini", {}) or {}
    out_dir = ROOT / "data/jobs/voice_samples"
    out_dir.mkdir(parents=True, exist_ok=True)

    if not notify.send("[미래마켓] 보이스 샘플을 보냅니다 — 같은 대사를 여러 목소리로 들려드려요.\n"
                       "마음에 드는 번호(또는 이름)를 알려주시면 그 목소리로 고정합니다.\n\n대사: " + SAMPLE):
        print("[voice] 텔레그램 미등록(로컬) — 발송 없이 종료. CI에서 실행하세요.")
        return 0

    sent = 0
    for i, (voice, label) in enumerate(GEMINI_VOICES, 1):
        try:
            out = tts._synth_gemini(SAMPLE, {**gcfg, "voice": voice})
            mp3 = _to_mp3(out.audio_bytes, out.audio_ext, out_dir / f"{i:02d}_{voice}.mp3")
            if notify.send_audio(mp3, caption=f"{i}. {voice} — {label}", title=f"{i}. {voice}"):
                sent += 1
                print(f"[voice] 전송: {i}. {voice}")
            else:
                print(f"[voice] 전송 실패: {voice}")
        except Exception as e:
            print(f"[voice] {voice} 합성/전송 실패: {e}")
            notify.send(f"{i}. {voice} — 생성 실패({str(e)[:120]})")

    # ElevenLabs Sarah(원어민 여성)도 키가 있으면 하나 더 — 프로바이더 비교용
    if tts.detect_available().get("elevenlabs"):
        try:
            out = tts._synth_elevenlabs(SAMPLE, tcfg.get("elevenlabs", {}) or {})
            mp3 = _to_mp3(out.audio_bytes, out.audio_ext, out_dir / "07_elevenlabs_sarah.mp3")
            if notify.send_audio(mp3, caption="7. ElevenLabs Sarah — 다른 엔진(원어민 여성)", title="7. ElevenLabs Sarah"):
                sent += 1
        except Exception as e:
            print(f"[voice] elevenlabs 실패: {e}")

    notify.send(f"[미래마켓] 보이스 샘플 {sent}개 전송 완료. 원하는 번호/이름을 알려주세요.")
    print(f"[voice] 완료 — {sent}개 전송")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
