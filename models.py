from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app
from flask_login import UserMixin
from sqlalchemy import CheckConstraint, UniqueConstraint
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    voter_id = db.Column(db.String(40), unique=True, index=True)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    mobile_number = db.Column(db.String(30))
    date_of_birth = db.Column(db.Date, nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="voter", index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    face_profile = db.relationship(
        "FaceProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("role IN ('voter', 'admin')", name="ck_user_role"),
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class FaceProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"),
                        unique=True, nullable=False)
    encrypted_encoding = db.Column(db.LargeBinary, nullable=False)
    consented_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    user = db.relationship("User", back_populates="face_profile")

    @staticmethod
    def _fernet():
        key = current_app.config.get("FACE_DATA_KEY")
        if not key:
            raise RuntimeError("FACE_DATA_KEY is required to store or verify facial data.")
        try:
            return Fernet(key.encode("ascii") if isinstance(key, str) else key)
        except (ValueError, TypeError) as exc:
            raise RuntimeError("FACE_DATA_KEY is invalid; generate a Fernet key.") from exc

    @classmethod
    def from_encoding(cls, user_id, encoding):
        import numpy as np

        payload = np.asarray(encoding, dtype=np.float64).tobytes()
        return cls(user_id=user_id, encrypted_encoding=cls._fernet().encrypt(payload))

    def get_encoding(self):
        import numpy as np

        try:
            raw = self._fernet().decrypt(self.encrypted_encoding)
        except InvalidToken as exc:
            raise RuntimeError("Stored facial data could not be decrypted.") from exc
        return np.frombuffer(raw, dtype=np.float64)


class Election(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="closed", index=True)
    publish_results = db.Column(db.Boolean, nullable=False, default=False)
    candidates = db.relationship("Candidate", backref="election", lazy=True)
    votes = db.relationship("Vote", backref="election", lazy=True)

    __table_args__ = (
        CheckConstraint("status IN ('open', 'closed')", name="ck_election_status"),
        CheckConstraint("end_time > start_time", name="ck_election_time_range"),
    )

    def is_open_now(self, now=None):
        now = now or utcnow()
        return self.status == "open" and self.start_time <= now <= self.end_time


class Candidate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    election_id = db.Column(db.Integer, db.ForeignKey("election.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    affiliation = db.Column(db.String(120), nullable=False, default="")
    manifesto = db.Column(db.Text, nullable=False, default="")
    profile_image = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    votes = db.relationship("Vote", backref="candidate", lazy=True)


class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    election_id = db.Column(db.Integer, db.ForeignKey("election.id"), nullable=False)
    voter_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidate.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint("election_id", "voter_id", name="uq_vote_election_voter"),
        db.Index("ix_vote_election_candidate", "election_id", "candidate_id"),
    )


class LoginAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject_hash = db.Column(db.String(64), nullable=False, index=True)
    occurred_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    succeeded = db.Column(db.Boolean, nullable=False, default=False)
    reason = db.Column(db.String(40), nullable=False, default="password")


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.String(255), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    actor = db.relationship("User", foreign_keys=[actor_id])
