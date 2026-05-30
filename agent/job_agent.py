#!/usr/bin/env python3
"""
Multi-User Job Search Agent — Private Repo Edition
====================================================
All user data lives in GitHub Secrets (encrypted), never in committed files.
Each user is one GitHub Secret named USER_<SLUG> containing their full JSON profile.

The agent discovers users by iterating env vars that start with USER_.

Cost strategy: claude-haiku-4-5 throughout (~15x cheaper than Sonnet).
Cover letters and app pre-fill are generated per-job, in parallel within each user run.
"""

import os
import json
import smtplib
import logging
import glob
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from anthropic import Anthropic

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.FileHandler("job_agent.log"), logging.StreamHandler()],
)
log = logging.getLogger(__name__)

MODEL           = "claude-haiku-4-5"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GMAIL_SENDER      = os.getenv("GMAIL_SENDER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")


# ── SOURCE MAP ────────────────────────────────────────────────────────────────
# Maps industry keywords → specific job boards and career pages to search.
# The agent injects the relevant sources into its search prompt so Claude knows
# exactly WHERE to look, not just what to look for.

SOURCE_MAP = {
    "Associations": [
        "careers.asaecenter.org",
        "jobs.associationcareernetwork.com",
        "nonprofitjobs.org",
        "idealist.org",
        "forumone.com/jobs",
        "jobs.councilofnonprofits.org",
    ],
    "Tech": [
        "linkedin.com/jobs",
        "greenhouse.io",
        "lever.co",
        "wellfound.com",
        "ycombinator.com/jobs",
        "builtin.com",
        "dice.com",
    ],
    "Hospitality": [
        "hcareers.com",
        "hospitalityonline.com",
        "hospitalityjobbase.com",
        "hirequest.com",
        "meetings.net/jobs",
        "mpiweb.org/careers",
        "pcma.org/career-center",
    ],
    "Events": [
        "mpiweb.org/careers",
        "pcma.org/career-center",
        "icesap.org/careers",
        "smartmeetings.com/jobs",
        "bizbash.com/jobs",
        "meetingsnet.com/jobs",
        "cvent.com/en/careers",
    ],
    "Foundations": [
        "philanthropy.com/jobs",
        "idealist.org",
        "exponentphilanthropy.org/jobs",
        "glasspockets.org",
        "grantstation.com/funding-opportunity",
        "compasspoint.org/jobs",
    ],
    "Corporate": [
        "linkedin.com/jobs",
        "indeed.com",
        "glassdoor.com/Jobs",
        "ziprecruiter.com",
        "careerbuilder.com",
    ],
    "Nonprofit": [
        "idealist.org",
        "devex.com/jobs",
        "nonprofitjobs.org",
        "workforgood.org",
        "bridgespan.org/insights/jobs",
        "guidestar.org/nonprofit-jobs",
    ],
    "Healthcare": [
        "healthcarejobsite.com",
        "healthjobsnationwide.com",
        "practicematch.com",
        "hirequest.com",
        "linkedin.com/jobs",
    ],
    "Education": [
        "higheredjobs.com",
        "chronicle.com/jobs",
        "edjoin.org",
        "k12jobspot.com",
        "linkedin.com/jobs",
    ],
    "Finance": [
        "efinancialcareers.com",
        "linkedin.com/jobs",
        "indeed.com",
        "buysidehiring.com",
        "selbyjennings.com",
    ],
    "Fintech": [
        "wellfound.com",
        "efinancialcareers.com",
        "linkedin.com/jobs",
        "builtinnyc.com",
        "fintech.io/jobs",
    ],
    "Media": [
        "mediabistro.com/jobs",
        "journalismjobs.com",
        "tvjobs.com",
        "hollywoodreporter.com/jobs",
        "linkedin.com/jobs",
    ],
    "Government": [
        "usajobs.gov",
        "governmentjobs.com",
        "cityofchicago.org/jobs",
        "linkedin.com/jobs",
    ],
    "Consulting": [
        "linkedin.com/jobs",
        "management-consulting-prep.com/consulting-jobs",
        "accenture.com/careers",
        "mckinsey.com/careers",
        "indeed.com",
    ],
    "Legal": [
        "simplylegal.com/jobs",
        "lawcrossing.com",
        "legalstaff.com",
        "linkedin.com/jobs",
    ],
}

