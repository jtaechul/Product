// 활동 데이터 (기획서 9번). 수치는 플레이 테스트로 조정 (기획서 8번).
// effects: 능력치 증가(소프트캡 적용 대상) / stamina·mental·money: 자원 변동 / pose: 선택 시 캐릭터 포즈 키
export const ACTIVITIES = [
  { id: "acting",    emoji: "🎬", name: "연기 학원", effects: { acting: 5, emotion: 3 }, mental: -3, money: -80000,  stamina: -10, pose: "acting",    desc: "연기력·감정표현" },
  { id: "vocal",     emoji: "🎤", name: "보컬 레슨", effects: { singing: 6 },            money: -60000, stamina: -8,  pose: "vocal",     desc: "가창" },
  { id: "dance",     emoji: "💃", name: "댄스 레슨", effects: { dance: 6 },              money: -60000, stamina: -10, pose: "dance",     desc: "댄스" },
  { id: "gym",       emoji: "🏋️", name: "헬스·PT",  effects: { looks: 3 },              money: -40000, stamina: 3,   pose: "gym",       desc: "체력·외모" },
  { id: "study",     emoji: "📖", name: "독서실",    effects: { study: 6 },              mental: -4, money: -30000,  stamina: -8,  pose: "study",     desc: "학업" },
  { id: "reading",   emoji: "📚", name: "독서·교양", effects: { character: 5, study: 2 }, mental: 3, money: -10000,  stamina: -3,  pose: "study",     desc: "인성·학업" },
  { id: "volunteer", emoji: "🤲", name: "봉사활동",  effects: { character: 7, network: 2 }, mental: 5,             stamina: -8,  pose: "volunteer", desc: "인성·인맥" },
  { id: "family",    emoji: "👨‍👩‍👧", name: "가족과 시간", effects: { character: 5 },       mental: 12,             stamina: 3,   pose: "family",    desc: "인성·멘탈" },
  { id: "friend",    emoji: "🧑‍🤝‍🧑", name: "친구와 우정", effects: { character: 3, network: 3 }, mental: 15, money: -30000, stamina: 5, pose: "family", desc: "인성·멘탈" },
  { id: "styling",   emoji: "💄", name: "스타일링",  effects: { looks: 4, fame: 3 },     money: -20000, stamina: -5,  pose: "good",      desc: "외모·인지도" },
  { id: "rest",      emoji: "☕", name: "휴식",      effects: {},                        mental: 15,             stamina: 20,  pose: "rest",      desc: "체력·멘탈 회복" },
  { id: "parttime",  emoji: "💼", name: "단기 알바", effects: {},                        mental: -5, money: 120000, stamina: -15, pose: "good",      desc: "돈 +12만" },
];

// 자동 활동(매달 기본 적용) — 학교 수업
export const AUTO_ACTIVITY = { name: "학교 수업", effects: { study: 2, character: 1 }, stamina: -5 };

// 능력치 메타 (라벨·계열)
export const STATS_META = [
  { key: "acting",   label: "연기력",  group: "연기" },
  { key: "emotion",  label: "감정표현", group: "연기" },
  { key: "vocal",    label: "발성",    group: "연기" },
  { key: "looks",    label: "외모",    group: "매력" },
  { key: "singing",  label: "가창",    group: "매력" },
  { key: "dance",    label: "댄스",    group: "매력" },
  { key: "study",    label: "학업",    group: "소양" },
  { key: "character",label: "인성",    group: "소양" },
  { key: "network",  label: "인맥",    group: "사회" },
  { key: "fame",     label: "인지도",  group: "사회" },
];
