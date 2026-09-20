#!/usr/bin/env python3
"""wrangler 가 뱉은 글에서 보관함(KV) 번호만 뽑는다.

    npx wrangler kv namespace list                        | python3 kv_id.py
    npx wrangler kv namespace create SHORTS_STUDIO_BLOB   | python3 kv_id.py

(verdict-theater/tools/kv_id.py 의 검증된 구현을 이식.)

⚠️ 이름을 그냥 "BLOB" 으로 두면 안 된다. 같은 Cloudflare 계정에 판결극장이 이미
   "BLOB" 이라는 보관함을 쓰고 있어서, 목록에서 그것을 집어 **남의 보관함에** 붙는다.

두 가지 글을 다 읽는다
    · list   → JSON 배열 (앞뒤 안내 문구가 섞여 있어 대괄호 사이만 읽는다)
    · create → 사람이 읽는 글. 그 안에 id = "…" 가 있다.
"""

import json
import re
import sys

WANT = "SHORTS_STUDIO_BLOB"


def pick(raw: str) -> str:
    i, j = raw.find("["), raw.rfind("]")
    if i >= 0 and j > i:
        try:
            got = json.loads(raw[i:j + 1])
        except Exception:  # noqa: BLE001
            got = None
        if isinstance(got, list):
            for n in got:
                if isinstance(n, dict) and n.get("title") == WANT:
                    return str(n.get("id") or "")
            for n in got:                      # 판마다 이름 앞에 워커 이름이 붙기도 한다
                if isinstance(n, dict) and str(n.get("title") or "").endswith(WANT):
                    return str(n.get("id") or "")
            return ""
    m = re.search(r'\bid\s*=\s*"([0-9a-fA-F]{32})"', raw)
    return m.group(1) if m else ""


def selftest() -> None:
    """진짜 출력 모양으로 시험한다. 짐작으로 만들면 조용히 헛돈다."""
    made = (
        ' ⛅️ wrangler 4.86.0\n───────────────────\n\n'
        '🌀 Creating namespace with title "SHORTS_STUDIO_BLOB"\n✨ Success!\n'
        '[[kv_namespaces]]\nbinding = "BLOB"\nid = "fd8c9bc19e4d4a3d944e705c013fe05b"\n'
    )
    assert pick(made) == "fd8c9bc19e4d4a3d944e705c013fe05b", "만든 직후 글을 못 읽는다"
    listed = (
        ' ⛅️ wrangler 4.86.0\n[\n'
        ' {"id":"aaaa","title":"BLOB"},\n'
        ' {"id":"fd8c9bc19e4d4a3d944e705c013fe05b","title":"SHORTS_STUDIO_BLOB"}\n]\n'
    )
    assert pick(listed) == "fd8c9bc19e4d4a3d944e705c013fe05b", "목록에서 우리 것을 못 찾는다"
    assert pick('[{"id":"aaaa","title":"BLOB"}]') == "", "판결극장 보관함을 우리 것이라 한다"
    assert pick("아무것도 없음") == "", "없는데 있다고 한다"
    print("자기시험 통과: 만든 직후 글도, 목록도 읽고, 남의 보관함은 집지 않는다", file=sys.stderr)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        sys.stdout.write(pick(sys.stdin.read()))
