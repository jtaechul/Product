#!/usr/bin/env python3
"""사진 1장 → Veo 영상 1컷 (이미지→영상). 돈이 나가는 유일한 자리.

    from veo import make_clip, estimate_krw
    make_clip("drone glide over the pool ...", Path("shot_1.png"), 4, Path("veo_1.mp4"), seed=123)

어디서 가져왔나
    jtaechul/verdict-theater 의 src/veo.py + src/cost.py 를 이 프로젝트에 맞게 줄였다.
    그쪽에서 0원·유료로 실측한 규격만 쓴다 (아래 '실측' 표시). 짐작으로 적은 값은 없다.

실측 (verdict-theater, 모델 veo-3.1-lite-generate-preview)
    - 요청: POST models/{모델}:predictLongRunning
      instances[0].prompt / instances[0].image = {bytesBase64Encoded, mimeType} (둘 다 있어야 한다, 하나만 넣으면 400)
      parameters: aspectRatio 16:9·9:16 만 / durationSeconds 4~8 / resolution 720p·1080p / seed / personGeneration "ALLOW_ALL"
      negativePrompt·numberOfVideos 는 미지원(400)
    - 1080p 는 4초·6초 모두 "not supported for a duration" 으로 거절 → 720p 만 쓴다
    - 안전 필터에 걸리면 오류가 아니라 done=true 인데 영상이 없다 (raiMediaFilteredCount) → RaiFiltered
    - 돈은 요청이 받아들여진 순간 나간다. 기다리다 실패해도 값은 나갔으므로 요청 직후 장부에 적는다

돈 (2026-10-09 공개 단가 · Veo 3.1 Lite)
    720p $0.05/초 · 1080p $0.08/초. 4초 x 7컷 = 28초 = $1.40 ≈ 2,060원 (환율 1,470).
    두 겹으로 막는다: 한 번 실행 RUN_KRW(기본 3,000원) · 한 달 MONTH_KRW(운영자 확정 50,000원).
    장부는 state/spend.json (저장소에 커밋되어 다음 실행이 이번 달 누적을 안다).

시험용
    VEO_FAKE=1 이면 구글을 부르지 않고 ffmpeg 로 사진을 살짝 움직인 가짜 클립을 만든다 (0원).
    합성 경로를 돈 안 쓰고 검증할 때만 쓴다. 워크플로에서는 켜지 않는다.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "state" / "spend.json"
BASE = "https://generativelanguage.googleapis.com/v1beta"


def _env(name: str, default: str) -> str:
    """워크플로가 빈 문자열을 넘길 수 있다(vars 미설정) → 빈 값은 기본값으로 본다."""
    return (os.environ.get(name) or "").strip() or default


MODEL = _env("VEO_MODEL", "veo-3.1-lite-generate-preview")
RESOLUTION = "720p"                                   # 실측: 1080p 는 4·6초 거절
USD_KRW = float(_env("USD_KRW", "1470"))
RUN_KRW = float(_env("STAY_RUN_KRW", "3000"))         # 1편 2,060원 + 안전필터 재시도 2컷(588원) 안에
MONTH_KRW = float(_env("STAY_MONTH_KRW", "50000"))    # 운영자 확정: 월 5만 원 상한
CALL_CAP = int(_env("VEO_CALL_CAP", "9"))             # 7컷 + 재시도 2번
POLL_SEC, POLL_MAX = 10, 60                           # 10초마다 · 최대 10분
FAKE = _env("VEO_FAKE", "") == "1"

# (이름 조각, 초당 달러) — 모르는 이름은 가장 비싼 값으로 쳐서 한도에 먼저 걸리게 한다
VIDEO_USD_SEC = [("veo-3.1-lite", 0.05), ("veo-3.1-fast", 0.10), ("veo-3.1", 0.40)]
VIDEO_USD_SEC_UNKNOWN = 0.40

_state = {"calls": 0, "spent": 0.0}


class VeoError(RuntimeError):
    pass


class RaiFiltered(VeoError):
    """안전 필터에 걸렸다 — 고장이 아니다. 씨앗을 바꿔 한 번 더 해 볼 수 있다."""


class CapReached(VeoError):
    """돈 한도(한 번 실행 또는 한 달)에 걸렸다. 만든 것은 그대로 남는다."""


def log(*a):
    print("[veo]", *a, flush=True)


# ── 돈 ─────────────────────────────────────────────────────────────────
def clip_krw(sec: float, model: str = MODEL) -> float:
    usd = next((u for k, u in VIDEO_USD_SEC if k in model), VIDEO_USD_SEC_UNKNOWN)
    return usd * max(0.0, float(sec)) * USD_KRW


def estimate_krw(n_clips: int, sec: float) -> float:
    return clip_krw(sec) * n_clips


def _ledger() -> list:
    if not LEDGER.exists():
        return []
    try:
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []                                     # 장부가 깨져도 제작은 멈추지 않는다


def record(krw: float, note: str):
    """쓴 돈 한 줄. 실패해도 예외를 올리지 않는다 (제작은 계속)."""
    try:
        if krw <= 0:
            return
        rows = _ledger()
        rows.append({"date": date.today().isoformat(), "kind": "veo", "krw": round(krw), "note": note[:120]})
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        LEDGER.write_text(json.dumps(rows[-2000:], ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        log("장부에 못 적었다:", e)


def month_total() -> float:
    ym = date.today().isoformat()[:7]
    return float(sum(r.get("krw", 0) for r in _ledger() if str(r.get("date", "")).startswith(ym)))


def spent_this_run() -> float:
    return _state["spent"]


def guard(sec: float):
    """돈을 쓰기 **전에** 세 가지 상한을 본다. 하나라도 걸리면 CapReached."""
    krw = clip_krw(sec)
    if _state["calls"] >= CALL_CAP:
        raise CapReached(f"이번 실행의 영상 호출 상한({CALL_CAP}번)에 걸렸습니다.")
    if _state["spent"] + krw > RUN_KRW:
        raise CapReached(f"한 번 실행 한도({RUN_KRW:,.0f}원)에 걸렸습니다. 여기까지 {_state['spent']:,.0f}원, "
                         f"이 컷 약 {krw:,.0f}원.")
    used = month_total()
    if used + krw > MONTH_KRW:
        raise CapReached(f"이번 달 한도({MONTH_KRW:,.0f}원)에 걸렸습니다. 지금까지 {used:,.0f}원, "
                         f"이 컷 약 {krw:,.0f}원. 다음 달 1일에 풀립니다.")
    return krw


# ── 구글 호출 ─────────────────────────────────────────────────────────
def _key() -> str:
    k = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not k:
        raise VeoError("GEMINI_API_KEY 가 실행 환경에 없습니다")
    return k


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(f"{BASE}/{path}", data=json.dumps(body).encode(), method="POST",
                                 headers={"x-goog-api-key": _key(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        msg = raw[:300]
        try:
            msg = json.loads(raw)["error"]["message"][:300]
        except Exception:  # noqa: BLE001
            pass
        if e.code == 429:
            raise VeoError(f"구글이 영상 생성을 받지 않습니다 (한도/결제). 구글 답: {msg}") from None
        raise VeoError(f"영상 요청 실패 (HTTP {e.code}): {msg}") from None


def _get(path: str) -> dict:
    req = urllib.request.Request(f"{BASE}/{path}", headers={"x-goog-api-key": _key()})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def _find_uri(obj):
    """응답 생김새가 판마다 다르다. 어디에 있든 영상 주소를 찾는다."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("uri", "videoUri", "url") and isinstance(v, str) and v.startswith("http"):
                return v
            got = _find_uri(v)
            if got:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = _find_uri(v)
            if got:
                return got
    return None


