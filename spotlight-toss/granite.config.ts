// 앱인토스 미니앱 설정 (기존 웹 프로젝트 방식).
// ⚠️ appName은 앱인토스 콘솔에 등록한 이름과 반드시 같아야 한다 (intoss://{appName} 딥링크로 쓰임).
//    콘솔에서 앱을 만든 뒤 아래 값을 실제 등록명으로 바꿀 것.
import { defineConfig } from "@apps-in-toss/web-framework/config";

export default defineConfig({
  appName: "spotlight",              // ← 콘솔 등록명으로 교체
  brand: {
    displayName: "SPOTLIGHT",        // 토스 안에서 보이는 앱 이름
    primaryColor: "#f3c969",         // 게임 골드 포인트 컬러
    icon: "",                        // ← 콘솔에 올린 앱 아이콘 이미지 URL로 교체
  },
  web: {
    host: "localhost",
    port: 5173,
    commands: {
      dev: "npm run dev",            // 로컬 미리보기 (정적 서빙)
      build: "npm run build",        // dist/ 생성 (정적 복사)
    },
  },
  permissions: [],                   // 카메라·위치 등 특수 권한 사용 없음
  outdir: "dist",
});
