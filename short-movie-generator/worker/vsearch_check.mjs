// 순수 로직 회귀 검증(네트워크 없음): 라이선스 안전판정·필터·정리 함수.
// 실행: node worker/vsearch_check.mjs  (실패 시 비정상 종료)
import { vsLicenseFromUrl, vsCommonsLicense, vsArchiveLicense,
         vsCleanTitle, vsStrip, vsFmtRank } from "./index.mjs";

let fails = 0;
function ok(cond, msg){ if(!cond){ console.error("FAIL:", msg); fails++; } }

// ── 라이선스 URL: 2차 저작(나레이션)·상업 허용만 safe. NC/ND는 차단 ──
ok(vsLicenseFromUrl("https://creativecommons.org/licenses/by-nd/4.0/")?.blocked === true, "by-nd blocked");
ok(vsLicenseFromUrl("https://creativecommons.org/licenses/by-nc/2.0/")?.blocked === true, "by-nc blocked");
ok(vsLicenseFromUrl("https://creativecommons.org/licenses/by-nc-sa/4.0/")?.blocked === true, "by-nc-sa blocked");
ok(vsLicenseFromUrl("https://creativecommons.org/licenses/by/3.0/")?.safe === true, "by safe");
ok(vsLicenseFromUrl("https://creativecommons.org/licenses/by-sa/4.0/")?.safe === true, "by-sa safe");
ok(vsLicenseFromUrl("http://creativecommons.org/licenses/publicdomain/")?.safe === true, "publicdomain safe");
ok(vsLicenseFromUrl("https://creativecommons.org/publicdomain/zero/1.0/")?.safe === true, "cc0 safe");
ok(vsLicenseFromUrl("") === null, "empty license -> null");

// ── Internet Archive 문서 판정 ──
ok(vsArchiveLicense({licenseurl:"https://creativecommons.org/licenses/by-nd/4.0/"}) === null, "IA nd -> excluded");
ok(vsArchiveLicense({licenseurl:"https://creativecommons.org/licenses/by/3.0/"})?.safe === true, "IA by -> safe");
ok(vsArchiveLicense({collection:["prelinger"]})?.safe === true, "IA PD collection -> safe");
ok(vsArchiveLicense({collection:["NASA"]})?.safe === true, "IA collection case-insensitive");
ok(vsArchiveLicense({collection:["random_stuff"]}) === null, "IA unknown collection -> excluded");
ok(vsArchiveLicense({}) === null, "IA no license/collection -> excluded");

// ── Commons extmetadata 판정 ──
ok(vsCommonsLicense({License:{value:"cc-by-sa-4.0"}})?.safe === true, "commons by-sa safe");
ok(vsCommonsLicense({License:{value:"cc-by-nc-4.0"}}) === null, "commons nc -> excluded");
ok(vsCommonsLicense({LicenseShortName:{value:"CC BY-ND 2.0"}}) === null, "commons nd (shortname) -> excluded");
ok(vsCommonsLicense({License:{value:"cc0"}})?.safe === true, "commons cc0 safe");
ok(vsCommonsLicense({})?.safe === false, "commons unknown -> amber(확인 필요)");

// ── 텍스트 정리 ──
ok(vsCleanTitle("Deep_Sea_Fish.ogv") === "Deep Sea Fish", "cleanTitle underscores+ext");
ok(vsStrip("<p>hi &amp; bye</p>") === "hi bye", "strip html+entities: got '"+vsStrip("<p>hi &amp; bye</p>")+"'");
ok(vsFmtRank("a.mp4") < vsFmtRank("a.webm"), "mp4 ranked before webm");
ok(vsFmtRank("a.webm") < vsFmtRank("a.ogv"), "webm ranked before ogv");

if(fails){ console.error(fails+" check(s) failed"); process.exit(1); }
console.log("vsearch_check: all passed");
