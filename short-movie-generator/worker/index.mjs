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
// ★빌드 표시(운영자 확정 · 혼선 방지): "메뉴가 안 바뀌었다"가 배포 문제인지 화면 캐시인지
//   즉시 구분하려고 화면 하단에 찍는다. 대시보드를 고칠 때마다 이 값을 올린다.
const BUILD="v2026-07-26-5 (컷 칸 표시·아이폰 폭)";
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
async function fetchRaw(path,fresh){
  // 공개 읽기 프록시 우선(무인증·어느 기기서든 동작). 실패 시 인증 API로 폴백(타임아웃).
  // fresh=true면 cb(타임스탬프)로 raw CDN·엣지 캐시를 우회해 최신 커밋을 즉시 읽는다(재생성 직후용).
  const cbq = fresh ? ("&cb="+Date.now()) : "";
  try{const r=await fetchT("/api/pub?path="+encodeURIComponent(path)+cbq);
    if(r.ok)return await r.text();}catch(e){}
  try{const r=await fetchT(API+"/contents/"+path+"?ref="+BRANCH,{headers:{...headers(true),"Accept":"application/vnd.github.raw+json"}});
    if(!r.ok)return null;return await r.text();}catch(e){return null;}
}
async function fetchManifest(){const t=await fetchRaw(CONTENT_DIR+"/manifest.json");try{const a=JSON.parse(t);return Array.isArray(a)?a:[];}catch(e){return [];}}
async function fetchCatalog(){const t=await fetchRaw(CATALOG_PATH);try{const a=JSON.parse(t);return Array.isArray(a)?a:[];}catch(e){return [];}}
// 전 콘텐츠 목록: 공개 매니페스트(manifest.json) 우선 → 어느 기기서든 무인증 조회.
// 인증 가능한 기기에선 디렉토리 API로 매니페스트에 아직 없는 레거시 레코드를 보강(중복 제거).
// 목록 정렬: 날짜 최신순 → 같은 날은 id 역순. 도감형(3자리)과 나레이션형(nv-…) id가 섞여
// 문자열 비교만으로는 순서가 뒤엉키므로 날짜를 1순위로 둔다.
function sortFeed(a){
  return a.sort((x,y)=>{
    const d=String(y.date||"").localeCompare(String(x.date||""));
    return d!==0?d:String(y.no).localeCompare(String(x.no));
  });
}
async function listContent(){
  const man=await fetchManifest();
  const out=man.filter(x=>x&&x.kind!=="longform"&&x.kind!=="narrate").map(x=>({
    no:String(x.id), common_name_ko:x.common_name_ko||x.common_name_en||"종",
    common_name_en:x.common_name_en||"", scientific_name:x.scientific_name||"",
    date:x.date||"", hasVideo:!!x.has_video, kind:"reels", href:"/c/"+num3(x.id)}));
  // ★나레이션형 쇼츠도 같은 목록에 넣는다(운영자 확정): 종이 없는 영상이라도 결국 '쇼츠'이므로
  //   실행 현황·라이브러리에서 보여야 한다. 예전엔 목록에서 아예 빠져 텔레그램 링크로만 열 수 있었다.
  //   ※상세 화면은 다르다(/nv/<id>) → href 를 항목마다 들고 다녀 잘못된 /c/ 로 가지 않게 한다.
  //     (실사고 nv-29999730295: 잘못 분류돼 /c/ 로 연결되며 "아직 제작 안 됨"만 뜨던 유령 항목)
  man.filter(x=>x&&x.kind==="narrate"&&(x.mode||"shorts")==="shorts").forEach(x=>out.push({
    no:String(x.id), common_name_ko:x.yt_title_ko||x.yt_title||"나레이션 쇼츠",
    common_name_en:x.yt_title||"", scientific_name:"",
    date:x.date||"", hasVideo:!!x.has_video, kind:"narrate",
    href:"/nv/"+encodeURIComponent(String(x.id))}));
  // 매니페스트에 모든 레코드가 들어있으므로, 인증 디렉토리 보강은 '인증 가능한 기기(서버모드/토큰)'에서만.
  // 무인증 폰(인앱 웹뷰)에선 api.github.com 요청이 멈추므로 아예 건너뛴다(매니페스트만으로 충분).
  if(!(SERVER||pat()))return sortFeed(out);
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
                hasVideo:!!(rec.media&&rec.media.video_url),
                kind:"reels", href:"/c/"+num3(id)};
      }));
      out.push(...recs.filter(Boolean));
    }
  }catch(e){}
  return sortFeed(out);
}
async function fetchRecord(id,fresh){const t=await fetchRaw(CONTENT_DIR+"/"+id+".json",fresh);try{return JSON.parse(t);}catch(e){return null;}}
// 롱폼 결과 목록: 공개 매니페스트에서 kind=longform 만.
async function listLongform(){
  const man=await fetchManifest();
  // ★나레이션형 롱폼도 같은 목록에 넣는다(쇼츠와 같은 이유 — 목록에서 빠져 텔레그램 링크로만
  //   열 수 있었다). 상세 화면 경로가 다르므로 href 를 항목마다 들고 다닌다(/lf/ vs /nv/).
  const lf=man.filter(x=>x&&x.kind==="longform")
              .map(x=>({...x, href:"/lf/"+encodeURIComponent(String(x.id))}));
  man.filter(x=>x&&x.kind==="narrate"&&x.mode==="longform").forEach(x=>lf.push({
    ...x, href:"/nv/"+encodeURIComponent(String(x.id))}));
  return sortFeed(lf.map(x=>({...x, no:String(x.id)})));
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
  // ★모든 화면 하단에 빌드 표시 — 화면이 최신인지 눈으로 바로 확인(캐시 혼선 방지).
  try{
    const v=view();
    if(v)v.insertAdjacentHTML("beforeend",
      '<div class="hint" style="text-align:center;opacity:.55;margin:14px 0 4px;font-size:11px">'+BUILD+'</div>');
  }catch(e){}
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
    // ★운영자 수동 지정(운영자 확정): 소스에서 쓸 구간·크롭 위치·컷 전환 수를 직접 정한다.
    //   전부 비우면 지금까지처럼 자동. 자동 판단이 엉뚱할 때(빈 바다·피사체 놓침) 여기서 잡는다.
    '<details class="tok" id="advbox" style="margin-bottom:8px"><summary>고급 설정 — 구간·크롭·컷 직접 지정 (선택)</summary>'+
      '<div class="hint" style="margin:6px 0 8px">비워두면 <b>자동</b>입니다. 영상이 마음에 안 들 때 값을 넣고 다시 제작하세요.</div>'+
      '<span class="lbl">소스에서 쓸 구간 (초) — 예: 12 ~ 40</span>'+
      '<div class="row2" style="margin-bottom:6px">'+
        '<input id="srcStart" placeholder="시작(초) · 비우면 자동" inputmode="decimal" autocomplete="off">'+
        '<input id="srcEnd" placeholder="끝(초) · 비우면 자동" inputmode="decimal" autocomplete="off">'+
      '</div>'+
      '<span class="lbl">크롭 가로 위치 (세로 화면에 담을 부분)</span>'+
      '<select id="cropX" style="margin-bottom:6px">'+
        '<option value="">자동 (피사체 추적)</option>'+
        '<option value="0.15">왼쪽</option>'+
        '<option value="0.35">가운데-왼쪽</option>'+
        '<option value="0.5">정가운데</option>'+
        '<option value="0.65">가운데-오른쪽</option>'+
        '<option value="0.85">오른쪽</option>'+
      '</select>'+
      '<span class="lbl">컷 전환 수 (구도가 바뀌는 횟수)</span>'+
      '<select id="cutsN">'+
        '<option value="">자동 (기본 4컷 = 전환 3회)</option>'+
        '<option value="3">3컷 (전환 2회 · 가장 차분)</option>'+
        '<option value="4">4컷 (전환 3회)</option>'+
        '<option value="5">5컷 (전환 4회)</option>'+
        '<option value="6">6컷 (전환 5회 · 빠름)</option>'+
      '</select>'+
      // ★컷별 구간 직접 지정(운영자 확정): 자동 컷 선택을 완전히 대체한다.
      //   한 줄이라도 채우면 위의 '컷 전환 수'는 무시되고 여기 지정한 컷만 쓴다.
      '<div style="margin-top:12px;border-top:1px solid rgba(255,255,255,.12);padding-top:10px">'+
        // ★원본 미리보기(운영자 확정 B안): 구간 초를 알려면 원본을 봐야 한다 →
        //   여기서 바로 재생하고, 재생 위치를 버튼 한 번으로 컷 칸에 넣는다.
        '<span class="lbl">원본 영상 보기 — 구간을 눈으로 정하세요</span>'+
        '<div class="row2" style="margin-bottom:6px">'+
          '<select id="srcPick" style="flex:2"><option value="">불러오는 중…</option></select>'+
          '<button class="go" id="srcLoad" style="flex:1;margin:0">재생</button>'+
        '</div>'+
        '<div id="srcBox" style="display:none;margin-bottom:8px">'+
          '<video id="srcVid" controls playsinline preload="metadata" '+
                 'style="width:100%;border-radius:10px;background:#000"></video>'+
          '<div class="hint" id="srcInfo" style="margin:6px 0"></div>'+
          '<div class="hint" style="margin:6px 0">영상을 원하는 지점에서 멈춘 뒤, 아래 버튼으로 그 시간을 컷에 넣으세요.</div>'+
          '<div id="srcMarks"></div>'+
        '</div>'+
        '<span class="lbl">컷별 구간 직접 지정 — 원본 영상의 초 단위</span>'+
        '<div class="hint" style="margin:4px 0 8px">한 줄이라도 채우면 <b>여기 지정한 컷만</b> 사용합니다(자동 컷 선택 안 함). '+
          '비워둔 줄은 무시됩니다. 컷 순서 = 영상에 나오는 순서.</div>'+
        [0,1,2,3].map(function(i){return ''+
          '<div class="row2" style="margin-bottom:6px;align-items:center">'+
            '<span class="hint" style="min-width:44px">컷 '+(i+1)+'</span>'+
            '<input id="cs'+i+'a" placeholder="시작(초)" inputmode="decimal" autocomplete="off" style="flex:1">'+
            '<input id="cs'+i+'b" placeholder="끝(초)" inputmode="decimal" autocomplete="off" style="flex:1">'+
            '<select id="cs'+i+'x" style="flex:1">'+
              '<option value="">크롭 자동</option>'+
              '<option value="0.15">왼쪽</option><option value="0.35">가운데-왼쪽</option>'+
              '<option value="0.5">정가운데</option><option value="0.65">가운데-오른쪽</option>'+
              '<option value="0.85">오른쪽</option>'+
            '</select>'+
            '<select id="cs'+i+'m" style="flex:1">'+
              '<option value="">프레이밍 자동</option>'+
              '<option value="fit">전체 담기</option>'+
              '<option value="closeup">접사(줌인)</option>'+
            '</select>'+
          '</div>';}).join('')+
      '</div>'+
    '</details>'+
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
    '<div class="hint" style="margin:4px 0 8px">키워드로 <b>키(API) 없이 직접 다운로드 가능한 무료 영상</b>을 찾아 썸네일·주제와 함께 보여줍니다. 소스: Wikimedia Commons(자유 라이선스) + Internet Archive(안전 필터) + <b>NOAA(미 해양대기청 · 미국 정부 저작물=퍼블릭도메인)</b>. 나레이션에 쓰려면 <b>2차 저작</b>이 가능해야 하므로 <b>변경금지(ND)·비상업(NC)은 제외</b>하고 재사용 가능(PD·CC0·CC BY·CC BY-SA)만 <span style="color:#7CFC9B">안전</span>으로 표시합니다. 최종 사용 전 원본 페이지에서 권리를 확인하세요.</div>'+
    '<div class="row2" style="margin-bottom:6px"><input id="vsq" placeholder="검색어 (예: deep sea anglerfish, jellyfish, shipwreck)" style="flex:2">'+
      '<select id="vssrc" style="flex:1"><option value="all">전체</option><option value="noaa">NOAA만</option><option value="commons">커먼스만</option><option value="archive">아카이브만</option></select></div>'+
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
  '<div class="card"><span class="lbl">실행 현황 <a href="#" id="refresh" style="color:var(--cy);float:right;text-decoration:none">새로고침</a></span>'+
    '<div class="runs" id="runs"><div class="hint">불러오는 중…</div></div></div>';

  // ── 원본 미리보기(컷 구간을 눈으로 정하기) ────────────────────────────────
  //   소싱 캐시(_video_cache.json)에 종별 원본 URL이 들어 있다. 그걸 목록으로 띄우고,
  //   고른 영상을 그대로 재생 → 재생 위치를 버튼으로 컷 칸에 채운다.
  //   ※ 화면에 보이는 초 = 파이프라인이 쓰는 초와 동일(원본 기준)이라 그대로 넣으면 맞는다.
  let SRC_CACHE=null;
  const fmt=t=>{t=Math.max(0,t||0);const m=Math.floor(t/60),sec=t-m*60;
    return m+":"+(sec<10?"0":"")+sec.toFixed(1);};
  // ★재생 호환(중요): 커먼스 원본은 대부분 **VP8 webm**이라 iOS 사파리에서 재생이 안 된다.
  //   커먼스가 자동 생성하는 **480p VP9 트랜스코드**는 iOS 14+에서 재생되고 용량도 훨씬 작다.
  //   원본: .../commons/5/5e/X.webm → 트랜스코드: .../commons/transcoded/5/5e/X.webm/X.webm.480p.vp9.webm
  //   실패하면 원본으로 자동 폴백한다(둘 다 안 되면 '원본 링크'로 안내).
  function transcodeUrl(u){
    try{
      if(!/^https:\\/\\/upload\\.wikimedia\\.org\\/wikipedia\\/commons\\//.test(u)) return "";
      if(/\\/transcoded\\//.test(u)) return "";
      if(!/\\.(webm|ogv)$/i.test(u)) return "";
      const name=u.split("/").pop();
      return u.replace("/commons/","/commons/transcoded/")+"/"+name+".480p.vp9.webm";
    }catch(e){return "";}
  }
  async function loadSrcList(){
    const sel=$("#srcPick"); if(!sel) return;
    try{
      const t=await fetchRaw("short-movie-generator/src/categories/_video_cache.json", true);
      SRC_CACHE=t?JSON.parse(t):{};
    }catch(e){SRC_CACHE={};}
    const keys=Object.keys(SRC_CACHE||{}).sort();
    if(!keys.length){sel.innerHTML='<option value="">확보된 원본이 없습니다 — 먼저 소싱하세요</option>';return;}
    // 입력한 대상과 이름이 겹치는 항목을 맨 위로(그대로 '재생'만 누르면 되게)
    const q=(($("#query")||{}).value||"").trim().toLowerCase();
    keys.sort((a,b)=>((q&&b.includes(q))?1:0)-((q&&a.includes(q))?1:0));
    sel.innerHTML=keys.map(k=>{
      const v=SRC_CACHE[k]||{};
      return '<option value="'+esc(k)+'">'+esc(k)+' — '+esc((v.credit||v.source||"").slice(0,40))+'</option>';
    }).join("");
  }
  function renderMarkButtons(){
    const box=$("#srcMarks"); if(!box) return;
    box.innerHTML=[0,1,2,3].map(function(i){return ''+
      '<div class="row2" style="margin-bottom:4px;align-items:center">'+
        '<span class="hint" style="min-width:44px">컷 '+(i+1)+'</span>'+
        '<button class="go" data-mk="'+i+'a" style="flex:1;margin:0;padding:8px">여기를 시작으로</button>'+
        '<button class="go" data-mk="'+i+'b" style="flex:1;margin:0;padding:8px">여기를 끝으로</button>'+
      '</div>';}).join("");
    box.querySelectorAll("[data-mk]").forEach(function(btn){
      btn.onclick=function(){
        const v=$("#srcVid"); if(!v) return;
        const t=Math.round((v.currentTime||0)*10)/10;
        const el=$("#cs"+btn.dataset.mk);
        if(el){el.value=String(t);
          banner("컷 "+(parseInt(btn.dataset.mk)+1)+" "+(btn.dataset.mk.endsWith("a")?"시작":"끝")+" = "+t+"초","ok");}
      };
    });
  }
  const _sl=$("#srcLoad");
  if(_sl)_sl.onclick=async()=>{
    const key=(($("#srcPick")||{}).value||"");
    const rec=(SRC_CACHE||{})[key];
    if(!rec||!rec.url){banner("원본 URL을 찾지 못했습니다. 먼저 '소싱하기'를 실행하세요.","err");return;}
    const v=$("#srcVid"), box=$("#srcBox");
    const tc=transcodeUrl(rec.url);
    let triedOriginal=!tc;
    const meta="출처: <b>"+esc(rec.credit||"-")+"</b> · 라이선스 "+esc(rec.license||"-")+
      ' · <a href="'+esc(rec.url)+'" target="_blank" style="color:var(--cy)">원본 링크</a>';
    v.src=prox(tc||rec.url); box.style.display="";
    $("#srcInfo").innerHTML=meta;
    v.onloadedmetadata=()=>{
      // ※여기 보이는 초 = 제작 파이프라인이 쓰는 초와 동일(원본 기준 타임라인)이라 그대로 넣으면 맞다.
      $("#srcInfo").innerHTML=meta+" · 길이 <b>"+fmt(v.duration)+"</b> ("+v.duration.toFixed(1)+"초)";
    };
    v.onerror=()=>{
      if(!triedOriginal){                 // 트랜스코드 실패 → 원본으로 폴백
        triedOriginal=true; v.src=prox(rec.url); v.load(); return;
      }
      banner("이 브라우저가 원본 형식(webm 등)을 재생하지 못합니다. 위 '원본 링크'로 열어 시간을 확인하세요.","err");
    };
    renderMarkButtons();
  };
  const _ab=$("#advbox"); if(_ab) _ab.addEventListener("toggle",()=>{ if(_ab.open&&!SRC_CACHE) loadSrcList(); });

  const _sp=$("#savepat");if(_sp)_sp.onclick=()=>{const v=$("#pat").value.trim();if(!v)return;
    localStorage.setItem("gh_pat",v);$("#pat").value="";const tb=$("#tokbox");if(tb)tb.open=false;banner("토큰 저장 완료. 다시 묻지 않습니다.","ok");};
  $("#go").onclick=async()=>{
    const category=($("#category")||{}).value||"deep_sea";
    // 심해가 아니면 세부 auto:* 는 의미 없음 → 그냥 auto
    let query=$("#query").value.trim()||$("#species").value;
    if(category!=="deep_sea" && query.startsWith("auto:")) query="auto";
    if(!authReady()){const tb=$("#tokbox");if(tb)tb.open=true;banner("GitHub 토큰을 아래 칸에 붙여넣고 생성을 누르면 이 기기에 저장돼 다시 묻지 않습니다.","err");return;}
    // ★고급 설정(선택): 값이 있는 것만 워크플로 inputs로 넘긴다(빈 값은 백엔드에서 '자동').
    const v=id=>(($("#"+id)||{}).value||"").trim();
    const inputs={query,category};
    for(const [k,id] of [["src_start","srcStart"],["src_end","srcEnd"],["crop_x","cropX"],["cuts","cutsN"]]){
      const val=v(id); if(val) inputs[k]=val;
    }
    // ★컷별 구간: 시작·끝이 둘 다 채워진 줄만 모아 JSON으로 넘긴다(자동 컷 선택 대체).
    const specs=[];
    for(let i=0;i<4;i++){
      const a=v("cs"+i+"a"), b=v("cs"+i+"b");
      if(!a||!b) continue;
      const o={start:parseFloat(a), end:parseFloat(b)};
      if(!(o.end>o.start)) continue;
      const cx=v("cs"+i+"x"); if(cx) o.crop_x=parseFloat(cx);
      const md=v("cs"+i+"m"); if(md) o.mode=md;
      specs.push(o);
    }
    if(specs.length) inputs.cut_specs=JSON.stringify(specs);
    const manualNote=[inputs.src_start||inputs.src_end?("구간 "+(inputs.src_start||"0")+"~"+(inputs.src_end||"끝")+"초"):"",
                      inputs.crop_x?("크롭 "+inputs.crop_x):"", inputs.cuts?(inputs.cuts+"컷"):"",
                      specs.length?("컷 직접지정 "+specs.length+"개"):""].filter(Boolean).join(" · ");
    $("#go").disabled=true;banner("생성 요청 중…"+(manualNote?(" ("+manualNote+")"):""));
    try{const r=await fetch(API+"/actions/workflows/"+WF+"/dispatches",{method:"POST",headers:headers(true),
        body:JSON.stringify({ref:BRANCH,inputs})});
      if(r.status===204){banner("생성 시작! 2~4분 뒤 텔레그램 전송 + 라이브러리 등록.","ok");setTimeout(loadRuns,4000);setTimeout(loadRuns,12000);}
      else{const t=await r.text();banner("실패("+r.status+"): 토큰 권한(Actions)을 확인하세요.<br><span class='mono' style='font-size:11px'>"+esc(t.slice(0,140))+"</span>","err");}
    }catch(e){banner("요청 실패: "+e,"err");}
    $("#go").disabled=false;};
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
  loadNarrateResults();
}
function srcbanner(t,c){const m=$("#srcmsg");if(m){m.className="banner show "+(c||"");m.innerHTML=t;}}
function nvbanner(t,c){const m=$("#nvmsg");if(m){m.className="banner show "+(c||"");m.innerHTML=t;}}
// 첨부 영상을 GitHub Release(태그 NV_TAG) 에셋으로 올리고 공개 다운로드 URL을 돌려준다.
// 워크플로가 이 URL을 urllib로 받아 나레이션을 입힌다(공개 저장소라 무인증 접근 가능).
async function uploadToRelease(file){
  // 0) 크기 가드 — Cloudflare Workers 무료 요청 본문 상한(≈100MB).
  if(file&&file.size>95*1024*1024)
    throw new Error("파일이 100MB를 넘습니다("+Math.round(file.size/1048576)+"MB). 아래 URL 칸에 직접 다운로드 링크를 붙여넣어 주세요(대용량은 워커 업로드 제한).");
  // 1) 릴리스 확보(api.github.com은 CORS 허용 → 브라우저 직접).
  let rel=null;
  const g=await fetch(API+"/releases/tags/"+NV_TAG,{headers:headers(true)});
  if(g.ok)rel=await g.json();
  else if(g.status===404){
    const c=await fetch(API+"/releases",{method:"POST",headers:{...headers(true),"Content-Type":"application/json"},
      body:JSON.stringify({tag_name:NV_TAG,name:"첨부 영상 입력",target_commitish:BRANCH,
        body:"첨부 영상 나레이션용 입력 파일 보관(자동 생성)"})});
    if(c.ok)rel=await c.json();
    else{const t=await c.text();throw new Error("릴리스 생성 실패("+c.status+") — 토큰에 Contents: Read and write 권한이 필요합니다. "+t.slice(0,100));}
  }else{const t=await g.text();throw new Error("릴리스 조회 실패("+g.status+"). "+t.slice(0,100));}
  if(!rel||!rel.id)throw new Error("릴리스 정보를 얻지 못했습니다.");
  // 2) 에셋 업로드 — 항상 워커 중계(uploads.github.com은 CORS 미지원 → 브라우저 직접 업로드 차단).
  const ext=((file.name||"").split(".").pop()||"mp4").toLowerCase().replace(/[^a-z0-9]/g,"")||"mp4";
  const name="attach_"+Date.now()+"."+ext;
  const ctype=file.type||"application/octet-stream";
  const hdr={"Content-Type":ctype};
  if(!SERVER&&pat())hdr["Authorization"]="Bearer "+pat();   // 같은 출처 워커에만 전달
  const up=await fetch("/api/ghupload?release_id="+rel.id+"&name="+encodeURIComponent(name)+"&ctype="+encodeURIComponent(ctype),
    {method:"POST",headers:hdr,body:file});
  if(!up.ok){const t=await up.text();throw new Error("업로드 실패("+up.status+") — 토큰 권한(Contents: Read and write) 또는 파일 크기를 확인하세요. "+t.slice(0,100));}
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
      try{ videoUrl=await uploadToRelease(file); }
      catch(e){ nvbanner("영상 업로드 실패 — "+esc(String(e&&e.message||e)),"err"); btn.disabled=false; return; }
      if(!videoUrl){nvbanner("영상 업로드 실패(원인 불명). 잠시 후 다시 시도하세요.","err");btn.disabled=false;return;}
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
async function renderNarrateDetail(id,fresh){
  view().innerHTML='<a class="back" href="/">← 제작 페이지</a><div class="card" id="nvcard"><div class="hint">불러오는 중…</div></div>';
  const rec=await fetchRecord(id,fresh);
  const dc=document.getElementById("nvcard");
  if(!rec){dc.innerHTML='<div class="hint">이 나레이션 기록을 찾을 수 없습니다(아직 제작 중이거나 완료 전).</div>'+
      '<div class="btnrow" style="margin-top:14px"><a class="btn" href="/">← 제작 페이지로</a></div>';return;}
  const md=rec.media||{};
  const mediaHtml=md.video_url?('<video id="nvout" src="'+prox(md.video_url)+'" controls playsinline preload="metadata"></video>'):"";
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
    // ★더빙 대본 검수(운영자 확정): 원본 화자 발화를 전사→일본어 번역한 대본을 표로 보여주고,
    //   어색한 '일본어' 줄을 고쳐 '수정 대본으로 재제작'하면 그 대본으로 발화 시각에 맞춰 다시 더빙한다.
    ((Array.isArray(rec.transcript)&&rec.transcript.length)?(
      '<div class="card" style="margin-top:12px">'+
        '<span class="lbl">더빙 대본 검수 (원문 → 일본어)</span>'+
        '<div class="hint" style="margin:4px 0 8px">원본 화자의 말을 <b>그 시각에 맞춰</b> 일본어로 더빙합니다. <b>일본어 칸만</b> 고치세요(시간·정렬은 자동). 다 고쳤으면 아래 <b>수정 대본으로 재제작</b>.</div>'+
        '<div id="trlist">'+ rec.transcript.map((s,i)=>(
          '<div class="trrow" style="display:grid;grid-template-columns:52px 1fr 1fr;gap:6px;margin-bottom:6px;align-items:start">'+
            '<span class="mono" style="font-size:11px;color:#89a;padding-top:6px">'+esc(vsDur(s.start||0))+'</span>'+
            '<textarea class="tro" readonly rows="2" style="font-size:12px;opacity:.75">'+esc(s.orig||"")+'</textarea>'+
            '<textarea class="trj" rows="2" data-start="'+(Number(s.start)||0)+'" data-end="'+(Number(s.end)||0)+'" style="font-size:12px">'+esc(s.jp||"")+'</textarea>'+
          '</div>')).join('')+'</div>'+
        (rec.source_url?'<button class="btn save" id="nvdub" style="margin-top:8px">수정 대본으로 재제작</button>':'<div class="hint">원본 URL이 없어 재제작 불가</div>')+
      '</div>'):'')+
    // ★유튜브 업로드(운영자 확정): 영상 확인 후 클릭 시에만 upload-longform.yml 디스패치(자동 업로드 없음).
    //   이미 업로드된 레코드는 링크만 표시(중복 업로드 방지 — 워크플로도 2중 가드).
    (md.youtube_url?(
      '<div class="card" style="margin-top:12px"><span class="lbl">유튜브</span>'+
        '<div class="hint" style="margin:4px 0 6px">이미 유튜브에 업로드된 영상입니다.</div>'+
        '<a class="btn save" href="'+esc(md.youtube_url)+'" target="_blank">유튜브에서 보기 → '+esc(md.youtube_url)+'</a></div>'
    ):(md.video_url?(
      '<div class="card" style="margin-top:12px"><span class="lbl">유튜브에 올리기</span>'+
        '<div class="hint" style="margin:4px 0 8px">위 영상·제목·설명을 확인한 뒤 올리세요. 제목·설명·해시태그(일본어)가 그대로 사용됩니다.</div>'+
        '<div class="row2" style="margin-bottom:8px"><select id="nvpriv" style="flex:1">'+
          '<option value="public">공개</option><option value="unlisted">일부공개(링크 공유)</option><option value="private">비공개</option>'+
        '</select></div>'+
        '<button class="btn save" id="nvup">유튜브에 올리기</button></div>'
    ):''))+
    // ★관리(운영자 확정): 이 나레이션 영상을 원본 그대로 다시 제작(재생성)하거나 영구 삭제.
    '<div class="card" style="margin-top:12px">'+
      '<span class="lbl">이 나레이션 영상 관리</span>'+
      '<div class="btnrow" style="margin-top:8px;display:grid;grid-template-columns:1fr 1fr;gap:8px">'+
        '<button class="btn" id="nvtitle">제목 재생성 (썸네일 포함)</button>'+
        '<button class="btn" id="nvdesc">설명 재생성</button>'+
        (rec.source_url?'<button class="btn" id="nvthumb">썸네일만 재생성</button>':'<button class="btn" id="nvthumb" disabled title="원본 URL 없음">썸네일 재생성 불가</button>')+
        (rec.source_url?'<button class="btn" id="nvregen">전체 다시 제작(재생성)</button>':'<button class="btn" id="nvregen" disabled title="원본 URL 없음">재생성 불가</button>')+
        // ★결과를 보고 구간을 다시 잡는 패널(운영자 확정 "일단 만들고 내가 고치기").
        //   원본을 여기서 재생하고, 원하는 지점에서 버튼을 눌러 컷 구간을 채운 뒤 재제작한다.
        (rec.source_url?(
          // ★전체 폭(grid-column:1/-1): 2열 그리드 안이라 절반 폭으로 찌그러져 아이폰에서 글자가
          //   세로로 쪼개졌다(운영자 지적). 편집 카드는 반드시 한 줄 전체를 차지한다.
          '<div class="card" id="nvcutbox" style="grid-column:1/-1;margin-top:10px;border:1px solid var(--cy)">'+
            '<span class="lbl" style="color:var(--cy)">구간·줌 직접 지정 — 내가 정해서 다시 만들기</span>'+
            cutEditorHTML("nc")+
            '<button class="btn save" id="ncgo" style="margin-top:8px">이 설정으로 다시 만들기 (같은 회차 덮어쓰기)</button>'+
          '</div>'
        ):'')+
        '<button class="btn" id="nvdel" style="background:#8b1a1a;color:#fff;grid-column:1/-1">이 영상 삭제 (영구)</button></div>'+
      '<div class="hint" style="margin-top:6px">'+
        '<b>구간·줌 다시 잡기</b>는 원본을 보며 컷 구간·줌 배율·크롭 위치를 직접 정해 <b>같은 회차에 덮어써</b> 다시 만듭니다(5~15분). '+
        '<b>제목 재생성</b>은 대본으로 제목·훅을 다시 만들고 <b>썸네일도 새 제목으로 함께</b> 다시 그립니다(2~5분 · 영상 유지'+(rec.source_url?'':' · 원본 URL이 없어 이 건은 텍스트만 갱신')+'). '+
        '<b>설명 재생성</b>은 설명·해시태그만 다시 만듭니다(1~2분 · 타임스탬프 목차 유지). '+
        '<b>썸네일만 재생성</b>은 문구는 그대로 두고 배경 장면만 다시 고릅니다(2~5분). '+
        (rec.source_url?'전체 재생성은 <b>같은 원본</b>으로 처음부터 다시 만듭니다(5~15분). ':'')+
        '삭제는 영상·기록을 되돌릴 수 없이 지웁니다.</div></div>'+
    '<div class="banner" id="msg" style="margin-top:10px"></div>';
  const V=s=>((document.getElementById(s)||{}).value||"");
  const B=(id2,src,msg)=>{const b=document.getElementById(id2);if(b)b.onclick=()=>copyText(V(src),msg);};
  B("nvcptj","nvtj","일본어 제목을 복사했어요.");B("nvcptk","nvtk","한국어 제목을 복사했어요.");
  B("nvcpdj","nvdj","일본어 설명을 복사했어요.");B("nvcpdk","nvdk","한국어 설명을 복사했어요.");
  B("nvcphj","nvhj","일본어 해시태그를 복사했어요.");B("nvcphk","nvhk","한국어 해시태그를 복사했어요.");
  if(md.video_url){const bd=document.getElementById("bdl");if(bd)bd.onclick=()=>saveVideo(prox(md.video_url),id+".mp4");}
  if(md.thumb_url){const th=document.getElementById("thdl");if(th)th.onclick=()=>saveVideo(prox(md.thumb_url),id+"_thumb.jpg",{btn:"#thdl",hint:"#thhint",mime:"image/jpeg",kind:"이미지"});}
  const rgn=document.getElementById("nvregen");
  if(rgn&&rec.source_url)rgn.onclick=()=>regenNarrate(id,rec.source_url,rec.mode||"shorts");
  // ★구간·줌 다시 잡기(공용 패널): 미리보기 mp4 → 커먼스 트랜스코드 → 원본 순으로 재생하고,
  //   지정한 컷·줌·크롭으로 **같은 회차에 덮어써** 다시 만든다(운영자 확정).
  const _cb=$("#nvcutbox");
  if(_cb&&rec.source_url){
    // ★필요한 총 길이: 제작 때 남긴 본문 길이(body_dur)를 쓰고, 옛 회차라 값이 없으면
    //   완성 영상 길이에서 오프닝 훅(약 4.6초)을 빼서 어림값이라도 보여준다(0으로 두지 않는다).
    const _out=document.getElementById("nvout");
    if(!(rec.body_dur||md.body_dur)&&_out)_out.onloadedmetadata=()=>{
      const st=ceState("nc"); st.need=Math.max(1,Math.round(((_out.duration||0)-4.6)*10)/10); ceRender("nc");};
    bindCutEditor("nc", {sheet: md.sheet||null,
                         srcs: [md.source_mp4_url, nvTranscode(rec.source_url), rec.source_url],
                         need: rec.body_dur||md.body_dur||0}, ()=>{
      const inp=cutEditorInputs("nc");
      if(!Object.keys(inp).length){banner("컷 구간·줌·크롭 중 최소 하나는 지정하세요.","err");return;}
      regenNarrate(id,rec.source_url,rec.mode||"shorts",inp);
    });
  }
  const dub=document.getElementById("nvdub");
  if(dub&&rec.source_url)dub.onclick=()=>regenNarrateDub(id,rec.source_url,rec.mode||"longform");
  const nvu=document.getElementById("nvup");if(nvu)nvu.onclick=()=>uploadNarrate(id);
  const nvti=document.getElementById("nvtitle");
  if(nvti)nvti.onclick=()=>regenNarratePartial(id,rec.source_url||"-",rec.mode||"longform","title","nvtitle","제목(+썸네일)");
  const nvde=document.getElementById("nvdesc");
  if(nvde)nvde.onclick=()=>regenNarratePartial(id,rec.source_url||"-",rec.mode||"longform","desc","nvdesc","설명");
  const nvt=document.getElementById("nvthumb");
  if(nvt&&rec.source_url)nvt.onclick=()=>regenNarratePartial(id,rec.source_url,rec.mode||"longform","thumb","nvthumb","썸네일");
  const nvd=document.getElementById("nvdel");if(nvd)nvd.onclick=()=>deleteContent(id,"narrate");
}

// 나레이션 부분 재생성(영상 유지): scope=meta(제목·설명) | thumb(썸네일) — narrate-video.yml 디스패치.
async function regenNarratePartial(id,sourceUrl,mode,scope,btnId,label){
  if(!authReady()){banner("재생성에는 GitHub 토큰(Actions: Read and write)이 필요합니다.","err");return;}
  const mins=(scope==="thumb"||scope==="title")?"2~5분":"1~2분";
  if(!confirm(label+"만 다시 만듭니다(영상은 그대로).\\n\\n완료되면 이 화면이 자동으로 갱신됩니다(약 "+mins+").\\n계속할까요?"))return;
  const b=document.getElementById(btnId); if(b){b.disabled=true;b.textContent=label+" 재생성 중…";}
  // ★현행화(운영자 지적): 재생성 완료 즉시 반영. 시작 시점의 updated_at을 스냅샷 → 레코드가 갱신되면
  //   자동으로 화면을 다시 그린다(수동 새로고침 불필요 · raw 캐시는 fresh 조회로 우회).
  const before=(await fetchRecord(id,true)||{}).updated_at||"";
  banner(label+" 재생성을 시작합니다… 완료되면 자동으로 갱신됩니다.");
  try{
    const r=await fetch(API+"/actions/workflows/"+NV_WF+"/dispatches",{method:"POST",headers:headers(true),
      body:JSON.stringify({ref:BRANCH,inputs:{video_url:(sourceUrl||"-"),mode:(mode||"longform"),
        content_id:String(id),scope:scope}})});
    if(r.status===204){banner(label+" 재생성 시작! 완료되면 이 화면이 자동으로 갱신됩니다(약 "+mins+").","ok");
      pollNarrateUpdate(id,before,label);}
    else{const t=await r.text();banner("시작 실패("+r.status+")<br><span class='mono' style='font-size:11px'>"+esc(t.slice(0,140))+"</span>","err");
      if(b){b.disabled=false;b.textContent=label+" 재생성";}}
  }catch(e){banner("오류: "+e,"err");if(b){b.disabled=false;b.textContent=label+" 재생성";}}
}

// 재생성 완료 자동 감지 → 화면 갱신. 시작 시점 updated_at과 달라지면(=새 커밋 반영) 상세를 다시 그린다.
// raw CDN 지연을 피하려 항상 fresh 조회. 최대 ~12분(15초 간격) 폴링 후 종료(수동 새로고침 안내).
async function pollNarrateUpdate(id,before,label){
  let tries=0; const max=48;
  const timer=setInterval(async()=>{
    tries++;
    // 현재 상세 화면이 이 id가 아니면(다른 곳으로 이동) 폴링 중단
    if(!location.pathname.startsWith("/nv/")){clearInterval(timer);return;}
    let rec=null; try{rec=await fetchRecord(id,true);}catch(e){}
    if(rec&&(rec.updated_at||"")&&rec.updated_at!==before){
      clearInterval(timer);
      banner((label||"내용")+" 재생성 완료 — 화면을 갱신했습니다.","ok");
      renderNarrateDetail(id,true);
      return;
    }
    if(tries>=max){clearInterval(timer);
      banner("아직 처리 중일 수 있습니다. 잠시 뒤 새로고침해 주세요.","err");}
  },15000);
}

// 나레이션 영상 유튜브 '수동' 업로드 — 롱폼과 같은 upload-longform.yml 디스패치(레코드 kind로 분기).
async function uploadNarrate(id){
  if(!authReady()){banner("유튜브 업로드에는 GitHub 토큰(Actions: Read and write)이 필요합니다.","err");return;}
  const priv=(document.getElementById("nvpriv")||{}).value||"public";
  const nm={public:"공개",unlisted:"일부공개",private:"비공개"}[priv]||priv;
  if(!confirm("이 영상을 유튜브에 '"+nm+"'로 올릴까요? 확인을 누르면 업로드가 시작됩니다."))return;
  const b=document.getElementById("nvup"); if(b){b.disabled=true;b.textContent="업로드 시작 중…";}
  banner("유튜브 업로드를 시작합니다… (1~3분 뒤 새로고침하면 링크가 표시됩니다)");
  try{
    const r=await fetch(API+"/actions/workflows/"+UP_WF+"/dispatches",{method:"POST",headers:headers(true),
      body:JSON.stringify({ref:BRANCH,inputs:{content_id:String(id),privacy:priv}})});
    if(r.status===204)banner("업로드 시작! 1~3분 뒤 이 화면을 새로고침하면 유튜브 링크가 표시됩니다.","ok");
    else{const t=await r.text();banner("업로드 시작 실패("+r.status+")<br><span class='mono' style='font-size:11px'>"+esc(t.slice(0,140))+"</span>","err");
      if(b){b.disabled=false;b.textContent="유튜브에 올리기";}}
  }catch(e){banner("업로드 오류: "+e,"err");if(b){b.disabled=false;b.textContent="유튜브에 올리기";}}
}

// 더빙 대본 재제작: 화면의 수정된 일본어 대본(원문·시각 유지)을 모아 narrate-video.yml에 transcript로
// 넘겨, 전사·번역을 건너뛰고 그 대본으로 원본 발화 시각에 맞춰 다시 더빙한다(같은 /nv/<id> 갱신).
async function regenNarrateDub(id,sourceUrl,mode){
  if(!authReady()){banner("재제작에는 GitHub 토큰(Actions: Read and write)이 필요합니다.","err");return;}
  if(!sourceUrl){banner("원본 URL 정보가 없어 재제작할 수 없습니다.","err");return;}
  const rows=[...document.querySelectorAll('#trlist .trrow')];
  const tr=rows.map(row=>{
    const j=row.querySelector('.trj'),o=row.querySelector('.tro');
    return {start:parseFloat(j&&j.dataset.start)||0,end:parseFloat(j&&j.dataset.end)||0,
            orig:(o?o.value:""),jp:((j?j.value:"")||"").trim()};
  }).filter(x=>x.jp);
  if(!tr.length){banner("일본어 대본이 비어 있습니다.","err");return;}
  if(!confirm("수정한 더빙 대본으로 이 영상을 다시 제작합니다.\\n\\n원본 발화 시각에 맞춰 다시 더빙하고 같은 화면(주소)이 갱신됩니다(5~15분).\\n계속할까요?"))return;
  banner("수정 대본으로 재제작 요청 중… (5~15분)");
  try{
    const r=await fetch(API+"/actions/workflows/"+NV_WF+"/dispatches",{method:"POST",headers:headers(true),
      body:JSON.stringify({ref:BRANCH,inputs:{video_url:sourceUrl,mode:(mode||"longform"),
        content_id:String(id),transcript:JSON.stringify(tr)}})});
    if(r.status===204)banner("재제작 시작! 5~15분 뒤 이 화면을 새로고침하면 수정 대본이 반영됩니다.","ok");
    else{const t=await r.text();banner("재제작 시작 실패("+r.status+")<br><span class='mono' style='font-size:11px'>"+esc(t.slice(0,140))+"</span>","err");}
  }catch(e){banner("재제작 오류: "+e,"err");}
}

// 나레이션 영상 재생성: 같은 원본 URL·형태로 narrate-video.yml을 디스패치하되 content_id를 넘겨
// 같은 레코드(같은 /nv/<id>)를 덮어쓴다(영상·썸네일·메타 갱신).
// 커먼스 webm은 iOS에서 재생이 안 돼 480p VP9 트랜스코드를 우선 시도한다(제작 화면과 동일 규칙).
function nvTranscode(u){
  try{
    if(!/^https:\\/\\/upload\\.wikimedia\\.org\\/wikipedia\\/commons\\//.test(u)) return "";
    if(/\\/transcoded\\//.test(u)) return "";
    if(!/\\.(webm|ogv)$/i.test(u)) return "";
    return u.replace("/commons/","/commons/transcoded/")+"/"+u.split("/").pop()+".480p.vp9.webm";
  }catch(e){return "";}
}
// ★★컷 편집기(운영자 확정 · 도감형/나레이션형 공용) — 손가락으로 '잘라낼 사각형'을 정한다.
//   설계 근거(운영자): "화면 비율이 정해져 있으니 줌과 크롭은 기능을 합쳐도 된다. 캡처 이미지를
//   보고 어디를 잘라낼지 손가락으로 고르게 해달라." → **9:16 사각형 하나 = 줌(크기) + 크롭(위치)**.
//   또 "컷마다 줌 비율이 다를 수 있다" → **컷 1~4를 각각 따로** 정한다.
//   ★영상 재생에 의존하지 않는다: 원본 대부분이 WebM이라 아이폰에서 재생이 안 돼 '여기 시작'
//     버튼이 0초만 입력되던 문제가 있었다. 그래서 **프레임 사진(스트립)** 을 탭해 구간을 고른다.
const CUTN=4;
const _ce={};   // pfx별 상태: {sheet, need, srcDur, cuts:[{box:{x,y,w}}], sel}
function ceState(pfx){ return (_ce[pfx] ||= {sheet:null, sel:0, need:0, srcDur:0,
  cuts:Array.from({length:CUTN},()=>({box:{x:0.5,y:0.5,w:0.6}}))}); }

// ★아이폰 최적화(운영자 지적 "너무 좁게 표현된다"): 편집 카드가 2열 그리드 안에 들어가 절반 폭으로
//   찌그러져 한글이 세로로 한 글자씩 쪼개졌다 → 카드는 항상 **전체 폭**(grid-column:1/-1)에 두고,
//   버튼은 nowrap · 높이 44px 이상(엄지 터치), 입력칸은 큰 글씨로.
const CE_BTN="flex:1;min-width:0;white-space:nowrap;min-height:44px;font-size:14px";
const CE_INP="flex:1;min-width:0;height:44px;font-size:16px;text-align:center";
function cutEditorHTML(pfx){
  let rows='';
  for(let i=0;i<CUTN;i++){
    rows+='<div id="'+pfx+'row'+i+'" data-cerow="'+i+'" style="border:1px solid #24405a;border-radius:10px;padding:8px;margin-bottom:8px">'+
      '<div style="display:flex;gap:6px;align-items:center">'+
        '<b style="min-width:42px;font-size:15px">컷 '+(i+1)+'</b>'+
        '<input id="'+pfx+i+'a" placeholder="시작(초)" inputmode="decimal" style="'+CE_INP+'">'+
        '<span class="hint">~</span>'+
        '<input id="'+pfx+i+'b" placeholder="끝(초)" inputmode="decimal" style="'+CE_INP+'">'+
      '</div>'+
      '<div style="display:flex;gap:6px;margin-top:6px">'+
        '<button class="mini" data-mk="'+pfx+i+'a" style="'+CE_BTN+'">여기 시작</button>'+
        '<button class="mini" data-mk="'+pfx+i+'b" style="'+CE_BTN+'">여기 끝</button>'+
        '<button class="mini" data-cesel="'+i+'" style="'+CE_BTN+'">잘라낼 곳</button>'+
      '</div></div>';
  }
  return ''+
    '<div class="hint" style="margin:6px 0 8px">① 원본을 재생하다가 <b>여기 시작 / 여기 끝</b>을 누르면 그 컷의 칸에 <b>초가 채워집니다</b>(사진 띠를 탭해도 됩니다). '+
      '② <b>잘라낼 곳</b>을 누르면 그 컷의 화면이 아래에 뜹니다 — <b>사각형을 손가락으로 옮기고 크기를 바꿔</b> 잘라낼 부분을 정하세요.</div>'+
    '<video id="'+pfx+'vid" controls playsinline preload="metadata" style="width:100%;border-radius:10px;background:#000"></video>'+
    '<div class="hint" id="'+pfx+'info" style="margin:6px 0"></div>'+
    '<div id="'+pfx+'need" style="margin:6px 0;padding:8px;border-radius:8px;background:#0e1a26;font-size:14px"></div>'+
    '<div class="hint" style="margin:6px 0 2px">사진 띠 — 탭하면 시작, 한 번 더 탭하면 끝이 채워집니다</div>'+
    '<div id="'+pfx+'strip" style="display:flex;overflow-x:auto;gap:6px;padding:4px 0;-webkit-overflow-scrolling:touch">'+
      '<div class="hint">프레임 사진 불러오는 중…</div></div>'+
    rows+
    '<div class="hint" style="margin:8px 0 2px">잘라낼 부분 — 사각형을 끌어 옮기고, 아래 막대로 크기(줌)를 바꿉니다</div>'+
    '<div id="'+pfx+'stage" style="position:relative;width:100%;background:#000;border-radius:10px;overflow:hidden;touch-action:none">'+
      '<img id="'+pfx+'frame" style="width:100%;display:block;opacity:.85">'+
      '<div id="'+pfx+'box" style="position:absolute;border:2px solid var(--cy);box-shadow:0 0 0 9999px rgba(0,0,0,.45);border-radius:4px"></div>'+
    '</div>'+
    '<input id="'+pfx+'zoom" type="range" min="30" max="100" value="60" style="width:100%;height:44px;margin:8px 0">'+
    '<div class="hint" id="'+pfx+'box_info" style="margin:2px 0"></div>';
}

// 프레임 사진 시트(소싱이 만든 contact sheet)를 읽어 스트립을 그린다.
async function ceLoadSheet(pfx, sheet){
  const st=ceState(pfx); st.sheet=sheet;
  const strip=document.getElementById(pfx+"strip"); if(!strip) return;
  if(!sheet){ strip.innerHTML='<div class="hint">프레임 사진이 아직 없습니다 — <b>소싱하기</b>를 한 번 돌리면 만들어집니다. '+
    '그동안은 아래 칸에 초를 직접 입력해도 됩니다.</div>'; return; }
  const cell=Math.round(100/sheet.cols*10)/10;
  let h='';
  for(let k=0;k<sheet.n;k++){
    const cx=k%sheet.cols, cy=Math.floor(k/sheet.cols);
    h+='<div data-cetile="'+k+'" style="flex:0 0 auto;width:84px;height:'+Math.round(84*sheet.th/sheet.tw)+'px;'+
       'background-image:url('+prox(sheet.url)+');background-size:'+(sheet.cols*100)+'% '+(sheet.rows*100)+'%;'+
       'background-position:'+(sheet.cols>1?(cx*100/(sheet.cols-1)):0)+'% '+(sheet.rows>1?(cy*100/(sheet.rows-1)):0)+'%;'+
       'border-radius:6px;border:2px solid transparent"></div>';
  }
  strip.innerHTML=h;
  strip.querySelectorAll("[data-cetile]").forEach(el=>{el.onclick=()=>ceTapTile(pfx, parseInt(el.dataset.cetile));});
  ceShowFrame(pfx);
}
// ★칸이 곧 값이다(운영자 지적 "여기 시작을 눌러도 칸이 안 채워진다"): 시작·끝은 **입력칸**에만
//   담고, 사진 탭·버튼·직접 입력이 모두 같은 칸을 채운다(값이 눈에 보이지 않는 상태를 없앤다).
function ceVal(pfx,i,f){
  const el=document.getElementById(pfx+i+f);
  const v=parseFloat(((el||{}).value||"").trim());
  return Number.isFinite(v)?v:null;
}
function ceSet(pfx,i,f,sec){
  const el=document.getElementById(pfx+i+f);
  if(!el) return;
  el.value=String(Math.round(sec*10)/10);
  ceRender(pfx);
}
function ceTapTile(pfx, k){
  const st=ceState(pfx), i=st.sel, sec=Math.round(k*st.sheet.step*10)/10;
  const s=ceVal(pfx,i,"a"), e=ceVal(pfx,i,"b");
  if(s===null || e!==null){ ceSet(pfx,i,"a",sec); const b=document.getElementById(pfx+i+"b"); if(b)b.value=""; }
  else if(sec>s){ ceSet(pfx,i,"b",sec); }
  else { ceSet(pfx,i,"a",sec); }
  ceShowFrame(pfx); ceRender(pfx);
}
// 선택한 컷의 시작 장면을 크게 띄우고 사각형을 얹는다.
function ceShowFrame(pfx){
  const st=ceState(pfx), img=document.getElementById(pfx+"frame");
  if(!img||!st.sheet) return;
  const k=Math.max(0, Math.min(st.sheet.n-1, Math.round((ceVal(pfx,st.sel,"a")||0)/st.sheet.step)));
  const cx=k%st.sheet.cols, cy=Math.floor(k/st.sheet.cols);
  img.src=""; // 시트를 배경으로 쓰는 대신 stage 배경으로 표시
  const stage=document.getElementById(pfx+"stage");
  if(stage){
    stage.style.backgroundImage="url("+prox(st.sheet.url)+")";
    stage.style.backgroundSize=(st.sheet.cols*100)+"% "+(st.sheet.rows*100)+"%";
    stage.style.backgroundPosition=(st.sheet.cols>1?(cx*100/(st.sheet.cols-1)):0)+"% "+
                                   (st.sheet.rows>1?(cy*100/(st.sheet.rows-1)):0)+"%";
    stage.style.aspectRatio=(st.sheet.tw+"/"+st.sheet.th);
    img.style.visibility="hidden";
  }
  ceDrawBox(pfx);
}
// 9:16 사각형 그리기(폭 w는 원본 가로 대비 비율 → 줌 = 1/w)
function ceDrawBox(pfx){
  const st=ceState(pfx), c=st.cuts[st.sel];
  const stage=document.getElementById(pfx+"stage"), box=document.getElementById(pfx+"box");
  if(!stage||!box) return;
  const W=stage.clientWidth||320, H=stage.clientHeight||180;
  const bw=Math.max(0.15, Math.min(1, c.box.w))*W;
  const bh=Math.min(H, bw*16/9);
  const bx=Math.max(0, Math.min(W-bw, c.box.x*W-bw/2));
  const by=Math.max(0, Math.min(H-bh, c.box.y*H-bh/2));
  box.style.left=bx+"px"; box.style.top=by+"px"; box.style.width=bw+"px"; box.style.height=bh+"px";
  const zoom=Math.round((1/Math.max(0.15,c.box.w))*100)/100;
  const el=document.getElementById(pfx+"box_info");
  if(el)el.innerHTML="컷 "+(st.sel+1)+" · 줌 <b>"+zoom.toFixed(2)+"배</b> · 가로 "+c.box.x.toFixed(2)+" · 세로 "+c.box.y.toFixed(2);
}
// ★필요한 총 길이 안내(운영자 확정): "30초면 두 구간을 반복할 게 아니라, 내가 30초 이상을 고르면
//   된다. 총 몇 초가 필요한지만 알려달라." → 본문 길이와 **지금 고른 합**을 항상 같이 보여준다.
function ceRender(pfx){
  const st=ceState(pfx);
  let sum=0, n=0;
  for(let i=0;i<CUTN;i++){
    const s=ceVal(pfx,i,"a"), e=ceVal(pfx,i,"b");
    const row=document.getElementById(pfx+"row"+i);
    if(row)row.style.borderColor=(i===st.sel?"var(--cy)":"#24405a");
    if(s===null||e===null||e<=s) continue;
    sum+=e-s; n++;
  }
  const el=document.getElementById(pfx+"need");
  if(!el) return;
  const need=st.need||0, sm=Math.round(sum*10)/10;
  if(!need){
    el.innerHTML="지금 고른 구간 <b>"+n+"개 · 합 "+sm+"초</b>";
    return;
  }
  const short=Math.round((need-sum)*10)/10;
  el.innerHTML="필요한 총 길이 <b style=\\"color:var(--cy)\\">"+need+"초</b> (나레이션 길이) · 지금 고른 합 <b>"+sm+"초</b>"+
    (short>0.05?(" → <b style=\\"color:#ffb84d\\">"+short+"초 부족</b> · 부족하면 고른 구간을 순서대로 반복해 채웁니다")
              : " → <b style=\\"color:#7ee787\\">충분합니다</b> · 넘는 만큼은 마지막 컷이 잘립니다");
}
// 편집기 값 → 워크플로 inputs(컷마다 개별 구간·줌·크롭)
function cutEditorInputs(pfx){
  const st=ceState(pfx), specs=[];
  for(let i=0;i<CUTN;i++){
    const s=ceVal(pfx,i,"a"), e=ceVal(pfx,i,"b"), b=st.cuts[i].box;
    if(s===null||e===null||e<=s) continue;
    specs.push({start:s, end:e,
                zoom:Math.round((1/Math.max(0.15,b.w))*100)/100,
                crop_x:Math.round(b.x*100)/100, crop_y:Math.round(b.y*100)/100});
  }
  return specs.length?{cut_specs:JSON.stringify(specs)}:{};
}
// 배선: 원본 재생 + '여기 시작/끝' + 컷 선택 + 사각형 드래그 + 줌 슬라이더 + 실행 버튼
//   opt = {sheet, srcs:[재생 후보 URL], need:본문 길이(초)}
function bindCutEditor(pfx, opt, onGo){
  const st=ceState(pfx);
  const o=(opt&&opt.sheet!==undefined)?opt:{sheet:opt||null,srcs:[],need:0};
  st.need=Math.round((o.need||0)*10)/10;
  // 원본 재생(후보 순서대로 시도): 미리보기 mp4 → 커먼스 트랜스코드 → 원본
  const v=document.getElementById(pfx+"vid");
  const list=(o.srcs||[]).filter(Boolean);
  if(v){
    let ci=0;
    const play=()=>{ if(ci>=list.length){
        const el=document.getElementById(pfx+"info");
        if(el)el.innerHTML="이 브라우저가 원본 형식을 재생하지 못합니다(대개 WebM). 아래 <b>사진 띠</b>를 탭해 구간을 고르세요.";
        return; }
      v.src=prox(list[ci]); v.load(); };
    v.onloadedmetadata=()=>{ st.srcDur=v.duration||0;
      const el=document.getElementById(pfx+"info");
      if(el)el.innerHTML="원본 길이 <b>"+(v.duration||0).toFixed(1)+"초</b> · 재생하다가 아래 <b>여기 시작 / 여기 끝</b>을 누르세요.";};
    v.onerror=()=>{ci++;play();};
    play();
  }
  // ★'여기 시작 / 여기 끝' → 그 컷의 칸에 초를 적어 넣는다(값이 눈에 보이게).
  document.querySelectorAll("[data-mk^='"+pfx+"']").forEach(b=>{b.onclick=()=>{
    const key=b.dataset.mk.slice(pfx.length);              // 예: "0a"
    const i=parseInt(key)||0, f=key.slice(-1);
    const t=Math.round(((v&&v.currentTime)||0)*10)/10;
    st.sel=i; ceSet(pfx,i,f,t); ceShowFrame(pfx);
    banner("컷 "+(i+1)+" "+(f==="a"?"시작":"끝")+" = "+t+"초 입력됨","ok");
  };});
  // 컷 선택(잘라낼 곳): 그 컷의 화면·사각형을 아래 편집기에 띄운다
  document.querySelectorAll("[data-cesel]").forEach(b=>{b.onclick=()=>{
    st.sel=parseInt(b.dataset.cesel)||0;
    const z=document.getElementById(pfx+"zoom");
    if(z)z.value=String(Math.round(st.cuts[st.sel].box.w*100));
    ceShowFrame(pfx); ceRender(pfx);
    const stg=document.getElementById(pfx+"stage");
    if(stg&&stg.scrollIntoView)stg.scrollIntoView({behavior:"smooth",block:"center"});
  };});
  // 칸에 직접 적어도 합계가 갱신되게
  for(let i=0;i<CUTN;i++)["a","b"].forEach(f=>{
    const el=document.getElementById(pfx+i+f); if(el)el.oninput=()=>ceRender(pfx);});
  const stage=document.getElementById(pfx+"stage");
  if(stage){
    const move=(cx,cy)=>{const r=stage.getBoundingClientRect();
      const c=st.cuts[st.sel];
      c.box.x=Math.max(0,Math.min(1,(cx-r.left)/(r.width||1)));
      c.box.y=Math.max(0,Math.min(1,(cy-r.top)/(r.height||1)));
      ceDrawBox(pfx);};
    stage.addEventListener("pointerdown",e=>{stage.setPointerCapture&&stage.setPointerCapture(e.pointerId);move(e.clientX,e.clientY);});
    stage.addEventListener("pointermove",e=>{if(e.buttons)move(e.clientX,e.clientY);});
  }
  const z=document.getElementById(pfx+"zoom");
  if(z)z.oninput=()=>{st.cuts[st.sel].box.w=Math.max(0.15,Math.min(1,(parseInt(z.value)||60)/100)); ceDrawBox(pfx);};
  ceLoadSheet(pfx, o.sheet); ceRender(pfx);
  const go=document.getElementById(pfx+"go"); if(go&&onGo)go.onclick=onGo;
}

// extra = 편집 패널이 만든 워크플로 inputs(cut_specs·zoom·crop_x·cuts). 없으면 자동 재제작.
async function regenNarrate(id,sourceUrl,mode,extra){
  if(!authReady()){banner("재생성에는 GitHub 토큰(Actions: Read and write)이 필요합니다.","err");return;}
  if(!sourceUrl){banner("원본 URL 정보가 없어 재생성할 수 없습니다.","err");return;}
  const hasEx=extra&&Object.keys(extra).length;
  const note=hasEx?"지정한 구간·줌으로 다시 만듭니다.":"같은 원본으로 처음부터 다시 만듭니다.";
  if(!confirm(note+"\\n\\n같은 화면(주소)이 새 결과로 갱신됩니다(5~15분).\\n계속할까요?"))return;
  banner("재제작 요청 중… ("+note+" · 5~15분)");
  try{
    const inputs=Object.assign({video_url:sourceUrl,mode:(mode||"shorts"),content_id:String(id)},
                               (typeof extra==="string"?{cut_specs:extra}:(extra||{})));
    const r=await fetch(API+"/actions/workflows/"+NV_WF+"/dispatches",{method:"POST",headers:headers(true),
      body:JSON.stringify({ref:BRANCH,inputs})});
    if(r.status===204)banner("재생성 시작! 5~15분 뒤 이 화면을 새로고침하면 새 결과가 표시됩니다.","ok");
    else{const t=await r.text();banner("재생성 시작 실패("+r.status+")<br><span class='mono' style='font-size:11px'>"+esc(t.slice(0,140))+"</span>","err");}
  }catch(e){banner("재생성 오류: "+e,"err");}
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
        // ★이 영상으로 바로 쇼츠 제작(운영자 확정). 종명·학명은 제작 시 자동 검색·확보한다.
        '<div style="margin-top:5px"><button class="mini" onclick="vsShorts('+i+')" '+
          'style="width:100%;border-color:#2e7d8f;color:#8fe3f5">이 영상으로 쇼츠 제작</button></div>'+
        '<div style="margin-top:4px"><a class="hint" href="'+esc(v.page)+'" target="_blank" rel="noopener" style="font-size:10px">원본 페이지 · 권리 확인</a></div>'+
      '</div></div>';
  });
  h+='</div>';
  el.innerHTML=h;
}
// ★찾은 영상으로 쇼츠 제작(운영자 확정).
//   요구사항: 이 경로로 만들 때는 **종명·학명이 추가로 검색·확보**되어야 한다 →
//   백엔드(run_pipeline --video-url)가 커먼스 구조화데이터·Wikidata로 학명을 확보한 뒤 제작하고,
//   확보 실패 시 학명을 지어내지 않고 중단한다(날조 금지). 여기서는 그 사실을 미리 안내한다.
async function vsShorts(i){
  const v=_vsList[i]; if(!v) return;
  if(!v.safe && !confirm("이 영상은 라이선스 '"+(v.license||"불명")+"' 로 재사용 가능 여부가 확인되지 않았습니다.\\n"+
                          "원본 페이지에서 권리를 직접 확인하셨습니까? 계속하시겠습니까?")) return;
  if(!authReady()){const tb=$("#tokbox");if(tb)tb.open=true;
    vsbanner("GitHub 토큰을 먼저 설정하세요(제작 카드 아래 안내).","err");return;}
  const cat=(($("#category")||{}).value||"deep_sea");
  if(!confirm("이 영상으로 쇼츠를 제작합니다.\\n\\n제목: "+(v.title||"")+"\\n카테고리: "+cat+"\\n\\n"+
              "※ 제작 형태는 자동으로 정해집니다.\\n"+
              "  ① 종명·학명이 확보되면 → 생물 쇼츠\\n"+
              "  ② 배 이름·그 배 자료가 확보되면 → 침몰선 쇼츠(화면=이 영상, 대본=그 배 자료)\\n"+
              "  ③ 둘 다 아니면 → 일반 나레이션형으로 전환(실패 아님)")) return;
  vsbanner("제작 요청 중…");
  try{
    const r=await fetch(API+"/actions/workflows/"+WF+"/dispatches",{method:"POST",headers:headers(true),
      body:JSON.stringify({ref:BRANCH,inputs:{
        query:"auto", category:cat,
        video_url:v.download||"", video_title:v.title||"",
        video_license:v.license||"", video_credit:v.credit||v.source||"",
      }})});
    if(r.status===204){
      vsbanner("제작 시작! 대상(종 또는 배) 확보 후 진행됩니다. 2~5분 뒤 텔레그램 전송 + 라이브러리 등록.","ok");
      setTimeout(loadRuns,4000); setTimeout(loadRuns,15000);
    }else{const t=await r.text();
      vsbanner("실패("+r.status+"): 토큰 권한(Actions)을 확인하세요.<br><span class='mono' style='font-size:11px'>"+esc(t.slice(0,140))+"</span>","err");}
  }catch(e){vsbanner("요청 실패: "+e,"err");}
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
async function loadRuns(){
  // ★진행 중 워크플로 조회(토큰 필요)와 완성 목록(무인증 가능)을 **분리**한다(운영자 확정 · 실사고).
  //   예전엔 둘을 한 try에 묶어, GitHub API가 실패하면 목록 전체가 "현황 조회 실패"로 사라졌다 →
  //   방금 만든 영상이 관리자 페이지에서 아예 안 보여 수정도 못 하던 문제. 목록은 항상 나와야 한다.
  let j = {workflow_runs: []}, apiErr = false;
  try{
    const r=await fetchT(API+"/actions/workflows/"+WF+"/runs?per_page=8",{headers:headers(true)});
    j=await r.json();
  }catch(e){ apiErr=true; }
  try{
    const cat=await listContent();
    const el=$("#runs");if(!el)return;el.innerHTML="";
    (j.workflow_runs||[]).filter(x=>x.status!=="completed").forEach(run=>{
      el.insertAdjacentHTML("beforeend",'<div class="run"><span class="st prog">'+(run.status==="queued"?"대기열":"진행 중")+'</span>'+
        '<a href="'+run.html_url+'" target="_blank">#'+num3(run.run_number)+' 쇼츠 생성(진행상황 보기)</a><span class="t">'+ago(run.created_at)+"</span></div>");});
    cat.slice(0,12).forEach(it=>{
      const name=esc(it.common_name_ko||it.common_name_en||"종");
      // 나레이션형은 회차 번호가 없고 상세도 /nv/ 라 라벨·링크를 따로 만든다.
      const label=(it.kind==="narrate")?("나레이션 · "+name):("#"+num3(it.no)+"_"+name+" 쇼츠");
      const href=it.href||("/c/"+num3(it.no));
      el.insertAdjacentHTML("beforeend",'<div class="run"><span class="st done">완료</span>'+
        '<a href="'+href+'">'+label+'</a><span class="t">'+esc(it.date||"")+"</span></div>");});
    if(apiErr)el.insertAdjacentHTML("afterbegin",
      '<div class="hint">진행 중 작업은 조회하지 못했습니다(토큰·네트워크) — '+
      '<a href="https://github.com/'+OWNER+'/'+REPO+'/actions" target="_blank">GitHub에서 보기</a>. 완성 목록은 아래 그대로입니다.</div>');
    if(!el.innerHTML)el.innerHTML='<div class="hint">아직 실행 기록이 없습니다.</div>';
    if((j.workflow_runs||[]).some(x=>x.status!=="completed"))setTimeout(loadRuns,20000);
  }catch(e){const el=$("#runs");if(el)el.innerHTML='<div class="hint">목록 조회 실패 — <a href="https://github.com/'+OWNER+'/'+REPO+'/actions" target="_blank">GitHub</a></div>';}
}

// ── 라이브러리: 롱폼 + 쇼츠 콘텐츠 목록 ──
async function renderLibrary(){
  view().innerHTML='<div class="card"><span class="lbl">롱폼 (탭하면 제목·설명 열람)</span><div id="lflist"><div class="hint">불러오는 중…</div></div></div>'+
    '<div class="card"><span class="lbl">쇼츠 (탭하면 열람·수정·재생성)</span><div id="clist"><div class="hint">불러오는 중…</div></div></div>';
  const [lf,cat]=await Promise.all([listLongform(),listContent()]);
  const lfel=document.getElementById("lflist");
  lfel.innerHTML=lf.length?lf.map(r=>(
    '<a class="clitem" href="'+(r.href||("/lf/"+encodeURIComponent(r.id)))+'">'+
    '<span class="no">'+(r.kind==="narrate"?"NARR":(esc(r.n||0)+"종"))+'</span>'+
    '<span class="nm">'+esc(r.yt_title||r.id)+'<small>'+esc(r.yt_title_ko||"")+'</small></span>'+
    '<span class="t">'+esc(String(r.date||"").slice(0,10))+'</span></a>'
  )).join(""):'<div class="hint">아직 롱폼이 없습니다.</div>';
  const el=document.getElementById("clist");
  el.innerHTML=cat.length?cat.map(it=>{
    const href=it.href||("/c/"+num3(it.no));
    // 나레이션형(종 없는 일반 해양 영상)도 같은 쇼츠 목록에 보이되, 번호 대신 'NARR' 칩으로 구분.
    const chip=(it.kind==="narrate")?"NARR":("#"+num3(it.no));
    const sub=(it.kind==="narrate")?esc(it.common_name_en||"")
                                   :(esc(it.common_name_en||"")+" · "+esc(it.scientific_name||""));
    return '<a class="clitem" href="'+href+'"><span class="no">'+chip+'</span>'+
      '<span class="nm">'+esc(it.common_name_ko||"종")+'<small>'+sub+'</small></span>'+
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
      '<button class="btn" id="bcut" style="grid-column:1/3;border-color:var(--cy);color:var(--cy)">구간·줌 직접 지정해서 다시 만들기</button>'+
      '<button class="btn" id="bdel" style="grid-column:1/3;background:#8b1a1a;color:#fff">이 제작물 삭제 (영상·기록 영구 삭제)</button>'+
    '</div>'+
    // ★구간·줌 직접 지정(운영자 확정): 자동으로 만든 결과가 마음에 안 들 때 여기서 잡아 다시 만든다.
    //   같은 회차에 덮어쓴다(운영자 선택). 비운 항목은 그 항목만 자동.
    // ★접어두지 않는다(운영자 지적 "메뉴가 아예 없다"): <details>로 접어두면 모바일에서 한 줄로만
    //   보여 있는지조차 모른다 → **항상 펼쳐진 카드**로 두고 제목을 크게 단다.
    '<div class="card" id="cutbox" style="margin-top:10px;border:1px solid var(--cy)">'+
      '<span class="lbl" style="color:var(--cy)">구간·줌 직접 지정 — 내가 정해서 다시 만들기</span>'+
      cutEditorHTML("ce")+
      '<button class="btn save" id="cego" style="margin-top:8px">이 설정으로 다시 만들기 (같은 회차 덮어쓰기)</button>'+
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
  // ★구간·줌 편집 패널: 열 때 원본을 찾아 재생(미리보기 mp4 우선 — 아이폰에서 WebM 재생 불가).
  //   원본 URL은 레코드에 없고 소싱 캐시(_video_cache.json)에 학명 키로 들어 있다.
  const _bcut=document.getElementById("bcut");
  if(_bcut)_bcut.onclick=()=>{const c=document.getElementById("cutbox");
    if(c&&c.scrollIntoView)c.scrollIntoView({behavior:"smooth",block:"start"});};
  const _cb=document.getElementById("cutbox");
  if(_cb)(async()=>{
    let sheet=null, srcs=[];
    try{
      const txt=await fetchRaw("short-movie-generator/src/categories/_video_cache.json");
      const cache=JSON.parse(txt||"{}");
      const key=String(sp.scientific_name||"").trim().toLowerCase();
      const ref=cache[key]||cache["wreck "+key]||null;
      sheet=(ref&&ref.sheet)||null;      // 소싱이 만든 프레임 사진 시트
      if(ref)srcs=[ref.preview_url, nvTranscode(ref.url||""), ref.url];
    }catch(e){}
    bindCutEditor("ce",{sheet:sheet, srcs:srcs, need:(md.duration||0)},()=>{
      const inp=cutEditorInputs("ce");
      if(!Object.keys(inp).length){banner("컷 구간·줌·크롭 중 최소 하나는 지정하세요.","err");return;}
      if(!confirm("지정한 구간·줌으로 이 회차를 다시 만듭니다(같은 번호에 덮어쓰기).\\n진행할까요?"))return;
      regen(id,"video",inp);
    });
  })();
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
  const label=(kind==="longform")?"이 롱폼":(kind==="narrate")?"이 나레이션 영상":"이 쇼츠";
  if(!confirm(label+" 제작물을 영구 삭제합니다.\\n\\n· 영상·이미지(릴리스 미디어)\\n· 콘텐츠 기록\\n\\n되돌릴 수 없습니다. 계속할까요?\\n\\nid: "+id))return;
  banner("삭제 중… (반영까지 20~40초)");
  try{
    const r=await fetch(API+"/actions/workflows/"+DEL_WF+"/dispatches",{method:"POST",headers:headers(true),
      body:JSON.stringify({ref:BRANCH,inputs:{content_id:String(id)}})});
    if(r.status===204){
      banner("삭제 시작! 20~40초 뒤 목록에서 사라집니다.","ok");
      // 잠시 뒤 목록으로 이동(상세는 곧 사라짐). 롱폼·나레이션 결과는 홈, 쇼츠는 라이브러리.
      setTimeout(()=>{location.href=(kind==="longform"||kind==="narrate")?"/":"/library";},1600);
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

async function regen(id,scope,extra){
  if(!authReady()){banner("재생성에는 GitHub 토큰(Actions: Read and write)이 필요합니다.","err");return;}
  banner("재생성 요청 중… ("+scope+")");
  const viz="panzoom"; // 현 시스템은 reels(실사 재편집·무료) 고정 — Veo 미사용(워크플로가 --mode reels 강제)
  try{
    const r=await fetch(API+"/actions/workflows/"+WF+"/dispatches",{method:"POST",headers:headers(true),
      body:JSON.stringify({ref:BRANCH,inputs:Object.assign({content_id:id,scope:scope,visualizer:viz},extra||{})})});
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
// NOAA(미 해양대기청) 전용 소스. NOAA는 미국 연방정부 저작물이라 **퍼블릭도메인**(직접 다운로드·2차 저작 자유).
// NOAA 자체 검색 API가 없으므로, NOAA 자료가 실제로 '직접 다운로드 가능한' 두 경로를 모아 보여준다:
//   ① Wikimedia Commons의 NOAA 영상(오케아노스 심해 ROV 등 다수가 PD로 업로드) ② Internet Archive의 NOAA 컬렉션.
// 둘 다 직다운 URL + PD라 안전. (오케아노스 등 심해 영상이 NOAA의 핵심 자산이라 심해 콘텐츠에 특히 유용.)
async function vsNoaa(q){
  const out = [];
  // ① Commons — NOAA 태그 영상
  try{
    const api = "https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search"+
      "&gsrsearch="+encodeURIComponent(q+" NOAA filetype:video")+"&gsrnamespace=6&gsrlimit=14"+
      "&prop=imageinfo&iiprop=url%7Csize%7Cmime%7Cextmetadata&iiurlwidth=360";
    const r = await fetch(api, {headers:{"User-Agent":VS_UA}});
    if(r.ok){
      const d = await r.json();
      for(const p of Object.values(((d.query||{}).pages)||{})){
        const ii = ((p.imageinfo||[])[0]) || {};
        if(!ii.url || !String(ii.mime||"").startsWith("video")) continue;
        const lic = vsCommonsLicense(ii.extmetadata||{});
        if(!lic) continue;
        const title = vsCleanTitle(String(p.title||"").replace(/^File:/,""));
        out.push({source:"NOAA (US)", title,
          topic:vsStrip(((ii.extmetadata||{}).ImageDescription||{}).value)||title,
          thumb:ii.thumburl||"", download:ii.url,
          page:"https://commons.wikimedia.org/wiki/"+encodeURIComponent(p.title||""),
          license:lic.label, safe:lic.safe,
          duration:ii.duration?Math.round(ii.duration):0, mime:ii.mime||""});
      }
    }
  }catch(e){/* Commons NOAA 실패는 무시 */}
  // ② Internet Archive — NOAA 컬렉션(미국 정부 기록 = PD)
  try{
    const api = "https://archive.org/advancedsearch.php?q="+
      encodeURIComponent("("+q+") AND mediatype:movies AND collection:(noaa OR noaaphotolib OR nationaloceanandatmosphericadministration OR oceanexplorergov)")+
      "&fl[]=identifier&fl[]=title&fl[]=description&fl[]=licenseurl&fl[]=collection&rows=10&output=json";
    const r = await fetch(api, {headers:{"User-Agent":VS_UA}});
    if(r.ok){
      const d = await r.json();
      const picks = [];
      for(const x of (((d.response||{}).docs)||[])){
        const id = String(x.identifier||"");
        if(!id || id.toLowerCase().startsWith("youtube-")) continue;
        picks.push(x);
        if(picks.length>=6) break;
      }
      const res = await Promise.all(picks.map(x =>
        vsArchiveResolve(x, {label:"Public Domain (NOAA · US Gov)", safe:true}).catch(()=>null)));
      for(const rr of res){ if(rr){ rr.source = "NOAA (US)"; out.push(rr); } }
    }
  }catch(e){/* Archive NOAA 실패는 무시 */}
  return out;
}
async function videoSearch(url){
  const q = (url.searchParams.get("q")||"").trim();
  const src = (url.searchParams.get("src")||"all").toLowerCase();
  if(!q) return j({error:"empty query", results:[]}, 400);
  const tasks = [];
  if(src==="all"||src==="noaa") tasks.push(vsNoaa(q).catch(()=>[]));
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
  // ★_video_cache.json 추가(원본 미리보기용): 종별 소싱 원본 URL이 여기 있다. 운영자가 컷 구간을
  //   눈으로 정하려면 원본을 재생해야 하므로 이 파일 읽기를 허용한다(읽기 전용 · 공개 저장소 경로).
  if(!/^short-movie-generator\/(content\/[\w.\-]+\.json|src\/categories\/_video_cache\.json|src\/categories\/deep_sea\/catalog\.json|src\/categories\/[\w\-]+\/[\w\-]+_(candidates|image_only)\.json)$/.test(path))
    return j({error:"path not allowed"}, 403);
  // ★현행화 지연 수정(운영자 지적: 재생성 완료 텔레그램 받았는데 관리자 페이지가 한참 뒤에 갱신):
  //   raw.githubusercontent.com은 경로 기준 CDN 캐시(~5분)가 있어, 재생성 커밋이 올라와도 옛 JSON을
  //   한동안 돌려준다. 클라이언트가 최신을 원할 때 cb(타임스탬프)를 붙여 오면 ①raw URL에 그 값을 실어
  //   CDN 캐시를 우회하고 ②워커 엣지 캐시도 끈다 → 즉시 현행화.
  const cb = url.searchParams.get("cb") || "";
  const q = cb ? ("?cb=" + encodeURIComponent(cb)) : "";
  const target = "https://raw.githubusercontent.com/" + OWNER + "/" + REPO + "/" + BRANCH + "/" + path + q;
  const cfopt = cb ? {cacheTtl:0, cacheEverything:false} : {cacheTtl:20, cacheEverything:true};
  try{
    const resp = await fetch(target, {headers:{"User-Agent":"deep-dive-log-dashboard"}, cf:cfopt});
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
  if(request.method !== "POST") return j({error:"method not allowed"}, 405);
  // 토큰: 서버 시크릿(GH_PAT) 우선, 없으면 브라우저가 넘긴 Authorization(PAT 모드) 사용.
  const fwd = (request.headers.get("Authorization") || "").replace(/^[Bb]earer\s+/, "");
  const token = (env && env.GH_PAT) || fwd;
  if(!token) return j({error:"토큰이 없습니다(로그인 또는 토큰 설정 필요)"}, 401);
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
// ★원본 소스 미리보기(운영자가 컷 구간을 눈으로 정하기 위함): 소싱처 원본을 그대로 재생해야
//   구간 초를 알 수 있다. 개방 프록시가 되지 않게 **소싱에 실제로 쓰는 호스트만** 허용한다.
const SOURCE_PREFIXES = [
  "https://upload.wikimedia.org/",          // Wikimedia Commons(주 소싱처)
  "https://oceanexplorer.noaa.gov/",        // NOAA Ocean Exploration
  "https://www.ncei.noaa.gov/",             // NOAA NCEI 비디오 포털
  "https://sanctuaries.noaa.gov/",          // NOAA 보호구역
];
const MEDIA_TYPES = { mp4: "video/mp4", jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png",
                      webm: "video/webm", mov: "video/quicktime", mkv: "video/x-matroska" };

async function mediaProxy(request, url) {
  const u = url.searchParams.get("u") || "";
  // ★릴리스 허용 판정은 대소문자 무시(github.repository의 정규 케이스가 'Product'/'product'로 달라도
  //   403이 나지 않게 — 저장 버튼이 갑자기 안 되던 사고의 방어). 개방 프록시는 여전히 차단.
  const lu = u.toLowerCase();
  const allowed = lu.startsWith(MEDIA_PREFIX.toLowerCase()) ||
                  SOURCE_PREFIXES.some(p => lu.startsWith(p));
  if (!allowed) return j({ error: "url not allowed" }, 403);
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
