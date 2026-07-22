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
.lfgrid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.lfchip{display:flex;align-items:flex-start;gap:7px;background:#0a1018;border:1px solid var(--line);
  border-radius:8px;padding:9px 10px;font-size:12px;cursor:pointer;user-select:none;position:relative}
.lfchip.on{border-color:var(--cy);background:#0d1e26}
.lfchip input{width:auto;padding:0;margin:2px 0 0;accent-color:var(--cy);flex-shrink:0}
.lfnm{display:block;line-height:1.35}
.lfnm i{font-style:normal;color:var(--gy);font-size:10.5px}
.lfcat{display:block;color:var(--gy);font-size:10px;letter-spacing:.5px;margin-top:2px}
.lfchip .rk{position:absolute;top:-7px;right:-7px;background:var(--cy);color:#00161c;font-weight:800;
  font-size:11px;width:18px;height:18px;border-radius:50%;display:flex;align-items:center;justify-content:center}
.lforder{font-size:12px;color:var(--cy);margin-top:8px;min-height:16px}
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
.ccard{display:flex;gap:10px;background:#0a1018;border:1px solid var(--line);border-radius:10px;padding:9px;margin-bottom:9px}
.cthumb{width:104px;height:74px;object-fit:cover;border-radius:7px;border:1px solid var(--line);flex:none;background:#050a0f}
.cthumb.noimg{display:flex;align-items:center;justify-content:center;font-size:10px;color:var(--gy);text-align:center}
.cbody{flex:1;min-width:0}
.ctitle{font-size:14px;font-weight:600;color:var(--wt)}
.cmeta{font-size:12px;color:var(--cy);margin-top:2px;word-break:break-all}
.cfact{font-size:12px;color:var(--gy);margin-top:3px;line-height:1.4}
.cfact.warn{color:var(--am)}
.cbadge{font-size:10px;color:var(--am);border:1px solid var(--am);border-radius:4px;padding:1px 5px}
.cgo{margin-top:7px;background:var(--cy);color:#04252b;border:0;border-radius:7px;padding:7px 12px;font-weight:700;font-size:13px;cursor:pointer}
.cgo:disabled{opacity:.5}
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
const LF_WF="generate-longform.yml";  // 롱폼(랭킹형 TOP N) 제작
const RGLF_WF="regen-longform-meta.yml"; // 롱폼 제목·설명·해시태그만 재생성(영상 유지·저비용)
const UP_WF="upload-longform.yml";    // 롱폼 유튜브 '수동' 업로드(운영자 확인 후 클릭)
const US_WF="upload-short.yml";       // 쇼츠 유튜브 '수동' 업로드(운영자 확인 후 클릭)
const SRC_WF="source-species.yml";    // 소싱(후보 발굴) — "소싱하기" 버튼
const DEL_WF="delete-content.yml";    // 제작물 삭제(레코드+매니페스트+미디어 릴리스)
const NV_WF="narrate-video.yml";      // 첨부 영상 나레이션(일본어 나레이션·자막)
const NV_TAG="attach-input";          // 첨부 영상 업로드용 릴리스 태그(에셋으로 보관)
// 실사 영상이 확보된 종 풀(코드 시드 추가 시 여기도 함께 갱신 — src/core/footage.py _SEED 참고).
// value는 data.SPECIES의 common_name_ko(정확 매칭 별칭)라 그대로 --species 인자로 쓸 수 있다.
// cat: 대시보드 표시용 카테고리 라벨(심해생물/일반해양/미세조류/침몰선). 현재 풀은 전부 심해생물.
const LF_POOL=[
  {v:"머리없는닭괴물",jp:"ユメナマコ",cat:"심해생물"},{v:"넓적문어",jp:"メンダコ",cat:"심해생물"},
  {v:"북태평양심해문어",jp:"シンカイダコ",cat:"심해생물"},{v:"대왕등각류",jp:"ダイオウグソクムシ",cat:"심해생물"},
  {v:"심해붉은해파리",jp:"シンカイクラゲ",cat:"심해생물"},{v:"파리지옥말미잘",jp:"ハエトリギンチャク",cat:"심해생물"},
  {v:"육식멍게",jp:"ニクショクホヤ",cat:"심해생물"},{v:"심해바다조름",jp:"シンカイウミエラ",cat:"심해생물"},
];
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
// s가 숫자(예: 종 수 n=6)여도 안전하게 문자열화 후 이스케이프. (숫자면 .replace가 없어 TypeError→
// 라이브러리 렌더가 통째로 죽으며 '불러오는 중…'에서 멈추던 실제 버그 수정.)
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}
function b64(str){return btoa(unescape(encodeURIComponent(str)));}
function ago(iso){if(!iso)return"";const s=(Date.now()-new Date(iso))/1000;
  if(s<90)return Math.round(s)+"초 전";if(s<5400)return Math.round(s/60)+"분 전";
  if(s<172800)return Math.round(s/3600)+"시간 전";return Math.round(s/86400)+"일 전";}
function banner(t,cls){let m=$("#msg");if(!m)return;m.className="banner show "+(cls||"");m.innerHTML=t;}
// Release 미디어 → 워커 프록시 URL(iOS 재생 가능한 inline·video/mp4로 중계)
function prox(u){return u?"/api/media?u="+encodeURIComponent(u):"";}
// 콘텐츠 버전 캐시버스터: 재생성 시 URL은 그대로(reels_<id>.mp4)라 옛 영상이 캐시로 나오던 문제를
// 막는다. 레코드의 rev(제작 실행 id)를 쿼리로 붙여 '새 버전 = 새 URL'로 만들어 미리보기·저장이
// 같은 최신본을 받게 한다. rev 없으면(구 레코드) 원래대로.
function bust(u,rev){return (u&&rev)?(u+(u.includes("?")?"&":"?")+"v="+encodeURIComponent(rev)):(u||"");}
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
// 유튜브 쇼츠 제목 폴백(구 레코드용): 훅 앞세우기+종명. 해시태그·범용 자극어 없음
// (쇼츠는 형식으로 자동 판정 — #Shorts는 글자 낭비·스팸 인상이라 정책상 금지).
// 신규 레코드는 시스템(LLM/폴백)이 만든 reels.yt_title/yt_title_ko를 우선 사용.
function ytTitle(hook,name,ko){
  hook=(hook||"").trim().replace(/[。．\\.！!?？]+$/,"");
  name=(name||"").trim();
  if(!name&&!hook)return "";
  if(!hook)return ko?"깊은 바다에 숨어 사는, "+name+"의 맨얼굴":"深海でひっそり生きる、"+name+"の素顔";
  return ko?hook+"——"+name+"의 정체":hook+"——"+name+"の正体";}
// ★쇼츠 제목 정책(운영자 확정): 제목 끝에 해시태그 2개를 붙인다. 신규 레코드는 시스템이 이미
// 태그가 붙은 yt_title을 저장하므로, 이 함수는 옛 레코드(제목 미저장) 폴백에만 쓰인다.
function titleTags(base,tags){base=(base||"").trim();
  const two=(tags||[]).map(t=>String(t).trim()).filter(Boolean).slice(0,2);
  return two.length?(base+" "+two.join(" ")).trim():base;}

// 타임아웃 fetch: 인앱 웹뷰(텔레그램·카카오 등)에서 api.github.com 같은 크로스오리진 요청이
// '영원히 pending' 되어 await가 안 풀리는 사고 방지(→ 라이브러리 '불러오는 중…' 멈춤의 실제 원인).
async function fetchT(url,opts,ms){
  const c=new AbortController();const t=setTimeout(()=>c.abort(),ms||7000);
  try{return await fetch(url,{...(opts||{}),signal:c.signal});}finally{clearTimeout(t);}
}
async function fetchRaw(path){
  // 공개 읽기 프록시 우선(무인증·어느 기기서든 동작). 실패 시 인증 API로 폴백(타임아웃).
  try{const r=await fetchT("/api/pub?path="+encodeURIComponent(path));
    if(r.ok)return await r.text();}catch(e){}
  try{const r=await fetchT(API+"/contents/"+path+"?ref="+BRANCH,{headers:{...headers(true),"Accept":"application/vnd.github.raw+json"}});
    if(!r.ok)return null;return await r.text();}catch(e){return null;}
}
async function fetchManifest(){const t=await fetchRaw(CONTENT_DIR+"/manifest.json");try{const a=JSON.parse(t);return Array.isArray(a)?a:[];}catch(e){return [];}}
async function fetchCatalog(){const t=await fetchRaw(CATALOG_PATH);try{const a=JSON.parse(t);return Array.isArray(a)?a:[];}catch(e){return [];}}
// 전 콘텐츠 목록: 공개 매니페스트(manifest.json) 우선 → 어느 기기서든 무인증 조회.
// 인증 가능한 기기에선 디렉토리 API로 매니페스트에 아직 없는 레거시 레코드를 보강(중복 제거).
async function listContent(){
  const man=await fetchManifest();
  const out=man.filter(x=>x&&x.kind!=="longform"&&x.kind!=="narrate").map(x=>({
    no:String(x.id), common_name_ko:x.common_name_ko||x.common_name_en||"종",
    common_name_en:x.common_name_en||"", scientific_name:x.scientific_name||"",
    date:x.date||"", hasVideo:!!x.has_video}));
  // 매니페스트에 모든 레코드가 들어있으므로, 인증 디렉토리 보강은 '인증 가능한 기기(서버모드/토큰)'에서만.
  // 무인증 폰(인앱 웹뷰)에선 api.github.com 요청이 멈추므로 아예 건너뛴다(매니페스트만으로 충분).
  if(!(SERVER||pat()))return out.sort((a,b)=>(a.no<b.no?1:-1));
  try{
    const r=await fetchT(API+"/contents/"+CONTENT_DIR+"?ref="+BRANCH,{headers:headers(true)});
    if(r.ok){
      const files=await r.json();
      const have=new Set(out.map(o=>o.no));
      const ids=(Array.isArray(files)?files:[]).map(f=>f.name||"").filter(n=>/^\\d{3}\\.json$/.test(n)).map(n=>n.slice(0,3)).filter(id=>!have.has(id));
      const recs=await Promise.all(ids.map(async id=>{
        const rec=await fetchRecord(id); if(!rec)return null; const sp=rec.species||{};
        return {no:id, common_name_ko:sp.common_name_ko||sp.common_name_en||"종",
                common_name_en:sp.common_name_en||"", scientific_name:sp.scientific_name||"",
                date:String(rec.updated_at||rec.created_at||"").slice(0,10),
                hasVideo:!!(rec.media&&rec.media.video_url)};
      }));
      out.push(...recs.filter(Boolean));
    }
  }catch(e){}
  return out.sort((a,b)=>(a.no<b.no?1:-1));
}
async function fetchRecord(id){const t=await fetchRaw(CONTENT_DIR+"/"+id+".json");try{return JSON.parse(t);}catch(e){return null;}}
// 롱폼 결과 목록: 공개 매니페스트에서 kind=longform 만.
async function listLongform(){
  const man=await fetchManifest();
  return man.filter(x=>x&&x.kind==="longform").sort((a,b)=>(String(a.id)<String(b.id)?1:-1));
}

// ── 라우팅: 전체 페이지 로드마다 경로로 뷰 결정 (worker가 모든 경로에 앱 셸 서빙) ──
function setNav(p){document.querySelectorAll("#nav a").forEach(a=>a.classList.toggle("on",a.dataset.p===p));}
function route(){
  const path=location.pathname;
  const m=path.match(/^\\/c\\/(\\w+)/);
  const lm=path.match(/^\\/lf\\/(\\S+)/);
  const nv=path.match(/^\\/nv\\/(\\S+)/);
  if(m){setNav("library");renderDetail(m[1]);}
  else if(nv){setNav("home");renderNarrateDetail(decodeURIComponent(nv[1]));}
  else if(lm){setNav("home");renderLongformDetail(decodeURIComponent(lm[1]));}
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
  '<div class="card">'+
    '<span class="lbl">소싱하기 · 새 대상 발굴 (수동)</span>'+
    '<select id="srccat">'+
      '<option value="deep_sea">심해 생물 (Deep Sea)</option>'+
      '<option value="marine_life">일반 해양생물 (Marine Life)</option>'+
      '<option value="marine_algae">해양 미세조류 (Marine Microalgae)</option>'+
      '<option value="shipwreck">침몰선 (Shipwreck)</option>'+
    '</select>'+
    '<div class="hint" style="margin:4px 0 8px">위키미디어 커먼스(NOAA·MBARI·Ifremer 등, CC 계열)에서 새 대상 영상을 찾아 <b>후보</b>로 담습니다. 아래 목록은 <b>영상+이미지 확보</b>와 <b>이미지전용(영상없음)</b> 두 탭으로 구분됩니다 — 영상 확보분만 자동 제작 풀에 들어갑니다. (침몰선은 이름·정보 확인이 필요할 수 있음)</div>'+
    '<button class="go" id="gosrc">소싱하기 (후보 발굴)</button>'+
    '<div class="banner" id="srcmsg"></div>'+
    '<div class="srccands" id="srccands" style="margin-top:12px"><div class="hint">후보를 불러오는 중…</div></div>'+
  '</div>'+
  '<div class="card">'+
    '<span class="lbl">다운로드 가능 영상 찾기 · 썸네일·주제 미리보기</span>'+
    '<div class="hint" style="margin:4px 0 8px">키워드로 <b>키(API) 없이 직접 다운로드 가능한 무료 영상</b>을 찾아 썸네일·주제와 함께 보여줍니다. 소스: Wikimedia Commons(자유 라이선스) + Internet Archive(안전 필터). 나레이션에 쓰려면 <b>2차 저작</b>이 가능해야 하므로 <b>변경금지(ND)·비상업(NC)은 제외</b>하고 재사용 가능(PD·CC0·CC BY·CC BY-SA)만 <span style="color:#7CFC9B">안전</span>으로 표시합니다. 최종 사용 전 원본 페이지에서 권리를 확인하세요.</div>'+
    '<div class="row2" style="margin-bottom:6px"><input id="vsq" placeholder="검색어 (예: deep sea anglerfish, jellyfish, shipwreck)" style="flex:2">'+
      '<select id="vssrc" style="flex:1"><option value="all">전체</option><option value="commons">커먼스만</option><option value="archive">아카이브만</option></select></div>'+
    '<button class="go" id="govs">영상 찾기</button>'+
    '<div class="banner" id="vsmsg"></div>'+
    '<div id="vsresults" style="margin-top:12px"></div>'+
  '</div>'+
  '<div class="card">'+
    '<span class="lbl">첨부 영상 나레이션 · 일본어 자막·나레이션 입히기</span>'+
    '<div class="hint" style="margin:4px 0 8px">직접 받은 영상(퍼블릭도메인/CC 등 <b>재가공 허용</b> 소스만)을 올리면 <b>영상 내용을 분석해 대본을 자동 생성</b>하고 <b>일본어 나레이션+자막</b>을 입힙니다. <b>제목·설명·해시태그</b>는 대본을 근거로 <b>일본어+한국어</b>로 자동 생성되어(직접 입력 불필요), 완료 후 텔레그램과 결과 페이지(/nv)에서 확인·복사할 수 있습니다. 출처·크레딧 표기는 운영자 책임입니다.</div>'+
    '<div class="row2" style="margin-bottom:6px"><label style="flex:1"><input type="radio" name="nvmode" value="shorts" checked> 숏츠 (9:16)</label>'+
      '<label style="flex:1"><input type="radio" name="nvmode" value="longform"> 롱폼 (16:9)</label></div>'+
    '<input id="nvfile" type="file" accept="video/*" style="margin-bottom:6px">'+
    '<input id="nvurl" placeholder="또는 영상 URL 붙여넣기 (예: NOAA 다운로드 링크)" style="margin-bottom:8px">'+
    '<button class="go" id="gonv">나레이션 제작</button>'+
    '<div class="banner" id="nvmsg"></div>'+
    '<div id="nvresults" style="margin-top:12px"></div>'+
  '</div>'+
  '<div class="card">'+
    '<span class="lbl">롱폼 · 랭킹형 TOP N (8분 유튜브)</span>'+
    '<div class="hint" style="margin:2px 0 8px">종은 <b>주제별로 랜덤 자동 추출</b>됩니다(수동 선택 폐지). 테마만 고르세요.</div>'+
    '<span class="lbl">테마 (비워두면 자동 추출된 종을 보고 AI가 자동으로 정함)</span>'+
    '<select id="lftheme">'+
      '<option value="자동" selected>자동 (AI가 종 조합을 보고 정함)</option>'+
      '<option value="기이한">기이한</option>'+
      '<option value="위험한">위험한</option>'+
      '<option value="놀라운">놀라운</option>'+
      '<option value="미스터리한">미스터리한</option>'+
      '<option value="무서운">무서운</option>'+
    '</select>'+
    '<div class="hint" style="margin:4px 0 8px">각 종의 실사 영상(NOAA·공용도메인)으로 세그먼트 조립 → 유튜브 <b>비공개</b> 자동 업로드 후 텔레그램으로 링크 전송(확인 후 직접 공개).</div>'+
    '<button class="go" id="golf">롱폼 생성 시작</button>'+
    '<div class="banner" id="lfmsg"></div>'+
    '<div class="lfresults" id="lfresults" style="margin-top:14px"></div>'+
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
  // 체크 순서 = 순위(1위부터). 클릭한 순서를 배열로 추적(DOM 순서가 아님).
  let lfOrder=[];
  function lfRenderOrder(){
    const grid=$("#lfgrid");
    if(grid)grid.querySelectorAll(".lfchip").forEach(ch=>{
      const v=ch.querySelector("input").value;
      const rk=lfOrder.indexOf(v);
      ch.classList.toggle("on",rk>=0);
      const old=ch.querySelector(".rk");if(old)old.remove();
      if(rk>=0){const b=document.createElement("span");b.className="rk";b.textContent=String(rk+1);ch.appendChild(b);}
    });
    const ord=$("#lforder");
    if(ord)ord.textContent=lfOrder.length?("선택 순서: "+lfOrder.map((v,i)=>(i+1)+")"+v).join("  ")):"선택된 종: 없음";
  }
  const lfGrid=$("#lfgrid");
  if(lfGrid)lfGrid.querySelectorAll(".lfchip").forEach(ch=>{
    ch.onclick=(e)=>{
      e.preventDefault();
      const cb=ch.querySelector("input");const v=cb.value;
      const i=lfOrder.indexOf(v);
      if(i>=0)lfOrder.splice(i,1);
      else if(lfOrder.length<6)lfOrder.push(v);
      else{lfbanner("최대 6개까지 선택할 수 있어요.","err");return;}
      cb.checked=lfOrder.includes(v);
      lfRenderOrder();
    };
  });
  const _lf=$("#golf");if(_lf)_lf.onclick=async()=>{
    const theme=($("#lftheme")||{}).value||"자동";
    // ★종 수동 선택 폐지 — 백엔드가 주제별로 랜덤 자동 추출(species 비움).
    const species="";
    if(!authReady()){const tb=$("#tokbox");if(tb)tb.open=true;lfbanner("먼저 GitHub 토큰을 설정하세요(위 안내).","err");return;}
    $("#golf").disabled=true;lfbanner("롱폼 생성 요청 중… (종 자동 추출)");
    try{const r=await fetch(API+"/actions/workflows/"+LF_WF+"/dispatches",{method:"POST",headers:headers(true),
        body:JSON.stringify({ref:BRANCH,inputs:{theme,species,privacy:"private"}})});
      if(r.status===204){lfbanner("롱폼 생성 시작! 완료 후 유튜브 비공개 업로드 + 텔레그램 링크 전송.","ok");setTimeout(loadRuns,4000);setTimeout(loadRuns,15000);}
      else{const t=await r.text();lfbanner("실패("+r.status+"): 토큰 권한(Actions)을 확인하세요.<br><span class='mono' style='font-size:11px'>"+esc(t.slice(0,140))+"</span>","err");}
    }catch(e){lfbanner("요청 실패: "+e,"err");}
    $("#golf").disabled=false;};
  // ── 소싱하기(후보 발굴) + 후보 검토·제작 ──
  const _gs=$("#gosrc");if(_gs)_gs.onclick=async()=>{
    const category=($("#srccat")||{}).value||"deep_sea";
    if(!authReady()){const tb=$("#tokbox");if(tb)tb.open=true;srcbanner("먼저 GitHub 토큰을 설정하세요(위 안내).","err");return;}
    $("#gosrc").disabled=true;srcbanner("소싱 요청 중… (1~3분 뒤 아래에 후보가 뜹니다)");
    try{const r=await fetch(API+"/actions/workflows/"+SRC_WF+"/dispatches",{method:"POST",headers:headers(true),
        body:JSON.stringify({ref:BRANCH,inputs:{category,want:"14"}})});
      if(r.status===204){srcbanner("소싱 시작! 1~3분 뒤 '새로고침'을 누르면 후보가 나타납니다.","ok");
        setTimeout(()=>loadCandidates(category),60000);setTimeout(()=>loadCandidates(category),120000);}
      else{const t=await r.text();srcbanner("실패("+r.status+"): 토큰 권한(Actions)을 확인하세요.<br><span class='mono' style='font-size:11px'>"+esc(t.slice(0,140))+"</span>","err");}
    }catch(e){srcbanner("요청 실패: "+e,"err");}
    $("#gosrc").disabled=false;};
  const _sc=$("#srccat");if(_sc)_sc.onchange=()=>loadCandidates(_sc.value);
  loadCandidates(($("#srccat")||{}).value||"deep_sea");

  // ── 다운로드 가능 영상 찾기 ──
  const _gvs=$("#govs");if(_gvs)_gvs.onclick=()=>findVideos();
  const _vsq=$("#vsq");if(_vsq)_vsq.onkeydown=(e)=>{if(e.key==="Enter")findVideos();};

  // ── 첨부 영상 나레이션(일본어 나레이션·자막) ──
  const _gnv=$("#gonv");if(_gnv)_gnv.onclick=()=>narrateAttached();

  $("#refresh").onclick=(e)=>{e.preventDefault();loadRuns();};
  loadRuns();
  loadLongformResults();
  loadNarrateResults();
}
function srcbanner(t,c){const m=$("#srcmsg");if(m){m.className="banner show "+(c||"");m.innerHTML=t;}}
function nvbanner(t,c){const m=$("#nvmsg");if(m){m.className="banner show "+(c||"");m.innerHTML=t;}}
// 첨부 영상을 GitHub Release(태그 NV_TAG) 에셋으로 올리고 공개 다운로드 URL을 돌려준다.
// 워크플로가 이 URL을 urllib로 받아 나레이션을 입힌다(공개 저장소라 무인증 접근 가능).
async function uploadToRelease(file){
  // 1) 입력 보관용 릴리스 확보(없으면 생성)
  let rel=null;
  try{
    const g=await fetch(API+"/releases/tags/"+NV_TAG,{headers:headers(true)});
    if(g.ok)rel=await g.json();
    else if(g.status===404){
      const c=await fetch(API+"/releases",{method:"POST",headers:{...headers(true),"Content-Type":"application/json"},
        body:JSON.stringify({tag_name:NV_TAG,name:"첨부 영상 입력",target_commitish:BRANCH,
          body:"첨부 영상 나레이션용 입력 파일 보관(자동 생성)"})});
      if(c.ok)rel=await c.json();
    }
  }catch(e){}
  if(!rel||!rel.id)return "";
  // 2) 에셋 업로드(파일명은 타임스탬프로 유니크 → 같은 이름 충돌 방지)
  const ext=((file.name||"").split(".").pop()||"mp4").toLowerCase().replace(/[^a-z0-9]/g,"")||"mp4";
  const name="attach_"+Date.now()+"."+ext;
  const ctype=file.type||"application/octet-stream";
  let up;
  try{
    if(SERVER){
      // 서버 토큰 모드: 워커가 uploads.github.com으로 중계(브라우저에 토큰 없음)
      up=await fetch("/api/ghupload?release_id="+rel.id+"&name="+encodeURIComponent(name)+"&ctype="+encodeURIComponent(ctype),
        {method:"POST",body:file});
    }else{
      up=await fetch("https://uploads.github.com/repos/"+OWNER+"/"+REPO+"/releases/"+rel.id+"/assets?name="+encodeURIComponent(name),
        {method:"POST",headers:{"Authorization":"Bearer "+pat(),"Content-Type":ctype,"X-GitHub-Api-Version":"2022-11-28"},body:file});
    }
  }catch(e){return "";}
  if(!up||!up.ok)return "";
  try{const a=await up.json();if(a&&a.browser_download_url)return a.browser_download_url;}catch(e){}
  return "https://github.com/"+OWNER+"/"+REPO+"/releases/download/"+NV_TAG+"/"+name;
}
let _nvTopic="";   // 소싱 출처(커먼스/아카이브) 설명 — '찾기'에서 넘어오면 대본 근거로만 사용(운영자 입력 아님)
// 첨부 영상 나레이션: (파일 업로드 또는 URL) → 워크플로 디스패치.
// ★제목·설명은 입력받지 않는다 — 영상 내용을 보고 대본을 만들고, 대본에서 제목·설명·해시태그(일/한)를 자동 생성.
async function narrateAttached(){
  if(!authReady()){const tb=$("#tokbox");if(tb)tb.open=true;nvbanner("먼저 GitHub 토큰을 설정하세요(위 안내).","err");return;}
  const mode=(document.querySelector('input[name=nvmode]:checked')||{}).value||"shorts";
  const urlInput=(($("#nvurl")||{}).value||"").trim();
  const fileEl=$("#nvfile");const file=fileEl&&fileEl.files&&fileEl.files[0];
  if(!urlInput&&!file){nvbanner("영상 파일을 올리거나 URL을 붙여넣으세요.","err");return;}
  const btn=$("#gonv");btn.disabled=true;
  try{
    let videoUrl=urlInput;
    if(!videoUrl&&file){
      nvbanner("영상 업로드 중… (파일 크기에 따라 시간이 걸립니다)");
      videoUrl=await uploadToRelease(file);
      if(!videoUrl){nvbanner("영상 업로드 실패. 파일 크기·토큰 권한(Contents RW)을 확인하세요.","err");btn.disabled=false;return;}
    }
    nvbanner("나레이션 제작 요청 중… (영상 내용 분석 → 대본 → 제목·설명·해시태그 자동 생성)");
    const src=(urlInput&&!file)?"":_nvTopic;   // '찾기'에서 온 경우에만 출처 설명을 근거로 전달
    const r=await fetch(API+"/actions/workflows/"+NV_WF+"/dispatches",{method:"POST",headers:headers(true),
        body:JSON.stringify({ref:BRANCH,inputs:{video_url:videoUrl,mode,source_topic:(src||"").slice(0,600)}})});
    if(r.status===204){nvbanner("제작 시작! 완료되면 <b>텔레그램</b>과 아래 <b>최근 나레이션 결과</b>에서 제목·설명·해시태그(일/한)를 확인·복사할 수 있습니다(5~15분).","ok");
      setTimeout(loadNarrateResults,90000);setTimeout(loadNarrateResults,180000);}
    else{const t=await r.text();nvbanner("실패("+r.status+"): 토큰 권한(Actions)을 확인하세요.<br><span class='mono' style='font-size:11px'>"+esc(t.slice(0,140))+"</span>","err");}
  }catch(e){nvbanner("요청 실패: "+e,"err");}
  btn.disabled=false;
}
// 완료된 나레이션 결과(레코드) 목록 — 홈 나레이션 카드 하단
async function listNarrate(){
  const man=await fetchManifest();
  return (man||[]).filter(x=>x&&x.kind==="narrate").sort((a,b)=>(String(a.id)<String(b.id)?1:-1));
}
async function loadNarrateResults(){
  const el=$("#nvresults");if(!el)return;
  let recs=[];try{recs=await listNarrate();}catch(e){}
  if(!recs.length){el.innerHTML="";return;}
  el.innerHTML='<span class="lbl">최근 나레이션 결과</span>'+recs.slice(0,6).map(r=>(
    '<a class="clitem" href="/nv/'+encodeURIComponent(r.id)+'"><span class="no">'+esc(r.mode==="longform"?"롱폼":"숏츠")+'</span>'+
    '<span class="nm">'+esc(r.yt_title||r.id)+'<small>'+esc(r.yt_title_ko||"")+'</small></span>'+
    '<span class="t">'+esc(String(r.date||r.created_at||"").slice(0,10))+'</span></a>'
  )).join('');
}
// 나레이션 결과 상세: 영상 + 자동 생성 제목·설명·해시태그(일/한) 복사
async function renderNarrateDetail(id){
  view().innerHTML='<a class="back" href="/">← 제작 페이지</a><div class="card" id="nvcard"><div class="hint">불러오는 중…</div></div>';
  const rec=await fetchRecord(id);
  const dc=document.getElementById("nvcard");
  if(!rec){dc.innerHTML='<div class="hint">이 나레이션 기록을 찾을 수 없습니다(아직 제작 중이거나 완료 전).</div>'+
      '<div class="btnrow" style="margin-top:14px"><a class="btn" href="/">← 제작 페이지로</a></div>';return;}
  const md=rec.media||{};
  const mediaHtml=md.video_url?('<video src="'+prox(md.video_url)+'" controls playsinline preload="metadata"></video>'):"";
  const tagsJp=(rec.hashtags||[]).join(" "), tagsKo=(rec.hashtags_ko||[]).join(" ");
  const thumbHtml=md.thumb_url?(
    '<div style="margin-top:12px"><span class="lbl">유튜브 커스텀 썸네일 (오프닝 훅 자동 생성)</span>'+
    '<img src="'+prox(md.thumb_url)+'" style="width:100%;max-width:480px;border-radius:8px;display:block;margin-top:6px">'+
    '<div class="btnrow" style="margin-top:6px"><button class="btn save" id="thdl">썸네일 저장</button></div><div class="hint" id="thhint"></div></div>'
  ):"";
  dc.className="card detail";
  dc.innerHTML=
    '<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:10px"><b style="font-size:19px">'+esc(id)+'</b>'+
      '<span class="mono" style="color:var(--gy);font-size:12px">'+esc(rec.mode==="longform"?"롱폼(16:9)":"숏츠(9:16)")+' · 첨부 영상 나레이션</span></div>'+
    (rec.hook?('<div class="hint" style="margin-bottom:8px">오프닝 훅: <b style="color:#f0c552">'+esc(rec.hook)+'</b></div>'):"")+
    mediaHtml+
    (md.video_url?'<div class="btnrow" style="margin-top:8px"><button class="btn save" id="bdl">비디오 저장하기</button></div><div class="hint" id="dlhint" style="margin-top:6px"></div>':"")+
    thumbHtml+
    '<div class="hint" style="margin:10px 0 2px">아래 제목·설명·해시태그는 <b>영상 대본을 근거로 자동 생성</b>된 값입니다(유튜브 업로드용 복사).</div>'+
    '<div class="dual" style="margin-top:8px">'+
      '<div><span class="lbl">제목 · 일본어</span><textarea id="nvtj" readonly rows="2">'+esc(rec.yt_title||"")+'</textarea>'+
        '<button class="btn save" id="nvcptj" style="margin-top:6px">일본어 제목 복사</button></div>'+
      '<div><span class="lbl">제목 · 한국어(참고)</span><textarea id="nvtk" readonly rows="2">'+esc(rec.yt_title_ko||"")+'</textarea>'+
        '<button class="btn" id="nvcptk" style="margin-top:6px">한국어 제목 복사</button></div>'+
    '</div>'+
    '<div class="dual" style="margin-top:8px">'+
      '<div><span class="lbl">설명 · 일본어</span><textarea id="nvdj" readonly rows="6">'+esc(rec.yt_description||"")+'</textarea>'+
        '<button class="btn save" id="nvcpdj" style="margin-top:6px">일본어 설명 복사</button></div>'+
      '<div><span class="lbl">설명 · 한국어(참고)</span><textarea id="nvdk" readonly rows="6">'+esc(rec.yt_description_ko||"")+'</textarea>'+
        '<button class="btn" id="nvcpdk" style="margin-top:6px">한국어 설명 복사</button></div>'+
    '</div>'+
    '<div class="dual" style="margin-top:8px">'+
      '<div><span class="lbl">해시태그 · 일본어</span><textarea id="nvhj" readonly rows="3">'+esc(tagsJp)+'</textarea>'+
        '<button class="btn save" id="nvcphj" style="margin-top:6px">일본어 해시태그 복사</button></div>'+
      '<div><span class="lbl">해시태그 · 한국어(참고)</span><textarea id="nvhk" readonly rows="3">'+esc(tagsKo)+'</textarea>'+
        '<button class="btn" id="nvcphk" style="margin-top:6px">한국어 해시태그 복사</button></div>'+
    '</div>'+
    '<div class="banner" id="msg" style="margin-top:10px"></div>';
  const V=s=>((document.getElementById(s)||{}).value||"");
  const B=(id2,src,msg)=>{const b=document.getElementById(id2);if(b)b.onclick=()=>copyText(V(src),msg);};
  B("nvcptj","nvtj","일본어 제목을 복사했어요.");B("nvcptk","nvtk","한국어 제목을 복사했어요.");
  B("nvcpdj","nvdj","일본어 설명을 복사했어요.");B("nvcpdk","nvdk","한국어 설명을 복사했어요.");
  B("nvcphj","nvhj","일본어 해시태그를 복사했어요.");B("nvcphk","nvhk","한국어 해시태그를 복사했어요.");
  if(md.video_url){const bd=document.getElementById("bdl");if(bd)bd.onclick=()=>saveVideo(prox(md.video_url),id+".mp4");}
  if(md.thumb_url){const th=document.getElementById("thdl");if(th)th.onclick=()=>saveVideo(prox(md.thumb_url),id+"_thumb.jpg",{btn:"#thdl",hint:"#thhint",mime:"image/jpeg",kind:"이미지"});}
}
function vsbanner(t,c){const m=$("#vsmsg");if(m){m.className="banner show "+(c||"");m.innerHTML=t;}}
function vsDur(s){s=Math.round(s||0);if(!s)return"";const m=Math.floor(s/60),ss=s%60;return m+":"+String(ss).padStart(2,"0");}
let _vsList=[];
// 다운로드 가능 영상 검색 → 썸네일·주제 카드 렌더
async function findVideos(){
  const q=(($("#vsq")||{}).value||"").trim();
  const src=(($("#vssrc")||{}).value||"all");
  if(!q){vsbanner("검색어를 입력하세요.","err");return;}
  const btn=$("#govs");if(btn)btn.disabled=true;
  vsbanner("검색 중… (5~15초)");
  try{
    const r=await fetch("/api/vsearch?q="+encodeURIComponent(q)+"&src="+encodeURIComponent(src));
    const d=await r.json();
    if(!r.ok){vsbanner("검색 실패("+r.status+")","err");if(btn)btn.disabled=false;return;}
    _vsList=(d.results||[]);
    if(!_vsList.length){vsbanner("결과가 없습니다. 다른 검색어(영문 권장)를 시도해 보세요.","");}
    else{vsbanner("총 "+_vsList.length+"개 — <span style='color:#7CFC9B'>안전</span>=재사용 가능. '나레이션에 사용'을 누르면 아래 나레이션 카드에 자동 입력됩니다.","ok");}
    renderVsResults();
  }catch(e){vsbanner("요청 실패: "+e,"err");}
  if(btn)btn.disabled=false;
}
function renderVsResults(){
  const el=$("#vsresults");if(!el)return;
  if(!_vsList.length){el.innerHTML="";return;}
  let h='<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px">';
  _vsList.forEach((v,i)=>{
    const badge=v.safe
      ?'<span style="background:#12351f;color:#7CFC9B;border:1px solid #2e7d4f;border-radius:4px;padding:1px 5px;font-size:10px">안전 · '+esc(v.license)+'</span>'
      :'<span style="background:#3a2f12;color:#f0c552;border:1px solid #7d652e;border-radius:4px;padding:1px 5px;font-size:10px">확인 필요 · '+esc(v.license)+'</span>';
    const dur=v.duration?('<span style="position:absolute;right:4px;bottom:4px;background:rgba(0,0,0,.75);color:#fff;font-size:10px;padding:1px 4px;border-radius:3px">'+vsDur(v.duration)+'</span>'):'';
    h+='<div style="border:1px solid #24303a;border-radius:8px;overflow:hidden;background:#0e161d">'+
      '<div style="position:relative;aspect-ratio:16/9;background:#050a0e">'+
        (v.thumb?('<img loading="lazy" src="'+esc(v.thumb)+'" style="width:100%;height:100%;object-fit:cover" onerror="this.style.display=\\'none\\'">'):'')+dur+'</div>'+
      '<div style="padding:7px 8px">'+
        '<div style="font-size:12px;line-height:1.3;max-height:32px;overflow:hidden">'+esc(v.title)+'</div>'+
        '<div class="hint" style="font-size:10px;margin:3px 0;max-height:26px;overflow:hidden">'+esc(v.topic||"")+'</div>'+
        '<div style="margin:4px 0">'+badge+' <span class="hint" style="font-size:10px">'+esc(v.source)+'</span></div>'+
        '<div class="row2" style="gap:5px">'+
          '<button class="mini" onclick="vsUse('+i+')" style="flex:1">나레이션에 사용</button>'+
          '<a class="mini" href="'+esc(v.download)+'" target="_blank" rel="noopener" style="flex:1;text-align:center;text-decoration:none">다운로드</a>'+
        '</div>'+
        '<div style="margin-top:4px"><a class="hint" href="'+esc(v.page)+'" target="_blank" rel="noopener" style="font-size:10px">원본 페이지 · 권리 확인</a></div>'+
      '</div></div>';
  });
  h+='</div>';
  el.innerHTML=h;
}
// 찾은 영상을 첨부 나레이션 카드에 채우기(URL·제목) + 스크롤
function vsUse(i){
  const v=_vsList[i];if(!v)return;
  const u=$("#nvurl");if(u)u.value=v.download;
  _nvTopic=(v.topic||v.title||"");   // 대본 근거로만 사용(운영자 입력 아님 · 제목·설명은 자동 생성)
  nvbanner("영상 URL을 나레이션 카드에 넣었습니다. 형태(숏츠/롱폼)만 고르고 '나레이션 제작'을 누르세요 — 제목·설명·해시태그는 자동 생성됩니다.","ok");
  const card=$("#gonv");if(card&&card.scrollIntoView)card.scrollIntoView({behavior:"smooth",block:"center"});
}
let _srcMode="video";   // "video"=영상+이미지 확보(제작 풀) · "image"=이미지전용(영상 없음·별도 보관)
async function loadCandidates(cat,mode){
  if(mode)_srcMode=mode;mode=_srcMode;
  const el=$("#srccands");if(!el)return;
  const isImg=mode==="image";
  // 두 목록의 개수를 함께 읽어 탭에 표시(영상 확보 vs 이미지전용을 한눈에 구분).
  const base="short-movie-generator/src/categories/"+cat+"/"+cat+"_";
  el.innerHTML='<div class="hint">목록 확인 중…</div>';
  async function get(sfx){try{const t=await fetchRaw(base+sfx+".json");const a=JSON.parse(t);return Array.isArray(a)?a:[];}catch(e){return [];}}
  const [vids,imgs]=await Promise.all([get("candidates"),get("image_only")]);
  const arr=isImg?imgs:vids;
  const tabBtn=(m,label,n,on)=>'<button class="stab" data-mode="'+m+'" style="flex:1;padding:8px 6px;border:1px solid '+(on?'var(--cy)':'#2a3550')+';background:'+(on?'rgba(90,200,245,.14)':'transparent')+';color:'+(on?'var(--cy)':'var(--gy)')+';border-radius:8px;font-weight:'+(on?'700':'500')+';cursor:pointer">'+label+' <b>'+n+'</b></button>';
  const tabs='<div style="display:flex;gap:8px;margin:2px 0 10px">'+
      tabBtn("video","영상+이미지 확보",vids.length,!isImg)+
      tabBtn("image","이미지전용(영상없음)",imgs.length,isImg)+'</div>';
  const desc=isImg
    ?'<div class="hint" style="margin:-4px 0 8px">영상이 <b>전혀 없어</b> 사진(4장↑) 다큐로만 만들 수 있는 소스입니다. 자동 제작 풀에서 <b>제외·별도 보관</b> 중이며, 참고·수동 제작용으로만 봅니다.</div>'
    :'<div class="hint" style="margin:-4px 0 8px">실사 <b>영상</b>이 확보돼 자동 제작 풀에 있는 소스입니다.</div>';
  const head='<span class="lbl">소싱 인벤토리 ('+cat+') <a href="#" id="srcref" style="color:var(--cy);float:right;text-decoration:none">새로고침</a></span>';
  const bindTabs=()=>{el.querySelectorAll(".stab").forEach(b=>{b.onclick=()=>loadCandidates(cat,b.getAttribute("data-mode"));});
    const rf=$("#srcref");if(rf)rf.onclick=(e)=>{e.preventDefault();loadCandidates(cat);};};
  if(!arr.length){el.innerHTML=head+tabs+desc+'<div class="hint">'+(isImg?'이미지전용 소스가 없습니다.':'아직 영상 확보 후보가 없습니다. 위 <b>소싱하기</b>를 눌러 발굴하세요.')+'</div>';bindTabs();return;}
  el.innerHTML=head+tabs+desc+arr.map(c=>{
    const isW=c.kind==="wreck";
    const title=isW?esc(c.name||c.key):(esc(c.name||"")+(c.common_name_ko?' <i style="color:var(--gy)">'+esc(c.common_name_ko)+'</i>':''));
    const thumb=c.thumbnail_url?'<img class="cthumb" src="'+prox(c.thumbnail_url)+'" alt="">':'<div class="cthumb noimg">썸네일 생성 중…</div>';
    const meta=[c.depth?('수심 '+esc(c.depth)+'m'):'',isW&&c.ship_type?('선종 '+esc(c.ship_type)):'',esc(c.license||'')].filter(Boolean).join(' · ');
    const fact=(c.facts&&c.facts[0])?('<div class="cfact">'+esc(String(c.facts[0]).slice(0,90))+'</div>'):(isW?'<div class="cfact warn">※ 배 이름·정보를 영상 확인 후 제작하세요.</div>':'');
    // 소싱 종류 배지(영상 확보 vs 이미지전용) — 두 그룹을 카드에서도 구분.
    const badge=isImg
      ?'<span style="display:inline-block;background:rgba(240,180,60,.18);color:#f0b43c;border:1px solid #6a5320;border-radius:6px;padding:1px 7px;font-size:11px">이미지전용·영상없음</span>'
      :'<span style="display:inline-block;background:rgba(90,200,120,.16);color:#5ac878;border:1px solid #2c5a3a;border-radius:6px;padding:1px 7px;font-size:11px">영상 확보</span>';
    const src=isImg
      ?(c.photo_count?('<div class="cmeta" style="font-size:11px">사진 '+esc(String(c.photo_count))+'장 확보'+(c.video_note?(' · '+esc(c.video_note)):'')+'</div>'):'')
      :(c.video_source?('<div class="cmeta" style="font-size:11px;color:var(--gy)">영상: '+esc(String(c.video_source).slice(0,60))+'</div>'):'');
    const rev=c.video_review?('<div class="cfact warn">※ '+esc(c.video_review)+'</div>'):'';
    const warn=(isW&&c.needs_confirm)?'<span class="cbadge">확인 필요</span>':'';
    const btn=isImg
      ?'<button class="cgo" data-key="'+esc(c.key)+'" data-cat="'+esc(cat)+'" style="background:#3a3320;border-color:#6a5320;color:#f0b43c">이미지로 수동 제작</button>'
      :'<button class="cgo" data-key="'+esc(c.key)+'" data-cat="'+esc(cat)+'">이 대상으로 제작</button>';
    return '<div class="ccard">'+thumb+'<div class="cbody"><div class="ctitle">'+title+' '+badge+' '+warn+'</div>'+
      '<div class="cmeta">'+meta+'</div>'+src+fact+rev+
      '<div class="cmeta" style="color:var(--gy);font-size:11px">'+esc(c.credit||'')+'</div>'+btn+'</div></div>';
  }).join('');
  bindTabs();
  el.querySelectorAll(".cgo").forEach(b=>{b.onclick=()=>produceCandidate(b.getAttribute("data-cat"),b.getAttribute("data-key"),b);});
}
async function produceCandidate(cat,key,btn){
  if(!authReady()){srcbanner("먼저 GitHub 토큰을 설정하세요.","err");return;}
  if(!confirm("이 대상으로 쇼츠를 제작할까요?\\n\\n"+key))return;
  if(btn)btn.disabled=true;srcbanner("제작 요청 중… ("+esc(key)+")");
  try{const r=await fetch(API+"/actions/workflows/"+WF+"/dispatches",{method:"POST",headers:headers(true),
      body:JSON.stringify({ref:BRANCH,inputs:{query:key,category:cat}})});
    if(r.status===204){srcbanner("제작 시작! 2~4분 뒤 텔레그램 전송 + 라이브러리 등록. (후보 목록에서 제외됩니다)","ok");
      setTimeout(loadRuns,4000);setTimeout(()=>loadCandidates(cat),15000);}
    else{const t=await r.text();srcbanner("실패("+r.status+"): 토큰 권한 확인.<br><span class='mono' style='font-size:11px'>"+esc(t.slice(0,140))+"</span>","err");if(btn)btn.disabled=false;}
  }catch(e){srcbanner("요청 실패: "+e,"err");if(btn)btn.disabled=false;}
}
function lfbanner(t,c){const m=$("#lfmsg");if(m){m.className="banner show "+(c||"");m.innerHTML=t;}}
async function loadLongformResults(){
  const el=$("#lfresults");if(!el)return;
  const recs=await listLongform();
  if(!recs.length){el.innerHTML="";return;}
  el.innerHTML='<span class="lbl">최근 롱폼 결과</span>'+recs.slice(0,6).map(r=>(
    '<a class="clitem" href="/lf/'+encodeURIComponent(r.id)+'"><span class="no">'+esc(r.n||0)+'종</span>'+
    '<span class="nm">'+esc(r.yt_title||r.id)+'<small>'+esc(r.yt_title_ko||"")+'</small></span>'+
    '<span class="t">'+esc(String(r.date||r.created_at||"").slice(0,10))+'</span></a>'
  )).join('');
}
async function loadRuns(){
  try{
    const [r,cat]=await Promise.all([fetchT(API+"/actions/workflows/"+WF+"/runs?per_page=8",{headers:headers(true)}),listContent()]);
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

// ── 라이브러리: 롱폼 + 쇼츠 콘텐츠 목록 ──
async function renderLibrary(){
  view().innerHTML='<div class="card"><span class="lbl">롱폼 (탭하면 제목·설명 열람)</span><div id="lflist"><div class="hint">불러오는 중…</div></div></div>'+
    '<div class="card"><span class="lbl">쇼츠 (탭하면 열람·수정·재생성)</span><div id="clist"><div class="hint">불러오는 중…</div></div></div>';
  const [lf,cat]=await Promise.all([listLongform(),listContent()]);
  const lfel=document.getElementById("lflist");
  lfel.innerHTML=lf.length?lf.map(r=>(
    '<a class="clitem" href="/lf/'+encodeURIComponent(r.id)+'"><span class="no">'+esc(r.n||0)+'종</span>'+
    '<span class="nm">'+esc(r.yt_title||r.id)+'<small>'+esc(r.yt_title_ko||"")+'</small></span>'+
    '<span class="t">'+esc(String(r.date||"").slice(0,10))+'</span></a>'
  )).join(""):'<div class="hint">아직 롱폼이 없습니다.</div>';
  const el=document.getElementById("clist");
  el.innerHTML=cat.length?cat.map(it=>{
    const id=num3(it.no);
    return '<a class="clitem" href="/c/'+id+'"><span class="no">#'+id+'</span>'+
      '<span class="nm">'+esc(it.common_name_ko||"종")+'<small>'+esc(it.common_name_en||"")+" · "+esc(it.scientific_name||"")+'</small></span>'+
      '<span class="t">'+esc(it.date||"")+'</span></a>';
  }).join(""):'<div class="hint">아직 쇼츠가 없습니다. <a href="/">제작하러 가기</a></div>';
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
  const _rev=md.rev||"r1";   // rev 없는 옛 레코드도 캐시버스터를 붙여 '옛 플레인 URL 캐시'를 한 번 무효화
  const vurl=bust(md.video_url,_rev), curl=bust(md.cover_url,_rev);
  if(md.video_url)mediaHtml='<video src="'+prox(vurl)+'" controls playsinline preload="metadata" poster="'+(md.cover_url?prox(curl):"")+'"></video>';
  else if(md.cover_url)mediaHtml='<img src="'+prox(curl)+'">';
  else mediaHtml='<div class="hint">미디어가 아직 업로드되지 않았습니다(제작 직후 잠시 후 반영).</div>';
  // ★유튜브 쇼츠 업로드는 자동으로 하지 않는다 — 위 영상을 확인하고 이상 없으면 버튼으로 직접 올린다.
  let upHtml="";
  if(md.youtube_url){
    upHtml='<div class="card" style="margin-top:12px;background:#0d2216;border-color:#1c5">'+
      '<span class="lbl">유튜브 쇼츠 업로드 완료('+esc(md.youtube_privacy||"")+')</span>'+
      '<a class="btn save" href="'+esc(md.youtube_url)+'" target="_blank" style="margin-top:8px">유튜브에서 보기 → '+esc(md.youtube_url)+'</a></div>';
  }else if(md.video_url){
    upHtml='<div class="card" style="margin-top:12px">'+
      '<span class="lbl">유튜브 쇼츠 올리기 — 위 영상을 확인하고 이상 없을 때만 누르세요(자동 업로드 안 함)</span>'+
      '<div class="btnrow" style="margin-top:8px;align-items:center;gap:8px">'+
        '<select id="shpriv" style="padding:8px;border-radius:8px"><option value="public">공개</option>'+
          '<option value="unlisted">일부공개(링크 아는 사람만)</option>'+
          '<option value="private">비공개(나만)</option></select>'+
        '<button class="btn save" id="shup">유튜브 쇼츠로 올리기</button></div>'+
      '<div class="hint" style="margin-top:6px">누르면 업로드가 시작되고 1~3분 뒤 이 화면을 새로고침하면 링크가 표시됩니다.</div></div>';
  }
  // 일/한 분리: 신규 레코드는 분리 필드(caption_ko 등), 구 레코드는 합본 캡션을 분해해 표시
  const legacy=splitLegacy(re.caption||"");
  const capJP=legacy.jp, capKO=re.caption_ko||legacy.ko;
  const hookKO=re.hook_ko||"";
  // 유튜브 제목용 일본어 종명: reveal_name("和名 / 学名")의 앞부분 → 없으면 영문명
  const jpName=((re.reveal_name||"").split("/")[0]||"").trim()||sp.common_name_en||"";
  const tagsKO=(re.hashtags_ko||[]).join(" ");
  const tags=(re.hashtags||[]).map(t=>'<span class="tag">'+esc(t)+'</span>').join("");
  dc.className="card detail";
  dc.innerHTML=
    '<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:10px"><b style="font-size:19px">#'+esc(id)+' '+esc(sp.common_name_ko||"")+'</b>'+
      '<span class="mono" style="color:var(--gy);font-size:12px">'+esc(sp.common_name_en||"")+'</span></div>'+
    mediaHtml+
    (md.video_url?'<div class="btnrow" style="margin-top:8px"><button class="btn save" id="bdl">비디오 저장하기</button></div><div class="hint" id="dlhint" style="margin-top:6px"></div>':"")+
    // ★유튜브 썸네일(전체 타이틀 노출 오프닝 프레임) — 미리보기 + 저장(유튜브 커스텀 썸네일용)
    (md.yt_thumb_url?('<div style="margin-top:12px"><span class="lbl">유튜브 썸네일 (오프닝 훅 · 제목 전체 노출)</span>'+
      '<img src="'+prox(bust(md.yt_thumb_url,md.rev||"r1"))+'" alt="유튜브 썸네일" style="width:150px;border-radius:8px;display:block;margin:6px 0"/>'+
      '<div class="btnrow"><button class="btn save" id="ythumb">유튜브 썸네일 저장</button></div>'+
      '<div class="hint" id="ythint" style="margin-top:4px"></div></div>'):"")+
    upHtml+
    '<div class="meta" style="margin-top:12px"><b>학명</b> <i>'+esc(sp.scientific_name||"")+'</i> · <b>수심</b> '+esc(sp.depth_range_m||"?")+'m<br>'+
      '<b>서식</b> '+esc(sp.habitat||"?")+' · <b>분포</b> '+esc(sp.distribution||"?")+'</div>'+
    // 유튜브 쇼츠 게시용 '영상 제목'(일/한) 프레임 — 편집·복사 가능(별도 프레임 요청 반영)
    '<div class="dual" style="margin-top:12px">'+
      '<div><span class="lbl">영상 제목 · 일본어(유튜브 쇼츠)</span>'+
        '<textarea id="etitlejp" rows="2">'+esc(re.yt_title||titleTags(ytTitle(re.hook,jpName),re.hashtags))+'</textarea>'+
        '<button class="btn save" id="cptjp" style="margin-top:6px">일본어 제목 복사</button></div>'+
      '<div><span class="lbl">영상 제목 · 한국어(참고)</span>'+
        '<textarea id="etitleko" rows="2">'+esc(re.yt_title_ko||titleTags(ytTitle(hookKO,sp.common_name_ko,1),re.hashtags_ko))+'</textarea>'+
        '<button class="btn" id="cptko" style="margin-top:6px">한국어 제목 복사</button></div>'+
    '</div>'+
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
      '<button class="btn" id="bdel" style="grid-column:1/3;background:#8b1a1a;color:#fff">이 제작물 삭제 (영상·기록 영구 삭제)</button>'+
    '</div>'+
    postSection(rec.post)+
    '<div class="hint">이미지 출처: '+esc(src.image_credit||"—")+'<br>정보 출처: '+esc((src.info_sources||[]).join(" · ")||"—")+'</div>';

  // 현 시스템은 실사 영상 재편집(무료) — Veo·카드뉴스 이미지 재생성은 구 시스템 유물이라 제거
  if($("#bdl"))$("#bdl").onclick=()=>saveVideo(prox(bust(md.video_url,md.rev||"r1")),esc(id)+"_"+(sp.common_name_ko||"reel")+".mp4");
  // 유튜브 커스텀 썸네일(오프닝 훅 · 제목 전체 노출 프레임) 저장 — 이미지용 mime/hint/btn 지정
  if($("#ythumb"))$("#ythumb").onclick=()=>saveVideo(prox(bust(md.yt_thumb_url,md.rev||"r1")),esc(id)+"_"+(sp.common_name_ko||"reel")+"_thumb.jpg",{mime:"image/jpeg",hint:"#ythint",btn:"#ythumb",kind:"이미지"});
  $("#cptjp").onclick=()=>copyText($("#etitlejp").value,"일본어 제목을 복사했어요. 유튜브 쇼츠 제목에 붙여넣기 하세요.");
  $("#cptko").onclick=()=>copyText($("#etitleko").value,"한국어 제목(참고)을 복사했어요.");
  $("#cpjp").onclick=()=>copyText($("#ecapjp").value,"일본어 캡션+해시태그를 복사했어요. 릴스에 붙여넣기 하세요.");
  $("#cpko").onclick=()=>copyText($("#ecapko").value,"한국어(참고)를 복사했어요.");
  $("#bsave").onclick=()=>saveCaption(id);
  $("#bcap").onclick=()=>capRegen(id);
  $("#bvid").onclick=()=>{if(confirm("이 회차의 영상을 같은 종으로 처음부터 다시 만듭니다(무료·2~4분). 진행할까요?"))regen(id,"video");};
  $("#ball").onclick=()=>{if(confirm("영상·캡션을 모두 처음부터 다시 만듭니다(무료·2~4분). 진행할까요?"))regen(id,"all");};
  $("#bigp").onclick=()=>igPublish(id,true);
  $("#big").onclick=()=>{if(confirm("이 릴스를 인스타그램(@abyss_0cean)에 실제로 발행합니다. 되돌릴 수 없어요. 진행할까요?"))igPublish(id,false);};
  $("#bdel").onclick=()=>deleteContent(id,"reel");
  const shBtn=document.getElementById("shup");
  if(shBtn)shBtn.onclick=()=>uploadShort(id);
}

// 쇼츠 유튜브 '수동' 업로드 — upload-short.yml 디스패치(운영자 확인 후 클릭).
async function uploadShort(id){
  if(!authReady()){banner("유튜브 업로드에는 GitHub 토큰(Actions: Read and write)이 필요합니다.","err");return;}
  const priv=($("#shpriv")||{}).value||"public";
  const nm={public:"공개",unlisted:"일부공개",private:"비공개"}[priv]||priv;
  if(!confirm("이 쇼츠를 유튜브에 '"+nm+"'로 올릴까요? 확인을 누르면 업로드가 시작됩니다."))return;
  const b=$("#shup"); if(b){b.disabled=true;b.textContent="업로드 시작 중…";}
  banner("유튜브 쇼츠 업로드를 시작합니다… (1~3분 뒤 새로고침하면 링크가 표시됩니다)");
  try{
    const r=await fetch(API+"/actions/workflows/"+US_WF+"/dispatches",{method:"POST",headers:headers(true),
      body:JSON.stringify({ref:BRANCH,inputs:{content_id:id,privacy:priv}})});
    if(r.status===204)banner("업로드 시작! 1~3분 뒤 이 화면을 새로고침하세요.","ok");
    else{const t=await r.text();banner("업로드 시작 실패("+r.status+")<br><span class='mono' style='font-size:11px'>"+esc(t.slice(0,140))+"</span>","err");
      if(b){b.disabled=false;b.textContent="유튜브 쇼츠로 올리기";}}
  }catch(e){banner("업로드 오류: "+e,"err");if(b){b.disabled=false;b.textContent="유튜브 쇼츠로 올리기";}}
}

// ── 롱폼 상세: 제목·설명(일/한, 타임스탬프 포함) 프레임 + 영상 미리보기 ──
async function renderLongformDetail(id){
  view().innerHTML='<a class="back" href="/">← 제작 페이지</a><div class="card" id="lfcard"><div class="hint">불러오는 중…</div></div>';
  const rec=await fetchRecord(id);
  const dc=document.getElementById("lfcard");
  if(!rec){
    dc.innerHTML='<div class="hint">이 롱폼 기록을 찾을 수 없습니다(아직 제작 중이거나 완료 전).</div>'+
      '<div class="btnrow" style="margin-top:14px"><a class="btn" href="/">← 제작 페이지로</a></div>';
    return;
  }
  const md=rec.media||{};
  let mediaHtml="";
  const _rev=md.rev||"r1";   // rev 없는 옛 레코드도 캐시버스터를 붙여 '옛 플레인 URL 캐시'를 한 번 무효화
  const vurl=bust(md.video_url,_rev), curl=bust(md.cover_url,_rev);
  if(md.video_url)mediaHtml='<video src="'+prox(vurl)+'" controls playsinline preload="metadata" poster="'+(md.cover_url?prox(curl):"")+'"></video>';
  else if(md.cover_url)mediaHtml='<img src="'+prox(curl)+'">';
  // ★유튜브 업로드는 자동으로 하지 않는다 — 아래 영상을 확인하고 이상 없으면 버튼으로 직접 올린다.
  let upHtml;
  if(md.youtube_url){
    upHtml='<div class="card" style="margin-top:12px;background:#0d2216;border-color:#1c5">'+
      '<span class="lbl">유튜브 업로드 완료('+esc(md.youtube_privacy||"")+')</span>'+
      '<a class="btn save" href="'+esc(md.youtube_url)+'" target="_blank" style="margin-top:8px">유튜브에서 보기 → '+esc(md.youtube_url)+'</a></div>';
  }else{
    upHtml='<div class="card" style="margin-top:12px">'+
      '<span class="lbl">유튜브 올리기 — 위 영상을 확인하고 이상 없을 때만 누르세요(자동 업로드 안 함)</span>'+
      '<div class="btnrow" style="margin-top:8px;align-items:center;gap:8px">'+
        '<select id="lfpriv" style="padding:8px;border-radius:8px"><option value="public">공개</option>'+
          '<option value="unlisted">일부공개(링크 아는 사람만)</option>'+
          '<option value="private">비공개(나만)</option></select>'+
        '<button class="btn save" id="lfup">유튜브에 올리기</button></div>'+
      '<div class="banner" id="msg"></div>'+
      '<div class="hint" style="margin-top:6px">누르면 업로드가 시작되고 1~3분 뒤 이 화면을 새로고침하면 링크가 표시됩니다.</div></div>';
  }
  dc.className="card detail";
  dc.innerHTML=
    '<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:10px"><b style="font-size:19px">'+esc(id)+'</b>'+
      '<span class="mono" style="color:var(--gy);font-size:12px">'+esc(rec.theme||"")+' · '+esc(rec.n||0)+'종 · '+Math.round(rec.total_s||0)+'초</span></div>'+
    mediaHtml+
    // 쇼츠 상세와 동일한 저장 UX(#bdl/#dlhint → saveVideo: 공유시트 우선, Blob 다운로드 폴백)
    (md.video_url?'<div class="btnrow" style="margin-top:8px"><button class="btn save" id="bdl">비디오 저장하기</button></div><div class="hint" id="dlhint" style="margin-top:6px"></div>':"")+
    upHtml+
    '<div class="dual" style="margin-top:12px">'+
      '<div><span class="lbl">영상 제목 · 일본어(유튜브)</span>'+
        '<textarea readonly rows="2">'+esc(rec.yt_title||"")+'</textarea></div>'+
      '<div><span class="lbl">영상 제목 · 한국어(참고)</span>'+
        '<textarea readonly rows="2">'+esc(rec.yt_title_ko||"")+'</textarea></div>'+
    '</div>'+
    '<div class="dual" style="margin-top:8px">'+
      '<div><span class="lbl">영상 설명(주제 + 00:00 타임스탬프) · 일본어</span>'+
        '<textarea readonly rows="14">'+esc(rec.yt_description||"")+'</textarea>'+
        '<button class="btn save" id="lfcpjp" style="margin-top:6px">일본어 설명 복사</button></div>'+
      '<div><span class="lbl">영상 설명(주제 + 00:00 타임스탬프) · 한국어</span>'+
        '<textarea readonly rows="14">'+esc(rec.yt_description_ko||"")+'</textarea>'+
        '<button class="btn" id="lfcpko" style="margin-top:6px">한국어 설명 복사</button></div>'+
    '</div>'+
    '<div class="dual" style="margin-top:8px">'+
      '<div><span class="lbl">해시태그(SEO 최적화) · 일본어</span>'+
        '<textarea id="lftagjp" readonly rows="4">'+esc((rec.hashtags||[]).join(" "))+'</textarea>'+
        '<button class="btn save" id="lfhtjp" style="margin-top:6px">일본어 해시태그 복사</button></div>'+
      '<div><span class="lbl">해시태그(SEO 최적화) · 한국어(참고)</span>'+
        '<textarea id="lftagko" readonly rows="4">'+esc((rec.hashtags_ko||[]).join(" "))+'</textarea>'+
        '<button class="btn" id="lfhtko" style="margin-top:6px">한국어 해시태그 복사</button></div>'+
    '</div>'+
    // 부분 재생성(영상 유지·저비용) — 과거 레코드(해시태그 빈칸 등) 보정용. 규칙대로 텍스트만 다시 생성.
    '<div class="card" style="margin-top:12px">'+
      '<span class="lbl">제목·설명·해시태그 재생성(영상은 그대로 · 20~40초)</span>'+
      '<div class="btnrow" style="margin-top:8px;display:grid;grid-template-columns:1fr 1fr;gap:8px">'+
        '<button class="btn warn" id="lfrgtag">해시태그 재생성</button>'+
        '<button class="btn" id="lfrgtitle">제목 재생성</button>'+
        '<button class="btn" id="lfrgdesc">설명 재생성</button>'+
        '<button class="btn" id="lfrgall">전체(제목+설명+해시태그)</button></div>'+
      '<div class="hint" style="margin-top:6px">누르면 20~40초 뒤 이 화면을 새로고침하면 값이 채워집니다.</div></div>'+
    '<div class="btnrow" style="margin-top:12px"><button class="btn" id="lfdel" style="background:#8b1a1a;color:#fff">이 롱폼 삭제 (영상·기록 영구 삭제)</button></div>';
  const tas=dc.querySelectorAll("textarea");
  $("#lfcpjp").onclick=()=>copyText(tas[2].value,"일본어 설명을 복사했어요. 유튜브 설명란에 붙여넣기 하세요.");
  $("#lfcpko").onclick=()=>copyText(tas[3].value,"한국어 설명(참고)을 복사했어요.");
  $("#lfhtjp").onclick=()=>copyText($("#lftagjp").value,"일본어 해시태그를 복사했어요. 유튜브 설명란·태그에 붙여넣기 하세요.");
  $("#lfhtko").onclick=()=>copyText($("#lftagko").value,"한국어 해시태그(참고)를 복사했어요.");
  $("#lfrgtag").onclick=()=>regenLongform(id,"hashtags");
  $("#lfrgtitle").onclick=()=>regenLongform(id,"title");
  $("#lfrgdesc").onclick=()=>regenLongform(id,"desc");
  $("#lfrgall").onclick=()=>regenLongform(id,"all");
  if($("#bdl"))$("#bdl").onclick=()=>saveVideo(prox(bust(md.video_url,md.rev||"r1")),esc(id)+"_longform.mp4");
  const upBtn=document.getElementById("lfup");
  if(upBtn)upBtn.onclick=()=>uploadLongform(id);
  if($("#lfdel"))$("#lfdel").onclick=()=>deleteContent(id,"longform");
}

// 롱폼 유튜브 '수동' 업로드 — upload-longform.yml 디스패치(운영자 확인 후 클릭).
async function uploadLongform(id){
  if(!authReady()){banner("유튜브 업로드에는 GitHub 토큰(Actions: Read and write)이 필요합니다.","err");return;}
  const priv=($("#lfpriv")||{}).value||"public";
  const nm={public:"공개",unlisted:"일부공개",private:"비공개"}[priv]||priv;
  if(!confirm("이 영상을 유튜브에 '"+nm+"'로 올릴까요? 확인을 누르면 업로드가 시작됩니다."))return;
  const b=$("#lfup"); if(b){b.disabled=true;b.textContent="업로드 시작 중…";}
  banner("유튜브 업로드를 시작합니다… (1~3분 뒤 새로고침하면 링크가 표시됩니다)");
  try{
    const r=await fetch(API+"/actions/workflows/"+UP_WF+"/dispatches",{method:"POST",headers:headers(true),
      body:JSON.stringify({ref:BRANCH,inputs:{content_id:id,privacy:priv}})});
    if(r.status===204)banner("업로드 시작! 1~3분 뒤 이 화면을 새로고침하세요.","ok");
    else{const t=await r.text();banner("업로드 시작 실패("+r.status+")<br><span class='mono' style='font-size:11px'>"+esc(t.slice(0,140))+"</span>","err");
      if(b){b.disabled=false;b.textContent="유튜브에 올리기";}}
  }catch(e){banner("업로드 오류: "+e,"err");if(b){b.disabled=false;b.textContent="유튜브에 올리기";}}
}

// 롱폼 제목·설명·해시태그만 재생성(영상 유지) — regen-longform-meta.yml 디스패치.
async function regenLongform(id,scope){
  if(!authReady()){banner("재생성에는 GitHub 토큰(Actions: Read and write)이 필요합니다.","err");return;}
  const nm={all:"제목·설명·해시태그 전체",title:"제목",desc:"설명",hashtags:"해시태그"}[scope]||scope;
  banner(nm+" 재생성 중… (영상은 그대로, 20~40초 뒤 새로고침)");
  try{
    const r=await fetch(API+"/actions/workflows/"+RGLF_WF+"/dispatches",{method:"POST",headers:headers(true),
      body:JSON.stringify({ref:BRANCH,inputs:{content_id:id,scope:scope}})});
    if(r.status===204)banner(nm+" 재생성 시작! 20~40초 뒤 이 화면을 새로고침하면 값이 채워집니다.","ok");
    else{const t=await r.text();banner("재생성 시작 실패("+r.status+")<br><span class='mono' style='font-size:11px'>"+esc(t.slice(0,140))+"</span>","err");}
  }catch(e){banner("재생성 오류: "+e,"err");}
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
        yt_title:($("#etitlejp")||{}).value||"", yt_title_ko:($("#etitleko")||{}).value||"",
      }})});
    if(r.status===204)banner("저장 시작! 20~40초 뒤 저장소에 반영됩니다(새로고침).","ok");
    else{const t=await r.text();banner("저장 실패("+r.status+")<br><span class='mono' style='font-size:11px'>"+esc(t.slice(0,140))+"</span>","err");}
  }catch(e){banner("저장 오류: "+e,"err");}
}

