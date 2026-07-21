# 영상 소싱 인벤토리 (영상+이미지 vs 이미지전용)

> 각 후보를 실제 제작 경로(`footage.fetch_footage`)로 굴려 **영상 확보 여부**로 분류.
> - **영상+이미지 확보**: 실사 영상이 잡히는 소스(→ `*_candidates.json`, 자동 제작 풀).
> - **이미지전용(영상 없음)**: 영상이 없어 사진 다큐로만 제작 → **별도 보관**(`*_image_only.json`), 자동 제작 풀에서 제외.
> - 분류·게이트: `_commons_search`(피사체 검증) + `_commons_category_videos`(분류군 카테고리) + NOAA OER + Internet Archive.


## 심해생물 (deep_sea) — 영상 8 · 이미지전용 15

### ✅ 영상+이미지 확보 (자동 제작 풀)

| # | 대상(key) | 영상 소스 | 비고 |
|---|---|---|---|
| 1 | riftia pachyptila | NOAA OER EX1711 DIVE13 (https://www.ncei.noaa.gov/metadata/g |  |
| 2 | chiridota heheva | NOAA OER EX1711 DIVE10 (https://www.ncei.noaa.gov/metadata/g |  |
| 3 | thalassocalyce | NOAA OER EX1708 DIVE11 (https://www.ncei.noaa.gov/metadata/g |  |
| 4 | bathynomus | File:Bathynomus giganteus.webm |  |
| 5 | ipnopidae | NOAA OER EX1711 DIVE01 (https://www.ncei.noaa.gov/metadata/g |  |
| 6 | chaunax stigmaeus | NOAA OER EX1711 DIVE15 (https://www.ncei.noaa.gov/metadata/g |  |
| 7 | macrouridae | File:Ex1402-dive11 fish.webm |  |
| 8 | coelorinchus caelorhincus | NOAA OER EX1803 DIVE15 (https://www.ncei.noaa.gov/metadata/g |  |

### 📷 이미지전용 · 영상 없음 (별도 보관)

| # | 대상(key) | 확보 사진 | 비고 |
|---|---|---|---|
| 1 | annelida | File:Earthworm movin | 영상 후보가 오소싱(문맥부적합) → 영상 제외, 사진만 보관 |
| 2 | holothuroidea | 7장 |  |
| 3 | actinopyga echinites | 7장 |  |
| 4 | eurypharynx pelecanoides | 7장 |  |
| 5 | anoplogaster cornuta | 5장 |  |
| 6 | scotoplanes globosa | 7장 |  |
| 7 | kiwa hirsuta | 7장 |  |
| 8 | diaphus effulgens | 7장 |  |
| 9 | chilara taylori | 7장 |  |
| 10 | electrona risso | 5장 |  |
| 11 | coryphaenoides rupestris | 7장 |  |
| 12 | chiasmodon niger | 7장 |  |
| 13 | opisthoproctus soleatus | 7장 |  |
| 14 | rimicaris | 7장 |  |
| 15 | macrocheira kaempferi | 7장 |  |

## 해양생물 (marine_life) — 영상 18 · 이미지전용 8

### ✅ 영상+이미지 확보 (자동 제작 풀)

| # | 대상(key) | 영상 소스 | 비고 |
|---|---|---|---|
| 1 | bolbometopon muricatum | File:Extraordinary-Aggressive-Behavior-from-the-Giant-Coral- | 피사체 수동확인 필요(논문/일반 클립 가능성) |
| 2 | bryaninops natans | File:Red-fluorescence-in-reef-fish - 1472-6785-8-16-S2.ogv | 피사체 수동확인 필요(논문/일반 클립 가능성) |
| 3 | enneapterygius destai | File:Red-fluorescence-in-reef-fish-A-novel-signalling-mechan | 피사체 수동확인 필요(논문/일반 클립 가능성) |
| 4 | nudibranchia | File:Spanish dancer nudibranch.webm |  |
| 5 | carcharodon carcharias | File:Cage diving with a great white shark.webm |  |
| 6 | sepia mestus | File:Red cuttle hunting.webm |  |
| 7 | carcharhinus melanopterus | File:Aerial view of a blacktip reef shark (Carcharhinus mela |  |
| 8 | rhinoptera bonasus | File:Cownose rays (Rhinoptera bonasus) Shark Reef Aquarium.w |  |
| 9 | carcharhinus amblyrhynchos | File:Grey reef shark (Carcharhinus amblyrhynchos) near Sipad |  |
| 10 | triaenodon obesus | File:School of whitetip reef sharks (Triaenodon obesus).webm |  |
| 11 | carcharhinus perezi | File:Feeding Caribbean reef sharks.webm |  |
| 12 | carcharias taurus | File:Requin taureau (Carcharias taurus), requin nourrice (Gi |  |
| 13 | nebrius ferrugineus | File:Tawny nurse sharks (Nebrius ferrugineus).webm |  |
| 14 | triakis semifasciata | File:Leopard shark (Triakis semifasciata).webm |  |
| 15 | lithodinae | File:King crab eating a brittle star.webm |  |
| 16 | anoplodactylus lentus | File:Sea Spiders.webm |  |
| 17 | astomonema | File:Astomonema 1 cliponly.webm |  |
| 18 | phallodrilinae | File:Gutless tmp cliponly.webm |  |

### 📷 이미지전용 · 영상 없음 (별도 보관)

| # | 대상(key) | 확보 사진 | 비고 |
|---|---|---|---|
| 1 | alopias pelagicus | 7장 |  |
| 2 | rhincodon typus | 7장 |  |
| 3 | carcharhinus limbatus | 7장 |  |
| 4 | sphyrnidae | 7장 |  |
| 5 | sardinops sagax | 7장 |  |
| 6 | diadumene cincta | 5장 |  |
| 7 | ophiothrix fragilis | 7장 |  |
| 8 | artemia salina | 7장 |  |

## ⚠️ 제작 불가(영상 오소싱 제거 후 사진 4장 미만) — 목록에서 제외

- marine_life: `lingulodinium polyedra` (영상=서핑 클립 오소싱 제거 → 사진 부족)


## 🔎 피사체 수동확인 필요(영상은 있으나 논문/일반 클립 의심)

- `bryaninops natans`·`enneapterygius destai`: 동일 논문 클립(Red-fluorescence-in-reef-fish) 공유 → 종 특정 불확실
- `bolbometopon muricatum`: 제목이 다른 어종(Giant Coral Grouper) 언급 → 확인 권장
- (격리 완료) `annelida`: 영상 후보가 육상 지렁이 + 문(phylum) 과다광범 → 이미지전용으로 이동

---
**합계: 영상 26 · 이미지전용 23 (총 49)**
