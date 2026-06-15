# 🎨 SPOTLIGHT 에셋 생성 프롬프트 모음 (nano banana / GPT 이미지용)

> 주인공 화풍을 **일관되게** 유지하기 위한 생성 프롬프트 모음입니다.
> **사용법**: 아래 프롬프트를 복사 → 이미지 생성 AI(nano banana=Gemini, GPT-4o 등)에
> 붙여넣고, **반드시 디자인 시트 PNG를 레퍼런스 이미지로 함께 첨부**하세요.
> (레퍼런스: `assets/portraits/heroine_design_sheet_brown.png` 또는 `_red.png`)

---

## 0) 공통 스타일 앵커 (모든 프롬프트 앞에 붙여 쓰기)

```
STYLE REFERENCE: Use the attached character design sheet as the exact style,
face, hair and outfit reference. Keep the SAME girl: bright cheerful Japanese-
anime style, soft cel shading, big expressive eyes with crisp highlights.
HAIR/EYES: long wavy BROWN hair with a blue flower-ribbon hair accessory and
brown eyes  (← for the RED version: crimson wavy long hair, red eyes, no flower).
OUTFIT (signature school uniform, keep identical every time): navy blazer,
white dress shirt, blue ribbon tie, light-blue plaid pleated skirt, navy
over-knee socks, brown loafers.
OUTPUT: single character only, clean isolated cutout on a FULLY TRANSPARENT
background, no scenery, no text, no watermark, no border, no extra characters,
consistent proportions with the reference.
```

> 💡 팁: 한 번에 한 포즈씩, 같은 시드/대화에서 이어 만들면 일관성이 더 좋아집니다.
> 전신은 세로 2:3 또는 3:4, 얼굴 포트레이트는 1:1 비율을 권장합니다.

---

## 1) 표정 5종 (기획서 14·17번) — 최우선 필요 ⭐

스프라이트 시트의 표정은 머리카락이 겹쳐 깔끔히 못 잘립니다 → **새로 생성 권장.**
같은 정면 얼굴/상반신으로 표정만 바꿔 5장 (배경 투명, 동일 구도):

| 파일명(권장) | 표정 | 프롬프트 핵심(공통 앵커 뒤에 붙이기) |
|---|---|---|
| `face_joy.png` | 기쁨 | `Front-facing bust (head and shoulders), bright happy smile, eyes curved in joy, cheeks slightly blushed.` |
| `face_sad.png` | 슬픔 | `Front-facing bust, sad downcast expression, teary glistening eyes, slightly trembling mouth.` |
| `face_surprise.png` | 놀람 | `Front-facing bust, surprised expression, wide open eyes, small open mouth, eyebrows raised.` |
| `face_proud.png` | 뿌듯 | `Front-facing bust, proud confident smile, eyes gently closed or sparkling, chin slightly up.` |
| `face_down.png` | 풀죽음 | `Front-facing bust, dejected gloomy expression, half-closed eyes, shoulders drooping, small sigh.` |

> ⚠️ 5장 모두 **머리·구도·조명·크기를 동일**하게(표정만 다르게) 만들어야 게임에서
> 얼굴 레이어 교체 시 어긋나지 않습니다. 한 장 만든 뒤 "같은 그림, 표정만 바꿔서"로 이어 요청하세요.

---

## 2) 활동 포즈 9종 (기획서 9·14번) — 전신, idle과 같은 크기/시점 ⭐

메인 화면에서 활동 선택 시 보여줄 **전신 동작 포즈**. (공통 앵커 + 아래 한 줄)

| 파일명 | 활동 | 프롬프트 핵심 |
|---|---|---|
| `pose_acting.png` | 🎬 연기 학원 | `Full body, holding a script booklet, emotive acting gesture with one hand raised.` |
| `pose_vocal.png` | 🎤 보컬 레슨 | `Full body, singing into a handheld microphone, eyes closed, music notes vibe.` |
| `pose_dance.png` | 💃 댄스 레슨 | `Full body, mid dance step pose, dynamic balanced posture, one leg lifted.` |
| `pose_gym.png` | 🏋️ 헬스·PT | `Full body, stretching / light dumbbell pose, sporty determined look, small sweat drop.` |
| `pose_study.png` | 📖 독서실·인강 | `Full body, sitting at a desk writing notes, focused concentrated expression.` |
| `pose_volunteer.png` | 🤲 봉사활동 | `Full body, carrying a box / warm bowing greeting, kind gentle smile.` |
| `pose_family.png` | 👨‍👩‍👧 가족과 시간 | `Full body, relaxed at-home posture, soft content smile, comfortable.` |
| `pose_rest.png` | ☕ 휴식 | `Full body, relaxing / slumped on a sofa, sleepy cozy expression (Zzz).` |
| `pose_filming.png` | 🎥 작품 출연 | `Full body, standing in front of a film camera and lighting, confident "action!" pose.` |