// 제작물 삭제: 레코드(content/<id>.json)+매니페스트 항목+미디어 릴리스를 영구 삭제.
// Contents/Releases API 직접 삭제는 토큰에 따라 403 → 저장과 동일하게 전용 워크플로 디스패치.
async function deleteContent(id,kind){
  if(!authReady()){banner("삭제에는 GitHub 토큰(Actions: Read and write)이 필요합니다.","err");return;}
  const label=(kind==="longform")?"이 롱폼":"이 쇼츠";
  if(!confirm(label+" 제작물을 영구 삭제합니다.\\n\\n· 영상·이미지(릴리스 미디어)\\n· 콘텐츠 기록\\n\\n되돌릴 수 없습니다. 계속할까요?\\n\\nid: "+id))return;
  banner("삭제 중… (반영까지 20~40초)");
  try{
    const r=await fetch(API+"/actions/workflows/"+DEL_WF+"/dispatches",{method:"POST",headers:headers(true),
      body:JSON.stringify({ref:BRANCH,inputs:{content_id:String(id)}})});
    if(r.status===204){
      banner("삭제 시작! 20~40초 뒤 목록에서 사라집니다.","ok");
      // 잠시 뒤 목록으로 이동(상세는 곧 사라짐)
      setTimeout(()=>{location.href=(kind==="longform")?"/":"/library";},1600);
    }else{const t=await r.text();banner("삭제 실패("+r.status+")<br><span class='mono' style='font-size:11px'>"+esc(t.slice(0,140))+"</span>","err");}
  }catch(e){banner("삭제 오류: "+e,"err");}
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
// 비디오/이미지 공용 저장(공유시트 우선 → Blob 다운로드 → 직접 링크 폴백).
// opt.hint/opt.btn: 상태·버튼 셀렉터(기본 비디오용). opt.mime: File 타입. opt.kind: 안내 문구('동영상'/'이미지').
async function saveVideo(u,name,opt){
  opt=opt||{};
  const h=$(opt.hint||"#dlhint"); const say=t=>{if(h)h.innerHTML=t;};
  const mime=opt.mime||"video/mp4"; const kind=opt.kind||"동영상";
  const saveWord=(mime.indexOf("image")===0)?"이미지를 사진에 저장":"비디오를 사진에 저장";
  // ★가장 확실한 폴백: 프록시 직접 다운로드 링크(dl=1 → 첨부). JS blob이 실패/멈춰도 이 링크는 항상 동작.
  const dl=u+(u.includes("?")?"&":"?")+"dl=1&name="+encodeURIComponent(name);
  const link='<a href="'+dl+'" target="_blank" rel="noopener" style="color:var(--cy);text-decoration:underline">여기를 눌러 저장</a>';
  const btn=$(opt.btn||"#bdl"); if(btn)btn.disabled=true;
  say(kind+' 준비 중… (안 되면 '+link+')');
  try{
    // 60초 타임아웃(멈춤 방지 — '준비 중'에서 무한 대기하던 사고 방지)
    const c=("AbortController"in window)?new AbortController():null;
    const to=c?setTimeout(()=>c.abort(),60000):0;
    const r=await fetch(u,c?{signal:c.signal}:{}); if(to)clearTimeout(to);
    if(!r.ok)throw new Error("HTTP "+r.status);
    const blob=await r.blob();
    const file=new File([blob],name,{type:mime});
    // ① 네이티브 공유 시트(아이폰: "사진에 저장"이 여기 있음)
    if(navigator.canShare&&navigator.canShare({files:[file]})){
      try{ await navigator.share({files:[file],title:name});
        say('공유 창에서 <b>"'+saveWord+'"</b>을 누르세요.'); if(btn)btn.disabled=false; return;
      }catch(e){ if(String(e).indexOf("AbortError")>=0){say("취소됨. "+link); if(btn)btn.disabled=false; return;} }
    }
    // ② 폴백: Blob 다운로드 → 파일 앱에 저장(거기서 사진으로 옮길 수 있음)
    const url=URL.createObjectURL(blob);
    const a=document.createElement("a"); a.href=url; a.download=name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),5000);
    say('저장을 시작했어요. (안 되면 '+link+')');
  }catch(e){ say('자동 저장 실패('+esc(String(e))+'). '+link+' 를 눌러 저장하세요.'); }
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

