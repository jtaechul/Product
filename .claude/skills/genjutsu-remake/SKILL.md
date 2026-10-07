---
name: genjutsu-remake
description: 사장님이 올린 밈 영상에 시바견을 Genjutsu식으로 합성(원본 영상·동작·구도·소리 그대로, 대상만 교체)하고 Real-ESRGAN으로 업스케일해 9:16 상품 광고 릴스를 만드는 절차. 밈 영상 파일과 함께 "젠주츠처럼", "합성해서", "시바견으로 바꿔", "리메이크"라고 하면 이 절차를 따른다.
---

# Genjutsu식 리메이크 (합성 → 업스케일)

**본질을 왜곡하지 않는다.** 원본 영상은 그대로 두고(모든 동작·구도·박자·소리), 지정한 대상(개·사람 머리 등)만 시바견으로 바꾼다.
새로 그리는 방식(`method: motion`, `shots`)은 사장님이 따로 시킬 때만.

**확정 설정(2026-10-07 사과 도둑 편 테스트로 확인, 사장님 선택 "720p로, 아예 안 흐리게")**
`method: "composite"` + `res: "720p"`(합성을 처음부터 720p로) + `pre_enhance: false`(원본 AI 복원은 제작 서버 CPU에서 40분 걸려 **끔** — 사장님 지시 2026-10-07; 720p 합성만으로 선명) + `upscale: 0`(720p 그대로 조립) + `ad: "vo"` + `ad_copy: true`(끝 광고 화면에 캡션 문구).
결과: 원본이 흐린 보안카메라 영상이어도 결과는 또렷한 720x1280, 사람은 사람 그대로·개만 시바견, 세로는 AI가 위아래를 이어 그림.
비용(장부 기준) 본편 8초 약 2.4 + 끝 광고 1.35 + 분석·스토리보드 0.2 = 약 4달러(실제 약 1.4달러). 시간: 원본 복원이 제작 서버 CPU에서 약 40분(8초 기준) + 합성·광고 약 10분.
1080p까지 올리려면 `out_h: 1920`(무료, 시간 +40분) — 인스타는 1080p로 다시 압축하므로 보통 720p면 충분.

## 비용 원칙
- 돈 드는 단계(스토리보드·영상·끝 광고)는 **사장님 확인 뒤에만**. 예상 비용을 먼저 말한다.
- 분석·프레임 검증·업스케일·조립은 무료(로컬 ffmpeg·CPU Real-ESRGAN).
- 한 편 비용 안내(장부 기준): 분석 0.01 + 스토리보드 0.15 + 본편 Omni edit 360p 0.1/초 + 끝 그림 0.15 + 끝 4초 0.4 + 내레이션 0.02.

## 절차
0. **상품**: 사장님이 링크를 주면 그대로, 없으면 `POST /api/coupang/search {keyword, limit}`로 찾아 보여 주고 고른다(사진은 ads-partners 주소 → 302로 쿠팡 CDN, 제작 쪽 `_http`가 따라감). 판매 페이지 등록은 `POST /api/add-book-to-catalog {bookInfo:{title,author,category,coreMessage,cover}, cover, coupangLink}`.
1. **원본 올리기**: `POST /api/remake/start {size}` → `id`; 5MB 조각으로 `POST /api/remake/upload?id&n`(제작 워크플로는 서명 주소로만 받음, 저장소에 원본을 남기지 않는다).
2. **무료 분석**(돈 쓰기 전):
   - `ffmpeg`로 0.25~0.5초 간격 프레임 시트를 뽑아 **직접 본다**. 검은 화면·창작자 로고 아웃트로는 `remake.window: [시작, 끝]`으로 뺀다.
   - 소리 크기 흐름(astats)으로 음악인지 효과음인지 가늠. 음악이면 `keep_audio: false` + 우리 효과음(`pet-episodes/sfx`).
   - 개그 포인트를 `remake.gags`(t·kind·en·text)로 적는다. AI 0.5초 시간표(`_timeline`)는 틀릴 수 있다 — 프레임과 대조해 틀리면 `remake.timeline`(목록)에 확인한 시간표를 직접 쓴다(2026-10 사과 도둑 편: AI가 "개가 덤벼든다"로 잘못 읽음).
