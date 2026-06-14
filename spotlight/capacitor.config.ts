import type { CapacitorConfig } from "@capacitor/cli";

// 같은 코드베이스를 iOS/Android 네이티브 앱으로 패키징하기 위한 설정.
// 웹 빌드 결과물(dist)을 앱 webDir 로 사용한다.
const config: CapacitorConfig = {
  appId: "com.spotlight.game",
  appName: "SPOTLIGHT",
  webDir: "dist",
  // 세로 고정은 각 플랫폼 프로젝트 설정에서 portrait 으로 잠근다.
};

export default config;
