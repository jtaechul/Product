# 반려동물 식당 에피소드 자동 제작 (「한 그릇의 품격」)

심해 쇼츠 v2(`short-movie-generator/v2`, 다른 브랜치)의 절차를 옮겨 왔다.

1. `/manage` 03단계 "프롬프트 만들기" 결과(= `/api/video-prompts` 응답)를 `episodes/<번호-이름>/episode.json`에 둔다.
2. `refs/food.jpg`(03단계 "음식 참고 이미지")를 둔다. `refs/character.png`가 있으면 캐릭터를 새로 만들지 않는다.
3. `requests/<id>.json`을 푸시하면 `.github/workflows/pet-episode.yml`이 돌아 `work/`에 결과를 커밋한다.
   - `work/final.mp4` 완성본 · `frames.jpg` 장면 모음 · `kf_cNN.png` 첫 장면 · `cNN.mp4` 컷 · `v_cNN.wav` 내레이션 · `log.json` 기록
4. 마음에 안 드는 컷은 새 요청에 `"redo": ["c03"]`(영상만) 또는 `"kf_c03"`(첫 장면부터)를 넣어 다시 뽑는다.
