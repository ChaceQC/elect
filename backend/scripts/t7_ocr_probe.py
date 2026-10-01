"""只加载随镜像提供的OCR模型，测量内存，不取验证码或访问学校。"""

import json
import resource
import time

from services.school_adapter.infrastructure.ocr import model

started = time.perf_counter()
model()
print(json.dumps({"scope": "OCR模型冷加载，无学校请求",
                  "load_seconds": round(time.perf_counter() - started, 3),
                  "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}))
