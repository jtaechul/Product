# 천하쟁패 (Color Battle) — 군웅할거 관전 시뮬레이션

> 색으로 나뉜 6세력이 지도를 정복하는 **관전용(faceless-YouTube) 시뮬레이션** 게임
> 단일 HTML + Canvas + Vanilla JS · 의존성 없음 · 시드 재현 가능

---

## 1. 프로젝트 성격 (중요)
- 이건 "플레이하는 게임"이 아니라 **"보는 시뮬레이션"**이다 (마블 레이스류)
- 핵심 흥행 레버 = **응원 · 보이는 인과 · 앰비언트 · 단순함 · 캐릭터 연속성** (근거는 `docs/plan-v9.md`)
- 판단 규칙: 충돌 시 **가독성(P3)·보이는 인과(P2)가 최우선**, 전략 깊이는 후순위(P10)

## 2. 폴더 구조
```
color-battle/
├── index.html            ← 게임 본체 (현재 v9, 단일 파일로 완결·바로 실행됨)
├── README.md             ← 이 문서
├── assets/
│   └── generals/         ← 장수 초상 (누끼 PNG) — 규칙은 하위 README 참조
├── docs/
│   ├── plan-v9.md        ← 설계 원칙 문서 (개발의 기준)
│   └── CHANGELOG.md      ← v1~v9 이력 요약
```

## 3. 실행
- `index.html`을 브라우저로 열면 끝 (빌드·서버 불필요)
- 현재 그래픽은 전부 **코드로 그린 도형·엠블럼** → 외부 에셋 없이 단독 동작

## 4. GitHub Pages 배포 (NIGHT HUNTER와 동일 방식)
1. 새 repo 생성 후 이 폴더 내용을 그대로 push
2. repo → **Settings → Pages → Source: `main` 브랜치 / 루트(`/`)**
3. 몇 분 뒤 `https://<사용자명>.github.io/<repo명>/` 로 접속
- `index.html`이 루트에 있으므로 추가 설정 불필요

## 5. 6세력 정의 (색·문양·표기 통일 — 코드와 일치)
| 세력 | 색 | HEX | 문양 | 초상 파일명 |
|---|---|---|---|---|
| 화염단 | 빨강 | `#ff5555` | 불꽃/용 | `flame.png` |
| 심해군 | 파랑 | `#3aa0ff` | 파도 | `wave.png` |
| 뇌전대 | 노랑 | `#ffcb33` | 번개 | `bolt.png` |
| 정글파 | 초록 | `#37d982` | 잎/덩굴 | `leaf.png` |
| 보라단 | 보라 | `#b874ff` | 별자리 | `star.png` |
| 벚꽃단 | 핑크 | `#ff77bd` | 벚꽃 | `blossom.png` |

## 6. 현재 상태 & 다음 단계
- **완료 (v10)** —
  1. 장수 초상 6장 누끼 완료 → `assets/generals/*.png` (투명 배경, 머리카락 틈까지 제거·갑옷 내부 보존)
  2. **VS 카드 렌더러** (좌우 초상 카드 + 이름/계급 + HP 게이지 + 충돌 섬광 + 勝/敗 도장) — 도형 격투 대체. 초상 없으면 세력 엠블럼 자동 대체
  3. **명장 시스템** (세력별 고정 로스터 3인 + 계급·전공·통산전적) — 최고 계급 명장이 출전, 승리 시 승급 (P9)
  4. 일기토 빈도 축소 (대군격돌 삭제 → 수도 결전 전용 + 쿨다운 14초)
- **완료 (v9)** — 지역 정복·행군·자원·일기토·관전 명료성 패키지 P2/P3
- **다음(검토/제안 중)** —
  - **공성전**(수도 함락 직전 단계) 도입 여부 — 고조-이완(P5)·카타르시스(P8) 강화 후보
  - 일기토 픽셀 애니메이션(코에이식) 연출 검토
  - 명장 3인 개별 초상(현재는 세력 대표 초상 1장 공용)
- **장기** — 헤드리스 렌더 → ffmpeg → YouTube 자동 업로드 (GitHub Actions)

## 7. 장수 초상 재생성 레시피 (나노바나나)
세트 일관성 원칙: **배경·구도·화풍·조명 고정, 세력색만 스왑 / 한 명씩 / 3:4 / 흰 배경**

공통 골격:
```
Cinematic character portrait for a strategy game roster card.
Chest-up bust, single character, slight three-quarter angle facing viewer, head and shoulders fully in frame, centered.
East-Asian warring-states fantasy general in ornate lacquered plate armor with fur-trimmed war cloak, battle-worn, confident intense expression.
Painterly semi-realistic game splash-art style, highly detailed face, dramatic rim lighting on the character only.
Plain solid pure white background (#ffffff), evenly lit, no scenery, no shadow on background, no text, no border.
Clean crisp edges, no color spill, easy background removal. 3:4 vertical.
```
세력색 문구(골격 + 한 줄): 화염=deep crimson red & gold, flame motifs / 심해=deep ocean blue & silver, wave motifs / 뇌전=golden yellow & bronze, lightning motifs / 정글=jade green & bronze, leaf motifs / 보라=violet purple & silver, star motifs / 벚꽃=cherry-blossom pink & rose-gold, blossom motifs

## 8. ⚠️ 재업로드 시 주의 (파일명 충돌)
- iOS는 사진을 전부 `FullSizeRender.jpeg`로 내보냄 → 여러 장을 한 번에 올리면 **같은 이름끼리 덮어써져 1장만 남음**
- 해결: **한 메시지에 한 장씩** 올리거나, 업로드 전 파일명을 `flame/wave/bolt/leaf/star/blossom`으로 변경

## 9. 튜닝 메모
- 모든 밸런스 상수는 `index.html` 상단 `P` 객체에 모여 있음 (생산·행군속도·수도방어·자원보정·일기토 확률 등)
- 수치는 플레이테스트 없이 추정한 값 → 관전하며 조정 필요
