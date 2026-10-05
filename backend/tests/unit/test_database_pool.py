import pytest

from services.common.database import create_database, pool_options


@pytest.mark.parametrize("size,overflow", [("0", "1"), ("2", "-1"), ("2", "11"),
                                          ("secret-url", "1"), ("2", "unlimited")])
def test_invalid_pool_config_fails_without_leaking_values(monkeypatch, size, overflow):
    monkeypatch.setenv("ELECT_DB_POOL_SIZE", size)
    monkeypatch.setenv("ELECT_DB_MAX_OVERFLOW", overflow)
    with pytest.raises(RuntimeError) as caught:
        pool_options()
    assert "secret-url" not in str(caught.value) and "unlimited" not in str(caught.value)


def test_pool_defaults_do_not_reduce_standalone_capacity(monkeypatch):
    monkeypatch.delenv("ELECT_DB_POOL_SIZE", raising=False)
    monkeypatch.delenv("ELECT_DB_MAX_OVERFLOW", raising=False)
    assert pool_options() == {"pool_size": 2, "max_overflow": 3}


def test_shared_pool_keeps_a_bounded_wait_and_overflow(monkeypatch):
    monkeypatch.setenv("ELECT_DB_POOL_SIZE", "2")
    monkeypatch.setenv("ELECT_DB_MAX_OVERFLOW", "1")
    engine = create_database("mysql+asyncmy://elect_monitoring_app:synthetic@mysql/elect_monitoring")
    assert engine.pool.size() == 2 and engine.pool._max_overflow == 1
    assert engine.pool.timeout() == 3
