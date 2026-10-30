from extensions import db
from models import FaceProfile, User


def registration_form(voter_id="VOTER-100", email="person@example.test"):
    return {
        "full_name": "Test Person",
        "voter_id": voter_id,
        "email": email,
        "mobile_number": "+1 555 123 4567",
        "date_of_birth": "1990-01-02",
        "password": "a-very-long-password",
        "confirm_password": "a-very-long-password",
        "face_consent": "yes",
        "face_image": "data:image/jpeg;base64,ZmFrZQ==",
    }


def test_successful_registration_hashes_password_and_saves_encrypted_face(client, app, face_encoding):
    response = client.post("/register", data=registration_form())
    assert response.status_code == 302
    with app.app_context():
        user = User.query.filter_by(email="person@example.test").one()
        profile = FaceProfile.query.filter_by(user_id=user.id).one()
        assert user.password_hash != "a-very-long-password"
        assert user.check_password("a-very-long-password")
        assert profile.encrypted_encoding != face_encoding.tobytes()
        assert profile.get_encoding().tolist() == face_encoding.tolist()


def test_duplicate_registration_is_rejected(client, app, face_encoding):
    assert client.post("/register", data=registration_form()).status_code == 302
    response = client.post("/register", data=registration_form(email="other@example.test"))
    assert response.status_code == 200
    assert b"already registered" in response.data
    with app.app_context():
        assert User.query.count() == 1


def test_password_confirmation_is_validated(client, app):
    data = registration_form()
    data["confirm_password"] = "different-password"
    response = client.post("/register", data=data)
    assert response.status_code == 200
    assert b"Passwords do not match" in response.data
    with app.app_context():
        assert User.query.count() == 0


def test_render_style_random_face_secret_can_encrypt_profile(app):
    with app.app_context():
        app.config["FACE_DATA_KEY"] = "render-generated-secret-value"
        profile = FaceProfile.from_encoding(1, [0.2, 0.4])
        assert profile.get_encoding().tolist() == [0.2, 0.4]
