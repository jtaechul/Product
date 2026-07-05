# 기술 스펙 — deep_sea / narrated_wildlife

> 규칙: `CLAUDE.md` · 요구사항: `PRD.md`. 방향 v3: 나레이션 야생 다큐(ROV/HUD 폐기).

## 1. 아키텍처 (2계층 + 무료 인프라)
- **공용 코어**: 파이프라인 오케스트레이션 · 라이선스 게이트 · 시각화 계약(veo/panzoom) · 합성 · 오디오 ·
  **tts · subtitle** · content_store(콘텐츠 레코드) · 출력/QC.
- **카테고리(deep_sea)**: 종 선정(suggest)·정보·소싱(종특정 실사)·상황/컷 뱅크·**script(대본)**·캡션·정확성 규칙.
- **무료 인프라($0/월)**: 제작 = GitHub Actions / 미디어 = GitHub Release / 관리·조작 = Cloudflare Workers /
  전송 = 텔레그램. (Cloudflare Containers·R2 유료 경로는 미도입.)

## 2. 파이프라인 (`pipeline.run_narrated`)
```
종명 입력 → 정보 조회 → 종특정 실사 소싱 → 라이선스 게이트(하드룰)
→ 대본 생성(script) → 동적 야생다큐 컷(Veo 수심인지 / panzoom 폴백) → concat
→ TTS 나레이션(문장별 톤) → 단어별 카라오케 자막(근사정렬·번인)
→ 앰비언트 SFX(배경음악 없음) [나레이션>영상이면 마지막 프레임 복제 연장]
→ 9:16 mp4 + 한국어 캡션(출처표기) + 콘텐츠 레코드 + 도감번호
```
- 모드: `--mode narrated`(기본) / `hud`(구 ROV, `pipeline.run`, 보존).

## 3. 모듈 계약
### script (`categories/deep_sea/script.py`)
- `build_script(info, behavior="") -> [{text, tone}]` (5~6문장). LLM=Gemini→Claude→결정적 폴백.
- 톤: `gravelly|slow|whispered|reverent|tense|hushed|awe`. 구조: 훅→행동→팩트2~3→감정마무리. 날조 금지.

### tts (`core/tts.py`)
- `synthesize(sentences, work_dir) -> (wav_path|None, timings[{text,tone,start,end}])`.
- Gemini `gemini-2.5-flash-preview-tts`, voice `Charon`, PCM L16 24kHz mono. 문장 사이 0.35s 무음.
- 톤태그 → 자연어 스타일 지시(깊은 ASMR). 키 없음/실패 → (None, []) 안전(앰비언트만).
- **실측(스파이크)**: 음질 양호·저비용. **단어 타임스탬프 미제공** → subtitle이 근사.

### subtitle (`core/subtitle.py`)
- `word_timings(sent_timings) -> [{word,start,end}]`: 문장 구간을 어절 글자수 비례로 분배(강제정렬 근사).
- `build_ass(words, path, w, h)`: 단어별 팝업(굵게·중앙 하단·페이드 팝) ASS. 폰트=Black Han Sans(vendor).
- `burn(video, ass, work_dir)`: FFmpeg `subtitles` 번인(vendor 폰트 우선, 시스템 폴백).

### Veo 프롬프트 (`categories/deep_sea/prompts.py::build_cuts_wildlife`)
- 동적 야생다큐 + **수심 인지**: `_is_deep(≥200m)`이면 어둠 장면(단일 탐사광·부정제약: 햇빛/수면/기포/산호초 금지),
  아니면 자연광. 형태 잠금(anatomy_lock·forbidden_features) + 비발광 명시. 카메라: brief wide → dynamic push-in.

### audio (`core/audio.py::add_narration`)
- 나레이션(주, vol 1.35, 300ms delay) + 낮은 앰비언트(브라운·lowpass·vol 0.45) amix. 배경음악 없음.

## 4. 데이터 계약 (요지)
- `SpeciesInfo`, `CaptionData(+alert)`, `RawAsset/ApprovedAsset`, `Situation/CutSpec`, `OutputResult`.
- 콘텐츠 레코드 `content/<id>.json`: id·species·reels(hook/caption/hashtags/video_file/visualizer)·source·
  media(Release URL)·post(중단 시 null). CI가 media·post URL 패치.

## 5. 하드 룰 (위반 금지)
1. 저작권 게이트: public-domain/cc0/cc-by/kogl-type1만. nc·sa·unknown 차단. 차단분 미포함.
2. 출처 크레딧 자동 삽입(캡션 말미 이미지·정보 출처). CC-BY 저작자·라이선스 표기 의무.
3. 사실 정확성: 생물 형태·행동 실제만. 없는 행동·수치·위험·포식·발광 날조 금지(대본·프롬프트 공통 게이트).
4. 시크릿: `.env`/GitHub secrets에서만. 하드코딩·커밋 금지.
5. 무음 발행 금지(나레이션 또는 앰비언트 필수).
6. 종특정 실사 필수(단일 하드코딩 URL로 전 종 동일사진 금지).

## 6. Veo·TTS 스파이크 실측 (2026-07-05, veo-3.1-lite)
- Veo: 컷당 43~54초 생성, 720×1280 9:16 8초 24fps. 화질·카메라(와이드→푸시인) 우수.
- **정확성**: (A) 원안 그대로면 심해종을 얕은 산호초·햇빛·기포로 오도 → **수심 인지형 프롬프트로 어둠·형태 개선**.
  잔여: 기포 약간·특이형태종 해부 불완전(Veo Lite 한계). → 크게 틀어지면 재생성/종 교체.
- TTS: Gemini TTS 20초 음성 10.5초 생성, 저비용. 단어 타임스탬프 미제공(자막 근사 사유).

## 7. 완성 판정 (수용 기준 11-1)
- [ ] 9:16 720×1280, 유음(나레이션+앰비언트), QC 통과(해상도·오디오·캡션·크레딧·라이선스).
- [ ] 대본 5~6문장 [훅→행동→팩트→마무리], 사실만.
- [ ] 단어별 자막이 나레이션에 동기(근사)·굵게·중앙.
- [ ] 심해종 영상이 어둠 서식지(수심 인지)·형태 보존.
- [ ] 캡션 출처 표기, 콘텐츠 레코드·도감번호 기록.
- 테스트: `pytest`(narrated E2E panzoom·무키 포함) green.
