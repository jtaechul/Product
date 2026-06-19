// 상점 아이템 (기획서 8단계 · 아이템 7종). 돈으로 구매 → 즉시 효과.
// effects: 능력치(소프트캡)·stamina·mental·fans 변동 / lucky: 다음 출연 평가 1회 +15%.
export const ITEMS = [
  { id: "nutrient",  emoji: "🥗", name: "종합 영양제",   desc: "체력 +30",            cost: 30000,  effects: { stamina: 30 } },
  { id: "mentalcare",emoji: "🧘", name: "멘탈 케어",     desc: "멘탈 +25",            cost: 30000,  effects: { mental: 25 } },
  { id: "script",    emoji: "📕", name: "명품 대본집",   desc: "연기력 +6",           cost: 120000, effects: { acting: 6 } },
  { id: "vocalbook", emoji: "🎙️", name: "발성 교본",     desc: "발성 +5",             cost: 90000,  effects: { vocal: 5 } },
  { id: "ptpass",    emoji: "💪", name: "PT 이용권",     desc: "외모 +4 · 체력 +12",   cost: 80000,  effects: { looks: 4, stamina: 12 } },
  { id: "network",   emoji: "🥂", name: "네트워킹 파티", desc: "인맥 +6",             cost: 100000, effects: { network: 6 } },
  { id: "charm",     emoji: "🍀", name: "행운의 부적",   desc: "다음 출연 평가 +15% (1회)", cost: 150000, lucky: true },
];
