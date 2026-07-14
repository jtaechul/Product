"""제품 등장(리빌) 효과음 '빠밤' — 썰피자식 드라마틱 두 방 스팅. 직접 합성(저작권 세이프).
'빠'(짧은 브라스 스탭) → '밤'(크게 터지는 브라스 코드 + 저음). 결정론(seed 고정)."""
import wave
from pathlib import Path
import numpy as np

sr = 44100
rng = np.random.default_rng(7)


def brass(freq, length, decay, nharm=10, detune=0.004):
    """브라스풍 톤 — 리치한 하모닉스(톱니 근사) + 살짝 디튠, 빠른 어택 + 지수 감쇠."""
    m = int(sr * length); tt = np.arange(m) / sr
    sig = np.zeros(m)
    for h in range(1, nharm + 1):
        a = 0.85 ** (h - 1)
        sig += a * np.sin(2 * np.pi * freq * h * tt)
        sig += 0.5 * a * np.sin(2 * np.pi * freq * (1 + detune) * h * tt)  # 디튠 겹침(두께)
    sig /= np.max(np.abs(sig))
    env = np.exp(-decay * tt)
    at = int(sr * 0.006); env[:at] *= np.linspace(0, 1, at)   # 빠른 어택
    return sig * env


dur = 0.85
n = int(sr * dur)
out = np.zeros(n)

# '빠' — 짧은 픽업 스탭(낮은 브라스), t=0
p1 = brass(147, 0.14, 20)                    # D3
out[:len(p1)] += 0.62 * p1

# '밤' — 크게 터지는 메인 히트: 밝은 장3화음 브라스 + 저음 thump, t≈0.17s, 길게
h2 = int(sr * 0.17); rem = n - h2; tt = np.arange(rem) / sr
chord = np.zeros(rem)
for f in (196, 247, 392):                    # G3 · B3 · G4 (밝고 웅장)
    c = brass(f, rem / sr, 5.5)
    chord[:len(c)] += c[:len(c)]
chord /= np.max(np.abs(chord))
thump = np.sin(2 * np.pi * 82 * tt) * np.exp(-8 * tt)          # 저음 무게감
subhit = np.sin(2 * np.pi * 55 * tt) * np.exp(-14 * tt)        # 킥 같은 초저역 임팩트
out[h2:] += 0.95 * chord + 0.7 * thump + 0.5 * subhit

out = out / np.max(np.abs(out)) * 0.97
fi = int(sr * 0.003); out[:fi] *= np.linspace(0, 1, fi)
fo = int(sr * 0.07); out[-fo:] *= np.linspace(1, 0, fo)

pcm = (out * 32767).astype(np.int16)
outp = Path("assets/sfx/reveal.wav"); outp.parent.mkdir(parents=True, exist_ok=True)
with wave.open(str(outp), "w") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())
# 두 방(빠·밤) 에너지 확인
e1 = np.sqrt(np.mean(out[:int(sr * 0.15)] ** 2))
e2 = np.sqrt(np.mean(out[h2:h2 + int(sr * 0.25)] ** 2))
print(f"wrote {outp} · {len(pcm)/sr:.2f}s · '빠' RMS {e1:.3f} / '밤' RMS {e2:.3f} (밤>빠 이어야 드라마틱)")
