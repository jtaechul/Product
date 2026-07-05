// DEEP DIVE LOG — 쇼츠/릴스 자동 제작 홈페이지 (Cloudflare Workers 무료)
// 구조: 이 워커는 제작 조작 페이지(정적)만 서빙. 실제 영상 제작은 GitHub Actions(무료)가 수행,
// 완성본은 텔레그램으로 자동 전송. 생성 트리거는 브라우저가 GitHub API를 직접 호출
// (사용자 개인 토큰은 본인 기기 localStorage에만 저장 — 서버 저장 없음).
const OWNER = "jtaechul";
const REPO = "Product";
const WORKFLOW = "generate-short.yml";
const BRANCH = "claude/gemini-shorts-reels-generator-dhjfdt";

const HTML = `<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DEEP DIVE LOG · 쇼츠 제작</title>
<style>
:root{--bg:#070b10;--panel:#0d151d;--line:rgba(150,200,215,.18);--cy:#43c8da;--wt:#e8eef2;--gy:#8fa0aa}
*{box-sizing:border-box;margin:0;padding:0}
body{background:radial-gradient(120% 100% at 50% 0%,#0b1620,#05080c 70%);color:var(--wt);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans KR",sans-serif;min-height:100vh}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.wrap{max-width:560px;margin:0 auto;padding:24px 16px 60px}
header{display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:18px}
.dot{width:10px;height:10px;border-radius:50%;background:var(--cy);box-shadow:0 0 12px var(--cy)}
h1{font-size:17px;letter-spacing:2px;font-weight:800}
h1 span{color:var(--cy)}
.sub{color:var(--gy);font-size:11px;letter-spacing:2px;margin-left:auto}
.card{background:linear-gradient(180deg,var(--panel),#0a1118);border:1px solid var(--line);border-radius:12px;padding:16px;position:relative;margin-bottom:16px}
.card::before{content:"";position:absolute;top:-1px;left:-1px;width:14px;height:14px;border-top:2px solid var(--cy);border-left:2px solid var(--cy);border-radius:2px 0 0 0}
.lbl{font-size:11px;letter-spacing:2px;color:var(--gy);text-transform:uppercase;margin:12px 0 6px;display:block}
.lbl:first-of-type{margin-top:0}
select,input,button{width:100%;background:#0a1018;color:var(--wt);border:1px solid var(--line);border-radius:8px;padding:12px;font-size:16px;font-family:inherit}
button.go{margin-top:16px;background:linear-gradient(180deg,#0f2630,#0a1a22);border-color:var(--cy);color:#eafcff;font-weight:800;letter-spacing:2px;cursor:pointer}
button.go:active{background:#123240}
button.go:disabled{opacity:.5}
.hint{color:var(--gy);font-size:12px;margin-top:10px;line-height:1.6}
.hint a{color:var(--cy)}
.ok{color:#5be08a}.err{color:#ff7b7b}
.runs{margin-top:4px}
.run{display:flex;align-items:center;gap:10px;padding:10px 4px;border-bottom:1px solid rgba(150,200,215,.08);font-size:14px}
.run .st{font-size:11px;padding:2px 8px;border-radius:12px;border:1px solid var(--line);letter-spacing:1px;white-space:nowrap}
.run .st.prog{border-color:var(--cy);color:var(--cy)}
.run .st.done{border-color:#5be08a;color:#5be08a}
.run .st.fail{border-color:#ff7b7b;color:#ff7b7b}
.run a{color:var(--wt);text-decoration:none;flex:1}
.run .t{color:var(--gy);font-size:12px;white-space:nowrap}
.tok{margin-top:8px}
.tok summary{color:var(--gy);font-size:13px;cursor:pointer;letter-spacing:1px}
.tok ol{margin:10px 0 0 18px;color:#c6d2da;font-size:13px;line-height:1.8}
.tok a{color:var(--cy)}
.row2{display:flex;gap:8px;margin-top:8px}
.row2 input{flex:1}
.row2 button{width:auto;padding:12px 14px}
.banner{font-size:13px;line-height:1.6;padding:10px 12px;border-radius:8px;border:1px solid var(--line);margin-top:12px;display:none}
.banner.show{display:block}
</style></head>
<body><div class="wrap">
<header><div class="dot"></div><h1>DEEP DIVE <span>LOG</span> · 쇼츠 제작</h1><div class="sub mono">FREE FACTORY</div></header>

<div class="card">
  <span class="lbl">생물 카테고리 (AI가 실존 종을 자동 추천 · 중복 없음)</span>
  <select id="species">
    <option value="auto">🎲 전체 자동 (아무 카테고리나)</option>
    <option value="auto:benthos">저서생물 (Benthos · 해저에 사는 생물)</option>
    <option value="auto:plankton">부유생물 (Plankton · 떠다니는 생물)</option>
    <option value="auto:nekton">유영생물 (Nekton · 헤엄치는 생물)</option>
  </select>
  <span class="lbl">또는 특정 종 직접 입력 (선택)</span>
  <input id="query" placeholder="비워두면 AI가 위 카테고리에서 자동 선택" autocomplete="off">
  <span class="lbl">영상 생성 방식</span>
  <select id="visualizer">
    <option value="panzoom">panzoom · 무료 미리보기 (키 불필요)</option>
    <option value="veo_text2video">veo_text2video · 실제 AI 영상 (Veo, 하루 10회)</option>
  </select>
  <button class="go" id="go">▶ 쇼츠 생성 시작</button>
  <div class="banner" id="msg"></div>
  <div class="hint">완성 영상은 2~4분 뒤 <b>텔레그램(북캐럿셀봇)</b>으로 자동 전송됩니다.
    아래 실행 현황에서 진행 상태를 확인하세요.</div>
  <details class="tok" id="tokbox">
    <summary>⚙ 최초 1회 설정 — GitHub 연결 토큰</summary>
    <ol>
      <li><a href="https://github.com/settings/personal-access-tokens/new" target="_blank">GitHub 토큰 만들기 페이지</a>를 여세요.</li>
      <li>Token name: <b>shorts-maker</b> / Expiration: 원하는 기간</li>
      <li>Repository access → <b>Only select repositories</b> → <b>${OWNER}/${REPO}</b> 선택</li>
      <li>Permissions → Repository permissions → <b>Actions</b> → <b>Read and write</b></li>
      <li>맨 아래 <b>Generate token</b> → 나온 코드를 복사해 아래에 붙여넣기</li>
    </ol>
    <div class="row2"><input id="pat" placeholder="github_pat_..." autocomplete="off">
      <button id="savepat">저장</button></div>
    <div class="hint">토큰은 <b>이 기기 브라우저에만</b> 저장됩니다(서버 전송·저장 없음).
      토큰 없이 쓰려면 <a href="https://github.com/${OWNER}/${REPO}/actions/workflows/${WORKFLOW}" target="_blank">GitHub 실행 페이지</a>에서 Run workflow를 눌러도 됩니다.</div>
  </details>
</div>

<div class="card">
  <span class="lbl">실행 현황 <a href="#" id="refresh" style="color:var(--cy);float:right;text-decoration:none">↻ 새로고침</a></span>
  <div class="runs" id="runs"><div class="hint">불러오는 중…</div></div>
</div>
</div>

<script>
const OWNER="${OWNER}",REPO="${REPO}",WF="${WORKFLOW}",BRANCH="${BRANCH}";
const $=s=>document.querySelector(s);
const API="https://api.github.com/repos/"+OWNER+"/"+REPO;
function pat(){return localStorage.getItem("gh_pat")||"";}
function msg(t,cls){const m=$("#msg");m.className="banner show "+(cls||"");m.innerHTML=t;}
function headers(auth){const h={"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"};if(auth&&pat())h["Authorization"]="Bearer "+pat();return h;}

$("#savepat").onclick=()=>{const v=$("#pat").value.trim();if(!v)return;
  localStorage.setItem("gh_pat",v);$("#pat").value="";$("#tokbox").open=false;
  msg("토큰 저장 완료 — 이제 버튼으로 바로 생성할 수 있습니다.","ok");};

$("#go").onclick=async()=>{
  const query=$("#query").value.trim()||$("#species").value;
  if(!pat()){$("#tokbox").open=true;
    msg("최초 1회 GitHub 연결 토큰이 필요합니다. 아래 ⚙ 설정을 따라 주세요.<br>"+
        "(또는 <a href='https://github.com/"+OWNER+"/"+REPO+"/actions/workflows/"+WF+"' target='_blank'>GitHub 실행 페이지</a>에서 직접 실행)","err");
    return;}
  $("#go").disabled=true;msg("생성 요청 중…");
  try{
    const r=await fetch(API+"/actions/workflows/"+WF+"/dispatches",{method:"POST",headers:headers(true),
      body:JSON.stringify({ref:BRANCH,inputs:{query,visualizer:$("#visualizer").value}})});
    if(r.status===204){msg("✔ 생성 시작! 2~4분 뒤 텔레그램으로 영상이 도착합니다.","ok");
      setTimeout(loadRuns,4000);setTimeout(loadRuns,12000);}
    else{const t=await r.text();msg("실패("+r.status+"): 토큰 권한(Actions: Read and write)을 확인하세요.<br><span class='mono' style='font-size:11px'>"+t.slice(0,140)+"</span>","err");}
  }catch(e){msg("요청 실패: "+e,"err");}
  $("#go").disabled=false;
};

function ago(iso){const s=(Date.now()-new Date(iso))/1000;
  if(s<90)return Math.round(s)+"초 전";if(s<5400)return Math.round(s/60)+"분 전";
  if(s<172800)return Math.round(s/3600)+"시간 전";return Math.round(s/86400)+"일 전";}
const CATALOG_PATH="short-movie-generator/src/categories/deep_sea/catalog.json";
function num3(n){return String(n).padStart(3,"0");}
async function fetchCatalog(){
  try{
    const r=await fetch(API+"/contents/"+CATALOG_PATH+"?ref="+BRANCH,
      {headers:{...headers(true),"Accept":"application/vnd.github.raw+json"}});
    if(!r.ok)return [];
    const arr=JSON.parse(await r.text());
    return Array.isArray(arr)?arr:[];
  }catch(e){return [];}
}
async function loadRuns(){
  try{
    const [r,cat]=await Promise.all([
      fetch(API+"/actions/workflows/"+WF+"/runs?per_page=8",{headers:headers(true)}),
      fetchCatalog(),
    ]);
    const j=await r.json();
    const el=$("#runs");el.innerHTML="";
    // 1) 진행 중/대기열 실행 (아직 도감에 기록 전) — 상단에 표시
    (j.workflow_runs||[]).filter(run=>run.status!=="completed").forEach(run=>{
      const label=run.status==="queued"?"대기열":"진행 중";
      el.insertAdjacentHTML("beforeend",
        '<div class="run"><span class="st prog">'+label+'</span>'+
        '<a href="'+run.html_url+'" target="_blank">#'+num3(run.run_number)+' 쇼츠 생성</a>'+
        '<span class="t">'+ago(run.created_at)+"</span></div>");
    });
    // 2) 제작 완료된 심해 생물 도감(#000_국문명) — 번호 내림차순(최근 먼저)
    const logged=[...cat].sort((a,b)=>(b.no||0)-(a.no||0)).slice(0,12);
    logged.forEach(it=>{
      const name=it.common_name_ko||it.common_name_en||"종";
      el.insertAdjacentHTML("beforeend",
        '<div class="run"><span class="st done">완료·전송됨</span>'+
        '<a href="https://github.com/'+OWNER+'/'+REPO+'/actions/workflows/'+WF+'" target="_blank">'+
        '#'+num3(it.no)+'_'+name+' 쇼츠 생성</a>'+
        '<span class="t">'+(it.date||"")+"</span></div>");
    });
    if(!el.innerHTML)el.innerHTML='<div class="hint">아직 실행 기록이 없습니다.</div>';
    if((j.workflow_runs||[]).some(x=>x.status!=="completed"))setTimeout(loadRuns,20000);
  }catch(e){$("#runs").innerHTML='<div class="hint">현황 조회 실패 — <a href="https://github.com/'+OWNER+'/'+REPO+'/actions" target="_blank" style="color:var(--cy)">GitHub에서 보기</a></div>';}
}
$("#refresh").onclick=(e)=>{e.preventDefault();loadRuns();};
loadRuns();
</script>
</body></html>`;

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname === "/health") return new Response("ok");
    return new Response(HTML, {
      headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" },
    });
  },
};
