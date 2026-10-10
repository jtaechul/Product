#!/usr/bin/env node
// 판박이 문항 찾기 — "새로 만든 문항이 정말 새 문항인가"를 숫자로 확인한다.
//
// 왜 필요한가: AI에게 형식 참고용으로 기존 문항을 보여주면 내용까지 따라 만든다.
// 실제로 소풍이 비로 미뤄지는 대화, 도서관 안내문이 여러 개 겹쳤다. 그러면 은행 숫자만
// 늘고 아이가 만나는 새 문제는 늘지 않는다 — 은행을 키우는 이유 자체가 없어진다.
//
// 기준(DUP_RATIO·DUP_SHARED)은 worker/authoring.mjs 에 한 벌로 두고, 생성기도 같은 것을 쓴다.
// 여기서 걸리는 것은 생성 단계에서도 걸린다.
//
// 사용: node tools/find-duplicates.mjs            (나갈 문항끼리만 — 기본)
//       node tools/find-duplicates.mjs --all      (내린 것까지 포함)

import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { PART_LIST, topicOverlap, itemTopicText, DUP_RATIO, DUP_SHARED } from '../worker/authoring.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const ALL = process.argv.includes('--all');

console.log(`기준: 겹침 ${Math.round(DUP_RATIO * 100)}% 이상 **그리고** 같은 낱말 ${DUP_SHARED}개 이상`);
console.log(ALL ? '(내린 문항까지 포함)\n' : '(출제 중 + 준비 중만)\n');

let pairs = 0, found = 0;
for (const part of PART_LIST) {
  const file = join(ROOT, 'content', 'questions', `${part}.json`);
  let items;
  try { items = JSON.parse(readFileSync(file, 'utf8')); } catch { continue; }
  const live = ALL ? items : items.filter((x) => (x.status || 'active') !== 'retired');
  const texts = live.map(itemTopicText);
  for (let i = 0; i < live.length; i += 1) {
    for (let j = i + 1; j < live.length; j += 1) {
      pairs += 1;
      const o = topicOverlap(texts[i], texts[j]);
      if (o.ratio < DUP_RATIO || o.shared < DUP_SHARED) continue;
      found += 1;
      const st = (x) => ({ active: '출제중', draft: '준비중', retired: '내림' }[x.status || 'active']);
      console.log(`[${part}] ${live[i].tmp_id}(${st(live[i])}) ≈ ${live[j].tmp_id}(${st(live[j])})`
        + `  겹침 ${Math.round(o.ratio * 100)}% · 같은 낱말 ${o.shared}개`);
      console.log(`      ${texts[i].replace(/\s+/g, ' ').slice(0, 72)}`);
      console.log(`      ${texts[j].replace(/\s+/g, ' ').slice(0, 72)}`);
    }
  }
}
console.log(`\n${pairs.toLocaleString()}쌍 중 판박이 ${found}쌍`);
process.exit(found ? 1 : 0);   // 판박이가 있으면 실패로 — 자동 검사에 걸 수 있게
