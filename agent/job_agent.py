#!/usr/bin/env python3
"""
Multi-User Job Search Agent
Loads all user profiles from /users/*.json, runs searches, sends digest emails.
Designed to run on GitHub Actions (free tier).

Cost-saving strategy:
  - Uses claude-haiku-4-5 for cover letters and fit analysis (cheap)
  - Uses claude-haiku-4-5 with web_search for job discovery
  - Batches all users in one run to share Action minutes
  - Skips users whose schedule doesn't match today
"""

import os
import json
import smtplib
import logging
import re
import glob
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from anthropic import Anthropic

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler("job_agent.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ── Model config (cost-optimized) ──────────────────────────────────────────────
# Haiku is ~15x cheaper than Sonnet per token. We use it for everything.
MODEL = "claude-haiku-4-5"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# ── Prompts ────────────────────────────────────────────────────────────────────

SEARCH_PROMPT = """You are a senior executive job search agent for {name}.

CANDIDATE PROFILE:
{resume}

SEARCH CRITERIA:
- Experience Level: {level}
- Target titles: {titles}
- Minimum Compensation: {salary}
- Sectors: {sectors}
- Location preference: {location}
- Special Focus: {custom_ask}
- Exclude roles containing: {exclude_keywords}
- Only roles posted within the last {recency_days} days

TODAY: {today}

Search for real, current job postings matching these criteria on LinkedIn, Indeed, company career pages, and industry-specific boards.

Return ONLY a valid JSON object (no markdown fences, no preamble):
{{
  "positive_message": "2-3 warm, specific, encouraging sentences for {name} referencing their career impact and today's date.",
  "jobs": [
    {{
      "title": "Job Title",
      "organization": "Company Name",
      "type": "Full-time",
      "location": "Remote / Hybrid — City, State",
      "salary": "$160,000–$185,000 + bonus",
      "posted": "2 days ago",
      "source": "LinkedIn",
      "description": "2-3 sentence role summary.",
      "why_fit": "2-3 sentences tying the candidate's specific experience to this role.",
      "network_angle": "1-2 sentences on network leverage.",
      "apply_url": "https://..."
    }}
  ],
  "proactive_targets": [
    {{
      "organization": "Organization Name",
      "sector": "Tech / Association / Hospitality / Corporate",
      "why": "2 sentences on fit.",
      "approach": "1 sentence on how to reach out.",
      "contact_type": "e.g. VP of HR, Chief of Staff"
    }}
  ]
}}

Find 3-5 matched roles and 3-5 proactive targets. Be specific — real org names, real URLs where possible."""

COVER_LETTER_PROMPT = """Write a concise, compelling cover letter for {name} applying to the role of {title} at {organization}.

CANDIDATE RESUME:
{resume}

ROLE CONTEXT:
{description}

WHY THEY FIT:
{why_fit}

Guidelines:
- 3 short paragraphs: hook, value proposition, close
- Confident but not generic
- Reference 1-2 specific accomplishments from the resume that map directly to the role
- Do NOT use the phrase "I am excited to apply" or any cliché opener
- Keep under 250 words
- Sign off with the candidate's name

Return ONLY the cover letter text, no subject line, no labels."""

APPLICATION_PROMPT = """You are helping {name} fill out a job application for {title} at {organization}.

CANDIDATE RESUME:
{resume}

Generate pre-filled answers for the most common job application fields. Return ONLY a valid JSON object:
{{
  "full_name": "",
  "email": "",
  "phone": "",
  "linkedin_url": "",
  "portfolio_url": "",
  "address": "",
  "desired_salary": "",
  "availability": "",
  "years_of_experience": "",
  "highest_education": "",
  "work_authorization": "Yes - US Citizen",
  "willing_to_relocate": "",
  "open_to_travel": "",
  "referral_source": "Job Search Agent",
  "why_interested": "2-3 sentence answer for 'Why are you interested in this role?'",
  "biggest_achievement": "2-3 sentence answer for 'Describe your biggest professional achievement'",
  "leadership_style": "2-3 sentence answer for 'Describe your leadership style'",
  "salary_expectations": "A professional answer to 'What are your salary expectations?'"
}}

Fill every field using information from the resume. For fields not in the resume (phone, email, linkedin), use placeholders like '[your phone]'."""


# ── HTML Templates ──────────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  body {{ margin:0; padding:0; background:#f5f4f0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; color:#2c2c2a; }}
  .wrapper {{ max-width:680px; margin:0 auto; padding:24px 16px; }}
  .header {{ background:#2c2c2a; border-radius:12px 12px 0 0; padding:28px 32px; }}
  .header h1 {{ color:#fff; font-size:20px; font-weight:500; margin:0 0 4px; }}
  .header p {{ color:#b4b2a9; font-size:13px; margin:0; }}
  .positive {{ background:#E1F5EE; padding:20px 32px; border-bottom:0.5px solid #9FE1CB; }}
  .positive p {{ color:#085041; font-size:15px; line-height:1.7; margin:0; }}
  .body {{ background:#fff; padding:24px 32px; border-radius:0 0 12px 12px; }}
  .section-label {{ font-size:11px; font-weight:500; color:#888780; text-transform:uppercase; letter-spacing:0.06em; margin:0 0 16px; border-bottom:0.5px solid #D3D1C7; padding-bottom:8px; }}
  .job-card {{ border:0.5px solid #D3D1C7; border-radius:10px; padding:18px 20px; margin-bottom:16px; }}
  .job-title {{ font-size:16px; font-weight:500; margin:0 0 3px; }}
  .job-org {{ font-size:14px; color:#5F5E5A; margin:0 0 10px; }}
  .badge {{ display:inline-block; font-size:11px; padding:2px 8px; border-radius:4px; font-weight:500; margin:0 4px 4px 0; }}
  .badge-teal {{ background:#E1F5EE; color:#0F6E56; }}
  .badge-purple {{ background:#EEEDFE; color:#3C3489; }}
  .badge-gray {{ background:#F1EFE8; color:#444441; }}
  .badge-blue {{ background:#E6F1FB; color:#185FA5; }}
  .field-label {{ font-size:11px; font-weight:500; color:#888780; text-transform:uppercase; letter-spacing:0.04em; margin:10px 0 3px; }}
  .field-text {{ font-size:14px; line-height:1.6; color:#2c2c2a; }}
  .apply-btn {{ display:inline-block; margin-top:12px; background:#2c2c2a; color:#fff !important; text-decoration:none; padding:8px 16px; border-radius:6px; font-size:13px; font-weight:500; }}
  .cover-letter-box {{ background:#FAFAF8; border:0.5px solid #D3D1C7; border-radius:8px; padding:16px 20px; margin-top:12px; font-size:13px; line-height:1.8; color:#3a3a38; white-space:pre-wrap; }}
  .app-fields {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:12px; }}
  .app-field {{ background:#F8F8F6; border-radius:6px; padding:8px 12px; }}
  .app-field-label {{ font-size:10px; color:#888780; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:2px; }}
  .app-field-value {{ font-size:13px; color:#2c2c2a; }}
  .divider {{ border:none; border-top:0.5px solid #D3D1C7; margin:24px 0; }}
  .proactive-item {{ padding:14px 0; border-bottom:0.5px solid #F1EFE8; }}
  .proactive-item:last-child {{ border-bottom:none; }}
  .proactive-org {{ font-size:15px; font-weight:500; margin:0 0 2px; }}
  .proactive-sector {{ font-size:12px; color:#888780; margin:0 0 6px; }}
  .proactive-text {{ font-size:13px; line-height:1.6; color:#5F5E5A; }}
  .footer {{ text-align:center; padding:20px 0 0; font-size:12px; color:#888780; }}
  .collapsible-toggle {{ font-size:12px; color:#185FA5; cursor:pointer; margin-top:8px; display:inline-block; }}
</style>
</head>
<body>
<div class="wrapper">
  <div class="header">
    <h1>{name}'s Job Search Digest</h1>
    <p>{today} &nbsp;·&nbsp; {job_count} roles matched &nbsp;·&nbsp; {proactive_count} proactive targets</p>
  </div>
  <div class="positive"><p>{positive_message}</p></div>
  <div class="body">
    <p class="section-label" style="margin-top:0;">Matched roles</p>
    {jobs_html}
    <hr class="divider">
    <p class="section-label">Proactive outreach</p>
    {proactive_html}
    <hr class="divider">
    <div class="footer">
      <p>Digest generated by your personal job search agent.</p>
      <p style="margin-top:4px; color:#aaa;">Filtered for {salary_min}+ · {location} · Posted within {recency_days} days</p>
    </div>
  </div>
</div>
</body>
</html>"""

JOB_HTML = """<div class="job-card">
  <div class="job-title">{title}</div>
  <div class="job-org">{organization}</div>
  <div style="margin-bottom:10px;">
    <span class="badge badge-teal">{location}</span>
    <span class="badge badge-purple">{salary}</span>
    <span class="badge badge-gray">{posted}</span>
    <span class="badge badge-blue">{source}</span>
  </div>
  <div class="field-label">Role overview</div>
  <div class="field-text">{description}</div>
  <div class="field-label">Why it fits you</div>
  <div class="field-text">{why_fit}</div>
  <div class="field-label">Network angle</div>
  <div class="field-text">{network_angle}</div>
  <hr style="border:none; border-top:0.5px solid #eee; margin:14px 0;">
  <div class="field-label">📝 Cover Letter</div>
  <div class="cover-letter-box">{cover_letter}</div>
  <hr style="border:none; border-top:0.5px solid #eee; margin:14px 0;">
  <div class="field-label">📋 Application Quick-Fill</div>
  <div class="app-fields">
    <div class="app-field"><div class="app-field-label">Desired Salary</div><div class="app-field-value">{app_salary}</div></div>
    <div class="app-field"><div class="app-field-label">Availability</div><div class="app-field-value">{app_availability}</div></div>
    <div class="app-field"><div class="app-field-label">Years of Experience</div><div class="app-field-value">{app_years}</div></div>
    <div class="app-field"><div class="app-field-label">Willing to Relocate</div><div class="app-field-value">{app_relocate}</div></div>
  </div>
  <div class="field-label" style="margin-top:12px;">Why Interested (pre-written answer)</div>
  <div class="field-text" style="font-style:italic;">{app_why_interested}</div>
  <div class="field-label">Biggest Achievement (pre-written answer)</div>
  <div class="field-text" style="font-style:italic;">{app_achievement}</div>
  <a class="apply-btn" href="{apply_url}" style="margin-top:16px; display:inline-block;">Apply → {organization}</a>
</div>"""

PROACTIVE_HTML = """<div class="proactive-item">
  <div class="proactive-org">{organization}</div>
  <div class="proactive-sector">{sector}</div>
  <div class="proactive-text">{why}</div>
  <div class="proactive-text" style="margin-top:4px;"><strong>Approach:</strong> {approach}</div>
  <div class="proactive-text"><strong>Contact:</strong> {contact_type}</div>
</div>"""


# ── Core agent logic ────────────────────────────────────────────────────────────

def should_run_today(schedule: str) -> bool:
    """
    Check if this user's schedule matches today.
    Supported: 'daily', 'weekly' (runs Mondays), 'biweekly' (runs Mon of weeks 1&3),
               day names like 'monday', 'tuesday', etc.
    """
    today = datetime.now(timezone.utc)
    day_name = today.strftime("%A").lower()
    week_of_month = (today.day - 1) // 7 + 1

    schedule = schedule.lower().strip()
    if schedule == "daily":
        return True
    if schedule == "weekly":
        return day_name == "monday"
    if schedule == "biweekly":
        return day_name == "monday" and week_of_month in (1, 3)
    # named day
    return day_name == schedule


def load_users(users_dir: str) -> list[dict]:
    """Load all user profile JSON files from the users/ directory."""
    profiles = []
    for path in glob.glob(os.path.join(users_dir, "*.json")):
        try:
            with open(path) as f:
                profile = json.load(f)
            profile["_file"] = path
            profiles.append(profile)
            log.info(f"Loaded user: {profile.get('name', path)}")
        except Exception as e:
            log.error(f"Failed to load {path}: {e}")
    return profiles


def call_claude(client: Anthropic, prompt: str, use_web_search: bool = False) -> str:
    """Make a Claude API call, optionally with web search. Returns text."""
    kwargs = dict(
        model=MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    if use_web_search:
        kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]

    response = client.messages.create(**kwargs)

    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text += block.text
    return text.strip()


def parse_json_response(text: str) -> dict:
    """Robustly extract JSON from a Claude response."""
    clean = text.replace("```json", "").replace("```", "").strip()
    start = clean.find("{")
    end = clean.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON found. Raw:\n{text[:400]}")
    return json.loads(clean[start:end])


def run_search(client: Anthropic, profile: dict, today_str: str) -> dict:
    """Run the job search for one user."""
    criteria = profile.get("criteria", {})
    prompt = SEARCH_PROMPT.format(
        name=profile["name"],
        resume=profile.get("resume", ""),
        level=criteria.get("experience_level", "Senior"),
        titles=", ".join(criteria.get("target_titles", [])),
        salary=criteria.get("min_salary", "Not specified"),
        sectors=", ".join(criteria.get("industry_focus", [])),
        location=criteria.get("location_preference", "Remote"),
        custom_ask=criteria.get("special_instructions", ""),
        exclude_keywords=", ".join(criteria.get("exclude_keywords", [])),
        recency_days=criteria.get("recency_days", 7),
        today=today_str,
    )
    log.info(f"  Searching jobs for {profile['name']}...")
    text = call_claude(client, prompt, use_web_search=True)
    return parse_json_response(text)


def generate_cover_letter(client: Anthropic, profile: dict, job: dict) -> str:
    """Generate a cover letter for one job."""
    prompt = COVER_LETTER_PROMPT.format(
        name=profile["name"],
        title=job.get("title", ""),
        organization=job.get("organization", ""),
        resume=profile.get("resume", ""),
        description=job.get("description", ""),
        why_fit=job.get("why_fit", ""),
    )
    return call_claude(client, prompt)


def generate_application_prefill(client: Anthropic, profile: dict, job: dict) -> dict:
    """Generate pre-filled application answers for one job."""
    prompt = APPLICATION_PROMPT.format(
        name=profile["name"],
        title=job.get("title", ""),
        organization=job.get("organization", ""),
        resume=profile.get("resume", ""),
    )
    text = call_claude(client, prompt)
    try:
        return parse_json_response(text)
    except Exception:
        return {}


def build_html_email(profile: dict, data: dict, today_str: str) -> str:
    criteria = profile.get("criteria", {})
    jobs = data.get("jobs", [])
    proactive = data.get("proactive_targets", [])
    positive = data.get("positive_message", "Your next chapter is closer than you think.")

    jobs_html_parts = []
    for j in jobs:
        cover_letter = j.get("_cover_letter", "")
        app = j.get("_application", {})
        jobs_html_parts.append(JOB_HTML.format(
            title=j.get("title", ""),
            organization=j.get("organization", ""),
            location=j.get("location", ""),
            salary=j.get("salary", "Not listed"),
            posted=j.get("posted", ""),
            source=j.get("source", ""),
            description=j.get("description", ""),
            why_fit=j.get("why_fit", ""),
            network_angle=j.get("network_angle", ""),
            apply_url=j.get("apply_url", "#"),
            cover_letter=cover_letter.replace("\n", "<br>") if cover_letter else "—",
            app_salary=app.get("desired_salary", criteria.get("min_salary", "")),
            app_availability=app.get("availability", "2–4 weeks"),
            app_years=app.get("years_of_experience", ""),
            app_relocate=app.get("willing_to_relocate", "Open to discussion"),
            app_why_interested=app.get("why_interested", ""),
            app_achievement=app.get("biggest_achievement", ""),
        ))

    proactive_html_parts = [
        PROACTIVE_HTML.format(
            organization=p.get("organization", ""),
            sector=p.get("sector", ""),
            why=p.get("why", ""),
            approach=p.get("approach", ""),
            contact_type=p.get("contact_type", ""),
        )
        for p in proactive
    ]

    return HTML_TEMPLATE.format(
        name=profile["name"],
        today=today_str,
        job_count=len(jobs),
        proactive_count=len(proactive),
        positive_message=positive,
        jobs_html="".join(jobs_html_parts),
        proactive_html="".join(proactive_html_parts),
        salary_min=criteria.get("min_salary", ""),
        location=criteria.get("location_preference", ""),
        recency_days=criteria.get("recency_days", 7),
    )


def build_plain_text(profile: dict, data: dict, today_str: str) -> str:
    jobs = data.get("jobs", [])
    proactive = data.get("proactive_targets", [])
    positive = data.get("positive_message", "")

    lines = [
        f"{profile['name'].upper()}'S JOB SEARCH DIGEST — {today_str}",
        "=" * 60, "", positive, "",
        f"{len(jobs)} MATCHED ROLES", "=" * 60,
    ]
    for i, j in enumerate(jobs, 1):
        lines += [
            f"\n{i}. {j.get('title')} — {j.get('organization')}",
            f"   {j.get('location')} | {j.get('salary')} | {j.get('posted')}",
            f"   Source: {j.get('source')}",
            f"\n   Role: {j.get('description')}",
            f"\n   Why it fits: {j.get('why_fit')}",
            f"\n   Network angle: {j.get('network_angle')}",
            f"\n   Apply: {j.get('apply_url')}",
        ]
        if j.get("_cover_letter"):
            lines += ["\n   COVER LETTER:", "   " + j["_cover_letter"].replace("\n", "\n   ")]
        lines.append("\n" + "-" * 60)

    lines += ["", "PROACTIVE OUTREACH", "=" * 60]
    for i, p in enumerate(proactive, 1):
        lines += [
            f"\n{i}. {p.get('organization')} ({p.get('sector')})",
            f"   {p.get('why')}",
            f"   Approach: {p.get('approach')}",
            f"   Contact: {p.get('contact_type')}",
        ]
    return "\n".join(lines)


def send_email(profile: dict, subject: str, html_body: str, plain_body: str) -> None:
    sender = os.getenv("GMAIL_SENDER")
    password = os.getenv("GMAIL_APP_PASSWORD")
    recipient = profile.get("email")

    if not all([sender, password, recipient]):
        raise ValueError(f"Missing email config for {profile['name']}: sender={sender}, recipient={recipient}")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    log.info(f"  Sending email to {recipient}...")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, recipient, msg.as_string())
    log.info(f"  Email sent to {recipient}")


def process_user(client: Anthropic, profile: dict, today_str: str) -> None:
    name = profile.get("name", "Unknown")
    log.info(f"\n{'='*50}")
    log.info(f"Processing: {name}")

    schedule = profile.get("schedule", "weekly")
    if not should_run_today(schedule):
        log.info(f"  Skipping {name} — schedule '{schedule}' doesn't match today")
        return

    try:
        # 1. Search for jobs
        data = run_search(client, profile, today_str)
        jobs = data.get("jobs", [])
        log.info(f"  Found {len(jobs)} jobs")

        # 2. Generate cover letter + application prefill for each job
        for j in jobs:
            log.info(f"  Generating cover letter for: {j.get('title')} @ {j.get('organization')}")
            j["_cover_letter"] = generate_cover_letter(client, profile, j)
            j["_application"] = generate_application_prefill(client, profile, j)

        # 3. Build and send email
        html = build_html_email(profile, data, today_str)
        plain = build_plain_text(profile, data, today_str)
        subject = f"{name}'s Job Search Digest — {datetime.now().strftime('%b %d')}"
        send_email(profile, subject, html, plain)

    except Exception as e:
        log.error(f"  Failed for {name}: {e}", exc_info=True)


def main():
    today_str = datetime.now().strftime("%A, %B %d, %Y")
    log.info(f"=== Multi-User Job Search Agent — {today_str} ===")

    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    # Users directory: sibling of this script
    users_dir = os.path.join(os.path.dirname(__file__), "..", "users")
    users_dir = os.path.abspath(users_dir)
    log.info(f"Loading users from: {users_dir}")

    profiles = load_users(users_dir)
    if not profiles:
        log.warning("No user profiles found. Add JSON files to the users/ directory.")
        return

    log.info(f"Loaded {len(profiles)} user(s)")
    for profile in profiles:
        process_user(client, profile, today_str)

    log.info("\n=== All users processed ===")


if __name__ == "__main__":
    main()
