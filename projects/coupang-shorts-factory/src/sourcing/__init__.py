"""소싱 엔진 패키지 (미래마켓 개조 SSOT §6·§11).

- models: SourceVideo·Project·Clip 데이터 모델 + JSON 영속화(data/sources/)
- base: SourceAdapter 추상 인터페이스 + 어댑터 레지스트리(§6.2 — 차단·구조변경 대비 분리)
- manual_seed: 반자동(운영자 시드) 어댑터 (§6.3)

⚠️ 개조 단계 산출물 — 기존 제작 경로(src/pipeline.py 등)는 아직 이 패키지를 쓰지 않는다
(SSOT §0·§14.9: 새 경로 검증 전까지 옛 경로 유지, 제거는 맨 마지막).
"""
