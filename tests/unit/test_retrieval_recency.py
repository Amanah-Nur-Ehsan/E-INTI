from datetime import datetime

from app.services.retrieval_service import min_recommendable_year


def test_min_recommendable_year_is_a_five_year_inclusive_window(monkeypatch):
    from app.services import retrieval_service

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 8, 3, tzinfo=tz)

    monkeypatch.setattr(retrieval_service, "datetime", _FrozenDatetime)
    # 2026 down through 2022 is 5 years inclusive: 2026, 2025, 2024, 2023, 2022.
    assert min_recommendable_year() == 2022


def test_min_recommendable_year_respects_a_configured_window(monkeypatch):
    from app.core.config import get_settings
    from app.services import retrieval_service

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 1, 1, tzinfo=tz)

    monkeypatch.setattr(retrieval_service, "datetime", _FrozenDatetime)
    get_settings.cache_clear()
    monkeypatch.setenv("CITATION_RECENCY_YEARS", "3")
    try:
        assert min_recommendable_year() == 2024
    finally:
        get_settings.cache_clear()
