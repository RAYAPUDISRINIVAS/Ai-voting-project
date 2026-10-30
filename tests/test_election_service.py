import pytest

from services.election_service import parse_local_datetime


def test_election_time_parser_accepts_naive_utc():
    assert parse_local_datetime("2030-01-02T03:04").isoformat() == "2030-01-02T03:04:00"


def test_election_time_parser_rejects_timezone_offsets():
    with pytest.raises(ValueError, match="UTC"):
        parse_local_datetime("2030-01-02T03:04+05:30")
