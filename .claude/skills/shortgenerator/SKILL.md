---
name: shortgenerator
description: >-
  ABYSS(심해·해양생물) 9:16 쇼츠 자동 제작·편집·검증 런북. 쇼츠를 새로 만들거나,
  실패/불량(검은 NOAA 카드·번인 로고·종 중복·얇은 띠·자막 깨짐·오프닝 등)을 고치거나,
  소싱·리프레임·훅/엔드카드·캡션을 손볼 때 이 절차를 따른다. `short-movie-generator/` 전용.
  트리거: "쇼츠 만들어/제작", "쇼츠 오류/불량 고쳐", "소싱/리프레임/자막 수정", "/shortgenerator".
---

# /shortgenerator — ABYSS 쇼츠 제작·편집 런북

대상 프로젝트: `short-movie-generator/` (핸들 톤: "ABYSS | 深淵アーカイブ", 일본어 영상·한국어 대시보드).
$0 운영: GitHub Actions가 제작, Cloudflare Worker가 대시보드. 세부 규칙은 `short-movie-generator/CLAUDE.md`가 최상위.

## 0. 절대 규칙 (위반 금지 — 먼저 읽는다)
- **라이선스 게이트**: `public-domain`/`cc0`/`cc-by`/`cc-by-sa`/`kogl-type1`만 사용. **`cc-by-nc`(비상업)·`cc-by-nc-sa` 차단.** 크레딧·라이선스명 캡션 자동 삽입.
  ⚠️ `'cc by'`가 `'cc by-nc'`의 부분일치라 **NC를 먼저 걸러야** 한다(`_norm_license`에 NC 선차단 유지).
- **날조 금지**: 생물의 형태·행동·수치는 실제만. 종은 **출처가 식별한 수준(종/속/과)** 으로만 표기, 애매하면 스킵.
- **종 중복 금지**: 이미 만든 종은 다시 만들지 않는다(재탕 로직 폐지). 풀 소진 시 **자동 발굴로 풀 보충**(`discovery.replenish`, 아래 §8) 또는 다른 카테고리로 로테이션.
- **번인 카드·로고 금지**: 인트로/아웃트로 타이틀카드·NOAA 로고가 본편에 남으면 안 됨(자동 카드트림 + delogo + reframe 텍스트-띠 제거).
- **OS 이모지 금지**: HUD·엔드카드·썸네일 어디에도 시스템 이모지 금지 → 커스텀 벡터/SVG/텍스트만.
- **일본어 敬体(존댓말)**: 나레이션·자막·캡션 문어체 존댓말. 반말 금지.
- **자막 분절**: 카라오케 청크는 1.5배 기준 한 줄(≈7자)에 들어가게. 길면 고아 글자 발생.
- **해시태그 정확히 2개 = [내용 1개] + [고정 공통 1개]**. **#Shorts 금지**(형식 자동판정·스팸 인상).
  고정 공통은 카테고리 태그(deep_sea=`#深海生物`/`#심해생물`, shipwreck=`#沈没船`/`#난파선`,
  collection 기본=`#海の生き物`/`#해양생물`). 구현: `rich_caption._final_tags` + 카테고리 `fixed_hashtag`.
  업로드(`upload-short.yml`)는 캡션 해시태그만 쓰고 #Shorts·범용 태그를 덧붙이지 않는다.

## 1. 제작 트리거 (3가지)
1. **대시보드 버튼**: `book-carousel`/제작 페이지에서 카테고리+종 선택 → 워크플로 디스패치.
2. **요청 파일 푸시**(원격 자동화): `short-movie-generator/requests/<name>.json` 추가·푸시 → `generate-short.yml` 트리거.
   ```json
   {"category":"deep_sea","query":"auto","visualizer":"panzoom","scope":"all","_note":"사유"}
   ```
   - `category`: `deep_sea | marine_life | marine_algae | shipwreck`
   - `query`: `auto`(미제작 종 자동) 또는 종명
