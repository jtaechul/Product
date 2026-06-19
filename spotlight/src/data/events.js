// 랜덤 이벤트 & 선택지 (기획서 13번). effects 키: 능력치/stamina/mental/money/fans, flag: 숨은 플래그.
export const EVENTS = [
  {
    id: "mentor", emoji: "🎬", title: "선배의 멘토링",
    text: "촬영장에서 만난 선배가 다가와 연기 노하우를 슬쩍 알려준다.",
    choices: [
      { label: "진지하게 배운다", effects: { acting: 8, character: 3, mental: 4 }, result: "선배의 조언이 큰 도움이 됐다!" },
      { label: "내 방식대로 간다", effects: { acting: 3 }, result: "내 색을 지켰다." },
    ],
  },
  {
    id: "fanletter", emoji: "💌", title: "팬레터",
    text: "정성스럽게 쓴 손편지 팬레터가 도착했다.",
    choices: [
      { label: "감사히 읽는다", effects: { mental: 15 }, result: "마음이 따뜻해지고 큰 힘이 됐다." },
    ],
  },
  {
    id: "helpjunior", emoji: "🤝", title: "후배 돕기",
    text: "잔뜩 긴장한 신인 후배가 조언을 구한다.",
    choices: [
      { label: "기꺼이 돕는다", effects: { character: 8, network: 3, mental: 3 }, flag: "respected", result: "후배가 진심으로 고마워했다." },
      { label: "내 연습이 먼저다", effects: { acting: 3, character: -2 }, result: "조금 미안한 마음이 남았다." },
    ],
  },
  {
    id: "hate", emoji: "💢", title: "악성 댓글",
    text: "근거 없는 악플이 우르르 달렸다. 어떻게 대응할까?",
    choices: [
      { label: "신경 쓰지 않는다", effects: { mental: -5 }, result: "흔들리지 않고 멘탈을 지켰다." },
      { label: "상처받는다", effects: { mental: -15 }, result: "마음이 한동안 무거웠다." },
      { label: "단호히 법적 대응", effects: { mental: -3, money: -200000 }, flag: "controversy_guard", result: "원칙대로 단호하게 대응했다." },
    ],
  },
  {
    id: "injury", emoji: "🤕", title: "몸이 보내는 신호",
    text: "빡빡한 일정에 몸 곳곳이 쑤신다.",
    choices: [
      { label: "푹 쉰다", effects: { stamina: 8, mental: 4 }, result: "회복에 집중했다." },
      { label: "참고 강행한다", effects: { stamina: -30 }, result: "몸이 더 상하고 말았다…" },
    ],
  },
  {
    id: "conflict", emoji: "🎭", title: "촬영장 갈등",
    text: "동료 배우가 NG를 연발해 촬영이 자정을 넘긴다.",
    choices: [
      { label: "따뜻하게 다독인다", effects: { character: 6, network: 3 }, flag: "respected", result: "현장 분위기가 한결 부드러워졌다." },
      { label: "대놓고 한숨 쉰다", effects: { character: -5 }, flag: "controversy", result: "어색한 침묵이 흘렀다…" },
      { label: "내 연기에 집중", effects: { acting: 3 }, result: "묵묵히 내 할 일을 했다." },
    ],
  },
  {
    id: "audition", emoji: "✨", title: "깜짝 오디션",
    text: "지나가던 캐스팅 디렉터가 즉석 연기를 청한다.",
    choices: [
      { label: "자신 있게 해본다", effects: { acting: 5, fans: 4, mental: 3 }, result: "강한 인상을 남겼다!" },
      { label: "정중히 사양한다", effects: { mental: 2 }, result: "다음을 기약했다." },
    ],
  },
  {
    id: "study", emoji: "📚", title: "시험 기간",
    text: "학교 시험이 코앞이다. 연기와 학업, 균형이 필요하다.",
    choices: [
      { label: "공부에 집중", effects: { study: 6, mental: -3 }, result: "성적을 챙겼다." },
      { label: "연습을 택한다", effects: { acting: 4, study: -2 }, result: "연기에 더 시간을 썼다." },
    ],
  },
];
