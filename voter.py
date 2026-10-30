from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from extensions import db
from models import Candidate, Election, Vote, utcnow
from services.election_service import election_status_label

bp = Blueprint("voter", __name__)


@bp.get("/dashboard")
@login_required
def dashboard():
    if current_user.role != "voter":
        abort(403)
    elections = Election.query.order_by(Election.start_time.desc()).all()
    voted_ids = {
        row[0]
        for row in db.session.query(Vote.election_id)
        .filter_by(voter_id=current_user.id)
        .all()
    }
    return render_template(
        "voter_dashboard.html",
        elections=elections,
        voted_ids=voted_ids,
        election_status_label=election_status_label,
        now=utcnow(),
    )


@bp.get("/elections/<int:election_id>/candidates")
@login_required
def candidates(election_id):
    if current_user.role != "voter":
        abort(403)
    election = db.session.get(Election, election_id)
    if election is None:
        abort(404)
    candidates = Candidate.query.filter_by(election_id=election_id, is_active=True).order_by(
        Candidate.name
    ).all()
    already_voted = Vote.query.filter_by(
        election_id=election_id, voter_id=current_user.id
    ).first() is not None
    return render_template(
        "candidates.html", election=election, candidates=candidates,
        already_voted=already_voted, now=utcnow()
    )


@bp.get("/elections/<int:election_id>/status")
@login_required
def status(election_id):
    if current_user.role != "voter":
        abort(403)
    election = db.session.get(Election, election_id)
    if election is None:
        abort(404)
    vote = Vote.query.filter_by(election_id=election_id, voter_id=current_user.id).first()
    return {
        "election_id": election.id,
        "status": election_status_label(election),
        "has_voted": vote is not None,
    }
