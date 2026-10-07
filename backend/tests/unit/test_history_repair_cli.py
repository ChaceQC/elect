"""维护命令默认只审查，显式apply才可写；失败不泄露配置。"""

import pytest

from services.room import repair_history


@pytest.mark.parametrize("arguments,apply", [([], False), (["--apply"], True)])
def test_cli_defaults_and_explicit_apply(monkeypatch, arguments, apply):
    seen = []

    async def run(args):
        seen.append(args)

    monkeypatch.setattr("sys.argv", ["repair_history", *arguments])
    monkeypatch.setattr(repair_history, "run", run)
    repair_history.main()
    assert seen[0].apply is apply
    assert seen[0].batch_size == 100 and seen[0].batches == 1
    assert seen[0].after == "00000000-0000-0000-0000-000000000000"


def test_cli_failure_does_not_expose_driver_error(monkeypatch):
    async def run(args):
        raise RuntimeError("synthetic-private-url")

    monkeypatch.setattr("sys.argv", ["repair_history"])
    monkeypatch.setattr(repair_history, "run", run)
    with pytest.raises(SystemExit) as failure:
        repair_history.main()
    assert "synthetic-private-url" not in str(failure.value)