FALLBACK_SOURCES = ["linkedin.com/jobs", "indeed.com", "glassdoor.com/Jobs", "ziprecruiter.com"]


def get_sources_for_profile(criteria: dict) -> list[str]:
    """Return deduplicated list of job boards relevant to this user's industries."""
    industries = criteria.get("industry_focus", [])
    # Also check special_instructions for keywords
    special = criteria.get("special_instructions", "").lower()
    
    sources = list(FALLBACK_SOURCES)  # always include general boards
    for industry in industries:
        for key, boards in SOURCE_MAP.items():
            if key.lower() in industry.lower() or industry.lower() in key.lower():
                sources.extend(boards)
    
    # Check special instructions for event/meeting keywords
    if any(kw in special for kw in ["event", "conference", "meeting", "convention"]):
        sources.extend(SOURCE_MAP.get("Events", []))
    
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for s in sources:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique


# ── PROMPTS ───────────────────────────────────────────────────────────────────

SEARCH_PROMPT = """You are a senior executive job search agent for {name}.

CANDIDATE PROFILE:
{resume}

SEARCH CRITERIA:
- Target titles: {titles}
- Minimum base salary: {salary}
- Location preference: {location}
- Industries: {sectors}
- Experience level: {level}
- Special requirements: {custom_ask}
- Exclude any role containing: {exclude_keywords}
- Only include roles posted within the last {recency_days} days

SPECIFIC JOB BOARDS AND SOURCES TO SEARCH (in priority order):
{sources}

SEARCH INSTRUCTIONS:
1. Search each of the sources listed above using the target titles and location criteria.
2. For niche boards (mpiweb.org, asaecenter.org, etc.), search them directly — these often have roles that never appear on LinkedIn.
3. Also check company career pages directly for organizations known to hire in these industries.
4. Cross-reference: if a role appears on a niche board AND LinkedIn, prioritize the direct application link.
5. Filter out any role that contains the excluded keywords in title or description.
6. Do NOT include roles that are clearly below the minimum salary or outside the location preference.

TODAY: {today}

Return ONLY a valid JSON object — no markdown, no preamble:
{{
  "positive_message": "2-3 warm, specific sentences for {name} about today's search, referencing something concrete from their career.",
  "jobs": [
    {{
      "title": "Exact job title",
      "organization": "Organization name",
      "type": "Full-time",
      "location": "Remote / Hybrid — City, State / On-site — City, State",
      "salary": "$160,000–$185,000 + bonus",
      "posted": "2 days ago",
      "source": "mpiweb.org",
      "source_url": "https://mpiweb.org/careers/...",
      "description": "2-3 sentence role summary.",
      "why_fit": "2-3 sentences tying the candidate's specific background to this role.",
      "network_angle": "1-2 sentences on who they might know or how to get a warm intro.",
      "apply_url": "https://direct-application-link.com"
    }}
  ],
  "proactive_targets": [
    {{
      "organization": "Organization Name",
      "sector": "Industry",
      "why": "2 sentences on why this is a strong fit.",
      "approach": "1 sentence on how to reach out (cold email, LinkedIn, mutual connection).",
      "contact_type": "VP of HR / Chief of Staff / Executive Director"
    }}
  ]
}}

Find 3-5 matched roles and 3-5 proactive targets. Use real organization names and real URLs where possible."""


COVER_LETTER_PROMPT = """Write a cover letter for {name} applying to {title} at {organization}.

RESUME:
{resume}

ROLE:
{description}

WHY THEY FIT:
{why_fit}

Requirements:
- Exactly 3 paragraphs: compelling hook, specific value proof, confident close
- Reference 2 specific career accomplishments from the resume with real numbers where available
- Do NOT open with "I am excited to apply" or any variation of that phrase
- Confident, direct, senior executive voice — not pleading, not generic
- Under 260 words
- End with the candidate's name only (no "Sincerely," etc.)

Return only the cover letter text — no subject line, no labels, no extra commentary."""


