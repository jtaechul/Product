
import http.server
import socketserver
import json
import subprocess
import os

# API 키를 환경 변수에서 가져옵니다.
API_KEY = os.getenv("GEMINI_API_KEY")
PORT = 8080

class GeminiCorrectionHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        # /spellcheck 엔드포인트에 대한 요청만 처리합니다.
        if self.path == '/spellcheck':
            if not API_KEY:
                self.send_error(500, "GEMINI_API_KEY가 설정되지 않았습니다.")
                return

            try:
                # 요청 본문의 길이를 가져옵니다.
                content_length = int(self.headers['Content-Length'])
                # 요청 본문을 읽고 JSON으로 파싱합니다.
                post_data = self.rfile.read(content_length)
                request_body = json.loads(post_data)
                input_text = request_body['text']

                # Gemini API에 보낼 데이터 (Payload)
                payload = {
                    "contents": [{
                        "parts": [{
                            "text": f"""다음 문장을 문맥에 맞게 가장 자연스럽고 정확한 한국어로 교정해주세요.
- 원본의 의미는 절대 변경하지 마세요.
- 어색한 표현, 문법 오류, 오타만 수정해주세요.
- 교정이 필요 없으면 원본 문장을 그대로 반환하세요.
- 설명 없이 교정된 문장만 간결하게 응답해주세요.

[원본 문장]
{input_text}

[교정된 문장]"""
                        }]
                    }]
                }

                # curl 명령어를 리스트 형태로 안전하게 구성
                command = [
                    "curl", "-s",
                    "-H", "Content-Type: application/json",
                    "-d", json.dumps(payload),
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={API_KEY}"
                ]

                # 터미널에서 curl 명령어 실행
                result = subprocess.run(command, capture_output=True, text=True, check=True)
                response_data = json.loads(result.stdout)

                # 오류 처리: API가 오류 메시지를 반환했는지 확인
                if 'error' in response_data:
                    error_message = response_data['error'].get('message', '알 수 없는 API 오류')
                    self.send_error(500, f"API Error: {error_message}")
                    return

                # 성공: 교정된 텍스트 추출
                corrected_text = response_data['candidates'][0]['content']['parts'][0]['text']
                response_payload = {'corrected_text': corrected_text.strip()}

                # 성공 응답(200 OK) 전송
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(response_payload).encode('utf-8'))

            except Exception as e:
                # 모든 예외 처리
                self.send_error(500, f"서버 내부 오류: {e}")
        else:
            # /spellcheck가 아닌 다른 경로로 POST 요청이 오면 404 에러 처리
             self.send_error(404, "Not Found")

    def do_GET(self):
        # 기본 GET 요청은 현재 디렉토리의 파일을 서비스하도록 합니다.
        # (index.html, main.js 등을 로드하기 위해 필요)
        return http.server.SimpleHTTPRequestHandler.do_GET(self)


with socketserver.TCPServer(("", PORT), GeminiCorrectionHandler) as httpd:
    print(f"{PORT} 포트에서 서버를 시작합니다...")
    print(f"웹 브라우저에서 http://localhost:{PORT} 로 접속하세요.")
    httpd.serve_forever()
