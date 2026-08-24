"""
Profile Completion Service

Computes a real completion score from whichever User/UserProfile fields
are actually filled in - no fixed/fabricated percentage. Deliberately
non-LLM: every check here is a plain truthiness test, the same
"heuristic over LLM call" reasoning RAG.services.dynamic_topk_service
already documents for why a per-request scoring decision shouldn't cost
a network round trip.

One implementation, two callers (RAG.views.profile_view and
admin_user_profile_view) - never two completion calculations that could
drift apart.
"""

# (label, checker(user, profile) -> bool) - equal weight, no fabricated
# bonus scoring. Order also drives the "Missing" checklist order.
PROFILE_FIELDS = [
    ("Full Name", lambda user, profile: bool(user.first_name and user.last_name)),
    ("Profile Photo", lambda user, profile: bool(profile.avatar)),
    ("Professional Headline", lambda user, profile: bool(profile.headline)),
    ("Phone Number", lambda user, profile: bool(profile.phone)),
    ("Department", lambda user, profile: bool(profile.department)),
    ("Job Title", lambda user, profile: bool(profile.job_title)),
    ("Location", lambda user, profile: bool(profile.location)),
    ("Time Zone", lambda user, profile: bool(profile.timezone)),
    ("Skills & Expertise", lambda user, profile: bool(profile.skills)),
    ("Manager", lambda user, profile: profile.manager_id is not None),
    ("LinkedIn Profile", lambda user, profile: bool(profile.linkedin_url)),
    ("GitHub or Portfolio Link", lambda user, profile: bool(profile.github_url or profile.portfolio_url)),
]

# Short, deterministic nudge per missing field - no LLM call.
_RECOMMENDATIONS = {
    "Full Name": "Add your first and last name so teammates can find you.",
    "Profile Photo": "Upload a profile photo to help teammates recognize you.",
    "Professional Headline": "Add a one-line headline so teammates know your role at a glance.",
    "Phone Number": "Add a phone number for account recovery and team contact.",
    "Department": "Set your department to help with org-wide search and filtering.",
    "Job Title": "Add your job title so your role is clear across the workspace.",
    "Location": "Add your location to help with timezone-aware scheduling.",
    "Time Zone": "Set your time zone so meeting times and timestamps display correctly for you.",
    "Skills & Expertise": "List your skills so teammates can find the right expert.",
    "Manager": "Set your manager to complete your place in the org structure.",
    "LinkedIn Profile": "Link your LinkedIn profile for professional networking.",
    "GitHub or Portfolio Link": "Link your GitHub or portfolio to showcase your work.",
}


def get_completion(user, profile):
    """
    Returns {"percent", "filled", "total", "missing", "recommendations"}
    computed fresh from the real field values on `user`/`profile` -
    never a stored or hardcoded number.
    """

    missing = []
    filled = 0

    for label, check in PROFILE_FIELDS:
        try:
            is_filled = bool(check(user, profile))
        except Exception:
            is_filled = False

        if is_filled:
            filled += 1
        else:
            missing.append(label)

    total = len(PROFILE_FIELDS)
    percent = round((filled / total) * 100) if total else 0

    return {
        "percent": percent,
        "filled": filled,
        "total": total,
        "missing": missing,
        "recommendations": [_RECOMMENDATIONS[label] for label in missing],
        # (label, recommendation) pairs - lets a template show the tip as
        # a tooltip on the missing-field chip without needing its own
        # separate list (and the vertical space that takes).
        "missing_with_tips": [(label, _RECOMMENDATIONS[label]) for label in missing],
    }