APPLICATION_PROMPT = """Pre-fill a job application for {name} applying to {title} at {organization}.

RESUME:
{resume}

Return ONLY valid JSON — no markdown, no extra text:
{{
  "full_name": "",
  "address": "",
  "desired_salary": "",
  "availability": "2 weeks notice",
  "years_of_experience": "",
  "highest_education": "",
  "work_authorization": "Yes — US Citizen",
  "willing_to_relocate": "",
  "open_to_travel": "",
  "why_interested": "A strong 2-3 sentence answer to 'Why are you interested in this role?'",
  "biggest_achievement": "A strong 2-3 sentence answer to 'Describe your biggest professional achievement' — include real numbers",
  "leadership_style": "A 2-3 sentence answer to 'Describe your leadership style'",
  "salary_expectations": "A confident, professional answer to 'What are your salary expectations?'"
}}

Fill every field from the resume. Use [your phone] / [your email] / [your LinkedIn] for contact fields not in the resume."""


# ── EMAIL TEMPLATES ───────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body{{margin:0;padding:0;background:#f5f4f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;color:#2c2c2a}}
.wrap{{max-width:680px;margin:0 auto;padding:24px 16px}}
.hdr{{background:#2c2c2a;border-radius:12px 12px 0 0;padding:28px 32px}}
.hdr h1{{color:#fff;font-size:20px;font-weight:500;margin:0 0 4px}}
.hdr p{{color:#b4b2a9;font-size:13px;margin:0}}
.positive{{background:#E1F5EE;padding:20px 32px;border-bottom:.5px solid #9FE1CB}}
.positive p{{color:#085041;font-size:15px;line-height:1.7;margin:0}}
.body{{background:#fff;padding:24px 32px;border-radius:0 0 12px 12px}}
.sec{{font-size:11px;font-weight:500;color:#888780;text-transform:uppercase;letter-spacing:.06em;margin:0 0 16px;border-bottom:.5px solid #D3D1C7;padding-bottom:8px}}
.card{{border:.5px solid #D3D1C7;border-radius:10px;padding:18px 20px;margin-bottom:16px}}
.card-title{{font-size:16px;font-weight:500;margin:0 0 3px}}
.card-org{{font-size:14px;color:#5F5E5A;margin:0 0 10px}}
.badge{{display:inline-block;font-size:11px;padding:2px 8px;border-radius:4px;font-weight:500;margin:0 4px 4px 0}}
.b-teal{{background:#E1F5EE;color:#0F6E56}}
.b-purple{{background:#EEEDFE;color:#3C3489}}
.b-gray{{background:#F1EFE8;color:#444441}}
.b-blue{{background:#E6F1FB;color:#185FA5}}
.b-gold{{background:#FEF9E7;color:#7D6008}}
.fl{{font-size:11px;font-weight:500;color:#888780;text-transform:uppercase;letter-spacing:.04em;margin:10px 0 3px}}
.ft{{font-size:14px;line-height:1.6;color:#2c2c2a}}
.cl-box{{background:#FAFAF8;border:.5px solid #D3D1C7;border-radius:8px;padding:14px 18px;margin-top:8px;font-size:13px;line-height:1.8;color:#3a3a38;white-space:pre-wrap}}
.app-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}}
.app-cell{{background:#F8F8F6;border-radius:6px;padding:8px 12px}}
.app-lbl{{font-size:10px;color:#888780;text-transform:uppercase;letter-spacing:.05em;margin-bottom:2px}}
.app-val{{font-size:13px;color:#2c2c2a}}
.apply{{display:inline-block;margin-top:14px;background:#2c2c2a;color:#fff!important;text-decoration:none;padding:9px 18px;border-radius:6px;font-size:13px;font-weight:500}}
.source-link{{display:inline-block;margin-top:8px;margin-left:10px;font-size:12px;color:#185FA5}}
.divider{{border:none;border-top:.5px solid #D3D1C7;margin:24px 0}}
.pro-item{{padding:14px 0;border-bottom:.5px solid #F1EFE8}}
.pro-item:last-child{{border-bottom:none}}
.pro-org{{font-size:15px;font-weight:500;margin:0 0 2px}}
.pro-sec{{font-size:12px;color:#888780;margin:0 0 6px}}
.pro-txt{{font-size:13px;line-height:1.6;color:#5F5E5A}}
.foot{{text-align:center;padding:20px 0 0;font-size:12px;color:#888780}}
</style>
</head>
<body>
<div class="wrap">
  <div class="hdr">
    <h1>{name}'s Job Search Digest</h1>
    <p>{today} &nbsp;&middot;&nbsp; {job_count} roles matched &nbsp;&middot;&nbsp; {proactive_count} proactive targets</p>
  </div>
  <div class="positive"><p>{positive_message}</p></div>
  <div class="body">
    <p class="sec" style="margin-top:0">Matched roles</p>
    {jobs_html}
    <hr class="divider">
    <p class="sec">Proactive outreach &mdash; reach out even without an open posting</p>
    {proactive_html}
    <hr class="divider">
    <div class="foot">
      <p>Filtered: {salary_min}+ &middot; {location} &middot; Posted within {recency_days} days</p>
      <p style="margin-top:4px;color:#aaa">Sources searched: {sources_searched}</p>
    </div>
  </div>
</div>
</body>
</html>"""

JOB_CARD = """<div class="card">
  <div class="card-title">{title}</div>
  <div class="card-org">{organization}</div>
  <div>
    <span class="badge b-teal">{location}</span>
    <span class="badge b-purple">{salary}</span>
    <span class="badge b-gray">{posted}</span>
    <span class="badge b-gold">{source}</span>
  </div>
  <div class="fl">Role overview</div><div class="ft">{description}</div>
  <div class="fl">Why it fits you</div><div class="ft">{why_fit}</div>
  <div class="fl">Network angle</div><div class="ft">{network_angle}</div>
  <hr style="border:none;border-top:.5px solid #eee;margin:12px 0">
  <div class="fl">Cover letter — ready to copy</div>
  <div class="cl-box">{cover_letter}</div>
  <hr style="border:none;border-top:.5px solid #eee;margin:12px 0">
  <div class="fl">Application quick-fill</div>
  <div class="app-grid">
    <div class="app-cell"><div class="app-lbl">Desired salary</div><div class="app-val">{app_salary}</div></div>
    <div class="app-cell"><div class="app-lbl">Availability</div><div class="app-val">{app_avail}</div></div>
    <div class="app-cell"><div class="app-lbl">Years of experience</div><div class="app-val">{app_years}</div></div>
    <div class="app-cell"><div class="app-lbl">Work authorization</div><div class="app-val">{app_auth}</div></div>
  </div>
  <div class="fl" style="margin-top:10px">Why you're interested (pre-written)</div>
  <div class="ft" style="font-style:italic">{app_why}</div>
  <div class="fl">Biggest achievement (pre-written)</div>
  <div class="ft" style="font-style:italic">{app_achieve}</div>
  <a class="apply" href="{apply_url}">Apply at {organization} &rarr;</a>
  <a class="source-link" href="{source_url}">View on {source}</a>
</div>"""

PROACTIVE_CARD = """<div class="pro-item">
  <div class="pro-org">{organization}</div>
  <div class="pro-sec">{sector}</div>
  <div class="pro-txt">{why}</div>
  <div class="pro-txt" style="margin-top:4px"><strong>Approach:</strong> {approach}</div>
  <div class="pro-txt"><strong>Contact:</strong> {contact_type}</div>
</div>"""


# ── AGENT LOGIC ───────────────────────────────────────────────────────────────

def should_run_today(schedule: str) -> bool:
    today = datetime.now(timezone.utc)
    day = today.strftime("%A").lower()
    week = (today.day - 1) // 7 + 1
    s = schedule.lower().strip()
    if s == "daily":    return True
    if s == "weekly":   return day == "monday"
    if s == "biweekly": return day == "monday" and week in (1, 3)
    return day == s


def load_users() -> list[dict]:
    """
    Load users from two sources:
    1. GitHub Secrets: env vars named USER_<SLUG> containing JSON
    2. users/ directory: JSON files (for local dev)
    """
    users = []

    # Source 1: GitHub Secrets (production)
    for key, val in os.environ.items():
        if key.startswith("USER_") and key != "USER_":
            try:
                profile = json.loads(val)
                profile["_source"] = f"secret:{key}"
                users.append(profile)
                log.info(f"Loaded from secret: {profile.get('name', key)}")
            except Exception as e:
                log.error(f"Failed to parse secret {key}: {e}")

    # Source 2: users/ directory (local dev / fallback)
    users_dir = os.path.join(os.path.dirname(__file__), "..", "users")
    if os.path.isdir(users_dir):
        for path in glob.glob(os.path.join(users_dir, "*.json")):
            try:
                with open(path) as f:
                    profile = json.load(f)
                profile["_source"] = f"file:{path}"
                users.append(profile)
                log.info(f"Loaded from file: {profile.get('name', path)}")
            except Exception as e:
                log.error(f"Failed to load {path}: {e}")

    return users


def call_claude(client: Anthropic, prompt: str, use_web_search: bool = False) -> str:
    kwargs = dict(
        model=MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    if use_web_search:
        kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]
    response = client.messages.create(**kwargs)
    return "".join(b.text for b in response.content if hasattr(b, "text")).strip()


def parse_json(text: str) -> dict:
    clean = text.replace("```json", "").replace("```", "").strip()
    start = clean.find("{")
    end = clean.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON found. Raw:\n{text[:300]}")
    return json.loads(clean[start:end])


def run_search(client: Anthropic, profile: dict, today_str: str) -> dict:
    criteria = profile.get("criteria", {})
    sources = get_sources_for_profile(criteria)
    sources_str = "\n".join(f"  - {s}" for s in sources)

    prompt = SEARCH_PROMPT.format(
        name=profile["name"],
        resume=profile.get("resume", ""),
        titles=", ".join(criteria.get("target_titles", [])),
        salary=criteria.get("min_salary", "Not specified"),
        location=criteria.get("location_preference", "Remote"),
        sectors=", ".join(criteria.get("industry_focus", [])),
        level=criteria.get("experience_level", "Senior"),
        custom_ask=criteria.get("special_instructions", ""),
        exclude_keywords=", ".join(criteria.get("exclude_keywords", [])),
        recency_days=criteria.get("recency_days", 7),
        sources=sources_str,
        today=today_str,
    )
    log.info(f"  Searching {len(sources)} sources for {profile['name']}...")
    text = call_claude(client, prompt, use_web_search=True)
    return parse_json(text)


def gen_cover_letter(client: Anthropic, profile: dict, job: dict) -> str:
    prompt = COVER_LETTER_PROMPT.format(
        name=profile["name"],
        title=job.get("title", ""),
        organization=job.get("organization", ""),
        resume=profile.get("resume", ""),
        description=job.get("description", ""),
        why_fit=job.get("why_fit", ""),
    )
    return call_claude(client, prompt)


def gen_app_prefill(client: Anthropic, profile: dict, job: dict) -> dict:
    prompt = APPLICATION_PROMPT.format(
        name=profile["name"],
        title=job.get("title", ""),
        organization=job.get("organization", ""),
        resume=profile.get("resume", ""),
    )
    try:
        return parse_json(call_claude(client, prompt))
    except Exception:
        return {}


def build_html(profile: dict, data: dict, today_str: str, sources: list) -> str:
    criteria = profile.get("criteria", {})
    jobs = data.get("jobs", [])
    proactive = data.get("proactive_targets", [])

    jobs_html = ""
    for j in jobs:
        app = j.get("_app", {})
        jobs_html += JOB_CARD.format(
            title=j.get("title", ""),
            organization=j.get("organization", ""),
            location=j.get("location", ""),
            salary=j.get("salary", "Not listed"),
            posted=j.get("posted", ""),
            source=j.get("source", ""),
            source_url=j.get("source_url", "#"),
            description=j.get("description", ""),
            why_fit=j.get("why_fit", ""),
            network_angle=j.get("network_angle", ""),
            apply_url=j.get("apply_url", "#"),
            cover_letter=(j.get("_cover_letter", "—") or "—").replace("\n", "<br>"),
            app_salary=app.get("desired_salary", criteria.get("min_salary", "")),
            app_avail=app.get("availability", "2 weeks"),
            app_years=app.get("years_of_experience", ""),
            app_auth=app.get("work_authorization", "Yes — US Citizen"),
            app_why=app.get("why_interested", ""),
            app_achieve=app.get("biggest_achievement", ""),
        )

    proactive_html = "".join(
        PROACTIVE_CARD.format(
            organization=p.get("organization", ""),
            sector=p.get("sector", ""),
            why=p.get("why", ""),
            approach=p.get("approach", ""),
            contact_type=p.get("contact_type", ""),
        )
        for p in proactive
    )

    top_sources = ", ".join(sources[:6]) + (f" +{len(sources)-6} more" if len(sources) > 6 else "")

    return HTML_TEMPLATE.format(
        name=profile["name"],
        today=today_str,
        job_count=len(jobs),
        proactive_count=len(proactive),
        positive_message=data.get("positive_message", "Today is a great day to move forward."),
        jobs_html=jobs_html,
        proactive_html=proactive_html,
        salary_min=criteria.get("min_salary", ""),
        location=criteria.get("location_preference", ""),
        recency_days=criteria.get("recency_days", 7),
        sources_searched=top_sources,
    )


def build_plain(profile: dict, data: dict, today_str: str) -> str:
    jobs = data.get("jobs", [])
    proactive = data.get("proactive_targets", [])
    lines = [
        f"{profile['name'].upper()}'S JOB SEARCH DIGEST — {today_str}",
        "=" * 60, "",
        data.get("positive_message", ""), "",
        f"{len(jobs)} MATCHED ROLES", "=" * 60,
    ]
    for i, j in enumerate(jobs, 1):
        lines += [
            f"\n{i}. {j.get('title')} — {j.get('organization')}",
            f"   {j.get('location')} | {j.get('salary')} | {j.get('posted')} | {j.get('source')}",
            f"\n   {j.get('description')}",
            f"\n   WHY IT FITS: {j.get('why_fit')}",
            f"\n   NETWORK ANGLE: {j.get('network_angle')}",
            f"\n   APPLY: {j.get('apply_url')}",
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


def send_email(profile: dict, subject: str, html: str, plain: str) -> None:
    recipient = profile.get("email")
    if not all([GMAIL_SENDER, GMAIL_APP_PASSWORD, recipient]):
        raise ValueError(f"Missing email config for {profile['name']}")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_SENDER
    msg["To"]      = recipient
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    log.info(f"  Sending to {recipient}...")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
        srv.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
        srv.sendmail(GMAIL_SENDER, recipient, msg.as_string())
    log.info(f"  Sent.")


def process_user(client: Anthropic, profile: dict, today_str: str) -> None:
    name = profile.get("name", "Unknown")
    log.info(f"\n{'='*50}\nProcessing: {name}")

    if not should_run_today(profile.get("schedule", "weekly")):
        log.info(f"  Skipping — schedule '{profile.get('schedule')}' doesn't match today")
        return

    try:
        data = run_search(client, profile, today_str)
        jobs = data.get("jobs", [])
        log.info(f"  Found {len(jobs)} matched roles")

        for j in jobs:
            org = j.get('organization', '')
            title = j.get('title', '')
            log.info(f"  Generating cover letter + app fill: {title} @ {org}")
            j["_cover_letter"] = gen_cover_letter(client, profile, j)
            j["_app"]          = gen_app_prefill(client, profile, j)

        sources = get_sources_for_profile(profile.get("criteria", {}))
        html  = build_html(profile, data, today_str, sources)
        plain = build_plain(profile, data, today_str)
        subj  = f"{name}'s Job Search Digest — {datetime.now().strftime('%b %d')}"
        send_email(profile, subj, html, plain)

    except Exception as e:
        log.error(f"  Failed for {name}: {e}", exc_info=True)


def main():
    today_str = datetime.now().strftime("%A, %B %d, %Y")
    log.info(f"=== Job Search Agent — {today_str} ===")

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    users  = load_users()

    if not users:
        log.warning("No users found. Add USER_<NAME> secrets or users/*.json files.")
        return

    log.info(f"Found {len(users)} user(s)")
    for profile in users:
        process_user(client, profile, today_str)

    log.info("\n=== All users processed ===")


if __name__ == "__main__":
    main()
