"""webapp.server — 쇼츠/릴스 자동 제작 조작용 웹 대시보드 (의존성 0, stdlib http.server).

종 입력 → 생성(파이프라인) → 실시간 로그 → 미리보기 → 다운로드.
무거운 처리(FFmpeg·Playwright·Veo)는 파이프라인 그대로 백그라운드 스레드에서 실행.

실행:  python -m webapp.server         (기본 http://127.0.0.1:8000)
        PORT=9000 python -m webapp.server
"""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import sys
import threading
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.categories.deep_sea import data as deep_sea_data  # noqa: E402
from src.core import pipeline  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
RUNS = ROOT / "webapp" / "runs"
RUNS.mkdir(parents=True, exist_ok=True)

_jobs: dict[str, dict] = {}
_lock = threading.Lock()


# ─────────────────────────── 잡(생성 작업) ───────────────────────────

class _JobLogHandler(logging.Handler):
    """해당 잡 스레드에서 나온 로그만 수집(동시 실행 시 로그 분리)."""

    def __init__(self, job_id: str, thread_ident: int):
        super().__init__()
        self.job_id, self.thread_ident = job_id, thread_ident

    def emit(self, record):
        if record.thread != self.thread_ident:
            return
        with _lock:
            job = _jobs.get(self.job_id)
            if job is not None:
                job["log"].append(self.format(record))


def _species_list() -> list[dict]:
    out = []
    for key, sp in deep_sea_data.SPECIES.items():
        out.append({"key": key, "ko": sp["common_name_ko"], "en": sp["common_name_en"]})
    return out


def _run_job(job_id: str, category: str, query: str, visualizer: str):
    handler = _JobLogHandler(job_id, threading.get_ident())
    handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
    root = logging.getLogger("src")
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    base = RUNS / job_id
    try:
        with _lock:
            _jobs[job_id]["status"] = "running"
        result = pipeline.run(category, query, visualizer, base_dir=str(base))
        meta = {}
        try:
            meta = json.loads(Path(result.sidecar_meta).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
        cap = meta.get("caption", {})
        with _lock:
            _jobs[job_id].update(
                status="done",
                result={
                    "video_url": f"/media/{job_id}",
                    "hook": cap.get("hook_text", ""),
                    "caption": cap.get("caption_body", ""),
                    "hashtags": cap.get("hashtags", []),
                    "reveal": cap.get("reveal_name", ""),
                    "qc_passed": bool(result.qc_passed),
                    "video_path": result.video_path,
                },
            )
    except Exception as e:  # noqa: BLE001
        with _lock:
            _jobs[job_id].update(status="error",
                                 error=f"{type(e).__name__}: {e}",
                                 log=_jobs[job_id]["log"] + [traceback.format_exc()])
    finally:
        root.removeHandler(handler)


def _start_job(category: str, query: str, visualizer: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = {"status": "queued", "log": [], "result": None, "error": None,
                         "params": {"category": category, "query": query, "visualizer": visualizer}}
    threading.Thread(target=_run_job, args=(job_id, category, query, visualizer), daemon=True).start()
    return job_id


def _job_video(job_id: str) -> Path | None:
    with _lock:
        job = _jobs.get(job_id)
    if not job or not job.get("result"):
        return None
    p = Path(job["result"]["video_path"])
    return p if p.exists() else None


# ─────────────────────────── HTTP 핸들러 ───────────────────────────

class Handler(BaseHTTPRequestHandler):
    server_version = "DeepDiveDash/0.1"

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path, ctype=None):
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype or mimetypes.guess_type(str(path))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_media(self, job_id: str):
        vid = _job_video(job_id)
        if vid is None:
            return self._json({"error": "not ready"}, 404)
        size = vid.stat().st_size
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):
            s, _, e = rng[6:].partition("-")
            start = int(s) if s else 0
            end = int(e) if e else size - 1
            end = min(end, size - 1)
            length = end - start + 1
            with open(vid, "rb") as f:
                f.seek(start)
                chunk = f.read(length)
            self.send_response(206)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(length))
            self.end_headers()
            self.wfile.write(chunk)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(size))
            self.end_headers()
            self.wfile.write(vid.read_bytes())

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/" or path == "/index.html":
            return self._file(STATIC / "index.html", "text/html; charset=utf-8")
        if path == "/api/species":
            return self._json({"category": "deep_sea", "species": _species_list()})
        if path.startswith("/api/jobs/"):
            job_id = path.rsplit("/", 1)[-1]
            with _lock:
                job = _jobs.get(job_id)
            if job is None:
                return self._json({"error": "unknown job"}, 404)
            return self._json({"status": job["status"], "log": job["log"][-400:],
                               "result": job["result"], "error": job["error"]})
        if path.startswith("/media/"):
            return self._serve_media(path.rsplit("/", 1)[-1])
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/jobs":
            n = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except Exception:  # noqa: BLE001
                body = {}
            query = (body.get("query") or "").strip()
            if not query:
                return self._json({"error": "종명을 입력하세요"}, 400)
            category = body.get("category") or "deep_sea"
            visualizer = body.get("visualizer") or "panzoom"
            job_id = _start_job(category, query, visualizer)
            return self._json({"job_id": job_id})
        return self._json({"error": "not found"}, 404)

    def log_message(self, *a):  # 조용히
        pass


def main():
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "127.0.0.1")
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"▶ Deep Dive 대시보드: http://{host}:{port}  (Ctrl+C 종료)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
