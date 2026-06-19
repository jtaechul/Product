// 게임 상태 + 진행 로직 (렌더와 분리). 기획서 6·7·8·9번.
import { ACTIVITIES, AUTO_ACTIVITY, STATS_META } from "../data/activities.js";
import { MEDIA } from "../data/media.js";
import { ACT_BOND, BOND_THRESHOLD } from "../data/bonds.js";
import { EVENTS } from "../data/events.js";
import { TOTAL_TURNS } from "../config.js";

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// 성장 소프트캡 (기획서 8번): 현재 스탯이 높을수록 상승 효율 감소 → 분산 유도.
function softCapMultiplier(cur) {
  if (cur < 40) return 1.0;
  if (cur < 60) return 0.7;
  if (cur < 80) return 0.5;
  return 0.3;
}

export class GameState {
  constructor() {
    this.turn = 1;                 // 1 ~ 36
    this.stats = {};
    for (const s of STATS_META) this.stats[s.key] = 5; // 시작값 5
    this.stamina = 70;             // 체력
    this.mental = 70;              // 멘탈
    this.money = 100000;           // 보통 난이도 시작 돈
    this.fans = 0;                 // 인지도(팬 수)
    this.filmography = [];         // 출연 기록 (기획서 4·11번)
    this.flags = new Set();        // 특수 플래그(영화제·해외·국민 등)
    this.offers = this.genOffers();// 이번 달 출연 제안
    this.bonds = { hanjiwon: 0, noh: 0, haneul: 0, yusea: 0 }; // 인연 게이지 (기획서 12번)
  }

  raiseBond(id, n) { if (this.bonds[id] !== undefined) this.bonds[id] = clamp(this.bonds[id] + n, 0, 100); }

  // 랜덤 이벤트 추첨 (기획서 13번): 약 38% 확률
  rollEvent() {
    if (Math.random() > 0.38) return null;
    return EVENTS[Math.floor(Math.random() * EVENTS.length)];
  }
  applyEventEffects(effects = {}, flag) {
    for (const [k, v] of Object.entries(effects)) {
      if (k === "mental") this.mental = clamp(this.mental + v, 0, 100);
      else if (k === "stamina") this.stamina = clamp(this.stamina + v, 0, 100);
      else if (k === "money") this.money = Math.max(0, this.money + v);
      else if (k === "fans") this.fans = Math.max(0, this.fans + v);
      else if (this.stats[k] !== undefined) {
        if (v >= 0) this._gainStat(k, v);
        else this.stats[k] = clamp(this.stats[k] + v, 0, 100);
      }
    }
    if (flag) this.flags.add(flag);
  }

  // 이번 달 출연 제안 1~3개 생성 (등장 가능 매체 중)
  genOffers() {
    if ((this.turn - 1) % 3 !== 0) return [];  // 분기(3개월)에 한 번만 제안
    const avail = MEDIA.filter((m) => m.from <= this.turn);
    const pool = [...avail];
    const n = Math.min(pool.length, this.turn > 12 ? 3 : 2);
    const out = [];
    while (out.length < n && pool.length) {
      out.push(pool.splice(Math.floor(Math.random() * pool.length), 1)[0].id);
    }
    return out;
  }

