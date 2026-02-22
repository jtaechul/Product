# -*- coding: utf-8 -*-
"""
Python용 한글 맞춤법 검사 모듈 (DAUM API 기반)
"""

import requests
import json
import time
import re
from .response import Checked
from .constants import base_url

_agent = requests.Session()

def check(text):
    """
    매개변수로 입력받은 한글 문장의 맞춤법을 체크합니다.
    """
    if isinstance(text, list):
        result = []
        for item in text:
            checked = check(item)
            result.append(checked)
        return result

    if len(text) > 1000:
        return Checked(result=False, original=text, checked=text, errors=0, time=0)

    payload = {'sentence': text}
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/57.0.2987.133 Safari/537.36',
        'referer': 'https://dic.daum.net/',
    }

    start_time = time.time()
    try:
        r = _agent.post(base_url, data=payload, headers=headers)
        r.raise_for_status()
    except requests.exceptions.RequestException as e:
        return Checked(result=False, original=text, checked=text, errors=0, time=time.time() - start_time)

    passed_time = time.time() - start_time

    # HTML 응답에서 교정된 텍스트 추출
    try:
        match = re.search(r'data-error-output="([^"]+)"', r.text)
        if match:
            checked_text = match.group(1)
        else:
            # 교정할 내용이 없으면 원본 텍스트를 그대로 사용
            checked_text = text
    except Exception:
        checked_text = text # 파싱 실패 시 원본 반환

    errors = 0
    if text != checked_text:
        # 간단하게 오류가 1개 이상 있다고 표시
        errors = 1

    result = {
        'result': True,
        'original': text,
        'checked': checked_text,
        'errors': errors,
        'time': passed_time,
    }

    return Checked(**result)
