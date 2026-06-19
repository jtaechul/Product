// 모듈형 엔딩 (기획서 15번): [분야]×[급]×[특성] 조합으로 회차마다 다른 40년 회고를 생성.
// 화면에는 수치를 노출하지 않고 서사·일러스트만 보여준다. when(c)은 우선순위 순서로 평가(위가 먼저).
// c = ending.js buildContext()가 만든 지표. illust = assets/endings/*.png 키.

const BOND_NAME = { hanjiwon: "한지원", noh: "노교수", haneul: "박하늘", yusea: "유세아" };

// 매체 id → 분야
export const FIELD_OF = {
  webdrama: "drama", shortdrama: "drama", dramabit: "drama", seasondrama: "drama",
  shortfilm: "film", filmlead: "film", ott: "ott", musical: "musical", cf: "ad",
};
const FIELD_LABEL = { drama: "드라마", film: "영화", ott: "OTT", musical: "뮤지컬", ad: "광고" };

// 플래그 → 수상/이력 문구
export const AWARD_OF = {
  filmaward: "그 해 최고 영화상 주연상",
  national: "방송사 연기대상",
  global: "해외 유수 시상식 본상",
  stage: "무대 평론가 협회상",
  filmfest: "국제 영화제 노미네이트",
};

export function bondPeople(bonds) {
  return Object.keys(bonds).filter((k) => bonds[k] >= 80).map((k) => BOND_NAME[k]);
}

