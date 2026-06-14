# 🌟 SPOTLIGHT

웹 2D 배우 육성 시뮬레이션 (우마무스메식 턴제 육성 · 모바일 세로 우선).

> **이 폴더가 SPOTLIGHT 프로젝트의 집입니다.** 앞으로 모든 SPOTLIGHT 관련 코드·에셋은
> 이 `spotlight/` 폴더 안에만 저장합니다. (루트의 다른 게임들과 분리)

- 전체 기획서·개발 규칙: 저장소 루트 **`CLAUDE.md`** 참고
- 배포 URL(GitHub Pages): https://jtaechul.github.io/Product/spotlight/

## 기술 스택 (기획서 #4)

- **렌더링**: PixiJS (WebGL/WebGPU) — DOM이 아닌 GPU로 그려 끊김 없는 애니
- **캐릭터 애니**: Live2D Cubism(메인) + Rive(전환·이펙트)
- **언어/빌드**: TypeScript + Vite
- **앱 패키징**: Capacitor (iOS/Android 네이티브 앱 + 웹 동시)
- **사운드**: Howler.js

## 로컬 실행

```bash
cd spotlight
npm install      # 최초 1회 (의존성 설치)
npm run dev      # 개발 서버 → 안내된 localhost 주소를 브라우저로 열기
```

빌드/미리보기:

```bash
npm run build    # dist/ 생성 (타입 체크 포함)
npm run preview  # 빌드 결과 미리보기
```

## 폴더 구조 (기획서 #19)

```
spotlight/
├── index.html            # Vite 엔트리 (canvas 마운트)
├── package.json / tsconfig.json / vite.config.ts / capacitor.config.ts
├── public/assets/        # 정적 에셋 (portraits, live2d, rive, bg, sfx ...)
└── src/
    ├── main.ts           # PixiJS 부트스트랩
    ├── config.ts         # 상수 + 디자인 토큰
    ├── core/             # SceneManager, Scene 베이스
    ├── scenes/           # 화면 단위 (Title, Create, Main, Production, Ending)
    ├── systems/          # 게임 로직 (stats, schedule, production ...)
    ├── anim/             # Live2D/Rive 캐릭터 제어
    ├── ui/               # HUD, 공용 컴포넌트
    └── data/             # 수치 데이터 (활동·매체·이벤트·엔딩)
```
