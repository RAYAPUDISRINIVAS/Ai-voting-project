from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import Candidate, Election, Vote, utcnow
from services.voting_service import VoteError, cast_vote

bp = Blueprint("voting", __name__)


@bp.route("/elections/<int:election_id>/vote", methods=["GET", "POST"])
@login_required
def vote(election_id):
    if current_user.role != "voter":
        abort(403)
    election = db.session.get(Election, election_id)
    if election is None:
        abort(404)
    if request.method == "GET":
        candidate_id = request.args.get("candidate_id", type=int)
        candidate = db.session.get(Candidate, candidate_id) if candidate_id else None
        if (
            candidate is None
            or candidate.election_id != election_id
            or not candidate.is_active
        ):
            abort(404)
        return render_template("confirm_vote.html", election=election, candidate=candidate)

    candidate_id = request.form.get("candidate_id", type=int)
    if candidate_id is None:
        abort(400)
    try:
        cast_vote(
            election_id=election_id,
            voter_id=current_user.id,
            candidate_id=candidate_id,
            now=utcnow(),
        )
    except VoteError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("voter.candidates", election_id=election_id))
    return render_template("vote_success.html", election=election)