def _download(uri: str, out: Path):
    sep = "&" if "?" in uri else "?"
    url = uri if "key=" in uri else f"{uri}{sep}key={_key()}"
    req = urllib.request.Request(url, headers={"x-goog-api-key": _key()})
    with urllib.request.urlopen(req, timeout=600) as r, open(out, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    if out.stat().st_size < 10_000:
        raise VeoError(f"받은 영상이 너무 작습니다 ({out.stat().st_size} 바이트)")


def seed_for(*parts) -> int:
    """같은 숙소·같은 컷이면 같은 씨앗 → 다시 만들어도 구도가 비슷하다."""
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(h[:8], 16) % 2_000_000_000


def _fake_clip(image: Path, sec: float, out: Path):
    """VEO_FAKE 시험용: 사진을 살짝 확대하는 4초 클립 (720x1280 · 24fps · 소리 없음). 0원."""
    frames = int(round(sec * 24))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-t", f"{sec:.2f}", "-i", str(image),
                    "-vf", f"scale=1440:2560,zoompan=z='min(1+0.08*on/{frames},1.08)':d={frames}:"
                           f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=720x1280:fps=24",
                    "-t", f"{sec:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                    "-pix_fmt", "yuv420p", str(out)], check=True)


def _transient(msg: str) -> int:
    """구글 쪽 일시 오류면 몇 초 쉬고 다시 할지, 아니면 0.

    2026-10-09 실측 (stay-run-4): 7컷 중 2컷이 이것으로 빠졌다.
      - HTTP 429 "You exceeded your current quota" — 분당 호출 한도. 바로 다음 컷은 통과했다 → 60초 쉬면 된다 (요청이 거절된 것이라 돈은 안 나갔다)
      - 생성 중 code 13 "internal server issue. Please try again in a few minutes" — 구글 내부 오류 (요청은 받아들여졌으므로 장부에는 적힌다)"""
    low = msg.lower()
    if "429" in msg or "한도/결제" in msg or "quota" in low:
        return 60
    if "internal server" in low or '"code": 13' in msg:
        return 20
    return 0


def make_clip(prompt: str, image: Path, sec: int, out: Path, seed: int | None = None,
              ratio: str = "9:16", mime: str = "image/png", retries: int = 2) -> float:
    """사진 1장 + 지시문 → 영상 1컷. 돌려주는 값은 이 컷에 쓴 돈(원). 구글 일시 오류는 쉬었다가 다시 한다.

    실패 갈래: CapReached(한도) · RaiFiltered(안전필터, 씨앗 바꿔 재시도 가능) · VeoError(그 밖)."""
    if FAKE:
        log(f"VEO_FAKE — 가짜 클립 ({sec}초, 0원): {out.name}")
        _fake_clip(image, sec, out)
        return 0.0
    total = 0.0
    for attempt in range(retries + 1):
        try:
            return total + _make_once(prompt, image, sec, out, seed, ratio, mime)
        except (RaiFiltered, CapReached):
            raise
        except VeoError as e:
            wait = _transient(str(e))
            if not wait or attempt == retries:
                raise
            total += getattr(e, "krw", 0.0)
            log(f"구글 일시 오류 → {wait}초 뒤 다시 ({attempt + 1}/{retries}): {str(e)[:120]}")
            time.sleep(wait)
    raise VeoError("도달할 수 없는 자리")


def _make_once(prompt: str, image: Path, sec: int, out: Path, seed, ratio: str, mime: str) -> float:
    krw = guard(sec)
    log(f"영상 요청 ({sec}초 · {RESOLUTION} · {ratio} · 약 {krw:,.0f}원): {out.name}")
    inst = {"prompt": prompt,
            "image": {"bytesBase64Encoded": base64.b64encode(image.read_bytes()).decode(), "mimeType": mime}}
    params = {"aspectRatio": ratio, "durationSeconds": int(sec), "resolution": RESOLUTION,
              "personGeneration": "ALLOW_ALL"}
    if seed is not None:
        params["seed"] = int(seed)
    op = _post(f"models/{MODEL}:predictLongRunning", {"instances": [inst], "parameters": params})
    _state["calls"] += 1
    name = op.get("name")
    if not name:
        raise VeoError(f"작업 번호를 못 받았습니다: {json.dumps(op, ensure_ascii=False)[:200]}")
    # 돈은 요청이 받아들여진 순간 나간다 → 여기서 적는다
    _state["spent"] += krw
    record(krw, f"{MODEL} {sec}초 {out.name}")

    for i in range(POLL_MAX):
        time.sleep(POLL_SEC)
        st = _get(name)
        if st.get("error"):
            err = VeoError(f"생성 중 실패: {json.dumps(st['error'], ensure_ascii=False)[:250]}")
            err.krw = krw                       # 요청은 받아들여졌으므로 이 컷 값은 이미 장부에 있다
            raise err
        if st.get("done"):
            uri = _find_uri(st)
            if not uri:
                blob = json.dumps(st, ensure_ascii=False)
                if any(k in blob.lower() for k in ("safety", "rai", "blocked", "filtered")):
                    raise RaiFiltered(f"안전 필터에 걸렸습니다: {blob[:250]}")
                raise VeoError(f"완료됐다는데 영상이 없습니다: {blob[:250]}")
            _download(uri, out)
            log(f"완료 {out.name} ({out.stat().st_size / 1e6:.1f}MB)")
            return krw
        if i and i % 6 == 0:
            log(f"…{(i + 1) * POLL_SEC}초 기다리는 중 ({out.name})")
    raise VeoError(f"{POLL_MAX * POLL_SEC}초를 기다려도 끝나지 않았습니다: {out.name}")


if __name__ == "__main__":
    print(f"모델 {MODEL} · {RESOLUTION} · 초당 {clip_krw(1):,.1f}원 (환율 {USD_KRW:,.0f})")
    print(f"1편(4초 x 7컷) 약 {estimate_krw(7, 4):,.0f}원 · 한 번 실행 한도 {RUN_KRW:,.0f}원 · 한 달 한도 {MONTH_KRW:,.0f}원")
    print(f"이번 달 쓴 돈 {month_total():,.0f}원 (장부 {LEDGER.relative_to(ROOT)})")
