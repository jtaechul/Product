"""리메이크 제작 자가 점검(돈 0원) — 새 편을 처음부터 끝까지 가짜 호출로 돌린다(사장님 지시 2026-10-10: "영상 만드는 거 오류 없게끔 다시 확인").
관리자 화면이 커밋하는 모양 그대로 episode.json을 만들고 ① 스토리보드 ② 영상 ③ 본편만 다시(한도 전·후) ④ 끝 광고만 다시 ⑤ 다시 조립 ⑥ 점검 모드
+ 고장 상황: AI 시간표 실패 / 영상 AI가 지시문을 막음 / 내레이션 빈 녹음 / 얼굴 위치 일부 실패 / 끝 그림 띠 오탐 / 사람을 바꾸라는 글(동물 있는 원본).
돈 드는 호출은 전부 가짜(기록만), 원본·결과 영상은 ffmpeg 시험 영상(사람 없음). 완성본은 9:16·중간 파일 0개·지시문 위험 낱말 0개여야 통과.
실행: python3 pet-episodes/tools/dry_run_remake.py [작업 폴더]   (코드를 고치면 push 전에 반드시 — 워크플로 pet-episode-selftest가 자동으로도 돈다)"""
from __future__ import annotations

import base64
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import episode as E  # noqa: E402

FF = os.environ.get("FFMPEG", "ffmpeg")
ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="dry_remake_")) / "dry_remake"
shutil.rmtree(ROOT, ignore_errors=True)
ROOT.mkdir(parents=True)
FAILS: list[str] = []


def vid(path: Path, sec: float, w: int, h: int):
    subprocess.run([FF, "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={w}x{h}:rate=24:duration={sec}",
                    "-f", "lavfi", "-i", f"sine=frequency=330:duration={sec}", "-shortest", "-c:v", "libx264", "-crf", "28",
                    "-c:a", "aac", "-pix_fmt", "yuv420p", str(path)], check=True)


