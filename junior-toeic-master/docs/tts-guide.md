# 듣기 음원 만들기 가이드 (1회성 작업)

> 이 작업은 **개발 단계에서 딱 한 번**만 하면 됩니다. 만들어진 음원은 영구 보관되고,
> 서비스 운영 중에는 TTS를 다시 호출하지 않습니다(운영비 0원 원칙).
> 실제 스크립트 실행은 준비물만 갖춰지면 Claude Code가 대신 해드릴 수 있습니다 —
> **아래 1단계(API 키)만 직접 주시면 됩니다.**

## 엔진 2종 — 기본은 Google Cloud TTS

| | **google (기본·권장)** | gemini (대안) |
|---|---|---|
| 서비스 | Cloud Text-to-Speech | Gemini API |
| 키 | `GOOGLE_TTS_KEY` | `GEMINI_API_KEY` |
| 준비 | GCP 결제 계정 + API 활성화 | 기존 Gemini 키 그대로 |
| **발음(미·영·호)** | **전용 성우로 고정 — 구분 확실** | 프롬프트로 지시 — 구분이 약할 수 있음 |
| 비용 | **뉴럴 월 100만 자 무료** (우리 물량 6천 자) | 사용량만큼 과금 |
| 대화(L3) | 줄마다 합성 후 이어붙임 | 멀티 스피커로 한 번에 |
| 출력 | MP3 | PCM → WAV (ffmpeg 있으면 MP3) |

**google을 기본으로 씁니다.** 점프리시는 미·영·호 발음 훈련이 핵심이라, 발음이 성우로
고정되는 쪽이 안전하고 무료 쿼터도 큽니다. gemini는 GCP 결제 계정을 쓸 수 없을 때의
대안으로 남겨 둡니다 (`TTS_ENGINE=gemini`).

## 1단계 — API 키 발급 (직접)

### google 엔진을 쓸 때 (권장)

1. [Google Cloud 콘솔](https://console.cloud.google.com) 접속 → 프로젝트 선택
2. [Cloud Text-to-Speech API 페이지](https://console.cloud.google.com/apis/library/texttospeech.googleapis.com)
   → **"사용"** 클릭 (상태가 "사용 설정됨"이 되면 완료)
3. **"사용자 인증 정보 만들기"** → **"API 키"** → `AIza...` 로 시작하는 문자열 복사

> **"결제 사용 설정 불가 — 프로젝트 수 한도" 오류가 나면?**
> 결제 계정마다 "결제를 켤 수 있는 프로젝트 수"가 정해져 있고, **삭제 대기 중(30일)인
> 프로젝트나 목록에 안 보이는 프로젝트도 개수를 차지합니다.**
> [리소스 관리](https://console.cloud.google.com/cloud-resource-manager)에서 삭제 대기 건을
> 정리하거나, 이미 결제가 켜진 다른 프로젝트에서 키를 만들면 됩니다
> (API 키는 어느 프로젝트에서 만들든 동일하게 작동합니다).

### gemini 엔진을 쓸 때

[Google AI Studio](https://aistudio.google.com/app/apikey) → **"Create API key"** → 복사.
TTS 모델은 무료 등급의 분당 요청 수가 매우 낮아 429가 잦습니다 — `TTS_DELAY`를 크게 잡으세요.

## 2단계 — 음원 생성 (Claude가 실행)

```
node tools/import.mjs                                        # 문항 ID 매핑 생성
GOOGLE_TTS_KEY=<키> TTS_LIMIT=3 node tools/tts-batch.mjs      # 먼저 3개만 시험 생성
GOOGLE_TTS_KEY=<키> node tools/tts-batch.mjs                  # 문제없으면 전량 생성
```

- 산출물: `tools/out/audio/` 폴더의 음원 + `audio-manifest.json`
- 듣기 문항은 총 46건(L1 8 · L2 24 · L3 6세트 · L4 8세트), 합성 글자수 약 6,000자
- L2는 질문+보기 A~D를 한 트랙으로, L3 대화는 화자별 목소리를 바꿔 만듭니다
- 이미 만든 파일은 건너뛰므로, 중간에 끊겨도 **다시 실행하면 이어서** 만듭니다

**조절 가능한 옵션** (환경변수)

| 변수 | 기본값 | 용도 |
|---|---|---|
| `TTS_ENGINE` | `google` | `gemini`로 바꾸면 Gemini API 사용 |
| `TTS_MODEL` | `gemini-2.5-flash-preview-tts` | gemini 전용. 고품질은 `gemini-2.5-pro-preview-tts` |
| `TTS_DELAY` | google 150 / gemini 1500 | 요청 간격(ms). 429가 잦으면 크게 |
| `TTS_LIMIT` | 없음 | 앞에서 N개만 만들고 중단 (시험용) |

## 3단계 — 청취 검수 (사용자 확인 필요)

전량 생성 후 표본 청취로 아래를 확인합니다.

- [ ] **미국·영국·호주 발음이 서로 구분되게 들리는가** (파트별 3개씩)
- [ ] 속도가 초등 저학년이 따라올 만한가 (앱에서 0.9배속도 지원)
- [ ] L2에서 질문과 보기 A~D 사이 간격이 충분한가
- [ ] L3 대화에서 두 화자의 목소리가 확실히 구분되는가
- [ ] 스크립트에 없는 말(안내 문구 등)이 섞여 들어가지 않았는가

## 4단계 — R2 업로드·연결 (Claude가 실행)

1. Cloudflare R2 버킷 `jumplish-assets` 생성 → 음원 업로드
2. 버킷에 공개 도메인 연결 (Cloudflare 대시보드에서 R2 → 버킷 → Settings → Public access)
3. `R2_PUBLIC_BASE=<공개 주소> node tools/import.mjs` → seed 재적용 → 앱에서 음원 재생 확인

## 자주 묻는 것

- **왜 실시간으로 안 만들고 미리 만드나요?** 학생이 들을 때마다 TTS를 호출하면 비용이 계속 나갑니다.
  미리 만들어 두면 몇 만 명이 들어도 추가 비용이 0원입니다.
- **비용은?** google 엔진은 월 100만 자까지 무료라 이번 물량(약 6천 자)은 **0원**입니다.
- **키가 유출되면?** 콘솔의 사용자 인증 정보(또는 AI Studio 키 목록)에서 삭제하면 즉시 무효화됩니다.
