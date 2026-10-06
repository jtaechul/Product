"""Real-ESRGAN(일반 영상용 x4v3, 경량 SRVGG) 업스케일 — Genjutsu식 '합성 뒤 고화질' 단계(사용자 지시 2026-10).
basicsr 없이 순수 torch(CPU)로 돌린다(깃허브 러너는 GPU 없음). 가중치는 처음 한 번 깃허브 릴리스에서 받아 둔다(약 5MB x2, 무료).
사용: upscale_video(src, out, scale=2, dn=0.3)  — 360x640 → 720x1280. 모델은 x4로 그린 뒤 원하는 배율로 줄인다(더 또렷함).
"""
from __future__ import annotations

import os
import subprocess
import sys
import urllib.request
from pathlib import Path

MODELS = Path(os.environ.get("ESR_MODELS", str(Path(__file__).resolve().parent.parent / "models")))
RELEASE = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/"
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")


def _weights(name: str) -> Path:
    MODELS.mkdir(parents=True, exist_ok=True)
    p = MODELS / name
    if not p.exists() or p.stat().st_size < 1_000_000:
        req = urllib.request.Request(RELEASE + name, headers={"User-Agent": "pet-episodes/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            p.write_bytes(r.read())
    return p


def _model(dn: float):
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    class SRVGG(nn.Module):                               # basicsr SRVGGNetCompact(num_feat=64, num_conv=32, upscale=4, prelu)
        def __init__(self):
            super().__init__()
            layers = [nn.Conv2d(3, 64, 3, 1, 1), nn.PReLU(64)]
            for _ in range(32):
                layers += [nn.Conv2d(64, 64, 3, 1, 1), nn.PReLU(64)]
            layers.append(nn.Conv2d(64, 3 * 16, 3, 1, 1))
            self.body = nn.ModuleList(layers)
            self.up = nn.PixelShuffle(4)

        def forward(self, x):
            out = x
            for m in self.body:
                out = m(out)
            return self.up(out) + F.interpolate(x, scale_factor=4, mode="nearest")

    def load(name):
        sd = torch.load(str(_weights(name)), map_location="cpu")
        return sd.get("params_ema") or sd.get("params") or sd

    a = load("realesr-general-x4v3.pth")
    if dn > 0:                                            # 노이즈 제거 강도: 두 가중치를 섞는다(원작 -dn 옵션과 같음)
        b = load("realesr-general-wdn-x4v3.pth")
        a = {k: a[k] * (1 - dn) + b[k] * dn for k in a}
    m = SRVGG()
    m.load_state_dict(a, strict=True)
    m.eval()
    torch.set_num_threads(max(1, os.cpu_count() or 1))
    return m


def _wh(src: Path) -> tuple[int, int]:
    r = subprocess.run([FFMPEG, "-hide_banner", "-i", str(src)], capture_output=True, text=True)
    import re
    m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", r.stderr)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def upscale_video(src: Path, out: Path, scale: int = 2, dn: float = 0.3, fps: int = 24, crf: int = 18) -> dict:
    """src(소리 없음이어도 됨) → out(영상만, 가로세로 scale배). 프레임을 파이프로 흘려 메모리를 아낀다."""
    _ensure_torch()
    import torch
    w, h = _wh(src)
    if not w:
        raise RuntimeError(f"업스케일: 영상 크기를 못 읽음 {src}")
    W, H = w * scale, h * scale
    model = _model(dn)
    dec = subprocess.Popen([FFMPEG, "-v", "error", "-i", str(src), "-an", "-vf", f"fps={fps}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE)
    enc = subprocess.Popen([FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
                            "-an", "-c:v", "libx264", "-crf", str(crf), "-preset", "medium", "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    n, frame_bytes = 0, w * h * 3
    with torch.no_grad():
        while True:
            buf = dec.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            x = torch.frombuffer(bytearray(buf), dtype=torch.uint8).reshape(h, w, 3).permute(2, 0, 1).float().div_(255).unsqueeze(0)
            y = model(x)                                   # x4
            if scale != 4:
                y = torch.nn.functional.interpolate(y, size=(H, W), mode="area")
            y = y.clamp_(0, 1).mul_(255).round_().to(torch.uint8).squeeze(0).permute(1, 2, 0).contiguous()
            enc.stdin.write(bytes(y.untyped_storage()))   # numpy 없이 바로 바이트로(torch 2.x)
            n += 1
    dec.stdout.close()
    enc.stdin.close()
    enc.wait()
    dec.wait()
    if enc.returncode != 0 or not out.exists():
        raise RuntimeError("업스케일 인코딩 실패")
    return {"ok": True, "frames": n, "size": f"{W}x{H}", "scale": scale, "dn": dn, "model": "realesr-general-x4v3"}


def _ensure_torch():
    """깃허브 러너에는 torch가 없다 → 필요할 때만 CPU판을 설치한다(약 190MB, 1분 안팎). 워크플로를 무겁게 하지 않으려고 여기서 한다."""
    try:
        import torch  # noqa: F401
        return
    except ImportError:
        pass
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--index-url", "https://download.pytorch.org/whl/cpu", "torch==2.4.1"], check=True)


if __name__ == "__main__":                                # python upscale.py in.mp4 out.mp4 [scale] [dn]
    a = sys.argv[1:]
    print(upscale_video(Path(a[0]), Path(a[1]), int(a[2]) if len(a) > 2 else 2, float(a[3]) if len(a) > 3 else 0.3))
