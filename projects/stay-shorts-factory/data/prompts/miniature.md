# 미니어처 연출 지시문 규칙 — "실사 숙소 안의 장난감 세상" (2026-10-12 운영자 결정 · 절대 규칙)

> Veo(이미지→영상) 컷에 들어가는 인물은 **이 문서의 캐릭터 블록을 글자 하나 바꾸지 않고** 앞에 붙인다. 장면 블록만 컷마다 쓴다.
> 운영자 Gemini 시험(2026-10-12, 3장): "점 눈·코 없음"처럼 비워 둔 항목을 모델이 매번 다르게 채웠다(흰자 눈+이빨 / 조각상 얼굴+쪽머리+수영복 없음 / 단순 점 눈).
> 2차 시험(2026-10-12, 운영자): 얼굴·머리·수영복·손·질감은 블록과 일치. 위반 1건 = 여자 인물 눈의 속눈썹 → "both figures identical eye construction" 강조 추가.
> → 얼굴 부품의 **생성 방식**(모양·개수·재질)을 하나로 못 박고, 표정은 눈·입의 곡선만 바뀌게 한다. 디테일 수준은 "아주 조금 있는" 중간(3번 사진보다 한 단계 위).

## 1. 캐릭터 블록 v3 — ⭐ 확정 (2026-10-12 운영자 "잘 만들어졌다, 이 이미지가 제일 마음에 든다") (고정 · 모든 컷 공통 · 영어 그대로 복사)

> v3 (2026-10-12 운영자 3차 시험 → "8등신 성인 체형, 남자 머리 계속 바뀜 — 통일"): 실측 문제 = 머리가 큰 4~5등신으로 나옴, 준의 머리가 뾰족·옆으로 넘김·헬멧형으로 3장 모두 다름, 수영복 바지 길이 들쭉날쭉.
> 고친 것: **8등신을 수치로**(머리 길이 × 8 = 키, 다리 = 키의 절반, "큰 머리·어린이·버블헤드 금지"), 준 머리를 **앞머리 내린 댄디컷 하나**로 모양·길이·결 선까지 고정(옆으로 넘김·뾰족·볼륨 금지), 미나 올림머리 위치·크기 고정,
> 수영복 디자인 고정(스쿱넥·가는 끈 / 허벅지 중간 길이·끈 없음), 크기 기준을 실제 비율로 교정(머그컵 높이·의자의 1/20·타일 = 머리), 피부색 하나.
> 2026-10-12 운영자 "미니어처가 너무 안 움직인다, 즐기듯 움직이는 게 자연스럽다" → 표정 범위를 차분~즐거움(닫힌 입 큰 미소)으로 넓히고, 영상 지시문은 "살아서 즐기는 뚜렷한 동작 2~3개 + 물 반응"으로 바꿈(스톱모션·같은 위치 고정 문구 삭제). 정체성(얼굴·머리·수영복·체형) 고정 문장은 유지.
> 실제 제작(Veo)에서는 이 블록 끝에 `BACKGROUND: use the attached hotel photograph as the exact, unchanged background — same walls, water, furniture, colors and lighting; nothing added, removed or redrawn.` 을 붙인다.
> **기준 이미지(확정)**: `assets/characters/ref.jpg` — v3 블록 + 장면 ③(수영장 가장자리 발 담그기)으로 운영자가 Gemini 에서 만든 결과. 8등신 성인 체형, 준 = 앞머리 내린 둥근 댄디컷,
> 미나 = 왼쪽 가르마 낮은 올림머리, 코발트 원피스(스쿱넥·가는 끈) / 남색 허벅지 중간 수영복. **모든 생성(정지 이미지·Veo)에 이 이미지를 참조로 첨부**하고,
> 블록 앞에 `Keep both figures exactly identical to the attached reference figurines — same faces, hairstyles, body proportions, skin tone and swimwear.` 를 붙인다(마른 장소는 `… and skin tone.` — 수영복 낱말 없음). 결과가 이 이미지와 다르면 버린다.

