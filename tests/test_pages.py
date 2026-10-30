from extensions import db
from models import Candidate, Election, User, utcnow


def sign_in_admin(client, app):
    with app.app_context():
        admin = User(full_name="Page Admin", email="page-admin@example.test", role="admin")
        admin.set_password("a-long-admin-password")
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id
    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True


def test_admin_management_pages_render(client, app, election_and_candidate):
    sign_in_admin(client, app)
    for path in ("/admin/candidates", "/admin/elections", "/admin/voters"):
        response = client.get(path)
        assert response.status_code == 200, path


def test_public_closed_election_results_render(client, app, election_and_candidate):
    election_id, _candidate_id = election_and_candidate
    with app.app_context():
        election = db.session.get(Election, election_id)
        election.status = "closed"
        db.session.commit()
    response = client.get(f"/results/{election_id}")
    assert response.status_code == 200
    assert b"Classroom Election" in response.data


def test_candidate_cannot_be_changed_during_open_election(client, app, election_and_candidate):
    sign_in_admin(client, app)
    _election_id, candidate_id = election_and_candidate
    response = client.get(f"/admin/candidates/{candidate_id}/edit")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/candidates")
