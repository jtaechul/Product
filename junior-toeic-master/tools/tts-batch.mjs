#!/usr/bin/env node
// 점프리시 배치 TTS — Google Cloud Text-to-Speech (docs/content-pipeline.md 5절)
// 개발 단계 1회성 실행. 운영 중에는 절대 호출되지 않는다 (정적 MP3만 서빙).
//
// 준비: docs/tts-guide.md 참고 (Google API 키 발급)
// 사용: GOOGLE_TTS_KEY=발급받은키 node tools/tts-batch.mjs
//  1) 반드시 node tools/import.mjs 를 먼저 실행 (ULID 매핑 생성)
//  2) 완료 후 tools/out/audio/ 에 MP3, tools/out/audio-manifest.json 생성
//  3) R2 업로드 → R2_PUBLIC_BASE=https://... node tools/import.mjs → seed 재적용

import { readFileSync, writeFileSync, mkdirSync, existsSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const CONTENT = join(ROOT, 'content');
const OUT = join(ROOT, 'tools', 'out');
const KEY = process.env.GOOGLE_TTS_KEY;
if (!KEY) {
  console.error('GOOGLE_TTS_KEY 환경변수가 필요합니다. 발급 방법: docs/tts-guide.md');
  process.exit(1);
}
const idmap = JSON.parse(readFileSync(join(CONTENT, '.idmap.json'), 'utf8'));

// 국가·성별 → Google 뉴럴 보이스 (content-pipeline.md 5-2 표)
const VOICES = {
  US: { female: 'en-US-Neural2-C', male: 'en-US-Neural2-A', lang: 'en-US' },
  UK: { female: 'en-GB-Neural2-A', male: 'en-GB-Neural2-B', lang: 'en-GB' },
  AU: { female: 'en-AU-Neural2-A', male: 'en-AU-Neural2-B', lang: 'en-AU' },
};
const RATE = '95%'; // 초등 청취 고려 −5% (음원은 한 벌 — 주니어는 앱에서 0.9배속)
const LETTERS = ['A', 'B', 'C', 'D'];

const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const ssml = (text, tail = '400ms') =>
  `<speak><prosody rate="${RATE}">${esc(text)}</prosody><break time="${tail}"/></speak>`;

async function synth(ssmlText, accent, gender) {
  const v = VOICES[accent];
  const res = await fetch(`https://texttospeech.googleapis.com/v1/text:synthesize?key=${KEY}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      input: { ssml: ssmlText },
      voice: { languageCode: v.lang, name: v[gender] },
      audioConfig: { audioEncoding: 'MP3', sampleRateHertz: 24000 },
    }),
  });
  if (!res.ok) throw new Error(`TTS ${res.status}: ${await res.text()}`);
  const { audioContent } = await res.json();
  return Buffer.from(audioContent, 'base64');
}

const manifest = existsSync(join(OUT, 'audio-manifest.json'))
  ? JSON.parse(readFileSync(join(OUT, 'audio-manifest.json'), 'utf8')) : {};
mkdirSync(join(OUT, 'audio', 'questions'), { recursive: true });
mkdirSync(join(OUT, 'audio', 'passages'), { recursive: true });

let made = 0, skipped = 0, chars = 0;
const files = readdirSync(join(CONTENT, 'questions')).filter((f) => /^L[1-4]\.json$/.test(f)).sort();

for (const file of files) {
  const items = JSON.parse(readFileSync(join(CONTENT, 'questions', file), 'utf8'));
  for (const it of items) {
    let relPath, buf;
    try {
      if (it.type === 'single') {
        const id = idmap[`q:${it.tmp_id}`];
        if (!id) throw new Error('idmap에 없음 — import.mjs 먼저 실행');
        relPath = `audio/questions/${id}.mp3`;
        if (existsSync(join(OUT, relPath))) { manifest[it.tmp_id] = relPath; skipped++; continue; }
        // L1: 문장 1개 / L2: 질문 + 보기 4개 응답을 한 트랙으로
        let text = it.tts_script;
        if (it.part === 'L2') {
          text += ' ... ' + it.choices.map((c, i) => `${LETTERS[i]}. ${c}`).join(' ... ');
        }
        chars += text.length;
        buf = await synth(ssml(text), it.accent, 'female');
      } else {
        const id = idmap[`p:${it.tmp_id}`];
        if (!id) throw new Error('idmap에 없음 — import.mjs 먼저 실행');
        relPath = `audio/passages/${id}.mp3`;
        if (existsSync(join(OUT, relPath))) { manifest[it.tmp_id] = relPath; skipped++; continue; }
        // 화자별 줄 분리 합성 후 이어붙임 (줄 끝 600ms 쉼)
        const lines = it.passage.script.split('\n').filter((l) => l.trim());
        const parts = [];
        for (const line of lines) {
          const m = line.match(/^([A-Z]):\s*(.*)$/);
          const speaker = m ? m[1] : 'N';
          const gender = it.passage.tts_voices?.[speaker] === 'male' ? 'male' : 'female';
          const text = m ? m[2] : line;
          chars += text.length;
          parts.push(await synth(ssml(text, '600ms'), it.passage.accent, gender));
        }
        buf = Buffer.concat(parts);
      }
      writeFileSync(join(OUT, relPath), buf);
      manifest[it.tmp_id] = relPath;
      made++;
      process.stdout.write(`\r생성 ${made} / 건너뜀 ${skipped} (${it.tmp_id})   `);
      await new Promise((r) => setTimeout(r, 150)); // 요청 간격 (쿼터 예의)
    } catch (e) {
      console.error(`\n실패 ${it.tmp_id}: ${e.message}`);
    }
  }
}

writeFileSync(join(OUT, 'audio-manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
console.log(`\n완료 — 생성 ${made}개, 건너뜀 ${skipped}개, 합성 글자수 약 ${chars.toLocaleString()}자`);
console.log(`(Google 무료 쿼터: 뉴럴 월 100만 자 — 이번 사용량은 그 안입니다)`);
console.log(`\n다음 단계 (R2 업로드 후 seed 재생성):`);
console.log(`  1) npx wrangler r2 bucket create jumplish-assets`);
console.log(`  2) cd tools/out && find audio -name '*.mp3' | while read f; do npx wrangler r2 object put "jumplish-assets/$f" --file "$f"; done`);
console.log(`  3) R2 공개 도메인 연결 후: R2_PUBLIC_BASE=https://<공개도메인> node tools/import.mjs`);
console.log(`  4) seed.sql 재적용 (audio_url 반영)`);