def frame(path: Path, w: int, h: int, band: bool = False):
    subprocess.run([FF, "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={w}x{h}", "-frames:v", "1", str(path)], check=True)
    if band:
        from PIL import Image, ImageDraw
        im = Image.open(path).convert("RGB")
        ImageDraw.Draw(im).rectangle((0, 0, w, h // 5), fill=(0, 0, 0))
        im.save(path)


SRC = ROOT / "src.mp4"
vid(SRC, 16.2, 720, 400)                                  # 가로 원본(타일매트 편과 같은 크기)
BODY = ROOT / "body.mp4"
vid(BODY, 9.5, 720, 1280)                                 # 영상 AI가 돌려주는 본편(가짜)
END = ROOT / "end.mp4"
vid(END, 4.0, 720, 1280)                                  # 끝 광고 영상(가짜)
END_IMG = ROOT / "end.png"
frame(END_IMG, 720, 1280)
END_IMG_BAND = ROOT / "end_band.png"
frame(END_IMG_BAND, 720, 1280, band=True)
BOARD = ROOT / "board.jpg"                                # 12칸 격자(4x3, 1792x2400) — 칸마다 무늬가 있는 시험 화면
from PIL import Image  # noqa: E402

_cell = ROOT / "cell.png"
frame(_cell, 448, 800)
_tile = Image.new("RGB", (1792, 2400))
for k in range(12):
    _tile.paste(Image.open(_cell), ((k % 4) * 448, (k // 4) * 800))
_tile.save(BOARD, quality=90)

TL = [{"t": f"{i / 2:.1f}-{(i + 1) / 2:.1f}", "action": a, "mouth": "closed", "sound": "paws on tile", "camera": "Fixed."} for i, a in enumerate(
    ["Woman walks in carrying two bowls.", "Woman bends down.", "Woman sets bowls on the floor.", "Woman starts rising.",
     "White dog and tan dog sprint in from the right.", "Tan dog collides into white dog.", "Both dogs tumble over each other.",
     "Dogs separate.", "Tan dog recovers.", "White dog hits the cabinet.", "Tan dog eats.", "White dog gets up.", "Both dogs eat.",
     "Both dogs eat.", "Both dogs eat.", "Both dogs lick bowls.", "Both dogs lick bowls.", "Both dogs lick bowls.", "Both dogs lick bowls."])]
RISKY_WORDS = r"collid\w*|crash\w*|\bhits?\b|crop top|shorts|slippers|replace the people|bare legs"


def make_ep(name: str, **over):
    d = ROOT / name
    (d / "requests").mkdir(parents=True)
    (d / "work").mkdir()
    ep = {"kind": "remake", "menuName": "리메이크 · 자가 점검", "clips": [],
          "source": {"youtube": "", "title": "시험", "music": ""},
          "remake": {"swap": "1) turn the tan dog into the Shiba Inu from image 1; 2) turn the white dog into a cream-coloured Shiba Inu",
                     "keep_people": True,
                     "cast": "exactly one real human woman (the owner, unchanged - grey crop top, black shorts and slippers) and two dogs, both Shiba Inus",
                     "swap_ko": "강아지 두 마리 → 시바견, 주인은 그대로", "ending": "The Shiba Inu calmly walks across the new mat, looking smug.",
                     "big": "타일 바닥 드리프트\n이제 그만!", "sub": "앞면은 러그 뒤는 방수 타일\n걱정 없이 뛰어놀게", "vo": "드리프트는 이제 그만. 구매는 프로필 링크에서",
                     "cut": "", "whimper": False, "music_pick": "", "ad": "vo", "ad_copy": True, "method": "composite", "res": "720p",
                     "pre_enhance": False, "upscale": 0, "cap": 5, **over},
          "caption": "x", "hashtags": ["#강아지매트"],
          "product": {"title": "시험 매트", "brand": "", "category": "기타", "reason": "x", "link": "https://link.coupang.com/x",
                      "image": "https://example.com/p.png"}}
    (d / "episode.json").write_text(json.dumps(ep, ensure_ascii=False, indent=2))
    return d, ep


def install_mocks(flags: dict) -> list:
    calls: list[str] = []
    E._key = lambda k: "x"
    E._check_stop = lambda *a, **k: None
    E._pick_model = lambda key, models: models[0]
    E._remake_src = lambda i, w: (shutil.copy(SRC, w / "_src.mp4"), w / "_src.mp4")[1]

    def vj(video, prompt):
        if "pieces" in prompt:
            calls.append("pick")
            return {"pieces": [[0, 9.5]], "hook": "h", "why": "w"}
        calls.append("timeline")
        return {} if flags.get("tl_fail") else {"steps": TL}
    E._video_json = vj
    E._vision_json = lambda img, prompt: (calls.append("vision"), {"place": "top", "why": "t"})[1]
    n_omni = {"n": 0}

    def omni(k, body):
        n_omni["n"] += 1
        calls.append("omni")
        text = [x["text"] for x in body["input"] if x.get("type") == "text"][0]
        bad = re.search(RISKY_WORDS, text, re.I)
        if bad:
            raise RuntimeError(f"위험 낱말이 지시문에 있음: {bad.group(0)}")
        if flags.get("block_once") and n_omni["n"] == 1:
            raise RuntimeError('Omni HTTP 400: {"error":{"message":"Input blocked","code":"content_blocked"}}')
        task = body["generation_config"]["video_config"]["task"]
        return (BODY if task == "edit" else END).read_bytes()
    E._omni_run = omni

    def gi(prompt, refs, out, aspect="9:16", size=""):
        calls.append("image")
        if "grid" in prompt:
            shutil.copy(BOARD, out)
        elif flags.get("end_band") and "real product" in prompt and not flags.get("_banded"):
            flags["_banded"] = True
            shutil.copy(END_IMG_BAND, out)
        else:
            shutil.copy(END_IMG, out)
        return {"ok": True}
    E.gen_image = gi
    n_tts = {"n": 0}

    def http(url, data=None, headers=None, timeout=60):
        if data is None:
            calls.append("product")
            return 200, END_IMG.read_bytes()
        if b"AUDIO" in data:
            n_tts["n"] += 1
            calls.append("tts")
            if flags.get("tts_empty") and n_tts["n"] == 1:
                pcm = b"".join(struct.pack("<h", 0) for _ in range(24000))
            else:
                pcm = b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 220 * i / 24000))) for i in range(24000 * 2))
            return 200, json.dumps({"candidates": [{"content": {"parts": [{"inlineData": {"data": base64.b64encode(pcm).decode()}}]}}]}).encode()
        if b"HUMAN person" in data:
            calls.append("head")
            if flags.get("head_fail") and len([c for c in calls if c == "head"]) % 7 == 0:
                return 500, b"temporary"
            return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps(
                [{"box_2d": [60, 219 + 400, 240, 219 + 540], "label": "head"}])}]}}]}).encode()
        raise RuntimeError(f"예상 못 한 인터넷 호출: {url[:80]}")
    E._http = http
    return calls


def run(d: Path, ep: dict, req: dict, flags: dict, title: str, expect_stop: str = "") -> dict:
    calls = install_mocks(flags)
    work = d / "work"
    try:
        log = json.loads((work / "log.json").read_text())
    except FileNotFoundError:
        log = {}
    try:
        E.step_remake(ep, d, work, log, req)
        ok, err = True, ""
    except Exception as x:  # noqa: BLE001
        ok, err = False, str(x)[:200]
    (work / "log.json").write_text(json.dumps(log, ensure_ascii=False))
    r = log.get("remake", {})
    leftovers = sorted(x.name for x in work.glob("_*"))
    fin = work / "final.mp4"
    counts = {c: calls.count(c) for c in dict.fromkeys(calls)}
    line = f"[{title}] {'통과' if ok else '멈춤: ' + err} | 호출 {counts} | 장부 {r.get('spent')}"
    good = ok if not expect_stop else (not ok and expect_stop in err)
    if ok and req["remake"]["mode"] == "full":
        try:
            E._assert_vertical(fin, "완성본")
            line += f" | 완성본 {round(E._dur(fin), 2)}초 {E._wh(fin)} 9:16"
        except Exception as x:  # noqa: BLE001
            good = False
            line += f" | ⚠ 완성본 검사 실패: {str(x)[:120]}"
    if leftovers:
        good = False
        line += f" | ⚠ 중간 파일 남음 {leftovers}"
    if re.search(RISKY_WORDS, r.get("edit_prompt", ""), re.I):
        good = False
        line += " | ⚠ 지시문에 위험 낱말"
    print(("OK  " if good else "FAIL") + " " + line, flush=True)
    if not good:
        FAILS.append(title)
    return log


