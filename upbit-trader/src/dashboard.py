"""대시보드 생성 — 백테스트 결과를 차트가 들어간 HTML 파일로 만듭니다.

외부 파이썬 의존성 없이, 데이터를 HTML 안에 내장하고 Chart.js(CDN)로 그립니다.
생성된 dashboard.html 을 브라우저로 열면:
  - 전략별 성적 비교표
  - 자산 곡선(equity curve) 비교 차트
  - 가격 차트 + 매수/매도 시점 표시
  - 거래 일지
를 한눈에 볼 수 있습니다.
"""

from __future__ import annotations

import json

_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Upbit 자동매매 대시보드</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  body {{ font-family: -apple-system, "Segoe UI", "Malgun Gothic", sans-serif;
         margin: 0; background:#0f1117; color:#e6e6e6; }}
  .wrap {{ max-width: 1100px; margin: 0 auto; padding: 24px; }}
  h1 {{ font-size: 22px; }}
  h2 {{ font-size: 16px; margin-top: 32px; border-left: 3px solid #4f8cff;
       padding-left: 8px; }}
  .meta {{ color:#9aa4b2; font-size: 13px; }}
  .warn {{ background:#3a2a00; color:#ffcf6b; padding:10px 14px; border-radius:8px;
          font-size:13px; margin:12px 0; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; margin-top:8px; }}
  th, td {{ padding: 8px 10px; text-align: right; border-bottom: 1px solid #232838; }}
  th:first-child, td:first-child {{ text-align: left; }}
  th {{ color:#9aa4b2; font-weight:600; }}
  .pos {{ color:#4ade80; }} .neg {{ color:#f87171; }}
  .card {{ background:#161a24; border:1px solid #232838; border-radius:10px;
          padding:16px; margin-top:12px; }}
  .buy {{ color:#4ade80; }} .sell {{ color:#f87171; }}
  canvas {{ max-height: 360px; }}
</style>
</head>
<body><div class="wrap">
  <h1>📊 Upbit 자동매매 대시보드</h1>
  <div class="meta">{meta}</div>
  <div class="warn">⚠️ {warning}</div>

  <h2>전략 성적 비교</h2>
  <div class="card"><table id="cmp">
    <thead><tr><th>전략</th><th>누적수익</th><th>단순보유</th>
      <th>매매</th><th>승률</th><th>최대낙폭</th></tr></thead>
    <tbody></tbody>
  </table></div>

  <h2>자산 곡선 (1.0 = 시작 자금)</h2>
  <div class="card"><canvas id="equity"></canvas></div>

  <h2>가격 차트 &amp; 매매 시점 — {best_name}</h2>
  <div class="card"><canvas id="price"></canvas></div>

  <h2>거래 일지 — {best_name}</h2>
  <div class="card"><table id="trades">
    <thead><tr><th>날짜</th><th>구분</th><th>체결가</th><th>거래후 총자산</th></tr></thead>
    <tbody></tbody>
  </table></div>
</div>
<script>
const DATA = {data_json};

function fmt(n, d=0) {{ return n.toLocaleString('ko-KR', {{maximumFractionDigits:d}}); }}
function pct(n) {{ return (n*100).toFixed(1) + '%'; }}
function cls(n) {{ return n >= 0 ? 'pos' : 'neg'; }}

// 비교표
const tb = document.querySelector('#cmp tbody');
DATA.comparison.forEach(s => {{
  tb.insertAdjacentHTML('beforeend',
    `<tr><td>${{s.name}}</td>
     <td class="${{cls(s.total_return)}}">${{pct(s.total_return)}}</td>
     <td class="${{cls(s.buy_hold)}}">${{pct(s.buy_hold)}}</td>
     <td>${{s.num_trades}}</td><td>${{(s.win_rate*100).toFixed(0)}}%</td>
     <td class="neg">${{pct(s.max_drawdown)}}</td></tr>`);
}});

// 자산 곡선
const palette = ['#4f8cff','#4ade80','#f59e0b','#a78bfa','#f87171'];
new Chart(document.getElementById('equity'), {{
  type:'line',
  data:{{ labels: DATA.dates, datasets: DATA.comparison.map((s,i)=>({{
    label:s.name, data:s.equity, borderColor:palette[i%palette.length],
    borderWidth:1.5, pointRadius:0, tension:0.1 }})) }},
  options:{{ responsive:true, interaction:{{mode:'index',intersect:false}},
    scales:{{ x:{{ ticks:{{maxTicksLimit:8, color:'#9aa4b2'}}, grid:{{color:'#232838'}} }},
      y:{{ ticks:{{color:'#9aa4b2'}}, grid:{{color:'#232838'}} }} }},
    plugins:{{ legend:{{ labels:{{color:'#e6e6e6'}} }} }} }}
}});

// 가격 + 매매 시점
const buys = DATA.markers.filter(m=>m.action==='BUY').map(m=>({{x:m.date,y:m.price}}));
const sells = DATA.markers.filter(m=>m.action==='SELL').map(m=>({{x:m.date,y:m.price}}));
new Chart(document.getElementById('price'), {{
  data:{{ labels: DATA.dates, datasets:[
    {{ type:'line', label:'가격', data:DATA.price, borderColor:'#6b7280',
       borderWidth:1, pointRadius:0 }},
    {{ type:'scatter', label:'매수', data:buys, backgroundColor:'#4ade80', pointRadius:5 }},
    {{ type:'scatter', label:'매도', data:sells, backgroundColor:'#f87171', pointRadius:5 }}
  ] }},
  options:{{ responsive:true,
    scales:{{ x:{{ type:'category', ticks:{{maxTicksLimit:8, color:'#9aa4b2'}}, grid:{{color:'#232838'}} }},
      y:{{ ticks:{{color:'#9aa4b2'}}, grid:{{color:'#232838'}} }} }},
    plugins:{{ legend:{{ labels:{{color:'#e6e6e6'}} }} }} }}
}});

// 거래 일지
const trb = document.querySelector('#trades tbody');
if (DATA.markers.length === 0) {{
  trb.insertAdjacentHTML('beforeend','<tr><td colspan="4">매매 없음</td></tr>');
}}
DATA.markers.forEach(m => {{
  const k = m.action==='BUY' ? 'buy' : 'sell';
  const label = m.action==='BUY' ? '매수' : '매도';
  trb.insertAdjacentHTML('beforeend',
    `<tr><td>${{m.date}}</td><td class="${{k}}">${{label}}</td>
     <td>${{fmt(m.price)}}</td><td>${{fmt(m.value)}}</td></tr>`);
}});
</script>
</body></html>"""


def build_dashboard_html(
    dates: list[str],
    price: list[float],
    comparison: list[dict],
    markers: list[dict],
    best_name: str,
    meta: str,
    warning: str,
) -> str:
    data = {
        "dates": dates,
        "price": price,
        "comparison": comparison,
        "markers": markers,
    }
    return _TEMPLATE.format(
        meta=meta,
        warning=warning,
        best_name=best_name,
        data_json=json.dumps(data, ensure_ascii=False),
    )