// 우선순위 순 엔딩 목록 (15종). core/quote로 서사 중반·소감을 만든다.
export const ENDINGS = [
  {
    id: "controversy", emoji: "💔", title: "구설수 속에 사라진 배우", trait: "논란", illust: "unknown_supporting",
    when: (c) => c.flags.has("controversy") && c.char < 35,
    core: (c) => `재능은 분명 빛났지만, 거듭된 구설은 그 빛을 가렸다. 화제의 중심에 섰던 만큼 등을 돌리는 사람도 빨랐다.`,
    quote: "다 가진 것 같았는데, 정작 사람을 잃었더군요.",
  },
  {
    id: "mentor_master", emoji: "🎓", title: "후학을 키운 대배우", trait: "후학양성", illust: "national",
    when: (c) => c.actAvg >= 68 && c.char >= 80 && c.study >= 45 && c.bondNoh >= 80,
    core: (c) => `정상에 오른 뒤에도 그/그녀는 강단과 현장을 떠나지 않았다. 수많은 후배가 그 손을 잡고 배우로 자라났다.`,
    quote: "재능보다 오래가는 건 사람됨이었습니다.",
  },
  {
    id: "national", emoji: "🏆", title: "국민 대배우", trait: "균형의 완성", illust: "national",
    when: (c) => c.actAvg >= 66 && c.char >= 56 && c.study >= 46 && (c.flags.has("national") || c.flags.has("filmaward")) && c.fame >= 68,
    core: (c) => `연기와 인격, 교양을 두루 갖춘 그/그녀는 세대를 아울러 사랑받았다. 영화와 드라마 양쪽에서 정점에 섰다.`,
    quote: "오래 사랑받는 배우이고 싶었습니다. 그거면 충분합니다.",
  },
  {
    id: "director_actor", emoji: "🎬", title: "감독 겸 배우", trait: "창작자", illust: "film_master",
    when: (c) => c.study >= 66 && c.char >= 58 && c.actAvg >= 60,
    core: (c) => `카메라 앞과 뒤를 모두 아는 사람이 되었다. 직접 쓰고 연출한 작품으로 또 한 번 박수를 받았다.`,
    quote: "연기를 알았기에, 이야기를 더 사랑하게 됐습니다.",
  },
  {
    id: "film_master", emoji: "🎬", title: "영화계의 거장", trait: "연기파", illust: "film_master",
    when: (c) => c.actAvg >= 62 && c.fieldTop === "film" && (c.flags.has("filmaward") || c.flags.has("filmfest")),
    core: (c) => `스크린 위에서 그/그녀의 얼굴은 한 편의 시였다. 깊은 감정 연기로 영화사에 이름을 새겼다.`,
    quote: "한 장면을 위해 일 년을 살아도 아깝지 않았습니다.",
  },
  {
    id: "global", emoji: "🍿", title: "글로벌 한류 스타", trait: "국제파", illust: "film_master",
    when: (c) => c.flags.has("global") && c.fame >= 72,
    core: (c) => `OTT를 타고 그/그녀의 연기는 국경을 넘었다. 전 세계 팬이 그 이름을 부르며 한국어 대사를 따라 했다.`,
    quote: "언어는 달라도, 마음은 연기로 전해지더군요.",
  },
  {
    id: "tv_star", emoji: "📺", title: "안방극장의 별", trait: "스타성", illust: "film_master",
    when: (c) => c.fieldTop === "drama" && c.fame >= 58 && c.actAvg >= 48,
    core: (c) => `매주 저녁, 그/그녀의 얼굴은 온 가족의 화제였다. 안방극장을 수놓은 숱한 명장면을 남겼다.`,
    quote: "평범한 저녁을 특별하게 만드는 게 제 일이었어요.",
  },
  {
    id: "musical", emoji: "🎵", title: "뮤지컬 디바/프린스", trait: "무대형", illust: "film_master",
    when: (c) => c.sing >= 56 && c.voc >= 50 && c.flags.has("stage"),
    core: (c) => `노래와 연기가 하나로 녹아든 무대. 객석을 울리고 웃기며 커튼콜마다 기립박수를 받았다.`,
    quote: "막이 오르는 그 순간만큼 살아있다고 느낀 적이 없습니다.",
  },
  {
    id: "theater", emoji: "🎭", title: "연극 무대의 거목", trait: "장인", illust: "film_master",
    when: (c) => c.actAvg >= 60 && c.voc >= 56 && c.fame < 55,
    core: (c) => `대중적 인기를 좇기보다, 그/그녀는 무대를 택했다. 작은 소극장에서도 관객은 그 깊이에 숨을 죽였다.`,
    quote: "박수 소리보다, 관객의 침묵이 더 큰 상이었습니다.",
  },
  {
    id: "character_actor", emoji: "🧩", title: "천의 얼굴 성격파", trait: "변신의 귀재", illust: "film_master",
    when: (c) => c.emo >= 60 && c.char >= 56 && c.praisedCount >= 4,
    core: (c) => `악역도, 광대도, 아버지도 — 작품마다 전혀 다른 사람이 되었다. "저 사람 누구야?"가 최고의 찬사였다.`,
    quote: "제 얼굴이 기억되지 않을 때, 배역이 살아남습니다.",
  },
  {
    id: "star", emoji: "🌟", title: "스타성 배우", trait: "비주얼 아이콘", illust: "film_master",
    when: (c) => c.looks >= 56 && c.fame >= 58,
    core: (c) => `화면에 등장하는 것만으로 시선을 사로잡았다. 광고와 화보, 레드카펫 위에서 가장 빛나는 별이었다.`,
    quote: "빛나는 건 잠깐이지만, 그 순간을 후회 없이 살았어요.",
  },
  {
    id: "variety", emoji: "🎪", title: "예능 대세", trait: "만능 엔터테이너", illust: "film_master",
    when: (c) => (c.dance >= 42 || c.sing >= 42) && c.net >= 42 && c.fame >= 42,
    core: (c) => `연기뿐 아니라 예능과 무대에서도 종횡무진. 어디서든 분위기를 살리는 대세로 자리 잡았다.`,
    quote: "웃게 만드는 것도, 만만치 않은 연기였습니다.",
  },
  {
    id: "scene_stealer", emoji: "🎭", title: "명품 조연·신스틸러", trait: "신스틸러", illust: "film_master",
    when: (c) => c.actAvg >= 50 && c.praisedCount >= 3,
    core: (c) => `주연은 아니었지만, 그/그녀가 나오는 장면은 늘 회자됐다. "이 배우 어디서 봤더라"가 입버릇처럼 따라다녔다.`,
    quote: "작은 역이라도, 큰 마음으로 했습니다.",
  },
  {
    id: "late_bloomer", emoji: "🌱", title: "대기만성 늦깎이", trait: "대기만성", illust: "unknown_supporting",
    when: (c) => c.actAvg >= 44 && c.praisedCount >= 2,
    core: (c) => `시작은 더뎠고 무명도 길었다. 그러나 포기하지 않은 시간이 뒤늦게 꽃을 피웠다.`,
    quote: "늦게 핀 꽃이 더 오래 향기롭더군요.",
  },
  {
    id: "unknown", emoji: "🌙", title: "묵묵한 무명·조연", trait: "성실", illust: "unknown_supporting",
    when: () => true,
    core: (c) => `크게 빛나진 못했지만, 그/그녀는 끝까지 카메라 앞을 떠나지 않았다. 누군가의 작품 한 켠을 묵묵히 지켰다.`,
    quote: "이름은 못 남겨도, 한 장면은 남겼다고 믿습니다.",
  },
];
