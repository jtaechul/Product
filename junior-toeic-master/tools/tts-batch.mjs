#!/usr/bin/env node
// 점프리시 배치 TTS (docs/content-pipeline.md 5절)
// 개발 단계 1회성 실행. 운영 중에는 절대 호출되지 않는다 (정적 음원만 서빙).
//
// 준비: docs/tts-guide.md 참고
// 사용: GOOGLE_TTS_KEY=발급받은키 node tools/tts-batch.mjs
//  1) 반드시 node tools/import.mjs 를 먼저 실행 (ULID 매핑 생성)
//  2) 완료 후 tools/out/audio/ 에 음원, tools/out/audio-manifest.json 생성
//  3) R2 업로드 → R2_PUBLIC_BASE=https://... node tools/import.mjs → seed 재적용
//
// 엔진 2종 — 기본은 google (미·영·호 전용 성우가 있어 발음 구분이 확실하고 무료 쿼터가 크다)
//   google  Cloud Text-to-Speech.  GOOGLE_TTS_KEY 필요. SSML·MP3 출력.
//   gemini  Gemini API.            GEMINI_API_KEY 필요. GCP 결제 계정을 못 쓸 때의 대안.
//                                  발음을 프롬프트로 지시하므로 미·영·호 구분이 약할 수 있다.
//
// 옵션 환경변수
//   TTS_ENGINE  google(기본) | gemini
//   TTS_MODEL   gemini 전용. 기본 gemini-2.5-flash-preview-tts
//   TTS_DELAY   요청 간격 ms. 기본 google 150 / gemini 1500
//   TTS_LIMIT   테스트용 — 앞에서 N개만 생성하고 중단