```
CHARACTERS — FIXED DESIGN, identical in every image and every shot. Two hand-sculpted, hand-painted miniature figurines of a Korean couple in their early 30s, "Mina" (woman) and "Jun" (man): collectible art-doll figurines with realistic adult fashion-figure proportions, photographed as tiny toys inside a real full-size place. Jun is 10 cm tall; Mina is 9.5 cm tall.

PROPORTIONS — strictly eight heads tall: total height equals eight head lengths. Small head, long neck, shoulders about two head-widths wide, legs exactly half of the total height, natural adult waist and hips. This is an elegant adult figurine — NOT a doll with an oversized head, NOT chibi, NOT a child, NOT a bobblehead. Mina: slim, graceful feminine build. Jun: slim athletic build with broad shoulders and a softly sculpted chest, no exaggerated muscles, no visible six-pack.

MATERIAL: smooth sculpted polymer clay with a soft satin finish, subtle hand-painted shading, a faint warm blush on the cheeks, nose tip and shoulders; edges slightly softened like a sculpted doll. No fingerprints, no seams, no plastic gloss, no realistic pores or skin texture. When wet, only a thin glossy sheen. Skin is one warm light-beige tone on both figures.

FACE — small because of the eight-head proportions, but fully detailed, and built identically on both figures: softly sculpted oval face with gentle cheekbones. Eyes: almond-shaped sculpted eyes with painted dark-brown irises and black pupils, only a thin sliver of white at the corners, one tiny white highlight. Closed eyes are a sculpted downward-curving lid with one thin painted dark line along the lash line — no individual eyelashes, no makeup. Eyebrows: thin, softly painted, natural dark-brown. Nose: small straight sculpted nose with a softly rounded tip and barely indicated nostrils. Mouth: small sculpted lips painted muted rose; when laughing, surprised or cheering the mouth may open into a simple rounded shape (plain sculpted interior, at most a simple white band for teeth, no tongue detail). Ears: small sculpted ears. Expression range: from calm to joyful — eyelids open, closed or happily curved, and the smile ranges from faint to a big open laugh; nothing else on the face changes.

HAIR — exact and never changes, wet or dry, from any angle:
Mina: dark chocolate-brown hair with a side part on her left side, all hair combed smoothly back over both ears into one neat round low bun at the nape of the neck; the bun is about half the size of her head; 10 to 12 shallow carved groove lines run from the hairline back to the bun; no fringe, no loose strands, no ponytail, no high bun.
Jun: jet-black short Korean dandy cut. The top is combed straight forward into a soft rounded fringe that covers the forehead and ends just above the eyebrows; the sides and back are short and tapered close to the head, with both ears fully visible; the whole outline is a smooth rounded cap shape with 8 to 10 shallow carved groove lines running from the crown toward the fringe. No side part, no swept-to-the-side hair, no spikes, no upward quiff, no volume lift, no messy or wet-look texture.

CLOTHING — exact and always worn: Mina wears a plain cobalt-blue one-piece swimsuit with a scoop neckline, thin shoulder straps and a moderate leg cut, matte finish; the straps stay visible above the waterline. Jun wears plain dark-navy swim shorts ending at mid-thigh with a flat elastic waistband, no drawstring, no stripes; bare chest. In sauna, room, lobby, restaurant and balcony scenes both wear plain cream waffle-texture bathrobes over the swimwear. No patterns, logos, jewelry, glasses or hats.

SCALE: each figure is about the height of a coffee mug (10 cm) placed in a real full-size place — a lounge chair is about twenty times longer than a figure, and a 2.5 cm pool mosaic tile is about as tall as a figure's head. Real objects in the scene stay full-size.

PHOTOGRAPHY: realistic macro toy photography, camera low near the figures' chest level, both figures fully in frame from head to the waterline or feet, shallow depth of field — figures tack-sharp, background softly blurred. Natural light matching the scene, soft contact shadows, true reflections in the water. Vertical 9:16.

FORBIDDEN: real people, realistic human skin, big heads, chibi, child or bobblehead proportions, dot eyes, cartoon or anime eyes, eyelashes, makeup, detailed realistic teeth, nudity or missing swimsuit straps, patterned or colorful swimwear, drawstrings, any hairstyle other than the ones described, side-swept or spiky hair on Jun, more than two figures, flyaway hair strands, distorted hands, extra fingers, text, logos, watermarks, melted or morphing shapes.
```

## 1-1. 모델 선택 (2026-10-12 운영자 결정)

- 미니어처 인물 영상 = **Gemini Omni Flash** (비오 라이트는 남녀가 뒤바뀌어 인물 컷 금지). 환경 움직임만(사람 없음) = Veo 3.1 Lite. 단순 줌·패닝 = 사진 무빙 0원.
- 옴니 카메라는 다가가며 원본 밖을 지어내므로(run-27: 없는 수영장) **첫 장면 구도 고정, 아주 약간의 당기기까지만**(코드 `VEO_TAIL`). 비전이 쓰는 동작에 카메라 지시(zoom·push·pan·close-up)는 금지 — 코드가 거른다.

## 1-2. 연출 톤 — 엉뚱하고 재밌게 (2026-10-12 운영자)

