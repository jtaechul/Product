import sys
import re
from collections import Counter

# 필수 라이브러리 임포트 확인
try:
    from pykospacing import Spacing
    from konlpy.tag import Okt
    import Levenshtein
except ImportError as e:
    print(f"[오류] 필수 라이브러리가 설치되지 않았습니다: {e}")
    print("다음 명령어로 설치해주세요: pip install -r requirements.txt")
    sys.exit(1)

class KoreanSpellChecker:
    def __init__(self, dictionary_path=None):
        print(">> [초기화] 모델 및 사전 로딩 중...")
        self.spacing = Spacing()
        self.okt = Okt()
        self.dictionary = set()

        # 1. 기본 사전 로드 (데모용 데이터 포함)
        self._load_default_dictionary()
        
        # 2. 사용자 지정 사전 로드 (선택 사항)
        if dictionary_path:
            self.load_user_dictionary(dictionary_path)
            
    def _load_default_dictionary(self):
        """
        기본적인 한국어 단어들을 사전에 등록합니다.
        실제 운영 시에는 국립국어원 표준국어대사전 등의 데이터를 파일로 로드하여 사용해야 합니다.
        """
        defaults = [
            "안녕하세요", "반갑습니다", "한국어", "분석", "테스트", "입니다", "오류", "교정", 
            "데이터", "딥러닝", "인공지능", "개발자", "파이썬", "프로그래밍", "API", 
            "통신", "사전", "맞춤법", "띄어쓰기", "형태소", "라이브러리", "알고리즘",
            "편집거리", "유사도", "추천", "기능", "작성", "코드", "실행", "결과"
        ]
        self.dictionary.update(defaults)

    def load_user_dictionary(self, path):
        """텍스트 파일에서 단어를 읽어 사전에 추가합니다. (한 줄에 한 단어)"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                words = [line.strip() for line in f if line.strip()]
                self.dictionary.update(words)
            print(f">> 사용자 사전 로드 완료: {len(words)}개 단어 추가됨")
        except FileNotFoundError:
            print(f"[경고] 사전 파일을 찾을 수 없습니다: {path}")

    def fix_spacing(self, text):
        """
        [1단계] PyKoSpacing을 사용한 띄어쓰기 교정
        """
        print(f"   [1단계] 띄어쓰기 교정 전: {text}")
        corrected = self.spacing(text)
        print(f"   [1단계] 띄어쓰기 교정 후: {corrected}")
        return corrected

    def find_best_match(self, word):
        """
        [3단계] Levenshtein Distance를 사용하여 가장 유사한 표준어 추천
        """
        best_match = None
        min_dist = float('inf')
        
        # 성능 최적화를 위해 길이 차이가 너무 큰 단어는 제외
        candidates = [w for w in self.dictionary if abs(len(w) - len(word)) <= 2]
        
        for dict_word in candidates:
            dist = Levenshtein.distance(word, dict_word)
            
            # 편집 거리가 2 이하인 경우만 유사 단어로 간주
            if dist <= 2:
                if dist < min_dist:
                    min_dist = dist
                    best_match = dict_word
                elif dist == min_dist:
                    # 거리가 같다면 더 많이 쓰이는 단어 우선 (여기선 단순 길이/가나다순)
                    pass
        
        return best_match if best_match else word

    def process(self, text):
        """
        전체 파이프라인 실행: 띄어쓰기 -> 형태소 분석 -> 미등록어 탐지 -> 교정
        """
        print("
" + "="*50)
        print(f"입력 텍스트: {text}")
        print("="*50)

        # 1. 띄어쓰기 교정
        spaced_text = self.fix_spacing(text)

        # 2. 형태소 분석 및 미등록어 탐지 (명사 위주로 교정)
        print(">> [2단계] 형태소 분석 및 미등록어(OOV) 탐지 중...")
        
        # Okt 형태소 분석 (Stemming 적용하지 않음)
        pos_results = self.okt.pos(spaced_text)
        
        corrected_tokens = []
        corrections = []

        for word, pos in pos_results:
            # 명사(Noun)이면서 사전에 없는 경우 교정 시도
            # (조사, 어미 등은 교정 대상에서 제외하여 오판 방지)
            if pos in ['Noun'] and word not in self.dictionary:
                suggestion = self.find_best_match(word)
                
                if suggestion != word:
                    corrections.append(f"{word} -> {suggestion}")
                    corrected_tokens.append(suggestion)
                else:
                    corrected_tokens.append(word)
            else:
                corrected_tokens.append(word)

        # 3. 결과 재조합
        final_text = spaced_text
        for correction in corrections:
            original, new = correction.split(" -> ")
            final_text = final_text.replace(original, new)

        print("
" + "="*50)
        print(f"최종 교정 결과: {final_text}")
        if corrections:
            print(f"교정된 단어 목록: {', '.join(corrections)}")
        else:
            print("교정된 단어가 없습니다.")
        print("="*50 + "
")
        
        return final_text

# 실행 예제
if __name__ == "__main__":
    checker = KoreanSpellChecker()
    
    # 테스트 케이스
    sample_texts = [
        "반갑습니가한국어분석테스트임니다",  # 띄어쓰기 오류 + 오타
        "파이썬을사용하여API통신없이작동하는코드", # 띄어쓰기 오류
        "딥러닝기반의알고리즘을적용해봅니다" # 미등록어 테스트
    ]

    for text in sample_texts:
        checker.process(text)
