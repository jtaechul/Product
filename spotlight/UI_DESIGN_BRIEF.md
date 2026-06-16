# 🎨 SPOTLIGHT UI 디자인 의뢰서 (메뉴맵 + 생성 프롬프트)

다른 생성형 AI(GPT-4o 이미지, nano banana, Galileo/Uizard 등)에게 **UI 디자인을 의뢰**하기 위한 문서입니다.
아래 블록을 복사해 사용하세요. **목표는 "화면 시안 PNG" 또는 "낱개 UI 부품 PNG"** 를 받아오는 것입니다.

---

## 0) 기본 사양 (모든 의뢰에 공통 — 맨 앞에 붙이기)

```
PROJECT: "SPOTLIGHT" — a 2D actress-raising life-sim mobile game (Korean), Umamusume-style.
TARGET: mobile PORTRAIT, design canvas 720 x 1280 px (9:16). One-hand thumb operation;
primary action buttons live in the BOTTOM 40% (thumb zone). Min tap target 96px.
ART DIRECTION: bright cheerful youthful anime UI. Pastel base (cream #FFF1E8, soft mint
#BFE6DF), accent CORAL #FF8A7A, MINT #7EE0C8, GOLD #F5C451; ink text #2A2A33. Rounded
cards (radius 14-26), soft shadows, friendly rounded Korean font. Clean, high-contrast,
readable. NO photo, flat illustration-style UI.
DELIVER: transparent-background PNG UI parts (panels, buttons, cards, frames, icons),
plus a full-screen mockup. No lorem text — use the Korean labels given.
```

---

## 1) 메뉴맵 (화면 구조 트리)

```
[타이틀] ──▶ [캐릭터 생성(머리색 선택)] ──▶ [메인 스케줄]
                                              │
  ┌───────────────────────────────────────────┘
  │  메인 스케줄 화면 (핵심)
  │   ├ 상단 상태바: 날짜(고1·3월) · 이름(소윤) · 체력 · 멘탈 · 돈 · 팬
  │   ├ 캐릭터(상반신 크게, 하단 패널이 다리 가림)
  │   ├ 매니저 말풍선 (한지원 대사)
  │   ├ 하단 명령 패널
  │   │    ├ 활동 슬롯 2개 (선택 현황)
  │   │    ├ [메뉴 1단계] 카테고리 4개: 🎭연기 / ✨매력 / 📚소양 / 💛생활
  │   │    │      └─(탭)─▶ [메뉴 2단계] 세부 활동 카드들
  │   │    │                 🎭연기: 연기 학원 · 차기작 준비
  │   │    │                 ✨매력: 보컬 레슨 · 댄스 레슨 · 헬스·PT · 스타일링
  │   │    │                 📚소양: 독서실 · 독서·교양 · 봉사활동
  │   │    │                 💛생활: 가족과 시간 · 친구와 우정 · 휴식 · 단기 알바
  │   │    └ [▶ 다음 달] 버튼
  │   └ 하단 탭(예정): 스탯 · 필모 · 상점 · 인연 · 설정
  │
  ├▶ [작품 출연/평가] (예정)   ├▶ [엔딩] (예정)
```

> 흐름: **카테고리 1개 탭 → 세부 활동 1개 선택(슬롯에 담김) → 카테고리로 복귀 → 두 번째 선택 → [다음 달]**

---

## 2) 화면 시안 의뢰 — 메인(카테고리 화면)

```
Design ONE full mobile screen (720x1280 portrait) for the main schedule screen,
CATEGORY-SELECT state. Layout top-to-bottom:
1) Top status bar (rounded white panel): left = date "고1·3월" (bold) and name "소윤";
   right = four small pill stats in 2x2: "체력 70", "멘탈 70", "돈 10만", "팬 0"
   (each pill tinted: 체력 red, 멘탈 blue, 돈 gold, 팬 coral).
2) Character zone (leave empty / transparent placeholder box ~center): the game places a
   large anime girl here (upper body); the bottom panel covers her legs. Do NOT draw her.
3) Manager speech bubble (dark navy rounded bar): label "한지원" in mint + line
   "이번 달은 뭘 해볼까?".
4) Bottom command panel (cream rounded-top sheet) containing:
   - two empty activity slot chips: "슬롯 1: 비어있음", "슬롯 2: 비어있음"
   - FOUR big category buttons in a row: 🎭 "연기", ✨ "매력", 📚 "소양", 💛 "생활"
     (colors: 연기 coral, 매력 mint, 소양 gold, 생활 periwinkle), each with emoji + label + tiny sub-desc.
   - a wide primary button at the very bottom: "▶ 다음 달".
Style per the base spec. Output the full screen mockup PNG.
```

