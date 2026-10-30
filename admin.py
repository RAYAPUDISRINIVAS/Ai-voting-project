import csv
import io
import os
from functools import wraps

from flask import (
    Blueprint, abort, current_app, flash, make_response, redirect, render_template, request, url_for
)
from flask_login import current_user, login_user
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from extensions import db
from models import AuditLog, Candidate, Election, FaceProfile, LoginAttempt, User, Vote
from services.election_service import parse_local_datetime
from services.image_service import delete_candidate_image, save_candidate_image
from auth import _is_rate_limited, _record_attempt, _subject_hash

bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("admin.login"))
        if current_user.role != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def _audit(action, details):
    db.session.add(AuditLog(actor_id=current_user.id, action=action, details=details[:255]))


def _csv_text(value):
    text = str(value or "")
    if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard" if current_user.role == "admin" else "voter.dashboard"))
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip().lower()
        password = request.form.get("password", "")
        subject_hash = _subject_hash(identifier)
        if _is_rate_limited(subject_hash):
            flash("Too many failed sign-in attempts. Try again after 15 minutes.", "danger")
            return render_template("admin_login.html")
        user = User.query.filter(func.lower(User.email) == identifier).first()
        if user and user.is_active and user.role == "admin" and user.check_password(password):
            login_user(user, remember=False, fresh=True)
            _record_attempt(subject_hash, True, "admin")
            _audit("admin.login", "Administrator signed in")
            db.session.commit()
            return redirect(url_for("admin.dashboard"))
        _record_attempt(subject_hash, False, "admin")
        flash("Administrator sign-in failed.", "danger")
    return render_template("admin_login.html")


@bp.get("/dashboard")
@admin_required
def dashboard():
    total_voters = User.query.filter_by(role="voter").count()
    active_voters = User.query.filter_by(role="voter", is_active=True).count()
    verified_voters = (
        db.session.query(FaceProfile.id)
        .join(User)
        .filter(User.role == "voter", User.is_active.is_(True))
        .count()
    )
    elections = Election.query.order_by(Election.start_time.desc()).all()
    participation = {
        election.id: Vote.query.filter_by(election_id=election.id).count()
        for election in elections
    }
    failed_attempts = LoginAttempt.query.filter_by(succeeded=False).order_by(
        LoginAttempt.occurred_at.desc()
    ).limit(20).all()
    audit_logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(20).all()
    return render_template(
        "admin_dashboard.html",
        total_voters=total_voters,
        active_voters=active_voters,
        verified_voters=verified_voters,
        elections=elections,
        participation=participation,
        failed_attempts=failed_attempts,
        audit_logs=audit_logs,
    )


@bp.route("/candidates", methods=["GET", "POST"])
@admin_required
def candidates():
    elections = Election.query.order_by(Election.title).all()
    if request.method == "POST":
        election_id = request.form.get("election_id", type=int)
        name = request.form.get("name", "").strip()
        affiliation = request.form.get("affiliation", "").strip()
        manifesto = request.form.get("manifesto", "").strip()
        election = db.session.get(Election, election_id) if election_id else None
        if election is None or not name or len(name) > 120:
            flash("Choose an election and enter a candidate name of 1–120 characters.", "danger")
        elif election.status == "open" or Vote.query.filter_by(election_id=election_id).first():
            flash("Candidates can only be changed before voting starts and before any votes exist.", "danger")
        else:
            destination = os.path.join(current_app.root_path, "static", "uploads", "candidates")
            try:
                image_name = save_candidate_image(request.files.get("profile_image"), destination)
            except ValueError as exc:
                flash(str(exc), "danger")
            else:
                candidate = Candidate(
                    election_id=election_id,
                    name=name,
                    affiliation=affiliation[:120],
                    manifesto=manifesto,
                    profile_image=image_name,
                )
                db.session.add(candidate)
                _audit("candidate.create", f"Created candidate {name} for election {election_id}")
                try:
                    db.session.commit()
                except SQLAlchemyError:
                    db.session.rollback()
                    if image_name:
                        delete_candidate_image(destination, image_name)
                    raise
                flash("Candidate added.", "success")
                return redirect(url_for("admin.candidates"))
    all_candidates = Candidate.query.order_by(Candidate.election_id, Candidate.name).all()
    return render_template("manage_candidates.html", elections=elections, candidates=all_candidates)


