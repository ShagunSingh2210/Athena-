"""Module 3 — Citizen Health Risk Advisory (backend).

Pipeline: AQI + health profile -> risk category (CPCB breakpoints) -> LLM drafts
a personalized, multilingual advisory -> officer reviews -> approve/reject -> send.

LLM provider: Gemini (`gemini-2.5-flash` by default), not Claude — Google's Flash/
Flash-Lite models carry a genuine, no-card-required free tier, unlike the Claude
API. Two things worth knowing before you rely on this for the demo:
  1. Free-tier rate limits are modest (roughly 10-15 requests/minute, low
     hundreds to ~1,500/day depending on model) — comfortably enough for a
     hackathon demo's advisory volume, not for a production citizen base.
  2. Google's free-tier terms allow using your prompts/responses to improve
     their models. This pipeline sends health-profile fields (age group,
     conditions, pregnancy) to generate the advisory — disclose that in your
     deck's privacy/methodology section rather than letting a judge find it.
  3. Google's free-tier model lineup changes faster than most: `GEMINI_MODEL`
     in `.env` is the override point if `gemini-2.5-flash` gets sunset before
     your demo — check https://ai.google.dev/gemini-api/docs/pricing for the
     current free-tier Flash/Flash-Lite list.

`GEMINI_API_KEY` is still the one true blocker — there is no keyless substitute
for LLM generation itself, only for this being a paid vs. free key.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from config import CPCB_PM25_BREAKPOINTS, GEMINI_API_KEY, GEMINI_MODEL, HEALTH_ADVISORY_TONE, SUPPORTED_LANGUAGES

_LANGUAGE_NAMES = {"en": "English", "hi": "Hindi", "raj": "Rajasthani (Marwari-influenced Hindi register)"}


class ApprovalStatus(str, Enum):
    """Officer-approval workflow states."""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"


@dataclass
class HealthProfile:
    """Minimal citizen health profile driving advisory personalization."""

    age_group: str            # "child" | "adult" | "elderly"
    has_respiratory_condition: bool = False
    has_cardiac_condition: bool = False
    is_pregnant: bool = False


@dataclass
class AdvisoryRequest:
    """One advisory through its full lifecycle — this is the object Person B's
    officer-approval screen and citizen chat UI both read/write via the backend."""

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    cell_id: str = ""
    pm25: float = 0.0
    profile: HealthProfile | None = None
    language: str = "en"
    risk_category: str = ""
    draft_text: str = ""
    status: ApprovalStatus = ApprovalStatus.DRAFT
    officer_note: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def classify_risk_category(pm25: float) -> str:
    """Map a PM2.5 reading to its CPCB category label.

    Args:
        pm25: 24h average PM2.5 concentration in ug/m3.

    Returns:
        Category label, e.g. "Poor". Values above the top band return "Severe";
        this deliberately never returns "unknown" since every advisory needs a
        category to select a tone for.
    """
    for label, _, _, c_lo, c_hi in CPCB_PM25_BREAKPOINTS:
        if c_lo <= pm25 <= c_hi:
            return label
    return "Severe" if pm25 > CPCB_PM25_BREAKPOINTS[-1][4] else "Good"


def _build_prompt(pm25: float, category: str, profile: HealthProfile, language: str) -> str:
    risk_flags = []
    if profile.has_respiratory_condition:
        risk_flags.append("has a respiratory condition (e.g. asthma/COPD)")
    if profile.has_cardiac_condition:
        risk_flags.append("has a cardiac condition")
    if profile.is_pregnant:
        risk_flags.append("is pregnant")
    flags_text = "; ".join(risk_flags) if risk_flags else "no disclosed risk conditions"

    lang_name = _LANGUAGE_NAMES.get(language, "English")
    tone = HEALTH_ADVISORY_TONE.get(category, "cautionary")

    return f"""You are drafting a short public-health SMS advisory for a citizen in India.

Air quality: PM2.5 = {pm25:.0f} ug/m3, CPCB category = "{category}".
Recipient: {profile.age_group}, {flags_text}.
Required tone: {tone}.
Write in {lang_name}.

Constraints:
- Maximum 3 short sentences.
- Give one concrete protective action (mask type, indoor/outdoor call, medication reminder if respiratory condition disclosed).
- No alarmist language beyond what the category warrants.
- Do not mention that you are an AI.

Return only the advisory text, nothing else."""


def draft_advisory(cell_id: str, pm25: float, profile: HealthProfile,
                    language: str = "en") -> AdvisoryRequest:
    """Generate a draft advisory via the Gemini API and place it in PENDING_REVIEW.

    Args:
        cell_id: Grid cell the citizen is querying from (joins to Module 2 output).
        pm25: Current PM2.5 reading for that cell.
        profile: Citizen health profile from the chat intake form.
        language: One of `config.SUPPORTED_LANGUAGES`.

    Returns:
        An `AdvisoryRequest` with `draft_text` populated and status PENDING_REVIEW.

    Raises:
        ValueError: If `language` isn't supported, or `GEMINI_API_KEY` is unset.
        google.genai.errors.APIError: Propagated from the SDK on any API-side
            failure (including free-tier 429 rate-limit errors) — deliberately
            not swallowed here, since a citizen-facing advisory silently
            falling back to a template could give stale/wrong guidance; the
            officer-approval step is the intended safety net, not a fallback.
    """
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language {language!r}; choose from {SUPPORTED_LANGUAGES}")
    if not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY is not set. Free, no-card-required key at "
            "https://aistudio.google.com/apikey — this is the one pipeline in "
            "this codebase with no keyless fallback."
        )

    from google import genai  # local import so the rest of the package works with zero deps installed
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)
    category = classify_risk_category(pm25)
    prompt = _build_prompt(pm25, category, profile, language)

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=300, temperature=0.4),
    )
    draft_text = (response.text or "").strip()

    return AdvisoryRequest(
        cell_id=cell_id, pm25=pm25, profile=profile, language=language,
        risk_category=category, draft_text=draft_text, status=ApprovalStatus.PENDING_REVIEW,
    )


def officer_review(advisory: AdvisoryRequest, approve: bool, note: str = "") -> AdvisoryRequest:
    """Apply an officer's approve/reject decision to a pending advisory.

    Args:
        advisory: An `AdvisoryRequest` currently in PENDING_REVIEW.
        approve: True to approve, False to reject.
        note: Optional officer note (e.g. reason for rejection, edit request).

    Returns:
        The same `advisory` object, mutated in place, with updated status.

    Raises:
        ValueError: If `advisory` is not currently PENDING_REVIEW — prevents an
            already-sent or already-rejected advisory from being silently
            re-decided, which matters for the audit trail this workflow needs.
    """
    if advisory.status != ApprovalStatus.PENDING_REVIEW:
        raise ValueError(f"Cannot review advisory in status={advisory.status}; must be PENDING_REVIEW")

    advisory.status = ApprovalStatus.APPROVED if approve else ApprovalStatus.REJECTED
    advisory.officer_note = note
    return advisory


def mark_sent(advisory: AdvisoryRequest) -> AdvisoryRequest:
    """Transition an APPROVED advisory to SENT once the citizen alert dispatches.

    Args:
        advisory: An `AdvisoryRequest` currently in APPROVED status.

    Returns:
        The same `advisory` object with status SENT.

    Raises:
        ValueError: If `advisory` is not currently APPROVED.
    """
    if advisory.status != ApprovalStatus.APPROVED:
        raise ValueError(f"Cannot send advisory in status={advisory.status}; must be APPROVED")
    advisory.status = ApprovalStatus.SENT
    return advisory
