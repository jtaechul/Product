// 작품 출연 매체 데이터 (기획서 11번). from: 등장 시작 턴(고1=1, 고2=13, 고3=25).
// req: 기대치 스탯, pay: 출연료(만원), fame: 호평 시 팬, gain: 호평 시 스탯, flag: 특수 플래그
export const MEDIA = [
  { id: "webdrama",  name: "웹드라마",        from: 1,  req: { acting: 10 },                         pay: 30,  fame: 5,  gain: { acting: 3 } },
  { id: "shortdrama",name: "단편 드라마",      from: 1,  req: { acting: 20, vocal: 15 },              pay: 50,  fame: 8,  gain: { vocal: 4 } },
  { id: "shortfilm", name: "단편 영화",        from: 10, req: { acting: 30, emotion: 20 },           pay: 70,  fame: 6,  gain: { emotion: 5 }, flag: "filmfest" },
  { id: "dramabit",  name: "드라마 단역",      from: 13, req: { acting: 35, vocal: 30 },             pay: 70,  fame: 12, gain: { acting: 3 } },
  { id: "cf",        name: "CF·광고",          from: 13, req: { looks: 45, fame: 25 },              pay: 95,  fame: 15, gain: { looks: 2 } },
  { id: "musical",   name: "뮤지컬 무대",      from: 13, req: { singing: 50, vocal: 45 },           pay: 80,  fame: 10, gain: { singing: 3 }, flag: "stage" },
  { id: "ott",       name: "OTT 조연",         from: 22, req: { acting: 50, emotion: 40, vocal: 40 }, pay: 120, fame: 20, gain: { acting: 4, emotion: 3 }, flag: "global" },
  { id: "filmlead",  name: "영화 조·주연",     from: 25, req: { acting: 65, emotion: 60, character: 40 }, pay: 170, fame: 30, gain: { acting: 5, emotion: 4 }, flag: "filmaward" },
  { id: "seasondrama",name: "시즌제 드라마 주연", from: 25, req: { acting: 70, looks: 55, fame: 60 }, pay: 230, fame: 30, gain: { acting: 4 }, flag: "national" },
];

// 등급별 연출 톤 (댓글)
export const GRADE_COMMENTS = {
  best:   ["연기 미쳤다… 소름 돋음", "이게 신인이라고? 인생 캐릭터 등극", "다시 돌려봤다 진짜 잘한다"],
  good:   ["생각보다 훨씬 잘하네!", "다음 작품도 기대된다", "연기 안정적이고 좋아요"],
  fair:   ["나쁘진 않은데 평범했음", "조금 아쉽지만 봐줄 만함", "무난무난"],
  bad:    ["발연기 논란…", "몰입이 안 됨ㅠ", "다음엔 더 준비하고 나오길"],
};
