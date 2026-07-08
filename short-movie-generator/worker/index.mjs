// DEEP DIVE LOG — 쇼츠/릴스 자동 제작 + 콘텐츠 관리자 (Cloudflare Workers 무료)
// 구조: 이 워커는 조작 페이지(정적)만 서빙. 실제 제작·재생성은 GitHub Actions(무료)가 수행.
// 라우트(클라이언트): "/" 생성+현황 · "/library" 콘텐츠 목록 · "/c/<id>" 상세(열람·캡션편집·재생성).
// 데이터: 콘텐츠 레코드 content/<id>.json + 도감 catalog.json + 미디어는 GitHub Release URL.
// 인증: 사용자 개인 토큰(PAT)은 본인 기기 localStorage에만 저장(서버 저장 없음).
const OWNER = "jtaechul";
const REPO = "Product";
const WORKFLOW = "generate-short.yml";
const BRANCH = "claude/gemini-shorts-reels-generator-dhjfdt";

const HTML = `<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DEEP DIVE LOG · 쇼츠 제작·관리</title>
<style>
:root{--bg:#070b10;--panel:#0d151d;--line:rgba(150,200,215,.18);--cy:#43c8da;--wt:#e8eef2;--gy:#8fa0aa;--am:#ffc24d;--rd:#ff6b6b;--gr:#5be08a}
*{box-sizing:border-box;margin:0;padding:0}
body{background:radial-gradient(120% 100% at 50% 0%,#0b1620,#05080c 70%);color:var(--wt);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans KR",sans-serif;min-height:100vh}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.wrap{max-width:560px;margin:0 auto;padding:20px 16px 60px}
header{display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:16px}
.dot{width:10px;height:10px;border-radius:50%;background:var(--cy);box-shadow:0 0 12px var(--cy)}
h1{font-size:16px;letter-spacing:2px;font-weight:800}
h1 span{color:var(--cy)}
h1 a{color:inherit;text-decoration:none}
.nav{margin-left:auto;display:flex;gap:6px}
.nav a{color:var(--gy);font-size:12px;letter-spacing:1px;text-decoration:none;padding:6px 10px;border:1px solid var(--line);border-radius:8px}
.nav a.on{color:#eafcff;border-color:var(--cy)}
.card{background:linear-gradient(180deg,var(--panel),#0a1118);border:1px solid var(--line);border-radius:12px;padding:16px;position:relative;margin-bottom:16px}
.card::before{content:"";position:absolute;top:-1px;left:-1px;width:14px;height:14px;border-top:2px solid var(--cy);border-left:2px solid var(--cy);border-radius:2px 0 0 0}
.lbl{font-size:11px;letter-spacing:2px;color:var(--gy);text-transform:uppercase;margin:12px 0 6px;display:block}
.lbl:first-of-type{margin-top:0}
select,input,textarea,button{width:100%;background:#0a1018;color:var(--wt);border:1px solid var(--line);border-radius:8px;padding:12px;font-size:16px;font-family:inherit}
textarea{min-height:120px;resize:vertical;line-height:1.6}
button.go{margin-top:16px;background:linear-gradient(180deg,#0f2630,#0a1a22);border-color:var(--cy);color:#eafcff;font-weight:800;letter-spacing:2px;cursor:pointer}
button.go:active{background:#123240}
button:disabled{opacity:.5}
.hint{color:var(--gy);font-size:12px;margin-top:10px;line-height:1.6}
.hint a{color:var(--cy)}
.ok{color:var(--gr)}.err{color:var(--rd)}
.runs{margin-top:4px}
.run{display:flex;align-items:center;gap:10px;padding:10px 4px;border-bottom:1px solid rgba(150,200,215,.08);font-size:14px}
.run .st{font-size:11px;padding:2px 8px;border-radius:12px;border:1px solid var(--line);letter-spacing:1px;white-space:nowrap}
.run .st.prog{border-color:var(--cy);color:var(--cy)}
.run .st.done{border-color:var(--gr);color:var(--gr)}
.run .st.fail{border-color:var(--rd);color:var(--rd)}
.run a{color:var(--wt);text-decoration:none;flex:1}
.run .t{color:var(--gy);font-size:12px;white-space:nowrap}
.tok{margin-top:8px}
.tok summary{color:var(--gy);font-size:13px;cursor:pointer;letter-spacing:1px}
.tok ol{margin:10px 0 0 18px;color:#c6d2da;font-size:13px;line-height:1.8}
.tok a{color:var(--cy)}
.row2{display:flex;gap:8px;margin-top:8px}
.row2 input{flex:1}.row2 button{width:auto;padding:12px 14px}
.banner{font-size:13px;line-height:1.6;padding:10px 12px;border-radius:8px;border:1px solid var(--line);margin-top:12px;display:none}
.banner.show{display:block}
/* 라이브러리 목록 */
.clitem{display:flex;align-items:center;gap:12px;padding:10px 6px;border-bottom:1px solid rgba(150,200,215,.08);text-decoration:none;color:var(--wt)}
.clitem .no{font-family:ui-monospace,monospace;color:var(--cy);font-size:13px;min-width:42px}
.clitem .nm{flex:1;font-size:15px}.clitem .nm small{color:var(--gy);font-size:12px;display:block;margin-top:2px}
.clitem .t{color:var(--gy);font-size:12px;white-space:nowrap}
/* 상세 */
.detail video,.detail img{width:100%;border-radius:10px;border:1px solid var(--line);background:#000;display:block}
/* 일본어(좌)·한국어(우) 동시 열람 2단 프레임 */
.dual{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.dual textarea{min-height:220px}
.meta{font-size:13px;color:#c6d2da;line-height:1.7}
.meta b{color:var(--wt)}
.tag{display:inline-block;font-size:12px;color:var(--cy);border:1px solid var(--line);border-radius:20px;padding:2px 10px;margin:3px 4px 0 0}
.btnrow{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}
.btn{cursor:pointer;font-size:13px;padding:11px;letter-spacing:1px}
.btn.save{grid-column:1/3;border-color:var(--cy);color:#eafcff;background:linear-gradient(180deg,#0f2630,#0a1a22);font-weight:700}
.btn.warn{border-color:var(--am);color:var(--am)}
.btn.rd{border-color:var(--rd);color:var(--rd)}
.back{color:var(--gy);text-decoration:none;font-size:13px;display:inline-block;margin-bottom:12px}
.postscroll{display:flex;gap:8px;overflow-x:auto;padding-bottom:6px;scroll-snap-type:x mandatory}
.postscroll img{height:300px;border-radius:8px;border:1px solid var(--line);scroll-snap-align:start;flex:none}
.sect{font-size:11px;letter-spacing:2px;color:var(--cy);text-transform:uppercase;margin:18px 0 8px;border-top:1px solid var(--line);padding-top:14px}
</style></head>
<body><div class="wrap">
<header><div class="dot"></div>
  <h1><a href="/">DEEP DIVE <span>LOG</span></a></h1>
  <div class="nav" id="nav"><a href="/" data-p="home">제작</a><a href="/library" data-p="library">라이브러리</a></div>
</header>
<div id="view"><div class="hint">불러오는 중…</div></div>
</div>

<script>
const OWNER="${OWNER}",REPO="${REPO}",WF="${WORKFLOW}",BRANCH="${BRANCH}";
const SAVE_WF="save-caption.yml";  // 캡션 저장 전용(Contents PUT 대신 Actions 디스패치 → 403 회피)
const IG_WF="publish-instagram.yml";  // 인스타 릴스 발행(점검/발행)
const CAP_WF="regen-caption.yml";     // 캡션+해시태그만 재생성(영상 유지·저비용)
// 서버 토큰 모드: 워커가 GitHub 토큰을 보관·프록시 → 어느 브라우저/기기에서도 토큰 입력 불필요.
// 미설정 시 기존 브라우저 토큰(localStorage) 모드로 자동 폴백.
let SERVER=false;
let API="https://api.github.com/repos/"+OWNER+"/"+REPO;
const CONTENT_DIR="short-movie-generator/content";
const CATALOG_PATH="short-movie-generator/src/categories/deep_sea/catalog.json";
const $=s=>document.querySelector(s);
const view=()=>document.getElementById("view");
function pat(){try{return localStorage.getItem("gh_pat")||"";}catch(e){return "";}}
// 입력칸에 토큰이 있으면 즉시 저장하고 반환 → '저장' 버튼을 따로 누르지 않아도 한 번 입력하면 계속 유지
function ensurePat(){const el=document.getElementById("pat");if(el&&el.value.trim()){try{localStorage.setItem("gh_pat",el.value.trim());}catch(e){}el.value="";}return pat();}
function headers(auth){const h={"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"};if(auth&&!SERVER&&pat())h["Authorization"]="Bearer "+pat();return h;}
// 인증 준비: 서버 모드면 항상 OK(토큰 불필요), 아니면 입력칸/localStorage 토큰 확보
function authReady(){return SERVER||!!ensurePat();}
function num3(n){return String(n).padStart(3,"0");}
function esc(s){return (s||"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}
function b64(str){return btoa(unescape(encodeURIComponent(str)));}
function ago(iso){if(!iso)return"";const s=(Date.now()-new Date(iso))/1000;
  if(s<90)return Math.round(s)+"초 전";if(s<5400)return Math.round(s/60)+"분 전";
  if(s<172800)return Math.round(s/3600)+"시간 전";return Math.round(s/86400)+"일 전";}
function banner(t,cls){let m=$("#msg");if(!m)return;m.className="banner show "+(cls||"");m.innerHTML=t;}
// Release 미디어 → 워커 프록시 URL(iOS 재생 가능한 inline·video/mp4로 중계)
function prox(u){return u?"/api/media?u="+encodeURIComponent(u):"";}
// 구버전 합본 캡션(JP+【한국어 참고 번역】+KO) → {jp, ko} 분해(신 레코드는 분리 필드 사용)
function splitLegacy(cap){const M="【한국어 참고 번역】";const i=(cap||"").indexOf(M);
  if(i<0)return{jp:cap||"",ko:""};
  return{jp:cap.slice(0,i).replace(/[─\\s]+$/,""),ko:cap.slice(i+M.length).trim()};}
// 캡션 + 해시태그를 한 프레임에 합침(끝에 해시태그 한 줄 추가)
function mergeCap(cap,tagStr){cap=(cap||"").replace(/\\s+$/,"");tagStr=(tagStr||"").trim();
  return tagStr?cap+"\\n\\n"+tagStr:cap;}
// 합친 프레임에서 끝쪽 '해시태그만 있는 줄'을 분리 → {caption, tags[]}
function splitTags(text){const lines=(text||"").replace(/\\s+$/,"").split(/\\n/);const tags=[];
  while(lines.length){const ln=lines[lines.length-1].trim();
    if(ln===""){lines.pop();continue;}
    const toks=ln.split(/\\s+/);
    if(toks.length&&toks.every(t=>t.startsWith("#"))){tags.unshift(...toks);lines.pop();}
    else break;}
  return{caption:lines.join("\\n").replace(/\\s+$/,""),tags};}

async function fetchRaw(path){
  try{const r=await fetch(API+"/contents/"+path+"?ref="+BRANCH,{headers:{...headers(true),"Accept":"application/vnd.github.raw+json"}});
    if(!r.ok)return null;return await r.text();}catch(e){return null;}
}
async function fetchCatalog(){const t=await fetchRaw(CATALOG_PATH);try{const a=JSON.parse(t);return Array.isArray(a)?a:[];}catch(e){return [];}}
// 전 카테고리 콘텐츠 목록: content/*.json 을 직접 나열(카테고리별 catalog에 의존 안 함).
// 심해뿐 아니라 일반해양생물·미세조류·난파선 등 모든 제작물이 라이브러리/현황에 보이게 함.
async function listContent(){
  try{
    const r=await fetch(API+"/contents/"+CONTENT_DIR+"?ref="+BRANCH,{headers:headers(true)});
    if(!r.ok)return [];
    const files=await r.json();
    const ids=(Array.isArray(files)?files:[]).map(f=>f.name||"").filter(n=>/^\\d{3}\\.json$/.test(n)).map(n=>n.slice(0,3));
    const recs=await Promise.all(ids.map(async id=>{
      const rec=await fetchRecord(id); if(!rec)return null;
      const sp=rec.species||{};
      return {no:id, common_name_ko:sp.common_name_ko||sp.common_name_en||"종",
              common_name_en:sp.common_name_en||"", scientific_name:sp.scientific_name||"",
              date:String(rec.updated_at||rec.created_at||"").slice(0,10),
              hasVideo:!!(rec.media&&rec.media.video_url)};
    }));
    return recs.filter(Boolean).sort((a,b)=>(a.no<b.no?1:-1));
  }catch(e){return [];}
}
async function fetchRecord(id){const t=await fetchRaw(CONTENT_DIR+"/"+id+".json");try{return JSON.parse(t);}catch(e){return null;}}

// ── 라우팅: 전체 페이지 로드마다 경로로 뷰 결정 (worker가 모든 경로에 앱 셸 서빙) ──
function setNav(p){document.querySelectorAll("#nav a").forEach(a=>a.classList.toggle("on",a.dataset.p===p));}
function route(){
  const path=location.pathname;
  const m=path.match(/^\\/c\\/(\\w+)/);
  if(m){setNav("library");renderDetail(m[1]);}
  else if(path.indexOf("/library")===0){setNav("library");renderLibrary();}
  else{setNav("home");renderHome();}
}

// ── 홈: 생성 + 실행 현황 ──
function renderHome(){
  view().innerHTML=
  '<div class="card">'+
    '<span class="lbl">카테고리</span>'+
    '<select id="category">'+
      '<option value="deep_sea">심해 생물 (Deep Sea)</option>'+
      '<option value="marine_life">일반 해양생물 (Marine Life)</option>'+
      '<option value="marine_algae">해양 미세조류 (Marine Microalgae)</option>'+
      '<option value="shipwreck">침몰선 (Shipwreck)</option>'+
    '</select>'+
    '<span class="lbl">세부 (심해: 자동 추천 · 중복 없음)</span>'+
    '<select id="species">'+
      '<option value="auto">전체 자동 (아무 대상이나)</option>'+
      '<option value="auto:benthos">저서생물 (Benthos · 해저에 사는 생물)</option>'+
      '<option value="auto:plankton">부유생물 (Plankton · 떠다니는 생물)</option>'+
      '<option value="auto:nekton">유영생물 (Nekton · 헤엄치는 생물)</option>'+
    '</select>'+
    '<span class="lbl">또는 특정 대상 직접 입력 (선택)</span>'+
    '<input id="query" placeholder="비워두면 AI가 위 카테고리에서 자동 선택" autocomplete="off">'+
    '<div class="hint" style="margin:4px 0 8px">제작 방식: <b>실사 심해 영상(NOAA·공용도메인) + 일본어 오프닝 훅·엔드카드·전환·임팩트 사운드</b> (팬줌·Veo 미사용)</div>'+
    '<button class="go" id="go">쇼츠 생성 시작</button>'+
    '<div class="banner" id="msg"></div>'+
    '<div class="hint">완성 영상은 2~4분 뒤 <b>텔레그램</b>으로 전송되고, <a href="/library">라이브러리</a>에 등록됩니다.</div>'+
    (SERVER
      ? '<div class="hint ok" style="margin-top:8px">GitHub 연결됨 ✓ — 서버에 저장되어 <b>어느 브라우저/기기에서도 토큰 입력이 필요 없습니다.</b></div>'
      : ('<details class="tok" id="tokbox"'+(pat()?'':' open')+'><summary>'+(pat()?'GitHub 토큰 — 저장됨 ✓ (변경하려면 열기)':'최초 1회 설정 — GitHub 연결 토큰')+'</summary>'+
          '<ol><li><a href="https://github.com/settings/personal-access-tokens/new" target="_blank">GitHub 토큰 만들기</a>를 여세요.</li>'+
          '<li>Repository access → Only select repositories → '+OWNER+'/'+REPO+'</li>'+
          '<li>Permissions → <b>Actions: Read and write</b> + <b>Contents: Read and write</b>(캡션 저장용)</li>'+
          '<li>Generate token → 코드를 복사해 아래에 붙여넣고 <b>생성 시작</b>을 누르면 저장됩니다(따로 저장 불필요).</li></ol>'+
          '<div class="row2"><input id="pat" placeholder="github_pat_..." autocomplete="off"><button id="savepat">저장</button></div>'+
          '<div class="hint">이 기기 브라우저에 저장됩니다. (여러 기기에서 입력 없이 쓰려면 <b>서버 토큰</b> 설정 필요 — README 참고)</div>'+
        '</details>'))+
  '</div>'+
  '<div class="card"><span class="lbl">실행 현황 <a href="#" id="refresh" style="color:var(--cy);float:right;text-decoration:none">새로고침</a></span>'+
    '<div class="runs" id="runs"><div class="hint">불러오는 중…</div></div></div>';

  const _sp=$("#savepat");if(_sp)_sp.onclick=()=>{const v=$("#pat").value.trim();if(!v)return;
    localStorage.setItem("gh_pat",v);$("#pat").value="";const tb=$("#tokbox");if(tb)tb.open=false;banner("토큰 저장 완료. 다시 묻지 않습니다.","ok");};
  $("#go").onclick=async()=>{
    const category=($("#category")||{}).value||"deep_sea";
    // 심해가 아니면 세부 auto:* 는 의미 없음 → 그냥 auto
    let query=$("#query").value.trim()||$("#species").value;
    if(category!=="deep_sea" && query.startsWith("auto:")) query="auto";
    if(!authReady()){const tb=$("#tokbox");if(tb)tb.open=true;banner("GitHub 토큰을 아래 칸에 붙여넣고 생성을 누르면 이 기기에 저장돼 다시 묻지 않습니다.","err");return;}
    $("#go").disabled=true;banner("생성 요청 중…");
    try{const r=await fetch(API+"/actions/workflows/"+WF+"/dispatches",{method:"POST",headers:headers(true),
        body:JSON.stringify({ref:BRANCH,inputs:{query,category}})});
      if(r.status===204){banner("생성 시작! 2~4분 뒤 텔레그램 전송 + 라이브러리 등록.","ok");setTimeout(loadRuns,4000);setTimeout(loadRuns,12000);}
      else{const t=await r.text();banner("실패("+r.status+"): 토큰 권한(Actions)을 확인하세요.<br><span class='mono' style='font-size:11px'>"+esc(t.slice(0,140))+"</span>","err");}
    }catch(e){banner("요청 실패: "+e,"err");}
    $("#go").disabled=false;};
  $("#refresh").onclick=(e)=>{e.preventDefault();loadRuns();};
  loadRuns();
}
async function loadRuns(){
  try{
    const [r,cat]=await Promise.all([fetch(API+"/actions/workflows/"+WF+"/runs?per_page=8",{headers:headers(true)}),listContent()]);
    const j=await r.json();const el=$("#runs");if(!el)return;el.innerHTML="";
    (j.workflow_runs||[]).filter(x=>x.status!=="completed").forEach(run=>{
      el.insertAdjacentHTML("beforeend",'<div class="run"><span class="st prog">'+(run.status==="queued"?"대기열":"진행 중")+'</span>'+
        '<a href="'+run.html_url+'" target="_blank">#'+num3(run.run_number)+' 쇼츠 생성(진행상황 보기)</a><span class="t">'+ago(run.created_at)+"</span></div>");});
    cat.slice(0,12).forEach(it=>{
      const name=esc(it.common_name_ko||it.common_name_en||"종");
      el.insertAdjacentHTML("beforeend",'<div class="run"><span class="st done">완료</span>'+
        '<a href="/c/'+num3(it.no)+'">#'+num3(it.no)+'_'+name+' 쇼츠</a><span class="t">'+esc(it.date||"")+"</span></div>");});
    if(!el.innerHTML)el.innerHTML='<div class="hint">아직 실행 기록이 없습니다.</div>';
    if((j.workflow_runs||[]).some(x=>x.status!=="completed"))setTimeout(loadRuns,20000);
  }catch(e){const el=$("#runs");if(el)el.innerHTML='<div class="hint">현황 조회 실패 — <a href="https://github.com/'+OWNER+'/'+REPO+'/actions" target="_blank">GitHub</a></div>';}
}

// ── 라이브러리: 콘텐츠 목록(도감 기준) ──
async function renderLibrary(){
  view().innerHTML='<div class="card"><span class="lbl">제작된 콘텐츠 (탭하면 열람·수정·재생성)</span><div id="clist"><div class="hint">불러오는 중…</div></div></div>';
  const cat=await listContent();
  const el=document.getElementById("clist");
  if(!cat.length){el.innerHTML='<div class="hint">아직 제작된 콘텐츠가 없습니다. <a href="/">제작하러 가기</a></div>';return;}
  el.innerHTML=cat.map(it=>{
    const id=num3(it.no);
    return '<a class="clitem" href="/c/'+id+'"><span class="no">#'+id+'</span>'+
      '<span class="nm">'+esc(it.common_name_ko||"종")+'<small>'+esc(it.common_name_en||"")+" · "+esc(it.scientific_name||"")+'</small></span>'+
      '<span class="t">'+esc(it.date||"")+'</span></a>';
  }).join("");
}

// 게시물(캐러셀) 섹션: 5장 이미지 가로 스크롤 + 게시물 캡션(다음날 오후 발행용)
function postSection(post){
  if(!post||!Array.isArray(post.image_urls)||!post.image_urls.length)
    return '<div class="sect">게시물(캐러셀)</div><div class="hint">아직 게시물 이미지가 없습니다(제작 직후 잠시 후 반영).</div>';
  const imgs=post.image_urls.map(u=>'<img src="'+prox(u)+'" loading="lazy">').join("");
  const cap=esc(post.caption||"").replace(/\\n/g,"<br>");
  return '<div class="sect">게시물(캐러셀) · '+post.image_urls.length+'장 · 다음날 오후 발행</div>'+
    '<div class="postscroll">'+imgs+'</div>'+
    (cap?'<div class="hint" style="margin-top:10px;white-space:normal">'+cap+'</div>':'');
}

// ── 상세: 미리보기 + 캡션 편집 + 재생성 ──
async function renderDetail(id){
  view().innerHTML='<a class="back" href="/library">← 라이브러리</a><div class="card" id="dcard"><div class="hint">불러오는 중…</div></div>';
  const rec=await fetchRecord(id);
  const dc=document.getElementById("dcard");
  if(!rec){
    // 레코드 없음: 도감 정보로 부드럽게 안내(빨간 오류 대신). 제작 미완료/이전 기록/미디어 미반영 상태.
    const cat=await fetchCatalog();
    const it=cat.find(x=>num3(x.no)===id);
    const nm=it?esc(it.common_name_ko||"종")+(it.common_name_en?' · '+esc(it.common_name_en):''):"";
    dc.innerHTML='<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:10px"><b style="font-size:19px">#'+esc(id)+'</b>'+
        (nm?'<span class="mono" style="color:var(--gy);font-size:13px">'+nm+'</span>':'')+'</div>'+
      '<div class="hint">이 회차는 아직 제작이 완료되지 않았거나 미디어가 반영되기 전입니다.<br>'+
        '제작이 끝나면 영상·캡션이 자동으로 채워집니다(보통 2~4분). 완성 영상은 <b>텔레그램</b>으로도 전송됩니다.</div>'+
      '<div class="btnrow" style="margin-top:14px"><a class="btn" href="/library">← 라이브러리로</a></div>';
    return;
  }
  const sp=rec.species||{},re=rec.reels||{},md=rec.media||{},src=rec.source||{};
  let mediaHtml="";
  // Release 자산은 attachment/octet-stream이라 <video> 직접 재생 불가(iOS) → 워커 프록시 경유
  if(md.video_url)mediaHtml='<video src="'+prox(md.video_url)+'" controls playsinline preload="metadata" poster="'+(md.cover_url?prox(md.cover_url):"")+'"></video>';
  else if(md.cover_url)mediaHtml='<img src="'+prox(md.cover_url)+'">';
  else mediaHtml='<div class="hint">미디어가 아직 업로드되지 않았습니다(제작 직후 잠시 후 반영).</div>';
  // 일/한 분리: 신규 레코드는 분리 필드(caption_ko 등), 구 레코드는 합본 캡션을 분해해 표시
  const legacy=splitLegacy(re.caption||"");
  const capJP=legacy.jp, capKO=re.caption_ko||legacy.ko;
  const hookKO=re.hook_ko||"";
  const tagsKO=(re.hashtags_ko||[]).join(" ");
  const tags=(re.hashtags||[]).map(t=>'<span class="tag">'+esc(t)+'</span>').join("");
  dc.className="card detail";
  dc.innerHTML=
    '<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:10px"><b style="font-size:19px">#'+esc(id)+' '+esc(sp.common_name_ko||"")+'</b>'+
      '<span class="mono" style="color:var(--gy);font-size:12px">'+esc(sp.common_name_en||"")+'</span></div>'+
    mediaHtml+
    (md.video_url?'<div class="btnrow" style="margin-top:8px"><button class="btn save" id="bdl">비디오 저장하기</button></div><div class="hint" id="dlhint" style="margin-top:6px"></div>':"")+
    '<div class="meta" style="margin-top:12px"><b>학명</b> <i>'+esc(sp.scientific_name||"")+'</i> · <b>수심</b> '+esc(sp.depth_range_m||"?")+'m<br>'+
      '<b>서식</b> '+esc(sp.habitat||"?")+' · <b>분포</b> '+esc(sp.distribution||"?")+'</div>'+
    // 캡션·해시태그를 한 프레임에 합쳐 표시(일본어 발행 / 한국어 참고). 저장 시 끝의 해시태그 줄을 분리.
    '<input type="hidden" id="ehook" value="'+esc(re.hook||"")+'">'+
    '<input type="hidden" id="ehookko" value="'+esc(hookKO)+'">'+
    '<div class="dual">'+
      '<div><span class="lbl">캡션 + 해시태그 · 일본어(발행용)</span>'+
        '<textarea id="ecapjp" rows="12">'+esc(mergeCap(capJP,(re.hashtags||[]).join(" ")))+'</textarea>'+
        '<button class="btn save" id="cpjp" style="margin-top:6px">일본어 캡션+해시태그 복사</button></div>'+
      '<div><span class="lbl">캡션 + 해시태그 · 한국어(참고 번역)</span>'+
        '<textarea id="ecapko" rows="12">'+esc(mergeCap(capKO,tagsKO))+'</textarea>'+
        '<button class="btn" id="cpko" style="margin-top:6px">한국어 복사</button></div>'+
    '</div>'+
    '<div style="margin-top:6px">'+tags+'</div>'+
    '<div class="banner" id="msg"></div>'+
    '<div class="btnrow">'+
      '<button class="btn save" id="bsave">수정 내용 저장 (재생성 없음)</button>'+
      '<button class="btn warn" id="bcap">캡션·해시태그 재생성 (영상 유지)</button>'+
      '<button class="btn warn" id="bvid">영상 다시 제작 (무료)</button>'+
      '<button class="btn" id="ball" style="grid-column:1/3">전체 재생성 (무료)</button>'+
      '<button class="btn" id="bigp" style="grid-column:1/3;background:#833ab4;color:#fff">인스타 계정 점검 (발행 안 함)</button>'+
      '<button class="btn" id="big" style="grid-column:1/3;background:#c13584;color:#fff">인스타 릴스 발행</button>'+
    '</div>'+
    postSection(rec.post)+
    '<div class="hint">이미지 출처: '+esc(src.image_credit||"—")+'<br>정보 출처: '+esc((src.info_sources||[]).join(" · ")||"—")+'</div>';

  // 현 시스템은 실사 영상 재편집(무료) — Veo·카드뉴스 이미지 재생성은 구 시스템 유물이라 제거
  if($("#bdl"))$("#bdl").onclick=()=>saveVideo(prox(md.video_url),esc(id)+"_"+(sp.common_name_ko||"reel")+".mp4");
  $("#cpjp").onclick=()=>copyText($("#ecapjp").value,"일본어 캡션+해시태그를 복사했어요. 릴스에 붙여넣기 하세요.");
  $("#cpko").onclick=()=>copyText($("#ecapko").value,"한국어(참고)를 복사했어요.");
  $("#bsave").onclick=()=>saveCaption(id);
  $("#bcap").onclick=()=>capRegen(id);
  $("#bvid").onclick=()=>{if(confirm("이 회차의 영상을 같은 종으로 처음부터 다시 만듭니다(무료·2~4분). 진행할까요?"))regen(id,"video");};
  $("#ball").onclick=()=>{if(confirm("영상·캡션을 모두 처음부터 다시 만듭니다(무료·2~4분). 진행할까요?"))regen(id,"all");};
  $("#bigp").onclick=()=>igPublish(id,true);
  $("#big").onclick=()=>{if(confirm("이 릴스를 인스타그램(@abyss_0cean)에 실제로 발행합니다. 되돌릴 수 없어요. 진행할까요?"))igPublish(id,false);};
}

async function saveCaption(id){
  if(!authReady()){banner("캡션 저장에는 GitHub 토큰(Actions: Read and write)이 필요합니다.","err");return;}
  // Contents API 직접 PUT은 토큰 권한에 따라 403이 나므로, 저장 전용 워크플로를 디스패치한다
  // (재생성 버튼과 동일한 Actions 권한만 필요 → 항상 성공). 커밋은 워크플로가 GITHUB_TOKEN으로 처리.
  const jp=splitTags($("#ecapjp").value);          // 일본어 프레임 → 캡션 + 해시태그 분리
  const ko=splitTags($("#ecapko").value);          // 한국어 프레임 → 캡션 + 해시태그 분리
  banner("저장 중… (반영까지 20~40초)");
  try{
    const r=await fetch(API+"/actions/workflows/"+SAVE_WF+"/dispatches",{method:"POST",headers:headers(true),
      body:JSON.stringify({ref:BRANCH,inputs:{
        content_id:id,
        caption:jp.caption, hashtags:jp.tags.join(" "),
        caption_ko:ko.caption, hashtags_ko:ko.tags.join(" "),
        hook:($("#ehook")||{}).value||"", hook_ko:($("#ehookko")||{}).value||"",
      }})});
    if(r.status===204)banner("저장 시작! 20~40초 뒤 저장소에 반영됩니다(새로고침).","ok");
    else{const t=await r.text();banner("저장 실패("+r.status+")<br><span class='mono' style='font-size:11px'>"+esc(t.slice(0,140))+"</span>","err");}
  }catch(e){banner("저장 오류: "+e,"err");}
}

// 클립보드 복사(릴스 붙여넣기용). navigator.clipboard 우선, 실패 시 textarea 폴백.
async function copyText(text,okmsg){
  try{
    if(navigator.clipboard&&navigator.clipboard.writeText){await navigator.clipboard.writeText(text);}
    else{const ta=document.createElement("textarea");ta.value=text;ta.style.position="fixed";ta.style.opacity="0";
      document.body.appendChild(ta);ta.focus();ta.select();document.execCommand("copy");ta.remove();}
    banner(okmsg||"복사했어요.","ok");
  }catch(e){banner("복사 실패 — 텍스트를 직접 길게 눌러 복사하세요: "+esc(String(e)),"err");}
}

// 비디오 저장: ① iOS 공유 시트(navigator.share)로 "비디오를 사진에 저장" 직접 노출
//             ② 안 되면 Blob 다운로드(파일 앱 저장). 길게눌러가 안 먹는 기기 대응.
async function saveVideo(u,name){
  const h=$("#dlhint"); const say=t=>{if(h)h.innerHTML=t;};
  const btn=$("#bdl"); if(btn)btn.disabled=true;
  say("동영상 준비 중… (10MB 내외, 잠시만요)");
  try{
    const r=await fetch(u); if(!r.ok)throw new Error("불러오기 "+r.status);
    const blob=await r.blob();
    const file=new File([blob],name,{type:"video/mp4"});
    // ① 네이티브 공유 시트(아이폰: "비디오를 사진에 저장"이 여기 있음)
    if(navigator.canShare&&navigator.canShare({files:[file]})){
      try{ await navigator.share({files:[file],title:name});
        say('공유 창에서 <b>"비디오를 사진에 저장"</b>을 누르세요.'); if(btn)btn.disabled=false; return;
      }catch(e){ if(String(e).indexOf("AbortError")>=0){say("취소됨."); if(btn)btn.disabled=false; return;} }
    }
    // ② 폴백: Blob 다운로드 → 파일 앱에 저장(거기서 사진으로 옮길 수 있음)
    const url=URL.createObjectURL(blob);
    const a=document.createElement("a"); a.href=url; a.download=name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),5000);
    say('저장을 시작했어요. (아이폰은 <b>"파일"에 저장</b> → 사진 앱으로 옮길 수 있어요)');
  }catch(e){ say("저장 실패: "+esc(String(e))+" — 영상 재생창의 공유 버튼으로도 저장할 수 있어요."); }
  if(btn)btn.disabled=false;
}

async function capRegen(id){
  if(!authReady()){banner("재생성에는 GitHub 토큰(Actions: Read and write)이 필요합니다.","err");return;}
  banner("캡션·해시태그 재생성 중… (영상은 그대로, 30~60초)");
  try{
    const r=await fetch(API+"/actions/workflows/"+CAP_WF+"/dispatches",{method:"POST",headers:headers(true),
      body:JSON.stringify({ref:BRANCH,inputs:{content_id:id}})});
    if(r.status===204)banner("시작! 30~60초 뒤 캡션·해시태그가 새로 채워집니다(새로고침).","ok");
    else{const t=await r.text();banner("실패("+r.status+")<br><span class='mono' style='font-size:11px'>"+esc(t.slice(0,140))+"</span>","err");}
  }catch(e){banner("요청 실패: "+e,"err");}
}

async function igPublish(id,probe){
  if(!authReady()){banner("인스타 발행에는 GitHub 토큰(Actions: Read and write)이 필요합니다.","err");return;}
  banner(probe?"인스타 계정 점검 중… (발행 안 함)":"인스타 발행 요청 중… (1~3분 소요)");
  try{
    const r=await fetch(API+"/actions/workflows/"+IG_WF+"/dispatches",{method:"POST",headers:headers(true),
      body:JSON.stringify({ref:BRANCH,inputs:{content_id:id,probe:probe?"true":"false"}})});
    if(r.status===204)banner(probe?"점검 시작! 결과는 텔레그램으로 옵니다(계정 확인 성공/실패).":"발행 시작! 완료되면 텔레그램으로 알림이 옵니다(1~3분).","ok");
    else{const t=await r.text();banner("실패("+r.status+")<br><span class='mono' style='font-size:11px'>"+esc(t.slice(0,140))+"</span>","err");}
  }catch(e){banner("요청 실패: "+e,"err");}
}

async function regen(id,scope){
  if(!authReady()){banner("재생성에는 GitHub 토큰(Actions: Read and write)이 필요합니다.","err");return;}
  banner("재생성 요청 중… ("+scope+")");
  const viz="panzoom"; // 현 시스템은 reels(실사 재편집·무료) 고정 — Veo 미사용(워크플로가 --mode reels 강제)
  try{
    const r=await fetch(API+"/actions/workflows/"+WF+"/dispatches",{method:"POST",headers:headers(true),
      body:JSON.stringify({ref:BRANCH,inputs:{content_id:id,scope:scope,visualizer:viz}})});
    if(r.status===204)banner("재생성 시작! 완료되면 이 페이지 미디어/캡션이 갱신됩니다(새로고침).","ok");
    else{const t=await r.text();banner("실패("+r.status+")<br><span class='mono' style='font-size:11px'>"+esc(t.slice(0,140))+"</span>","err");}
  }catch(e){banner("요청 실패: "+e,"err");}
}

// 서버 토큰 모드 감지 후 라우팅(어느 브라우저든 서버에 토큰이 있으면 입력창을 아예 띄우지 않음)
async function init(){
  try{const r=await fetch("/api/mode");if(r.ok){const j=await r.json();SERVER=!!j.server;if(SERVER)API="/api/gh";}}catch(e){}
  route();
}
init();
</script>
</body></html>`;

