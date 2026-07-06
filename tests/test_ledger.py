"""Unit tests for the append-only JSONL ledger."""

from app_guru.ledger import LedgerEntry, append_to_ledger, read_ledger, validated_subjects


def test_append_and_read_round_trip(tmp_path):
    path = tmp_path / "ledger.jsonl"
    entries = [
        LedgerEntry(station="trends", subject="quit vaping", verdict="RISING", data={"change_pct": 9.0}),
        LedgerEntry(station="mine", subject="hostile co-parenting", verdict=None, data={"quotes": ["x"]}),
    ]

    append_to_ledger(entries, path=path)
    loaded = read_ledger(path)

    assert len(loaded) == 2
    assert loaded[0].station == "trends"
    assert loaded[0].verdict == "RISING"
    assert loaded[0].data == {"change_pct": 9.0}
    assert loaded[1].verdict is None
    # id/ts are auto-generated and preserved through the round trip
    assert loaded[0].id and loaded[1].id
    assert loaded[0].id != loaded[1].id


def test_append_is_additive_not_overwriting(tmp_path):
    path = tmp_path / "ledger.jsonl"
    append_to_ledger([LedgerEntry(station="trends", subject="a", verdict="FLAT")], path=path)
    append_to_ledger([LedgerEntry(station="trends", subject="b", verdict="RISING")], path=path)

    loaded = read_ledger(path)
    assert [e.subject for e in loaded] == ["a", "b"]


def test_append_creates_parent_directory(tmp_path):
    path = tmp_path / "nested" / "dir" / "ledger.jsonl"
    append_to_ledger([LedgerEntry(station="trends", subject="a", verdict="RISING")], path=path)
    assert path.exists()


def test_read_ledger_missing_file_returns_empty(tmp_path):
    assert read_ledger(tmp_path / "does-not-exist.jsonl") == []


def test_validated_subjects_only_counts_rising(tmp_path):
    path = tmp_path / "ledger.jsonl"
    entries = [
        LedgerEntry(station="trends", subject="quit vaping", verdict="RISING"),
        LedgerEntry(station="trends", subject="track macros", verdict="FLAT"),
        LedgerEntry(station="mine", subject="hostile co-parenting", verdict=None),
        LedgerEntry(station="trends", subject="prd maker", verdict="DECLINING"),
    ]
    append_to_ledger(entries, path=path)
    assert validated_subjects(path) == ["quit vaping"]


def test_validated_subjects_deduplicates(tmp_path):
    path = tmp_path / "ledger.jsonl"
    entries = [
        LedgerEntry(station="trends", subject="quit vaping", verdict="RISING"),
        LedgerEntry(station="trends", subject="quit vaping", verdict="RISING"),
    ]
    append_to_ledger(entries, path=path)
    assert validated_subjects(path) == ["quit vaping"]