  // 출연 평가 (기획서 11번): 종합점수 vs 기대치 → 등급 → 보상 + 필모 기록
  runProduction(id) {
    const m = MEDIA.find((x) => x.id === id);
    if (!m) return null;
    let P = 0, E = 0;
    for (const [k, v] of Object.entries(m.req)) {
      E += v;
      P += k === "fame" ? this.fans : (this.stats[k] || 0);
    }
    if (this.bonds.hanjiwon >= BOND_THRESHOLD) P *= 1.1; // 매니저 인연: 평가 +10%
    const ratio = E ? P / E : 1;
    let grade = "bad";
    if (ratio >= 1.25) grade = "best";
    else if (ratio >= 1.0) grade = "good";
    else if (ratio >= 0.8) grade = "fair";

    const fameMult = { best: 1.6, good: 1.0, fair: 0.3, bad: 0 }[grade];
    const payMult = { best: 1.0, good: 1.0, fair: 0.7, bad: 0.4 }[grade];
    this.fans = Math.max(0, this.fans + Math.round(m.fame * fameMult));
    this.money += Math.round(m.pay * 10000 * payMult);
    if (grade === "best" || grade === "good") {
      for (const [k, v] of Object.entries(m.gain || {})) this._gainStat(k, grade === "best" ? v * 1.5 : v);
      this.mental = clamp(this.mental + (grade === "best" ? 15 : 8), 0, 100);
      if (m.flag) this.flags.add(m.flag);
    } else if (grade === "bad") {
      this.mental = clamp(this.mental - 12, 0, 100);
    }
    if (this.bonds.yusea >= BOND_THRESHOLD && (grade === "best" || grade === "good")) this._gainStat("acting", 2); // 라이벌 자극
    this.raiseBond("hanjiwon", 10); this.raiseBond("yusea", 6);
    this.filmography.push({ turn: this.turn, label: this.label, id: m.id, name: m.name, grade });
    return { media: m, grade };
  }

  // 현재 턴 → "고1·5월" 형태
  get label() {
    const grade = ["고1", "고2", "고3"][Math.floor((this.turn - 1) / 12)] || "졸업";
    let month = ((this.turn - 1) % 12) + 3;
    if (month > 12) month -= 12;
    return `${grade}·${month}월`;
  }

  get isLastTurn() {
    return this.turn >= TOTAL_TURNS;
  }

  // 능력치 1종 상승 (소프트캡 + 멘탈 보정 적용)
  _gainStat(key, base) {
    let mult = softCapMultiplier(this.stats[key]);
    if (this.mental < 30) mult *= 0.5;        // 멘탈 낮으면 -50% (기획서 7번)
    else if (this.mental >= 80) mult *= 1.2;  // 멘탈 높으면 +20%
    this.stats[key] = clamp(Math.round(this.stats[key] + base * mult), 0, 100);
  }

  _applyOne(act) {
    if (!act) return;
    // 인연 보너스: 노교수(연기 효율 +20%), 박하늘(멘탈 회복 +30%)
    const actBoost = act.cat === "acting" && this.bonds.noh >= BOND_THRESHOLD ? 1.2 : 1.0;
    for (const [k, v] of Object.entries(act.effects || {})) {
      if (k === "fame") this.fans = Math.max(0, this.fans + v);
      else if (this.stats[k] !== undefined) this._gainStat(k, v * actBoost);
    }
    if (act.stamina) this.stamina = clamp(this.stamina + act.stamina, 0, 100);
    if (act.mental) {
      let mv = act.mental;
      if (mv > 0 && this.bonds.haneul >= BOND_THRESHOLD) mv = Math.round(mv * 1.3);
      this.mental = clamp(this.mental + mv, 0, 100);
    }
    if (act.money) this.money = Math.max(0, this.money + act.money);
  }

  // 선택한 활동 id 배열(최대 2)로 한 달 진행 → 정산 후 다음 턴.
  advance(selectedIds) {
    const before = { stamina: this.stamina, mental: this.mental, money: this.money, fans: this.fans };
    // 1) 자동: 학교 수업
    this._applyOne(AUTO_ACTIVITY);
    // 2) 선택 활동
    for (const id of selectedIds) {
      this._applyOne(ACTIVITIES.find((a) => a.id === id));
      if (ACT_BOND[id]) this.raiseBond(ACT_BOND[id], 8);
    }
    // 3) 매달 용돈 +50,000
    this.money += 50000;
    // 4) 턴 경과 + 다음 달 출연 제안 갱신
    this.turn += 1;
    this.offers = this.genOffers();
    return {
      d: {
        stamina: this.stamina - before.stamina,
        mental: this.mental - before.mental,
        money: this.money - before.money,
        fans: this.fans - before.fans,
      },
    };
  }

  // 돈을 "18만" 형태로
  moneyShort() {
    return `${Math.floor(this.money / 10000)}만`;
  }
}
