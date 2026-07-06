"""
veo_lite_rov_test.py
심해 릴스 파이프라인 - 시각화 모듈 실측 (Veo 3.1 Lite, ROV 탐사정 룩)

목적: NOAA 퍼블릭도메인 이미지를 Veo 3.1 Lite로 9:16 영상 3컷 생성해
      "저화질 무인탐사정(ROV) 느낌 + 사실형"이 콘셉트에 맞는지 실측

사전 준비:
  1) pip install google-genai
  2) export GEMINI_API_KEY="발급받은키"   (하드코딩 금지)
  3) NOAA 이미지를 dumbo.jpg 로 저장, 이 파일과 같은 폴더에 둘 것
  4) python veo_lite_rov_test.py

비용: Lite 약 $0.05~0.08/초 x 8초 x 3컷 = 릴스당 약 $1.2~1.9 (성공분만 과금)
주의: 생성 영상은 Google 서버에 2일만 보관 -> 스크립트가 즉시 로컬 저장
"""

import os
import time
import pathlib
from google import genai
from google.genai import types

# ---- 설정 ----
MODEL = "veo-3.1-lite-generate-preview"   # Veo 3.1 Lite (유료 프리뷰)
IMAGE_PATH = "dumbo.jpg"                    # NOAA에서 받은 이미지 파일명
IMAGE_MIME = "image/jpeg"

# 형태 왜곡 방지용 네거티브 프롬프트 (텍스트/워터마크/사람은 후처리에서만)
NEGATIVE = "extra limbs, deformed anatomy, morphing, text, HUD, watermark, human, diver, treasure"

# ROV(무인 원격조종 잠수정) 룩 3컷. 연출은 과감히, 생물 형태·행동은 실제만.
# * 먼저 1컷만 테스트하려면 아래 딕셔너리에서 원치 않는 항목을 주석 처리하세요.
PROMPTS = {
    "cut1_discovery": (
        "POV footage from a deep-sea ROV (remotely operated vehicle) exploring the pitch-black abyss. "
        "A hard floodlight beam sweeps through turbid blue-green water thick with marine snow, and a "
        "dumbo octopus with large ear-like fins slowly emerges from the darkness into the light. "
        "The camera drifts and shakes subtly like an underwater vehicle, slowly approaching. "
        "Murky low-light underwater look with faint video noise and compression artifacts, not overly sharp. "
        "Keep the octopus's exact shape, proportions, and number of fins and arms unchanged; do not distort or add features. "
        "Suspenseful deep-sea discovery mood. Vertical 9:16."
    ),
    "cut2_behavior": (
        "Deep-sea ROV footage tracking a dumbo octopus as it propels itself through the dark water by "
        "flapping its large ear-like fins like wings, webbed arms trailing beneath. Hard floodlight from "
        "the vehicle lights the creature against total blackness; marine snow streaks past the lens. "
        "Subtle camera drift and vibration of an underwater vehicle. Murky, slightly noisy low-light "
        "camera look, not overly sharp. "
        "Keep the octopus's exact shape, proportions, and number of fins and arms unchanged; do not distort or add features. "
        "Immersive deep-sea exploration mood. Vertical 9:16."
    ),
    "cut3_detail": (
        "Deep-sea ROV camera slowly closing in on a dumbo octopus near the seafloor, its webbed arms and "
        "fine texture revealed under the vehicle's floodlight in murky blue-green water. Faint suspended "
        "particles drift through the beam. Subtle vehicle camera shake, shallow murky low-light look with "
        "light video noise, not overly sharp. "
        "Keep the octopus's exact shape, proportions, and number of arms unchanged; do not distort or add features. "
        "Intimate, mysterious deep-sea mood. Vertical 9:16."
    ),
}


def main():
    # API 키는 환경변수 GEMINI_API_KEY 자동 인식
    client = genai.Client()
    # 자동 인식 안 되면 위 줄 대신: client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    if not pathlib.Path(IMAGE_PATH).exists():
        raise SystemExit(f"[에러] 이미지 파일이 없습니다: {IMAGE_PATH} (NOAA 이미지를 이 이름으로 저장하세요)")

    img_bytes = pathlib.Path(IMAGE_PATH).read_bytes()

    for name, prompt in PROMPTS.items():
        print(f"\n[생성 시작] {name}")
        try:
            operation = client.models.generate_videos(
                model=MODEL,
                prompt=prompt,
                image=types.Image(image_bytes=img_bytes, mime_type=IMAGE_MIME),
                config=types.GenerateVideosConfig(
                    aspect_ratio="9:16",
                    resolution="720p",
                    duration_seconds=8,
                    number_of_videos=1,
                    negative_prompt=NEGATIVE,
                    generate_audio=False,   # 앰비언트는 후처리 -> 오디오 끔(비용 절감). Lite가 거부하면 이 줄 삭제
                ),
            )

            # 비동기 작업: 완료까지 폴링
            while not operation.done:
                print("  ...영상 생성 대기 중")
                time.sleep(10)
                operation = client.operations.get(operation)

            # SDK 버전에 따라 .response 또는 .result 일 수 있음
            resp = getattr(operation, "response", None) or getattr(operation, "result", None)
            video = resp.generated_videos[0].video

            out = f"{name}.mp4"
            client.files.download(file=video)   # 서버에서 내려받기
            video.save(out)                      # 로컬 저장 (대안: client.files.download(file=video, download_path=out))
            print(f"[완료] 저장됨 -> {out}")

        except Exception as e:
            print(f"[실패] {name}: {e}")

    print("\n전체 완료. 3개 클립을 확인하세요.")
    print("이어붙이기(FFmpeg concat)와 자막/워터마크 오버레이는 다음 단계입니다.")


if __name__ == "__main__":
    main()
