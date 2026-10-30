from sqlalchemy.exc import IntegrityError

from extensions import db
from models import Candidate, Election, Vote


class VoteError(ValueError):
    pass


def cast_vote(*, election_id, voter_id, candidate_id, now):
    election = db.session.get(Election, election_id)
    if election is None or not election.is_open_now(now):
        raise VoteError("This election is not currently open.")
    candidate = db.session.get(Candidate, candidate_id)
    if candidate is None or candidate.election_id != election_id or not candidate.is_active:
        raise VoteError("The selected candidate is not available in this election.")

    vote = Vote(
        election_id=election_id,
        voter_id=voter_id,
        candidate_id=candidate_id,
    )
    db.session.add(vote)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise VoteError("A vote has already been recorded for this election.") from exc
    return vote
