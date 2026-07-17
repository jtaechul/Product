"""상품 영상 링크(유튜브·인스타·틱톡) → 자동 추출 → 릴리스 캐시 → 라인 후보 (2026-07-16 사용자 지시).

관리자 '새 상품 등록'에서 제품 영상 링크를 넣으면 data/video_links/{row_hash}.json 으로 커밋되고,
candidates 실행 시 이 모듈이:
  ① 이미 추출해 둔 릴리스(product-assets) 자산({row_hash}_link{url해시}.*)이 있으면 그걸 재사용(다운로드)
  ② 없으면 yt-dlp로 영상을 내려받아 릴리스에 업로드(다음 실행부터 재사용) + 로컬 경로 반환
파이프라인은 이 영상을 라인별 후보('제품영상' 태그, 포스터 썸네일)로 올리고, 운영자가 고르면
load_selections→렌더가 그 라인 구간에서 영상을 재생한다(렌더는 mp4/mov/webm/gif 라인 픽 지원).

⚠️ 저작권·정책(§3.2 개정, 2026-07-16 사용자 결정): 이 기능은 '판매자·제조사가 올린 제품 소개 영상'
전용이다. 타인 창작 영상은 Content ID 클레임·저작권 위험 — 관리자 화면에도 같은 경고를 띄운다.
또한 클라우드 러너 IP는 플랫폼(특히 유튜브)이 봇으로 차단할 수 있어 추출은 실패할 수 있다 —
실패해도 제작·후보 생성은 계속되고(이미지 후보만), 텔레그램으로 실패를 알린다.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import requests

from src.product.assets import REPO, TAG, VIDEO_EXTS, _headers

MAX_LINKS = 2
MAX_BYTES = 200 * 1024 * 1024
_CT = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm", ".m4v": "video/x-m4v"}
_BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
# 최후 폴백 — 공개 cobalt(오픈소스 다운로더 서비스) 인스턴스에 다운로드를 위임한다(savefrom과 같은
# 계열). 커뮤니티 인스턴스라 수명이 유동적 — 실패하면 다음 인스턴스로 넘어가고,
# SHORTS_COBALT_INSTANCES 환경변수(콤마 구분)로 교체 가능.
# ⚠️ 대부분의 공개 cobalt(v10+) 인스턴스는 이제 API 키/Turnstile 인증을 요구해(익명 POST 거절:
#   error.api.auth.* ) 서버-서버 위임이 갈수록 막힌다. 그래서 이 자동 폴백은 '되면 좋고' 수준이고,
#   확실한 길은 사람이 브라우저(cobalt.tools 등)에서 받아 관리자로 올리는 것이다(_maybe_notify_fail 안내).
#   SHORTS_COBALT_INSTANCES(콤마 구분)로 직접 교체·확장 가능.
_COBALT_INSTANCES = [
    "https://cobalt-api.kwiatekmiki.com",
    "https://cobalt-backend.canine.tools",
    "https://cobalt-api.meowing.de",
]


def ensure_link_videos(row_hash: str, dest_dir: Path, project_root: Path) -> list:
    """등록된 링크 영상들을 로컬 파일로 확보(릴리스 캐시 우선, 없으면 yt-dlp 추출+업로드). 실패 시 건너뜀."""
    links_path = Path(project_root) / "data" / "video_links" / f"{row_hash}.json"
    if not links_path.exists():
        return []
    try:
        urls = [str(u).strip() for u in (json.loads(links_path.read_text(encoding="utf-8")).get("urls") or [])]
        urls = [u for u in urls if u.startswith("http")][:MAX_LINKS]
    except Exception as e:
        print(f"[vlink] 링크 파일 파싱 실패({e}) — 건너뜀")
        return []
    if not urls:
        return []
    out_dir = Path(dest_dir) / "product_videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    assets = _release_assets()
    out = []
    for url in urls:
        key = f"{row_hash}_link{hashlib.sha1(url.encode()).hexdigest()[:10]}"
        hit = next((a for a in assets
                    if str(a.get("name", "")).startswith(key)
                    and str(a.get("name", "")).lower().endswith(VIDEO_EXTS)), None)
        if hit:  # ① 이전 실행에서 추출해 둔 캐시 재사용 (영상 확장자만 — 실패 마커(.txt)는 제외)
            p = _download_asset(hit, out_dir)
            if p:
                print(f"[vlink] 링크 영상 캐시 재사용: {Path(p).name}")
                out.append(p)
                continue
        local = None
        try:    # ② yt-dlp(PO토큰+클라이언트 폴백) 추출
            local = _ytdlp_download(url, out_dir, key)
        except Exception as e1:
            # ③ 최후: 다운로드를 외부 다운로더 서비스(cobalt)에 위임 — 러너 IP가 아닌
            #    그 서비스의 서버가 유튜브에 접근하므로 러너 IP 차단과 무관하게 성공할 수 있다.
            print("[vlink] yt-dlp 전 방식 차단 → 다운로더 서비스(cobalt) 인스턴스로 위임 시도")
            try:
                local = _cobalt_download(url, out_dir, key)
            except Exception as e2:
                msg = (f"yt-dlp: {str(e1)[:110]}\ncobalt: {type(e2).__name__} {str(e2)[:110]}")
                print(f"[vlink] 링크 영상 추출 최종 실패({url[:70]}) — 이미지 후보만 진행")
                _maybe_notify_fail(url, msg, key, assets)
                continue
        _upload_asset(Path(local))   # 실패해도 이번 실행은 로컬본으로 진행(재사용만 안 됨)
        print(f"[vlink] 링크 영상 추출 완료: {Path(local).name} ({Path(local).stat().st_size >> 20}MB)")
        out.append(str(local))
    return out


def _cobalt_download(url: str, out_dir: Path, key: str) -> str:
    """공개 cobalt 인스턴스에 추출을 위임 — POST {url} → tunnel/redirect URL → 파일 스트림."""
    insts = [i.strip().rstrip("/") for i in (os.environ.get("SHORTS_COBALT_INSTANCES") or "").split(",")
             if i.strip()] or _COBALT_INSTANCES
    last = None
    for inst in insts:
        try:
            r = requests.post(inst + "/", json={"url": url, "videoQuality": "1080",
                                                "youtubeVideoCodec": "h264", "filenameStyle": "basic"},
                              headers={"Accept": "application/json", "Content-Type": "application/json",
                                       "User-Agent": _BROWSER_UA}, timeout=30)
            d = r.json() if r.content else {}
            if d.get("status") not in ("tunnel", "redirect") or not d.get("url"):
                err = (d.get("error") or {}).get("code") if isinstance(d.get("error"), dict) else d.get("error")
                last = RuntimeError(f"{inst}: {d.get('status') or r.status_code} {str(err or '')[:60]}")
                print(f"[vlink] cobalt {inst} 거절({last}) → 다음 인스턴스")
                continue
            dest = out_dir / f"{key}.mp4"
            size = 0
            with requests.get(d["url"], stream=True, timeout=600,
                              headers={"User-Agent": _BROWSER_UA}) as resp:
                resp.raise_for_status()
                with dest.open("wb") as f:
                    for chunk in resp.iter_content(1 << 20):
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise RuntimeError("용량 초과")
                        f.write(chunk)
            if size > 100_000:   # 에러 페이지·빈 응답 방지(최소 크기)
                print(f"[vlink] cobalt 위임 추출 성공({inst}, {size >> 20}MB)")
                return str(dest)
            dest.unlink(missing_ok=True)
            last = RuntimeError(f"{inst}: 결과 파일이 너무 작음({size}B)")
        except Exception as e:
            last = e
            print(f"[vlink] cobalt {inst} 실패({type(e).__name__}: {str(e)[:80]}) → 다음 인스턴스")
    raise last if last else RuntimeError("cobalt 인스턴스 전부 실패")


def video_poster(video_path: Path, out_jpg: Path) -> bool:
    """후보 그리드 썸네일용 포스터 프레임(1초 지점, 폭 480) 추출."""
    try:
        import imageio_ffmpeg
        out_jpg.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-ss", "1", "-i", str(video_path),
                        "-frames:v", "1", "-vf", "scale=480:-2", str(out_jpg)],
                       capture_output=True, check=True, timeout=120)
        return out_jpg.exists() and out_jpg.stat().st_size > 0
    except Exception as e:
        print(f"[vlink] 포스터 추출 실패({Path(video_path).name}: {e})")
        return False


def _ytdlp_download(url: str, out_dir: Path, key: str) -> str:
    """yt-dlp로 추출 → {key}.{ext} 로 정리해 경로 반환. (임포트는 사용 시점 — 무거움)

    유튜브의 데이터센터 IP 봇 차단("Sign in to confirm you're not a bot")에 3중 대응:
      ① PO 토큰 프로바이더(bgutil) — 워크플로가 도커로 로컬 기동, 플러그인이 자동 감지해
         유튜브 봇 검증 토큰을 만들어 통과시킨다(savefrom류 사이트가 쓰는 것과 같은 원리).
      ② 플레이어 클라이언트 폴백 — tv/android/ios 클라이언트는 웹보다 봇 검증이 느슨하다.
      ③ (선택) SHORTS_YTDLP_COOKIES 시크릿(cookies.txt 내용) — 로그인 쿠키. 계정 제재 위험이
         있어 최후 수단(등록 안 하면 그냥 건너뜀)."""
    import imageio_ffmpeg
    import yt_dlp
    tmp = out_dir / "dl"
    tmp.mkdir(parents=True, exist_ok=True)
    base = {
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": str(tmp / "dl.%(ext)s"),
        "quiet": True, "no_warnings": True, "noplaylist": True,
        "max_filesize": MAX_BYTES,
        "ffmpeg_location": imageio_ffmpeg.get_ffmpeg_exe(),
    }
    cookies = (os.environ.get("SHORTS_YTDLP_COOKIES") or "").strip()
    if cookies:
        cf = tmp / "cookies.txt"
        cf.write_text(cookies + "\n", encoding="utf-8")
        base["cookiefile"] = str(cf)
        print("[vlink] 쿠키 시크릿 사용(SHORTS_YTDLP_COOKIES)")
    attempts = [
        {},   # 기본(웹 클라이언트) — bgutil PO 토큰 프로바이더가 떠 있으면 대부분 여기서 통과
        {"extractor_args": {"youtube": {"player_client": ["tv", "android"]}}},
        {"extractor_args": {"youtube": {"player_client": ["ios", "web_safari"]}}},
    ]
    last = None
    for i, extra in enumerate(attempts, 1):
        for old in tmp.glob("dl.*"):
            old.unlink(missing_ok=True)
        try:
            with yt_dlp.YoutubeDL({**base, **extra}) as ydl:
                ydl.download([url])
            got = sorted(tmp.glob("dl.*"), key=lambda p: p.stat().st_size, reverse=True)
            if got and got[0].stat().st_size > 0:
                ext = got[0].suffix.lower() if got[0].suffix.lower() in _CT else ".mp4"
                dest = out_dir / f"{key}{ext}"
                got[0].replace(dest)
                if i > 1:
                    print(f"[vlink] {i}차 방식(클라이언트 폴백)으로 추출 성공")
                return str(dest)
            last = RuntimeError("추출 결과 파일 없음(용량 초과 가능)")
        except Exception as e:
            last = e
            print(f"[vlink] 추출 {i}/{len(attempts)}차 실패({type(e).__name__}: {str(e)[:90]}) → 다음 방식")
    raise last if last else RuntimeError("추출 실패")


def _release_assets() -> list:
    try:
        r = requests.get(f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}",
                         headers=_headers(), timeout=30)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        return r.json().get("assets") or []
    except Exception as e:
        print(f"[vlink] 릴리스 목록 조회 실패({e}) — 캐시 없이 진행")
        return []


def _download_asset(asset: dict, out_dir: Path) -> str | None:
    try:
        fp = Path(out_dir) / str(asset["name"])
        with requests.get(asset["browser_download_url"], timeout=300, stream=True) as resp:
            resp.raise_for_status()
            with fp.open("wb") as f:
                for chunk in resp.iter_content(1 << 20):
                    f.write(chunk)
        return str(fp)
    except Exception as e:
        print(f"[vlink] 캐시 다운로드 실패({asset.get('name')}: {e})")
        return None


def _upload_asset(path: Path) -> bool:
    """추출본을 릴리스 product-assets 에 업로드(다음 실행 캐시). 토큰 없으면 조용히 건너뜀."""
    tok = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if not tok:
        print("[vlink] GH 토큰 없음 — 릴리스 캐시 업로드 생략(로컬 사용만)")
        return False
    try:
        h = _headers()
        r = requests.get(f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}", headers=h, timeout=30)
        if r.status_code == 404:
            r = requests.post(f"https://api.github.com/repos/{REPO}/releases", headers=h, timeout=30,
                              json={"tag_name": TAG, "name": "제품 영상 (관리자 업로드·링크 추출)",
                                    "body": "상품별 제품 영상 자산", "make_latest": "false"})
        r.raise_for_status()
        rid = r.json()["id"]
        ct = _CT.get(path.suffix.lower(), "application/octet-stream")
        up = requests.post(
            f"https://uploads.github.com/repos/{REPO}/releases/{rid}/assets?name={path.name}",
            headers={**h, "Content-Type": ct}, data=path.read_bytes(), timeout=600)
        if up.status_code == 422:   # 이미 존재(경쟁 실행) — 캐시 목적은 달성
            print(f"[vlink] 릴리스에 이미 존재: {path.name}")
            return True
        up.raise_for_status()
        print(f"[vlink] 릴리스 캐시 업로드 완료: {path.name}")
        return True
    except Exception as e:
        print(f"[vlink] 릴리스 업로드 실패({path.name}: {e}) — 이번 실행은 로컬본 사용")
        return False


def _maybe_notify_fail(url: str, msg: str, key: str, assets: list) -> None:
    """실패 텔레그램은 같은 링크당 1회만(사용자 지시: 반복 실패 알림 금지) — 릴리스에 실패 마커
    자산({key}.fail.txt)을 남겨 다음 실행부터는 조용히 로그만 남긴다."""
    marker = f"{key}.fail.txt"
    if any(str(a.get("name", "")) == marker for a in assets):
        print(f"[vlink] 실패 알림 생략(이미 알림 — {marker})")
        return
    try:
        from src import notify
        notify.send(
            "[쿠팡쇼츠] 상품 영상 링크 추출 실패 (이 링크는 다시 알리지 않습니다)\n"
            f"{url[:120]}\n{msg}\n\n"
            "유튜브가 서버(클라우드) IP를 봇으로 막아 자동 추출이 실패했습니다 — 흔한 문제이며,\n"
            "가장 확실한 해결은 폰/PC 브라우저에서 직접 받아 올리는 것입니다(가입 불필요):\n"
            "1) cobalt.tools 접속 → 링크 붙여넣기 → Download 로 mp4 저장\n"
            "2) 관리자 상품 목록에서 그 상품 '영상 올리기'(또는 이미지 탭 '내 파일 올리기')로 업로드\n"
            "→ 이러면 추출 없이 동일하게 영상 후보로 쓰입니다.")
    except Exception:
        pass
    try:   # 마커 업로드(다음 실행 알림 억제) — 실패해도 무해
        import tempfile
        mf = Path(tempfile.mkdtemp()) / marker
        mf.write_text(msg[:500] + "\n", encoding="utf-8")
        _upload_asset(mf)
    except Exception as e:
        print(f"[vlink] 실패 마커 업로드 생략({e})")
