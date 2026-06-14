"""GitHub Pages 게시 — 대시보드 HTML을 저장소에 올려 공개 URL로 보이게 한다.

원리: VM의 실시간 데이터를 브라우저/클로드 어디서나 보려면, 도달 가능한 곳에 올려야 한다.
이 저장소는 GitHub Pages가 켜져 있으므로, GitHub Contents API(토큰 인증)로 파일 하나를
저장소에 PUT 하면 → Pages가 공개 URL로 서빙한다. (로컬 git 작업과 무관 = auto-update 와 충돌 없음)

설정(.env):
    GITHUB_TOKEN=ghp_xxx            # repo contents 쓰기 권한 토큰(파인그레인드 권장)
    GITHUB_REPO=jtaechul/Product    # (선택) 기본값
    GITHUB_PAGES_BRANCH=main        # (선택) Pages 가 서빙하는 브랜치

토큰이 없으면 publish_file 은 (False, "no token") 을 돌려주고 아무 것도 안 한다.
⚠️ 공개 저장소이므로 올린 내용은 누구나 볼 수 있다 → 민감정보는 올리지 말 것.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.request

try:
    from . import config  # noqa: F401  (.env 로딩 부수효과)
except Exception:
    pass


def _cfg():
    return (os.getenv("GITHUB_TOKEN", ""),
            os.getenv("GITHUB_REPO", "jtaechul/Product"),
            os.getenv("GITHUB_PAGES_BRANCH", "main"))


def pages_url(path_in_repo: str) -> str:
    _, repo, _ = _cfg()
    owner, name = (repo.split("/", 1) + ["", ""])[:2]
    return f"https://{owner.lower()}.github.io/{name}/{path_in_repo}"


def publish_file(path_in_repo: str, content: str,
                 message: str = "update dashboard") -> tuple[bool, str]:
    """저장소의 path_in_repo 파일을 content 로 생성/갱신. 반환 (성공?, URL 또는 사유)."""
    token, repo, branch = _cfg()
    if not token:
        return False, "no token"
    api = f"https://api.github.com/repos/{repo}/contents/{path_in_repo}"
    headers = {"Authorization": f"Bearer {token}",
               "Accept": "application/vnd.github+json",
               "User-Agent": "upbit-dashboard"}
    sha = None
    try:  # 기존 파일이 있으면 sha 필요(갱신)
        req = urllib.request.Request(f"{api}?ref={branch}", headers=headers)
        with urllib.request.urlopen(req, timeout=15) as r:
            sha = json.loads(r.read()).get("sha")
    except Exception:
        pass
    body = {"message": message, "branch": branch,
            "content": base64.b64encode(content.encode("utf-8")).decode()}
    if sha:
        body["sha"] = sha
    try:
        req = urllib.request.Request(api, data=json.dumps(body).encode(),
                                     headers=headers, method="PUT")
        with urllib.request.urlopen(req, timeout=20) as r:
            ok = r.status in (200, 201)
        return ok, pages_url(path_in_repo)
    except Exception as exc:
        return False, str(exc)
