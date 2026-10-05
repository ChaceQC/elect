"""按事件独立判定必需作业，只有快速场景允许三组完整验证跳过。"""
import json
import os
import re

QUICK = {"backend", "frontend"}
FULL = {"business", "compatibility", "delivery"}
REQUIRED = QUICK | FULL


def requires_full(event, ref, validation="full"):
    if event == "pull_request":
        return True
    if event == "push":
        if ref.startswith("refs/heads/"):
            return False
        if re.fullmatch(r"refs/tags/v[0-9]+\.[0-9]+\.[0-9]+", ref):
            return True
    if event == "workflow_dispatch" and validation in {"full", "quick"}:
        # 在标签上手动运行也保留完整验证，但不会进入发布作业。
        return ref.startswith("refs/tags/") or validation == "full"
    raise ValueError("不支持的CI触发场景或验证范围")


def verify(needs, full=True):
    if not isinstance(needs, dict) or set(needs) != REQUIRED:
        raise ValueError("必需作业集合缺失或发生意外变化")
    failed = [name for name, value in needs.items()
              if not isinstance(value, dict)
              or value.get("result") != ("success" if full or name in QUICK else "skipped")]
    if failed:
        raise ValueError("作业结果不符合当前场景：" + ", ".join(sorted(failed)))


if __name__ == "__main__":
    full = requires_full(os.environ["GITHUB_EVENT_NAME"], os.environ["GITHUB_REF"],
                         os.environ.get("CI_VALIDATION", "full"))
    verify(json.loads(os.environ["CI_NEEDS"]), full)
    print("前后端和三组完整验证全部成功" if full else "前后端快速检查全部成功，三组完整验证按场景跳过")
