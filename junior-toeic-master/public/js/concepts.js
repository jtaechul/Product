// 개념 그림 해설 — 글로 길게 쓰는 대신 규칙을 한 장의 그림으로 보여준다.
// 전부 손으로 그린 벡터(SVG)라 AI 이미지처럼 엉뚱하게 그려질 일이 없고,
// 파일을 받아오지 않으므로 운영 중 외부 호출 0회 규칙도 그대로 지킨다.
// 문항의 개념 태그(G.prep 등) 하나가 그림 한 장에 대응한다.

const box = (x, y, w, h) => `<rect class="c-box" x="${x}" y="${y}" width="${w}" height="${h}" rx="8"/>`;
const ball = (cx, cy, r = 9) => `<circle class="c-ball" cx="${cx}" cy="${cy}" r="${r}"/>`;
const en = (x, y, t, anchor = 'middle') => `<text class="c-en" x="${x}" y="${y}" text-anchor="${anchor}">${t}</text>`;
const ko = (x, y, t, anchor = 'middle') => `<text class="c-ko" x="${x}" y="${y}" text-anchor="${anchor}">${t}</text>`;
const svg = (h, body) => `<svg class="concept-svg" viewBox="0 0 300 ${h}" role="img">${body}</svg>`;

// 왼쪽 영어 / 오른쪽 우리말 뜻이 줄줄이 놓이는 표 — 여러 개념이 이 모양을 쓴다
const rows = (items, opt = {}) => {
  const rowH = opt.rowH || 34;
  const h = items.length * rowH + 8;
  const body = items.map((it, i) => {
    const y = i * rowH + 4;
    return box(0, y, 300, rowH - 6)
      + en(14, y + 19, it[0], 'start')
      + ko(286, y + 19, it[1], 'end');
  }).join('');
  return svg(h, body);
};

