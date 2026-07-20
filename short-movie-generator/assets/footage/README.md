# 운영자 수동 영상 드롭 폴더

NOAA Ocean Explorer 포털·유튜브 등 **자동 소싱이 안 되는 풍부한 공개영상(PD)** 을 직접 받아
여기에 넣으면, 그 종 쇼츠를 만들 때 **이 클립을 최우선으로** 사용합니다(자동 커먼스 소싱보다 먼저).

## 넣는 방법

1. 파일명 = **그 종의 학명(소문자, 공백은 `_`)** + 확장자.
   - 예) 아귀 `Melanocetus johnsonii` → `melanocetus_johnsonii.mp4`
   - 확장자: `.mp4` `.webm` `.mov` `.mkv` `.m4v`
2. 이 폴더(`short-movie-generator/assets/footage/`)에 넣고 커밋.
3. (선택) 저작자 표기가 필요하면 같은 이름의 `<학명>.credit.txt` 를 함께 넣으세요.
   - 예) `melanocetus_johnsonii.credit.txt` 안에 `NOAA Ocean Exploration`
   - 없으면 캡션 크레딧은 일반 `Public Domain`으로 표기됩니다.

## 라이선스 주의 (필수 · 수익화 채널)

- **퍼블릭 도메인(PD) 또는 상업 이용 허용** 영상만 넣으세요.
  - NOAA Ocean Exploration 영상 = 미국 정부 저작물 = **PD** (안전 · 크레딧은 NOAA로).
  - 유튜브 영상은 "PD"라 적혀 있어도 재업로드가 위험할 수 있으니, **원 제작자가 NOAA/정부/CC0** 인
    것만 쓰세요.
- 넣은 영상은 자동으로 9:16 크롭·워터마크 제거·정지영상 게이트를 거칩니다(로고·URL은 자동 제거 시도).

## 왜 이 방식인가 (자동화 한계)

NOAA NCEI 비디오 포털은 공개 API가 없어(검색폼→ZIP/이메일) 자동 소싱이 불가능하고,
Internet Archive엔 NOAA 공식 컬렉션이 없습니다(유튜브 미러·무관 영상뿐). 그래서 **손으로 고른
좋은 PD 클립을 드롭하는 이 경로가 가장 확실**합니다. 자동 소싱(커먼스)은 그대로 병행됩니다.
