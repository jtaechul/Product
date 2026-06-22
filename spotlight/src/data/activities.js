// 활동 카테고리 (기획서 7번 계열 기반, 우마무스메식 2단 메뉴 상위 4종)
export const CATEGORIES = [
  { id: "acting", emoji: "🎭", label: "연기", color: 0xff8a7a, desc: "연기력·감정·발성" },
  { id: "charm",  emoji: "✨", label: "매력", color: 0x7ee0c8, desc: "외모·가창·댄스" },
  { id: "mind",   emoji: "📚", label: "소양", color: 0xf5c451, desc: "학업·인성·인맥" },
  { id: "life",   emoji: "💛", label: "생활", color: 0x9aa7ff, desc: "휴식·관계·돈" },
];

// 활동 데이터 (기획서 9번). cat: 소속 카테고리.
// effects: 능력치 증가(소프트캡 적용) / stamina·mental·money: 자원 변동 / pose: 선택 시 캐릭터 포즈 키
// bg: 활동 연출 배경 (assets/bg/*.png) — 행동마다 다른 배경 (기획서 14B)
export const ACTIVITIES = [
  { id: "acting",    cat: "acting", emoji: "🎬", name: "연기 학원", effects: { acting: 5, emotion: 3 }, mental: -3, money: -80000,  stamina: -8,  pose: "acting",    bg: "academy", desc: "연기력·감정표현" },
  { id: "emote",     cat: "acting", emoji: "🎬", name: "감정 연기 특훈", effects: { emotion: 6, acting: 2 }, mental: -3, money: -50000, stamina: -8, pose: "acting", bg: "academy", desc: "감정표현·연기력" },
  { id: "prep",      cat: "acting", emoji: "🎯", name: "차기작 준비", effects: { acting: 2 }, prodBonus: 1.2, money: -10000, stamina: -7,  pose: "acting",    bg: "set",     desc: "다음 출연 평가↑" },
  { id: "vocal",     cat: "charm",  emoji: "🎤", name: "보컬 레슨", effects: { singing: 6, vocal: 5 },   money: -60000, stamina: -7,  pose: "vocal",     bg: "recording",   desc: "가창·발성" },
  { id: "dance",     cat: "charm",  emoji: "💃", name: "댄스 레슨", effects: { dance: 6 },              money: -60000, stamina: -9,  pose: "dance",     bg: "stage",   desc: "댄스" },
  { id: "gym",       cat: "charm",  emoji: "🏋️", name: "헬스·PT",  effects: { looks: 3 },              money: -40000, stamina: 6,   pose: "gym",       bg: "gym", desc: "체력·외모" },
  { id: "styling",   cat: "charm",  emoji: "💄", name: "스타일링",  effects: { looks: 4, fame: 3 },     money: -20000, stamina: -4,  pose: "redcarpet", bg: "salon",    desc: "외모·팬" },
  { id: "study",     cat: "mind",   emoji: "📖", name: "독서실",    effects: { study: 6 },              mental: -4, money: -30000,  stamina: -7,  pose: "study",     bg: "school",  desc: "학업" },
  { id: "reading",   cat: "mind",   emoji: "📚", name: "독서·교양", effects: { character: 3, study: 2 },            money: -10000,  stamina: -3,  pose: "study",     bg: "library",    desc: "인성·학업" },
  { id: "volunteer", cat: "mind",   emoji: "🤲", name: "봉사활동",  effects: { character: 5, network: 3 },                      stamina: -7,  pose: "volunteer", bg: "park",  desc: "인성·인맥" },
  { id: "family",    cat: "life",   emoji: "👨‍👩‍👧", name: "가족과 시간", effects: { character: 3 },       mental: 5,              stamina: 6,   pose: "family",    bg: "home",    desc: "인성·멘탈" },
  { id: "friend",    cat: "life",   emoji: "🧑‍🤝‍🧑", name: "친구와 우정", effects: { character: 2, network: 4 }, mental: 6, money: -30000, stamina: 4, pose: "family", bg: "school",  desc: "인성·멘탈" },
  { id: "rest",      cat: "life",   emoji: "☕", name: "휴식",      effects: {},                        mental: 10,             stamina: 45,  pose: "rest",      bg: "home",    desc: "체력·멘탈 회복" },
  { id: "parttime",  cat: "life",   emoji: "💼", name: "단기 알바", effects: {},                        mental: -6, money: 90000,  stamina: -12, pose: "good",      bg: "cafe",     desc: "돈 +9만" },
];

// 분기 특별활동 (기획서 3·5: 우마무스메식 분기 이벤트) — (turn-1)%3===0 인 달에만 등장.
// 매력·팬 위주 강화. 모두 '출연/행사'라 출연료를 받는다(돈 +). 아이돌/스타/뮤지컬/예능 루트를 떠받친다.
export const SPECIAL_ACTS = [
  { id: "idol_stage", cat: "special", name: "아이돌 쇼케이스", effects: { singing: 5, dance: 5, fame: 8 },            money: 60000,  stamina: -14, pose: "dance",  bg: "stage", desc: "가창·댄스·팬 大" },
  { id: "photoshoot", cat: "special", name: "화보 촬영",       effects: { looks: 6, fame: 6 },             money: 90000,  stamina: -8,  pose: "photo", bg: "photostudio",  desc: "외모·팬·모델료" },
  { id: "fanmeeting", cat: "special", name: "팬미팅",         effects: { fame: 10, network: 3 }, mental: 3, money: 70000,  stamina: -10, pose: "cheer",  bg: "fanmeet", desc: "팬 大·인맥·행사비" },
  { id: "varietyshow",cat: "special", name: "예능 출연",       effects: { network: 5, fame: 7, dance: 3 }, money: 50000,  stamina: -12, pose: "interview", bg: "variety_set",   desc: "인맥·팬·출연료" },
];

