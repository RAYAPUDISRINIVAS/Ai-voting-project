from flask import Blueprint, abort, render_template
from sqlalchemy import func

from admin import admin_required
from extensions import db
from models import Candidate, Election, User, Vote

bp = Blueprint("results", __name__)


def aggregate_results(election):
    totals = dict(
        db.session.query(Vote.candidate_id, func.count(Vote.id))
        .filter(Vote.election_id == election.id)
        .group_by(Vote.candidate_id)
        .all()
    )
    candidates = Candidate.query.filter_by(election_id=election.id).order_by(Candidate.name).all()
    valid_votes = sum(totals.values())
    eligible = User.query.filter_by(role="voter", is_active=True).count()
    rows = [
        {
            "candidate": candidate,
            "votes": totals.get(candidate.id, 0),
            "percentage": (totals.get(candidate.id, 0) * 100 / valid_votes)
            if valid_votes
            else 0,
        }
        for candidate in candidates
    ]
    return {
        "rows": rows,
        "valid_votes": valid_votes,
        "eligible": eligible,
        "turnout": valid_votes * 100 / eligible if eligible else 0,
    }


@bp.get("/results/<int:election_id>")
def public_results(election_id):
    election = db.session.get(Election, election_id)
    if election is None:
        abort(404)
    if not election.publish_results and election.status == "open":
        abort(403)
    return render_template(
        "results.html", election=election, results=aggregate_results(election), is_admin=False
    )


@bp.get("/admin/results/<int:election_id>")
@admin_required
def admin_results(election_id):
    election = db.session.get(Election, election_id)
    if election is None:
        abort(404)
    return render_template(
        "results.html", election=election, results=aggregate_results(election), is_admin=True
    )
