from datetime import timedelta

from pathlib import Path

from sqlalchemy import text

from extensions import db
from models import Candidate, Election, User, Vote, utcnow
from results import aggregate_results
from admin import _csv_text
from app import create_app
from config import TestConfig, normalize_database_url


def test_unauthorized_admin_dashboard_is_rejected(client):
    response = client.get("/admin/dashboard")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/login")


def test_admin_role_can_access_admin_dashboard(client, app):
    with app.app_context():
        admin = User(full_name="Admin", email="admin@example.test", role="admin")
        admin.set_password("a-very-long-admin-password")
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id
    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True
    response = client.get("/admin/dashboard")
    assert response.status_code == 200
    assert b"Dashboard" in response.data


def test_aggregate_results_and_zero_eligible_turnout(app):
    with app.app_context():
        now = utcnow()
        election = Election(
            title="Results",
            start_time=now - timedelta(days=1),
            end_time=now + timedelta(days=1),
            status="closed",
        )
        db.session.add(election)
        db.session.flush()
        first = Candidate(election_id=election.id, name="Alpha")
        second = Candidate(election_id=election.id, name="Beta")
        voter_one = User(full_name="One", voter_id="ONE", email="one@example.test")
        voter_one.set_password("long-test-password-one")
        voter_two = User(full_name="Two", voter_id="TWO", email="two@example.test")
        voter_two.set_password("long-test-password-two")
        db.session.add_all([first, second, voter_one, voter_two])
        db.session.flush()
        db.session.add_all([
            Vote(election_id=election.id, voter_id=voter_one.id, candidate_id=first.id),
            Vote(election_id=election.id, voter_id=voter_two.id, candidate_id=first.id),
        ])
        db.session.commit()

        result = aggregate_results(election)
        assert result["valid_votes"] == 2
        assert result["eligible"] == 2
        assert result["turnout"] == 100
        assert result["rows"][0]["votes"] == 2
        assert result["rows"][0]["percentage"] == 100

        db.session.query(User).filter_by(role="voter").update({"is_active": False})
        db.session.commit()
        assert aggregate_results(election)["turnout"] == 0


def test_results_publication_setting_controls_open_election(client, app, election_and_candidate):
    election_id, _candidate_id = election_and_candidate
    response = client.get(f"/results/{election_id}")
    assert response.status_code == 403
    with app.app_context():
        db.session.get(Election, election_id).publish_results = True
        db.session.commit()
    assert client.get(f"/results/{election_id}").status_code == 200


def test_csv_text_is_safe_from_spreadsheet_formulas():
    assert _csv_text("=SUM(A1:A2)") == "'=SUM(A1:A2)"
    assert _csv_text("Candidate name") == "Candidate name"


def test_sqlite_foreign_keys_are_enabled(app):
    with app.app_context():
        assert db.session.execute(text("PRAGMA foreign_keys")).scalar_one() == 1


def test_one_time_admin_bootstrap_uses_configured_secret(tmp_path, monkeypatch):
    class BootstrapConfig(TestConfig):
        TESTING = False
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{Path(tmp_path) / 'bootstrap.db'}"

    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "bootstrap@example.test")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_NAME", "Bootstrap Admin")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "long-random-bootstrap-password")
    app = create_app(BootstrapConfig)
    with app.app_context():
        admin = User.query.filter_by(role="admin").one()
        assert admin.email == "bootstrap@example.test"
        assert admin.check_password("long-random-bootstrap-password")
        db.session.remove()
        db.drop_all()


def test_postgres_urls_select_installed_psycopg2_driver():
    assert normalize_database_url("postgres://user:pass@host/db") == (
        "postgresql+psycopg2://user:pass@host/db"
    )
    assert normalize_database_url("postgresql://user:pass@host/db") == (
        "postgresql+psycopg2://user:pass@host/db"
    )
    assert normalize_database_url("sqlite:///demo.db") == "sqlite:///demo.db"