// ── 다운로드 가능 영상 찾기(키 없이 · 썸네일·주제 미리보기) ──
// 목적: 운영자가 직접 소싱할 '다운로드 가능한' 영상을 키워드로 찾아 썸네일·주제와 함께 보여준다.
// 소스: ① Wikimedia Commons(항상 자유 라이선스 · 직다운 URL) ② Internet Archive(엄격 안전필터).
// ★저작권: 나레이션·자막을 입히는 것은 '2차 저작물'이라 변경금지(ND)·비상업(NC)은 배제하고
//   PD/CC0/CC-BY/CC-BY-SA만 '안전(safe)'으로 표시한다. 유튜브 미러(archive의 youtube-*)는 항상 제외.
//   운영자는 최종 사용 전 원본 페이지에서 권리를 다시 확인한다(모듈은 소싱 후보만 제시).
const VS_UA = "deep-dive-log-dashboard";
// Internet Archive에서 라이선스 표기가 없어도 퍼블릭도메인으로 신뢰할 수 있는 컬렉션(정부·기록보관)
const VS_PD_COLLECTIONS = ["prelinger","nasa","noaa","usgs","navalhistory","naval-history",
  "usnationalarchives","nara","peabodyawards","fedflix","usgovfilms","biodiversity"];

// 라이선스 URL/토큰 → 재사용(2차 저작·상업) 허용 여부. NC/ND는 불허, PD/CC0/BY/BY-SA만 허용.
function vsLicenseFromUrl(u){
  const s = String(u || "").toLowerCase();
  if(!s) return null;
  if(s.includes("publicdomain") || s.includes("/zero/") || s.includes("cc0"))
    return {label:"Public Domain / CC0", safe:true};
  const m = s.match(/licenses\/(by(?:-[a-z]+)*)\b/);
  const tok = m ? m[1] : "";
  if(!tok.startsWith("by")) return null;                 // 알 수 없음
  if(tok.includes("nc") || tok.includes("nd"))           // 비상업·변경금지 → 나레이션 불가
    return {label:"CC "+tok.toUpperCase()+" (사용 불가)", safe:false, blocked:true};
  return {label:"CC "+tok.toUpperCase(), safe:true};
}
// Commons extmetadata → 라이선스 라벨/안전여부. nc/nd면 제외(null).
function vsCommonsLicense(em){
  const lic = String(((em.License||{}).value)||"").toLowerCase();          // 예: cc-by-sa-4.0, cc0, pd
  const name = String(((em.LicenseShortName||{}).value)||"");
  if(lic.includes("nc") || lic.includes("nd") || /-(nc|nd)\b/.test(name.toLowerCase())) return null;
  if(lic.includes("cc0") || lic==="pd" || lic.includes("publicdomain") || /public domain|cc0/i.test(name))
    return {label:name||"Public Domain", safe:true};
  if(lic.startsWith("cc-by") || /^cc by/i.test(name))
    return {label:name||"CC BY", safe:true};
  // Commons는 대체로 자유 라이선스지만, 명확치 않으면 '확인 필요'(amber)로 노출
  return {label:name||"라이선스 확인 필요", safe:false};
}
// Internet Archive 문서 → 라이선스 판정(null=제외). youtube 미러는 호출 전 제외.
function vsArchiveLicense(doc){
  const lic = vsLicenseFromUrl(doc.licenseurl);
  if(lic){ if(lic.blocked) return null; return lic; }
  const colls = [].concat(doc.collection || []).map(c => String(c).toLowerCase());
  if(colls.some(c => VS_PD_COLLECTIONS.includes(c)))
    return {label:"Public Domain (아카이브 컬렉션)", safe:true};
  return null;                                            // 라이선스 불명 → 위험(제외)
}
function vsCleanTitle(t){
  return String(t||"").replace(/\.[a-z0-9]{2,4}$/i,"").replace(/[_]+/g," ")
    .replace(/\s+/g," ").trim().slice(0,120);
}
function vsStrip(t){
  return String(t||"").replace(/<[^>]*>/g," ").replace(/&[a-z]+;/gi," ")
    .replace(/\s+/g," ").trim().slice(0,180);
}
function vsFmtRank(name){
  const e=(String(name).split(".").pop()||"").toLowerCase();
  return e==="mp4"?0:e==="m4v"?1:e==="webm"?2:e==="ogv"?3:4;
}