d, ep = make_ep("normal")
log = run(d, ep, {"remake": {"mode": "board"}}, {}, "① 스토리보드")
print("    세로", log["remake"].get("vertical"), "| cast:", log["remake"].get("cast_used"))
run(d, ep, {"remake": {"mode": "full"}}, {}, "② 영상")
run(d, ep, {"remake": {"mode": "full", "redo": ["body"]}}, {}, "③ 본편만 다시(한도 5: 지우기 전에 멈춰야)", expect_stop="아무것도 지우지 않고")
if not ((d / "work" / "remake.mp4").exists() and (d / "work" / "rm_seg1.mp4").exists()):
    FAILS.append("③ 한도 멈춤 뒤 본편 파일이 사라짐")
    print("FAIL ③ 한도 멈춤 뒤 본편 파일이 사라짐")
ep["remake"]["cap"] = 10
run(d, ep, {"remake": {"mode": "full", "redo": ["body"]}}, {}, "③ 본편만 다시(한도 10)")
run(d, ep, {"remake": {"mode": "full", "redo": ["ending"]}}, {}, "④ 끝 광고만 다시")
run(d, ep, {"remake": {"mode": "full"}}, {}, "⑤ 다시 조립(돈 0)")
d2, ep2 = make_ep("check")
run(d2, ep2, {"remake": {"mode": "check"}}, {}, "⑥ 점검 모드")
d3, ep3 = make_ep("tlfail")
run(d3, ep3, {"remake": {"mode": "board"}}, {"tl_fail": True}, "⑦ AI 시간표 실패 → 스토리보드")
run(d3, ep3, {"remake": {"mode": "full"}}, {"tl_fail": True}, "⑦ AI 시간표 실패 → 영상")
d4, ep4 = make_ep("block")
run(d4, ep4, {"remake": {"mode": "board"}}, {}, "⑧ 지시문 막힘 → 스토리보드")
log = run(d4, ep4, {"remake": {"mode": "full"}}, {"block_once": True}, "⑧ 지시문 막힘 → 영상(짧은 지시문으로 한 번 더)")
if not log["remake"].get("prompt_min"):
    FAILS.append("⑧ 짧은 지시문이 안 쓰임")
d5, ep5 = make_ep("tts")
run(d5, ep5, {"remake": {"mode": "board"}}, {}, "⑨ 빈 녹음 → 스토리보드")
run(d5, ep5, {"remake": {"mode": "full"}}, {"tts_empty": True}, "⑨ 빈 녹음 → 영상(한 번 더 녹음)")
d6, ep6 = make_ep("head")
run(d6, ep6, {"remake": {"mode": "board"}}, {}, "⑩ 얼굴 위치 일부 실패 → 스토리보드")
log = run(d6, ep6, {"remake": {"mode": "full"}}, {"head_fail": True}, "⑩ 얼굴 위치 일부 실패 → 영상(못 읽은 장면만 다시)")
if (log["remake"].get("faces") or {}).get("missing"):
    FAILS.append("⑩ 얼굴 위치를 끝내 못 찾은 장면이 있음")
d7, ep7 = make_ep("endband")
run(d7, ep7, {"remake": {"mode": "board"}}, {}, "⑪ 끝 그림 띠 → 스토리보드")
log = run(d7, ep7, {"remake": {"mode": "full"}}, {"end_band": True}, "⑪ 끝 그림 띠 오탐 → 영상(한 번 다시 그림)")
print("    끝 그림:", log["remake"].get("end_bands"))
d8, ep8 = make_ep("nopeople", keep_people=False, cast="",
                  swap="1) replace the woman's head with the head of the Shiba Inu from image 1; 2) turn her visible arms and legs into furry Shiba legs")
run(d8, ep8, {"remake": {"mode": "board"}}, {}, "⑫ 사람을 시바견으로(동물 있는 원본 → 자동 바로잡기) 스토리보드")
log = run(d8, ep8, {"remake": {"mode": "full"}}, {}, "⑫ 영상")
if not log["remake"].get("swap_fixed"):
    FAILS.append("⑫ 동물 있는 원본인데 사람을 바꾸게 둠")
print("\n결과:", "모두 통과" if not FAILS else "실패 " + ", ".join(FAILS))
sys.exit(1 if FAILS else 0)
