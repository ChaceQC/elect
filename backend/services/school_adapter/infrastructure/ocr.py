"""仅供后台恢复与显式烟测；人工登录绝不自动回答验证码。"""

import base64
import os
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

    limited = os.environ.get("ELECT_OCR_LOW_RESOURCE", "false")
    if limited not in {"true", "false"}:
        raise RuntimeError("OCR低资源开关只允许true/false")
    if limited == "false":
        return ddddocr.DdddOcr(show_ad=False)
    import onnxruntime as ort
    from ddddocr.core.ocr_engine import OCREngine

    options = ort.SessionOptions()
    options.intra_op_num_threads = options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.add_session_config_entry("session.intra_op.allow_spinning", "0")
    options.add_session_config_entry("session.inter_op.allow_spinning", "0")
    options.log_severity_level = 3

    class LimitedEngine(OCREngine):
        def initialize(self, **kwargs):
            # 只配置这个模型加载器，避免全局替换ONNX函数或先加载两份模型。
            self.model_loader.load_model = lambda path: ort.InferenceSession(
                path, sess_options=options, providers=["CPUExecutionProvider"],
            )
            super().initialize(**kwargs)

    result = ddddocr.DdddOcr(ocr=False, show_ad=False)
    result.det, result.ocr_enabled = False, True
    result.ocr_engine = LimitedEngine()
    return result


def solve_image(image):
    raw = base64.b64decode(image.split(",", 1)[1], validate=True)
    return arithmetic_answer(model().classification(raw))
