from datetime import date, timedelta
import hashlib
import re

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from extensions import db
from face_service import FaceServiceError, compare_encodings, encoding_from_capture
from models import FaceProfile, LoginAttempt, User, utcnow

bp = Blueprint("auth", __name__)


def _subject_hash(identifier):
    material = f"{identifier.strip().lower()}|{request.remote_addr or 'unknown'}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _is_rate_limited(subject_hash):
    cutoff = utcnow() - timedelta(minutes=current_app.config["LOGIN_ATTEMPT_WINDOW_MINUTES"])
    attempts = (
        db.session.query(func.count(LoginAttempt.id))
        .filter(
            LoginAttempt.subject_hash == subject_hash,
            LoginAttempt.occurred_at >= cutoff,
            LoginAttempt.succeeded.is_(False),
        )
        .scalar()
    )
    return attempts >= current_app.config["LOGIN_ATTEMPT_LIMIT"]


def _record_attempt(subject_hash, succeeded, reason):
    db.session.add(
        LoginAttempt(subject_hash=subject_hash, succeeded=succeeded, reason=reason)
    )
    db.session.commit()


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("voter.dashboard"))
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        voter_id = request.form.get("voter_id", "").strip()
        email = request.form.get("email", "").strip().lower()
        mobile = request.form.get("mobile_number", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        dob_value = request.form.get("date_of_birth", "")
        consent = request.form.get("face_consent") == "yes"

        errors = []
        if not full_name or len(full_name) > 120:
            errors.append("Enter a name of 1–120 characters.")
        if not re.fullmatch(r"[A-Za-z0-9-]{3,40}", voter_id):
            errors.append("Voter ID must be 3–40 letters, numbers, or hyphens.")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 254:
            errors.append("Enter a valid email address.")
        if mobile and not re.fullmatch(r"[+0-9() .-]{7,30}", mobile):
            errors.append("Enter a valid mobile number.")
        if len(password) < 10 or len(password) > 128:
            errors.append("Password must contain 10–128 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")
        if not consent:
            errors.append("Informed consent is required to process facial data.")
        try:
            dob = date.fromisoformat(dob_value) if dob_value else None
            if dob and dob >= utcnow().date():
                errors.append("Date of birth must be in the past.")
        except ValueError:
            dob = None
            errors.append("Enter a valid date of birth.")
        if User.query.filter(or_(func.lower(User.email) == email, User.voter_id == voter_id)).first():
            errors.append("That voter ID or email address is already registered.")
        capture = request.form.get("face_image", "")
        if not capture:
            errors.append("Capture or upload a face image before registering.")
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("register.html")

        try:
            encoding = encoding_from_capture(capture)
            user = User(
                full_name=full_name,
                voter_id=voter_id,
                email=email,
                mobile_number=mobile or None,
                date_of_birth=dob,
            )
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            db.session.add(FaceProfile.from_encoding(user.id, encoding))
            db.session.commit()
        except FaceServiceError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            return render_template("register.html")
        except IntegrityError:
            db.session.rollback()
            flash("That voter ID or email address is already registered.", "danger")
            return render_template("register.html")
        except RuntimeError:
            db.session.rollback()
            current_app.logger.exception("Could not encrypt facial data during registration.")
            flash("Facial-data encryption is not configured correctly. Contact the administrator.", "danger")
            return render_template("register.html")
        flash("Registration complete. Sign in with your password and verify your face.", "success")
        return redirect(url_for("auth.login"))
    return render_template("register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("voter.dashboard"))
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        subject_hash = _subject_hash(identifier)
        if _is_rate_limited(subject_hash):
            flash("Too many failed sign-in attempts. Try again after 15 minutes.", "danger")
            return render_template("login.html")
        user = User.query.filter(
            or_(func.lower(User.email) == identifier.lower(), User.voter_id == identifier)
        ).first()
        if (
            not user
            or user.role != "voter"
            or not user.is_active
            or not user.check_password(password)
        ):
            _record_attempt(subject_hash, False, "password")
            flash("Sign-in failed. Check your credentials and try again.", "danger")
            return render_template("login.html")
        session.clear()
        session["pending_face_user_id"] = user.id
        session["pending_face_subject_hash"] = subject_hash
        return redirect(url_for("auth.verify_face"))
    return render_template("login.html")


@bp.route("/verify-face", methods=["GET", "POST"])
def verify_face():
    user_id = session.get("pending_face_user_id")
    if not user_id:
        flash("Sign in with your password before face verification.", "warning")
        return redirect(url_for("auth.login"))
    user = db.session.get(User, user_id)
    if user is None or not user.is_active or user.face_profile is None:
        session.clear()
        flash("Account or facial profile is unavailable. Contact the administrator.", "danger")
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        subject_hash = session.get("pending_face_subject_hash", _subject_hash(user.email))
        if _is_rate_limited(subject_hash):
            flash("Too many failed sign-in attempts. Try again after 15 minutes.", "danger")
            return render_template("face_verify.html", user=user)
        try:
            live = encoding_from_capture(request.form.get("face_image", ""))
            verified, _distance = compare_encodings(
                user.face_profile.get_encoding(),
                live,
                current_app.config["FACE_DISTANCE_THRESHOLD"],
            )
        except FaceServiceError as exc:
            _record_attempt(subject_hash, False, "face_input")
            flash(str(exc), "danger")
            return render_template("face_verify.html", user=user)
        except RuntimeError:
            current_app.logger.exception("Could not read the encrypted facial profile.")
            flash("Facial verification is unavailable. Contact the administrator.", "danger")
            return render_template("face_verify.html", user=user)
        if not verified:
            _record_attempt(subject_hash, False, "face")
            flash("Face verification failed. Try again with even lighting and a clear view.", "danger")
            return render_template("face_verify.html", user=user)
        _record_attempt(subject_hash, True, "complete")
        session.pop("pending_face_user_id", None)
        session.pop("pending_face_subject_hash", None)
        login_user(user, remember=False, fresh=True)
        return redirect(url_for("voter.dashboard"))
    return render_template("face_verify.html", user=user)


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("index"))
