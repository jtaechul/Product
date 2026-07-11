"""shipwreck 카테고리 — 침몰선(난파선).

바다에 가라앉은 배를 다룬다. 확인된 사실(선종·수심·위치)만 사용하고, 미확인 역사·보물·인명
피해 등은 날조하지 않는다. reels 계약은 collection_base가 이행.
"""
from __future__ import annotations

from pathlib import Path

from src.categories.collection_base import CollectionCategory
from src.registry import register

# 각 배 = 실존 침몰선(사실 검증 완료). ship=구조화 제원(선명·선종·톤수·건조·침몰연도·침몰사유·수심).
# 확인 안 된 값(예: 일부 배의 톤수)은 지어내지 않고 생략한다(하드룰: 사실 왜곡 금지).
SUBJECTS = {
    "aries": {
        "scientific_name": "Wreck Aries",   # footage._SEED 키 'wreck aries'와 일치
        "common_name_ko": "아리에스호 난파선",
        "common_name_en": "Wreck Aries (cargo ship)",
        "depth_range_m": "18",
        "distribution": "포르투갈 연안",
        "habitat": "수심 18m 침몰 화물선",
        "diet": [],
        "ship": {"name_ko": "아리에스호", "type_ko": "화물선", "depth_m": 18,
                 "note_ko": "포르투갈 연안 수심 18m에 가라앉은 화물선"},
        "fun_facts": [
            "선종: 화물선(cargo ship)입니다",
            "포르투갈 연안 수심 18m에 가라앉아 있습니다",
            "선체 구조물이 그대로 남아 다이버들의 탐사 대상이 됩니다",
            "세월이 흐르며 물고기와 해양생물의 서식처가 되었습니다",
        ],
        "sources": ["Vitor Alves (Wikimedia Commons) · CC BY"],
    },
    "u1277": {
        "scientific_name": "Wreck U-1277",   # footage._SEED 키 'wreck u-1277'
        "common_name_ko": "U-1277 잠수함 난파선",
        "common_name_en": "Wreck U-1277 (WWII German U-boat)",
        "depth_range_m": "31",
        "distribution": "포르투갈 북부 연안(포르투 앞바다)",
        "habitat": "수심 31m 침몰 잠수함",
        "diet": [],
        "ship": {"name_ko": "U-1277", "type_ko": "Type VIIC/41 U보트(잠수함)",
                 "tonnage_ko": "수상 배수량 약 769톤", "built_ko": "1944년 취역",
                 "sunk_year": 1945, "sunk_reason_ko": "제2차 세계대전 종전 직후 승조원이 자침(自沈)",
                 "depth_m": 31, "note_ko": "포르투갈 북부 연안 수심 31m"},
        "fun_facts": [
            "선종: 제2차 세계대전 당시 독일 해군의 Type VIIC/41 U보트(잠수함)입니다",
            "수상 배수량은 약 769톤입니다",
            "1945년 종전 직후 승조원이 스스로 배를 가라앉혔습니다(자침)",
            "포르투갈 북부 연안 수심 31m에 잠들어 있습니다",
            "선체는 이제 말미잘과 물고기의 서식처가 되었습니다",
        ],
        "sources": ["Victor Marafona (Wikimedia Commons) · CC BY", "Wikipedia: German submarine U-1277"],
    },
    # ※ SS Wisconsin(4:3 소스)은 레터박스 문제로 제외(footage 종횡비 게이트). 16:9 실사 확보 시 재편입.
    "madeirense": {
        "scientific_name": "Wreck Madeirense",   # footage._SEED 키 'wreck madeirense'
        "common_name_ko": "마데이렌스호 난파선",
        "common_name_en": "Wreck Madeirense (cargo ship)",
        "depth_range_m": "34",
        "distribution": "포르투갈 포르투 산투 앞바다",
        "habitat": "수심 34m 침몰 화물선(인공어초)",
        "diet": [],
        "ship": {"name_ko": "마데이렌스호", "type_ko": "화물선(바나나 운반선)",
                 "length_ko": "전장 약 70m", "built_ko": "1962년 건조",
                 "sunk_year": 2000, "sunk_reason_ko": "2000년 다이빙 명소용 인공어초로 의도적 자침",
                 "depth_m": 34, "note_ko": "포르투 산투 앞바다 수심 약 34m"},
        "fun_facts": [
            "선종: 1962년 건조된 화물선으로, 마데이라와 본토 사이에서 바나나를 운반했습니다",
            "전장은 약 70m입니다",
            "2000년, 다이빙 명소를 위한 인공어초로 의도적으로 가라앉혔습니다",
            "포르투 산투 앞바다 수심 약 34m에 있습니다",
            "지금은 다양한 해양생물이 모이는 인공어초가 되었습니다",
        ],
        "sources": ["Victor Marafona (Wikimedia Commons) · CC BY", "Visit Madeira · Porto Santo diving"],
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
            "青い海の底に、", "横たわる、", "大きな影。", "その正体は、", "沈没船。",
            "アリエスという、", "貨物船の、", "なれの果て。", "水深、", "十八メートル。",
            "船体は今も、", "その姿を、", "残しています。", "やがて魚が、", "集まり、",
            "海藻が、", "はりつきます。", "沈んだ船は、", "人工の岩礁。",
            "新しい命の、", "すみかです。", "海に還った、", "静かな船です。",
        ],
    },
    "u1277": {
        "jp_name": "Uボート U1277",
        "hook_line1": "海に沈んだ、",
        "hook_line2": "戦争の遺物。",
        "pop_words": ["海に沈んだ、", "戦争の遺物。"],
        "feature_line": "戦いを終え、命の宿となったUボート",
        "feature_glow_word": "命",
        "hook_ko": "바다에 잠든, 전쟁의 유물.",
        "feature_ko": "전쟁을 끝내고 생명의 보금자리가 된 U보트",
        "tags": ["#沈没船", "#Uボート", "#潜水艦"],
        "tags_ko": ["#난파선", "#유보트", "#잠수함"],
        "body": [
            "暗い海の底に、", "長い鉄の影。", "その正体は、", "潜水艦。",
            "ドイツの、", "Uボート。", "U1277です。", "大戦を、", "生き延び、",
            "終戦のあと、", "乗組員が、", "自らの手で、", "沈めました。",
            "水深、", "三十一メートル。", "砲塔には今、", "白い花に似た、", "生き物が、", "びっしりと。",
            "戦うことは、", "もうありません。", "鉄の艦は、", "魚たちの、", "すみかです。",
        ],
    },
    "madeirense": {
        "jp_name": "沈没船マデイレンセ",
        "hook_line1": "海に還った、",
        "hook_line2": "バナナ運搬船。",
        "pop_words": ["海に還った、", "バナナ運搬船。"],
        "feature_line": "人工の岩礁となった、かつての貨物船",
        "feature_glow_word": "岩礁",
        "hook_ko": "바다로 돌아간, 바나나 운반선.",
        "feature_ko": "인공어초가 된 옛 화물선",
        "tags": ["#沈没船", "#難破船", "#人工魚礁"],
        "tags_ko": ["#난파선", "#침몰선", "#인공어초"],
        "body": [
            "青い海に、", "横たわる船。", "名前は、", "マデイレンセ。",
            "一九六二年、", "造られた、", "貨物船です。", "かつては、", "バナナを積み、",
            "島と本土を、", "結びました。", "二〇〇〇年、", "役目を終え、",
            "人工の岩礁に、", "なりました。", "水深、", "三十四メートル。",
            "全長は、", "七十メートル。", "今では、", "多くの命が、", "集う場所です。",
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
    fixed_hashtag = "#沈没船"     # 고정 공통 태그(난파선은 생물 아님 → 海の生き物 대신)
    fixed_hashtag_ko = "#난파선"
    SUBJECTS = SUBJECTS
    COPY = COPY
    _dir = Path(__file__).resolve().parent


register(ShipwreckCategory())
