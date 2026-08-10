from datetime import UTC, datetime

from localforge.storage.orm import UTCNaiveDateTime


def test_utc_aware_timestamps_are_normalized_for_postgres_timestamp_columns() -> None:
    value = datetime(2026, 8, 7, 17, 40, 1, 209857, tzinfo=UTC)

    normalized = UTCNaiveDateTime().process_bind_param(value, None)

    assert normalized == value.replace(tzinfo=None)
    assert normalized is not None
    assert normalized.tzinfo is None


def test_naive_and_null_timestamps_are_preserved() -> None:
    value = datetime(2026, 8, 7, 17, 40, 1)
    converter = UTCNaiveDateTime()

    assert converter.process_bind_param(value, None) == value
    assert converter.process_bind_param(None, None) is None
