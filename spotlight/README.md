# 🌟 SPOTLIGHT

웹 2D 배우 육성 시뮬레이션 (우마무스메식 턴제 육성 · 모바일 세로 우선).

> **이 폴더가 SPOTLIGHT 프로젝트의 집입니다.** 앞으로 모든 SPOTLIGHT 관련 코드·에셋은
> 이 `spotlight/` 폴더 안에만 저장합니다. (루트의 다른 게임들과 분리)

- 전체 기획서·개발 규칙: 저장소 루트 **`CLAUDE.md`** 참고
- 배포 URL(GitHub Pages): https://jtaechul.github.io/Product/spotlight/

## 로컬 실행

저장소 루트에서:

```bash
python3 -m http.server 8000
```

브라우저에서 `http://localhost:8000/spotlight/` 열기. (모바일 세로 화면 기준으로 확인)

## 폴더 구조 (기획서 19번)

```
spotlight/
├── index.html      # 게임 셸 (세로 레이아웃)
├── style.css       # 디자인 시스템 / 세로 레이아웃
├── js/
│   ├── main.js     # 게임 루프 / 턴 / 난이도
│   └── data/       # 활동·매체·이벤트·엔딩 등 데이터 (수치 분리)
└── assets/
    ├── portraits/  # 주인공 디자인 시트 (브라운/레드 2종)
    ├── manager/  rivals/  bg/  endings/  sfx/  lottie/
```