3. **로컬 실행**(검증용):
   ```bash
   cd short-movie-generator
   python -m src.run_pipeline "auto" --category deep_sea --mode reels
   # 출력: output/<종>_<날짜>.mp4 + .json (QC 로그)
   ```
   - 로컬엔 Chromium이 없을 수 있음 → `pip install playwright` (브라우저는 /opt/pw-browsers 사용).
   - 특정 종 강제: 로컬 `catalog.json`에서 해당 종을 잠깐 빼고 auto 실행.

- **매일 자동(스케줄)**: `generate-short.yml` cron `30 2 * * *`(11:30 KST). `category=__rotate__` → **미제작 종 남은 카테고리를 요일별 회전 선택**(한 카테고리 소진해도 매일 1편). ★스케줄은 **main의 워크플로 파일**로 도니, generate-short.yml 수정 시 **main에도 동기화**해야 반영됨.

## 2. 파이프라인 단계 (`src/core/pipeline.run_reels`)
```
종 선택(auto=미제작만, 중복금지)
 → footage.fetch_footage: 시드/커먼즈 → 라이선스·종횡비·움직임 게이트 + 자동 카드트림(프레임정확 재인코딩)
 → watermark_qc.plan: OCR 슬레이트 회피 + delogo 박스 → footage_clean
 → reframe.reframe_to_vertical(wide=False): 씬 인터리브 마이크로컷(1-1,2-1,…) + 줌인 얼굴 중앙 + 틸 그레이딩
 → narration_sync: edge-tts 일본어(ja-JP-KeitaNeural) + 카라오케 자막(≈7자 청크)
 → hook_intro_stage: 오프닝 훅(피사체 배경) + 엔드카드(도감번호·리빌) + 전환·임팩트 SFX + 앰비언트
 → 캡션(JP 본문+KR 참고, 해시태그 3개, 크레딧·라이선스)
 → output mp4 + 콘텐츠 레코드(content_store.write_record) + 미디어 발행
```
난파선만 `reframe_wide=True`(원경 cover-fill, 인터리브 미적용).

## 3. 출력 검증 (제작·수정 후 필수)
```bash
V=output/<파일>.mp4
D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$V")
# 전 구간 균등 프레임 추출 후 육안 점검
python3 -c "import subprocess;d=float('$D');[subprocess.run(['ffmpeg','-y','-loglevel','error','-ss',str(round(d*f,1)),'-i','$V','-frames:v','1',f'/tmp/v_{i}.png']) for i,f in enumerate([.03,.15,.3,.5,.7,.85,.97])]"
```
체크리스트: ① 9:16(720x1280) ② **NOAA 카드·로고 없음**(중간 검은 화면 문구 X) ③ **얇은 띠 없음**(피사체가 적정 비율) ④ 오프닝에 피사체 보임 ⑤ 씬 자주 전환 ⑥ 줌인 시 얼굴 중앙 ⑦ 자막 고아 글자 없음 ⑧ 엔드카드 정상 ⑨ 소리 있음(무음 금지). QC 로그(.json)도 확인.

## 4. 자주 나는 문제 → 원인·해결 (이미 반영됨)
| 증상 | 원인 | 조치(코드) |
|---|---|---|
| 검은 화면 NOAA 문구 반복 | 인트로 카드가 소스에 남음 + 콜드오픈 루프 | `footage._auto_trim_cards`(자동 카드트림) |
| 인트로 카드가 본편에 | `-ss + -c copy`가 키프레임 단위로 부정확 | 트림을 **프레임정확 재인코딩**으로 |
| 얇은 띠(피사체 납작) | 밝은 모래를 텍스트로 오검 → 과크롭 | `reframe` 텍스트-띠 `HIT=0.070`(모래↔텍스트 분리) |
| 같은 종 반복 | 재탕(회차 순환) 로직 | 재탕 폐지 — `footage_candidates`=미제작만 |
| "제작 눌러도 안 나옴" | 종 소진(정상 중단) | 새 종 시드 추가 or 스케줄은 카테고리 로테이션 |
| 붉지 않은 생물 추적 불량 | reframe가 붉은색 전용 | (진행중) 살리언시 일반화로 확장 |