- 컷당 **개그 하나**, 그 장소를 즐기는 행동과 이어지게. 예: 파도에 밀려 둘이 동시에 뒤로 엉덩방아 → 거품 수염을 달고 일어나 웃기 / 김 속에서 준이 고개만 쏙 내밀기 /
  미나가 수건을 뗏목처럼 띄우고 눕기 / 준이 물을 튀기려다 자기 얼굴에 맞기 / 창가 소파에서 둘이 같은 자세로 기지개 / 침대에 누워 이불 속으로 쏙 사라졌다 나오기.
- 금지: 위험 행동(얕은 물 다이빙·젖은 바닥 뛰기·난간 오르기), 시설 오용·파손, 다른 사람 방해, 사실과 다른 시설 기능. (입 벌림은 2026-10-12 운영자 허용 — 웃음·놀람·환호 때 자연스럽게)

## 1-3. 편당 구성 — 미니어처 3컷 (2026-10-12 운영자 결정)

| 순서 | 컷 | 모델 | 내용 |
|---|---|---|---|
| ① | 컷 1 (훅) | Omni Flash | **장소 개그** — 첫 1초에 웃음으로 멈추게. 물 사진 우선 |
| ② | 중간 컷 1개 (객실·특별 공간 중 하나) | Omni Flash | **장소 개그** — ①과 다른 장소·다른 개그 |
| ③ | 마지막 내용 컷(끝 카드 직전) | Omni Flash | **채널 시그니처 포즈**(아래 고정 블록, 매 편 동일) |
| — | 물·김 움직임 컷 0~1개 (사람 없음) | Veo 3.1 Lite | 파도·물결·김·커튼 |
| — | 나머지 컷 | 사진 무빙 0원 | 줌·패닝 |

- 편당 예상(추정): 합성 이미지 3장 약 170원 + 옴니 4초 3컷 약 1,764원 + (라이트 1컷 294원) + 글·음성 약 80원 = **약 2,000~2,300원**. 월 18편이면 약 36,000~41,000원으로 월 5만 원 상한에 가깝다 → 라이트 컷은 물 장면이 정말 좋을 때만.
- 옴니 단가·우리 키 사용 가능 여부는 모델 목록(무료)과 공식 가격표로 확정한 뒤 코드에 넣는다(확정 전 추정).
- 한 편 안에서 개그는 2개(①②) + 시그니처 1개(③)만. 같은 개그를 연속 편에서 반복하지 않는다(최근 3편 기록 확인).

## 1-4. 채널 시그니처 포즈 — 고정 블록 (매 편 마지막 미니어처 컷 · 글자 그대로)

장소는 그 편에서 가장 대표적인 사진(보통 훅과 같은 물 공간의 **마른 가장자리·데크**, 없으면 객실 침대 앞)을 쓴다. 젖은 바닥 뛰기 같은 위험 동작 없음.

```
SIGNATURE ENDING — identical in every video. Mina and Jun stand side by side at the real spot described, facing the camera, both wearing a cream terry-towel "sheep-head" wrap (a Korean jjimjilbang style towel rolled into two small round ears on top of the head) over their usual hair, wearing the same outfit as in the first frame. 0 to 1.5 seconds: they turn to the camera at the same time and give one small hop of excitement. 1.5 to 3 seconds: they raise both arms over their heads and join their hands to form one big heart shape together, tilting their heads toward each other. 3 to 4 seconds: they hold the big heart pose with big happy smiles and happily curved eyes, bouncing once in rhythm. No text, no props other than the towel wraps.
```

## 1-5. 장소 개그 사전 (컷 ①② · 장소와 연결 · 하나만 고른다)

| 장소 유형 | 개그 (4초) |
|---|---|
| 실내 파도풀 | 파도가 오자 둘이 서핑 자세를 잡다가 그대로 덮여 엉덩방아 → 거품 수염을 달고 일어나 웃기 |
| 노천탕·자쿠지 | 준이 물을 튀기려다 자기 얼굴에 맞고 멍한 표정 → 미나가 웃으며 어깨를 토닥 |
| 사우나·스파 | 둘이 양머리 수건을 쓰고 무지 노란 우유병으로 건배 → 동시에 "크~" 하듯 눈을 질끈 감기 |
| 레인 수영장 | 가장자리에 앉아 둘이 발장구를 치다 점점 빨라져 물보라가 커지고 서로 쳐다보며 웃기 |
| 인피니티풀 | 난간에 팔을 걸치고 풍경을 보다가 손가락 쌍안경을 만들어 서로를 쳐다보고 깜짝 |
| 객실 침대 | 둘이 동시에 침대에 대자로 풀썩 쓰러진 뒤 이불 속으로 사라졌다가 고개만 쏙 |
| 객실 창가·소파 | 손가락 쌍안경으로 창밖 산을 보다 서로를 보고 놀라기 / 같은 자세로 기지개 |
| 발코니·테라스 | 난간 앞에서 짧은 어깨춤(이름 없는 단순 동작) 후 하이파이브 |
| 레스토랑·조식 | 접시 앞에서 둘이 볼이 빵빵해진 채 엄지척(입은 닫힌 채) |
| 로비·복도 | 작은 캐리어를 끌고 들어오다 멈춰 두 팔 벌려 "짠" 포즈 |

