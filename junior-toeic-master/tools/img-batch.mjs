#!/usr/bin/env node
// 점프리시 L1(사진 고르기) 보기 4컷 — 픽사베이에서 "실제 사진"을 찾아 내려받는다.
// (v3: AI 생성 → 사진 검색. AI가 그린 그림은 손가락·개수·상황이 자주 틀려서 폐기)
//
// 개발 단계 1회성 실행. 운영 중에는 절대 호출되지 않는다 (내려받아 커밋한 파일만 서빙).
// 실제 실행은 GitHub Actions(.github/workflows/generate-l1-images.yml) — 개발 샌드박스는 외부망이 막혀 있다.
//
// 사용: PIXABAY_API_KEY=<키> node tools/img-batch.mjs
//  1) 반드시 node tools/import.mjs 를 먼저 실행 (ULID 매핑 생성)
//  2) 산출: public/img/l1/{question_id}-{0..3}.jpg (이미 있으면 건너뜀 — 재실행 안전)
//           content/l1-photos.json (어떤 사진을 썼는지 출처 기록 — 사람이 눈으로 검수)
//  3) 한 문항의 4컷이 모두 갖춰지면 content/questions/L1.json 의 status를 active로 올린다
//
// ⭐ 엉뚱한 사진 차단: 검색 결과를 그냥 쓰지 않는다. 사진에 붙은 태그를 보고
//    need(반드시 있어야 할 말)를 모두 갖고 avoid(있으면 안 되는 말)가 하나도 없는
//    후보만 채택한다. 못 찾으면 그 컷은 실패로 남기고 다음에 다시 시도한다.
//    → "자전거 타는 그림" 자리에 연날리기 사진이 들어가는 사고를 구조적으로 막는다.

import { readFileSync, writeFileSync, mkdirSync, existsSync, statSync, readdirSync, unlinkSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const CONTENT = join(ROOT, 'content');
const OUT_DIR = join(ROOT, 'public', 'img', 'l1');
const KEY = process.env.PIXABAY_API_KEY;
const DELAY = Number(process.env.IMG_DELAY || 800);   // 픽사베이 권장 한도(분당 100회) 여유
const LIMIT = Number(process.env.IMG_LIMIT || 0);

if (!KEY) {
  console.error('PIXABAY_API_KEY가 필요합니다 (저장소 시크릿 PIXABAY_API_KEY를 주입하세요).');
  process.exit(1);
}

const idmap = JSON.parse(readFileSync(join(CONTENT, '.idmap.json'), 'utf8'));
const l1Path = join(CONTENT, 'questions', 'L1.json');
const items = JSON.parse(readFileSync(l1Path, 'utf8'));
const photoPath = join(CONTENT, 'l1-photos.json');
const photos = existsSync(photoPath) ? JSON.parse(readFileSync(photoPath, 'utf8')) : {};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function get(url, tries = 4) {
  for (let attempt = 1; ; attempt++) {
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(60000) });
      if (res.status === 429) throw new Error('요청이 너무 잦음(429)');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res;
    } catch (e) {
      if (attempt >= tries) throw e;
      const wait = 4000 * attempt;
      console.log(`  재시도 ${attempt} (${e.message}) — ${wait}ms 대기`);
      await sleep(wait);
    }
  }
}

// 검색 → 태그 조건을 통과하는 첫 후보. 가로 사진을 먼저 보고, 없으면 방향 제한을 푼다.
async function findPhoto({ q, need = [], avoid = [] }) {
  for (const orientation of ['horizontal', 'all']) {
    const url = 'https://pixabay.com/api/?' + new URLSearchParams({
      key: KEY, q, image_type: 'photo', safesearch: 'true', lang: 'en',
      order: 'popular', per_page: '40', orientation,
    });
    const { hits = [] } = await (await get(url)).json();
    for (const h of hits) {
      const tags = String(h.tags || '').toLowerCase();
      if (!need.every((w) => tags.includes(w.toLowerCase()))) continue;
      if (avoid.some((w) => tags.includes(w.toLowerCase()))) continue;
      return h;
    }
    await sleep(DELAY);
  }
  return null;
}

