"""显式执行的学校参考协议烟测；不属于正式 Adapter，不在普通 CI 执行。"""

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]


def load_reference():
    document = (ROOT / "docs/学校对接API文档.md").read_text()
    blocks = []
    for section in ["9.2", "9.3", "9.4"]:
        match = re.search(rf"### {re.escape(section)} .*?```python\n(.*?)\n```", document, re.S)
        if not match:
            raise RuntimeError("学校参考代码块缺失")
        blocks.append(match[1])
    # 只载入 B01/B02 及会话基础，后续建单/付款代码不进入本烟测。
    blocks[2] = blocks[2].split("    def rooms_page", 1)[0]
    # 只允许最多两次取图识别，一次认证提交，无失败后的自动重试。
    blocks[1] = blocks[1].replace("range(4)", "range(2)")
    namespace = {"__name__": "elect_readonly_reference"}
    exec(compile("\n\n".join(blocks), "school_readonly_reference", "exec"), namespace)
    return namespace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--auth-file", type=Path, default=ROOT / "auth.txt")
    parser.add_argument("--record", type=Path)
    args = parser.parse_args()
    reference = load_reference()
    result = {
        "date": datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat(),
        "source": "学校文档参考实现",
        "scope": ["A01", "A02", "A03", "A04", "B01", "B02"],
        "external_business_writes": False,
        "production_adapter_verified": False,
    }
    try:
        username, password = reference["load_auth_file"](args.auth_file)
        try:
            token = reference["cas_login"](username, password)
        finally:
            del username, password
        with reference["SchoolClient"](token) as client:
            info = client.get_info()
            user_id = (info.get("user") or {}).get("userId")
            if user_id is None:
                raise RuntimeError("B01 必需字段缺失")
            rooms = client.bound_rooms(user_id)
            result.update(
                {
                    "authentication": "passed",
                    "current_user": "passed",
                    "bound_rooms": "passed",
                    "bound_room_count": len(rooms),
                }
            )
        del token, info, user_id, rooms
    except Exception as error:
        # 不输出异常文本、URL、请求/响应、原始账户与 token。
        result.update({"result": "failed", "failure_class": type(error).__name__})
    else:
        result["result"] = "passed"
    content = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.record:
        args.record.parent.mkdir(parents=True, exist_ok=True)
        args.record.write_text(content)
    print(content, end="")
    if result["result"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
