"""제품 등장(리빌) 효과음을 직접 합성 → assets/sfx/reveal.wav (저작권 세이프 · 자체 생성물).
휘익(상승 노이즈 스웹) → 쨍(밝은 벨 임팩트 + 저음 thump) → 반짝 잔향. 결정론(seed 고정)."""
import wave
from pathlib import Path
import numpy as np

sr = 44100
rng = np.random.default_rng(42)
dur = 0.75
n = int(sr * dur)
t = np.arange(n) / sr
out = np.zeros(n)
exp = lambda tt, d: np.exp(-d * tt)

# 1) 휘익(whoosh): 상승 피치 스웹 + 노이즈 스웰 (0~0.28s) → 임팩트로 빨려들어감
wn = int(sr * 0.28); wt = np.arange(wn) / sr
noise = rng.standard_normal(wn)
sweep = np.sin(2 * np.pi * np.cumsum(np.linspace(200, 1600, wn)) / sr)
swell = (wt / wt[-1]) ** 2
out[:wn] += (0.35 * noise + 0.5 * sweep) * swell

# 2) 임팩트(0.26s~): 밝은 벨(G5·D6·G6) + 저음 thump + 짧은 클릭
hs = int(sr * 0.26); ht = np.arange(n - hs) / sr
bell = (1.0 * np.sin(2 * np.pi * 784 * ht) * exp(ht, 10)
        + 0.7 * np.sin(2 * np.pi * 1175 * ht) * exp(ht, 12)
        + 0.5 * np.sin(2 * np.pi * 1568 * ht) * exp(ht, 15))
thump = 0.9 * np.sin(2 * np.pi * 80 * ht) * exp(ht, 16)
click = np.zeros(len(ht)); click[:int(sr * 0.004)] = 1.0
out[hs:] += 0.55 * bell + thump + 0.15 * click

# 3) 반짝 잔향(high shimmer, tremolo)
ss = int(sr * 0.30); st = np.arange(n - ss) / sr
out[ss:] += 0.12 * np.sin(2 * np.pi * 2637 * st) * exp(st, 9) * np.sin(2 * np.pi * 7 * st)

out = out / np.max(np.abs(out)) * 0.97
fi = int(sr * 0.003); out[:fi] *= np.linspace(0, 1, fi)
fo = int(sr * 0.06); out[-fo:] *= np.linspace(1, 0, fo)

pcm = (out * 32767).astype(np.int16)
outp = Path("assets/sfx/reveal.wav"); outp.parent.mkdir(parents=True, exist_ok=True)
with wave.open(str(outp), "w") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())
print(f"wrote {outp} · {len(pcm)/sr:.2f}s · peak {np.max(np.abs(out)):.2f}")
