"""제품 등장 효과음 '두둥' — 깊은 타이코/팀파니 북 두 방. 직접 합성(저작권 세이프).

진짜 북처럼 들리게 하는 핵심(합성 티를 없애는 물리 모델링):
  ① 비배음(inharmonic) 멤브레인 모드 — 실제 북 가죽은 1·2·3배음이 아니라
     1.00·1.59·2.14·2.30·2.65… 비정수 비율로 울린다(그래서 '소리'가 아니라 '북').
  ② 모드별 감쇠 — 높은 모드가 먼저 죽어야 자연스럽다.
  ③ 피치 하강 어택 — 타격 순간 음이 확 떨어지며 '펀치'가 생긴다.
  ④ 서브 텀프(가슴을 치는 초저역) + 말렛 타격 노이즈 트랜지언트.
  ⑤ tanh 새추레이션(따뜻함·라우드니스) + 컨볼루션 잔향(공간감).
'두'(첫 타, 조금 높고 짧게) → '둥'(둘째 타, 더 깊고 크게 — 제품 공개의 임팩트). 결정론(seed 고정)."""
import wave
from pathlib import Path
import numpy as np

sr = 44100

# 이상적 원형 멤브레인 진동 모드비(낮은 모드가 지배) + 모드별 상대감쇠(높을수록 빨리 죽음)
MODES = [(1.00, 1.00, 1.0), (1.59, 0.55, 1.7), (2.14, 0.32, 2.4),
         (2.30, 0.22, 2.8), (2.65, 0.14, 3.4), (2.92, 0.09, 4.2)]


def drum(f0, dur, amp, decay0, drop, seed):
    rng = np.random.default_rng(seed)
    n = int(sr * dur); t = np.arange(n) / sr
    fenv = f0 * (1 + drop * np.exp(-t * 55))                 # 피치 하강(펀치의 핵심)
    ph = 2 * np.pi * np.cumsum(fenv) / sr
    body = np.zeros(n)
    for ratio, a, dm in MODES:                               # 비배음 모드 합 + 모드별 감쇠
        body += a * np.sin(ph * ratio) * np.exp(-decay0 * dm * t)
    body /= np.max(np.abs(body)) + 1e-9
    sub = np.sin(2 * np.pi * f0 * 0.5 * t) * np.exp(-decay0 * 0.8 * t) * 0.6  # 가슴 텀프
    click = rng.standard_normal(n) * np.exp(-t * 90) * 0.5   # 말렛 타격 트랜지언트
    mix = np.tanh((body + sub + click) * 1.6)                # 소프트 새추레이션(따뜻함·크게)
    return mix * amp


def reverb(x, amount, ir_len, seed):                        # 감쇠 노이즈 IR 컨볼루션(방 울림)
    rng = np.random.default_rng(seed)
    m = int(sr * ir_len)
    ir = rng.standard_normal(m) * np.exp(-np.arange(m) / sr * 16)
    wet = np.convolve(x, ir)[:len(x)]
    wet /= np.max(np.abs(wet)) + 1e-9
    return x + wet * amount * np.max(np.abs(x))


dur = 1.35
N = int(sr * dur)
out = np.zeros(N)
h1 = drum(92, 0.5, 0.72, decay0=6.5, drop=0.42, seed=11)    # 두
out[:len(h1)] += h1
o2 = int(sr * 0.23)
h2 = drum(64, 1.05, 1.0, decay0=4.2, drop=0.5, seed=23)     # 둥(더 깊고 큼)
out[o2:o2 + min(len(h2), N - o2)] += h2[:N - o2]

out = reverb(out, amount=0.22, ir_len=0.3, seed=7)          # 공간감
out = out / np.max(np.abs(out)) * 0.97                       # 풀스케일 근접(크게)
fi = int(sr * 0.001); out[:fi] *= np.linspace(0, 1, fi)
fo = int(sr * 0.12); out[-fo:] *= np.linspace(1, 0, fo)

pcm = (out * 32767).astype(np.int16)
outp = Path("assets/sfx/reveal.wav"); outp.parent.mkdir(parents=True, exist_ok=True)
with wave.open(str(outp), "w") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())
e1 = np.sqrt(np.mean(out[:int(sr * 0.2)] ** 2))
e2 = np.sqrt(np.mean(out[o2:o2 + int(sr * 0.25)] ** 2))
print(f"wrote {outp} · {len(pcm)/sr:.2f}s · peak {np.max(np.abs(out)):.2f} · "
      f"'두' RMS {e1:.3f} / '둥' RMS {e2:.3f}")