---

## 3) 화면 시안 의뢰 — 메인(세부 활동 화면)

```
Design the SAME main screen but in SUB-ACTIVITY state after tapping "매력".
Same top bar, character placeholder, manager bubble, and bottom panel. In the panel:
- one slot filled "슬롯 1: 보컬 레슨", one empty "슬롯 2: 비어있음"
- a small "← 카테고리" back button, and section title "✨ 매력"
- a 2-column grid of activity cards, each card = emoji + name + sub-stat + cost line:
    "🎤 보컬 레슨 / 가창 / 돈 -6만 체력 -8"
    "💃 댄스 레슨 / 댄스 / 돈 -6만 체력 -10"
    "🏋️ 헬스·PT / 체력·외모 / 돈 -4만 체력 +3"
    "💄 스타일링 / 외모·인지도 / 돈 -2만 체력 -5"
- bottom primary button "▶ 다음 달" (active coral).
Output the full screen mockup PNG.
```

---

## 4) 낱개 UI 부품 의뢰 (★ 게임에 바로 넣기 좋음 — 권장)

> 화면 통짜보다 **부품 PNG(투명배경)** 를 받으면 제가 코드에 정확히 끼워 넣기 쉽습니다.
> 아래를 각각 의뢰하세요. 9-slice(늘어나는 모서리) 가능하면 더 좋습니다.

```
On a fully transparent background, design these flat anime-style UI parts as a labeled set,
matching the base spec palette (coral/mint/gold/cream, rounded, soft shadow):
A) Bottom command panel sheet (rounded-top, cream) — 720px wide.
B) Primary CTA button (coral, rounded 20) in 3 states: normal / pressed / disabled(gray).
C) Activity card (white rounded, soft border) blank template, 330x94.
D) Category button (rounded 14, solid color) blank template, 163x150.
E) Slot chip (rounded, light) blank, 330x46.
F) Top status pill (rounded) blank, 118x38.
G) Manager speech bubble bar (dark navy, rounded) 688x66 with a small tail.
Each part centered with clear padding, exported separately, transparent PNG.
```

```
On a transparent background, design a set of 12 cute flat activity ICONS, single object each,
soft pastel, rounded, consistent style, 1:1:
연기학원(script+mask) 차기작준비(target) 보컬레슨(microphone) 댄스레슨(dancing shoes)
헬스PT(dumbbell) 스타일링(lipstick/mirror) 독서실(desk lamp+book) 독서교양(open book)
봉사활동(helping hands/heart) 가족과시간(house+heart) 친구와우정(two hands) 휴식(coffee cup)
No text. Export each icon separately.
```

```
On a transparent background, design 4 category ICONS, flat pastel, 1:1, consistent set:
🎭연기(theater masks) ✨매력(sparkle/star) 📚소양(stacked books) 💛생활(heart/home).
No text. Export each separately.
```

---

## 5) 돌려받을 때 형식 (저에게 보내실 때)

- **투명배경 PNG**로, 부품은 낱개 파일로.
- 파일명에 용도 표기(캡션이나 파일명): 예) `panel_bottom`, `btn_next_normal`, `card_activity`,
  `cat_acting`, `icon_vocal` …
- 화면 통짜 시안이면 "카테고리 화면 / 세부 화면"이라고만 적어주세요.

→ 받으면 제가 배경정리·크기조정 후 **현재 코드(좌표·상태머신)에 그대로 교체**해 넣겠습니다.
지금 코드는 기능(2단 메뉴·정산·포즈전환)이 동작하니, **그림만 갈아끼우면** 됩니다.