import { readFileSync, writeFileSync, mkdirSync, existsSync, readdirSync, unlinkSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const CONTENT = join(ROOT, 'content');
const OUT = join(ROOT, 'tools', 'out');

const ENGINE = process.env.TTS_ENGINE || 'google';
if (!['google', 'gemini'].includes(ENGINE)) {
  console.error(`TTS_ENGINE은 google 또는 gemini 여야 합니다 (받은 값: ${ENGINE})`);
  process.exit(1);
}
const KEY = ENGINE === 'google'
  ? (process.env.GOOGLE_TTS_KEY || process.env.GEMINI_API_KEY)
  : (process.env.GEMINI_API_KEY || process.env.GOOGLE_TTS_KEY);
if (!KEY) {
  const need = ENGINE === 'google' ? 'GOOGLE_TTS_KEY' : 'GEMINI_API_KEY';
  console.error(`${need} 환경변수가 필요합니다. 발급 방법: docs/tts-guide.md`);
  process.exit(1);
}
const MODEL = process.env.TTS_MODEL || 'gemini-2.5-flash-preview-tts';
const DELAY = Number(process.env.TTS_DELAY || (ENGINE === 'google' ? 150 : 1500));
const LIMIT = Number(process.env.TTS_LIMIT || 0);
const idmap = JSON.parse(readFileSync(join(CONTENT, '.idmap.json'), 'utf8'));

// gemini는 raw PCM을 주므로 WAV로 감싼다. ffmpeg가 있으면 MP3로 줄인다(WAV는 약 15배 크다).
const HAS_FFMPEG = (() => {
  try { execFileSync('ffmpeg', ['-version'], { stdio: 'ignore' }); return true; } catch { return false; }
})();
const EXT = ENGINE === 'google' || HAS_FFMPEG ? 'mp3' : 'wav';

// 초등 청취를 고려해 또박또박·약간 느리게 (음원은 한 벌 — 주니어는 앱에서 0.9배속)
const RATE = '95%';
const LETTERS = ['A', 'B', 'C', 'D'];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// 실제 TOEIC Bridge 듣기 진행을 따른다.
// 실전은 질문과 보기를 거의 붙여서 한 번에 읽고(보기 사이 약 0.5초), 다 읽은 뒤
// 문항당 약 10초의 답 고르는 시간을 준다. 우리 앱은 학생이 보기를 눌러 바로
// 넘어가므로 그 10초는 음원에 넣지 않는다(끝에 무음만 남는다).
// 실전 모의고사 모드가 필요해지면 TTS_PAUSE_ANSWER=10s 로 켠다.
const PAUSE = {
  lead: process.env.TTS_PAUSE_LEAD || '1s',          // 음원 시작 → 첫 발화
  afterStem: process.env.TTS_PAUSE_STEM || '1s',     // 질문 → 첫 보기
  between: process.env.TTS_PAUSE_BETWEEN || '500ms', // 보기 사이
  line: process.env.TTS_PAUSE_LINE || '500ms',       // 대화 줄 사이
  answer: process.env.TTS_PAUSE_ANSWER || '',        // 끝의 답 고르는 시간(기본 없음)
};

// ---------- 공통: HTTP 호출 (429·5xx 지수 백오프) ----------
async function postJson(url, body, tries = 4) {
  for (let attempt = 1; ; attempt++) {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (res.status === 429 || res.status >= 500) {
      if (attempt >= tries) throw new Error(`TTS ${res.status}: ${(await res.text()).slice(0, 200)}`);
      const wait = Math.max(DELAY, 1000) * 2 ** attempt;
      process.stdout.write(`\r  ${res.status} — ${wait}ms 대기 후 재시도 (${attempt}/${tries - 1})   `);
      await sleep(wait);
      continue;
    }
    if (!res.ok) throw new Error(`TTS ${res.status}: ${(await res.text()).slice(0, 200)}`);
    return res.json();
  }
}

// ---------- 엔진 A: Google Cloud Text-to-Speech ----------
// 국가·성별 → 전용 뉴럴 보이스 (content-pipeline.md 5-2 표). 발음이 보이스로 고정된다.
const GOOGLE_VOICES = {
  US: { female: 'en-US-Neural2-C', male: 'en-US-Neural2-A', lang: 'en-US' },
  UK: { female: 'en-GB-Neural2-A', male: 'en-GB-Neural2-B', lang: 'en-GB' },
  AU: { female: 'en-AU-Neural2-A', male: 'en-AU-Neural2-B', lang: 'en-AU' },
};
const escXml = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

// 보기 기호(A/B/C)는 반드시 say-as로 감싼다.
// "D. He's ten years old." 처럼 평문으로 두면 TTS가 마침표 붙은 홑글자를 약어로
// 해석해 엉뚱하게 읽는 사고가 실제로 있었다(영국 성우가 D를 A로 발음).
// say-as interpret-as="characters"는 글자 이름 그대로 읽도록 강제한다.
// 기호는 본문보다 느리게 읽는다. 원속도로 읽으면 "에이비씨"처럼 뭉개져
// 어느 보기를 말하는지 아이가 놓친다.
const LETTER_RATE = process.env.TTS_LETTER_RATE || '65%';
const LETTER_GAP = process.env.TTS_LETTER_GAP || '500ms';
const sayLetter = (letter) => {
  if (!/^[A-Z]$/.test(letter)) throw new Error(`보기 기호가 A~Z 한 글자가 아닙니다: ${letter}`);
  return `<prosody rate="${LETTER_RATE}"><say-as interpret-as="characters">${letter}</say-as></prosody>` +
    `<break time="${LETTER_GAP}"/>`;
};

// parts: 문자열(그대로 읽기) / {pause} (쉼) / {letter,text} (보기 기호 + 내용)
const buildSsml = (parts, { lead = true } = {}) =>
  `<speak>${lead ? `<break time="${PAUSE.lead}"/>` : ''}` +
  parts.map((p) => {
    if (typeof p === 'string') return `<prosody rate="${RATE}">${escXml(p)}</prosody>`;
    if (p.pause) return `<break time="${p.pause}"/>`;
    return `<prosody rate="${RATE}">${sayLetter(p.letter)}${escXml(p.text)}</prosody>`;
  }).join('') +
  `</speak>`;

async function googleSynth(ssmlText, accent, gender) {
  const v = GOOGLE_VOICES[accent];
  const json = await postJson(`https://texttospeech.googleapis.com/v1/text:synthesize?key=${KEY}`, {
    input: { ssml: ssmlText },
    voice: { languageCode: v.lang, name: v[gender] },
    audioConfig: { audioEncoding: 'MP3', sampleRateHertz: 24000 },
  });
  return Buffer.from(json.audioContent, 'base64');
}

const googleBackend = {
  single: (parts, accent, gender) => googleSynth(buildSsml(parts), accent, gender),
  // 화자별로 따로 합성해 이어붙인다. 시작 쉼은 첫 줄에만 붙인다.
  async dialogue(lines, accent, voiceGenders) {
    const bufs = [];
    for (const [i, l] of lines.entries()) {
      const gender = voiceGenders?.[l.speaker] === 'male' ? 'male' : 'female';
      const ssmlText = buildSsml([l.text, { pause: PAUSE.line }], { lead: i === 0 });
      bufs.push(await googleSynth(ssmlText, accent, gender));
    }
    return Buffer.concat(bufs);
  },
};

// ---------- 엔진 B: Gemini API ----------
// 발음은 보이스 ID가 아니라 프롬프트 지시문으로 지정한다.
const ACCENT_PROMPT = {
  US: 'a standard American English accent',
  UK: 'a standard British English (Received Pronunciation) accent',
  AU: 'a standard Australian English accent',
};
const GEMINI_VOICES = {
  US: { female: 'Kore', male: 'Puck' },
  UK: { female: 'Leda', male: 'Charon' },
  AU: { female: 'Aoede', male: 'Fenrir' },
};
const PACE = 'clearly and at a slightly slow, steady pace suitable for young English learners';

// PCM(16bit·모노) → WAV 헤더 44바이트를 앞에 붙인다.
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
const rateOf = (mime) => Number(/rate=(\d+)/.exec(mime || '')?.[1] || 24000);

async function geminiSynth(prompt, speechConfig) {
  const json = await postJson(
    `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent?key=${KEY}`,
    { contents: [{ parts: [{ text: prompt }] }], generationConfig: { responseModalities: ['AUDIO'], speechConfig } });
  const part = json.candidates?.[0]?.content?.parts?.find((p) => p.inlineData);
  if (!part) throw new Error(`오디오가 없는 응답: ${JSON.stringify(json).slice(0, 200)}`);
  return toWav(Buffer.from(part.inlineData.data, 'base64'), rateOf(part.inlineData.mimeType));
}

const geminiBackend = {
  // gemini는 SSML을 못 받으므로 쉼을 프롬프트로 지시한다(정확도는 google보다 낮다).
  single(parts, accent, gender) {
    const text = parts
      .filter((p) => typeof p === 'string' || p.letter)
      .map((p) => (typeof p === 'string' ? p : `${p.letter}. ${p.text}`)).join('\n');
    const hasPause = parts.some((p) => typeof p === 'object' && p.pause);
    return geminiSynth(
      `Read the following aloud in ${ACCENT_PROMPT[accent]}, ${PACE}. ` +
      (hasPause ? 'Leave a clear two-second silence between each line. ' : '') +
      `Read only the text itself, with no extra commentary:\n\n${text}`,
      { voiceConfig: { prebuiltVoiceConfig: { voiceName: GEMINI_VOICES[accent][gender] } } });
  },
  // 한 번의 호출로 대화 전체를 합성한다 (멀티 스피커, 최대 2명)
  dialogue(lines, accent, voiceGenders) {
    const speakers = [...new Set(lines.map((l) => l.speaker))];
    // 화자 1명(L4 안내방송 등)은 멀티 스피커가 거부되고, 화자 라벨을 그대로 두면
    // 성우가 "N"을 글자로 읽어버린다 → 라벨을 떼고 단일 화자로 합성한다.
    if (speakers.length < 2) {
      const gender = voiceGenders?.[speakers[0]] === 'male' ? 'male' : 'female';
      return this.single([lines.map((l) => l.text).join('\n')], accent, gender);
    }
    const script = lines.map((l) => `${l.speaker}: ${l.text}`).join('\n');
    return geminiSynth(
      `TTS the following conversation in ${ACCENT_PROMPT[accent]}, ${PACE}. ` +
      `Leave a short natural pause between speakers:\n\n${script}`,
      {
        multiSpeakerVoiceConfig: {
          speakerVoiceConfigs: speakers.slice(0, 2).map((sp, i) => ({
            speaker: sp,
            voiceConfig: {
              prebuiltVoiceConfig: {
                voiceName: GEMINI_VOICES[accent][(voiceGenders?.[sp] || (i ? 'male' : 'female')) === 'male' ? 'male' : 'female'],
              },
            },
          })),
        },
      });
  },
};

const backend = ENGINE === 'google' ? googleBackend : geminiBackend;

// gemini(WAV)에서 ffmpeg가 있으면 MP3로 바꾸고 WAV는 지운다
function writeAudio(absPathNoExt, buf) {
  if (ENGINE === 'google' || !HAS_FFMPEG) { writeFileSync(`${absPathNoExt}.${EXT}`, buf); return; }
  const tmp = `${absPathNoExt}.tmp.wav`;
  writeFileSync(tmp, buf);
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', tmp, '-codec:a', 'libmp3lame',
    '-b:a', '64k', '-ar', '24000', '-ac', '1', `${absPathNoExt}.mp3`]);
  unlinkSync(tmp);
}