3. **episode.json** (`pet-episodes/episodes/<id>/episode.json`, kind `remake`):
   - `remake.method: "composite"`, `res: "720p"`, `pre_enhance: false`, `upscale: 0`(위 확정 설정), `window`, `timeline`, `gags`, `keep_audio`.
   - 바꿀 대상: `swap`(무엇을 시바견으로, 무엇은 그대로). 사람을 그대로 둘 땐 `keep_people: true` + `cast: "exactly one human man and one dog"`.
   - 끝 광고(4초, 같은 장소·같은 개): `ending`(장면), `vo`("…구매는 프로필 링크에서."), `big`/`sub`(캡션용), `ad: "vo"`, `hashtags` 5개(쇼핑 검색어).
   - `product.link`·`product.image`(쿠팡 상품) **필수** — 없으면 영상 단계가 돈 쓰기 전에 멈춘다.
4. **스토리보드**: `requests/NN_remake_board.json` `{"remake":{"mode":"board"}}` + `pet-episodes/stop.json`의 `allow`에 `"<id>:NN_remake_board.json"`. 원본 6장면 격자에 대상만 바꾼 합성 미리보기(`_remake_board`, keep_people이면 `REMAKE_BOARD_KEEP`). → 사장님 확인.
5. **영상**: `NN_remake_full.json` `{"remake":{"mode":"full"}}` + allow.
   - 사전 점검(`_remake_preflight`, 무료)을 통과해야 돈을 쓴다: 시간표 있음·개그 포인트 반영·막힐 낱말·옛 원본 분석·여러 번 만들기.
   - (끔, 선택) 원본 복원(`pre_enhance`): CPU 약 40분이라 기본 끔. 켜면 `upscale.py`로 원본을 깨끗하게 한 뒤 합성.
   - 본편: Omni `edit` 720p **한 번**(`_remake_seg`, 원본 소리 없이 영상만 넣고 소리는 조립 때 원본에서). 가로·정사각 원본은 9:16 틀에 넣고 위아래를 AI가 이어 그리게(`REMAKE_EXTEND`). 결과가 꽉 찬 9:16이 아니면 멈춤(`_assert_vertical`).
   - (선택) 업스케일: `upscale`/`out_h`로 1080x1920까지(무료, 느림).
   - 끝 광고 4초 + 내레이션(Enceladus 1.3배) + **화면 위 캡션 문구(big/sub, `ad_copy: true`, 위치는 개·상품을 안 가리는 쪽 `copy_place`)** + 작은 "구매는 프로필 링크에서"(사장님 확정 2026-10-07).
6. **검사·보내기**: `_assert_vertical`(파일·속화면·흐린 띠) 통과, 장면 캡처를 직접 보고 꽉 찬 세로·합성 품질·개그 포인트 확인 뒤 보낸다. 보고는 짧게(원인 한 줄·조치 한 줄).

## 디테일 올리는 손잡이(사장님이 편마다 고름)
- `res: "720p"` — 합성을 처음부터 720p로(실제 요금 약 3배: 360p 약 0.03달러/초 → 720p 약 0.10달러/초, 장부는 x3). 디테일이 가장 확실.
- `pre_enhance: true` — 합성 전에 원본을 Real-ESRGAN(노이즈 제거 0.5)으로 먼저 복원(무료, CPU 약 8분). 합성 AI가 깨끗한 입력을 보고 더 자세히 그린다.
- `upscale: 3` 또는 `out_h: 1920` — 결과를 1080x1920까지(무료). 모델은 x4로 그린 뒤 줄여서 더 또렷하다. 끝 장면도 같은 크기로 맞춘다.
- `upscale_dn`(0~1) — 업스케일 노이즈 제거 강도(AI 결과물은 0.3, 압축 심한 원본은 0.5).
- 바깥 업스케일러(Runway `upscale_video`, 4K)는 내 세션의 크레딧으로 수동 한 번 — 사장님이 시킬 때만.

## 거절·실패 대응(요금 없음)
- `HTTP 400` 차단은 장부에서 되돌린다. 실제 인물 거절(likeness)은 얼굴을 가려 한 번만 다시(`_mask_faces`). 그래도 안 되면 멈추고 사장님께 보고 — 자동으로 다른 방식에 돈을 쓰지 않는다.
- 막힐 만한 표현은 동작은 두고 부위·낱말만 바꾼다(사타구니 → 엉덩이, 맨살 → 털).

## 관련 코드
`pet-episodes/tools/episode.py`: `step_remake`(method 분기) · `_remake_seg`(합성) · `REMAKE_SWAP_KEEP`/`REMAKE_BOARD_KEEP` · `_remake_preflight` · `_assert_vertical` · `_gag_text`
`pet-episodes/tools/upscale.py`: `upscale_video(src, out, scale, dn)`
