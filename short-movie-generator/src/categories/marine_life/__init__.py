"""marine_life 카테고리 — 일반 해양생물(심해가 아닌 바다 생물 포함).

상어·문어·갑오징어·해파리·가오리 등 얕은 바다·연안·원양의 해양생물을 폭넓게 다룬다.
사실만 사용하고 없는 행동·수치는 날조하지 않는다. reels 계약은 collection_base가 이행.
"""
from __future__ import annotations

from pathlib import Path

from src.categories.collection_base import CollectionCategory
from src.registry import register

SUBJECTS = {
    "caribbean_reef_squid": {
        "scientific_name": "Sepioteuthis sepioidea",   # footage._SEED 키와 일치
        "common_name_ko": "카리브암초오징어",
        "common_name_en": "Caribbean reef squid",
        "depth_range_m": "1-150",
        "distribution": "카리브해·서대서양 산호초",
        "habitat": "얕은 산호초·해초밭(원양성)",
        "diet": ["작은 물고기", "새우"],
        "fun_facts": [
            "몸의 색과 무늬를 순식간에 바꾼다",
            "색·무늬로 동료에게 신호를 보내며 소통한다",
            "몸 가장자리의 지느러미를 물결치듯 움직여 정지 비행하듯 머문다",
            "무리를 지어 산호초 위를 떠다닌다",
        ],
        "sources": ["Atsme (Wikimedia Commons) · CC BY", "WoRMS"],
    },
}

COPY = {
    "caribbean_reef_squid": {
        "jp_name": "カリブリーフイカ",
        "hook_line1": "体の色で、",
        "hook_line2": "会話をする。",
        "pop_words": ["体の色で、", "会話をする。"],
        "feature_line": "色を変えて話す、サンゴ礁のイカ",
        "feature_glow_word": "色",
        "hook_ko": "몸의 색으로, 대화를 한다.",
        "feature_ko": "색을 바꿔 대화하는, 산호초의 오징어",
        "tags": ["#イカ", "#海の生き物", "#サンゴ礁"],
        "tags_ko": ["#오징어", "#해양생물", "#산호초"],
        "body": [
            "サンゴ礁の上を、", "ただよう影。", "その正体は、", "リーフイカ。",
            "イカの仲間です。", "体のふちの、", "ひれを波打たせ、", "その場にとどまる。",
            "おどろくのは、", "体の色。", "一瞬で、", "模様を変える。",
            "仲間と、", "色や模様で、", "合図を送りあう。",
            "色は、", "かれらの言葉。", "サンゴ礁で暮らす、", "おしゃべりなイカです。",
        ],
    },
}


class MarineLifeCategory(CollectionCategory):
    category_id = "marine_life"
    style_profile = "marine_wildlife"
    series_title = "海の生き物 図鑑"
    corner_label = "OCEAN · WILD CAM"
    scale_label = "生息水深"
    show_scale = True
    SUBJECTS = SUBJECTS
    COPY = COPY
    _dir = Path(__file__).resolve().parent


register(MarineLifeCategory())