- 춤·세리머니: 이름 없는 단순 동작만(어깨 들썩, 엉덩이 흔들기, 두 팔 벌려 비행기, 하늘 가리키기). **유행 챌린지 이름·안무, 음원, 선수 이름·등번호·유니폼은 쓰지 않는다**(저작권·퍼블리시티권 위험 — 확실하지 않음, 보수적으로).
- 4초 안에 동작 1~2개만, 크고 단순하게(빠르고 복잡하면 작은 인형의 팔다리·얼굴이 무너진다).
- 개그용 소품(양머리 수건·무지 우유병·작은 캐리어)은 그 컷에서만 허용 — 캐릭터 블록의 "no props/hats" 보다 이 사전이 우선.

## 2. 장면 블록 (컷마다 · 장소 사전에서 고른다 · 영어)

틀: `SCENE: [위치] + [자세] + [동작 1개 · 4초 타임라인] + [환경 반응 1개] ` (카메라 문장은 코드가 고정으로 붙인다 — 장면 블록에 쓰지 않는다)

| 장소 유형 | 위치·자세 | 동작(4초) | 환경 반응 |
|---|---|---|---|
| 야외 온천·자쿠지 | 가까운 가장자리, 어깨까지 잠김, 카메라 쪽 비스듬히 | Mina 머리를 돌 테두리에 기대고, Jun 한 손을 들어 물을 떨어뜨림 | 김이 오른쪽으로 흐르고 작은 물결 |
| 실내 파도풀 | 얕은 앞쪽, 허리 깊이, 손 잡고 | 낮은 파도가 뒤에서 와 둘을 살짝 띄웠다 내림, Jun 손 들어 환호 | 천장 조명에 물 반짝임, 작은 물방울 |
| 레인 수영장 | 가장자리에 나란히 앉아 발 담금 | Mina 발을 천천히 저음 | 발끝에서 물결 퍼짐 |
| 인피니티풀 | 끝 난간에 팔 걸치고 풍경 보는 뒷모습 | Jun 고개를 돌려 Mina 를 봄 | 수면 반사, 멀리 풍경 그대로 |
| 사우나 | 가운 입고 나무 벤치에 나란히 앉음 | Mina 눈을 감고 고개 젖힘 | 은은한 김 |
| 객실 침대 | 가운 입고 이불 위에 눕기 | Jun 이 이불 위로 폴짝 올라와 눕고 Mina 가 웃음 | 이불 표면 살짝 눌림 |
| 객실 소파·창가 | 가운 입고 소파에 앉아 창밖 보기 | Mina 가 창 쪽을 가리킴 | 커튼 미세 흔들림 |
| 발코니·테라스 | 난간 앞에 서서 산을 보는 뒷모습 | Jun 이 기지개 | 나뭇잎 미세 흔들림 |
| 레스토랑 | 테이블에 앉아 작은 접시 앞 | Mina 가 포크 든 손을 들어 올림 | 창밖 빛 그대로 |
| 복도·로비·외관 | 걸어 들어오며 두리번 | 둘이 나란히 네 걸음 | 바닥 반사 그대로 |

## 3. 조립·검증 규칙 (코드)

1. 컷의 "화면에 보이는 것" 설명으로 장소 유형을 고르고, Gemini 가 표의 형식대로 장면 블록만 쓴다(인물 묘사 금지 — 인물은 블록이 담당).
2. 최종 지시문 = 캐릭터 블록 + 장면 블록 (코드가 붙임). 한 편 안에서 캐릭터 블록은 바이트 단위로 동일.
3. 일관성 장치: 기준 이미지 `assets/characters/ref.jpg` 를 매 생성에 참조로 첨부한다. 제작 순서(예정·유료라 승인 뒤 구현):
   ① Gemini 이미지 편집 = 숙소 사진 + ref.jpg + 캐릭터 블록 + 장면 블록 → 인물이 들어간 첫 프레임 1장(사진 배경은 그대로)
   ② Veo 이미지→영상 = 그 첫 프레임에서 4초 동작(장면 블록의 타임라인). 인물이 첫 프레임부터 있어 "갑자기 나타남"·얼굴 흔들림이 줄어든다.
