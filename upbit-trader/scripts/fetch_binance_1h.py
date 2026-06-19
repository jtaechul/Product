#!/usr/bin/env python3
"""Binance 1시간봉 월별 zip을 받아 csv로 풀어 정리하는 다운로드/정리 스크립트.

하는 일(분석은 하지 않음 — 데이터 확보/정리 전용):
  1) 링크 목록 파일(기본 data/download_links_2019_2026.txt)의 URL을 순서대로 내려받음
  2) 404(상장 이전 월 등)는 조용히 건너뜀
  3) 받은 zip을 같은 폴더에 풀어 csv 추출 후 zip 삭제
  4) 코인별 파일 개수와 데이터 기간(최초~최종)을 요약 출력

네트워크가 열린 PC/서버에서 실행:
    python -m scripts.fetch_binance_1h
    python -m scripts.fetch_binance_1h --links data/download_links_2019_2026.txt \
        --out data/binance_1h_2019_2026

표준 라이브러리만 사용(추가 설치 불필요).
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LINKS = ROOT / "data" / "download_links_2019_2026.txt"
DEFAULT_OUT = ROOT / "data" / "binance_1h_2019_2026"


def read_links(path: Path) -> list[str]:
    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def download(url: str, dest: Path, timeout: int = 60) -> str:
    """반환: 'ok' | 'skip'(이미 있음) | '404' | 'err:<사유>'."""
    csv_name = dest.name.replace(".zip", ".csv")
    if (dest.parent / csv_name).exists():
        return "skip"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "binance-fetch"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            dest.write_bytes(r.read())
        return "ok"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return "404"
        return f"err:HTTP{e.code}"
    except Exception as e:  # noqa: BLE001
        return f"err:{type(e).__name__}"


def extract(zip_path: Path) -> bool:
    try:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(zip_path.parent)
        zip_path.unlink()  # zip 제거(csv만 남김)
        return True
    except Exception:
        return False


def coin_of(filename: str) -> str:
    # 예: BTCUSDT-1h-2020-01.csv → BTCUSDT
    return filename.split("-", 1)[0]


def _ms_to_date(ms: int) -> str:
    return dt.datetime.utcfromtimestamp(ms / 1000).strftime("%Y-%m-%d")


def first_last_date(csv_path: Path) -> tuple[str, str] | None:
    """csv의 첫/마지막 행 open_time(ms)으로 날짜 범위. 헤더 행이 있으면 건너뜀."""
    try:
        with csv_path.open() as f:
            lines = [ln for ln in f if ln.strip()]
        if not lines:
            return None
        def parse(ln):
            tok = ln.split(",")[0]
            return int(float(tok))
        # 헤더(open_time 같은 문자열) 방어
        start_idx = 0
        try:
            parse(lines[0])
        except ValueError:
            start_idx = 1
        if start_idx >= len(lines):
            return None
        return _ms_to_date(parse(lines[start_idx])), _ms_to_date(parse(lines[-1]))
    except Exception:
        return None


def summarize(out_dir: Path) -> None:
    csvs = sorted(out_dir.glob("*.csv"))
    by_coin: dict[str, list[Path]] = {}
    for c in csvs:
        by_coin.setdefault(coin_of(c.name), []).append(c)
    print("\n" + "=" * 56)
    print(f"📊 정리 결과 ({out_dir})")
    print("=" * 56)
    if not by_coin:
        print("받은 csv 없음.")
        return
    print(f"{'코인':<12}{'파일수':>6}   기간(최초 ~ 최종)")
    print("-" * 56)
    for coin in sorted(by_coin):
        files = sorted(by_coin[coin])
        lo = first_last_date(files[0])
        hi = first_last_date(files[-1])
        start = lo[0] if lo else "?"
        end = hi[1] if hi else "?"
        print(f"{coin:<12}{len(files):>6}   {start} ~ {end}")
    print("-" * 56)
    print(f"합계: {len(csvs)}개 csv, {len(by_coin)}개 코인")


def main() -> None:
    p = argparse.ArgumentParser(description="Binance 1h 다운로드/정리")
    p.add_argument("--links", default=str(DEFAULT_LINKS))
    p.add_argument("--out", default=str(DEFAULT_OUT))
    args = p.parse_args()

    links_path = Path(args.links)
    out_dir = Path(args.out)
    if not links_path.exists():
        print(f"링크 파일 없음: {links_path}")
        sys.exit(1)
    out_dir.mkdir(parents=True, exist_ok=True)

    urls = read_links(links_path)
    print(f"총 {len(urls)}개 URL 처리 시작 → {out_dir}")
    stat = {"ok": 0, "skip": 0, "404": 0, "err": 0}
    for i, url in enumerate(urls, 1):
        name = url.rsplit("/", 1)[-1]
        zip_path = out_dir / name
        res = download(url, zip_path)
        if res == "ok":
            if extract(zip_path):
                stat["ok"] += 1
            else:
                stat["err"] += 1
                print(f"  [{i}/{len(urls)}] 압축해제 실패: {name}")
        elif res == "skip":
            stat["skip"] += 1
        elif res == "404":
            stat["404"] += 1
        else:
            stat["err"] += 1
            print(f"  [{i}/{len(urls)}] {res}: {name}")
        if i % 50 == 0:
            print(f"  …진행 {i}/{len(urls)} (받음 {stat['ok']}, 건너뜀 {stat['skip']}, "
                  f"404 {stat['404']}, 오류 {stat['err']})")

    print(f"\n완료: 받음 {stat['ok']} / 이미있음 {stat['skip']} / "
          f"404건너뜀 {stat['404']} / 오류 {stat['err']}")
    summarize(out_dir)


if __name__ == "__main__":
    main()
