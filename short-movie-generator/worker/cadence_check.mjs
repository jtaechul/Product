// 라이브러리 상단 '발행 빈도' 카드가 최근 7일 발행 수를 실제로 세는지 확인(브라우저 없이).
// 오늘 기준으로 매니페스트를 만들어(고정 날짜를 쓰면 시간이 지나 테스트가 썩는다) 세 가지를 본다:
//   ① 최근 7일 + 유튜브 URL 있는 것만 센다  ② 8일 전은 안 센다  ③ 미업로드는 안 센다
import worker from "./index.mjs";

const res = await worker.fetch(new Request("https://x/"), {}, {});
const js = [...(await res.text()).matchAll(/<script>([\s\S]*?)<\/script>/g)].map(x => x[1]).join("\n");

const els = {};
const el = id => (els[id] ??= { id, innerHTML: "", value: "", style: {}, dataset: {},
  classList: { toggle(){}, add(){}, remove(){} }, addEventListener(){}, querySelectorAll: () => [],
  insertAdjacentHTML(_p, h){ this.innerHTML += h; }, onclick: null, getAttribute: () => null });
globalThis.window = { location: { pathname: "/" } }; globalThis.location = window.location;
globalThis.document = { getElementById: el, querySelector: s => el(s.replace(/^#/, "")),
  querySelectorAll: () => [], addEventListener(){}, createElement: () => ({}) };
globalThis.localStorage = { getItem: () => null, setItem(){}, removeItem(){} };
globalThis.fetch = async () => ({ ok: true, status: 200, text: async () => "[]", json: async () => [] });

const api = new Function(js + "\n; return { cadenceInfo, cadenceCard, PUB_WEEKLY_TARGET };").call(null);
const day = n => new Date(Date.now() - n * 864e5).toISOString().slice(0, 10);
const items = [
  { date: day(0), youtube_url: "https://youtu.be/a" },   // 셈
  { date: day(3), youtube_url: "https://youtu.be/b" },   // 셈
  { date: day(6), youtube_url: "https://youtu.be/c" },   // 셈
  { date: day(8), youtube_url: "https://youtu.be/d" },   // 8일 전 → 제외
  { date: day(1), youtube_url: "" },                      // 미업로드 → 제외
];
const few = [{ date: day(1), youtube_url: "https://youtu.be/a" }];
console.log(JSON.stringify({
  target: api.PUB_WEEKLY_TARGET,
  counted: api.cadenceInfo(items).count,
  over: api.cadenceInfo(items).over,
  underOver: api.cadenceInfo(few).over,
  cardShowsCount: api.cadenceCard(items).includes("최근 7일 발행 3편"),
  cardWarnsWhenOver: api.cadenceCard(items).includes("한 편의 완성도"),
  cardEncouragesWhenUnder: api.cadenceCard(few).includes("좁은 대상"),
}));
