#!/usr/bin/env python3
"""
Daily Job Search Agent
Runs weekly, searches for senior event executive roles,
and sends a digest email via Gmail.
"""

import os
import json
import smtplib
import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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

ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY")
GMAIL_SENDER        = os.getenv("GMAIL_SENDER")
GMAIL_APP_PASSWORD  = os.getenv("GMAIL_APP_PASSWORD")
RECIPIENT_EMAIL     = os.getenv("RECIPIENT_EMAIL")
RESUME_CONTENT     = os.getenv("RESUME_CONTENT")
CRITERIA_CONTENT   = json.loads(os.getenv("CRITERIA_CONTENT"))

SEARCH_PROMPT = """ You are a senior executive job search agent for {name}.

CANDIDATE PROFILE:
{resume}

SEARCH CRITERIA:
- Experience Level: {level}
- Target titles: {titles}
- Minimum Compensation: {salary}
- Sectors: {sectors}
- Location preference: {location}
- Special Focus: {custom_ask}

SOURCES: LinkedIn, Industry Boards, and Company Career Pages.

TODAY: {today}

Generate a realistic, detailed job search result set...
1. Matched Roles: List 3-5 roles that best fit the criteria. For each role, provide:
   - Title, Organization, Location, Salary, Posted Date, Source
   - A brief description of the role
   - Why it fits the candidate's profile
   - A potential network angle (e.g., "Alumni from X university work here")
   - A direct apply URL
2. Proactive Targets: List 3-5 organizations that don't have open roles but are a strong fit based on the candidate's profile. For each, provide:
   - Organization name, Sector, Email or LinkedIn contact type

Respond ONLY with a valid JSON object (no markdown fences, no preamble). Structure:
{{
  "positive_message": "2-3 warm, specific, encouraging sentences for LaTonya referencing her career impact and today's date.",
  "jobs": [
    {{
      "title": "Job Title",
      "organization": "Company Name",
      "type": "Full-time",
      "location": "Remote / Hybrid — City, State / On-site — City, State",
      "salary": "$160,000–$185,000 + bonus" or "Not listed",
      "posted": "2 days ago",
      "source": "LinkedIn / etc.",
      "description": "2-3 sentence role summary.",
      "why_fit": "2-3 sentences tying user's specific experience to this role.",
      "network_angle": "1-2 sentences on any network leverage they may have.",
      "apply_url": "https://..."
    }}
  ],
  "proactive_targets": [
    {{
      "organization": "Organization Name",
      "sector": "Tech / Association / Hospitality / Corporate",
      "why": "2 sentences on fit and what kind of role to pitch.",
      "approach": "1 sentence on how to reach out.",
      "contact_type": "e.g. VP of HR, Chief of Staff, Director of Operations"
    }}
  ]
}}
"""

