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

// coordsConfirmed: true = 사용자가 확정한 정확 좌표 / false = 근사값(런칭 전 교체 필요)
export const SPOTS = [
  {
    id: 'sohwang',
    name: '소황사구해역 해양보호구역',
    desc: '충남 보령시 웅천읍 앞바다의 해양보호구역. 해안 사구와 철새가 어우러진 가을 명소입니다.',
    // 36°11'59.6"N 126°32'21.6"E (사용자 확정)
    lat: 36.199889,
    lng: 126.539333,
    radiusM: 200,
    coordsConfirmed: true,
  },
  {
    id: 'muchangpo',
    name: '무창포해수욕장',
    desc: '바닷길이 열리는 신비의 해변. 가을 낙조 명소로 사랑받습니다. (보령시 웅천읍)',
    lat: 36.25430,
    lng: 126.53860,
    radiusM: 200,
    coordsConfirmed: false, // 근사값 — 확정 좌표 받으면 교체
  },
  {
    id: 'gunheon',
    name: '군헌어촌체험휴양마을',
    desc: '충남 보령시 오천면의 갯벌체험 휴양마을. 서해 갯벌과 어촌 정취를 즐길 수 있습니다.',
    // 36°20'15.2"N 126°31'57.7"E (사용자 확정)
    lat: 36.337556,
    lng: 126.532694,
    radiusM: 200,
    coordsConfirmed: true,
  },
];

export function getSpot(id) {
  return SPOTS.find((s) => s.id === id) || null;
}