export const CONCEPTS = {
  'G.prep': {
    title: 'in · on · at — 어디에 있는지',
    svg: svg(120,
      // in: 상자 안 / on: 상자 위 / at: 한 지점(문 앞)
      box(8, 20, 84, 52) + ball(50, 46) + en(50, 92, 'in') + ko(50, 110, '안에')
      + box(108, 20, 84, 52) + ball(150, 12) + en(150, 92, 'on') + ko(150, 110, '위에')
      + `<path class="c-line" d="M250 20v52"/>` + ball(232, 60, 7)
      + en(250, 92, 'at') + ko(250, 110, '그 지점에')),
  },
  'G.compare': {
    title: '둘을 견줄 때 — than 이 보이면',
    svg: svg(126,
      `<rect class="c-bar" x="20" y="52" width="46" height="34" rx="6"/>`
      + `<rect class="c-bar on" x="86" y="26" width="46" height="60" rx="6"/>`
      + en(43, 104, 'tall') + en(109, 104, 'taller')
      + ko(76, 122, '짧은 말 → -er')
      + `<path class="c-line" d="M154 56h20"/>`
      + `<rect class="c-bar" x="186" y="52" width="46" height="34" rx="6"/>`
      + `<rect class="c-bar on" x="248" y="26" width="46" height="60" rx="6"/>`
      + en(209, 104, 'useful') + en(271, 104, 'more ~')
      + ko(240, 122, '긴 말 → more')
      + ko(150, 16, 'than = ~보다')),
  },
  'G.tense': {
    title: '언제 있었던 일인지',
    svg: svg(112,
      `<path class="c-line" d="M16 60h268"/>`
      + ball(50, 60, 7) + ball(150, 60, 7) + ball(250, 60, 7)
      + ko(50, 40, '어제') + ko(150, 40, '지금') + ko(250, 40, '계속')
      + en(50, 84, 'played') + en(150, 84, 'is playing') + en(250, 84, 'has played')
      + ko(50, 102, '-ed 붙임') + ko(150, 102, '~하는 중') + ko(250, 102, '그때부터 쭉')),
  },
  'G.agreement': {
    title: '한 명이면 s, 여럿이면 그대로',
    svg: svg(112,
      ball(58, 34, 11) + `<path class="c-line" d="M58 47v22M44 78l14-11 14 11"/>`
      + en(58, 100, 'runs') + ko(58, 20, '한 명·하나')
      + `<path class="c-line" d="M150 34v52"/>`
      + ball(206, 34, 11) + `<path class="c-line" d="M206 47v22M192 78l14-11 14 11"/>`
      + ball(250, 34, 11) + `<path class="c-line" d="M250 47v22M236 78l14-11 14 11"/>`
      + en(228, 100, 'run') + ko(228, 20, '둘 이상')),
  },
  'G.pronoun': {
    title: '이름 대신 쓰는 말',
    svg: rows([['he / she', '그가 · 그녀가 (하는 사람)'], ['his / her', '그의 · 그녀의 (누구 것)'],
      ['him / her', '그를 · 그녀를 (받는 쪽)'], ['mine / yours', '내 것 · 네 것']]),
  },
  'G.conj': {
    title: '두 이야기를 잇는 말',
    svg: rows([['and', '그리고 (더하기)'], ['but', '하지만 (반대)'],
      ['because', '왜냐하면 (까닭)'], ['so', '그래서 (결과)']]),
  },
  'G.modal': {
    title: '얼마나 센 말인지',
    svg: svg(126,
      `<rect class="c-bar on" x="0" y="10" width="120" height="26" rx="7"/>`
      + en(14, 28, 'can', 'start') + ko(300, 28, '할 수 있어', 'end')
      + `<rect class="c-bar on" x="0" y="50" width="190" height="26" rx="7"/>`
      + en(14, 68, 'should', 'start') + ko(300, 68, '하는 게 좋아', 'end')
      + `<rect class="c-bar on" x="0" y="90" width="260" height="26" rx="7"/>`
      + en(14, 108, 'must / have to', 'start') + ko(300, 108, '꼭 해야 해', 'end')),
  },
  'G.toinf': {
    title: '뒤에 -ing 인지 to 인지',
    svg: rows([['enjoy · finish + -ing', '이미 하고 있는 일'], ['want · need + to ~', '앞으로 할 일'],
      ['go to the store to buy', '~하려고 (까닭)']]),
  },
  'G.pos': {
    title: '낱말이 앉는 자리',
    svg: svg(96,
      box(0, 22, 66, 34) + en(33, 44, 'a')
      + box(76, 22, 122, 34) + en(137, 44, 'beautiful')
      + box(208, 22, 92, 34) + en(254, 44, 'voice')
      + ko(33, 76, '하나') + ko(137, 76, '꾸미는 말') + ko(254, 76, '이름말')
      + ko(150, 14, '꾸미는 말은 이름말 앞에')),
  },
  'G.passive': {
    title: '누가 했는지 / 무엇이 되었는지',
    svg: svg(112,
      box(0, 16, 128, 34) + en(64, 38, 'They built it')
      + ko(64, 66, '그들이 만들었다')
      + `<path class="c-line arrow" d="M138 33h24M156 27l6 6-6 6"/>`
      + box(172, 16, 128, 34) + en(236, 38, 'It was built')
      + ko(236, 66, '그것이 만들어졌다')
      + ko(150, 100, '한 사람이 안 보이면 was/were + 만들어진 말')),
  },
  'LS.qr': {
    title: '묻는 말이 답을 정한다',
    svg: rows([['What ~?', '무엇 (물건·색)'], ['Where ~?', '어디 (장소)'],
      ['When / What time ~?', '언제 (때·시각)'], ['Who / Whose ~?', '누구 · 누구 것'],
      ['How much / long ~?', '얼마 · 얼마나 오래']], { rowH: 32 }),
  },
};

export const conceptOf = (code) => CONCEPTS[code] || null;