async function vsCommons(q){
  const api = "https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search"+
    "&gsrsearch="+encodeURIComponent(q+" filetype:video")+"&gsrnamespace=6&gsrlimit=14"+
    "&prop=imageinfo&iiprop=url%7Csize%7Cmime%7Cextmetadata&iiurlwidth=360";
  const r = await fetch(api, {headers:{"User-Agent":VS_UA}});
  if(!r.ok) return [];
  const d = await r.json();
  const pages = ((d.query||{}).pages) || {};
  const out = [];
  for(const p of Object.values(pages)){
    const ii = ((p.imageinfo||[])[0]) || {};
    if(!ii.url || !String(ii.mime||"").startsWith("video")) continue;
    const lic = vsCommonsLicense(ii.extmetadata||{});
    if(!lic) continue;                                    // nc/nd 제외
    const title = vsCleanTitle(String(p.title||"").replace(/^File:/,""));
    const desc = vsStrip(((ii.extmetadata||{}).ImageDescription||{}).value) || title;
    out.push({source:"Wikimedia Commons", title, topic:desc,
      thumb:ii.thumburl||"", download:ii.url,
      page:"https://commons.wikimedia.org/wiki/"+encodeURIComponent(p.title||""),
      license:lic.label, safe:lic.safe,
      duration:ii.duration?Math.round(ii.duration):0, mime:ii.mime||""});
  }
  return out;
}
async function vsArchiveResolve(doc, lic){
  const id = String(doc.identifier);
  const m = await fetch("https://archive.org/metadata/"+encodeURIComponent(id), {headers:{"User-Agent":VS_UA}});
  if(!m.ok) return null;
  const d = await m.json();
  const files = (d.files||[]).filter(f => /\.(mp4|webm|ogv|m4v)$/i.test(String(f.name||"")));
  if(!files.length || !d.server || !d.dir) return null;
  files.sort((a,b)=>vsFmtRank(a.name)-vsFmtRank(b.name));
  const f = files[0];
  const dur = parseFloat(f.length||"0");  // 'H:MM:SS' 또는 초. 숫자만 신뢰.
  return {source:"Internet Archive", title:vsCleanTitle(doc.title||id),
    topic:vsStrip(doc.description) || vsCleanTitle(doc.title||id),
    thumb:"https://archive.org/services/img/"+encodeURIComponent(id),
    download:"https://"+d.server+d.dir+"/"+encodeURIComponent(f.name),
    page:"https://archive.org/details/"+encodeURIComponent(id),
    license:lic.label, safe:lic.safe,
    duration:Number.isFinite(dur)?Math.round(dur):0, mime:""};
}
async function vsArchive(q){
  // 검색 단계에서 이미 '라이선스 있음 또는 PD 컬렉션'으로 좁힌다(안 그러면 상위 결과가 미러·미라이선스
  // 영화로 차서 코드 필터 후 0건이 된다). NC/ND는 vsArchiveLicense가 코드에서 다시 걸러낸다.
  const lc = "(licenseurl:(*creativecommons* OR *publicdomain*) OR collection:(prelinger OR nasa OR noaa OR usgs OR fedflix OR biodiversity))";
  const api = "https://archive.org/advancedsearch.php?q="+
    encodeURIComponent("("+q+") AND mediatype:movies AND "+lc)+
    "&fl[]=identifier&fl[]=title&fl[]=description&fl[]=licenseurl&fl[]=collection&rows=14&output=json";
  const r = await fetch(api, {headers:{"User-Agent":VS_UA}});
  if(!r.ok) return [];
  const d = await r.json();
  const docs = ((d.response||{}).docs) || [];
  const picks = [];
  for(const x of docs){
    const id = String(x.identifier||"");
    if(!id || id.toLowerCase().startsWith("youtube-")) continue;   // 유튜브 미러 제외
    const lic = vsArchiveLicense(x);
    if(!lic) continue;
    picks.push({x, lic});
    if(picks.length>=6) break;
  }
  const res = await Promise.all(picks.map(p => vsArchiveResolve(p.x, p.lic).catch(()=>null)));
  return res.filter(Boolean);
}
async function videoSearch(url){
  const q = (url.searchParams.get("q")||"").trim();
  const src = (url.searchParams.get("src")||"all").toLowerCase();
  if(!q) return j({error:"empty query", results:[]}, 400);
  const tasks = [];
  if(src==="all"||src==="commons") tasks.push(vsCommons(q).catch(()=>[]));
  if(src==="all"||src==="archive") tasks.push(vsArchive(q).catch(()=>[]));
  const arr = (await Promise.all(tasks)).flat();
  const seen = new Set(); const out = [];
  for(const rr of arr){
    if(!rr || !rr.download || seen.has(rr.download)) continue;
    seen.add(rr.download); out.push(rr);
  }
  out.sort((a,b)=>(b.safe?1:0)-(a.safe?1:0));            // 안전(재사용 가능) 먼저
  return j({q, count:out.length, results:out.slice(0,24)});
}
// 테스트용(순수 로직) export — 네트워크 없이 회귀 검증
export { vsLicenseFromUrl, vsCommonsLicense, vsArchiveLicense, vsCleanTitle, vsStrip, vsFmtRank };

