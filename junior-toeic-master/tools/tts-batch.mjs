#!/usr/bin/env node
// 점프리시 배치 TTS — Gemini API (docs/content-pipeline.md 5절)
// 개발 단계 1회성 실행. 운영 중에는 절대 호출되지 않는다 (정적 음원만 서빙).
//
// 준비: docs/tts-guide.md 참고 (Gemini API 키 — 기존 키 그대로 사용)
// 사용: GEMINI_API_KEY=발급받은키 node tools/tts-batch.mjs
//  1) 반드시 node tools/import.mjs 를 먼저 실행 (ULID 매핑 생성)
//  2) 완료 후 tools/out/audio/ 에 음원, tools/out/audio-manifest.json 생성
//  3) R2 업로드 → R2_PUBLIC_BASE=https://... node tools/import.mjs → seed 재적용
//
// 옵션 환경변수
//   TTS_MODEL   기본 gemini-2.5-flash-preview-tts (고품질: gemini-2.5-pro-preview-tts)
//   TTS_DELAY   요청 간격 ms, 기본 1500 (무료 등급은 분당 요청 수가 낮아 넉넉히 둔다)
//   TTS_LIMIT   테스트용 — 앞에서 N개만 생성하고 중단
//
// Google Cloud TTS와 다른 점
//   - 발음(미/영/호)은 보이스 ID가 아니라 프롬프트 지시문으로 지정한다.
//   - 응답이 raw PCM(24kHz·16bit·모노)이라 WAV 헤더를 직접 붙인다.
//     ffmpeg가 설치돼 있으면 MP3로 자동 변환하고 WAV는 지운다.
//   - L3·L4 대화는 멀티 스피커 기능으로 한 번에 합성한다(줄별 합성·이어붙이기 불필요).

