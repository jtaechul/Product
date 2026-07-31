"""NOAA 심해탐사 **검증 완료 심해생물 클립 풀**(운영자 지시 "심해 생물 영상을 추가 확보").

출처: oceanexplorer.noaa.gov — **미 연방정부 저작물 = 퍼블릭도메인**(프로젝트 허용 라이선스).
  전량(mp4 1,563개)을 열거 → 심해 생물 클립만 추림 → **실제로 내려받아** 아래를 실측했다.
    ① 재생·해상도  ② 길이 8초 이상  ③ 움직임(watermark_qc.motion_score — 정지화면 배제)
    ④ 로고/크레딧 슬레이트 초(watermark_qc.plan)
  `slate_s`가 큰 클립은 앞뒤에 크레딧 화면이 있다는 뜻 — 제작 단계의 슬레이트 회피가 처리한다.

★종(학명) 단정 금지: NOAA가 파일에 붙인 이름은 대개 **일반명 수준**(cuskeel·chimaera 등)이라,
  여기서 학명을 임의로 붙이지 않는다(사실 날조 금지 규칙). `tags`는 NOAA 파일명이 말하는
  일반명 낱말일 뿐이며, 종 확정은 기존 종 검증 절차가 담당한다.

측정일: 2026-07-31 (커밋 기준).
"""
from __future__ import annotations

LICENSE = "public-domain"
CREDIT = "NOAA Ocean Exploration"

