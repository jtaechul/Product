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
const API="https://api.github.com/repos/"+OWNER+"/"+REPO;
const CONTENT_DIR="short-movie-generator/content";
const CATALOG_PATH="short-movie-generator/src/categories/deep_sea/catalog.json";
const $=s=>document.querySelector(s);
const view=()=>document.getElementById("view");
function pat(){return localStorage.getItem("gh_pat")||"";}
function headers(auth){const h={"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"};if(auth&&pat())h["Authorization"]="Bearer "+pat();return h;}
function num3(n){return String(n).padStart(3,"0");}
function esc(s){return (s||"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}
function b64(str){return btoa(unescape(encodeURIComponent(str)));}
function ago(iso){if(!iso)return"";const s=(Date.now()-new Date(iso))/1000;
  if(s<90)return Math.round(s)+"초 전";if(s<5400)return Math.round(s/60)+"분 전";
  if(s<172800)return Math.round(s/3600)+"시간 전";return Math.round(s/86400)+"일 전";}
function banner(t,cls){let m=$("#msg");if(!m)return;m.className="banner show "+(cls||"");m.innerHTML=t;}

async function fetchRaw(path){
  try{const r=await fetch(API+"/contents/"+path+"?ref="+BRANCH,{headers:{...headers(true),"Accept":"application/vnd.github.raw+json"}});
    if(!r.ok)return null;return await r.text();}catch(e){return null;}
}
async function fetchCatalog(){const t=await fetchRaw(CATALOG_PATH);try{const a=JSON.parse(t);return Array.isArray(a)?a:[];}catch(e){return [];}}
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
    '<span class="lbl">생물 카테고리 (AI가 실존 종을 자동 추천 · 중복 없음)</span>'+
    '<select id="species">'+
      '<option value="auto">전체 자동 (아무 카테고리나)</option>'+
      '<option value="auto:benthos">저서생물 (Benthos · 해저에 사는 생물)</option>'+
      '<option value="auto:plankton">부유생물 (Plankton · 떠다니는 생물)</option>'+
      '<option value="auto:nekton">유영생물 (Nekton · 헤엄치는 생물)</option>'+
    '</select>'+
    '<span class="lbl">또는 특정 종 직접 입력 (선택)</span>'+
    '<input id="query" placeholder="비워두면 AI가 위 카테고리에서 자동 선택" autocomplete="off">'+
    '<span class="lbl">영상 생성 방식</span>'+
    '<select id="visualizer">'+
      '<option value="panzoom">panzoom · 무료 미리보기 (키 불필요)</option>'+
      '<option value="veo_text2video">veo_text2video · 실제 AI 영상 (Veo, 하루 10회)</option>'+
    '</select>'+
    '<button class="go" id="go">쇼츠 생성 시작</button>'+
    '<div class="banner" id="msg"></div>'+
    '<div class="hint">완성 영상은 2~4분 뒤 <b>텔레그램</b>으로 전송되고, <a href="/library">라이브러리</a>에 등록됩니다.</div>'+
    '<details class="tok" id="tokbox"><summary>최초 1회 설정 — GitHub 연결 토큰</summary>'+
      '<ol><li><a href="https://github.com/settings/personal-access-tokens/new" target="_blank">GitHub 토큰 만들기</a>를 여세요.</li>'+
      '<li>Repository access → Only select repositories → '+OWNER+'/'+REPO+'</li>'+
      '<li>Permissions → <b>Actions: Read and write</b> + <b>Contents: Read and write</b>(캡션 저장용)</li>'+
      '<li>Generate token → 코드를 복사해 아래에 붙여넣기</li></ol>'+
      '<div class="row2"><input id="pat" placeholder="github_pat_..." autocomplete="off"><button id="savepat">저장</button></div>'+
      '<div class="hint">토큰은 <b>이 기기 브라우저에만</b> 저장됩니다(서버 저장 없음).</div>'+
    '</details>'+
  '</div>'+
  '<div class="card"><span class="lbl">실행 현황 <a href="#" id="refresh" style="color:var(--cy);float:right;text-decoration:none">새로고침</a></span>'+
    '<div class="runs" id="runs"><div class="hint">불러오는 중…</div></div></div>';

  $("#savepat").onclick=()=>{const v=$("#pat").value.trim();if(!v)return;
    localStorage.setItem("gh_pat",v);$("#pat").value="";$("#tokbox").open=false;banner("토큰 저장 완료.","ok");};
  $("#go").onclick=async()=>{
    const query=$("#query").value.trim()||$("#species").value;
    if(!pat()){$("#tokbox").open=true;banner("최초 1회 GitHub 토큰이 필요합니다. 아래 설정을 따라 주세요.","err");return;}
    $("#go").disabled=true;banner("생성 요청 중…");
    try{const r=await fetch(API+"/actions/workflows/"+WF+"/dispatches",{method:"POST",headers:headers(true),
        body:JSON.stringify({ref:BRANCH,inputs:{query,visualizer:$("#visualizer").value}})});
      if(r.status===204){banner("생성 시작! 2~4분 뒤 텔레그램 전송 + 라이브러리 등록.","ok");setTimeout(loadRuns,4000);setTimeout(loadRuns,12000);}
      else{const t=await r.text();banner("실패("+r.status+"): 토큰 권한(Actions)을 확인하세요.<br><span class='mono' style='font-size:11px'>"+esc(t.slice(0,140))+"</span>","err");}
    }catch(e){banner("요청 실패: "+e,"err");}
    $("#go").disabled=false;};
  $("#refresh").onclick=(e)=>{e.preventDefault();loadRuns();};
  loadRuns();
}
async function loadRuns(){
  try{
    const [r,cat]=await Promise.all([fetch(API+"/actions/workflows/"+WF+"/runs?per_page=8",{headers:headers(true)}),fetchCatalog()]);
    const j=await r.json();const el=$("#runs");if(!el)return;el.innerHTML="";
    (j.workflow_runs||[]).filter(x=>x.status!=="completed").forEach(run=>{
      el.insertAdjacentHTML("beforeend",'<div class="run"><span class="st prog">'+(run.status==="queued"?"대기열":"진행 중")+'</span>'+
        '<a href="'+run.html_url+'" target="_blank">#'+num3(run.run_number)+' 쇼츠 생성</a><span class="t">'+ago(run.created_at)+"</span></div>");});
    [...cat].sort((a,b)=>(b.no||0)-(a.no||0)).slice(0,12).forEach(it=>{
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
  const cat=await fetchCatalog();
  const el=document.getElementById("clist");
  if(!cat.length){el.innerHTML='<div class="hint">아직 제작된 콘텐츠가 없습니다. <a href="/">제작하러 가기</a></div>';return;}
  el.innerHTML=[...cat].sort((a,b)=>(b.no||0)-(a.no||0)).map(it=>{
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
  const imgs=post.image_urls.map(u=>'<img src="'+u+'" loading="lazy">').join("");
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
  if(!rec){dc.innerHTML='<div class="hint err">콘텐츠 #'+esc(id)+' 레코드를 찾을 수 없습니다. (아직 미디어/레코드 업로드 전일 수 있어요)</div>';return;}
  const sp=rec.species||{},re=rec.reels||{},md=rec.media||{},src=rec.source||{};
  let mediaHtml="";
  if(md.video_url)mediaHtml='<video src="'+md.video_url+'" controls playsinline poster="'+(md.cover_url||"")+'"></video>';
  else if(md.cover_url)mediaHtml='<img src="'+md.cover_url+'">';
  else mediaHtml='<div class="hint">미디어가 아직 업로드되지 않았습니다(제작 직후 잠시 후 반영).</div>';
  const tags=(re.hashtags||[]).map(t=>'<span class="tag">'+esc(t)+'</span>').join("");
  dc.className="card detail";
  dc.innerHTML=
    '<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:10px"><b style="font-size:19px">#'+esc(id)+' '+esc(sp.common_name_ko||"")+'</b>'+
      '<span class="mono" style="color:var(--gy);font-size:12px">'+esc(sp.common_name_en||"")+'</span></div>'+
    mediaHtml+
    '<div class="meta" style="margin-top:12px"><b>학명</b> <i>'+esc(sp.scientific_name||"")+'</i> · <b>수심</b> '+esc(sp.depth_range_m||"?")+'m<br>'+
      '<b>서식</b> '+esc(sp.habitat||"?")+' · <b>분포</b> '+esc(sp.distribution||"?")+'</div>'+
    '<span class="lbl">훅</span><input id="ehook" value="'+esc(re.hook||"")+'">'+
    '<span class="lbl">캡션 (출처 표기 포함 · 그대로 저장됩니다)</span><textarea id="ecap">'+esc(re.caption||"")+'</textarea>'+
    '<span class="lbl">해시태그 (공백/줄바꿈 구분)</span><input id="etags" value="'+esc((re.hashtags||[]).join(" "))+'">'+
    '<div style="margin-top:6px">'+tags+'</div>'+
    '<div class="banner" id="msg"></div>'+
    '<div class="btnrow">'+
      '<button class="btn save" id="bsave">캡션·해시태그 저장 (재생성 없음)</button>'+
      '<button class="btn warn" id="bcap">캡션 재생성</button>'+
      '<button class="btn warn" id="bimg">이미지 재생성</button>'+
      '<button class="btn rd" id="bvid">영상 재생성 (Veo 쿼터)</button>'+
      '<button class="btn" id="ball">전체 재생성</button>'+
    '</div>'+
    postSection(rec.post)+
    '<div class="hint">이미지 출처: '+esc(src.image_credit||"—")+'<br>정보 출처: '+esc((src.info_sources||[]).join(" · ")||"—")+'</div>';

  $("#bsave").onclick=()=>saveCaption(id);
  $("#bcap").onclick=()=>regen(id,"caption");
  $("#bimg").onclick=()=>regen(id,"images");
  $("#bvid").onclick=()=>{if(confirm("영상 재생성은 Veo 쿼터/비용을 소모합니다(하루 10회 제한). 진행할까요?"))regen(id,"video");};
  $("#ball").onclick=()=>{if(confirm("전체 재생성하시겠어요? (영상 포함 시 Veo 쿼터 소모)"))regen(id,"all");};
}

async function saveCaption(id){
  if(!pat()){banner("캡션 저장에는 GitHub 토큰(Contents: Read and write)이 필요합니다.","err");return;}
  const path=CONTENT_DIR+"/"+id+".json";
  banner("저장 중…");
  try{
    const g=await fetch(API+"/contents/"+path+"?ref="+BRANCH,{headers:headers(true)});
    if(!g.ok){banner("레코드 조회 실패("+g.status+")","err");return;}
    const meta=await g.json();
    const rec=JSON.parse(decodeURIComponent(escape(atob(meta.content.replace(/\\n/g,"")))));
    rec.reels=rec.reels||{};
    rec.reels.hook=$("#ehook").value;
    rec.reels.caption=$("#ecap").value;
    rec.reels.hashtags=$("#etags").value.split(/[\\s]+/).filter(Boolean);
    rec.updated_at=new Date().toISOString();
    const put=await fetch(API+"/contents/"+path,{method:"PUT",headers:headers(true),
      body:JSON.stringify({message:"edit: 콘텐츠 #"+id+" 캡션 수정 [skip ci]",content:b64(JSON.stringify(rec,null,2)),sha:meta.sha,branch:BRANCH})});
    if(put.ok)banner("저장 완료. (변경이 저장소에 반영됐습니다)","ok");
    else{const t=await put.text();banner("저장 실패("+put.status+"): 토큰에 Contents 권한이 있는지 확인하세요.<br><span class='mono' style='font-size:11px'>"+esc(t.slice(0,140))+"</span>","err");}
  }catch(e){banner("저장 오류: "+e,"err");}
}

async function regen(id,scope){
  if(!pat()){banner("재생성에는 GitHub 토큰(Actions: Read and write)이 필요합니다.","err");return;}
  banner("재생성 요청 중… ("+scope+")");
  const viz=(scope==="video"||scope==="all")?"veo_text2video":"panzoom";
  try{
    const r=await fetch(API+"/actions/workflows/"+WF+"/dispatches",{method:"POST",headers:headers(true),
      body:JSON.stringify({ref:BRANCH,inputs:{content_id:id,scope:scope,visualizer:viz}})});
    if(r.status===204)banner("재생성 시작! 완료되면 이 페이지 미디어/캡션이 갱신됩니다(새로고침).","ok");
    else{const t=await r.text();banner("실패("+r.status+")<br><span class='mono' style='font-size:11px'>"+esc(t.slice(0,140))+"</span>","err");}
  }catch(e){banner("요청 실패: "+e,"err");}
}

route();
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
