import { defineConfig } from "vite";

// GitHub Pages는 https://jtaechul.github.io/Product/spotlight/ 로 서빙되므로
// base 경로를 맞춰야 에셋이 깨지지 않는다. (앱 빌드 시엔 무시됨)
export default defineConfig({
  base: "./",
  build: {
    target: "es2020",
    outDir: "dist",
  },
});