## 5. 새 종 추가 절차 (정확성 우선)
1. **소싱**: 커먼즈는 **학명 검색 말고 공통명·분류군 주제어 + 카테고리 순회**로 찾는다(학명검색은 거의 0건). Ifremer 등 CC-BY 기관도 가용.
2. **검증**: 다운로드 → 종횡비[1.55~1.95]·움직임(≥3.0)·자동 카드트림 통과 → **프레임 육안 확인**(정말 그 종인지).
3. **시드 등록**: `footage._SEED`에 `{url,license,credit,source,(trim)}`.
4. **데이터**: `deep_sea/data.py`(또는 카테고리)에 종 정보 — **출처가 준 식별 수준까지만**(속·종 단정 금지).
5. **JP 카피**: `hook._SEED`(훅)·`_BODY_SEED`(본문, 敬体·≤7자 청크). 없으면 LLM 자동생성 폴백.
6. **검증 제작**: 로컬 auto로 1편 만들어 3장 체크리스트 통과 확인 후 커밋.

## 6. 자동 발굴(풀 자동보충 · 소스 확대) — `src/core/discovery.py`
운영자가 매번 시드를 손으로 넣지 않아도 되게, 미제작 종이 소진되면 시스템이 스스로 새 해양생물
영상을 찾아 풀을 채운다(사용자 확정).
- **소스**: Wikimedia Commons 전체(NOAA 한정 아님 — MBARI·Ifremer·다이버·수족관 등, **CC-BY-SA 포함**).
- **날조 금지**: 정체성 = 구조화데이터(P180)→Wikidata 또는 파일명 학명→Wikidata(P31=분류군·P225=학명 실존 종만).
  사실 = 그 종 Wikipedia(일→영) 발췌(출처 있음). 둘 중 하나라도 없으면 스킵. JP 카피는 이 사실로 LLM 생성.
- **필터**: 라이선스·종횡비·정지·카드 게이트 + 조류/육상 배제(`_EXCLUDE`) + 연구·사체·해부·양식 배제(`_BADCLIP`).
- **영속화**: `src/categories/*/discovered.json`(커밋). import 시 `footage._SEED`·`data.SPECIES`에 병합.
  워크플로 커밋 스텝에 이 파일 포함(§1 generate-short.yml).
- **연결**: `pipeline.run_reels`가 후보 0/전원탈락이면 `_replenish_and_refresh`로 발굴·병합 후 재시도.
- **주의(NC 차단)**: `'cc by'`가 `'cc by-nc'` 부분일치라 `_norm_license`가 NC를 먼저 걸러야 오통과가 없다.
- **수동 발굴**(운영자/개발): `python -c "from src.core import discovery; print(discovery.replenish('deep_sea', want=3))"`.

## 7. 핵심 파일 맵
- `src/core/pipeline.py` — reels 오케스트레이션(`run_reels`)
- `src/core/footage.py` — 소싱·게이트·카드트림·시드(`_SEED`, discovered 병합)
- `src/core/discovery.py` — 해양생물 영상 자동 발굴(풀 자동보충·소스 확대·CC-BY-SA)
- `src/core/reframe.py` — 9:16 씬 인터리브·얼굴중앙·텍스트띠 제거
- `src/core/watermark_qc.py` — OCR 슬레이트 회피·delogo
- `src/core/narration_sync.py` — TTS·카라오케 자막
- `src/core/hook_intro*.py` — 오프닝 훅·엔드카드
- `src/categories/<cat>/` — 종 데이터·훅/본문 카피·원장(catalog)
- `.github/workflows/generate-short.yml` — 제작 워크플로(스케줄=main 동기화 주의)
- `worker/index.mjs` — 대시보드(Cloudflare Worker)

## 8. 배포 규칙
- 개발은 작업 브랜치 `claude/gemini-shorts-reels-generator-dhjfdt`. 커밋은 **한 프로젝트 폴더만**(`.github/`·`.claude/`는 공용 예외).
- 푸시는 `git push -u origin <branch>`(실패 시 지수 백오프 재시도). PR은 사용자가 명시할 때만.
- 수정 후 **반드시 §3 검증**을 거친 뒤 보고. 실패/스킵은 그대로 보고(과장 금지).
