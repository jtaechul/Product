"""marine_algae 카테고리 — 해양 미세조류(식물성 플랑크톤).

현미경/근접 촬영으로 규조류·와편모조류 등 바다의 미세조류를 다룬다. 사실만(그룹 수준 특성)
사용하고, 없는 종·수치·행동은 날조하지 않는다. reels 계약은 collection_base가 이행.
"""
from __future__ import annotations

from pathlib import Path

from src.categories.collection_base import CollectionCategory
from src.registry import register

# 대상(SUBJECTS): scientific_name 은 core footage._SEED 키(소문자)와 일치해야 auto 선택됨.
SUBJECTS = {
    "diatom": {
        "scientific_name": "Bacillariophyta",
        "common_name_ko": "규조류",
        "common_name_en": "Diatom",
        "depth_range_m": "0-200",          # 유광층(광합성)
        "distribution": "전 세계 바다·담수",
        "habitat": "유광층(플랑크톤)",
        "diet": [],
        "fun_facts": [
            "유리질(이산화규소) 껍질을 가진 단세포 미세조류다",
            "광합성으로 지구 산소의 약 20%를 만들어낸다",
            "바다 먹이사슬의 바탕이 되는 식물성 플랑크톤이다",
            "좌우 대칭의 정교한 기하학적 껍질 무늬를 가진다",
        ],
        "sources": ["Michael Clarke Stuff (Wikimedia Commons) · CC BY", "WoRMS"],
    },
}

# COPY: 일본어 훅/본문 + 한국어 번역. (일본어 명조 오프닝·한국어 참고)
COPY = {
    "diatom": {
        "jp_name": "ケイソウ",
        "hook_line1": "地球の酸素の、",
        "hook_line2": "五分の一を作る。",
        "pop_words": ["地球の酸素の、", "五分の一を作る。"],
        "feature_line": "ガラスの殻をもつ、海の微細藻",
        "feature_glow_word": "ガラス",
        "hook_ko": "지구 산소의, 5분의 1을 만든다.",
        "feature_ko": "유리 껍질을 가진, 바다의 미세조류",
        "tags": ["#ケイソウ", "#プランクトン", "#海"],
        "tags_ko": ["#규조류", "#플랑크톤", "#바다"],
        "body": [
            "顕微鏡の中に、", "きらめく小さな影。", "その正体は、", "ケイソウ。",
            "海をただよう、", "微細な藻の仲間です。", "体はたった、", "ひとつの細胞。",
            "その殻は、", "ガラスと同じ、", "二酸化ケイ素でできている。",
            "左右対称の、", "精巧な模様をもつ。", "光合成をして、",
            "地球の酸素の、", "五分の一を生み出す。", "海の食物連鎖の、",
            "いちばん底をささえる、", "小さな命です。",
        ],
    },
}


class MarineAlgaeCategory(CollectionCategory):
    category_id = "marine_algae"
    style_profile = "marine_micro"
    series_title = "海の微細藻 図鑑"
    corner_label = "MARINE · MICRO CAM"
    show_scale = False           # 미세조류는 '서식수심' 스케일이 무의미
    SUBJECTS = SUBJECTS
    COPY = COPY
    _dir = Path(__file__).resolve().parent


register(MarineAlgaeCategory())
