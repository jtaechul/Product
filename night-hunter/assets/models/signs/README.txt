night-hunter/assets/models/signs/
=================================

분당 상권 가로 간판 52개 GLB 파일을 이 폴더에 업로드.
파일명은 반드시 sign id 와 일치해야 함 (예: starlucks.glb).

SketchUp 워크플로우
-------------------
1. /root/.claude/uploads/.../sign_generator_prompt.md 의 Python 코드를
   사용자 로컬 SketchUp + MCP 환경에서 실행
2. bundang_signs_all.skp 저장
3. SketchUp 내 각 Sign_{id} 그룹을 우클릭 → "Export 3D Model" → .glb
4. 파일명 = {id}.glb (소문자, 확장자 .glb)
5. 이 폴더(assets/models/signs/) 에 업로드 → 커밋 → push

폴백 동작
---------
GLB 파일이 없으면 js/signs.js 가 절차적 Box + CanvasTexture 로
즉시 간판을 렌더링하므로 게임은 항상 동작.

전체 ID 목록 (52개)
-------------------
카페/커피 8 :
  starlucks, edia, megalatte, kompose, twosome,
  paulbass, hallis, paikda

음식점 14 :
  maeburger, burgerqueen, lotteria, bbpchicken, gyowon,
  bhpchicken, dominopizza, bonbab, hansot, subwaysand,
  kimbabchon, papabird, ramennoodle, sundae

병원/의원 8 :
  yensae, chastar, brighteye, gooddental, hamsoa,
  sungshim, misobeauty, sjclinic

학원/교육 6 :
  nunbit, daekyo, sidaeprep, engkingdom, mathgenius, cheongdam

의류/뷰티/쇼핑 6 :
  olivebom, daigashop, unikro, abcshoes, naturechip, innibar

금융/은행 4 :
  kukminbank, sinhanbank, kakaomoney, tossmoney

편의점/생활/기타 6 :
  gu25, sebong, cg24, bundangpharm, pctime, noraebang

GLB 메시 명명 규칙
------------------
js/signs.js 의 applyTextureToGLB 가 메인 보드 메시를 찾아
CanvasTexture(영문+한글 상호명)를 자동 적용하려면
메시 이름에 "main_board" 또는 "mainboard" 가 포함돼야 함.
다른 파츠(border, emblem, led)는 GLB 의 머티리얼을 그대로 사용.