// id로 일반/특별 활동을 통합 조회
export function findActivity(id) {
  return ACTIVITIES.find((a) => a.id === id) || SPECIAL_ACTS.find((a) => a.id === id) || null;
}

// 활동별 연출 대사 (다음 달 진행 시 활동 이미지와 함께 노출) — 기획서 14번 B
export const ACT_LINES = {
  acting:    ["감정선을 따라 대본을 읽어 내려갔다. 조금씩 인물이 보인다.", "노교수님의 디렉션에 연기 호흡이 한 뼘 자랐다."],
  prep:      ["다음 작품을 위해 캐릭터 노트를 빼곡히 채웠다.", "거울 앞에서 배역을 머릿속으로 그려본다."],
  vocal:     ["한 음 한 음, 목소리에 색이 입혀진다.", "막혔던 고음이 한결 편해졌다!"],
  dance:     ["거울 앞에서 같은 동작을 수십 번. 몸이 기억하기 시작했다.", "스텝이 음악과 딱 맞아떨어지는 순간!"],
  gym:       ["땀이 쏟아졌지만, 체력이 붙는 게 느껴진다.", "한 세트 더! 거울 속 내가 단단해진다."],
  styling:   ["거울 속 내가 조금 더 마음에 든다.", "작은 변화 하나로 분위기가 달라졌다."],
  study:     ["문제집을 덮으니 머리가 맑아졌다.", "오늘 분량을 끝내고 자습실을 나섰다."],
  reading:   ["좋은 문장은 마음을 넓혀준다.", "책 한 권이 새로운 시야를 열어줬다."],
  volunteer: ["누군가를 돕고 나니 마음이 따뜻해졌다.", "고맙다는 말 한마디에 하루가 환해졌다."],
  family:    ["엄마가 차려준 밥에 하루의 피로가 녹았다.", "가족과의 시간이 마음을 든든하게 채워준다."],
  friend:    ["친구의 응원에 다시 웃을 수 있었다.", "수다 한 판에 묵은 스트레스가 날아갔다."],
  rest:      ["오랜만에 아무것도 안 하는 사치. 충전 완료!", "푹 쉬고 나니 몸도 마음도 가뿐하다."],
  parttime:  ["고된 하루였지만 통장 잔고가 늘었다.", "땀 흘려 번 돈, 뿌듯함은 덤이다."],
  idol_stage:["함성 속에서 무대를 휘어잡았다. 심장이 뛴다!", "노래와 춤이 하나로 터지는 순간, 객석이 들썩였다.", "응원봉이 파도처럼 출렁였다. 이 맛에 무대에 선다.", "마지막 포즈에 터진 환호. 다리가 후들거렸지만 행복했다."],
  photoshoot:["플래시 세례 속, 카메라가 나를 사랑하기 시작했다.", "한 컷 한 컷이 화보가 됐다.", "포토그래퍼가 엄지를 척! 이번 컷, 표지감이래.", "콘셉트가 바뀔 때마다 전혀 다른 내가 됐다."],
  fanmeeting:["나를 보러 와 준 사람들. 이름을 불러주는 목소리에 울컥했다.", "팬들의 응원이 큰 힘이 됐다.", "한 명 한 명 눈을 맞추며 사인했다. 손끝이 따뜻해졌다.", "'덕분에 힘냈어요'라는 편지에 코끝이 찡했다."],
  varietyshow:["예능 감각이 빛난 하루! 웃음 속에 이름을 알렸다.", "순발력으로 분위기를 살렸다.", "리액션 한 방에 스튜디오가 빵 터졌다.", "MC가 '신인 맞아요?' 하며 엄지를 들었다."],
};

// 계절별 특별 분위기 대사 (가끔 활동 연출 앞에 삽입) — 월별 이벤트성 톤
export const SEASON_LINES = {
  봄: "벚꽃이 흩날리는 교정, 새 학기의 설렘이 가득하다.",
  여름: "무더운 여름, 매미 소리 속에서도 꿈은 식지 않는다.",
  가을: "선선한 바람에 마음을 다잡는 계절이 왔다.",
  겨울: "추운 겨울, 하얀 입김을 불며 오늘도 한 걸음.",
};

// 자동 활동(매달 기본 적용) — 학교 수업. 밸런스: 학업·인성은 자동으로 오르지 않는다(직접 활동으로만 성장).
export const AUTO_ACTIVITY = { name: "학교 수업", effects: {}, stamina: -5 };

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
  { key: "fame",     label: "팬",  group: "사회" },
];
