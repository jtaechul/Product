// 세이브/로드 (기획서 9·19번). GameState ↔ localStorage.
import { GameState } from "./game.js";

const KEY = "spotlight_save";

export function saveGame(game) {
  try {
    const data = game.toData();
    data.savedAt = Date.now();
    localStorage.setItem(KEY, JSON.stringify(data));
    return true;
  } catch (e) { return false; }
}

export function loadSaveData() {
  try { const s = localStorage.getItem(KEY); return s ? JSON.parse(s) : null; } catch (e) { return null; }
}

export function loadGame() {
  const d = loadSaveData();
  return d ? GameState.fromData(d) : null;
}

export function hasSave() { return !!loadSaveData(); }
export function clearSave() { try { localStorage.removeItem(KEY); } catch (e) {} }

// 저장 시각을 "고2·5월 · 3분 전" 같은 짧은 라벨로
export function saveLabel() {
  const d = loadSaveData();
  if (!d) return null;
  const grade = ["고1", "고2", "고3"][Math.floor(((d.turn || 1) - 1) / 12)] || "졸업";
  let month = (((d.turn || 1) - 1) % 12) + 3; if (month > 12) month -= 12;
  return `${grade}·${month}월`;
}
