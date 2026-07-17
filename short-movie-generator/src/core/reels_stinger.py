"""reels_stinger — 쇼츠 오프닝 훅 뒤에 붙는 '지도 → 해역 락온 → 수심 하강' 스팅어(9:16, ~2.3초).

운영자 확정(플랜 B): 롱폼의 하강 모션(`longform.motion.render_locate_descent`)을 그대로 재사용해
세로(720×1280)·압축 타이밍으로 렌더한다. 화면에 표시되는 **수심은 종의 실제 서식수심**(날조 아님),
해역은 일반화된 라벨(정확한 좌표·숫자는 노출하지 않음 — 하드룰 '임의 좌표 금지' 준수).

반환: {"path": mp4, "duration": s} 또는 None(실패 시 스팅어 없이 진행 — 발행 불정지).
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


def _depth_max(depth_range_m: str) -> int | None:
    """서식수심 최댓값(m). 실제 수심 데이터가 없으면 None(→ 스팅어 생략)."""
    nums = [int(x) for x in re.findall(r"\d+", depth_range_m or "")]
    return max(nums) if nums else None


def _zones_for(depth: int) -> list[tuple]:
    """수심 눈금 지층(일반 심해층 — 종 수심 이하만 표시). 과장·날조 없음."""
    z = [(100, "有光層"), (600, "薄明層"), (2500, "漸深層"), (4600, "深海層")]
    keep = [(d, n) for d, n in z if d < max(int(depth), 250)]
    return keep or [(100, "有光層")]


def build_stinger(info, out_mp4: str, work_dir: str) -> dict | None:
    """종 정보로 9:16 하강 스팅어 mp4 생성(무음 오디오 포함 → 본문과 concat 호환)."""
    try:
        from src.core.longform import motion
    except Exception as e:  # noqa: BLE001
        log.warning("[stinger] motion 로드 실패 → 스팅어 생략: %s", e)
        return None
    depth = _depth_max(getattr(info, "depth_range_m", "") or "")
    if depth is None:
        # ★수심 위치를 모르는 생물은 지도·수심 하강 스팅어를 생략(운영자 확정 · 날조 방지)
        log.info("[stinger] 서식수심 데이터 없음 → 지도·수심 스팅어 생략")
        return None
    wd = Path(work_dir)
    frames_dir = wd / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    try:
        spec = motion.MotionSpec(target_depth_m=depth, region_label_jp="生息海域",
                                 region_label_en="HABITAT", zones=_zones_for(depth))
        # 9:16 세로 + 압축 타이밍(총 ~2.3초) + 세로용 map_box
        cfg = motion.MotionConfig(W=720, H=1280, FPS=24, t_map=0.9, t_flash=0.15,
                                  t_desc=1.0, t_hold=0.25, map_box=(70, 300, 650, 820))
        r = motion.render_locate_descent(str(frames_dir), spec, cfg)
    except Exception as e:  # noqa: BLE001
        log.warning("[stinger] 렌더 실패 → 스팅어 생략: %s", e)
        return None
    # ★프레임 → mp4 + '지도 스캔 → 해역 락온 → 수심 하강' 효과음(롱폼과 동일 체계).
    #   예전엔 무음(anullsrc)이라 지도줌·수심 하강 애니가 소리 없이 지나갔다(운영자 지적) →
    #   모션 단계에 맞춰 scan/lockon/splash SFX를 입힌다. SFX 실패 시 무음으로 폴백(발행 불정지).
    total = float(r["total_s"])
    ms = lambda t: max(0, int(t * 1000))  # noqa: E731
    scan_s, lockon_s, splash_s = 0.0, cfg.t_map, cfg.t_map + cfg.t_flash
    aud_inputs, aud_fc, amap = [], "", "0:a"
    try:
        from src.core.longform import sfx as SFX
        sd = SFX.gen_all(str(wd / "sfx"))
        aud_inputs = ["-f", "lavfi", "-t", f"{total:.3f}",
                      "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                      "-i", sd["scan"], "-i", sd["lockon"], "-i", sd["splash"]]
        aud_fc = (f";[1:a]volume=0[bed];"
                  f"[2:a]adelay={ms(scan_s)}|{ms(scan_s)},volume=1.3[sc];"
                  f"[3:a]adelay={ms(lockon_s)}|{ms(lockon_s)},volume=1.3[lk];"
                  f"[4:a]adelay={ms(splash_s)}|{ms(splash_s)},volume=1.5[sp];"
                  f"[bed][sc][lk][sp]amix=inputs=4:duration=first:normalize=0,"
                  f"alimiter=limit=0.95[a]")
        amap = "[a]"
    except Exception as e:  # noqa: BLE001
        log.warning("[stinger] SFX 생성 실패 → 무음 스팅어로 진행: %s", e)
        aud_inputs = ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
    try:
        rc = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-framerate", str(r["fps"]), "-i", r["frames_glob"], *aud_inputs,
             "-filter_complex", f"[0:v]scale=720:1280,setsar=1[v]{aud_fc}",
             "-map", "[v]", "-map", amap, "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-crf", "19", "-c:a", "aac", "-b:a", "128k", "-shortest", str(out_mp4)],
            timeout=120)
    except Exception as e:  # noqa: BLE001
        log.warning("[stinger] 인코딩 오류 → 스팅어 생략: %s", e)
        return None
    if rc.returncode != 0 or not Path(out_mp4).exists() or Path(out_mp4).stat().st_size < 10_000:
        log.warning("[stinger] 인코딩 실패 → 스팅어 생략")
        return None
    return {"path": str(out_mp4), "duration": float(r["total_s"])}


def build_map_cut(lat: float, lon: float, region_jp: str | None, region_en: str | None,
                  out_mp4: str, work_dir: str, dur: float = 3.2) -> dict | None:
    """★침몰 위치 지도 컷(9:16, 무음): 우리 세계지도 → 침몰 해역 락온 → 지점 마커 + 해역명.
    난파선 다큐 본문(무음) 시퀀스의 '사고·침몰' 구간에 삽입되며, 나레이션이 위에 얹힌다
    (그래서 지도 컷 자체는 무음 — SFX를 넣으면 나레이션과 겹친다). 실패 시 None(지도 컷 생략).

    ★난파선 좌표는 위키백과에 문서화된 사실 → 지도 표기는 하드룰 '임의 좌표 금지' 대상이 아니다."""
    import shutil
    try:
        from src.core.longform import motion
    except Exception as e:  # noqa: BLE001
        log.warning("[mapcut] motion 로드 실패 → 지도 컷 생략: %s", e)
        return None
    wd = Path(work_dir); frames = wd / "mapframes"
    frames.mkdir(parents=True, exist_ok=True)
    nx = lon / 360.0
    ny = (90.0 - lat) / 180.0
    spec = motion.MotionSpec(region_nx=nx, region_ny=ny,
                             region_label_jp=region_jp or "沈没地点",
                             region_label_en=region_en or "SINKING SITE",
                             locate_label="LOCATING WRECK…")
    cfg = motion.MotionConfig(W=720, H=1280, FPS=30, map_box=(70, 300, 650, 820))
    FPS = 30
    t_anim = max(1.6, dur * 0.62)          # 스캔 → 줌인
    n_anim = max(2, int(t_anim * FPS))
    n_hold = max(1, int(max(0.8, dur - t_anim) * FPS))   # 마지막(락온) 홀드
    try:
        for i in range(n_anim):
            f = motion._map_frame(min(1.0, i / (n_anim - 1)), spec, cfg)
            f.convert("RGB").save(str(frames / f"mc_{i:04d}.png"))
        last = frames / f"mc_{n_anim - 1:04d}.png"
        for j in range(n_hold):             # 홀드는 마지막 프레임 복사(재렌더 불필요)
            shutil.copyfile(last, frames / f"mc_{n_anim + j:04d}.png")
    except Exception as e:  # noqa: BLE001
        log.warning("[mapcut] 프레임 렌더 실패 → 지도 컷 생략: %s", e)
        return None
    total = n_anim + n_hold
    try:
        rc = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
             "-i", str(frames / "mc_%04d.png"), "-frames:v", str(total),
             "-vf", "scale=720:1280,setsar=1,format=yuv420p",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19", "-an", str(out_mp4)],
            timeout=180)
    except Exception as e:  # noqa: BLE001
        log.warning("[mapcut] 인코딩 오류 → 지도 컷 생략: %s", e)
        return None
    if rc.returncode != 0 or not Path(out_mp4).exists() or Path(out_mp4).stat().st_size < 10_000:
        log.warning("[mapcut] 인코딩 실패 → 지도 컷 생략")
        return None
    return {"path": str(out_mp4), "duration": round(total / FPS, 3)}


def prepend_to_body(stinger_path: str, body_video: str, out_video: str) -> bool:
    """스팅어 + 본문영상을 이어붙인다(스케일·오디오 정합 concat 필터, 재인코딩). 성공 시 True."""
    try:
        rc = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", stinger_path, "-i", body_video,
             "-filter_complex",
             "[0:v]scale=720:1280,setsar=1,fps=24[v0];[1:v]scale=720:1280,setsar=1,fps=24[v1];"
             "[v0][0:a][v1][1:a]concat=n=2:v=1:a=1[v][a]",
             "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-crf", "19", "-c:a", "aac", "-b:a", "192k", out_video],
            timeout=240)
        return rc.returncode == 0 and Path(out_video).exists() and Path(out_video).stat().st_size > 10_000
    except Exception as e:  # noqa: BLE001
        log.warning("[stinger] 본문 결합 실패: %s", e)
        return False
