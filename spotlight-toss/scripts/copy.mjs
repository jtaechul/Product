// 빌드 = 정적 복사. SPOTLIGHT는 빌드 없는 순수 정적 사이트라서(기획서 4번)
// ../spotlight 폴더를 dist/로 그대로 복사하는 것이 곧 빌드다.
// 단, 게임이 런타임에 읽지 않는 파일(디자인 시트·목업·문서·미사용 폰트·서비스워커)은
// 패키지 용량을 줄이기 위해 제외한다. (저장소의 spotlight/ 원본은 그대로 유지)
import { cpSync, rmSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const src = path.resolve(here, "../../spotlight");
const out = path.resolve(here, "../dist");

// 제외 규칙: 경로에 이 문자열이 포함되면 복사하지 않는다
const EXCLUDE = [
  "/sw.js",                    // GitHub Pages 캐시 대응용 — 토스 WebView에선 불필요
  "/assets/mockups",           // 디자인 목표 시안 (런타임 미사용)
  "/assets/live2d",            // 후반 예정 폴더 (비어 있음)
  "/assets/rive",              // 후반 예정 폴더 (비어 있음)
  "heroine_design_sheet",      // 주인공 디자인 시트 (레퍼런스)
  "heroine_sprite_sheet",      // 스프라이트 시트 원본 (레퍼런스)
  "/assets/portraits/expressions", // 미사용 표정 원본
  "/assets/portraits/faces",       // 미사용 얼굴 크롭
  "heroine_red_idle.png",      // 레드 버전 idle (현재 미사용)
  "KoPubWorldDotumLight.ttf",  // 미사용 폰트 웨이트
  "ASSET_PROMPTS.md", "README.md", "UI_DESIGN_BRIEF.md", // 개발 문서
];

if (existsSync(out)) rmSync(out, { recursive: true });
cpSync(src, out, {
  recursive: true,
  filter: (p) => {
    const norm = p.split(path.sep).join("/");
    return !EXCLUDE.some((e) => norm.includes(e));
  },
});
console.log("복사 완료:", src, "→", out);
