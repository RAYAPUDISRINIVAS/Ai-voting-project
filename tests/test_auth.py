import numpy as np

from extensions import db
from models import LoginAttempt, User


def test_successful_password_login_requires_face_step(client, app, voter):
    response = client.post("/login", data={"identifier": "TEST-001", "password": "a-long-test-password"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/verify-face")
    with client.session_transaction() as session:
        assert "pending_face_user_id" in session
        assert "_user_id" not in session


def test_failed_password_login_is_recorded(client, app, voter):
    response = client.post("/login", data={"identifier": "TEST-001", "password": "wrong-password"})
    assert response.status_code == 200
    assert b"Sign-in failed" in response.data
    with app.app_context():
        assert LoginAttempt.query.filter_by(succeeded=False, reason="password").count() == 1


def test_face_verification_success_and_failure(client, app, voter, monkeypatch):
    import auth

    client.post("/login", data={"identifier": "TEST-001", "password": "a-long-test-password"})
    monkeypatch.setattr(auth, "encoding_from_capture", lambda _image: np.array([9.0, 9.0, 9.0]))
    response = client.post("/verify-face", data={"face_image": "capture"})
    assert response.status_code == 200
    assert b"Face verification failed" in response.data
    monkeypatch.setattr(auth, "encoding_from_capture", lambda _image: np.array([0.1, 0.2, 0.3]))
    response = client.post("/verify-face", data={"face_image": "capture"})
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert "_user_id" in session
        assert "pending_face_user_id" not in session


def test_failed_attempt_limit_blocks_further_password_checks(client, app, voter):
    for _ in range(5):
        client.post("/login", data={"identifier": "TEST-001", "password": "wrong-password"})
    response = client.post("/login", data={"identifier": "TEST-001", "password": "a-long-test-password"})
    assert response.status_code == 200
    assert b"Too many failed sign-in attempts" in response.data