import { readFileSync, writeFileSync, mkdirSync, existsSync, readdirSync, unlinkSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const CONTENT = join(ROOT, 'content');
const OUT = join(ROOT, 'tools', 'out');
const KEY = process.env.GEMINI_API_KEY || process.env.GOOGLE_TTS_KEY;
if (!KEY) {
  console.error('GEMINI_API_KEY 환경변수가 필요합니다. 발급 방법: docs/tts-guide.md');
  process.exit(1);
}
const MODEL = process.env.TTS_MODEL || 'gemini-2.5-flash-preview-tts';
const DELAY = Number(process.env.TTS_DELAY || 1500);
const LIMIT = Number(process.env.TTS_LIMIT || 0);
const idmap = JSON.parse(readFileSync(join(CONTENT, '.idmap.json'), 'utf8'));

// ffmpeg가 있으면 MP3로 줄인다(WAV는 약 15배 크다). 없으면 WAV 그대로 쓴다 — 브라우저 재생 가능.
const HAS_FFMPEG = (() => {
  try { execFileSync('ffmpeg', ['-version'], { stdio: 'ignore' }); return true; } catch { return false; }
})();
const EXT = HAS_FFMPEG ? 'mp3' : 'wav';

// 발음 지시문 — Gemini 보이스는 억양이 고정돼 있지 않아 프롬프트로 지정한다.
const ACCENT_PROMPT = {
  US: 'a standard American English accent',
  UK: 'a standard British English (Received Pronunciation) accent',
  AU: 'a standard Australian English accent',
};
// 국가·성별 → Gemini 프리빌트 보이스 (억양은 위 지시문이 담당, 여기선 음색만 구분)
const VOICES = {
  US: { female: 'Kore', male: 'Puck' },
  UK: { female: 'Leda', male: 'Charon' },
  AU: { female: 'Aoede', male: 'Fenrir' },
};
// 초등 청취를 고려해 또박또박·약간 느리게 (음원은 한 벌 — 주니어는 앱에서 0.9배속)
const PACE = 'clearly and at a slightly slow, steady pace suitable for young English learners';
const LETTERS = ['A', 'B', 'C', 'D'];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// PCM(24kHz·16bit·모노) → WAV 헤더 44바이트를 앞에 붙인다.
function toWav(pcm, sampleRate = 24000, channels = 1, bits = 16) {
  const head = Buffer.alloc(44);
  head.write('RIFF', 0);
  head.writeUInt32LE(36 + pcm.length, 4);
  head.write('WAVE', 8);
  head.write('fmt ', 12);
  head.writeUInt32LE(16, 16);
  head.writeUInt16LE(1, 20);
  head.writeUInt16LE(channels, 22);
  head.writeUInt32LE(sampleRate, 24);
  head.writeUInt32LE((sampleRate * channels * bits) / 8, 28);
  head.writeUInt16LE((channels * bits) / 8, 32);
  head.writeUInt16LE(bits, 34);
  head.write('data', 36);
  head.writeUInt32LE(pcm.length, 40);
  return Buffer.concat([head, pcm]);
}

// mimeType 예: "audio/L16;codec=pcm;rate=24000"
const rateOf = (mime) => Number(/rate=(\d+)/.exec(mime || '')?.[1] || 24000);

async function callTts(prompt, speechConfig, tries = 4) {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent?key=${KEY}`;
  for (let attempt = 1; ; attempt++) {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: { responseModalities: ['AUDIO'], speechConfig },
      }),
    });
    if (res.status === 429 || res.status >= 500) {
      if (attempt >= tries) throw new Error(`TTS ${res.status}: ${(await res.text()).slice(0, 200)}`);
      const wait = DELAY * 2 ** attempt; // 429는 쿼터 — 점점 길게 쉬었다 재시도
      process.stdout.write(`\r  ${res.status} — ${wait}ms 대기 후 재시도 (${attempt}/${tries - 1})   `);
      await sleep(wait);
      continue;
    }
    if (!res.ok) throw new Error(`TTS ${res.status}: ${(await res.text()).slice(0, 200)}`);
    const json = await res.json();
    const part = json.candidates?.[0]?.content?.parts?.find((p) => p.inlineData);
    if (!part) throw new Error(`오디오가 없는 응답: ${JSON.stringify(json).slice(0, 200)}`);
    return toWav(Buffer.from(part.inlineData.data, 'base64'), rateOf(part.inlineData.mimeType));
  }
}

// 단일 화자 — L1·L2용
function synthSingle(text, accent, gender) {
  const prompt = `Read the following aloud in ${ACCENT_PROMPT[accent]}, ${PACE}. ` +
    `Read only the text itself, with no extra commentary:\n\n${text}`;
  return callTts(prompt, {
    voiceConfig: { prebuiltVoiceConfig: { voiceName: VOICES[accent][gender] } },
  });
}

// 여러 화자 — L3·L4 대화/담화용. 한 번의 호출로 대화 전체를 합성한다.
function synthDialogue(lines, accent, voiceGenders) {
  const speakers = [...new Set(lines.map((l) => l.speaker))];
  // 화자 1명(L4 안내방송 등)은 멀티 스피커가 거부되고, 화자 라벨을 그대로 두면
  // 성우가 "N"을 글자로 읽어버린다 → 라벨을 떼고 단일 화자로 합성한다.
  if (speakers.length < 2) {
    const gender = voiceGenders?.[speakers[0]] === 'male' ? 'male' : 'female';
    return synthSingle(lines.map((l) => l.text).join('\n'), accent, gender);
  }
  const script = lines.map((l) => `${l.speaker}: ${l.text}`).join('\n');
  const prompt = `TTS the following conversation in ${ACCENT_PROMPT[accent]}, ${PACE}. ` +
    `Leave a short natural pause between speakers:\n\n${script}`;
  // 멀티 스피커는 최대 2명 — 3명 이상이면 앞의 2명 기준으로 번갈아 배정
  const picked = speakers.slice(0, 2);
  return callTts(prompt, {
    multiSpeakerVoiceConfig: {
      speakerVoiceConfigs: picked.map((sp, i) => {
        const gender = voiceGenders?.[sp] || (i === 0 ? 'female' : 'male');
        return {
          speaker: sp,
          voiceConfig: {
            prebuiltVoiceConfig: { voiceName: VOICES[accent][gender === 'male' ? 'male' : 'female'] },
          },
        };
      }),
    },
  });
}

// WAV를 MP3로 바꾸고 WAV는 지운다 (ffmpeg 있을 때만)
function writeAudio(absPathNoExt, wav) {
  if (!HAS_FFMPEG) { writeFileSync(`${absPathNoExt}.wav`, wav); return; }
  const tmp = `${absPathNoExt}.tmp.wav`;
  writeFileSync(tmp, wav);
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', tmp, '-codec:a', 'libmp3lame',
    '-b:a', '64k', '-ar', '24000', '-ac', '1', `${absPathNoExt}.mp3`]);
  unlinkSync(tmp);
}

const manifest = existsSync(join(OUT, 'audio-manifest.json'))
  ? JSON.parse(readFileSync(join(OUT, 'audio-manifest.json'), 'utf8')) : {};
mkdirSync(join(OUT, 'audio', 'questions'), { recursive: true });
mkdirSync(join(OUT, 'audio', 'passages'), { recursive: true });

let made = 0, skipped = 0, failed = 0, chars = 0;
const files = readdirSync(join(CONTENT, 'questions')).filter((f) => /^L[1-4]\.json$/.test(f)).sort();

console.log(`모델 ${MODEL} / 출력 ${EXT.toUpperCase()}${HAS_FFMPEG ? '' : ' (ffmpeg 없음 — WAV로 저장)'} / 간격 ${DELAY}ms`);

outer:
for (const file of files) {
  const items = JSON.parse(readFileSync(join(CONTENT, 'questions', file), 'utf8'));
  for (const it of items) {
    if (LIMIT && made >= LIMIT) break outer;
    let relPath;
    try {
      if (it.type === 'single') {
        const id = idmap[`q:${it.tmp_id}`];
        if (!id) throw new Error('idmap에 없음 — import.mjs 먼저 실행');
        relPath = `audio/questions/${id}.${EXT}`;
        if (existsSync(join(OUT, relPath))) { manifest[it.tmp_id] = relPath; skipped++; continue; }
        // L1: 문장 1개 / L2: 질문 + 보기 4개 응답을 한 트랙으로
        let text = it.tts_script;
        if (it.part === 'L2') {
          text += '\n\n' + it.choices.map((c, i) => `${LETTERS[i]}. ${c}`).join('\n');
        }
        chars += text.length;
        writeAudio(join(OUT, `audio/questions/${id}`), await synthSingle(text, it.accent, 'female'));
      } else {
        const id = idmap[`p:${it.tmp_id}`];
        if (!id) throw new Error('idmap에 없음 — import.mjs 먼저 실행');
        relPath = `audio/passages/${id}.${EXT}`;
        if (existsSync(join(OUT, relPath))) { manifest[it.tmp_id] = relPath; skipped++; continue; }
        // "A: 대사" 형태를 화자·대사로 분리 (화자 표기가 없는 줄은 내레이터 N)
        const lines = it.passage.script.split('\n').filter((l) => l.trim()).map((line) => {
          const m = line.match(/^([A-Za-z][\w ]*):\s*(.*)$/);
          return m ? { speaker: m[1].trim(), text: m[2] } : { speaker: 'N', text: line.trim() };
        });
        chars += lines.reduce((n, l) => n + l.text.length, 0);
        writeAudio(join(OUT, `audio/passages/${id}`),
          await synthDialogue(lines, it.passage.accent, it.passage.tts_voices));
      }
      manifest[it.tmp_id] = relPath;
      made++;
      process.stdout.write(`\r생성 ${made} / 건너뜀 ${skipped} / 실패 ${failed} (${it.tmp_id})          `);
      await sleep(DELAY);
    } catch (e) {
      failed++;
      console.error(`\n실패 ${it.tmp_id}: ${e.message}`);
    }
  }
}

writeFileSync(join(OUT, 'audio-manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
console.log(`\n완료 — 생성 ${made}개, 건너뜀 ${skipped}개, 실패 ${failed}개, 합성 글자수 약 ${chars.toLocaleString()}자`);
if (failed) console.log('실패분은 다시 실행하면 이어서 만듭니다 (이미 만든 파일은 건너뜀).');
if (!HAS_FFMPEG) console.log('※ ffmpeg를 설치하면 다음 실행부터 MP3로 저장돼 용량이 크게 줄어듭니다.');
console.log(`\n다음 단계 (R2 업로드 후 seed 재생성):`);
console.log(`  1) npx wrangler r2 bucket create jumplish-assets`);
console.log(`  2) cd tools/out && find audio -name '*.${EXT}' | while read f; do npx wrangler r2 object put "jumplish-assets/$f" --file "$f"; done`);
console.log(`  3) R2 공개 도메인 연결 후: R2_PUBLIC_BASE=https://<공개도메인> node tools/import.mjs`);
console.log(`  4) seed.sql 재적용 (audio_url 반영)`);
