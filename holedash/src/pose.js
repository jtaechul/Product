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
      numPoses: 3, // 여러 명 감지 → 화면 중앙에 선 사람을 우선 선택
      minPoseDetectionConfidence: 0.5,
      minPosePresenceConfidence: 0.5,
      minTrackingConfidence: 0.5,
    });
    this.ready = true;
  }

  // 웹캠 시작 — 가로 전용 게임이므로 항상 가로(16:9) 카메라를 요청
  async startCamera() {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } },
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
      this.lastResult = pickCentral(result.landmarks); // 화면 중앙에 가장 가까운 사람
    } else {
      this.lastResult = null;
    }
    return this.lastResult;
  }
}

// 여러 사람 중 '화면 중앙(x=0.5)에 가장 가까운' 사람을 우선 선택.
// (동점이면 더 크게 보이는=가까운 사람 우선)
function pickCentral(poses) {
  if (poses.length === 1) return poses[0];
  let best = null, bestScore = Infinity;
  for (const lm of poses) {
    const ls = lm[11], rs = lm[12], lh = lm[23], rh = lm[24];
    if (!ls || !rs) continue;
    const cx = (ls.x + rs.x + (lh ? lh.x : ls.x) + (rh ? rh.x : rs.x)) / 4;
    const shoulderW = Math.abs(ls.x - rs.x) || 0.1;
    // 중앙에서 벗어난 정도(주), 작게 보이면(멀면) 약간 페널티
    const score = Math.abs(cx - 0.5) - shoulderW * 0.15;
    if (score < bestScore) { bestScore = score; best = lm; }
  }
  return best || poses[0];
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