# ── HTML email template ─────────────────────────────────────────────────────────
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Job Search Digest</title>
<style>
  body {{ margin:0; padding:0; background:#f5f4f0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; color:#2c2c2a; }}
  .wrapper {{ max-width:680px; margin:0 auto; padding:24px 16px; }}
  .header {{ background:#2c2c2a; border-radius:12px 12px 0 0; padding:28px 32px; }}
  .header h1 {{ color:#fff; font-size:20px; font-weight:500; margin:0 0 4px; }}
  .header p {{ color:#b4b2a9; font-size:13px; margin:0; }}
  .positive {{ background:#E1F5EE; border-radius:0; padding:20px 32px; border-bottom:0.5px solid #9FE1CB; }}
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
  .meta {{ margin-bottom:12px; }}
  .field-label {{ font-size:11px; font-weight:500; color:#888780; text-transform:uppercase; letter-spacing:0.04em; margin:10px 0 3px; }}
  .field-text {{ font-size:14px; line-height:1.6; color:#2c2c2a; }}
  .apply-btn {{ display:inline-block; margin-top:12px; background:#2c2c2a; color:#fff !important; text-decoration:none; padding:8px 16px; border-radius:6px; font-size:13px; font-weight:500; }}
  .divider {{ border:none; border-top:0.5px solid #D3D1C7; margin:24px 0; }}
  .proactive-item {{ padding:14px 0; border-bottom:0.5px solid #F1EFE8; }}
  .proactive-item:last-child {{ border-bottom:none; }}
  .proactive-org {{ font-size:15px; font-weight:500; margin:0 0 2px; }}
  .proactive-sector {{ font-size:12px; color:#888780; margin:0 0 6px; }}
  .proactive-text {{ font-size:13px; line-height:1.6; color:#5F5E5A; }}
  .footer {{ text-align:center; padding:20px 0 0; font-size:12px; color:#888780; }}
</style>
</head>
<body>
<div class="wrapper">
  <div class="header">
    <h1>LaTonya's Job Search Digest</h1>
    <p>{today} &nbsp;·&nbsp; {job_count} roles matched &nbsp;·&nbsp; 5 proactive targets</p>
  </div>

  <div class="positive">
    <p>{positive_message}</p>
  </div>

  <div class="body">
    <p class="section-label" style="margin-top:0;">Today's matched roles</p>

    {jobs_html}

    <hr class="divider">
    <p class="section-label">Proactive outreach — follow up even with no open posting</p>

    {proactive_html}

    <hr class="divider">
    <div class="footer">
      <p>Filtered for {salary}+ &nbsp;·&nbsp; {location} &nbsp;·&nbsp; Posted within {recency} days</p>
      <p style="margin-top:4px;">Digest generated by your personal job search agent.</p>
    </div>
  </div>
</div>
</body>
</html>"""

JOB_HTML = """
<div class="job-card">
  <div class="job-title">{title}</div>
  <div class="job-org">{organization}</div>
  <div class="meta">
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
  <a class="apply-btn" href="{apply_url}">Apply →</a>
</div>
"""

PROACTIVE_HTML = """
<div class="proactive-item">
  <div class="proactive-org">{organization}</div>
  <div class="proactive-sector">{sector}</div>
  <div class="proactive-text">{why}</div>
  <div class="proactive-text" style="margin-top:4px;"><strong>Approach:</strong> {approach}</div>
  <div class="proactive-text"><strong>Contact:</strong> {contact_type}</div>
</div>
"""

def run_search(today_str: str) -> dict:
    """Call Anthropic API with web search to generate job listings."""
    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = SEARCH_PROMPT.format(
    name=CRITERIA_CONTENT["candidate_name"],
        resume=RESUME_CONTENT,
        level=CRITERIA_CONTENT["experience_level"],
        titles=", ".join(CRITERIA_CONTENT["target_titles"]),
        salary=CRITERIA_CONTENT["min_salary"],
        sectors=", ".join(CRITERIA_CONTENT["industry_focus"]),
        location=CRITERIA_CONTENT["location_preference"],
        custom_ask=CRITERIA_CONTENT["special_instructions"],
        today=today_str
    )

    log.info("Calling Anthropic API with web search enabled...")
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )

    # Collect all text blocks (web search results feed back in automatically)
    text = ""
    for block in response.content:
        if block.type == "text":
            text += block.text

    # Strip any accidental markdown fences
    clean = text.strip().replace("```json", "").replace("```", "").strip()

    # Find the JSON object
    start = clean.find("{")
    end = clean.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON found in response. Raw text:\n{text[:500]}")

    return json.loads(clean[start:end])


def build_html_email(data: dict, today_str: str) -> str:
    jobs = data.get("jobs", [])
    proactive = data.get("proactive_targets", [])
    positive = data.get("positive_message", "Today is a great day to move forward. Your next chapter is waiting.")

    jobs_html = "".join(
        JOB_HTML.format(
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
        )
        for j in jobs
    )

    proactive_html = "".join(
        PROACTIVE_HTML.format(
            organization=p.get("organization", ""),
            sector=p.get("sector", ""),
            why=p.get("why", ""),
            approach=p.get("approach", ""),
            contact_type=p.get("contact_type", ""),
        )
        for p in proactive
    )

    return HTML_TEMPLATE.format(
        today=today_str,
        job_count=len(jobs),
        positive_message=positive,
        jobs_html=jobs_html,
        proactive_html=proactive_html,
    )


def build_plain_text(data: dict, today_str: str) -> str:
    jobs = data.get("jobs", [])
    proactive = data.get("proactive_targets", [])
    positive = data.get("positive_message", "")

    lines = [
        f"LATONYA'S JOB SEARCH DIGEST — {today_str}",
        "=" * 60,
        "",
        positive,
        "",
        f"{len(jobs)} MATCHED ROLES",
        "=" * 60,
    ]

    for i, j in enumerate(jobs, 1):
        lines += [
            f"\n{i}. {j.get('title')} — {j.get('organization')}",
            f"   {j.get('location')} | {j.get('salary')} | {j.get('posted')}",
            f"   Source: {j.get('source')}",
            f"\n   Role: {j.get('description')}",
            f"\n   Why it fits you: {j.get('why_fit')}",
            f"\n   Network angle: {j.get('network_angle')}",
            f"\n   Apply: {j.get('apply_url')}",
            "\n" + "-" * 60,
        ]

    lines += ["", "PROACTIVE OUTREACH TARGETS", "=" * 60]
    for i, p in enumerate(proactive, 1):
        lines += [
            f"\n{i}. {p.get('organization')} ({p.get('sector')})",
            f"   {p.get('why')}",
            f"   Approach: {p.get('approach')}",
            f"   Contact: {p.get('contact_type')}",
        ]

    lines += [
        "",
        "=" * 60,
        "Filtered for $150K+ | Remote/Hybrid ≤30mi Winston-Salem | Posted within 7 days",
    ]
    return "\n".join(lines)


def send_email(subject: str, html_body: str, plain_body: str) -> None:
    """Send the digest via Gmail SMTP with App Password."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_SENDER
    msg["To"]      = RECIPIENT_EMAIL

    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    log.info(f"Sending email to {RECIPIENT_EMAIL}...")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_SENDER, RECIPIENT_EMAIL, msg.as_string())
    log.info("Email sent successfully.")


def main():
    today_str = datetime.now().strftime("%A, %B %d, %Y")
    subject   = f"Your Job Search Digest — {datetime.now().strftime('%b %d')}"

    log.info(f"=== Job Search Agent starting — {today_str} ===")

    try:
        data       = run_search(today_str)
        html_body  = build_html_email(data, today_str)
        plain_body = build_plain_text(data, today_str)
        send_email(subject, html_body, plain_body)
        log.info("=== Run complete ===")
    except Exception as e:
        log.error(f"Agent failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
