from datetime import timedelta

from extensions import db
from models import Candidate, Election, User, Vote, utcnow


def authenticate(client, voter_id):
    with client.session_transaction() as session:
        session["_user_id"] = str(voter_id)
        session["_fresh"] = True


def test_unauthenticated_vote_is_rejected(client, election_and_candidate):
    election_id, candidate_id = election_and_candidate
    response = client.post(
        f"/elections/{election_id}/vote", data={"candidate_id": candidate_id}
    )
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_successful_vote_and_duplicate_submission_protection(
    client, app, voter, election_and_candidate
):
    election_id, candidate_id = election_and_candidate
    authenticate(client, voter)
    response = client.post(
        f"/elections/{election_id}/vote", data={"candidate_id": candidate_id}
    )
    assert response.status_code == 200
    assert b"Your vote was recorded" in response.data
    again = client.post(
        f"/elections/{election_id}/vote", data={"candidate_id": candidate_id}
    )
    assert again.status_code == 302
    with app.app_context():
        assert Vote.query.filter_by(election_id=election_id, voter_id=voter).count() == 1


def test_closed_election_does_not_accept_vote(client, app, voter, election_and_candidate):
    election_id, candidate_id = election_and_candidate
    with app.app_context():
        db.session.get(Election, election_id).status = "closed"
        db.session.commit()
    authenticate(client, voter)
    response = client.post(
        f"/elections/{election_id}/vote", data={"candidate_id": candidate_id}
    )
    assert response.status_code == 302
    with app.app_context():
        assert Vote.query.count() == 0


def test_invalid_candidate_is_rejected(client, app, voter, election_and_candidate):
    election_id, _candidate_id = election_and_candidate
    authenticate(client, voter)
    response = client.post(
        f"/elections/{election_id}/vote", data={"candidate_id": "99999"}
    )
    assert response.status_code == 302
    with app.app_context():
        assert Vote.query.count() == 0


def test_candidate_from_another_election_is_rejected(client, app, voter, election_and_candidate):
    election_id, _candidate_id = election_and_candidate
    with app.app_context():
        other = Election(
            title="Other",
            start_time=utcnow() - timedelta(days=1),
            end_time=utcnow() + timedelta(days=1),
            status="open",
        )
        db.session.add(other)
        db.session.flush()
        foreign = Candidate(election_id=other.id, name="Foreign candidate")
        db.session.add(foreign)
        db.session.commit()
        foreign_id = foreign.id
    authenticate(client, voter)
    client.post(f"/elections/{election_id}/vote", data={"candidate_id": foreign_id})
    with app.app_context():
        assert Vote.query.count() == 0


def test_vote_after_logout_is_rejected(client, app, voter, election_and_candidate):
    election_id, candidate_id = election_and_candidate
    authenticate(client, voter)
    client.post("/logout")
    response = client.post(
        f"/elections/{election_id}/vote", data={"candidate_id": candidate_id}
    )
    assert response.status_code == 302
    with app.app_context():
        assert Vote.query.count() == 0
