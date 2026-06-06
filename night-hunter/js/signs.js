// signs.js — 분당 상권 가로 간판 (실사풍 절차적 + GLB 폴백)
// 배치 규칙: 상업지구 모든 건물의 창문 사이 (2층 ~ 옥상 직전) 에 부착.

(function () {

// 사이즈 (게임 단위 ≈ 1m) — 창문 사이 1.7m 공간에 들어가도록 조정
const SIZES = {
    L: { w: 4.5, h: 1.20, d: 0.28, bw: 0.07, ew: 0.95 },
    M: { w: 3.5, h: 1.05, d: 0.22, bw: 0.06, ew: 0.85 },
    S: { w: 2.5, h: 0.90, d: 0.18, bw: 0.06, ew: 0.70 }
};

// ── 기본 52개 ──────────────────────────────────────
const BASE_SIGNS = [
    // 카페/커피 8
    { id:'starlucks',   en:'STARLUCKS',      kr:'스타락스',     sz:'L', bg:'#007048', fg:'#ffffff', bd:'#00462d', bx:'#ffd700' },
    { id:'edia',        en:'EDIA COFFEE',    kr:'이지아커피',   sz:'M', bg:'#1b2a6b', fg:'#ffffff', bd:'#0f1950', bx:'#ffc800' },
    { id:'megalatte',   en:'MEGALATTE',      kr:'메가라떼',     sz:'M', bg:'#ffd700', fg:'#000000', bd:'#c8a000', bx:'#000000' },
    { id:'kompose',     en:'KOMPOSE',        kr:'콤포즈커피',   sz:'M', bg:'#00a99d', fg:'#ffffff', bd:'#006e64', bx:'#ffffff' },
    { id:'twosome',     en:'TWOSOME HOUSE',  kr:'투썸하우스',   sz:'L', bg:'#c8102e', fg:'#ffffff', bd:'#8c0a1e', bx:'#ffd700' },
    { id:'paulbass',    en:'PAUL BASS',      kr:'폴배쓰카페',   sz:'M', bg:'#6b3f2a', fg:'#f0dcbe', bd:'#462814', bx:'#c8b48c' },
    { id:'hallis',      en:'HALLIS COFFEE',  kr:'할리즈커피',   sz:'M', bg:'#f47920', fg:'#ffffff', bd:'#be500a', bx:'#ffffff' },
    { id:'paikda',      en:'PAIKDA COFFEE',  kr:'빽다커피',     sz:'M', bg:'#ffffff', fg:'#1e1e1e', bd:'#d21e1e', bx:'#d21e1e' },

    // 음식점 14
    { id:'maeburger',   en:'MAE BURGER',     kr:'맥버거',       sz:'L', bg:'#da291c', fg:'#ffd300', bd:'#aa140a', bx:'#ffd300' },
    { id:'burgerqueen', en:'BURGER QUEEN',   kr:'버거퀸',       sz:'L', bg:'#ff6600', fg:'#ffffff', bd:'#b43c00', bx:'#ffd700' },
    { id:'lotteria',    en:'LOTTERIA',       kr:'롯테리아',     sz:'M', bg:'#c41e3a', fg:'#ffffff', bd:'#8c0a23', bx:'#ffd700' },
    { id:'bbpchicken',  en:'BBP CHICKEN',    kr:'BBP치킨',      sz:'L', bg:'#ffc107', fg:'#000000', bd:'#c89100', bx:'#dc0000' },
    { id:'gyowon',      en:'GYOWON',         kr:'교원치킨',     sz:'L', bg:'#8b0000', fg:'#ffd700', bd:'#5a0000', bx:'#ffd700' },
    { id:'bhpchicken',  en:'BHP CHICKEN',    kr:'BHP치킨',      sz:'M', bg:'#c81e1e', fg:'#ffffff', bd:'#8c0a0a', bx:'#ffff00' },
    { id:'dominopizza', en:'DOMINO PIZZA',   kr:'도미노파자',   sz:'L', bg:'#0064b4', fg:'#ffffff', bd:'#003c82', bx:'#dc1e1e' },
    { id:'bonbab',      en:'BONBAB',         kr:'본밥',         sz:'S', bg:'#1565c0', fg:'#ffffff', bd:'#0a3c96', bx:'#ffd700' },
    { id:'hansot',      en:'HANSOT BAPSANG', kr:'한솥밥상',     sz:'S', bg:'#2e7d32', fg:'#ffffff', bd:'#145019', bx:'#ffeb3b' },
    { id:'subwaysand',  en:'SUBWAY SAND',    kr:'써브웨이샌드', sz:'M', bg:'#00833e', fg:'#ffc400', bd:'#005a28', bx:'#ffc400' },
    { id:'kimbabchon',  en:'KIMBAB CHON',    kr:'김밥천우',     sz:'M', bg:'#c62828', fg:'#ffffff', bd:'#8c0a0a', bx:'#ffd700' },
    { id:'papabird',    en:'PAPA BIRD',      kr:'파파버드',     sz:'M', bg:'#e65100', fg:'#ffffff', bd:'#aa3200', bx:'#ffd700' },
    { id:'ramennoodle', en:'DONGNE RAMEN',   kr:'동네라멘',     sz:'S', bg:'#b71c1c', fg:'#ffeb3b', bd:'#820000', bx:'#ffeb3b' },
    { id:'sundae',      en:'BUNDANG SUNDAE', kr:'분당순대국',   sz:'S', bg:'#643214', fg:'#ffebc8', bd:'#461e0a', bx:'#c89632' },

    // 병원/의원 8
    { id:'yensae',      en:'YENSAE ENT',     kr:'연새이비인후과', sz:'S', bg:'#0d47a1', fg:'#ffffff', bd:'#c8cdd7', bx:'#ffffff' },
    { id:'chastar',     en:'CHA STAR SKIN',  kr:'차앤별피부과', sz:'S', bg:'#ffffff', fg:'#ec407a', bd:'#ec407a', bx:'#ec407a' },
    { id:'brighteye',   en:'BRIGHT EYE',     kr:'밝은눈안과',   sz:'S', bg:'#01579b', fg:'#ffffff', bd:'#c8d2dc', bx:'#64c8ff' },
    { id:'gooddental',  en:'GOOD DENTAL',    kr:'선한치과의원', sz:'S', bg:'#009688', fg:'#ffffff', bd:'#c8d7d2', bx:'#ffffff' },
    { id:'hamsoa',      en:'HAMSOA CLINIC',  kr:'함소아한의원', sz:'S', bg:'#1b5e20', fg:'#ffffff', bd:'#c8dcc8', bx:'#ffeb3b' },
    { id:'sungshim',    en:'SUNGSHIM ORTH',  kr:'성심정형외과', sz:'S', bg:'#1565c0', fg:'#ffffff', bd:'#c8d2dc', bx:'#ffffff' },
    { id:'misobeauty',  en:'MISO BEAUTY',    kr:'미소성형외과', sz:'S', bg:'#ffffff', fg:'#ad1457', bd:'#ad1457', bx:'#ad1457' },
    { id:'sjclinic',    en:'SJ PEDIATRIC',   kr:'SJ소아과',     sz:'S', bg:'#64b5f6', fg:'#ffffff', bd:'#1e64c8', bx:'#ffffff' },

    // 학원/교육 6
    { id:'nunbit',      en:'NUNBIT EDU',     kr:'눈빛이학원',   sz:'M', bg:'#ff9800', fg:'#ffffff', bd:'#c86400', bx:'#ffffff' },
    { id:'daekyo',      en:'DAEKYO YEOLGI',  kr:'대교열기',     sz:'M', bg:'#1565c0', fg:'#ffffff', bd:'#0a4196', bx:'#ffd700' },
    { id:'sidaeprep',   en:'SIDAE PREP',     kr:'시대준비학원', sz:'M', bg:'#1a237e', fg:'#ffd700', bd:'#0f145a', bx:'#ffd700' },
    { id:'engkingdom',  en:'ENG KINGDOM',    kr:'영어왕국',     sz:'M', bg:'#ffeb3b', fg:'#000000', bd:'#c8af00', bx:'#ff5000' },
    { id:'mathgenius',  en:'MATH GENIUS',    kr:'수학천재',     sz:'M', bg:'#1565c0', fg:'#ffffff', bd:'#0a3c96', bx:'#ffeb3b' },
    { id:'cheongdam',   en:'CHEONGDAM LANG', kr:'청담어학당',   sz:'M', bg:'#121450', fg:'#d4af37', bd:'#d4af37', bx:'#d4af37' },

    // 의류/뷰티/쇼핑 6
    { id:'olivebom',    en:'OLIVE BOM',      kr:'올리브봄',     sz:'L', bg:'#6c7537', fg:'#ffffff', bd:'#414b14', bx:'#ffeb3b' },
    { id:'daigashop',   en:'DAIGA SHOP',     kr:'다이가샵',     sz:'L', bg:'#1e88e5', fg:'#ffffff', bd:'#f0f0f0', bx:'#ffffff' },
    { id:'unikro',      en:'UNIKRO',         kr:'유니크로',     sz:'L', bg:'#d32f2f', fg:'#ffffff', bd:'#f0f0f0', bx:'#ffffff' },
    { id:'abcshoes',    en:'ABC SHOES',      kr:'ABC슈즈마트',  sz:'M', bg:'#0d47a1', fg:'#ffffff', bd:'#ffd700', bx:'#ffd700' },
    { id:'naturechip',  en:'NATURE CHIP',    kr:'네이처채집',   sz:'M', bg:'#388e3c', fg:'#ffffff', bd:'#c8dcc8', bx:'#ffffff' },
    { id:'innibar',     en:'INNIBAR',        kr:'이니발르',     sz:'M', bg:'#1b5e20', fg:'#ffffff', bd:'#b4cdb4', bx:'#c8e6c8' },

    // 금융/은행 4
    { id:'kukminbank',  en:'KUKMIN BANK',    kr:'국민우리은행', sz:'M', bg:'#ffc107', fg:'#000000', bd:'#c89100', bx:'#000000' },
    { id:'sinhanbank',  en:'SINHAN SMART',   kr:'신한스마트은행', sz:'M', bg:'#0c3f96', fg:'#ffffff', bd:'#c8d2dc', bx:'#ffffff' },
    { id:'kakaomoney',  en:'KAKAO MONEY',    kr:'카카오머니',   sz:'M', bg:'#ffeb00', fg:'#3c1e00', bd:'#c8af00', bx:'#3c1e00' },
    { id:'tossmoney',   en:'TOSS MONEY',     kr:'토스머니',     sz:'M', bg:'#0277bd', fg:'#ffffff', bd:'#c8d2e1', bx:'#ffffff' },

    // 편의점/생활/기타 6
    { id:'gu25',        en:'GU MARKET',      kr:'GU마켓',       sz:'L', bg:'#1565c0', fg:'#ffa500', bd:'#ffa500', bx:'#ffa500' },
    { id:'sebong',      en:'SEBONG STORE',   kr:'세봉스토어',   sz:'L', bg:'#ff8f00', fg:'#006400', bd:'#006400', bx:'#ffffff' },
    { id:'cg24',        en:'CG 24',          kr:'CG24편의점',   sz:'L', bg:'#6a1b9a', fg:'#ffffff', bd:'#c896ff', bx:'#ffffff' },
    { id:'bundangpharm',en:'BUNDANG PHARM',  kr:'분당약국',     sz:'S', bg:'#ffffff', fg:'#d32f2f', bd:'#d32f2f', bx:'#d32f2f' },
    { id:'pctime',      en:'PC TIME',        kr:'피씨타임',     sz:'M', bg:'#0d0d1e', fg:'#00c8ff', bd:'#00c8ff', bx:'#00ff96' },
    { id:'noraebang',   en:'STAR SINGING',   kr:'스타노래방',   sz:'M', bg:'#1e0a32', fg:'#c800ff', bd:'#c800ff', bx:'#ffd700' }
];

// ── 추가 40개 (실제 분당 상권 추가 업종) ────────
const EXTRA_SIGNS = [
    // 카페/디저트 추가 6
    { id:'baskinrobbin',en:'BASKIN ROBBIN',  kr:'배스킨라빈',   sz:'L', bg:'#e6007e', fg:'#ffffff', bd:'#a3005a', bx:'#1976d2' },
    { id:'tousles',     en:'TOUSLES JOURS',  kr:'뚜레쥬르',     sz:'M', bg:'#3e2723', fg:'#ffd700', bd:'#1a0a04', bx:'#d4af37' },
    { id:'paribag',     en:'PARI BAGUETTE',  kr:'파리바게뜨',   sz:'L', bg:'#0a3d8c', fg:'#ffffff', bd:'#062862', bx:'#ffd700' },
    { id:'sulbings',    en:'SULBINGS',       kr:'설빙스',       sz:'M', bg:'#ffffff', fg:'#5d4037', bd:'#5d4037', bx:'#a1887f' },
    { id:'jujuboba',    en:'JUJU BOBA',      kr:'쥬쥬버블티',   sz:'S', bg:'#fce4ec', fg:'#880e4f', bd:'#ad1457', bx:'#ec407a' },
    { id:'gongcha',     en:'GONGTEA',        kr:'공테라',       sz:'M', bg:'#3e2723', fg:'#ffc107', bd:'#1a0a04', bx:'#ffc107' },

    // 음식점 추가 10
    { id:'pizzahole',   en:'PIZZA HOLE',     kr:'피자홀',       sz:'L', bg:'#c62828', fg:'#ffd54f', bd:'#7f0000', bx:'#ffd54f' },
    { id:'mrpizza',     en:'MR PIZZA',       kr:'미스터피자',   sz:'L', bg:'#212121', fg:'#ffd700', bd:'#000000', bx:'#dc0000' },
    { id:'goobne',      en:'GOOBNES',        kr:'굽네치킨',     sz:'M', bg:'#ff5722', fg:'#ffffff', bd:'#bf360c', bx:'#ffd700' },
    { id:'norangtong',  en:'NORANG CHICKEN', kr:'노랑통닭',     sz:'M', bg:'#ffd600', fg:'#212121', bd:'#aa8800', bx:'#212121' },
    { id:'sinjeon',     en:'SINJEON BUSAN',  kr:'신전떡볶이',   sz:'S', bg:'#d32f2f', fg:'#ffeb3b', bd:'#8c0000', bx:'#ffeb3b' },
    { id:'jjajangmen',  en:'JJAJANG HOUSE',  kr:'짜장마을',     sz:'M', bg:'#3e2723', fg:'#ffd54f', bd:'#1a0a04', bx:'#ff6f00' },
    { id:'ihop',        en:'I HOPPING',      kr:'아이호핑',     sz:'M', bg:'#1565c0', fg:'#ffffff', bd:'#0a3c96', bx:'#ff5722' },
    { id:'ssamzy',      en:'SSAMZY GRILL',   kr:'쌈지구이',     sz:'M', bg:'#558b2f', fg:'#ffffff', bd:'#33691e', bx:'#ffeb3b' },
    { id:'donkatsu',    en:'DONKATSU MARU',  kr:'돈가스마루',   sz:'S', bg:'#5d4037', fg:'#ffe0b2', bd:'#3e2723', bx:'#ffb74d' },
    { id:'kfcwing',     en:'KFC WING',       kr:'케이프씨윙',   sz:'L', bg:'#d32f2f', fg:'#ffffff', bd:'#7f0000', bx:'#ffffff' },

    // 병원/의원 추가 6
    { id:'wellbeing',   en:'WELLBEING INT',  kr:'웰빙내과',     sz:'S', bg:'#00838f', fg:'#ffffff', bd:'#005662', bx:'#ffffff' },
    { id:'soulpsy',     en:'SOUL PSY',       kr:'마음정신과',   sz:'S', bg:'#7b1fa2', fg:'#ffffff', bd:'#4a0072', bx:'#ce93d8' },
    { id:'newlife',     en:'NEW LIFE OBGY',  kr:'새생명산부인과', sz:'S', bg:'#f06292', fg:'#ffffff', bd:'#ba2d65', bx:'#ffffff' },
    { id:'pawsvet',     en:'PAWS ANIMAL',    kr:'발도장동물병원', sz:'S', bg:'#5d4037', fg:'#ffeb3b', bd:'#3e2723', bx:'#ffeb3b' },
    { id:'happyfoot',   en:'HAPPY FOOT',     kr:'해피발족부과', sz:'S', bg:'#0277bd', fg:'#ffffff', bd:'#01579b', bx:'#ffd700' },
    { id:'oneear',      en:'ONE EAR ENT',    kr:'원이비인후과', sz:'S', bg:'#0d47a1', fg:'#ffffff', bd:'#0a2e6b', bx:'#ffffff' },

    // 학원/교육 추가 4
    { id:'ybmlang',     en:'YBM LANGUAGE',   kr:'YBM어학원',    sz:'M', bg:'#d32f2f', fg:'#ffffff', bd:'#7f0000', bx:'#ffffff' },
    { id:'jeishakwon',  en:'JEI SCHOOL',     kr:'재이학원',     sz:'M', bg:'#1565c0', fg:'#ffeb3b', bd:'#0a3c96', bx:'#ffeb3b' },
    { id:'codeking',    en:'CODE KING',      kr:'코딩왕국',     sz:'M', bg:'#212121', fg:'#00e676', bd:'#000000', bx:'#00e676' },
    { id:'pianoworld',  en:'PIANO WORLD',    kr:'피아노세상',   sz:'M', bg:'#ffffff', fg:'#212121', bd:'#212121', bx:'#212121' },

    // 의류/뷰티 추가 6
    { id:'spaolic',     en:'SPAOLIC',        kr:'스파올릭',     sz:'L', bg:'#ff5252', fg:'#ffffff', bd:'#c50e29', bx:'#ffffff' },
    { id:'aritaom',     en:'ARITA OM',       kr:'아리타옴',     sz:'M', bg:'#ffffff', fg:'#5d4037', bd:'#5d4037', bx:'#a1887f' },
    { id:'beanpot',     en:'BEANPOT JEAN',   kr:'빈포트진',     sz:'M', bg:'#1565c0', fg:'#ffffff', bd:'#0a3c96', bx:'#ffd700' },
    { id:'modahous',    en:'MODA HOUS',      kr:'모다하우스',   sz:'M', bg:'#ad1457', fg:'#ffffff', bd:'#78002e', bx:'#fce4ec' },
    { id:'glowfacial',  en:'GLOW FACIAL',    kr:'글로우페이셜', sz:'S', bg:'#fce4ec', fg:'#880e4f', bd:'#ec407a', bx:'#ec407a' },
    { id:'nailpop',     en:'NAIL POP',       kr:'네일팝',       sz:'S', bg:'#e91e63', fg:'#ffffff', bd:'#ad1457', bx:'#ffd700' },

    // 편의점/생활/기타 추가 8
    { id:'emart24',     en:'EMARK 24',       kr:'이마크24',     sz:'L', bg:'#ffc107', fg:'#000000', bd:'#c89100', bx:'#ff5722' },
    { id:'minicvs',     en:'MINI CVS',       kr:'미니씨브이',   sz:'M', bg:'#388e3c', fg:'#ffffff', bd:'#1b5e20', bx:'#ffeb3b' },
    { id:'cleanlaundr', en:'CLEAN LAUNDRY',  kr:'크린세탁소',   sz:'S', bg:'#0277bd', fg:'#ffffff', bd:'#01579b', bx:'#ffffff' },
    { id:'mrbarber',    en:'MR BARBER',      kr:'미스터바버',   sz:'S', bg:'#212121', fg:'#ffd700', bd:'#000000', bx:'#dc0000' },
    { id:'goldjewel',   en:'GOLD JEWEL',     kr:'골드주얼리',   sz:'M', bg:'#3e2723', fg:'#ffd700', bd:'#ffd700', bx:'#ffd700' },
    { id:'flowershop',  en:'FLOWER SHOP',    kr:'꽃집',         sz:'S', bg:'#fff3e0', fg:'#388e3c', bd:'#ff7043', bx:'#ec407a' },
    { id:'realestate',  en:'BUNDANG REAL',   kr:'분당부동산',   sz:'M', bg:'#1a237e', fg:'#ffd700', bd:'#0d164e', bx:'#ffd700' },
    { id:'sportsclub',  en:'SPORTS CLUB',    kr:'스포츠클럽',   sz:'M', bg:'#d32f2f', fg:'#ffffff', bd:'#7f0000', bx:'#ffeb3b' }
];

const SIGNS = BASE_SIGNS.concat(EXTRA_SIGNS);  // 총 92개

// ── 헬퍼 ────────────────────────────────────────
function hexToColor(h) { return new THREE.Color(h); }

function lighten(hex, amount) {
    const c = new THREE.Color(hex);
    c.r = Math.min(1, c.r + amount);
    c.g = Math.min(1, c.g + amount);
    c.b = Math.min(1, c.b + amount);
    return c;
}

function darken(hex, amount) {
    const c = new THREE.Color(hex);
    c.r = Math.max(0, c.r - amount);
    c.g = Math.max(0, c.g - amount);
    c.b = Math.max(0, c.b - amount);
    return '#' + c.getHexString();
}

// ── 실사풍 메인 보드 텍스처 ──────────────────────
function makeBoardTexture(sign) {
    const cv = document.createElement('canvas');
    cv.width = 1024; cv.height = 256;
    const ctx = cv.getContext('2d');

    // 1) 배경 — 세로 그라디언트 (상단 약간 어둡게: 차양 그림자)
    const bgGrad = ctx.createLinearGradient(0, 0, 0, 256);
    bgGrad.addColorStop(0, darken(sign.bg, 0.08));
    bgGrad.addColorStop(0.15, sign.bg);
    bgGrad.addColorStop(0.85, sign.bg);
    bgGrad.addColorStop(1, darken(sign.bg, 0.05));
    ctx.fillStyle = bgGrad;
    ctx.fillRect(0, 0, 1024, 256);

    // 2) 미세 노이즈 (실사 텍스처 — 미세한 알루미늄 결)
    const img = ctx.getImageData(0, 0, 1024, 256);
    for (let i = 0; i < img.data.length; i += 4) {
        const n = (Math.random() - 0.5) * 10;
        img.data[i]     = Math.max(0, Math.min(255, img.data[i]     + n));
        img.data[i + 1] = Math.max(0, Math.min(255, img.data[i + 1] + n));
        img.data[i + 2] = Math.max(0, Math.min(255, img.data[i + 2] + n));
    }
    ctx.putImageData(img, 0, 0);

    // 3) 상단 하이라이트 (LED 광원 반사)
    const hi = ctx.createLinearGradient(0, 0, 0, 30);
    hi.addColorStop(0, 'rgba(255,255,255,0.18)');
    hi.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = hi;
    ctx.fillRect(0, 0, 1024, 30);

    // 4) 엠블럼 박스 (좌측, 둥근 모서리 + 안쪽 그림자)
    const emX = 22, emY = 22, emS = 212;
    ctx.fillStyle = sign.bx;
    ctx.beginPath();
    const r = 16;
    ctx.moveTo(emX + r, emY);
    ctx.lineTo(emX + emS - r, emY);
    ctx.quadraticCurveTo(emX + emS, emY, emX + emS, emY + r);
    ctx.lineTo(emX + emS, emY + emS - r);
    ctx.quadraticCurveTo(emX + emS, emY + emS, emX + emS - r, emY + emS);
    ctx.lineTo(emX + r, emY + emS);
    ctx.quadraticCurveTo(emX, emY + emS, emX, emY + emS - r);
    ctx.lineTo(emX, emY + r);
    ctx.quadraticCurveTo(emX, emY, emX + r, emY);
    ctx.closePath();
    ctx.fill();
    // 엠블럼 내부 광택 (상단)
    const emHi = ctx.createLinearGradient(0, emY, 0, emY + emS);
    emHi.addColorStop(0, 'rgba(255,255,255,0.35)');
    emHi.addColorStop(0.4, 'rgba(255,255,255,0)');
    ctx.fillStyle = emHi;
    ctx.fill();
    // 엠블럼 테두리 (살짝 어두운 외곽선)
    ctx.strokeStyle = sign.bd;
    ctx.lineWidth = 4;
    ctx.stroke();
    // 엠블럼 안에 영문 이니셜 (영문 첫 글자)
    ctx.fillStyle = sign.bd;
    ctx.font = 'bold 130px "Inter", "Noto Sans KR", sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(sign.en.charAt(0), emX + emS / 2, emY + emS / 2 + 8);

    // 5) 영문 상호명 — 큰 글씨 + 드롭 섀도우
    const tx = 270;
    ctx.shadowColor = 'rgba(0,0,0,0.35)';
    ctx.shadowBlur = 6;
    ctx.shadowOffsetX = 2;
    ctx.shadowOffsetY = 2;
    ctx.fillStyle = sign.fg;
    ctx.font = 'bold 80px "Inter", "Noto Sans KR", sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'alphabetic';
    ctx.fillText(sign.en, tx, 115);

    // 6) 한글 상호명
    ctx.font = 'bold 60px "Noto Sans KR", "Inter", sans-serif';
    ctx.fillText(sign.kr, tx, 200);

    // 7) 그림자 리셋 + 좌하단 작은 부가 정보 (전화 아이콘 패턴)
    ctx.shadowColor = 'transparent';
    ctx.shadowBlur = 0;
    ctx.shadowOffsetX = 0;
    ctx.shadowOffsetY = 0;

    // 8) 우측 상단 작은 별표 (LED 점등 표시)
    ctx.fillStyle = 'rgba(255,255,255,0.7)';
    ctx.beginPath();
    ctx.arc(990, 30, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(970, 30, 3, 0, Math.PI * 2);
    ctx.fill();

    const tex = new THREE.CanvasTexture(cv);
    tex.anisotropy = 8;
    tex.minFilter = THREE.LinearMipmapLinearFilter;
    tex.magFilter = THREE.LinearFilter;
    return tex;
}

// ── 절차적 간판 (실사풍 박스) ──────────────────
function buildProceduralSign(sign) {
    const sz = SIZES[sign.sz];
    const W = sz.w, H = sz.h, D = sz.d, BW = sz.bw;
    const group = new THREE.Group();
    group.name = `Sign_${sign.id}`;

    // 메인 보드 — 앞면(+Z)에만 텍스트 텍스처
    const boardTex = makeBoardTexture(sign);
    const matFront = new THREE.MeshStandardMaterial({
        map: boardTex,
        emissive: hexToColor('#ffffff'),
        emissiveMap: boardTex,
        emissiveIntensity: 0.5,
        roughness: 0.38,
        metalness: 0.25
    });
    const matSide = new THREE.MeshStandardMaterial({
        color: hexToColor(darken(sign.bg, 0.1)),
        roughness: 0.6,
        metalness: 0.3
    });
    const innerW = W - BW * 2;
    const innerH = H - BW * 2;
    const board = new THREE.Mesh(
        new THREE.BoxGeometry(innerW, innerH, D),
        [matSide, matSide, matSide, matSide, matFront, matSide]
    );
    board.castShadow = true;
    board.receiveShadow = true;
    group.add(board);

    // 알루미늄 테두리 4면 — 약간 메탈릭 광택
    const borderMat = new THREE.MeshStandardMaterial({
        color: hexToColor(sign.bd),
        emissive: hexToColor(sign.bd),
        emissiveIntensity: 0.12,
        roughness: 0.35,
        metalness: 0.7
    });
    const bTop = new THREE.Mesh(new THREE.BoxGeometry(W, BW, D + 0.03), borderMat);
    bTop.position.set(0, H / 2 - BW / 2, 0.005);
    bTop.castShadow = true;
    group.add(bTop);
    const bBot = new THREE.Mesh(new THREE.BoxGeometry(W, BW, D + 0.03), borderMat);
    bBot.position.set(0, -H / 2 + BW / 2, 0.005);
    bBot.castShadow = true;
    group.add(bBot);
    const bL = new THREE.Mesh(new THREE.BoxGeometry(BW, H, D + 0.03), borderMat);
    bL.position.set(-W / 2 + BW / 2, 0, 0.005);
    bL.castShadow = true;
    group.add(bL);
    const bR = new THREE.Mesh(new THREE.BoxGeometry(BW, H, D + 0.03), borderMat);
    bR.position.set(W / 2 - BW / 2, 0, 0.005);
    bR.castShadow = true;
    group.add(bR);

    // LED 하단 조명띠 (실제 형광튜브 느낌 — 얇은 실린더 + 발광 박스)
    const ledColor = lighten(sign.bg, 0.35);
    const ledMat = new THREE.MeshStandardMaterial({
        color: ledColor,
        emissive: ledColor,
        emissiveIntensity: 1.0,
        roughness: 0.2,
        metalness: 0.05
    });
    const led = new THREE.Mesh(
        new THREE.BoxGeometry(W - 0.05, 0.07, D + 0.08),
        ledMat
    );
    led.position.set(0, -H / 2 - 0.05, 0.04);
    group.add(led);

    // 벽 부착 브래킷 (간판 뒷면 2개 — 살짝 보이는 디테일)
    const brackMat = new THREE.MeshStandardMaterial({
        color: 0x333333, roughness: 0.8, metalness: 0.4
    });
    [-W * 0.3, W * 0.3].forEach(bx => {
        const bracket = new THREE.Mesh(
            new THREE.BoxGeometry(0.08, H * 0.5, D * 1.4),
            brackMat
        );
        bracket.position.set(bx, 0, -D * 0.55);
        group.add(bracket);
    });

    return group;
}

// ── GLB 폴백 텍스처 적용 ───────────────────────
function applyTextureToGLB(root, sign) {
    const tex = makeBoardTexture(sign);
    root.traverse(child => {
        if (!child.isMesh) return;
        const name = (child.name || '').toLowerCase();
        if (name.includes('main_board') || name.includes('mainboard')) {
            child.material = new THREE.MeshStandardMaterial({
                map: tex,
                emissiveMap: tex,
                emissive: hexToColor('#ffffff'),
                emissiveIntensity: 0.5,
                roughness: 0.38,
                metalness: 0.25
            });
        }
        child.castShadow = true;
    });
}

function loadSignMesh(sign, onReady) {
    const url = `assets/models/signs/${sign.id}.glb`;
    const loader = new THREE.GLTFLoader();
    loader.load(
        url,
        (gltf) => {
            const root = gltf.scene;
            applyTextureToGLB(root, sign);
            root.name = `Sign_${sign.id}_GLB`;
            onReady(root);
        },
        undefined,
        (_err) => { onReady(buildProceduralSign(sign)); }
    );
}

// ── 빌딩 1개에 간판 부착 (창문 사이, 2층부터) ──
// 창문 중심: y = 1.5 + f*3 (f=0,1,2...). 창문 사이 = y = 3, 6, 9, 12...
// "2층부터" = 최저 y=3 (1F 창문 위, 2F 창문 아래)
function attachSignsToBuilding(scene, building, signList) {
    const { x, z, w, d, h } = building;
    const frontZ = z + d / 2 + 0.20;

    // 가용 y 슬롯 산출 (y=3,6,9,... up to h-1.2)
    const slots = [];
    for (let y = 3.0; y <= h - 1.2; y += 3.0) slots.push(y);
    if (slots.length === 0) return;

    const count = Math.min(slots.length, signList.length);
    if (count === 0) return;

    for (let i = 0; i < count; i++) {
        const sign = signList[i];
        const sz = SIZES[sign.sz];
        // 빌딩 폭보다 크면 스케일 다운 (양쪽 0.3 여유)
        const maxW = w - 0.6;
        const scale = sz.w > maxW ? maxW / sz.w : 1.0;
        const yPos = slots[i];

        loadSignMesh(sign, (mesh) => {
            mesh.scale.setScalar(scale);
            mesh.position.set(x, yPos, frontZ);
            scene.add(mesh);
        });
    }
}

// ── 메인 진입점 ────────────────────────────────
window.loadSigns = function (scene, buildingData) {
    if (!buildingData || !Array.isArray(buildingData)) return;
    const commercial = buildingData.filter(b => b.zone === 'COMMERCIAL');
    if (commercial.length === 0) return;

    // 빌딩별 슬롯 합산해서 필요한 만큼 시작 인덱스 분산 — 모든 빌딩이 채워지도록 modulo cycling
    let cursor = 0;
    for (const b of commercial) {
        // 빌딩 높이에서 가용 슬롯 계산
        const slotsCount = Math.max(1, Math.floor((b.h - 1.2 - 3.0) / 3.0) + 1);
        // signList 만들기 — 풀에서 순환 추출
        const portion = [];
        for (let i = 0; i < slotsCount; i++) {
            portion.push(SIGNS[cursor % SIGNS.length]);
            cursor++;
        }
        attachSignsToBuilding(scene, b, portion);
    }
};

window.SIGN_DATA = SIGNS;
window.SIGN_SIZES = SIZES;

})();
