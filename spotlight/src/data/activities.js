// 활동 카테고리 (기획서 7번 계열 기반, 우마무스메식 2단 메뉴 상위 4종)
export const CATEGORIES = [
  { id: "acting", emoji: "🎭", label: "연기", color: 0xff8a7a, desc: "연기력·감정·발성" },
  { id: "charm",  emoji: "✨", label: "매력", color: 0x7ee0c8, desc: "외모·가창·댄스" },
  { id: "mind",   emoji: "📚", label: "소양", color: 0xf5c451, desc: "학업·인성·인맥" },
  { id: "life",   emoji: "💛", label: "생활", color: 0x9aa7ff, desc: "휴식·관계·돈" },
];

// 활동 데이터 (기획서 9번). cat: 소속 카테고리.
// effects: 능력치 증가(소프트캡 적용) / stamina·mental·money: 자원 변동 / pose: 선택 시 캐릭터 포즈 키
export const ACTIVITIES = [
  { id: "acting",    cat: "acting", emoji: "🎬", name: "연기 학원", effects: { acting: 5, emotion: 3 }, mental: -3, money: -80000,  stamina: -10, pose: "acting",    desc: "연기력·감정표현" },
  { id: "prep",      cat: "acting", emoji: "🎯", name: "차기작 준비", effects: { acting: 2 },           money: -10000, stamina: -8,  pose: "acting",    desc: "다음 출연 평가↑" },
  { id: "vocal",     cat: "charm",  emoji: "🎤", name: "보컬 레슨", effects: { singing: 6 },            money: -60000, stamina: -8,  pose: "vocal",     desc: "가창" },
  { id: "dance",     cat: "charm",  emoji: "💃", name: "댄스 레슨", effects: { dance: 6 },              money: -60000, stamina: -10, pose: "dance",     desc: "댄스" },
  { id: "gym",       cat: "charm",  emoji: "🏋️", name: "헬스·PT",  effects: { looks: 3 },              money: -40000, stamina: 3,   pose: "gym",       desc: "체력·외모" },
  { id: "styling",   cat: "charm",  emoji: "💄", name: "스타일링",  effects: { looks: 4, fame: 3 },     money: -20000, stamina: -5,  pose: "good",      desc: "외모·인지도" },
  { id: "study",     cat: "mind",   emoji: "📖", name: "독서실",    effects: { study: 6 },              mental: -4, money: -30000,  stamina: -8,  pose: "study",     desc: "학업" },
  { id: "reading",   cat: "mind",   emoji: "📚", name: "독서·교양", effects: { character: 5, study: 2 }, mental: 3, money: -10000,  stamina: -3,  pose: "study",     desc: "인성·학업" },
  { id: "volunteer", cat: "mind",   emoji: "🤲", name: "봉사활동",  effects: { character: 7, network: 2 }, mental: 5,             stamina: -8,  pose: "volunteer", desc: "인성·인맥" },
  { id: "family",    cat: "life",   emoji: "👨‍👩‍👧", name: "가족과 시간", effects: { character: 5 },       mental: 12,             stamina: 3,   pose: "family",    desc: "인성·멘탈" },
  { id: "friend",    cat: "life",   emoji: "🧑‍🤝‍🧑", name: "친구와 우정", effects: { character: 3, network: 3 }, mental: 15, money: -30000, stamina: 5, pose: "family", desc: "인성·멘탈" },
  { id: "rest",      cat: "life",   emoji: "☕", name: "휴식",      effects: {},                        mental: 15,             stamina: 20,  pose: "rest",      desc: "체력·멘탈 회복" },
  { id: "parttime",  cat: "life",   emoji: "💼", name: "단기 알바", effects: {},                        mental: -5, money: 120000, stamina: -15, pose: "good",      desc: "돈 +12만" },
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
