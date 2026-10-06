import asyncio
import base64
import io
import sys

import pytest

from services.school_adapter.infrastructure.ocr import model, solve_image
from services.school_adapter.infrastructure.ocr_executor import OcrExecutor
from services.school_adapter.infrastructure.transport import Deadline


def test_single_thread_session_does_not_replace_global_onnx_factory(monkeypatch):
    import onnxruntime as ort

    factory = ort.InferenceSession
    monkeypatch.setenv("ELECT_OCR_LOW_RESOURCE", "true")
    model.cache_clear()
    try:
        from PIL import Image, ImageDraw

        picture = Image.new("RGB", (160, 60), "white")
        ImageDraw.Draw(picture).text((10, 15), "1+2=", fill="black")
        buffer = io.BytesIO()
        picture.save(buffer, format="PNG")
        encoded = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()

        async def cold_start():
            executor = OcrExecutor(solve_image)
            try:
                await executor.solve(encoded, Deadline(30))
            finally:
                assert await executor.close()

        asyncio.run(cold_start())
        value = model()
        assert model() is value
        options = value.ocr_engine.session.get_session_options()
        assert options.intra_op_num_threads == options.inter_op_num_threads == 1
        assert options.get_session_config_entry("session.intra_op.allow_spinning") == "0"
        assert options.get_session_config_entry("session.inter_op.allow_spinning") == "0"
        assert options.execution_mode == ort.ExecutionMode.ORT_SEQUENTIAL
        assert ort.InferenceSession is factory
        assert value.ocr_engine.session.get_providers() == ["CPUExecutionProvider"]
        if sys.platform == "linux":
            import resource

            print(f"offline_ocr_process_peak_kib={resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}")
    finally:
        model.cache_clear()


def test_invalid_ocr_resource_mode_cannot_silently_use_unbounded_threads(monkeypatch):
    monkeypatch.setenv("ELECT_OCR_LOW_RESOURCE", "yes")
    model.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="只允许true/false"):
            model()
    finally:
        model.cache_clear()
