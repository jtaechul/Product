#!/usr/bin/env node
// 점프리시 캐릭터·배경 배치 생성 — Gemini 이미지 생성 (개발 단계 1회성, 운영 중 호출 0)
//
// 등반 지도에 올릴 동물 캐릭터 6종 + 산 배경 1장을 한 번에 만든다.
// 토큰을 아끼려고 한 번에 다 뽑고, 이미 있는 파일은 건너뛴다(재실행 안전).
//
// 사용: GEMINI_API_KEY=<키> node tools/char-batch.mjs
//  - 산출: public/img/char/{key}.png (캐릭터 6), public/img/map/mountain.png (배경 1)
//  - 이 샌드박스는 외부망이 막혀 있어 실제 실행은 GitHub Actions(generate-chars.yml).

import { writeFileSync, mkdirSync, existsSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const KEY = process.env.GEMINI_API_KEY;
if (!KEY) {
  console.error('GEMINI_API_KEY 시크릿이 필요합니다 (저장소 시크릿 GEMINI_API_KEY_JUMPLISH 를 주입하세요).');
  process.exit(1);
}
const MODEL = process.env.IMG_MODEL || 'gemini-2.5-flash-image';

// 6종이 한 세트로 보이도록 화풍 문구를 공유한다. 배경은 반드시 단색(흰색) —
// 앱에서 산 위에 올려야 하므로 배경이 있으면 네모난 사각형이 그대로 보인다.
const STYLE = 'cute kawaii mascot character for a kids English learning app, '
  + 'simple flat vector illustration, bold clean outlines, bright cheerful colors, '
  + 'big friendly eyes, chibi proportions, front view, standing pose, full body, '
  + 'centered, plain pure white background, no text, no letters, no shadow';

const CHARACTERS = {
  squirrel: 'a cheerful brown squirrel with a big fluffy tail',
  penguin: 'a happy little blue-grey penguin with an orange beak',
  cat: 'a friendly orange tabby cat sitting upright',
  fox: 'a smiling young orange fox with white chest fur',
  rabbit: 'a cute white rabbit with long ears and pink inner ears',
  bear: 'a round soft honey-brown bear cub waving',
};

const SCENES = {
  'map/mountain': 'A tall green mountain seen from the front for a children\'s progress map, '
    + 'simple flat vector illustration, soft rounded shapes, gentle winding trail path from '
    + 'bottom to the summit, small pine trees along the slope, a flag at the very top, '
    + 'sunny pastel sky with a few soft clouds, bright cheerful colors, no text, no letters, '
    + 'no characters, no people',
};

async function generate(prompt, tries = 3) {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent?key=${KEY}`;
  for (let attempt = 1; ; attempt++) {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }] }),
    });
    if (res.status === 429 || res.status >= 500) {
      if (attempt >= tries) throw new Error(`Gemini ${res.status}: ${(await res.text()).slice(0, 160)}`);
      const wait = 4000 * attempt;
      console.log(`  ${res.status} — ${wait}ms 후 재시도`);
      await new Promise((r) => setTimeout(r, wait));
      continue;
    }
    if (!res.ok) throw new Error(`Gemini ${res.status}: ${(await res.text()).slice(0, 200)}`);
    const json = await res.json();
    const part = json.candidates?.[0]?.content?.parts?.find((p) => p.inlineData);
    if (!part) throw new Error(`이미지가 없는 응답: ${JSON.stringify(json).slice(0, 200)}`);
    const buf = Buffer.from(part.inlineData.data, 'base64');
    // PNG 매직바이트 확인 (에러 페이지·빈 응답 차단)
    if (buf.length < 5000 || buf[0] !== 0x89 || buf[1] !== 0x50) {
      throw new Error(`PNG가 아닌 응답 (${buf.length}B)`);
    }
    return buf;
  }
}

let made = 0, skipped = 0, failed = 0;
const jobs = [
  ...Object.entries(CHARACTERS).map(([k, d]) => [`char/${k}`, `${STYLE}. The character is ${d}.`]),
  ...Object.entries(SCENES),
];

for (const [rel, prompt] of jobs) {
  const file = join(ROOT, 'public', 'img', `${rel}.png`);
  if (existsSync(file) && statSync(file).size > 5000) { skipped++; continue; }
  mkdirSync(dirname(file), { recursive: true });
  try {
    const buf = await generate(prompt);
    writeFileSync(file, buf);
    made++;
    console.log(`${rel}: ${(buf.length / 1024).toFixed(0)}KB`);
    await new Promise((r) => setTimeout(r, 1500));
  } catch (e) {
    failed++;
    console.error(`${rel} 실패: ${e.message}`);
  }
}

console.log(`완료 — 생성 ${made}, 건너뜀 ${skipped}, 실패 ${failed}`);
if (failed) process.exit(1);
