# Night Hunter — 도시 원칙 (City Design Principles)

이 문서는 도시 레이아웃 관련 **불변 규칙**을 정의한다. 어떤 변경도 이 규칙을
위반해서는 안 된다. 위반 시 즉시 수정 + 회귀 검증.

## 🚨 SYNC RULE (절대 위반 금지) — 실 맵 = 미니맵

### **실제 맵(world.js)과 미니맵(ui.js)은 항상 100% 동일해야 한다.**

- **데이터 중복 금지**: 공원·로데오·건물·도로 등 좌표·치수 배열을
  world.js 와 ui.js 양쪽에 따로 적지 않는다. 가능한 한 `window.*`
  단일 export(`window.MAIN_ROADS`, `window._policeStation`,
  `window._buildingPositions` 등)를 통해 ui.js 가 world.js 의 데이터를
  그대로 읽어 그린다.
- 부득이하게 ui.js 에 좌표 배열을 별도로 둬야 한다면(`PARKS`, `RODEOS`
  같은 시각 보조 배열), **world.js 의 원본 배열과 항목 수·좌표·치수가
  1:1로 정확히 일치**해야 하며, world.js 를 수정하면 **반드시 같은 커밋에서**
  ui.js 의 대응 배열도 함께 수정한다.
- **검증 절차**: world.js 의 `createCityParks`, `createRodeoStreet`,
  `defineBlocks`, `createPoliceStation` 등 좌표를 변경할 때마다
  ui.js 의 `updateMinimap`/`drawFullMap` 안의 대응 배열을 grep 하여
  일치 여부를 확인하고, 불일치 시 즉시 수정한다.
- 실 맵에서 삭제한 오브젝트(공원, 건물, props 등)는 **같은 작업에서**
  미니맵에서도 삭제한다 — 한쪽만 지우는 것은 CORE RULE 의
  "실 맵/미니맵 모두 적용" 조항 위반이다.

## 🚨 CORE RULE (절대 위반 금지)

### **도로 위에는 그 어떤 고정된 물체나 건물도 있을 수 없다.**

- 도로 = MAIN_ROADS 의 asphalt 영역 (도로 중심 ±`w/2`)
- 위반 금지 대상: 건물, 가로등, 가로수, 화분, 표지판, 벤치, 분수,
  사인포스트 등 모든 정적 메쉬
- 예외: **도로 표면 페인팅(횡단보도, 차선)** 만 허용 — 이건 도로의 일부
- 동적 객체(자동차, 보행자) 는 도로 위 이동 가능

### **이 규칙은 실 맵(world.js) 과 미니맵(ui.js) 모두에 적용된다.**

- 실 맵의 건물/props 좌표가 도로 asphalt 와 겹치면 안 됨
- 미니맵 그릴 때도 도로 위에 건물 사각형이 그려지면 안 됨
- 둘은 항상 동일한 데이터(MAIN_ROADS, BUILDING_BLOCKS) 에서 도출

## 도로 vs 건물

1. **도로 asphalt 영역은 어떠한 건물 footprint 와도 겹치지 않는다.**
   - 도로 z 또는 x 좌표 기준 ± `w/2` 가 asphalt 영역.
   - 빌딩 footprint (`bx ± bw/2`, `bz ± bd/2`) 가 이 영역과 교차하면 안 됨.

2. **도로 위에는 어떤 물체도 놓이지 않는다.**
   - 가로등, 벤치, 화분, 표지판, 가로수 등 모든 props 는 도로 asphalt
     영역 밖(인도 또는 잔디)에 위치해야 함.
   - 횡단보도는 예외 (도로 표면에 직접 페인팅하므로).

3. **건물 블록(BUILDING_BLOCKS)의 minZ/maxZ 또는 minX/maxX 는 인접 도로
     중심에서 최소 `w/2 + 1.0m` 이상 떨어져야 한다.**
   - 도로 폭 8m → 블록 경계는 도로 중심에서 ±5.0m 이상.
   - 도로 폭 10m → ±6.0m 이상.

4. **검증 절차** (defineBlocks 후 즉시 실행):
   - 각 BUILDING_BLOCKS 의 사각형과 각 MAIN_ROADS asphalt 영역을 AABB
     교차 검사.
   - 교차 발생 시 console.error 로 즉시 보고.
   - **추가**: 모든 props 함수(createStreetProps, createCityParks,
     createRodeoStreet) 가 배치한 mesh 좌표도 도로 영역과 비교.

## 도로 연결성

5. **모든 도로는 사각형 perimeter + 내부 격자로 완전히 연결된다.**
   - 끊긴 도로(dead-end) 없음.
   - V 도로는 모두 남측 perimeter 와 북측 perimeter (또는 우회 경로) 에 연결.
   - 모든 H × V 교차로에 횡단보도.

## 횡단보도

6. **횡단보도는 교차로 4면(북/남/동/서) 의 인도 끝에만 배치.**
   - 교차로 가운데 (도로 교차 영역) 에는 횡단보도 띠 없음.
   - zebra 패턴: 흰 띠 5개, 폭 0.45m, 간격 0.45m, 도로를 가로지름.

## 미니맵 ↔ 실 맵 일치

7. **미니맵 (`updateMinimap`, `drawFullMap`) 은 `window.MAIN_ROADS` 를
   동적으로 읽어 그린다.** 하드코딩된 좌표 사용 금지.

8. **공원, 로데오 거리, 특수 영역도 미니맵 범례 및 채색에 반드시 반영.**

9. **CORE RULE 준수**: 미니맵에서도 건물 사각형이 도로 선과 겹치면 안 됨.
   미니맵 렌더링 시 빌딩이 도로 영역에 그려지지 않는지 시각 검증.

## 위치 상수 단일 출처

10. **경찰서 좌표, shop 좌표, rescue 목적지 좌표 등 가변 위치 상수는
    `window._policeStation = { x, z, w, d }` 와 같은 단일 export 를 통해
    shop.js / minigame.js / npc.js 가 참조해야 한다.**
    - 하드코딩된 `0, 110` 같은 좌표 절대 금지.
    - 변경 시 한 곳만 수정해도 모든 모듈이 따라가도록.

## 상업지구 형태

11. **상업지구는 전체가 로데오 거리 형태로 구성된다.**
    - 차량용 도로(MAIN_ROADS)가 상업지구 내부를 가로지르지 않음.
    - 내부는 보행자 plaza + 양옆 상가 건물 행으로만 구성.
    - 외부 perimeter H/V 도로에서만 진입 가능.

## 변경 절차

- 도로, 블록, 경찰서 위치 등을 변경할 때는 위 1~11 모든 규칙을 다시 검증.
- 검증 실패 시 변경 거부.
- 특히 CORE RULE 위반 발생 시 PR 자체 reject.

