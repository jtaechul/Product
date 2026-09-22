"""사용자 시크릿을 모아 워커가 읽을 JSON 한 덩어리로 만든다(배포 워크플로가 실행).

왜 아이디마다 시크릿을 따로 두는가: GitHub 시크릿은 **한 번 넣으면 다시 볼 수 없다.**
전부 한 칸에 몰아 두면 세 번째 사람을 추가할 때 앞의 두 명 것까지 다시 타이핑해야 하고,
하나라도 빠뜨리면 그 사람이 조용히 로그인 못 하게 된다.
아이디마다 칸을 나눠 두면 **추가는 새 칸 하나, 수정은 그 칸 하나**로 끝나고
나머지는 손댈 일이 없다.

한 칸의 형식(한 줄):  아이디:비밀번호:보여줄이름
  예) jt:내비밀번호:장태철      (이름을 빼면 아이디를 그대로 쓴다)
비밀번호에 콜론(:)이 있어도 된다. 마지막 콜론 뒤가 이름이다.
"""
from __future__ import annotations

import json
import os
import sys

SLOTS = 8          # 칸 수. 더 필요하면 여기와 배포 워크플로에 같이 늘린다.


def parse(line: str) -> dict | None:
    line = (line or "").strip()
    if not line or ":" not in line:
        return None
    uid, rest = line.split(":", 1)
    if ":" in rest:
        pw, name = rest.rsplit(":", 1)
    else:
        pw, name = rest, ""
    uid, name = uid.strip(), name.strip()
    if not uid or not pw:
        return None
    return {"id": uid, "pw": pw, "name": name or uid}


def main() -> int:
    users: list[dict] = []
    seen: set[str] = set()
    for i in range(1, SLOTS + 1):
        u = parse(os.environ.get(f"U{i}", ""))
        if not u:
            continue
        if u["id"] in seen:
            print(f"::warning::아이디 '{u['id']}' 가 여러 칸에 있습니다. 뒤엣것은 무시합니다.")
            continue
        seen.add(u["id"])
        users.append(u)

    # 한 칸에 몰아 넣는 옛 방식(MOVIEGEN_USERS)도 계속 받아 준다.
    if not users:
        raw = os.environ.get("USERS_JSON", "").strip()
        if raw:
            try:
                for u in json.loads(raw):
                    if u.get("id") and u.get("pw"):
                        users.append({"id": str(u["id"]), "pw": str(u["pw"]),
                                      "name": str(u.get("name") or u["id"])})
            except Exception as e:  # noqa: BLE001
                print(f"::error::MOVIEGEN_USERS 가 올바른 JSON 이 아닙니다: {e}")
                return 1

    out = sys.argv[1] if len(sys.argv) > 1 else "users.json"
    if not users:
        # 비밀번호는 절대 찍지 않는다. 아이디만 알린다.
        print("등록된 사용자가 없습니다 — 아이디 admin 1인 모드로 둡니다.")
        return 0
    with open(out, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False)
    print(f"사용자 {len(users)}명: {', '.join(u['id'] for u in users)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