---

## 3) 컨디션·결과 연출 포즈 (기획서 14번 A·C)

| 파일명 | 용도 | 프롬프트 핵심 |
|---|---|---|
| `idle_good.png` | 좋은 컨디션 idle | `Full body relaxed idle, humming happily, light bounce, very cheerful.` |
| `idle_tired.png` | 지친 idle (체력 낮음) | `Full body, shoulders drooping, tired heavy breathing, weary expression.` |
| `result_cheer.png` | 극찬/호평 | `Full body, jumping with a victory "V" sign, big delighted smile, confetti feel.` |
| `result_sad.png` | 혹평 | `Full body, crouching dejected, dark gloomy mood, disappointed.` |
| `result_fail.png` | 트레이닝 실패 | `Full body, stumbling off-balance, sweat drop, flustered.` |

---

## 4) 조력 캐릭터 4인 (기획서 12·17번) — 각자 포트레이트 + 표정 3~4종

공통 앵커의 "주인공" 부분을 아래 인물 설명으로 교체. **각 인물도 화풍은 동일하게.**

| 캐릭터 | 설명 프롬프트(공통 출력규칙은 0번 재사용) |
|---|---|
| 🎧 매니저 한지원 | `A friendly young male/female talent manager in a smart casual blazer, late 20s, warm trustworthy smile, holding a tablet. Same anime art style as the heroine.` |
| 🔥 라이벌 유세아 | `A sharp confident teenage actress rival, stylish, slight smirk, intense eyes, school uniform variant in a cooler color. Same anime art style.` |
| 🎓 연기선생 노교수 | `An older distinguished acting teacher, 50s, glasses, gentle but firm expression, cardigan. Same anime art style.` |
| 🧑‍🤝‍🧑 단짝 친구 | `A cheerful supportive teenage best friend, casual school uniform, bright laughing face. Same anime art style.` |

> 각 인물: **얼굴 포트레이트(1:1) 1장 + 표정 3~4종**(기쁨/걱정/놀람/응원)을 1번과 같은 방식으로.

---

## 5) 배경 6종 (기획서 17번) — 캐릭터 없이, 가로 또는 세로 9:16

```
[공통] Bright anime background illustration, soft pastel youthful tone,
NO characters, no text. Vertical 9:16 friendly mobile-game backdrop.
```
- `bg_school.png` — 밝은 고등학교 교실/복도
- `bg_academy.png` — 연기 학원 연습실 (거울·바)
- `bg_set.png` — 드라마/영화 촬영장 (카메라·조명)
- `bg_stage.png` — 뮤지컬/연극 무대 (스포트라이트)
- `bg_award.png` — 시상식 무대 (레드카펫·트로피)
- `bg_home.png` — 아늑한 집 거실/방

---

## 6) 엔딩 일러스트 15종 (기획서 15번) — 노년 배우 회고 분위기

```
[공통] Emotional anime illustration, 60-year-old veteran actress version of the
SAME character (aged-up gracefully, keep hair color cue), cinematic warm lighting,
award-ceremony / film-set mood. Portrait or scene, no text. Vertical 3:4.
```
대표 엔딩(파일명 예): `end_national.png`(국민 대배우·공로상 무대), `end_film.png`(영화계 거장),
`end_drama.png`(안방극장의 별), `end_global.png`(한류스타), `end_musical.png`(뮤지컬 디바),
`end_theater.png`(연극 거목), `end_star.png`(스타성), `end_variety.png`(예능 대세),
`end_character.png`(천의 얼굴), `end_supporting.png`(명품 조연), `end_latebloom.png`(대기만성),
`end_director.png`(감독 겸 배우), `end_mentor.png`(후학 양성), `end_unknown.png`(묵묵한 무명),
`end_scandal.png`(구설수). → 기획서 15번 표의 분위기를 한 줄씩 덧붙여 생성.

---

## 7) UI/아이콘 (선택) — 활동 카드·매체 썸네일

```
[공통] Cute flat anime-style icon, single object, simple soft pastel palette,
rounded, on transparent background, no text. 1:1.
```
- 활동 14종 아이콘(연기/보컬/댄스/헬스/독서/봉사/가족/우정/스타일링/차기작/휴식/알바/학교/출연)
- 매체 썸네일(웹드라마·단편영화·CF·뮤지컬·OTT·영화 등)

---

## 📌 저장 위치 가이드 (생성 후 넣을 폴더)

```
spotlight/assets/
├── portraits/
│   ├── faces/            ← 표정 5종, 인물 포트레이트
│   └── poses/            ← 활동·연출 전신 포즈 (새로 만들 폴더)
├── manager/ rivals/      ← 조력 캐릭터
├── bg/                   ← 배경 6종
└── endings/              ← 엔딩 15종
```

생성해서 보내주시면 제가 배경 키잉(투명 처리)·크기 정리·게임 코드 연결까지 처리하겠습니다.
