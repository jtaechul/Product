"""롱폼 세그먼트 시작 모션용 효과음(무료·결정론 합성, stdlib만).

- gen_scan   : 소나 스윕(지도 스캔) — 상승 스윕 + 노이즈 훅.
- gen_lockon : 타깃 락온 — 디지털 비프 3연 + 확정 저음.
- gen_splash : 워터 스플래시(하강 직전) — 임팩트 + 하강 피치 + 버블 노이즈.
- gen_boom   : hook_intro.generate_boom 재사용(도달 임팩트).
모두 mono 16bit 44.1kHz WAV.
"""
from __future__ import annotations
import math
import random
import struct
import wave

SR = 44100


def _write(path: str, buf: list[float], norm: float = 0.98) -> str:
    peak = max(1e-6, max(abs(x) for x in buf))
    sc = norm / peak
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, x * sc)) * 32767)) for x in buf))
    return path


def gen_scan(path: str, dur: float = 0.8) -> str:
    """소나 스윕: 저→고 주파수 스윕 사인 + 필터드 노이즈 훅(라이즈)."""
    N = int(SR * dur)
    rnd = random.Random(21)
    buf = [0.0] * N
    prev = 0.0
    for i in range(N):
        t = i / SR
        p = t / dur
        f = 300 + (1500 - 300) * p                      # 상승 스윕
        env = math.sin(math.pi * p) ** 0.6              # 부드러운 인/아웃
        sweep = math.sin(2 * math.pi * f * t) * env * 0.7
        # 필터드(1차 저역통과) 노이즈 훅
        n = rnd.uniform(-1, 1)
        prev = prev + 0.06 * (n - prev)
        noise = prev * env * 0.5 * p
        buf[i] = math.tanh((sweep + noise) * 1.2)
    return _write(path, buf)


def gen_lockon(path: str, dur: float = 0.55) -> str:
    """타깃 락온: 고음 비프 3연(점점 짧게) + 확정 하강 2음."""
    N = int(SR * dur)
    buf = [0.0] * N
    beeps = [(0.00, 1200, 0.08), (0.12, 1200, 0.06), (0.22, 1600, 0.05)]  # (시작, Hz, 길이)
    confirm = [(0.32, 900, 0.10), (0.40, 600, 0.14)]                       # 확정 하강
    for i in range(N):
        t = i / SR
        s = 0.0
        for st, f, ln in beeps:
            dt = t - st
            if 0 <= dt < ln:
                s += math.sin(2 * math.pi * f * dt) * math.exp(-dt / (ln * 0.5)) * 0.8
        for st, f, ln in confirm:
            dt = t - st
            if 0 <= dt < ln:
                s += math.sin(2 * math.pi * f * dt) * math.exp(-dt / (ln * 0.6)) * 0.7
        buf[i] = math.tanh(s * 1.3)
    return _write(path, buf)


def gen_splash(path: str, dur: float = 0.9) -> str:
    """워터 스플래시: 빠른 어택 노이즈 버스트 + 저역 '풍덩' + 버블 진폭변조 + 하강 피치."""
    N = int(SR * dur)
    rnd = random.Random(33)
    buf = [0.0] * N
    prev = 0.0
    for i in range(N):
        t = i / SR
        p = t / dur
        # 노이즈 버스트(빠른 어택 → 지수 감쇠)
        n = rnd.uniform(-1, 1)
        prev = prev + 0.25 * (n - prev)                 # 살짝 밝은 노이즈
        atk = 1.0 if t < 0.01 else math.exp(-(t - 0.01) / 0.18)
        splash = prev * atk * 0.9
        # 저역 '풍덩'(하강 피치)
        f = 220 * math.exp(-t / 0.12) + 45
        plunge = math.sin(2 * math.pi * f * t) * math.exp(-t / 0.22) * 0.8
        # 버블(진폭변조 노이즈, 후반)
        bub = rnd.uniform(-1, 1) * math.exp(-abs(p - 0.55) / 0.18) * 0.25 * (0.5 + 0.5 * math.sin(2 * math.pi * 30 * t))
        buf[i] = math.tanh((splash + plunge + bub) * 1.15)
    return _write(path, buf)


def gen_dive_transition(path: str, dur: float = 0.85) -> str:
    """★수심 표시 → 본 영상 전환용 '다이브 후시(whoosh)'(합성 폴백). 운영자가 고른 실제 SFX를
    아직 안 넣었을 때 무음이 되지 않도록 쓰는 결정론 합성음. 하강하는 필터드 노이즈 스윕 +
    저역 서브 드롭 + 짧은 물 임팩트로 '심해로 빨려드는' 느낌을 만든다(mono 16bit 44.1kHz)."""
    N = int(SR * dur)
    rnd = random.Random(51)
    buf = [0.0] * N
    prev = 0.0
    for i in range(N):
        t = i / SR
        p = t / dur
        # 하강 whoosh: 밴드 노이즈를 고→저로 스윕(공기가 아래로 훑고 지나가는 느낌)
        n = rnd.uniform(-1, 1)
        prev = prev + (0.05 + 0.25 * (1 - p)) * (n - prev)     # p↑일수록 저역(어두워짐)
        env = math.sin(math.pi * min(1.0, p / 0.9)) ** 0.7     # 부드러운 인/아웃
        whoosh = prev * env * 0.85
        # 저역 서브 드롭(피치 하강)
        f = 180 * math.exp(-t / 0.30) + 38
        sub = math.sin(2 * math.pi * f * t) * math.exp(-t / 0.5) * 0.55
        buf[i] = math.tanh((whoosh + sub) * 1.15)
    return _write(path, buf)


def gen_all(work_dir: str) -> dict:
    """세 SFX 파일 경로를 생성해 반환."""
    from pathlib import Path
    d = Path(work_dir)
    d.mkdir(parents=True, exist_ok=True)
    return {
        "scan": gen_scan(str(d / "sfx_scan.wav")),
        "lockon": gen_lockon(str(d / "sfx_lockon.wav")),
        "splash": gen_splash(str(d / "sfx_splash.wav")),
    }
