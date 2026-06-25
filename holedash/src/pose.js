// ===== 인식 레이어 =====
// 웹캠 + MediaPipe Pose Landmarker → 매 프레임 33개 관절 좌표(정규화 0~1) 제공.

// 로컬 vendoring(에셋을 저장소에 동봉) → CDN 의존 없이 오프라인·빠른 로드.
const VENDOR = new URL('../vendor/', import.meta.url);
const BUNDLE_URL = new URL('vision_bundle.mjs', VENDOR).href;
const WASM_PATH = new URL('wasm', VENDOR).href;
const MODEL_URL = new URL('pose_landmarker_lite.task', VENDOR).href;

export class PoseTracker {
  constructor(video) {
    this.video = video;
    this.landmarker = null;
    this.lastResult = null;
    this.lastVideoTime = -1;
    this.ready = false;
  }

  // 모델 로드 (CDN 동적 import)
  async init() {
    const { FilesetResolver, PoseLandmarker } = await import(
      /* @vite-ignore */ BUNDLE_URL
    );
    const fileset = await FilesetResolver.forVisionTasks(WASM_PATH);
    this.landmarker = await PoseLandmarker.createFromOptions(fileset, {
      baseOptions: { modelAssetPath: MODEL_URL, delegate: 'GPU' },
      runningMode: 'VIDEO',
      numPoses: 1,
      minPoseDetectionConfidence: 0.5,
      minPosePresenceConfidence: 0.5,
      minTrackingConfidence: 0.5,
    });
    this.ready = true;
  }

  // 웹캠 시작 — 세로 화면이면 세로 비율 카메라를 요청해 좌우가 넓게 보이도록
  async startCamera() {
    const portrait = window.innerHeight > window.innerWidth;
    const ideal = portrait ? { width: { ideal: 720 }, height: { ideal: 1280 } }
                           : { width: { ideal: 1280 }, height: { ideal: 720 } };
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'user', ...ideal },
      audio: false,
    });
    this.video.srcObject = stream;
    await new Promise((res) => {
      if (this.video.readyState >= 2) return res();
      this.video.onloadedmetadata = () => res();
    });
    await this.video.play();
  }

  // 현재 프레임 감지 → landmarks 배열 반환(없으면 null)
  detect(nowMs) {
    if (!this.ready || this.video.readyState < 2) return this.lastResult;
    if (this.video.currentTime === this.lastVideoTime) return this.lastResult;
    this.lastVideoTime = this.video.currentTime;
    const result = this.landmarker.detectForVideo(this.video, nowMs);
    if (result && result.landmarks && result.landmarks.length > 0) {
      this.lastResult = result.landmarks[0]; // 첫 번째 사람
    } else {
      this.lastResult = null;
    }
    return this.lastResult;
  }
}

// 두 정규화 좌표 사이 거리(화면 비율 고려 안 함 — 픽셀 변환은 호출부에서)
export function dist(a, b) {
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  return Math.hypot(dx, dy);
}

// 유효 관절(visibility 충분)인지
export function visible(lm, idx, thr = 0.4) {
  return lm[idx] && (lm[idx].visibility === undefined || lm[idx].visibility >= thr);
}