4. Veo 전에 같은 지시문으로 정지 이미지 2~3장(무료 구간)을 뽑아 블록과 맞는지 **운영자가** 본다(AI 검수 호출 없음 — 운영자 "검수는 돈").
5. 캡션 끝에 "미니어처 인물은 AI 연출입니다" 한 줄. 영상 안에는 글자 추가 없음.

## 4. 오류 요인 검수 규칙 (2026-10-12 운영자 "한 번 더 검수해서 오류 날 요인 전부 고쳐" · 코드로 강제)

| 요인 (실측 근거) | 규칙 | 코드 |
|---|---|---|
| 마른 장소 지시문의 물 낱말(run-27 없는 수영장) | 마른 장소의 합성·옴니 지시문에 water·pool·swim·splash·wave·ripple·wet·spa·bath·tub·jacuzzi·steam **0개**. 부정문도 금지. 남으면 돈 쓰기 전에 멈춤 | `make_mini.edit_prompt`·`omni_prompt` 검사, `make_solo.mini_errs` |
| 캐릭터 블록·유지 문장 속 수영복·'wet' | 마른 장소는 CLOTHING·젖음·수영복 금지 항목·'wet or dry'·'wet-look' 삭제, 유지 문장도 수영복 없이, 옷은 가운 고정 | `character_block(water=False)`, `KEEP_LINE_DRY`, `OUTFIT_DRY` |
| 비전이 인형 생김새를 적음('hand-carved wooden' → 나무 인형) | 인형은 이름으로만. 생김새 낱말은 지워서 보냄 | `clean_scene`, `MINI_SYSTEM` |
| 크게 당기는 카메라 | 동작에 카메라 지시 금지, 옴니는 구도 고정 | `CAMERA_WORDS`, `VEO_TAIL` |
| 인형이 자막·앱 버튼 자리에 들어감(run-27 훅 65~95%, 시그니처 84~95%) | 인형 전신은 화면 높이 25~60%·오른쪽 15% 밖. 비전 상자 세로 0.15~0.66·오른쪽 0.90 안. 합성 뒤 상자 중심 0.70 넘으면 옴니 생략 | `EDIT_SCALE`, `ZONE`, `mini_errs`, `make_minis` |
| 인형이 너무 작음(run-27 객실 12%·전경 11%) | 비전 상자 높이 0.15 이상, 합성 뒤 0.12 미만이면 옴니 생략 | `mini_errs`, `make_minis` |
| 원본 복원 때 몸 잘림(run-27 훅: 머리 없는 인형) | 상자 다듬기는 색 차이까지 보고 위로 넉넉히(최소 22%) 찾는다. 상한을 넘겨 제한할 때도 위로 높이 80% | `refine_box` |
| 합성이 배경을 통째로 다시 그림 → 상자가 커져 가짜 배경이 살아남음 | 상자는 비전 상자의 2.5배·화면 40% 이하. 복원 뒤에도 30% 넘게 바뀌면 옴니 생략 | `refine_box`, `make_minis` |
| 화면 가장자리 인형이 복원 때 지워짐 | 가장자리에 붙은 변은 안쪽으로 들이지 않고 이음매 검사에서도 뺀다 | `paste_back` |
| 시그니처 양머리 수건 vs 캐릭터 블록 'no hats' 충돌 | 시그니처 컷에만 수건 허용 줄을 붙인다. 물가 데크여도 물 반응 문장 없음 | `PROPS_SIGNATURE` |
| 짧은 나레이션에 하트 포즈가 잘림 | 미니어처 컷 최소 3.4초 | `MIN_MINI` |
| 환경 컷(라이트)의 '드론 글라이드'·'표면 전체 파도' | 카메라 고정 + 약 5% 당기기, 있는 물·김·빛만 움직임 | `ENV_PROMPT` |
| 잔잔한 풀에서 파도 개그 등 시설과 다른 연출 | 개그는 사진에 보이는 것만으로 가능해야 함 | `MINI_SYSTEM` |
| `"fake": true` 면 미니어처(합성·옴니)가 허락 없이 유료로 돌 수 있었음 | 미니어처는 옴니·합성 둘 다 가짜일 때만 허락 면제 | `make_stay.main`, `make_mini.main` |
| 합성 이미지 비용이 한 번 실행 한도에서 빠짐 | 이미지도 실행 한도(3,000원)에 합산 | `composite` |

