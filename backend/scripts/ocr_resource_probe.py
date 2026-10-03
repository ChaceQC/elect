"""无网络合成图测OCR冷加载、推理、线程与空闲CPU；不取学校验证码。"""

import hashlib
import io
import json
import resource
import statistics
import time
from pathlib import Path

from services.school_adapter.infrastructure.ocr import model


def cpu_seconds():
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_utime + usage.ru_stime


def probe():
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (100, 40), "white")
    ImageDraw.Draw(image).text((10, 10), "1+2=", fill="black", font_size=24)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    started = time.perf_counter()
    ocr = model()
    load = time.perf_counter() - started
    timings, answers = [], set()
    for _ in range(10):
        started = time.perf_counter()
        answers.add(ocr.classification(buffer.getvalue()))
        timings.append(time.perf_counter() - started)
    cpu_started = cpu_seconds()
    time.sleep(2)
    idle_cpu = cpu_seconds() - cpu_started
    status = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines())
    options = ocr.ocr_engine.session.get_session_options()
    return {
        "scope": "仅合成图/无网络，非学校验证码识别验收",
        "load_seconds": round(load, 4),
        "inference_p50_ms": round(statistics.median(timings) * 1000, 3),
        "inference_max_ms": round(max(timings) * 1000, 3),
        "idle_cpu_seconds_over_2s": round(idle_cpu, 4),
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "threads": int(status["Threads"]),
        "intra_op_threads": options.intra_op_num_threads,
        "inter_op_threads": options.inter_op_num_threads,
        "result_digest": hashlib.sha256("\n".join(sorted(answers)).encode()).hexdigest(),
        "distinct_results": len(answers),
    }


if __name__ == "__main__":
    print(json.dumps(probe(), ensure_ascii=False))