# tags: NOAA 파일명이 가리키는 일반명 낱말 · dur/w/h/motion/slate_s: 실측치
CLIPS: list[dict] = [
    {"tags": ['anemone'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2022/09/ex2206-dive07-my-worst-anemone-1920x1080-1.mp4",
     "source": "https://oceanexplorer.noaa.gov/multimedia/video-playlist-ex2206-worst-anemone/attachment/13840/",
     "dur": 67.4, "w": 1920, "h": 1080, "motion": 28.3, "slate_s": 0},
    {"tags": ['anemone'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2023/07/dive02-anemone-1280x720-1.mp4",
     "source": "https://oceanexplorer.noaa.gov/multimedia/okeanos-explorations-seascape-alaska-ex2304-gallery-media-dive02-anemone/attachment/15047/",
     "dur": 56.9, "w": 1280, "h": 720, "motion": 29.6, "slate_s": 0},
    {"tags": ['catshark'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2022/07/dive08-catshark-1280x720-1.mp4",
     "source": "https://oceanexplorer.noaa.gov/multimedia/okeanos-explorations-22voyage-to-the-ridge-gallery-media-dive08-catshark/attachment/13525/",
     "dur": 57.1, "w": 1280, "h": 720, "motion": 9.0, "slate_s": 0},
    {"tags": ['chimaera'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2022/07/dive08-chimaera-1280x720-1.mp4",
     "source": "https://oceanexplorer.noaa.gov/multimedia/okeanos-explorations-22voyage-to-the-ridge-gallery-media-dive08-chimaera/attachment/15983/",
     "dur": 35.9, "w": 1280, "h": 720, "motion": 11.5, "slate_s": 5},
    {"tags": ['combjelly'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2018/05/combjelly_1280x720.mp4",
     "source": "https://oceanexplorer.noaa.gov/multimedia/video-playlist-arctic-comb/attachment/16134/",
     "dur": 15.6, "w": 1280, "h": 720, "motion": 6.0, "slate_s": 0},
    {"tags": ['corals'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2022/03/corals-1920x1080-1.mp4",
     "source": "https://oceanexplorer.noaa.gov/multimedia/edu-resources-dsd-corals/attachment/16445/",
     "dur": 791.4, "w": 1920, "h": 1080, "motion": 32.5, "slate_s": 5},
    {"tags": ['crab'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2023/07/dive07-crab-eating-1280x720-1.mp4",
     "source": "https://oceanexplorer.noaa.gov/multimedia/okeanos-explorations-seascape-alaska-ex2304-gallery-media-dive07-crab-eating/attachment/16073/",
     "dur": 85.1, "w": 1280, "h": 720, "motion": 16.4, "slate_s": 0},
    {"tags": ['crab'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2021/11/dive12-crab-1280x720-1.mp4",
     "source": "https://oceanexplorer.noaa.gov/multimedia/okeanos-explorations-ex2107-gallery-media-dive12-crab/attachment/15833/",
     "dur": 39.1, "w": 1280, "h": 720, "motion": 45.7, "slate_s": 0},
    {"tags": ['cuskeel'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2021/11/dive11-cuskeel-1280x720-1.mp4",
     "source": "https://oceanexplorer.noaa.gov/multimedia/video-playlist-ex2107-eellike/attachment/15553/",
     "dur": 59.5, "w": 1280, "h": 720, "motion": 5.1, "slate_s": 21},
    {"tags": ['dumbo'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2023/04/ex2301-dive09-dumbo-1280x720-1.mp4",
     "source": "https://oceanexplorer.noaa.gov/multimedia/video-playlist-ex2301-dumbo/attachment/15175/",
     "dur": 89.4, "w": 1280, "h": 720, "motion": 14.8, "slate_s": 0},
    {"tags": ['fish'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2018/07/0701-fish-1920x1080-1.mp4",
     "source": "https://oceanexplorer.noaa.gov/multimedia/video-playlist-ex1605-first-sighting/attachment/15156/",
     "dur": 83.6, "w": 1920, "h": 1080, "motion": 26.2, "slate_s": 0},
    {"tags": ['hagfish'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2023/04/ex2301-dive01-hagfish-1280x720-1.mp4",
     "source": "https://oceanexplorer.noaa.gov/multimedia/okeanos-explorations-express-ex2301-gallery-media-ex2301-dive01-hagfish/attachment/14815/",
     "dur": 41.5, "w": 1280, "h": 720, "motion": 5.9, "slate_s": 0},
    {"tags": ['jelly'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2023/07/dive01-dinner-plate-jelly-1280x720-1.mp4",
     "source": "https://oceanexplorer.noaa.gov/multimedia/okeanos-explorations-seascape-alaska-ex2304-gallery-media-dive01-dinner-plate-jelly/attachment/15237/",
     "dur": 76.6, "w": 1280, "h": 720, "motion": 16.0, "slate_s": 39},
    {"tags": ['jelly'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2022/07/ex2205-dive02-jelly-720x480-1.mp4",
     "source": "https://oceanexplorer.noaa.gov/multimedia/okeanos-explorations-22voyage-to-the-ridge-gallery-media-ex2205-dive02-jelly/attachment/14684/",
     "dur": 42.1, "w": 720, "h": 480, "motion": 29.5, "slate_s": 5},
    {"tags": ['jelly'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2018/07/jelly-1280x720-1.mp4",
     "source": "https://oceanexplorer.noaa.gov/multimedia/video-playlist-invert-jellyfish/attachment/14318/",
     "dur": 41.3, "w": 1280, "h": 720, "motion": 11.2, "slate_s": 22},
    {"tags": ['octopus'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2023/07/dive05-octopus-1280x720-1.mp4",
     "source": "https://oceanexplorer.noaa.gov/multimedia/okeanos-explorations-seascape-alaska-ex2304-gallery-media-dive05-octopus/attachment/13734/",
     "dur": 59.3, "w": 1280, "h": 720, "motion": 13.9, "slate_s": 0},
    {"tags": ['ray'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2026/03/EX2206-ray-1920x1080-1.mp4",
     "source": "https://oceanexplorer.noaa.gov/news/fish-distribution/ex2206-ray-1920x1080/",
     "dur": 13.2, "w": 1920, "h": 1080, "motion": 12.9, "slate_s": 5},
    {"tags": ['shark'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2022/08/dive10-shark-1280x720-1.mp4",
     "source": "https://oceanexplorer.noaa.gov/multimedia/okeanos-explorations-22voyage-to-the-ridge-gallery-media-dive10-shark/attachment/13903/",
     "dur": 50.6, "w": 1280, "h": 720, "motion": 7.0, "slate_s": 43},
    {"tags": ['shark'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2021/11/dive08-shark-1280x720-1.mp4",
     "source": "https://oceanexplorer.noaa.gov/multimedia/okeanos-explorations-ex2107-gallery-media-dive08-shark/attachment/15856/",
     "dur": 26.3, "w": 1280, "h": 720, "motion": 13.4, "slate_s": 0},
    {"tags": ['snailfish'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2026/01/Seascape-Alaska-Snailfish-1920x1080_1.mp4",
     "source": "https://oceanexplorer.noaa.gov/ocean-fact/what-is-the-deepest-living-fish/seascape-alaska-snailfish-1920x1080_1/",
     "dur": 39.3, "w": 1920, "h": 1080, "motion": 36.2, "slate_s": 5},
    {"tags": ['sponge'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2024/07/sponge-video-1280x720-1.mp4",
     "source": "https://oceanexplorer.noaa.gov/multimedia/explorations-24pr-usvi-biotech-gallery-media-sponge-video/attachment/13990/",
     "dur": 190.0, "w": 1280, "h": 720, "motion": 15.2, "slate_s": 0},
    {"tags": ['sponge'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2018/05/sponge-1280x720-1.mp4",
     "source": "https://oceanexplorer.noaa.gov/multimedia/video-playlist-ex1708-giant-sponge/attachment/14691/",
     "dur": 84.4, "w": 1280, "h": 720, "motion": 7.9, "slate_s": 21},
    {"tags": ['sponge'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2019/09/sponge-a-palooza-1920x1080-1.mp4",
     "source": "https://oceanexplorer.noaa.gov/multimedia/video-playlist-canyon-spongeapalooza/attachment/14567/",
     "dur": 74.8, "w": 1280, "h": 720, "motion": 8.9, "slate_s": 0},
    {"tags": ['sponge'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2021/11/dive07-sponge-heaven-1280x720-1.mp4",
     "source": "https://oceanexplorer.noaa.gov/multimedia/video-playlist-ex2107-spongeheaven/attachment/15085/",
     "dur": 64.9, "w": 1280, "h": 720, "motion": 7.7, "slate_s": 10},
    {"tags": ['squid'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2023/07/dive01-glass-squid-1280x720-1.mp4",
     "source": "https://oceanexplorer.noaa.gov/multimedia/video-playlist-ex2304-glass-squid/attachment/14474/",
     "dur": 68.2, "w": 1280, "h": 720, "motion": 3.6, "slate_s": 50},
    {"tags": ['squid'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2021/11/dive08-squid-1280x720-1.mp4",
     "source": "https://oceanexplorer.noaa.gov/multimedia/okeanos-explorations-ex2107-gallery-media-dive08-squid/attachment/13476/",
     "dur": 54.5, "w": 1280, "h": 720, "motion": 6.1, "slate_s": 0},
    {"tags": ['starfish'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2019/07/starfish-1920x1080-1.mp4",
     "source": "https://oceanexplorer.noaa.gov/multimedia/okeanos-explorations-ex1903-dailyupdates-june29-media-starfish/attachment/14042/",
     "dur": 83.7, "w": 1280, "h": 720, "motion": 25.7, "slate_s": 0},
    {"tags": ['tapirfish'], "url": "https://oceanexplorer.noaa.gov/wp-content/uploads/2021/11/dive11-tapirfish-1280x720-1.mp4",
     "source": "https://oceanexplorer.noaa.gov/multimedia/okeanos-explorations-ex2107-gallery-media-dive11-tapirfish/attachment/15226/",
     "dur": 59.5, "w": 1280, "h": 720, "motion": 9.0, "slate_s": 26},
]


def find(*names: str) -> list[dict]:
    """일반명 낱말(예: "dumbo octopus", "hagfish")로 검증된 클립을 찾는다.

    ★일반적인 낱말은 매칭에서 제외한다(운영자 품질 규칙): "fish"·"coral" 같은 말은 거의 모든
      종 이름에 들어 있어, 그대로 두면 **무관한 종에 엉뚱한 영상**이 붙는다(실제로 테스트에서
      가상의 'test fish'가 NOAA의 일반 어류 클립을 물어 왔다). 구체적인 이름만 매칭한다.
    반환 순서: 움직임 큰 것 → 긴 것.
    """
    GENERIC = {"fish", "coral", "corals", "star", "video"}
    want = {w for n in names
            for w in str(n or "").lower().replace("-", " ").replace(".", " ").split()
            if w and w not in GENERIC and len(w) >= 4}
    if not want:
        return []

    def hit(tag: str) -> bool:
        if tag in GENERIC:
            return False
        return any(tag == w or (len(tag) >= 5 and len(w) >= 5 and (tag in w or w in tag))
                   for w in want)

    got = [c for c in CLIPS if any(hit(t) for t in c["tags"])]
    return sorted(got, key=lambda c: (-c["motion"], -c["dur"]))
