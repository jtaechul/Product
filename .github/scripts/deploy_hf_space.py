"""shorts_studio/ → 허깅페이스 Space 배포.

Space는 저장소 루트에서 Dockerfile을 찾으므로 shorts_studio/ '안의 내용'을 루트로 올린다.
허깅페이스가 Streamlit SDK를 더 이상 받지 않아(gradio/docker/static만 허용) Docker로 띄운다.
README.md에는 Space 설정용 YAML 머리말을 붙여야 앱이 인식된다.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from huggingface_hub import HfApi

SRC = Path("shorts_studio")
STAGE = Path("_hf_stage")

FRONTMATTER = """---
title: AI 숏폼 동화 스튜디오
colorFrom: pink
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
short_description: 주제 한 줄로 만드는 한국 전래동화 쇼츠
---

"""


def main() -> int:
    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        print("::error::HF_TOKEN 시크릿이 없습니다. 저장소 Settings > Secrets에 추가하세요.")
        return 1

    api = HfApi(token=token)
    user = api.whoami()["name"]
    repo_id = f"{user}/{os.environ.get('SPACE_NAME', 'shorts-studio')}"

    if STAGE.exists():
        shutil.rmtree(STAGE)
    shutil.copytree(SRC, STAGE, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    readme = STAGE / "README.md"
    readme.write_text(FRONTMATTER + readme.read_text(encoding="utf-8"), encoding="utf-8")

    api.create_repo(repo_id=repo_id, repo_type="space", space_sdk="docker",
                    exist_ok=True)
    api.upload_folder(repo_id=repo_id, repo_type="space", folder_path=str(STAGE),
                      commit_message=f"deploy from {os.environ.get('GITHUB_SHA', 'local')[:7]}")

    url = f"https://huggingface.co/spaces/{repo_id}"
    print(f"배포 완료: {url}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"## 배포 완료\n\n앱 주소: {url}\n\n"
                    f"빌드가 끝날 때까지 5~10분 걸립니다(ffmpeg·한글 폰트 설치).\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
