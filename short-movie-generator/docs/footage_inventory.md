# 영상 소싱 인벤토리 (영상+이미지 vs 이미지전용)

> 각 후보를 실제 제작 경로(`footage.fetch_footage`)로 굴려 **영상 확보 여부**로 분류.
> - **영상+이미지 확보**: 실사 영상 확보(→ `*_candidates.json`, 자동 제작 풀). 찾은 영상 URL은 `_video_cache.json`에 캐시돼 제작 때 그대로 재사용(분류=제작 일치).
> - **이미지전용(영상 없음)**: 영상이 없어 사진 다큐로만 → **별도 보관**(`*_image_only.json`), 자동 풀 제외.


## 심해생물 (deep_sea) — 영상 7 · 이미지전용 15

### ✅ 영상+이미지 확보 (자동 제작 풀)

| # | 대상(key) | 영상 소스 |
|---|---|---|
| 1 | riftia pachyptila | NOAA OER EX1711 DIVE13 (https://www.ncei.noaa.gov/metadata/granule/geo |
| 2 | chiridota heheva | NOAA OER EX1711 DIVE10 (https://www.ncei.noaa.gov/metadata/granule/geo |
| 3 | thalassocalyce | NOAA OER EX1708 DIVE11 (https://www.ncei.noaa.gov/metadata/granule/geo |
| 4 | bathynomus | File:Bathynomus giganteus.webm |
| 5 | ipnopidae | NOAA OER EX1711 DIVE01 (https://www.ncei.noaa.gov/metadata/granule/geo |
| 6 | macrouridae | File:Ex1402-dive11 fish.webm |
| 7 | coelorinchus caelorhincus | NOAA OER EX1803 DIVE15 (https://www.ncei.noaa.gov/metadata/granule/geo |

### 📷 이미지전용 · 영상 없음 (별도 보관)

| # | 대상(key) | 사진 | 비고 |
|---|---|---|---|
| 1 | annelida | - | 오소싱(육상 지렁이·문 과다광범) 격리 |
| 2 | holothuroidea | 7장 | 영상 미확보(검색 3회 실패)→이미지전용 |
| 3 | actinopyga echinites | 7장 | 영상 미확보(검색 3회 실패)→이미지전용 |
| 4 | eurypharynx pelecanoides | 7장 | 영상 미확보(검색 3회 실패)→이미지전용 |
| 5 | anoplogaster cornuta | 5장 | 영상 미확보(검색 3회 실패)→이미지전용 |
| 6 | scotoplanes globosa | 7장 | 영상 미확보(검색 3회 실패)→이미지전용 |
| 7 | kiwa hirsuta | 7장 | 영상 미확보(검색 3회 실패)→이미지전용 |
| 8 | diaphus effulgens | 7장 | 영상 미확보(검색 3회 실패)→이미지전용 |
| 9 | chilara taylori | 7장 | 영상 미확보(검색 3회 실패)→이미지전용 |
| 10 | electrona risso | 5장 | 영상 미확보(검색 3회 실패)→이미지전용 |
| 11 | coryphaenoides rupestris | 7장 | 영상 미확보(검색 3회 실패)→이미지전용 |
| 12 | chiasmodon niger | 7장 | 영상 미확보(검색 3회 실패)→이미지전용 |
| 13 | opisthoproctus soleatus | 7장 | 영상 미확보(검색 3회 실패)→이미지전용 |
| 14 | rimicaris | 7장 | 영상 미확보(검색 3회 실패)→이미지전용 |
| 15 | macrocheira kaempferi | 7장 | 영상 미확보(검색 3회 실패)→이미지전용 |

## 해양생물 (marine_life) — 영상 15 · 이미지전용 11

### ✅ 영상+이미지 확보 (자동 제작 풀)

| # | 대상(key) | 영상 소스 |
|---|---|---|
| 1 | nudibranchia | File:Spanish dancer nudibranch.webm |
| 2 | carcharodon carcharias | File:Cage diving with a great white shark.webm |
| 3 | sepia mestus | File:Red cuttle hunting.webm |
| 4 | carcharhinus melanopterus | File:Aerial view of a blacktip reef shark (Carcharhinus melanopterus)  |
| 5 | rhinoptera bonasus | File:Cownose rays (Rhinoptera bonasus) Shark Reef Aquarium.webm |
| 6 | carcharhinus amblyrhynchos | File:Grey reef shark (Carcharhinus amblyrhynchos) near Sipadan.webm |
| 7 | triaenodon obesus | File:School of whitetip reef sharks (Triaenodon obesus).webm |
| 8 | carcharhinus perezi | File:Feeding Caribbean reef sharks.webm |
| 9 | carcharias taurus | File:Requin taureau (Carcharias taurus), requin nourrice (Ginglymostom |
| 10 | nebrius ferrugineus | File:Tawny nurse sharks (Nebrius ferrugineus).webm |
| 11 | triakis semifasciata | File:Leopard shark (Triakis semifasciata).webm |
| 12 | lithodinae | File:King crab eating a brittle star.webm |
| 13 | anoplodactylus lentus | File:Sea Spiders.webm |
| 14 | astomonema | File:Astomonema 1 cliponly.webm |
| 15 | phallodrilinae | File:Gutless tmp cliponly.webm |

### 📷 이미지전용 · 영상 없음 (별도 보관)

| # | 대상(key) | 사진 | 비고 |
|---|---|---|---|
| 1 | bolbometopon muricatum | - | 제목상 다른 어종(grouper) 의심 격리 |
| 2 | bryaninops natans | - | 동일 논문 일반 클립 공유 격리 |
| 3 | enneapterygius destai | - | 동일 논문 일반 클립 공유 격리 |
| 4 | alopias pelagicus | 7장 | 영상 미확보(검색 3회 실패)→이미지전용 |
| 5 | rhincodon typus | 7장 | 영상 미확보(검색 3회 실패)→이미지전용 |
| 6 | carcharhinus limbatus | 7장 | 영상 미확보(검색 3회 실패)→이미지전용 |
| 7 | sphyrnidae | 7장 | 영상 미확보(검색 3회 실패)→이미지전용 |
| 8 | sardinops sagax | 7장 | 영상 미확보(검색 3회 실패)→이미지전용 |
| 9 | diadumene cincta | 5장 | 영상 미확보(검색 3회 실패)→이미지전용 |
| 10 | ophiothrix fragilis | 7장 | 영상 미확보(검색 3회 실패)→이미지전용 |
| 11 | artemia salina | 7장 | 영상 미확보(검색 3회 실패)→이미지전용 |

---
**합계: 영상 22 · 이미지전용 26 (총 48)**  ·  영상 URL 캐시: 22종
