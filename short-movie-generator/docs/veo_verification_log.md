# Veo 실측 검증 로그

> 유료 생성마다 결과를 기록. 다음 프롬프트 보정의 근거.

## v3 — 2026-07-05 (STEP 0 반영, cut1 discovery, 8s, ~$0.5)

### 개선 확인 (성공)
- [x] 해저 퇴적층 배경 (benthic 데이터 반영) + 바닥 실트 헤이즈
- [x] ROV 장비 하단 가장자리 노출 (프레임/암) → "ROV가 찍는다" 느낌 달성
- [x] 스케일 레이저 점 2개 (평행 red dots)
- [x] 후방산란(렌즈 근처 입자 블룸) — 수중 실사 단서 확보
- [x] 공기 기포(상승 기포열) 미발생
- [x] 귀 지느러미 유지 (f4·f7에서 명확)

### 남은 문제 (다음 보정 목록)
1. **상부 수직 광선 기둥**: 조명=카메라 동축 지시에도 위에서 내리꽂는 빔 생성
   (금지 문구 "no light shafts from above" 무시됨). → 보정안: "the only lights are
   attached beside the camera; nothing above the scene emits or casts light" 강화,
   또는 후처리 상단 비네트로 가림.
2. **해저가 너무 밝고 청록(얕은 바다 톤)**: 심해 해저는 좁은 광원 풀 + 어두운 주변이어야
   함. → 보정안: "only a small pool of light on the seafloor directly ahead; the
   bottom fades to black beyond the beam" + 후처리 그레이딩(② 예정)으로 보정.
3. cut1 초반 하단 검은 띠 잔존(부분) → ②의 cropdetect 자동 크롭으로 처리 예정.

### 결론
- 프롬프트만으로 80% 도달. 남은 20%(광선·밝기)는 ② 후처리(그레이딩·비네트·크롭)와
  다음 유료 테스트에서 프롬프트 보정 1회로 마무리 판단.