// ── 서버 측: GitHub 토큰(Cloudflare Secret env.GH_PAT)로 프록시 → 브라우저 토큰 불필요 ──
function j(o, status){return new Response(JSON.stringify(o),{status:status||200,headers:{"Content-Type":"application/json","Cache-Control":"no-store"}});}

async function ghProxy(request, url, env){
  const token = env && env.GH_PAT;
  if(!token) return j({error:"server token not configured"}, 501);
  const rest = url.pathname.slice("/api/gh/".length);
  const m = request.method;
  // 이 앱이 실제로 쓰는 경로/메서드만 허용(토큰 오남용 방지)
  const ok =
    (m==="POST" && /^actions\/workflows\/[^/]+\/dispatches$/.test(rest)) ||
    (m==="GET"  && /^actions\/workflows\/[^/]+\/runs/.test(rest)) ||
    (m==="GET"  && /^contents\//.test(rest));
  if(!ok) return j({error:"path not allowed"}, 403);
  const target = "https://api.github.com/repos/" + OWNER + "/" + REPO + "/" + rest + url.search;
  const h = {
    "Accept": request.headers.get("Accept") || "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "Authorization": "Bearer " + token,
    "User-Agent": "deep-dive-log-dashboard",
  };
  const body = (m==="GET"||m==="HEAD") ? undefined : await request.text();
  if(body) h["Content-Type"] = "application/json";
  const resp = await fetch(target, {method:m, headers:h, body});
  const text = await resp.text();
  return new Response(text, {status:resp.status,
    headers:{"Content-Type": resp.headers.get("Content-Type") || "application/json", "Cache-Control":"no-store"}});
}

// ── 미디어 프록시: GitHub Release 자산을 '인라인 재생 가능'하게 중계 ──
// 왜(실제 결함): Release 다운로드 URL은 Content-Disposition: attachment +
// Content-Type: application/octet-stream 으로 응답해 iOS Safari <video>가 재생을 거부했다
// (라이브러리 영상이 검은 화면 + 재생불가 아이콘). 워커가 올바른 타입·inline으로 바꿔 중계하고
// Range 요청을 그대로 전달해 스트리밍 탐색도 지원한다.
const MEDIA_PREFIX = "https://github.com/" + OWNER + "/" + REPO + "/releases/download/";
const MEDIA_TYPES = { mp4: "video/mp4", jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png" };

async function mediaProxy(request, url) {
  const u = url.searchParams.get("u") || "";
  if (!u.startsWith(MEDIA_PREFIX)) return j({ error: "url not allowed" }, 403);  // 개방 프록시 방지
  const ext = (u.split(".").pop() || "").toLowerCase();
  const type = MEDIA_TYPES[ext];
  if (!type) return j({ error: "type not allowed" }, 403);
  const h = { "User-Agent": "deep-dive-log-dashboard" };
  const range = request.headers.get("Range");
  if (range) h["Range"] = range;
  const resp = await fetch(u, { headers: h, redirect: "follow" });
  if (!resp.ok && resp.status !== 206) return j({ error: "upstream " + resp.status }, 502);
  const out = new Headers();
  out.set("Content-Type", type);
  out.set("Content-Disposition", "inline");   // 항상 inline 재생(iOS '파일 열기' 화면 전환 방지)
  out.set("Accept-Ranges", "bytes");
  out.set("Cache-Control", "public, max-age=86400");
  for (const k of ["Content-Length", "Content-Range"]) {
    const v = resp.headers.get(k); if (v) out.set(k, v);
  }
  return new Response(resp.body, { status: resp.status, headers: out });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/health") return new Response("ok");
    if (url.pathname === "/api/mode") return j({ server: !!(env && env.GH_PAT) });
    if (url.pathname === "/api/media") return mediaProxy(request, url);
    if (url.pathname.startsWith("/api/gh/")) return ghProxy(request, url, env);
    return new Response(HTML, {
      headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" },
    });
  },
};
