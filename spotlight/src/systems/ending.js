// 엔딩 판정 + 40년 회고 서사 생성 (기획서 15번). 수치는 화면에 노출하지 않는다.
import { ENDINGS, FIELD_OF, AWARD_OF, bondPeople } from "../data/endings.js";
import { storageGet, storageSet } from "./platform.js";

export const ENDING_COUNT = ENDINGS.length;

// 매체 규모 순위(대표작 선정용): 클수록 큰 작품
const MEDIA_RANK = {
  webdrama: 1, shortdrama: 2, shortfilm: 3, dramabit: 4, cf: 5, musical: 6, ott: 7, filmlead: 8, seasondrama: 9,
};

function buildContext(game) {
  const s = game.stats;
  const praised = game.filmography.filter((f) => f.grade === "best" || f.grade === "good");
  // 분야별 호평작 분포
  const fieldCount = {};
  for (const f of praised) {
    const fld = FIELD_OF[f.id] || "drama";
    fieldCount[fld] = (fieldCount[fld] || 0) + 1;
  }
  let fieldTop = null, top = 0;
  for (const k of Object.keys(fieldCount)) if (fieldCount[k] > top) { top = fieldCount[k]; fieldTop = k; }
  // 대표작 = 호평작 중 매체 규모 최상위
  let bestWork = null, bestRank = -1;
  for (const f of praised) { const r = MEDIA_RANK[f.id] || 0; if (r > bestRank) { bestRank = r; bestWork = f; } }
  return {
    act: s.acting, emo: s.emotion, voc: s.vocal, looks: s.looks, sing: s.singing,
    dance: s.dance, study: s.study, char: s.character, net: s.network,
    fame: game.fans,
    actAvg: (s.acting + s.emotion + s.vocal) / 3,
    flags: game.flags,
    bondNoh: game.bonds.noh || 0,
    praised, praisedCount: praised.length, fieldCount, fieldTop,
    firstWork: game.filmography[0] || null,
    bestWork,
    people: bondPeople(game.bonds),
    name: game.heroName || "그",
  };
}

function composeStory(c, e) {
  const debut = c.firstWork
    ? `열일곱의 ${c.name}. 작은 작품 「${c.firstWork.name}」으로 카메라 앞에 처음 섰다.`
    : `열일곱의 ${c.name}. 길거리 캐스팅 명함 한 장에서 모든 것이 시작됐다.`;
  const rep = c.bestWork ? `대표작 「${c.bestWork.name}」은 오래도록 회자됐다.` : "";
  const mid = e.core(c);
  const awards = Object.keys(AWARD_OF).filter((k) => c.flags.has(k)).map((k) => AWARD_OF[k]);
  const awardLine = awards.length ? `그 길에는 영광도 따랐다 — ${awards.join(", ")}.` : "";
  const peopleLine = c.people.length ? `무엇보다, 곁에는 늘 ${c.people.join("·")}이(가) 있었다.` : "";
  const closing = `예순의 ${c.name}, 지난 40년을 돌아보며 말했다.\n"${e.quote}"`;
  return [debut, mid, rep, awardLine, peopleLine, closing].filter(Boolean).join("\n\n");
}

// 게임 상태 → 최종 엔딩 결과
export function computeEnding(game) {
  const c = buildContext(game);
  const e = ENDINGS.find((x) => x.when(c)) || ENDINGS[ENDINGS.length - 1];
  return {
    id: e.id, emoji: e.emoji, title: e.title, trait: e.trait, illust: e.illust,
    story: composeStory(c, e),
    filmography: c.praised.slice().reverse(),         // 호평작(최신순)
    awards: Object.keys(AWARD_OF).filter((k) => c.flags.has(k)).map((k) => AWARD_OF[k]),
    people: c.people,
  };
}

// 엔딩 도감 (플랫폼 저장소: 토스=네이티브 Storage, 웹=localStorage)
const DEX_KEY = "spotlight_ending_dex";
export function saveToDex(id) {
  try {
    const set = new Set(JSON.parse(storageGet(DEX_KEY) || "[]"));
    set.add(id);
    storageSet(DEX_KEY, JSON.stringify([...set]));
    return set.size;
  } catch (e) { return 0; }
}
export function dexCount() {
  try { return new Set(JSON.parse(storageGet(DEX_KEY) || "[]")).size; } catch (e) { return 0; }
}

// ── 리더보드용 커리어 점수 (토스게임센터 제출용) ──────────────────────
// 화면에는 노출하지 않는 내부 점수: 능력치 총합(최대 1000) + 팬(500 상한)
// + 호평작×15 + 수상×40. 균형 성장·호평·수상이 높을수록 상위.
export function computeCareerScore(game) {
  const s = game.stats;
  const statTotal = Object.values(s).reduce((a, b) => a + (b || 0), 0);
  const praised = game.filmography.filter((f) => f.grade === "best" || f.grade === "good").length;
  const awards = Object.keys(AWARD_OF).filter((k) => game.flags.has(k)).length;
  return Math.round(statTotal + Math.min(game.fans, 500) + praised * 15 + awards * 40);
}