// ── 공개 읽기 프록시: content 레코드/카탈로그/매니페스트를 raw.githubusercontent.com(공개·무인증)로 중계 ──
// 왜(실제 결함): 기기에 PAT 없으면 GitHub API가 403 → 텔레그램 링크로 연 폰에서 레코드가 안 열림
// (무한 로딩). raw는 공개 리포에 무인증 200 → 어느 기기서든 조회 가능. 허용 경로만(개방 프록시 방지).
async function pubRead(url){
  const path = url.searchParams.get("path") || "";
  if(!/^short-movie-generator\/(content\/[\w.\-]+\.json|src\/categories\/deep_sea\/catalog\.json|src\/categories\/[\w\-]+\/[\w\-]+_(candidates|image_only)\.json)$/.test(path))
    return j({error:"path not allowed"}, 403);
  const target = "https://raw.githubusercontent.com/" + OWNER + "/" + REPO + "/" + BRANCH + "/" + path;
  try{
    const resp = await fetch(target, {headers:{"User-Agent":"deep-dive-log-dashboard"}, cf:{cacheTtl:20, cacheEverything:true}});
    if(!resp.ok) return new Response("", {status: resp.status});
    return new Response(await resp.text(), {status:200,
      headers:{"Content-Type":"application/json","Cache-Control":"no-store"}});
  }catch(e){ return new Response("", {status:502}); }
}

