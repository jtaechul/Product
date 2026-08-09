#!/usr/bin/env node
// 점프리시 효과음 배치 다운로드 — Freesound API (개발 단계 1회성, 운영 중 호출 0)
// Web Audio 합성음이 빈약해 실제 사운드로 교체한다. 상용 B2B이므로 **CC0(저작권
// 완전 포기) 라이선스만** 검색해 받는다 — 표기 의무·분쟁 소지 없음.
//
// 사용: FREESOUND_API_KEY=<키> node tools/sfx-batch.mjs
//  - 산출: public/sfx/{select,correct,wrong,done}.mp3 + CREDITS.md(출처 기록)
//  - 이미 있는 파일은 건너뜀. 이 샌드박스는 외부망이 막혀 있어 실제 실행은
//    GitHub Actions(generate-sfx.yml)에서 한다.

import { writeFileSync, mkdirSync, existsSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const OUT = join(ROOT, 'public', 'sfx');
const KEY = process.env.FREESOUND_API_KEY;
if (!KEY) {
  console.error('FREESOUND_API_KEY 시크릿이 필요합니다.');
  console.error('발급: https://freesound.org/apiv2/apply/  → 저장소 시크릿 FREESOUND_API_KEY 로 등록');
  process.exit(1);
}

// 역할별 검색어 — 아동 학습 앱 톤: 밝고 짧고 부드럽게 (오답도 기죽지 않는 소리)
const ROLES = {
  select: { q: 'ui click pop soft', dur: '[0 TO 1]' },
  correct: { q: 'correct answer chime bright', dur: '[0 TO 2]' },
  wrong: { q: 'wrong answer gentle soft buzzer', dur: '[0 TO 2]' },
  done: { q: 'success fanfare short jingle win', dur: '[0.5 TO 4]' },
};

async function searchCC0(query, dur) {
  const url = 'https://freesound.org/apiv2/search/text/'
    + `?query=${encodeURIComponent(query)}`
    + `&filter=${encodeURIComponent(`license:"Creative Commons 0" duration:${dur}`)}`
    + '&sort=downloads_desc&page_size=5'
    + '&fields=id,name,username,url,license,previews,avg_rating,num_downloads'
    + `&token=${KEY}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Freesound ${res.status}: ${(await res.text()).slice(0, 150)}`);
  const { results } = await res.json();
  return results?.[0] || null;  // 다운로드 수 1위
}

mkdirSync(OUT, { recursive: true });
const credits = ['# 효과음 출처 (Freesound, 전부 CC0 — 저작권 표기 의무 없음)', ''];
let made = 0, skipped = 0, failed = 0;

for (const [role, { q, dur }] of Object.entries(ROLES)) {
  const file = join(OUT, `${role}.mp3`);
  if (existsSync(file) && statSync(file).size > 1000) { skipped++; continue; }
  try {
    const hit = await searchCC0(q, dur);
    if (!hit) throw new Error(`CC0 검색 결과 없음: "${q}"`);
    // preview-hq-mp3는 토큰 없이 받을 수 있는 공개 CDN 주소 (짧은 효과음엔 충분한 음질)
    const mp3 = await fetch(hit.previews['preview-hq-mp3']);
    if (!mp3.ok) throw new Error(`다운로드 실패 ${mp3.status}`);
    const buf = Buffer.from(await mp3.arrayBuffer());
    if (buf.length < 1000) throw new Error('빈 파일');
    writeFileSync(file, buf);
    credits.push(`- ${role}.mp3 — "${hit.name}" by ${hit.username} (${hit.url}) · CC0 · 다운로드 ${hit.num_downloads}회`);
    made++;
    console.log(`${role}: "${hit.name}" (${(buf.length / 1024).toFixed(0)}KB)`);
    await new Promise((r) => setTimeout(r, 800));  // 무료 API 예의 (분당 60회 제한)
  } catch (e) {
    failed++;
    console.error(`${role} 실패: ${e.message}`);
  }
}

if (made) writeFileSync(join(OUT, 'CREDITS.md'), credits.join('\n') + '\n');
console.log(`완료 — 받음 ${made}, 건너뜀 ${skipped}, 실패 ${failed}`);
if (failed) process.exit(1);