mkdirSync(OUT_DIR, { recursive: true });

// 그림 출처가 바뀌면(AI 생성 → 사진) 예전 파일을 전부 지우고 새로 받는다.
// "이미 있으면 건너뜀" 규칙 때문에 이 장치가 없으면 옛 그림이 영영 남는다.
const SOURCE = 'pixabay-photo-v1';
const markerPath = join(OUT_DIR, '.source');
if (!existsSync(markerPath) || readFileSync(markerPath, 'utf8').trim() !== SOURCE) {
  const stale = readdirSync(OUT_DIR).filter((f) => f.endsWith('.jpg'));
  for (const f of stale) unlinkSync(join(OUT_DIR, f));
  const oldStyle = join(OUT_DIR, '.style');
  if (existsSync(oldStyle)) unlinkSync(oldStyle);
  if (stale.length) console.log(`그림 출처 변경 — 예전 ${stale.length}컷 삭제 후 다시 받음`);
  for (const k of Object.keys(photos)) delete photos[k];
  writeFileSync(markerPath, SOURCE + '\n');
}

let made = 0, skipped = 0, failed = 0, changed = false;

outer:
for (const it of items) {
  const qid = idmap[`q:${it.tmp_id}`];
  if (!qid) { console.error(`${it.tmp_id}: idmap에 없음 — import.mjs 먼저 실행`); failed += 4; continue; }
  const queries = it.choice_image_queries;
  if (!Array.isArray(queries) || queries.length !== 4) {
    console.error(`${it.tmp_id}: choice_image_queries 4개 필요`); failed += 4; continue;
  }

  let ok = 0;
  for (let i = 0; i < 4; i++) {
    if (LIMIT && made >= LIMIT) break outer;
    const file = join(OUT_DIR, `${qid}-${i}.jpg`);
    if (existsSync(file) && statSync(file).size > 5000) { ok++; skipped++; continue; }
    try {
      const hit = await findPhoto(queries[i]);
      if (!hit) throw new Error(`조건에 맞는 사진 없음 (검색어 "${queries[i].q}")`);
      const buf = Buffer.from(await (await get(hit.webformatURL)).arrayBuffer());
      if (buf.length < 5000 || buf[0] !== 0xFF || buf[1] !== 0xD8) {
        throw new Error(`사진이 아닌 응답 (${buf.length}B)`);
      }
      writeFileSync(file, buf);
      // 어떤 사진을 왜 골랐는지 남긴다 — 사람이 나중에 눈으로 검수·교체할 수 있게
      photos[`${qid}-${i}`] = {
        tmp_id: `${it.tmp_id}#${i}`, query: queries[i].q, tags: hit.tags,
        pixabay_id: hit.id, page: hit.pageURL, by: hit.user,
      };
      made++; ok++;
      console.log(`${it.tmp_id}#${i} ← ${hit.tags} (${hit.pageURL})`);
      await sleep(DELAY);
    } catch (e) {
      failed++;
      console.error(`실패 ${it.tmp_id}#${i}: ${e.message}`);
    }
  }
  // 4컷이 모두 갖춰진 문항만 공개(active) — 일부만 있으면 draft 유지
  const want = ok === 4 ? 'active' : 'draft';
  if (it.status !== want) { it.status = want; changed = true; }
}

writeFileSync(photoPath, JSON.stringify(photos, null, 2) + '\n');
if (changed) writeFileSync(l1Path, JSON.stringify(items, null, 2) + '\n');
console.log(`\n완료 — 새로 받음 ${made}컷, 건너뜀 ${skipped}컷, 실패 ${failed}컷` +
  (changed ? ' / L1.json status 갱신됨' : ''));
if (failed) { console.log('실패분은 검색어를 손보고 다시 실행하면 이어서 받습니다.'); process.exit(1); }