async function ghProxy(request, url, env){
  const token = env && env.GH_PAT;
  if(!token) return j({error:"server token not configured"}, 501);
  const rest = url.pathname.slice("/api/gh/".length);
  const m = request.method;
  // 이 앱이 실제로 쓰는 경로/메서드만 허용(토큰 오남용 방지)
  const ok =
    (m==="POST" && /^actions\/workflows\/[^/]+\/dispatches$/.test(rest)) ||
    (m==="GET"  && /^actions\/workflows\/[^/]+\/runs/.test(rest)) ||
    (m==="GET"  && /^contents\//.test(rest)) ||
    (m==="GET"  && /^releases\/tags\//.test(rest)) ||   // 첨부 영상 나레이션: 입력 릴리스 조회
    (m==="POST" && /^releases$/.test(rest));            // 첨부 영상 나레이션: 입력 릴리스 생성
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

// ── 첨부 영상 업로드 프록시: 브라우저 파일 → uploads.github.com Release 에셋 ──
// 서버 토큰 모드에서 브라우저에 토큰이 없으므로, 워커가 env.GH_PAT로 uploads.github.com에 중계한다.
// (파일 본문은 스트림 그대로 전달 → 큰 영상도 메모리 폭주 없이 업로드.)
async function ghUpload(request, url, env){
  const token = env && env.GH_PAT;
  if(!token) return j({error:"server token not configured"}, 501);
  if(request.method !== "POST") return j({error:"method not allowed"}, 405);
  const rid = url.searchParams.get("release_id") || "";
  const name = url.searchParams.get("name") || "";
  const ctype = url.searchParams.get("ctype") || "application/octet-stream";
  if(!/^\d+$/.test(rid) || !name) return j({error:"bad params"}, 400);
  const target = "https://uploads.github.com/repos/" + OWNER + "/" + REPO +
    "/releases/" + rid + "/assets?name=" + encodeURIComponent(name);
  const resp = await fetch(target, {method:"POST", headers:{
    "Authorization": "Bearer " + token,
    "Content-Type": ctype,
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "deep-dive-log-dashboard",
  }, body: request.body});
  const text = await resp.text();
  return new Response(text, {status:resp.status,
    headers:{"Content-Type":"application/json","Cache-Control":"no-store"}});
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
  // ★릴리스 허용 판정은 대소문자 무시(github.repository의 정규 케이스가 'Product'/'product'로 달라도
  //   403이 나지 않게 — 저장 버튼이 갑자기 안 되던 사고의 방어). 개방 프록시는 여전히 차단.
  if (!u.toLowerCase().startsWith(MEDIA_PREFIX.toLowerCase())) return j({ error: "url not allowed" }, 403);
  // 확장자 판정 시 캐시버스터(?v=...) 쿼리는 떼고 본다(붙어 있으면 'mp4?v=1'로 오판돼 403 나던 버그).
  const ext = (u.split("?")[0].split(".").pop() || "").toLowerCase();
  const type = MEDIA_TYPES[ext];
  if (!type) return j({ error: "type not allowed" }, 403);
  const h = { "User-Agent": "deep-dive-log-dashboard" };
  const range = request.headers.get("Range");
  if (range) h["Range"] = range;
  const resp = await fetch(u, { headers: h, redirect: "follow" });
  if (!resp.ok && resp.status !== 206) return j({ error: "upstream " + resp.status }, 502);
  const out = new Headers();
  out.set("Content-Type", type);
  // ★dl=1이면 첨부(파일 저장)로 내려준다 — JS blob 없이 브라우저 네이티브 다운로드(가장 확실한 폴백).
  //   없으면 inline(재생용, iOS '파일 열기' 화면 전환 방지).
  const dl = url.searchParams.get("dl");
  if (dl) {
    const name = (url.searchParams.get("name") || "video.mp4").replace(/[^\w.\-가-힣]+/g, "_");
    out.set("Content-Disposition", 'attachment; filename="' + name + '"');
  } else {
    out.set("Content-Disposition", "inline");
  }
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
    if (url.pathname === "/api/pub") return pubRead(url);
    if (url.pathname === "/api/ghupload") return ghUpload(request, url, env);
    if (url.pathname === "/api/vsearch") return videoSearch(url);
    if (url.pathname.startsWith("/api/gh/")) return ghProxy(request, url, env);
    return new Response(HTML, {
      headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" },
    });
  },
};
