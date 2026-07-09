"""YouTube 업로드용 리프레시 토큰 1회 발급 헬퍼(로컬 실행).

왜 필요한가: 유튜브 자동 업로드는 Google 계정 권한이 필요한데, 서버(CI)에는 브라우저가 없다.
그래서 **내 컴퓨터에서 한 번만** 브라우저로 로그인해 '리프레시 토큰'(장기 열쇠)을 받아,
그 값을 GitHub 시크릿에 넣어두면 이후 CI가 그 열쇠로 자동 업로드한다.

준비(한 번만):
  1) Google Cloud Console → 프로젝트 생성 → 'YouTube Data API v3' 사용 설정.
  2) 'OAuth 동의 화면' 구성(외부, 테스트 사용자에 본인 Gmail 추가).
  3) '사용자 인증 정보 → OAuth 클라이언트 ID → 데스크톱 앱' 생성 → client_id/secret 확보.

실행:
  pip install google-auth-oauthlib
  YOUTUBE_CLIENT_ID=xxx YOUTUBE_CLIENT_SECRET=yyy python scripts/youtube_oauth.py
  → 브라우저가 열리면 본인 유튜브 계정으로 로그인/허용 → 터미널에 REFRESH TOKEN 출력.

출력된 3개 값(CLIENT_ID / CLIENT_SECRET / REFRESH_TOKEN)을 GitHub 저장소
  Settings → Secrets and variables → Actions 에
  YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET / YOUTUBE_REFRESH_TOKEN 로 저장하면 끝.
"""
from __future__ import annotations

import os
import sys

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main() -> int:
    cid = os.environ.get("YOUTUBE_CLIENT_ID")
    csec = os.environ.get("YOUTUBE_CLIENT_SECRET")
    if not cid or not csec:
        print("환경변수 YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET 를 먼저 지정하세요.")
        return 2
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("먼저 설치: pip install google-auth-oauthlib")
        return 2
    client_config = {
        "installed": {
            "client_id": cid,
            "client_secret": csec,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    # 브라우저 자동 오픈(로컬 서버 콜백). 브라우저가 없으면 콘솔 URL을 붙여넣는 방식으로 안내.
    try:
        creds = flow.run_local_server(port=0, prompt="consent")
    except Exception:
        creds = flow.run_console()  # 구버전 폴백
    print("\n================ 아래 3개를 GitHub Actions 시크릿에 저장 ================")
    print(f"YOUTUBE_CLIENT_ID     = {cid}")
    print(f"YOUTUBE_CLIENT_SECRET = {csec}")
    print(f"YOUTUBE_REFRESH_TOKEN = {creds.refresh_token}")
    print("=======================================================================")
    if not creds.refresh_token:
        print("⚠️ refresh_token 이 비어있습니다. 위 안내대로 prompt=consent 재시도하세요.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
