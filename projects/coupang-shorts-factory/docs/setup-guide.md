# 운영 준비 가이드 (iPad에서 전부 가능)

파이프라인은 코드가 완성돼 있고, 아래 **열쇠(시크릿) 등록만으로 기능이 하나씩 켜집니다.**
등록 위치: [GitHub 시크릿 등록 페이지](https://github.com/jtaechul/Product/settings/secrets/actions) → **New repository secret**

## 0. 관리자 페이지 — 모든 조작은 여기서 (노코드)

**[관리자 페이지 열기](https://shorts-admin.jtaechul.workers.dev)** — 상품 등록·삭제, 제작 실행,
실행 기록(영상 다운로드), 벤치마크 채널 관리를 전부 버튼과 입력칸으로 처리합니다.
파일이나 코드를 직접 편집할 일이 없습니다. (사파리 공유 버튼 → **홈 화면에 추가**를 해두면 앱처럼 열립니다)

최초 1회, 페이지가 저장소를 조작할 수 있게 **GitHub 토큰(출입증)** 을 연결합니다:

1. [GitHub 새 토큰 만들기 화면](https://github.com/settings/personal-access-tokens/new) 열기
2. Token name: `shorts-admin` / Expiration: **Custom**으로 최대(약 1년) 선택
3. Repository access: **Only select repositories** → `jtaechul/Product`
4. Permissions → Repository permissions에서 딱 2개만:
   **Contents = Read and write**, **Actions = Read and write**
5. 맨 아래 **Generate token** → 초록색 긴 문자열 복사 → 관리자 페이지 **설정 탭**에 붙여넣고 저장

토큰은 그 기기의 브라우저에만 저장됩니다 (저장소·서버로 올라가지 않음).

## 시크릿 현황표

| 이름 | 켜지는 기능 | 상태 |
|---|---|---|
| `SHORTS_TYPECAST_API_KEY` | 음성(TTS) | ✅ 등록됨 |
| `SHORTS_PEXELS_API_KEY` | 배경 영상 자동 확보 | ✅ 등록됨 |
| `ANTHROPIC_API_KEY` | 대본 자동 작성(M3) | 다른 프로젝트용으로 이미 등록돼 있으면 그대로 재사용됨(전용 키를 쓰려면 `SHORTS_ANTHROPIC_API_KEY` 등록) |
| `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` | 성공/실패 텔레그램 알림 | 기존 등록분 자동 재사용 |
| `SHORTS_YT_CLIENT_ID` + `SHORTS_YT_CLIENT_SECRET` + `SHORTS_YT_REFRESH_TOKEN` | **유튜브 자동 업로드(M7)** | ❌ 아래 절차로 발급 필요 |
| `SHORTS_YT_API_KEY` | 소재 리서치(M1, 주간 리포트) | ✅ 등록됨 |
| `SHORTS_COUPANG_ACCESS_KEY` + `SHORTS_COUPANG_SECRET_KEY` | 쿠팡 상품 자동 검색·딥링크(M2 1안) | ❌ 파트너스 승인 후 |

> ⚠️ 기존 `YOUTUBE_REFRESH_TOKEN`(다른 채널 계정)은 **의도적으로 사용하지 않습니다** —
> 쿠팡 쇼츠가 엉뚱한 채널에 올라가는 사고 방지. 새 채널 계정으로 `SHORTS_YT_REFRESH_TOKEN`을 발급하세요.

---

## A. 유튜브 업로드 인증 (SHORTS_YT_* 3종) — 브라우저만으로 가능

사전 준비: 쿠팡 쇼츠용 **새 유튜브 채널**(브랜드 계정 권장)을 만들어 두세요.
채널을 만들 준비가 되면 Claude에게 "채널 만들자"라고 말하세요 — 이름·핸들·초기 설정
컨설팅과, 만든 채널에 대한 피드백까지 진행하기로 예약되어 있습니다.

1. [Google Cloud Console](https://console.cloud.google.com/)에서 기존 프로젝트 선택(또는 새로 만들기)
2. **API 및 서비스 → 라이브러리** → "YouTube Data API v3" 검색 → **사용 설정**
3. **API 및 서비스 → 사용자 인증 정보 → 사용자 인증 정보 만들기 → OAuth 클라이언트 ID**
   - 애플리케이션 유형: **웹 애플리케이션**
   - 승인된 리디렉션 URI에 추가: `https://developers.google.com/oauthplayground`
   - 만들기 → 표시되는 **클라이언트 ID / 클라이언트 보안 비밀**을 각각
     `SHORTS_YT_CLIENT_ID` / `SHORTS_YT_CLIENT_SECRET` 시크릿으로 등록
4. **OAuth 동의 화면**에서 게시 상태를 **프로덕션**으로 전환
   (테스트 상태면 발급 토큰이 7일 뒤 만료됩니다. "확인되지 않은 앱" 경고는 본인만 쓰므로 무시 가능)
5. [OAuth Playground](https://developers.google.com/oauthplayground) 접속 → 오른쪽 위 **톱니바퀴** →
   **Use your own OAuth credentials** 체크 → 3번의 클라이언트 ID/비밀 입력
6. 왼쪽 Step 1 입력칸에 아래 두 줄을 넣고 **Authorize APIs**:
   ```
   https://www.googleapis.com/auth/youtube.upload
   https://www.googleapis.com/auth/youtube.force-ssl
   ```
7. 구글 로그인 창에서 **쿠팡 쇼츠 채널 계정** 선택 → 허용
8. Step 2에서 **Exchange authorization code for tokens** → 표시되는 **Refresh token**을
   `SHORTS_YT_REFRESH_TOKEN` 시크릿으로 등록

등록 후 Actions에서 produce를 실행하면 자동으로 **비공개(private) 업로드 + 고지 댓글 등록**까지 진행됩니다.
(댓글 "고정"만 유튜브 앱에서 1탭 — API가 고정 기능을 지원하지 않습니다)

## B. 리서치용 API 키 (SHORTS_YT_API_KEY) — 5분, 무료

"벤치마크 채널에서 최근 유독 터진 영상"을 매주 자동 수집하는 열쇠입니다.
A(업로드 인증)와 별개라서 **이것만 먼저 해도 됩니다.**

1. [Google Cloud Console](https://console.cloud.google.com/) 접속 → 구글 계정으로 로그인
   - 처음이라 프로젝트가 없으면: 위쪽 프로젝트 선택 → **새 프로젝트** → 이름 아무거나 → 만들기
2. 왼쪽 메뉴(☰) → **API 및 서비스 → 라이브러리** → 검색창에 `YouTube Data API v3`
   → 결과 클릭 → 파란 **사용(Enable)** 버튼
3. 왼쪽 **API 및 서비스 → 사용자 인증 정보** → 상단 **+ 사용자 인증 정보 만들기 → API 키**
   → 화면에 뜨는 긴 키 문자열 복사 (이 키가 `SHORTS_YT_API_KEY`입니다)
4. [GitHub 시크릿 등록 페이지](https://github.com/jtaechul/Product/settings/secrets/actions)
   → **New repository secret** → Name: `SHORTS_YT_API_KEY`, Secret: 복사한 키 → **Add secret**
5. [관리자 페이지](https://shorts-admin.jtaechul.workers.dev) **채널 탭**에서
   유튜브 앱의 @핸들을 붙여넣고 **채널 추가** — 끝

이후 매주 월요일 09:00 자동 실행 + 텔레그램으로 후보 top5 발송. 바로 돌려보려면
[리서치 워크플로우](https://github.com/jtaechul/Product/actions/workflows/shorts-research.yml) → **Run workflow**.

## C. 쿠팡 파트너스 — 상품 한 줄 추가하는 법 (iPad 웹만으로 가능)

### C-1. 제휴 링크 만들기

1. [쿠팡 파트너스](https://partners.coupang.com) 로그인 → 상단 **링크 생성 → 상품 링크**
2. 영상으로 만들 상품 검색 → 원하는 상품의 **링크 생성** 버튼
3. **단축 URL**(`https://link.coupang.com/a/...` 형태) 복사 — 이게 `제휴링크` 칸에 들어갑니다

### C-2. 상품 이미지 주소 얻기 (같은 화면에서)

1. 링크 생성 결과 화면에서 **이미지** 또는 **이미지+텍스트** 탭 선택
2. 코드 안에서 `https://` 로 시작해 `.jpg` 나 `.png` 로 끝나는 주소만 골라 복사
   — 파트너스가 공식 제공하는 상품 이미지라 저작권 걱정 없이 영상에 쓸 수 있습니다 (스펙 §3.2)
3. 복잡하면 이미지 칸은 **비워도 됩니다** — 영상은 자막+배경만으로 만들어집니다
   (쿠팡 상품 페이지의 이미지를 임의로 긁어오는 것은 금지 — 파트너스 제공분만 사용)

### C-3. 관리자 페이지에서 상품 등록 (링크 + 캡처 첨부)

1. **상품 페이지 PDF 만들기** (아이폰·아이패드):
   사파리에서 쿠팡 상품 페이지 열기 → 리뷰 부분까지 한 번 스크롤(그래야 후기도 담김) →
   **스크린샷** → 왼쪽 아래 미리보기 탭 → 위쪽 **전체 페이지** 선택 → 공유 → **파일에 저장**
2. [관리자 페이지](https://shorts-admin.jtaechul.workers.dev) → **상품 탭**:
   **제휴 링크**(C-1) 붙여넣기 + **캡처 칸에서 방금 저장한 PDF 선택** (스크린샷 이미지
   여러 장도 되고, 복사한 이미지를 화면에 붙여넣기 해도 첨부됩니다)
   - 상품명·가격·특징·후기 요점은 캡처에서 **자동으로 읽어냅니다** (직접 입력은 선택)
   - 이미지 주소(C-2)는 선택 — 있으면 영상에 상품 사진이 들어갑니다
   - 캡처는 정보 추출에만 쓰고 영상 화면에는 넣지 않습니다(저작권 규칙 §3.2)
   - 참고: 캡처 맨 위에 쿠팡 로그인 이름(별표 마스킹됨)이 보일 수 있습니다. 저장소가
     공개라서 신경 쓰이면 로그아웃 상태로 캡처하세요 (업로드 성공 후엔 자동 삭제됨)
3. **제작 탭 → 지금 제작하기** — 대기열 맨 위 상품부터 제작됩니다
   - 업로드까지 성공하면 사용한 캡처 파일은 자동으로 정리됩니다
   - 기존 `[테스트]` 행은 상품 탭 목록의 **삭제** 버튼으로 정리하세요

### C-4. (나중에) 쿠팡 Open API

Open API 키가 발급되면(파트너스 실적 요건 있음) `SHORTS_COUPANG_ACCESS_KEY/SECRET_KEY` 등록
→ 상품 검색·딥링크 자동화(M2 1안)로 전환 — 위 수동 과정이 통째로 자동화됩니다.

## D. 자동 스케줄 (이미 켜져 있음)

- **제작**: 평일(월~금) 아침 07:30 KST — 큐에 미처리 상품이 있고 **유튜브 업로드 키(SHORTS_YT_*)까지
  준비된 경우에만** 실제 제작 (미비하면 크레딧을 쓰지 않고 조용히 통과 — 같은 상품을 매일
  중복 제작하는 낭비 방지. 업로드 키 없이 영상만 뽑아보려면 Actions 수동 실행을 사용)
- **리서치**: 월요일 09:00 KST
- 끄는 법: Actions → 해당 워크플로우 → ⋯ 메뉴 → **Disable workflow**
