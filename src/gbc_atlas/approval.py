"""Recorded human approval verification."""

from ._validation import require
from .model import Atlas


def verify_approval(data: Atlas) -> None:
    """Verify recorded approval evidence against this pack; never grant approval."""
    m, digest = data.manifest, data.digest
    approval = m.get("approval", {})
    require(
        approval.get("status") == "approved" and approval.get("digest") == digest,
        "Missing or stale approval: review this exact revision before generation",
    )
    require(
        all(
            isinstance(approval.get(k), str) and approval[k].strip()
            for k in ("by", "date", "evidence")
        ),
        "Record who approved, when, and their approval evidence",
    )