// ---------- 실행 ----------
const manifest = existsSync(join(OUT, 'audio-manifest.json'))
  ? JSON.parse(readFileSync(join(OUT, 'audio-manifest.json'), 'utf8')) : {};
mkdirSync(join(OUT, 'audio', 'questions'), { recursive: true });
mkdirSync(join(OUT, 'audio', 'passages'), { recursive: true });

let made = 0, skipped = 0, failed = 0, chars = 0;
const files = readdirSync(join(CONTENT, 'questions')).filter((f) => /^L[1-4]\.json$/.test(f)).sort();

console.log(`엔진 ${ENGINE}${ENGINE === 'gemini' ? ` (${MODEL})` : ''} / 출력 ${EXT.toUpperCase()} / 간격 ${DELAY}ms`);

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
        // L1: 문장 1개 / L2: 질문 → (쉼) → 보기 A~C를 쉼으로 끊어 한 트랙으로
        const parts = [it.tts_script];
        if (it.part === 'L2') {
          parts.push({ pause: PAUSE.afterStem });
          it.choices.forEach((c, i) => {
            if (i) parts.push({ pause: PAUSE.between });
            parts.push({ letter: LETTERS[i], text: c });
          });
        }
        if (PAUSE.answer) parts.push({ pause: PAUSE.answer });
        chars += parts.reduce((n, p) => n + (typeof p === 'string' ? p.length : (p.text?.length || 0)), 0);
        writeAudio(join(OUT, `audio/questions/${id}`), await backend.single(parts, it.accent, 'female'));
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
          await backend.dialogue(lines, it.passage.accent, it.passage.tts_voices));
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
if (ENGINE === 'google') console.log('(Google 무료 쿼터: 뉴럴 월 100만 자 — 이번 사용량은 그 안입니다)');
else if (!HAS_FFMPEG) console.log('※ ffmpeg를 설치하면 다음 실행부터 MP3로 저장돼 용량이 크게 줄어듭니다.');
console.log(`\n다음 단계 (R2 업로드 후 seed 재생성):`);
console.log(`  1) npx wrangler r2 bucket create jumplish-assets`);
console.log(`  2) cd tools/out && find audio -name '*.${EXT}' | while read f; do npx wrangler r2 object put "jumplish-assets/$f" --file "$f"; done`);
console.log(`  3) R2 공개 도메인 연결 후: R2_PUBLIC_BASE=https://<공개도메인> node tools/import.mjs`);
console.log(`  4) seed.sql 재적용 (audio_url 반영)`);
