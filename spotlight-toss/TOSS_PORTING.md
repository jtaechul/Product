# SPOTLIGHT — 토스 앱인토스 출시 가이드

> 이 문서는 SPOTLIGHT를 [토스 앱인토스](https://developers-apps-in-toss.toss.im/)에 올리기 위해
> **이미 코드에 해둔 것**과 **앞으로 사람이 직접 해야 하는 것**을 정리한 안내서다.
> (사용자는 터미널 초보 — 실제 명령 실행 단계는 Claude Code 세션에서 함께 진행할 것)

---

## 1. 이미 완료된 것 (코드)

| 항목 | 내용 | 위치 |
|---|---|---|
| 토스 SDK 동봉 | 공식 `@apps-in-toss/web-framework`를 단일 파일로 번들(26KB). 빌드 없는 구조 유지 | `spotlight/vendor/apps-in-toss.min.mjs` |
| 플랫폼 어댑터 | 토스 안=SDK / 일반 웹=localStorage 자동 전환. **토스 밖에서는 SDK를 아예 로드하지 않음** → GitHub Pages 버전은 예전과 완전히 동일하게 동작 | `spotlight/src/systems/platform.js` |
| 네이티브 저장소 | 세이브·사운드설정·엔딩도감 3곳을 토스 Storage로 전환 (필수 SDK ①) | `save.js` `sound.js` `ending.js` |
| 게임 로그인 | `getUserKey()` — 토스 유저 식별자(hash) 발급 준비 (필수 SDK ②) | `platform.js` |
| 리더보드 | 엔딩 도달 시 커리어 점수 자동 제출 (필수 SDK ③) | `ending.js computeCareerScore` + `MainScene.showEnding` |
| Safe Area | 토스 SDK 인셋과 env() 중 큰 값 적용 — 노치·다이나믹아일랜드·홈바 (필수 SDK ④) | `SceneManager._safeInsets` |
| 행동 로그 | 게임시작/이어하기/턴 진행/출연 결과/엔딩 (필수 SDK ⑤) | `TitleScene` `MainScene` |
| 로딩 최적화 | 첫 화면 필수 에셋만 대기, 연출용(배경 16장·인연 4장·포즈)은 백그라운드 로드 — "10초 이내 최초 화면" 심사 기준 대응 | `MainScene.onEnter` |
| 패키징 래퍼 | `npm run build` = spotlight → dist 정적 복사(불필요 파일 제외, 125MB) | `spotlight-toss/` |

**커리어 점수(리더보드) 계산**: 능력치 10종 합(최대 1000) + 팬수(500 상한) + 호평작×15 + 수상×40.
화면에는 노출하지 않고 토스게임센터 순위에만 쓴다.

## 2. 앞으로 해야 하는 것 (사람 작업)

### ① 게임물 등급분류 심의 — 가장 먼저, 가장 오래 걸림

모든 게임은 법(게임산업법 제21조)에 따라 등급분류가 필요하다. 애플/구글 IARC 등급은 국내 무효.

- **경로 A — 게임물관리위원회(GRAC) 직접**: [www.grac.or.kr](https://www.grac.or.kr) 에서 등급분류 신청
  → **등급분류증명서**를 앱인토스 콘솔에 첨부.
- **경로 B — 자체등급분류사업자 경유**: 원스토어·삼성 갤럭시스토어 등(자체등급분류사업자)에 앱을 먼저 출시
  → 그 **스토어 링크**를 첨부.
- SPOTLIGHT는 폭력·사행성·선정성 없음 → **전체이용가** 예상. 신청서에 쓸 자료(스크린샷·설명)는 Claude 세션에서 만들어줄 수 있다.

### ② 앱인토스 콘솔 준비

1. [앱인토스 개발자센터](https://developers-apps-in-toss.toss.im/) → 콘솔 가입, **워크스페이스** 생성 (사업자 정보 필요할 수 있음)
2. 새 미니앱 등록: **카테고리 = 게임** (게임 로그인·리더보드 API는 게임 카테고리에서만 동작)
3. 앱 이름·아이콘·소개 이미지 등록
4. 등록 후 받은 **appName**을 `spotlight-toss/granite.config.ts`의 `appName`에, 아이콘 URL을 `brand.icon`에 기입 ← Claude에게 맡기면 됨

### ③ 리더보드 개설

토스게임센터 콘솔에서 **리더보드(순위표)를 생성**해야 점수 제출이 동작한다.
(코드는 이미 제출하게 되어 있음 — 콘솔에 리더보드가 없으면 `LEADERBOARD_NOT_FOUND`로 조용히 무시됨)

### ④ 빌드·업로드 (콘솔 등록 후 Claude와 함께)

```bash
cd spotlight-toss
npm install          # 최초 1회
npx ait init         # 앱인토스 초기화(콘솔 연동)
npm run build        # dist/ 생성 (정적 복사)
# → 콘솔 '앱 출시' 메뉴에 번들 업로드 → 샌드박스 앱에서 테스트 → 출시 요청
```

### ⑤ 심사 (평균 2~3일, 4단계)

운영 검수(서류) → 기능 검수(오류 없이 동작) → 디자인 검수(토스 UI 가이드) → 보안 검수.
게임은 **심의 완료(①) 없이는 런칭 불가**.

## 3. 심사 기준 대비 현황

| 심사 항목 | 상태 |
|---|---|
| 풀스크린 + Safe Area | ✅ 대응 (SDK 인셋 병합) |
| 세로/가로 모드 정상 | ✅ 세로 고정 설계 + 가로 회전 대응 |
| 최초 화면 10초 이내 | ✅ 로딩 2단계 분리 완료 |
| 인터랙션 2초 이내 | ✅ PixiJS GPU 렌더 |
| eval 등 외부 코드 실행 금지 | ✅ 없음 |
| SSR 금지 | ✅ 정적 사이트 |
| wss:// 외 WebSocket 금지 | ✅ WebSocket 미사용 |
| 네이티브 저장소 | ✅ 전환 완료 |
| 외부 링크/자사 앱 유도 금지 | ✅ 없음 |
| 결제 | 해당 없음 (인앱결제 미사용) |
| 생성형 AI 고지 | 해당 없음 (런타임 AI 없음) |

## 4. 남은 확인·선택 사항

- **패키지 용량 125MB**: 앱인토스 번들 용량 제한이 있는지 콘솔에서 확인 필요.
  초과 시: BGM mp3 9곡(26MB)을 96kbps로 재인코딩(-40%), 엔딩 일러스트 15장(26MB) 압축(-30%) 여지 있음.
- **리더보드 UI**: 현재 점수 제출만 함. 원하면 메뉴에 "순위 보기" 버튼(`openLeaderboard()`) 추가 가능.
- **토스 인앱 테스트**: 샌드박스 앱을 설치한 실기기에서 저장·리더보드·Safe Area 실동작 확인 필요
  (SDK는 토스 앱 안에서만 실제로 동작한다 — 브라우저에선 자동으로 웹 모드).

## 5. 정책 확인 결과 (서비스 오픈 정책 대조)

- 제한 서비스(가상자산·사행성·금융·의료 등) 해당 없음 — 배우 육성 시뮬레이션.
- 광고·결제·로그인 정책: 외부 광고/결제/소셜로그인 미사용이므로 충돌 없음.
- 어뷰징 방지: 동일 워크스페이스 내 유사 앱 반복 출시 금지 — SPOTLIGHT 1개만 출시 예정이므로 해당 없음.

> 참고 문서: [게임 출시 체크리스트](https://developers-apps-in-toss.toss.im/checklist/app-game.html) ·
> [서비스 오픈 정책](https://developers-apps-in-toss.toss.im/intro/guide.html) ·
> [WebView(기존 웹) 가이드](https://developers-apps-in-toss.toss.im/tutorials/webview.html) ·
> [게임 필수 SDK 5종 블로그](https://toss.im/apps-in-toss/blog/apps-in-toss-game-sdk-guide)
