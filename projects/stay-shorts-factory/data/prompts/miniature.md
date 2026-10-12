# 미니어처 연출 지시문 규칙 — "실사 숙소 안의 장난감 세상" (2026-10-12 운영자 결정 · 절대 규칙)

> Veo(이미지→영상) 컷에 들어가는 인물은 **이 문서의 캐릭터 블록을 글자 하나 바꾸지 않고** 앞에 붙인다. 장면 블록만 컷마다 쓴다.
> 운영자 Gemini 시험(2026-10-12, 3장): "점 눈·코 없음"처럼 비워 둔 항목을 모델이 매번 다르게 채웠다(흰자 눈+이빨 / 조각상 얼굴+쪽머리+수영복 없음 / 단순 점 눈).
> 2차 시험(2026-10-12, 운영자): 얼굴·머리·수영복·손·질감은 블록과 일치. 위반 1건 = 여자 인물 눈의 속눈썹 → "both figures identical eye construction" 강조 추가.
> → 얼굴 부품의 **생성 방식**(모양·개수·재질)을 하나로 못 박고, 표정은 눈·입의 곡선만 바뀌게 한다. 디테일 수준은 "아주 조금 있는" 중간(3번 사진보다 한 단계 위).

## 1. 캐릭터 블록 v2 (고정 · 모든 컷 공통 · 영어 그대로 복사)

> v2 (2026-10-12 운영자 "이런 느낌의 캐릭터를 원한다" — 눈 쪽 온천 반실사 피규어 사진): 3등신 점눈 클레이 → **반실사 손조각·손채색 피규어**(6등신, 아몬드형 채색 눈, 작은 코·닫힌 입술, 조각 머리, 미나는 낮은 올림머리).
> 예외 없이 지킬 것: 수영복 끈이 수면 위로 보인다(나체처럼 보이는 결과 금지), 속눈썹·화장·이빨 금지, 두 인물 같은 눈 구조.
> 실제 제작(Veo)에서는 이 블록 끝에 `BACKGROUND: use the attached hotel photograph as the exact, unchanged background — same walls, water, furniture, colors and lighting; nothing added, removed or redrawn.` 을 붙인다.

```
CHARACTERS — FIXED DESIGN, identical in every image and every shot. Two hand-sculpted, hand-painted miniature figurines of a Korean couple in their early 30s, "Mina" (woman) and "Jun" (man): collectible art-doll figurines about 10 cm tall with semi-realistic adult proportions (about six heads tall), photographed as tiny toys inside a real full-size place.

MATERIAL: smooth sculpted polymer clay with a soft satin finish, subtle hand-painted shading, a faint warm blush on the cheeks, nose tip and shoulders; edges slightly softened like a sculpted doll. No fingerprints, no seams, no plastic gloss, no realistic pores or skin texture. When wet, only a thin glossy sheen.

FACE — identical construction on both figures: softly sculpted oval face with gentle cheekbones. Eyes: almond-shaped sculpted eyes with painted dark-brown irises and black pupils, only a thin sliver of white at the corners, one tiny white highlight. Closed eyes are a sculpted downward-curving lid with one thin painted dark line along the lash line — no individual eyelashes, no makeup. Eyebrows: thin, softly painted, natural dark-brown. Nose: small straight sculpted nose with a softly rounded tip and barely indicated nostrils. Mouth: small closed sculpted lips painted muted rose with a calm faint smile; no teeth, never open. Ears: small sculpted ears. Expression range: calm, relaxed, content — only the eyelids (open or closed) and the faint smile change.

HAIR: sculpted as one solid piece with shallow carved groove lines suggesting strands, satin finish, no loose strands. Mina: dark chocolate-brown hair with a side part, pulled back smoothly into a neat low round bun at the back of the head. Jun: black short hair, slightly longer on top and swept to one side, short sides.

BODY: slim adult build, sculpted shoulders and subtle collarbones, hands with five simplified sculpted fingers held softly together, natural relaxed poses.

CLOTHING — always worn: Mina wears a plain cobalt-blue one-piece swimsuit whose thin shoulder straps stay visible above the waterline; Jun wears plain navy swim trunks with a bare chest. In sauna, room, lobby, restaurant and balcony scenes both wear plain cream waffle-texture bathrobes over the swimwear. No patterns, logos, jewelry, glasses or hats.

SCALE: the figures are tiny — about one-sixth the length of a lounge chair, each head roughly the size of a walnut next to a pool rim or a pebble next to a stone edge. Real objects in the scene stay full-size.

PHOTOGRAPHY: realistic macro toy photography, camera low near the figures' eye level, shallow depth of field — figures tack-sharp, background softly blurred. Natural light matching the scene, soft contact shadows, true reflections in the water. Vertical 9:16.

FORBIDDEN: real people, realistic human skin, chibi or big-head proportions, dot eyes, cartoon or anime eyes, eyelashes, makeup, teeth, open mouths, nudity or missing swimsuit straps, patterned or colorful swimwear, more than two figures, flyaway hair strands, distorted hands, extra fingers, text, logos, watermarks, melted or morphing shapes.
```

## 2. 장면 블록 (컷마다 · 장소 사전에서 고른다 · 영어)

틀: `SCENE: [위치] + [자세] + [동작 1개 · 4초 타임라인] + [환경 반응 1개] + Camera: locked-off, slow 5 percent push-in. Vertical 9:16, 4 seconds, photoreal background, toy-scale clay figures in focus.`

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
3. 일관성 장치: 캐릭터 참조 이미지(정면·뒷모습·흰 배경, 이 블록으로 생성)를 `assets/characters/` 에 두고 Veo 참조 입력으로 함께 보낸다.
4. Veo 전에 같은 지시문으로 정지 이미지 2~3장(무료 구간)을 뽑아 블록과 맞는지 **운영자가** 본다(AI 검수 호출 없음 — 운영자 "검수는 돈").
5. 캡션 끝에 "미니어처 인물은 AI 연출입니다" 한 줄. 영상 안에는 글자 추가 없음.
