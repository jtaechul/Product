"""shipwreck 카테고리 — 침몰선(난파선).

바다에 가라앉은 배를 다룬다. 확인된 사실(선종·수심·위치)만 사용하고, 미확인 역사·보물·인명
피해 등은 날조하지 않는다. reels 계약은 collection_base가 이행.
"""
from __future__ import annotations

from pathlib import Path

from src.categories.collection_base import CollectionCategory
from src.registry import register

SUBJECTS = {
    "aries": {
        "scientific_name": "Wreck Aries",   # footage._SEED 키 'wreck aries'와 일치
        "common_name_ko": "아리에스호 난파선",
        "common_name_en": "Wreck Aries (cargo ship)",
        "depth_range_m": "18",
        "distribution": "포르투갈 연안",
        "habitat": "수심 18m 침몰 화물선",
        "diet": [],
        "fun_facts": [
            "수심 18m에 가라앉은 화물선의 잔해다",
            "선체 구조물이 그대로 남아 다이버들의 탐사 대상이 된다",
            "세월이 흐르며 물고기와 해양생물의 서식처가 되었다",
            "가라앉은 배는 인공 암초처럼 생태계를 이룬다",
        ],
        "sources": ["Vitor Alves (Wikimedia Commons) · CC BY"],
    },
}

COPY = {
    "aries": {
        "jp_name": "沈没船アリエス",
        "hook_line1": "海の底で、",
        "hook_line2": "眠る船。",
        "pop_words": ["海の底で、", "眠る船。"],
        "feature_line": "海の命が宿る、沈んだ貨物船",
        "feature_glow_word": "命",
        "hook_ko": "바다 밑에서, 잠든 배.",
        "feature_ko": "바다 생명이 깃든, 가라앉은 화물선",
        "tags": ["#沈没船", "#難破船", "#海"],
        "tags_ko": ["#난파선", "#침몰선", "#바다"],
        "body": [
            "青い海の底に、", "横たわる大きな影。", "その正体は、", "沈没船。",
            "アリエスという、", "貨物船のなれの果て。", "水深十八メートル。",
            "船体は今も、", "そのかたちを、", "とどめている。", "やがて、",
            "魚たちが集まり、", "海藻がはりつく。", "沈んだ船は、",
            "人工の岩礁となり、", "新しい命の、", "すみかになる。",
            "海に還った、", "静かな船です。",
        ],
    },
}


class ShipwreckCategory(CollectionCategory):
    category_id = "shipwreck"
    style_profile = "shipwreck_dive"
    series_title = "沈没船 図鑑"
    bgm_filename = "shipwreck_beneath_the_weight.mp3"
    corner_label = "WRECK · DIVE CAM"
    scale_label = "水深"          # 서식수심 대신 '수심'
    show_scale = False           # 단일 침몰 수심이라 스케일 눈금 무의미
    reframe_wide = True          # 선체 전체가 넓게 보이도록 원경 프레이밍(줌 억제)
    SUBJECTS = SUBJECTS
    COPY = COPY
    _dir = Path(__file__).resolve().parent


register(ShipwreckCategory())