@bp.route("/candidates/<int:candidate_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_candidate(candidate_id):
    candidate = db.session.get(Candidate, candidate_id)
    if candidate is None:
        from flask import abort
        abort(404)
    if candidate.election.status == "open" or Vote.query.filter_by(
        election_id=candidate.election_id
    ).first():
        flash("Candidates cannot be changed after voting starts or votes are recorded.", "danger")
        return redirect(url_for("admin.candidates"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name or len(name) > 120:
            flash("Candidate name is required and must be 120 characters or fewer.", "danger")
        else:
            destination = os.path.join(current_app.root_path, "static", "uploads", "candidates")
            try:
                image_name = save_candidate_image(request.files.get("profile_image"), destination)
            except ValueError as exc:
                flash(str(exc), "danger")
                return render_template("edit_candidate.html", candidate=candidate)
            old_image_name = candidate.profile_image
            candidate.name = name
            candidate.affiliation = request.form.get("affiliation", "").strip()[:120]
            candidate.manifesto = request.form.get("manifesto", "").strip()
            if image_name:
                candidate.profile_image = image_name
            _audit("candidate.update", f"Updated candidate {candidate.id}")
            try:
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                if image_name:
                    delete_candidate_image(destination, image_name)
                raise
            if image_name:
                delete_candidate_image(destination, old_image_name)
            flash("Candidate updated.", "success")
            return redirect(url_for("admin.candidates"))
    return render_template("edit_candidate.html", candidate=candidate)


@bp.post("/candidates/<int:candidate_id>/toggle")
@admin_required
def toggle_candidate(candidate_id):
    candidate = db.session.get(Candidate, candidate_id)
    if candidate is None:
        from flask import abort
        abort(404)
    if candidate.election.status == "open" or Vote.query.filter_by(
        election_id=candidate.election_id
    ).first():
        flash("Candidate status cannot be changed after voting starts or votes are recorded.", "danger")
        return redirect(url_for("admin.candidates"))
    candidate.is_active = not candidate.is_active
    _audit("candidate.toggle", f"Candidate {candidate.id} active={candidate.is_active}")
    db.session.commit()
    flash("Candidate status updated.", "success")
    return redirect(url_for("admin.candidates"))


@bp.route("/elections", methods=["GET", "POST"])
@admin_required
def elections():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        try:
            start = parse_local_datetime(request.form.get("start_time"))
            end = parse_local_datetime(request.form.get("end_time"))
            if end <= start:
                raise ValueError("End time must be after start time.")
            if not title or len(title) > 160:
                raise ValueError("Election title is required and limited to 160 characters.")
            election = Election(
                title=title,
                description=description,
                start_time=start,
                end_time=end,
                publish_results=request.form.get("publish_results") == "yes",
            )
            db.session.add(election)
            db.session.flush()
            _audit("election.create", f"Created election {election.id}")
            db.session.commit()
            flash("Election created in closed state.", "success")
            return redirect(url_for("admin.elections"))
        except ValueError as exc:
            flash(str(exc), "danger")
    elections = Election.query.order_by(Election.start_time.desc()).all()
    return render_template("manage_elections.html", elections=elections)


@bp.get("/voters")
@admin_required
def voters():
    voter_accounts = User.query.filter_by(role="voter").order_by(User.full_name).all()
    return render_template("manage_voters.html", voters=voter_accounts)


@bp.post("/voters/<int:user_id>/toggle")
@admin_required
def toggle_voter(user_id):
    voter = db.session.get(User, user_id)
    if voter is None or voter.role != "voter":
        from flask import abort
        abort(404)
    voter.is_active = not voter.is_active
    _audit("voter.access_toggle", f"Voter {voter.id} active={voter.is_active}")
    db.session.commit()
    flash("Voter access updated.", "success")
    return redirect(url_for("admin.voters"))


@bp.route("/elections/<int:election_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_election(election_id):
    election = db.session.get(Election, election_id)
    if election is None:
        from flask import abort
        abort(404)
    if request.method == "POST":
        try:
            start = parse_local_datetime(request.form.get("start_time"))
            end = parse_local_datetime(request.form.get("end_time"))
            title = request.form.get("title", "").strip()
            if not title or len(title) > 160 or end <= start:
                raise ValueError("Enter a title and an end time after the start time.")
            election.title = title
            election.description = request.form.get("description", "").strip()
            election.start_time = start
            election.end_time = end
            election.publish_results = request.form.get("publish_results") == "yes"
            _audit("election.update", f"Updated election {election.id}")
            db.session.commit()
            flash("Election updated.", "success")
            return redirect(url_for("admin.elections"))
        except ValueError as exc:
            flash(str(exc), "danger")
    return render_template("edit_election.html", election=election)


@bp.post("/elections/<int:election_id>/<action>")
@admin_required
def election_action(election_id, action):
    election = db.session.get(Election, election_id)
    if election is None:
        from flask import abort
        abort(404)
    if action not in {"open", "close"}:
        from flask import abort
        abort(404)
    election.status = action
    _audit(f"election.{action}", f"Changed election {election.id} to {action}")
    db.session.commit()
    flash(f"Election {action}ed.", "success")
    return redirect(url_for("admin.elections"))


@bp.get("/results/<int:election_id>/export")
@admin_required
def export_results(election_id):
    election = db.session.get(Election, election_id)
    if election is None:
        from flask import abort
        abort(404)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["Candidate", "Affiliation", "Votes"])
    counts = dict(
        db.session.query(Vote.candidate_id, func.count(Vote.id))
        .filter(Vote.election_id == election_id)
        .group_by(Vote.candidate_id)
        .all()
    )
    for candidate in Candidate.query.filter_by(election_id=election_id).order_by(Candidate.name):
        writer.writerow([
            _csv_text(candidate.name),
            _csv_text(candidate.affiliation),
            counts.get(candidate.id, 0),
        ])
    _audit("results.export", f"Exported aggregate results for election {election_id}")
    db.session.commit()
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = f'attachment; filename="election-{election_id}-results.csv"'
    return response
