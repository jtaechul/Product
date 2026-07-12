# 운영 준비 가이드 (iPad에서 전부 가능)

파이프라인은 코드가 완성돼 있고, 아래 **열쇠(시크릿) 등록만으로 기능이 하나씩 켜집니다.**
등록 위치: [GitHub 시크릿 등록 페이지](https://github.com/jtaechul/Product/settings/secrets/actions) → **New repository secret**

## 시크릿 현황표

| 이름 | 켜지는 기능 | 상태 |
|---|---|---|
| `SHORTS_TYPECAST_API_KEY` | 음성(TTS) | ✅ 등록됨 |
| `SHORTS_PEXELS_API_KEY` | 배경 영상 자동 확보 | ✅ 등록됨 |
| `ANTHROPIC_API_KEY` | 대본 자동 작성(M3) | 다른 프로젝트용으로 이미 등록돼 있으면 그대로 재사용됨(전용 키를 쓰려면 `SHORTS_ANTHROPIC_API_KEY` 등록) |
| `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` | 성공/실패 텔레그램 알림 | 기존 등록분 자동 재사용 |
| `SHORTS_YT_CLIENT_ID` + `SHORTS_YT_CLIENT_SECRET` + `SHORTS_YT_REFRESH_TOKEN` | **유튜브 자동 업로드(M7)** | ❌ 아래 절차로 발급 필요 |
| `SHORTS_YT_API_KEY` | 소재 리서치(M1, 주간 리포트) | ❌ 발급 필요(5분) |
| `SHORTS_COUPANG_ACCESS_KEY` + `SHORTS_COUPANG_SECRET_KEY` | 쿠팡 상품 자동 검색·딥링크(M2 1안) | ❌ 파트너스 승인 후 |

> ⚠️ 기존 `YOUTUBE_REFRESH_TOKEN`(다른 채널 계정)은 **의도적으로 사용하지 않습니다** —
> 쿠팡 쇼츠가 엉뚱한 채널에 올라가는 사고 방지. 새 채널 계정으로 `SHORTS_YT_REFRESH_TOKEN`을 발급하세요.

---

## A. 유튜브 업로드 인증 (SHORTS_YT_* 3종) — 브라우저만으로 가능

사전 준비: 쿠팡 쇼츠용 **새 유튜브 채널**(브랜드 계정 권장)을 만들어 두세요.

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

## B. 리서치용 API 키 (SHORTS_YT_API_KEY)

1. 같은 Google Cloud 프로젝트 → **사용자 인증 정보 만들기 → API 키**
2. 키를 `SHORTS_YT_API_KEY`로 등록
3. [config/competitors.yaml](../config/competitors.yaml)에 벤치마크 채널 ID를 채우면
   매주 월요일 아침 소재 후보 리포트가 자동 생성됩니다(텔레그램 발송 포함)

## C. 쿠팡 파트너스

1. [쿠팡 파트너스](https://partners.coupang.com) 가입 → 활동 시작(초기엔 링크 수동 생성)
2. 상품 추가 방법: [data/products_manual.csv](../data/products_manual.csv)에 1행 추가
   (파트너스에서 만든 제휴 링크를 `affiliate_url` 칸에) → main에 커밋하면 준비 완료
3. Open API 키가 발급되면(실적 요건 있음) `SHORTS_COUPANG_ACCESS_KEY/SECRET_KEY` 등록
   → 상품 검색·딥링크 자동화(M2 1안)로 전환 가능

## D. 자동 스케줄 (이미 켜져 있음)

- **제작**: 평일(월~금) 아침 07:30 KST — 큐에 미처리 상품이 있고 **유튜브 업로드 키(SHORTS_YT_*)까지
  준비된 경우에만** 실제 제작 (미비하면 크레딧을 쓰지 않고 조용히 통과 — 같은 상품을 매일
  중복 제작하는 낭비 방지. 업로드 키 없이 영상만 뽑아보려면 Actions 수동 실행을 사용)
- **리서치**: 월요일 09:00 KST
- 끄는 법: Actions → 해당 워크플로우 → ⋯ 메뉴 → **Disable workflow**
