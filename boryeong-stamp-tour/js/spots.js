// 보령 가을 스탬프 투어 — 관광지 3개소 데이터
// ⚠️ 좌표는 플레이스홀더(대략값)입니다. 실제 행사 확정 후 정확한 위경도로 교체하세요.
// 반경(radiusM)은 기본 200m. 지점별로 조정 가능.

export const EVENT = {
  title: '보령 가을愛 스탬프 투어',
  subtitle: '가을, 보령의 세 곳을 걸으며 스탬프를 모으세요',
  // 행사 기간(미정) — 확정 후 교체. 프로토타입에서는 안내용으로만 사용.
  periodText: '2026년 가을 (기간 확정 예정)',
  // 선착순 인원 상한(미정) — 확정 후 교체. 프로토타입 mock 조기마감 시연용.
  firstComeLimit: 300,
  requiredCount: 3,
};

// ⚠️ 아래 lat/lng 는 대략적인 근사 좌표입니다(자동 조회 제한).
//    실제 런칭 전, 각 지점의 "인증 기준점"을 네이버/카카오 지도에서 확인해
//    정확한 좌표로 교체하세요. (반경 200m 인증이라 오차가 크면 인증이 안 됩니다.)
//    coordsConfirmed: true 로 바꾸면 확정 좌표라는 표시입니다.
export const SPOTS = [
  {
    id: 'sohwang',
    name: '소황사구',
    desc: '충남 보령시 웅천읍 소황리 일원의 해안 사구. 해양보호구역으로 지정된 가을 산책 명소입니다.',
    lat: 36.25060,
    lng: 126.50650,
    radiusM: 200,
    coordsConfirmed: false,
  },
  {
    id: 'muchangpo',
    name: '무창포해수욕장',
    desc: '바닷길이 열리는 신비의 해변. 가을 낙조 명소로 사랑받습니다. (보령시 웅천읍)',
    lat: 36.25430,
    lng: 126.53860,
    radiusM: 200,
    coordsConfirmed: false,
  },
  {
    id: 'gunheon',
    name: '군헌어촌계',
    desc: '충남 보령시 오천면의 갯벌체험 어촌마을. 서해 갯벌과 어촌 정취를 느낄 수 있습니다.',
    lat: 36.34300,
    lng: 126.47000,
    radiusM: 200,
    coordsConfirmed: false,
  },
];

export function getSpot(id) {
  return SPOTS.find((s) => s.id === id) || null;
}
