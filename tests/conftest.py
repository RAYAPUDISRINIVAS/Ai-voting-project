import os

os.environ.setdefault("SECRET_KEY", "pytest-secret")

import numpy as np
import pytest

from app import create_app
from extensions import db
from models import Candidate, Election, User, utcnow


@pytest.fixture
def app():
    app = create_app("config.TestConfig")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def face_encoding(monkeypatch):
    import auth

    monkeypatch.setattr(auth, "encoding_from_capture", lambda _image: np.array([0.1, 0.2, 0.3]))
    return np.array([0.1, 0.2, 0.3])


@pytest.fixture
def voter(app, face_encoding):
    with app.app_context():
        user = User(full_name="Demo Voter", voter_id="TEST-001", email="voter@example.test")
        user.set_password("a-long-test-password")
        db.session.add(user)
        db.session.flush()
        from models import FaceProfile

        db.session.add(FaceProfile.from_encoding(user.id, face_encoding))
        db.session.commit()
        return user.id


@pytest.fixture
def election_and_candidate(app):
    with app.app_context():
        now = utcnow()
        election = Election(
            title="Classroom Election",
            description="Test election",
            start_time=now.replace(year=now.year - 1),
            end_time=now.replace(year=now.year + 1),
            status="open",
        )
        db.session.add(election)
        db.session.flush()
        candidate = Candidate(election_id=election.id, name="Candidate One")
        db.session.add(candidate)
        db.session.commit()
        return election.id, candidate.id
