# 🌟 SPOTLIGHT

웹 2D 배우 육성 시뮬레이션 (우마무스메식 턴제 육성 · 모바일 세로 우선).

> **이 폴더가 SPOTLIGHT 프로젝트의 집입니다.** 모든 SPOTLIGHT 코드·아트는 이 `spotlight/` 안에만 저장.

- 전체 기획서·개발 규칙: 저장소 루트 **`CLAUDE.md`** 참고
- 배포 URL(GitHub Pages): https://jtaechul.github.io/Product/spotlight/

## 기술 방식 (기획서 #4)

- **렌더링**: PixiJS (GPU/WebGL) — `vendor/pixi.min.mjs` 로컬 로드
- **빌드 없음**: 순수 ES 모듈. GitHub Pages가 소스를 그대로 서빙 → 빌드/번들 단계 불필요
- **아트**: 고퀄 **래스터 일러스트(PNG)** 를 PixiJS Sprite로 조립 (SVG 손그림 ❌)
- **앱화(후반)**: Capacitor로 정적 사이트를 iOS/Android 앱으로 포장

## 로컬 실행 (빌드 불필요)

```bash
cd spotlight
python3 -m http.server 8000
# 브라우저: http://localhost:8000/  (모바일 세로 기준 확인)
```

## 폴더 구조

```
spotlight/
├── index.html        # importmap으로 vendor/pixi 로드 + src/main.js
├── vendor/pixi.min.mjs
├── assets/           # 래스터 아트(PNG): mockups, portraits, bg, sfx ...
└── src/
    ├── main.js       # PixiJS 부트스트랩
    ├── config.js     # 상수 + 디자인 토큰
    ├── core/         # SceneManager(9:16 스케일), Scene 베이스
    └── scenes/       # MainScene (이후 Create/Production/Ending 추가)
```
