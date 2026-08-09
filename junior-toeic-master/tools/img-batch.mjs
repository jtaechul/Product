#!/usr/bin/env node
// 점프리시 배치 그림 생성 — L1(사진 고르기) 보기 4컷 (docs/content-pipeline.md 6절)
// 개발 단계 1회성 실행. 운영 중에는 절대 호출되지 않는다 (정적 이미지만 서빙).
//
// Pollinations.ai(무료·키 불필요)로 choice_image_prompts 4개를 각각 그림으로 만든다.
// 이 저장소의 개발 샌드박스는 외부망이 막혀 있어, 실제 실행은 GitHub Actions
// (.github/workflows/generate-l1-images.yml)에서 한다.
//
// 사용: node tools/img-batch.mjs
//  1) 반드시 node tools/import.mjs 를 먼저 실행 (ULID 매핑 생성)
//  2) 산출: public/img/l1/{question_id}-{0..3}.jpg  (이미 있으면 건너뜀 — 재실행 안전)
//  3) 한 문항의 4컷이 모두 만들어지면 content/questions/L1.json 의 status를 active로 올린다
//
// 옵션 환경변수
//   IMG_DELAY  요청 간격 ms (기본 1200 — 무료 서비스 예의)
//   IMG_LIMIT  테스트용 — 앞에서 N컷만 생성하고 중단

import { readFileSync, writeFileSync, mkdirSync, existsSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const CONTENT = join(ROOT, 'content');
const OUT_DIR = join(ROOT, 'public', 'img', 'l1');
const DELAY = Number(process.env.IMG_DELAY || 1200);
const LIMIT = Number(process.env.IMG_LIMIT || 0);

const idmap = JSON.parse(readFileSync(join(CONTENT, '.idmap.json'), 'utf8'));
const l1Path = join(CONTENT, 'questions', 'L1.json');
const items = JSON.parse(readFileSync(l1Path, 'utf8'));

// 4컷이 같은 화풍으로 나오도록 고정 스타일 접두어를 붙인다.
// 실제 TOEIC Bridge Part 1은 흑백 선화 일러스트 — 실전과 동일한 룩으로 맞춘다.
// safe=true: 아동 서비스이므로 세이프 필터 필수. nologo: 워터마크 제거.
const STYLE = 'Simple black and white line drawing illustration, like a standardized English ' +
  'test picture, clean bold outlines, monochrome, no color, minimal shading, plain white ' +
  'background, one clear subject, no text, no letters';
const urlFor = (prompt, seed) =>
  'https://image.pollinations.ai/prompt/' + encodeURIComponent(`${STYLE}. ${prompt}`) +
  `?width=512&height=512&nologo=true&safe=true&seed=${seed}`;

// 문항·컷마다 고정 시드 → 재실행해도 같은 그림 (결정적)
const seedOf = (tmpId, i) => {
  let h = 0;
  for (const ch of `${tmpId}#${i}`) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return h % 1000000;
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function fetchImage(url, tries = 4) {
  for (let attempt = 1; ; attempt++) {
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(90000) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const buf = Buffer.from(await res.arrayBuffer());
      // JPEG 매직바이트 + 최소 크기 검사 (에러 페이지·빈 응답 차단)
      if (buf.length < 5000 || buf[0] !== 0xFF || buf[1] !== 0xD8) {
        throw new Error(`이미지가 아닌 응답 (${buf.length}B)`);
      }
      return buf;
    } catch (e) {
      if (attempt >= tries) throw e;
      const wait = 3000 * attempt;
      process.stdout.write(`\n  재시도 ${attempt}/${tries - 1} (${e.message}) — ${wait}ms 대기`);
      await sleep(wait);
    }
  }
}

mkdirSync(OUT_DIR, { recursive: true });

// 스타일이 바뀌면 기존 그림을 전부 지우고 새로 뽑는다 (마커 파일로 감지).
// "이미 있으면 건너뜀" 규칙 때문에, 이 장치가 없으면 옛 스타일이 영영 남는다.
const styleHash = (() => { let h = 0; for (const ch of STYLE) h = (h * 31 + ch.charCodeAt(0)) >>> 0; return String(h); })();
const markerPath = join(OUT_DIR, '.style');
const oldHash = existsSync(markerPath) ? readFileSync(markerPath, 'utf8').trim() : null;
if (oldHash !== styleHash) {
  const { readdirSync, unlinkSync } = await import('node:fs');
  const stale = readdirSync(OUT_DIR).filter((f) => f.endsWith('.jpg'));
  for (const f of stale) unlinkSync(join(OUT_DIR, f));
  if (stale.length) console.log(`스타일 변경 감지 — 기존 ${stale.length}컷 삭제 후 재생성`);
  writeFileSync(markerPath, styleHash + '\n');
}

let made = 0, skipped = 0, failed = 0;
let changed = false;

outer:
for (const it of items) {
  const qid = idmap[`q:${it.tmp_id}`];
  if (!qid) { console.error(`${it.tmp_id}: idmap에 없음 — import.mjs 먼저 실행`); failed += 4; continue; }
  if (!Array.isArray(it.choice_image_prompts) || it.choice_image_prompts.length !== 4) {
    console.error(`${it.tmp_id}: choice_image_prompts 4개 필요`); failed += 4; continue;
  }

  let ok = 0;
  for (let i = 0; i < 4; i++) {
    if (LIMIT && made >= LIMIT) break outer;
    const file = join(OUT_DIR, `${qid}-${i}.jpg`);
    if (existsSync(file) && statSync(file).size > 5000) { ok++; skipped++; continue; }
    try {
      const buf = await fetchImage(urlFor(it.choice_image_prompts[i], seedOf(it.tmp_id, i)));
      writeFileSync(file, buf);
      made++; ok++;
      process.stdout.write(`\r생성 ${made} / 건너뜀 ${skipped} / 실패 ${failed} (${it.tmp_id}#${i})   `);
      await sleep(DELAY);
    } catch (e) {
      failed++;
      console.error(`\n실패 ${it.tmp_id}#${i}: ${e.message}`);
    }
  }
  // 4컷이 모두 갖춰진 문항만 공개(active) — 일부만 있으면 draft 유지
  if (ok === 4 && it.status !== 'active') { it.status = 'active'; changed = true; }
}

if (changed) writeFileSync(l1Path, JSON.stringify(items, null, 2) + '\n');
console.log(`\n완료 — 생성 ${made}컷, 건너뜀 ${skipped}컷, 실패 ${failed}컷` +
  (changed ? ' / L1.json status 갱신됨' : ''));
if (failed) { console.log('실패분은 다시 실행하면 이어서 만듭니다.'); process.exit(1); }
