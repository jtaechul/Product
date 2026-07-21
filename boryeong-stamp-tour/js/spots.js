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

export const SPOTS = [
  {
    id: 'daecheon',
    name: '대천해수욕장',
    desc: '서해안 대표 해변. 머드로 유명한 보령의 상징적인 관광지입니다.',
    lat: 36.31150,
    lng: 126.51400,
    radiusM: 200,
  },
  {
    id: 'muchangpo',
    name: '무창포해수욕장',
    desc: '바닷길이 열리는 신비의 해변. 가을 낙조 명소로 사랑받습니다.',
    lat: 36.25400,
    lng: 126.53900,
    radiusM: 200,
  },
  {
    id: 'gaehwa',
    name: '개화예술공원',
    desc: '조각과 야생화가 어우러진 예술 공원. 가을 산책에 좋습니다.',
    lat: 36.39000,
    lng: 126.64800,
    radiusM: 200,
  },
];

export function getSpot(id) {
  return SPOTS.find((s) => s.id === id) || null;
}
