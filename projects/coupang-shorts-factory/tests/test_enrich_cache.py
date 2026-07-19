"""⭐ PDF 분석 캐시 회귀 검증 — "자료 업로드당 LLM 분석은 딱 1회" 원칙 (2026-07-19 사용자 확정).

CI(shorts-produce.yml)가 파이프라인 실행 **전에** 이 테스트를 돌린다. 캐시를 깨뜨리는
코드 변경이 들어오면 토큰을 쓰기 전에 워크플로우가 실패한다(재발 방지 게이트).
LLM 호출(_extract)은 카운터 스텁으로 치환하므로 API 키·네트워크가 전혀 필요 없다.

검증 항목:
  T1. 첫 실행 → 분석(LLM 호출) 정확히 1회 + 캐시 파일 생성 + 상품 정보 채움
  T2. 같은 자료로 재실행 → 분석 0회(캐시 재활용) + 결과 동일 + 히어로 이미지 재생성
  T3. 기획→대본→이미지→제작처럼 연속 5회 실행 → 분석 누적 여전히 1회
  T4. 자료 내용 변경(1바이트) → 지문 불일치 → 정확히 1회만 재분석
  T5. 자료 파일 추가 → 재분석
  T6. 빈 껍데기 캐시({}) → 일시 오류로 간주하고 재분석
  T7. 손상된 캐시(JSON 깨짐) → 크래시 없이 재분석
  T8. 상품명 없는 정상 캐시(specs만) → 재사용(직접 입력 상품에서 재분석 반복 금지)
  T9. 중복 분석 감시 장부 — 같은 지문을 2회 분석하면 캐시 파일 이력에 기록이 남는다

실행: python tests/test_enrich_cache.py  (프로젝트 루트에서)
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.product import enrich  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="enrichcache_"))
NOTES = TMP / "notes"
CACHE = TMP / "enrich"
JOB = TMP / "job"
NOTES.mkdir()
JOB.mkdir()

# 모듈 경로를 임시 폴더로 치환(실 데이터 불가침) + LLM 호출을 카운터 스텁으로 치환
enrich.NOTES_DIR = NOTES
enrich.ENRICH_CACHE_DIR = CACHE
CALLS = {"n": 0}
FAKE = {"name": "테스트 무선 청소기", "price": 129000,
        "specs": ["흡입력 25000Pa", "무게 1.5kg"], "category": "생활가전",
        "review_points": ["소음이 적다"], "product_image_indexes": [0]}
enrich._extract = lambda *a, **k: (CALLS.__setitem__("n", CALLS["n"] + 1) or dict(FAKE))

RH = "abc123def456"
(NOTES / f"{RH}.md").write_text("상품 요약 메모", encoding="utf-8")
(NOTES / f"{RH}_1.png").write_bytes(b"\x89PNG_fake_image_bytes_for_candidate")
SETTINGS = {"enrich": {"model": "claude-sonnet-4-6"}}
fails = []


def run(job=None):
    """실제 파이프라인과 같은 형태의 빈 상품(링크만 등록)으로 enrich 1회 실행."""
    return enrich.enrich_product(
        {"_row_hash": RH, "name": "", "price": 0, "specs": []}, SETTINGS, job)


def check(tid, cond, msg):
    print(f"  {'PASS' if cond else 'FAIL'}  [{tid}] {msg}")
    if not cond:
        fails.append(tid)


print("== T1: 첫 실행 — 정확히 1회 분석 + 캐시 생성 ==")
p1 = run(JOB)
check("T1", CALLS["n"] == 1, f"LLM 호출 횟수 = {CALLS['n']} (기대 1)")
cache_file = CACHE / f"{RH}.json"
check("T1", cache_file.exists(), "캐시 파일 생성됨")
check("T1", p1["name"] == "테스트 무선 청소기" and p1["price"] == 129000,
      f"상품 정보 채움: {p1['name']} / {p1['price']}")
saved = json.loads(cache_file.read_text(encoding="utf-8"))
check("T1", saved["fingerprint"] == enrich._notes_fingerprint(RH), "지문 저장 일치")

print("== T2: 같은 자료 재실행 — 분석 0회(캐시 재활용), 결과 동일 ==")
shutil.rmtree(JOB); JOB.mkdir()          # CI 재실행처럼 job 산출물은 초기화
p2 = run(JOB)
check("T2", CALLS["n"] == 1, f"LLM 호출 누적 = {CALLS['n']} (기대 1 — 재분석 없음)")
check("T2", p2["name"] == p1["name"] and p2["specs"] == p1["specs"], "결과 동일")
check("T2", len(p2["hero_images"]) == 1 and Path(p2["hero_images"][0]).exists(),
      "캐시 히트여도 히어로 이미지는 로컬 재생성됨")

print("== T3: 연속 5회 실행(기획→대본→이미지→제작 시뮬) — 총 1회 유지 ==")
for _ in range(5):
    run(JOB)
check("T3", CALLS["n"] == 1, f"5회 연속 실행 후 LLM 호출 누적 = {CALLS['n']} (기대 1)")

print("== T4: 자료 내용 변경 → 자동 재분석 정확히 1회 ==")
(NOTES / f"{RH}.md").write_text("상품 요약 메모 — 수정됨", encoding="utf-8")
run(JOB)
check("T4", CALLS["n"] == 2, f"변경 후 LLM 호출 누적 = {CALLS['n']} (기대 2)")
run(JOB)
check("T4", CALLS["n"] == 2, "변경분 재분석 후 다시 캐시 히트")

print("== T5: 자료 파일 추가 → 재분석 ==")
(NOTES / f"{RH}_2.png").write_bytes(b"\x89PNG_more_bytes")
run(JOB)
check("T5", CALLS["n"] == 3, f"파일 추가 후 LLM 호출 누적 = {CALLS['n']} (기대 3)")

print("== T6: 빈 껍데기 캐시({}) → 재분석 ==")
cache_file.write_text(json.dumps(
    {"fingerprint": enrich._notes_fingerprint(RH), "data": {}}), encoding="utf-8")
run(JOB)
check("T6", CALLS["n"] == 4, f"빈 캐시 무시하고 재분석 = {CALLS['n']} (기대 4)")

print("== T7: 손상 캐시(JSON 깨짐) → 크래시 없이 재분석 ==")
cache_file.write_text("{broken json!!", encoding="utf-8")
run(JOB)
check("T7", CALLS["n"] == 5, f"손상 캐시 복구 재분석 = {CALLS['n']} (기대 5)")

print("== T8: 상품명 없는 정상 캐시(specs만) → 재사용(재분석 반복 금지) ==")
cache_file.write_text(json.dumps({
    "fingerprint": enrich._notes_fingerprint(RH),
    "data": {"name": "", "specs": ["1000W"], "product_image_indexes": [0]}},
    ensure_ascii=False), encoding="utf-8")
p8 = enrich.enrich_product(
    {"_row_hash": RH, "name": "직접입력 상품명", "price": 9900, "specs": []}, SETTINGS, JOB)
check("T8", CALLS["n"] == 5, f"이름 없는 캐시도 재사용 = {CALLS['n']} (기대 5 — 증가 없음)")
check("T8", p8["name"] == "직접입력 상품명" and p8["specs"] == ["1000W"],
      "직접 입력 이름 유지 + 캐시 specs 채움")

print("== T9: 중복 분석 감시 장부 — 같은 지문 재분석이 이력에 남는다 ==")
# T6·T7에서 같은 지문이 여러 번 분석됐으므로 마지막 캐시 파일의 analyzed 이력으로 확인
cache_file.unlink()                      # 새로 시작
run(JOB)                                 # 분석 1회(이력 1)
cache_file2 = json.loads(cache_file.read_text(encoding="utf-8"))
check("T9", len(cache_file2.get("analyzed", [])) == 1, "정상 흐름: 분석 이력 1건")
cache_file.write_text(json.dumps(       # 데이터만 비워 재분석 유도(지문·이력은 유지)
    {**cache_file2, "data": {}}, ensure_ascii=False), encoding="utf-8")
run(JOB)                                 # 같은 지문 2번째 분석 → 경고 + 이력 2건
cache_file3 = json.loads(cache_file.read_text(encoding="utf-8"))
check("T9", len(cache_file3.get("analyzed", [])) == 2, "중복 분석이 이력에 기록됨(경고 출력)")

shutil.rmtree(TMP)
print()
if fails:
    print(f"::error::캐시 회귀 검증 실패 {len(fails)}건 → {sorted(set(fails))} — "
          "자료 업로드당 1회 분석 원칙이 깨졌습니다. 수정 전에는 파이프라인을 돌리지 마세요.")
    sys.exit(1)
print("결과: 전체 통과 — 자료가 같으면 LLM 분석은 상품당 정확히 1회만 일어난다.")
