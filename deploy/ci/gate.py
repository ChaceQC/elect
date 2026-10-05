"""第一轮所有场景均要求五组完整成功；缺失和跳过按失败处理。"""
import json
import os

REQUIRED = {"backend", "frontend", "business", "compatibility", "delivery"}


def verify(needs):
    if not isinstance(needs, dict) or set(needs) != REQUIRED:
        raise ValueError("必需作业集合缺失或发生意外变化")
    failed = [name for name, value in needs.items()
              if not isinstance(value, dict) or value.get("result") != "success"]
    if failed:
        raise ValueError("必需作业未成功：" + ", ".join(sorted(failed)))


if __name__ == "__main__":
    verify(json.loads(os.environ["CI_NEEDS"]))
    print("前后端和三组完整验证全部成功")
