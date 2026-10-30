from datetime import datetime

from models import Election, utcnow


def parse_local_datetime(value):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Enter valid election start and end dates.") from exc
    if parsed.tzinfo is not None:
        raise ValueError("Enter election times in UTC without a timezone offset.")
    return parsed


def election_status_label(election, now=None):
    now = now or utcnow()
    if election.status != "open":
        return "Closed"
    if now < election.start_time:
        return "Scheduled"
    if now > election.end_time:
        return "Ended"
    return "Open"
