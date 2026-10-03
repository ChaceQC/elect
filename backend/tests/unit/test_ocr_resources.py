import pytest

from services.school_adapter.infrastructure.ocr import model


def test_single_thread_session_does_not_replace_global_onnx_factory(monkeypatch):
    import onnxruntime as ort

    factory = ort.InferenceSession
    monkeypatch.setenv("ELECT_OCR_LOW_RESOURCE", "true")
    model.cache_clear()
    try:
        value = model()
        assert model() is value
        options = value.ocr_engine.session.get_session_options()
        assert options.intra_op_num_threads == options.inter_op_num_threads == 1
        assert options.get_session_config_entry("session.intra_op.allow_spinning") == "0"
        assert options.get_session_config_entry("session.inter_op.allow_spinning") == "0"
        assert options.execution_mode == ort.ExecutionMode.ORT_SEQUENTIAL
        assert ort.InferenceSession is factory
        assert value.ocr_engine.session.get_providers() == ["CPUExecutionProvider"]
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
