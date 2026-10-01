"""仅供后台恢复与显式烟测；人工登录绝不自动回答验证码。"""

import base64
import re
from functools import lru_cache


def arithmetic_answer(raw):
    match = re.fullmatch(r"\s*(\d)\s*([+\-*/xX])\s*(\d)\s*=?\s*", raw)
    if not match:
        return None
    left, operator, right = int(match[1]), match[2].lower(), int(match[3])
    if operator == "+":
        return str(left + right)
    if operator == "-":
        return str(left - right)
    if operator in ("*", "x"):
        return str(left * right)
    if right == 0 or left % right:
        return None
    return str(left // right)


@lru_cache(maxsize=1)
def model():
    import ddddocr

    return ddddocr.DdddOcr(show_ad=False)


def solve_image(image):
    raw = base64.b64decode(image.split(",", 1)[1], validate=True)
    return arithmetic_answer(model().classification(raw))
