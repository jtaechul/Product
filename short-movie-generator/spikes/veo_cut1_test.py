"""
veo_cut1_test.py
심해 릴스 파이프라인 - 시각화 모듈 실측 (Veo 3.1 Lite) / cut1 한 컷만

목적: NOAA 퍼블릭도메인 이미지 1장을 Veo 3.1 Lite로 9:16 영상 1컷(cut1_discovery)
      생성해 ① API 접근 성공 여부 ② 실제 소요시간 ③ 실측 비용을 확인.
      (spec.md 16장 1순위 미결정 = "Veo 프로그램적 접근·비용" 검증용)

사전 준비:
  1) .venv 에 google-genai, python-dotenv 설치됨
  2) 이 폴더 상위(short-movie-generator/)의 .env 에 GEMINI_API_KEY=... 채움
  3) NOAA 덤보문어 퍼블릭도메인 이미지를 이 파일과 같은 폴더에 dumbo.jpg 로 저장
  4) ../.venv/bin/python veo_cut1_test.py

오디오 주의: 심해 앰비언트 사운드는 '필수'지만, 이 raw 클립 단계에서는 넣지 않는다.
  → generate_audio=False (Veo 네이티브 오디오 끔, 비용 절감). 심해 앰비언트는 후처리
    audio 모듈에서 FFmpeg로 로열티프리 심해음을 레이어링해 최종 영상에 반드시 포함한다.
비용: Lite 오디오 off 약 $0.03~0.08/초. 8초 1컷 ≈ 약 $0.24~0.65 (성공분만 과금).
주의: 생성 영상은 Google 서버에 2일만 보관 -> 스크립트가 즉시 로컬 저장.
"""

import os
import time
import pathlib
from dotenv import load_dotenv
from google import genai
from google.genai import types

# 상위 폴더의 .env 로드 (GEMINI_API_KEY)
HERE = pathlib.Path(__file__).resolve().parent
load_dotenv(HERE.parent / ".env")

# ---- 설정 ----
MODEL = "veo-3.1-lite-generate-preview"   # Veo 3.1 Lite (유료 프리뷰)
IMAGE_PATH = HERE / "dumbo.jpg"            # NOAA에서 받은 이미지 (이 폴더에 둘 것)
IMAGE_MIME = "image/jpeg"
DURATION_S = 8
# 실측 비용 추정용 단가 범위 ($/초, Lite 오디오 off 기준) — 실제 청구는 콘솔에서 확정
RATE_LO, RATE_HI = 0.03, 0.08

NEGATIVE = "extra limbs, deformed anatomy, morphing, text, HUD, watermark, human, diver, treasure"

# cut1 (discovery/발견) 한 컷만.
CUT1_PROMPT = (
    "POV footage from a deep-sea ROV (remotely operated vehicle) exploring the pitch-black abyss. "
    "A hard floodlight beam sweeps through turbid blue-green water thick with marine snow, and a "
    "dumbo octopus with large ear-like fins slowly emerges from the darkness into the light. "
    "The camera drifts and shakes subtly like an underwater vehicle, slowly approaching. "
    "Murky low-light underwater look with faint video noise and compression artifacts, not overly sharp. "
    "Keep the octopus's exact shape, proportions, and number of fins and arms unchanged; do not distort or add features. "
    "Suspenseful deep-sea discovery mood. Vertical 9:16."
)


def main():
    if not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit("[에러] GEMINI_API_KEY 없음 → short-movie-generator/.env 에 키를 채우세요.")
    if not IMAGE_PATH.exists():
        raise SystemExit(f"[에러] 입력 이미지 없음: {IMAGE_PATH}  (NOAA 덤보문어 이미지를 dumbo.jpg 로 저장)")

    client = genai.Client()
    img_bytes = IMAGE_PATH.read_bytes()

    print(f"[생성 시작] cut1_discovery  (model={MODEL}, {DURATION_S}s, 9:16, audio=off)")
    t0 = time.time()
    try:
        operation = client.models.generate_videos(
            model=MODEL,
            prompt=CUT1_PROMPT,
            image=types.Image(image_bytes=img_bytes, mime_type=IMAGE_MIME),
            config=types.GenerateVideosConfig(
                aspect_ratio="9:16",
                resolution="720p",
                duration_seconds=DURATION_S,
                number_of_videos=1,
                negative_prompt=NEGATIVE,
                generate_audio=False,  # 심해 앰비언트는 후처리에서 레이어링(필수). Lite가 거부하면 이 줄 삭제
            ),
        )

        while not operation.done:
            print(f"  ...영상 생성 대기 중 ({int(time.time() - t0)}s 경과)")
            time.sleep(10)
            operation = client.operations.get(operation)

        resp = getattr(operation, "response", None) or getattr(operation, "result", None)
        video = resp.generated_videos[0].video

        out = HERE / "cut1_discovery.mp4"
        client.files.download(file=video)
        video.save(str(out))
        elapsed = time.time() - t0

        print(f"\n[완료] 저장됨 -> {out}")
        print(f"[소요시간] {elapsed:.0f}초")
        print(f"[실측 비용(추정)] {DURATION_S}s × ${RATE_LO}~${RATE_HI}/s "
              f"= 약 ${DURATION_S*RATE_LO:.2f}~${DURATION_S*RATE_HI:.2f} "
              f"(정확한 청구액은 Google AI Studio/Cloud 콘솔에서 확인)")

    except Exception as e:
        print(f"[실패] cut1: {e}")
        raise


if __name__ == "__main__":
    main()
