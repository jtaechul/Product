# short-movie-generator

카테고리별로 소싱·제작을 달리하는 **확장형 9:16 쇼츠/릴스 자동 생성 플랫폼**.
현재 첫 번째 카테고리 = **심해 해양생물(deep_sea)**. 상세 규칙은 [CLAUDE.md](CLAUDE.md).

## 구조 (공용 코어 + 카테고리 모듈)
```
src/
├── core/                     # 카테고리 불변 (공용)
│   ├── contracts.py          # 데이터 계약 (spec 9장)
│   ├── license_gate.py       # 라이선스 게이트 (하드 룰)
│   ├── visualization/        # 인터페이스 계약 + panzoom / veo 구현체 (교체 가능)
│   ├── assembler.py          # FFmpeg concat
│   ├── overlay.py            # 훅·정보·워터마크·크레딧 (Pillow)
│   ├── audio.py              # 심해 앰비언트 (무음 금지)
│   ├── output.py             # mp4 + 사이드카 메타 + QC (spec 11-1)
│   └── pipeline.py           # 오케스트레이션
├── categories/deep_sea/      # 카테고리 #1 (정보·소싱·상황뱅크·캡션·정확성)
├── registry.py               # 카테고리 등록/로드
└── run_pipeline.py           # CLI 진입점
```

## 설치
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# (오버레이 한국어 폰트) sudo apt-get install -y fonts-noto-cjk ffmpeg
```

## 실행
```bash
# panzoom(무료·API키 불필요) — 파이프라인 전체 완주
.venv/bin/python -m src.run_pipeline "dumbo octopus"

# Veo(사실형 AI 영상) — .env 에 GEMINI_API_KEY 필요 (과금)
cp .env.example .env   # GEMINI_API_KEY 채우기
.venv/bin/python -m src.run_pipeline "dumbo octopus" --visualizer veo_img2video
```
결과: `output/<종명>_<시각>.mp4` + 같은 이름 `.json`(캡션·크레딧·QC 메타).

## 시각화 구현체 (spec 3장, 교체 가능)
| 구현체 | 비용 | 용도 |
|---|---|---|
| `panzoom` | 무료 (FFmpeg 켄번즈) | 기본·검증·폴백. 정지 이미지 → 9:16 클립 |
| `veo_img2video` | 과금 (Veo 3.1 Lite) | 사실형 AI 영상. `GEMINI_API_KEY` 필요 |

두 구현체는 동일 인터페이스 계약("승인 이미지+컷 → 9:16 클립")을 지키므로 상·하류 변경 없이 교체된다.

## 테스트
```bash
.venv/bin/python -m pytest tests/ -q          # 전체 (E2E 포함)
.venv/bin/python -m pytest tests/ -q -m "not e2e"   # 빠른 단위 테스트만
```

## 하드 룰 (요약)
- 라이선스 게이트: `public-domain/cc0/cc-by/kogl-type1`만 통과. 차단 에셋은 시각화 이후 절대 미포함.
- 생물 왜곡 금지 + `accuracy_flags` 위배 컷 차단(발광 등).
- 심해 앰비언트 오디오 필수(무음 발행 금지) — 후처리 레이어링.
- 출처 크레딧 자동 삽입 / 시크릿은 `.env`에서만.

## 현재 상태 / 다음 단계
- ✅ MVP 수직 슬라이스(panzoom) E2E 완주 + QC 전 항목 통과 + 실사(NOAA 퍼블릭도메인) 경로 검증
- ⏳ **Veo 실호출**: `GEMINI_API_KEY` 주입 후 `--visualizer veo_img2video` 로 검증 필요(과금)
- ⏳ Cloudflare Containers 배포(사용자 결정: cut1 검증 후) / 상황뱅크 종 확대 / 로열티프리 실제 앰비언트 음원
