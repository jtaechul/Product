"""소싱 데이터 모델 (SSOT §11) — SourceVideo · Project · Clip + JSON 영속화.

SSOT §11 초안을 그대로 반영하되, 실무에 필요한 보조 필드(title·duration·uploader)를 더한다.
저장 위치: data/sources/videos/{id}.json, data/sources/projects/{id}.json.
- 산출물(mp4 등)은 커밋 금지 규칙이 있으므로 여기엔 '메타데이터'만 저장한다(경로만 기록).
- 타임스탬프·id는 결정론적 테스트를 위해 주입 가능(없으면 자동 생성).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]   # coupang-shorts-factory/
SOURCES_DIR = PROJECT_ROOT / "data" / "sources"

VALID_SOURCE_MODES = ("auto", "manual")
# SourceVideo.status 전이: discovered(메타만) → downloaded(원본 확보) → failed(수집/다운 실패)
VALID_VIDEO_STATUS = ("discovered", "downloaded", "failed")
# Project.status 전이: draft(편집중) → rendering → done → published (발행은 수동, §9)
VALID_PROJECT_STATUS = ("draft", "rendering", "done", "published", "failed")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ─────────────────────────────────────────────────────────────────────────────
# Clip (§11) — 소싱 영상의 한 구간 + 줌 지정. 운영자가 편집 대시보드(§7)에서 만든다.
#   zoom_region은 원본 프레임 좌표계(정규화 0~1)로 저장해 해상도에 독립적이게 한다.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Clip:
    source_video_id: str
    start_time: float                 # 초
    end_time: float                   # 초
    zoom_region: dict | None = None   # {x,y,w,h} 정규화(0~1). None=전체
    zoom_scale: float = 1.0           # 1.0=원본, >1.0=확대
    clip_id: str = field(default_factory=lambda: _new_id("clip"))

    def duration(self) -> float:
        return max(0.0, float(self.end_time) - float(self.start_time))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Clip":
        return cls(
            source_video_id=d["source_video_id"],
            start_time=float(d.get("start_time", 0.0)),
            end_time=float(d.get("end_time", 0.0)),
            zoom_region=d.get("zoom_region"),
            zoom_scale=float(d.get("zoom_scale", 1.0)),
            clip_id=d.get("clip_id") or _new_id("clip"),
        )


# ─────────────────────────────────────────────────────────────────────────────
# SourceVideo (§11) — 소싱한 원본 영상 1건의 메타데이터(원본 파일은 별도, 경로만 기록).
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class SourceVideo:
    platform: str                     # youtube · tiktok · instagram …
    source_url: str
    view_count: int | None = None
    downloaded_path: str | None = None   # 원본 저장 경로(다운로드 후). 메타엔 경로만.
    download_url: str | None = None       # 무워터마크 재생 URL(예: tikwm). 만료 가능 → download가 재해석 폴백.
    cover: str | None = None              # 썸네일(커버) 이미지 URL — 관리자 추천 카드용.
    tags: list = field(default_factory=list)
    source_mode: str = "manual"       # auto | manual (§6)
    status: str = "discovered"        # discovered | downloaded | failed
    title: str | None = None
    duration: float | None = None     # 초
    uploader: str | None = None
    sourced_at: str = field(default_factory=_now_iso)
    id: str = field(default_factory=lambda: _new_id("sv"))

    def __post_init__(self):
        if self.source_mode not in VALID_SOURCE_MODES:
            raise ValueError(f"source_mode 오류: {self.source_mode} (가능: {VALID_SOURCE_MODES})")
        if self.status not in VALID_VIDEO_STATUS:
            raise ValueError(f"status 오류: {self.status} (가능: {VALID_VIDEO_STATUS})")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SourceVideo":
        return cls(
            platform=d["platform"],
            source_url=d["source_url"],
            view_count=d.get("view_count"),
            downloaded_path=d.get("downloaded_path"),
            download_url=d.get("download_url"),
            cover=d.get("cover"),
            tags=list(d.get("tags") or []),
            source_mode=d.get("source_mode", "manual"),
            status=d.get("status", "discovered"),
            title=d.get("title"),
            duration=d.get("duration"),
            uploader=d.get("uploader"),
            sourced_at=d.get("sourced_at") or _now_iso(),
            id=d.get("id") or _new_id("sv"),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Project (§11) — 완성 쇼츠 1편의 편집 상태(소싱영상·클립·순서·자막·더빙·산출물).
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Project:
    title: str
    source_video_ids: list = field(default_factory=list)
    clips: list = field(default_factory=list)          # list[Clip]
    clip_order: list = field(default_factory=list)      # list[clip_id] — 재배치 순서
    hook_clip_id: str | None = None
    subtitle_path: str | None = None
    dubbing_path: str | None = None
    output_path: str | None = None
    status: str = "draft"
    created_at: str = field(default_factory=_now_iso)
    id: str = field(default_factory=lambda: _new_id("prj"))

    def __post_init__(self):
        if self.status not in VALID_PROJECT_STATUS:
            raise ValueError(f"status 오류: {self.status} (가능: {VALID_PROJECT_STATUS})")

    def ordered_clips(self) -> list:
        """clip_order대로 정렬한 Clip 리스트(순서 미지정 클립은 뒤에 원래 순서로)."""
        by_id = {c.clip_id: c for c in self.clips}
        out = [by_id[cid] for cid in self.clip_order if cid in by_id]
        out += [c for c in self.clips if c.clip_id not in set(self.clip_order)]
        return out

    def to_dict(self) -> dict:
        d = asdict(self)
        d["clips"] = [c.to_dict() if isinstance(c, Clip) else c for c in self.clips]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        return cls(
            title=d.get("title", ""),
            source_video_ids=list(d.get("source_video_ids") or []),
            clips=[Clip.from_dict(c) for c in (d.get("clips") or [])],
            clip_order=list(d.get("clip_order") or []),
            hook_clip_id=d.get("hook_clip_id"),
            subtitle_path=d.get("subtitle_path"),
            dubbing_path=d.get("dubbing_path"),
            output_path=d.get("output_path"),
            status=d.get("status", "draft"),
            created_at=d.get("created_at") or _now_iso(),
            id=d.get("id") or _new_id("prj"),
        )


# ─────────────────────────────────────────────────────────────────────────────
# JSON 영속화 — base_dir 주입 가능(테스트는 임시 폴더로).
# ─────────────────────────────────────────────────────────────────────────────
def _dir(base_dir: Path | None, sub: str) -> Path:
    d = (base_dir or SOURCES_DIR) / sub
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_source_video(sv: SourceVideo, base_dir: Path | None = None) -> Path:
    p = _dir(base_dir, "videos") / f"{sv.id}.json"
    p.write_text(json.dumps(sv.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def load_source_video(sv_id: str, base_dir: Path | None = None) -> SourceVideo | None:
    p = _dir(base_dir, "videos") / f"{sv_id}.json"
    if not p.exists():
        return None
    return SourceVideo.from_dict(json.loads(p.read_text(encoding="utf-8")))


def load_all_source_videos(base_dir: Path | None = None) -> list:
    d = _dir(base_dir, "videos")
    return [SourceVideo.from_dict(json.loads(f.read_text(encoding="utf-8")))
            for f in sorted(d.glob("*.json"))]


def save_project(prj: Project, base_dir: Path | None = None) -> Path:
    p = _dir(base_dir, "projects") / f"{prj.id}.json"
    p.write_text(json.dumps(prj.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def load_project(prj_id: str, base_dir: Path | None = None) -> Project | None:
    p = _dir(base_dir, "projects") / f"{prj_id}.json"
    if not p.exists():
        return None
    return Project.from_dict(json.loads(p.read_text(encoding="utf-8")))
