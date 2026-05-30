#!/usr/bin/env python3
"""
Job Search Agent v2 — reads user profiles from a private GitHub data repo.
For each user it:
  1. Fetches their profile.json, resume, and cover letter from the private data repo
  2. Searches industry-specific job boards via Claude + web_search
  3. Tailors the RESUME highlights for each matched role
  4. Rewrites the COVER LETTER for each role, matching the candidate's existing voice
  5. Pre-fills common application fields
  6. Emails an HTML digest

Env vars needed (GitHub Actions Secrets on the PUBLIC code repo):
  ANTHROPIC_API_KEY   — Anthropic API key
  GMAIL_SENDER        — Gmail address that sends digests
  GMAIL_APP_PASSWORD  — Gmail App Password
  GITHUB_TOKEN        — PAT with read access to the private data repo
  GITHUB_DATA_REPO    — "owner/job-agent-users" (the private repo)
"""

import os, json, base64, smtplib, logging, glob, urllib.request, urllib.error
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from anthropic import Anthropic

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler("job_agent.log"), logging.StreamHandler()])
log = logging.getLogger(__name__)

MODEL              = "claude-haiku-4-5"
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY")
GMAIL_SENDER       = os.getenv("GMAIL_SENDER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
GITHUB_TOKEN       = os.getenv("GITHUB_TOKEN")
GITHUB_DATA_REPO   = os.getenv("GITHUB_DATA_REPO")

# ── Source map ─────────────────────────────────────────────────────────────────
SOURCE_MAP = {
    "Associations": ["careers.asaecenter.org","jobs.associationcareernetwork.com","nonprofitjobs.org","idealist.org"],
    "Events":       ["mpiweb.org/careers","pcma.org/career-center","bizbash.com/jobs","smartmeetings.com/jobs","meetingsnet.com/jobs","cvent.com/en/careers"],
    "Hospitality":  ["hcareers.com","hospitalityonline.com","hospitalityjobbase.com","pcma.org/career-center"],
    "Tech":         ["linkedin.com/jobs","greenhouse.io","lever.co","wellfound.com","builtin.com"],
    "Nonprofit":    ["idealist.org","devex.com/jobs","workforgood.org","bridgespan.org"],
    "Healthcare":   ["healthcarejobsite.com","healthjobsnationwide.com","linkedin.com/jobs"],
    "Finance":      ["efinancialcareers.com","linkedin.com/jobs","buysidehiring.com"],
    "Fintech":      ["wellfound.com","efinancialcareers.com","linkedin.com/jobs"],
    "Media":        ["mediabistro.com/jobs","journalismjobs.com","linkedin.com/jobs"],
    "Education":    ["higheredjobs.com","chronicle.com/jobs","edjoin.org"],
    "Government":   ["usajobs.gov","governmentjobs.com"],
    "Corporate":    ["linkedin.com/jobs","indeed.com","glassdoor.com/Jobs"],
    "Consulting":   ["linkedin.com/jobs","indeed.com"],
    "Legal":        ["simplylegal.com/jobs","lawcrossing.com","linkedin.com/jobs"],
    "Foundations":  ["philanthropy.com/jobs","idealist.org","exponentphilanthropy.org/jobs"],
}
ALWAYS = ["linkedin.com/jobs","indeed.com","glassdoor.com/Jobs","ziprecruiter.com"]

def sources_for(criteria):
    seen, out = set(ALWAYS), list(ALWAYS)
    for ind in criteria.get("industry_focus", []):
        for key, boards in SOURCE_MAP.items():
            if key.lower() in ind.lower() or ind.lower() in key.lower():
                for b in boards:
                    if b not in seen: seen.add(b); out.append(b)
    if any(k in criteria.get("special_instructions","").lower() for k in ["event","conference","meeting"]):
        for b in SOURCE_MAP.get("Events",[]):
            if b not in seen: seen.add(b); out.append(b)
    return out

# ── Private data repo access ───────────────────────────────────────────────────
def gh_get_text(path):
    url = f"https://api.github.com/repos/{GITHUB_DATA_REPO}/contents/{path}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read())
            b64 = data.get("content","").replace("\n","")
            return base64.b64decode(b64).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 404: return None
        raise

def list_user_slugs():
    url = f"https://api.github.com/repos/{GITHUB_DATA_REPO}/contents/users"
    req = urllib.request.Request(url, headers={
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(req) as r:
            return [i["name"] for i in json.loads(r.read()) if i["type"]=="dir"]
    except: return []

def load_user(slug):
    txt = gh_get_text(f"users/{slug}/profile.json")
    if not txt: return None
    profile = json.loads(txt)
    rf = profile.get("resume_file")
    cf = profile.get("cover_letter_file")
    profile["_resume"]     = gh_get_text(f"users/{slug}/{rf}") or "" if rf else ""
    profile["_cover_letter"] = gh_get_text(f"users/{slug}/{cf}") or "" if cf else ""
    return profile

# ── Claude helpers ─────────────────────────────────────────────────────────────
def claude(client, prompt, web=False):
    kwargs = dict(model=MODEL, max_tokens=2000, messages=[{"role":"user","content":prompt}])
    if web: kwargs["tools"] = [{"type":"web_search_20250305","name":"web_search"}]
    r = client.messages.create(**kwargs)
    return "".join(b.text for b in r.content if hasattr(b,"text")).strip()

def parse_json(text):
    c = text.replace("```json","").replace("```","").strip()
    s, e = c.find("{"), c.rfind("}")+1
    if s<0 or e==0: raise ValueError(f"No JSON in: {text[:200]}")
    return json.loads(c[s:e])

# ── Per-job generation ─────────────────────────────────────────────────────────
def tailor_resume(client, profile, job):
    if not profile["_resume"]:
        return "No resume uploaded — visit the signup form to add yours."
    return claude(client, f"""Tailor this resume for the target role. Keep all facts exact — reorder and reframe, never fabricate.

ORIGINAL RESUME:
{profile['_resume']}

TARGET: {job.get('title')} at {job.get('organization')}
DESCRIPTION: {job.get('description')}

Instructions: Move the most relevant accomplishments to the top. Strengthen the summary to speak to this role. Keep the same length and format. Return the full tailored resume text only.""")

def write_cover_letter(client, profile, job):
    voice = f"\nCANDIDATE'S EXISTING COVER LETTER (match this voice exactly):\n{profile['_cover_letter']}" if profile["_cover_letter"] else ""
    return claude(client, f"""Write a cover letter for {profile['name']} applying to {job.get('title')} at {job.get('organization')}.

RESUME:
{profile['_resume'] or 'Not provided — use the why_fit section below'}
{voice}

ROLE: {job.get('description')}
WHY THEY FIT: {job.get('why_fit')}

Requirements:
- 3 paragraphs: compelling hook, specific value proof with real numbers, confident close
- Never open "I am excited to apply" or any cliché
- Match the voice from their existing cover letter if provided
- Under 260 words, senior executive register
- End with candidate's name only

Return only the cover letter text.""")

def prefill_app(client, profile, job):
    try:
        return parse_json(claude(client, f"""Pre-fill a job application for {profile['name']} applying to {job.get('title')} at {job.get('organization')}.
RESUME: {profile['_resume'] or 'Not provided'}
Return ONLY valid JSON: {{"desired_salary":"","availability":"2 weeks notice","years_of_experience":"","work_authorization":"Yes — US Citizen","willing_to_relocate":"","why_interested":"2-3 strong sentences","biggest_achievement":"2-3 sentences with real numbers","leadership_style":"2-3 sentences","salary_expectations":"Confident professional answer"}}"""))
    except: return {}

def search_jobs(client, profile, today_str):
    criteria = profile.get("criteria", {})
    srcs = sources_for(criteria)
    return parse_json(claude(client, f"""You are a job search agent for {profile['name']}.
RESUME: {profile['_resume'] or 'See criteria'}
CRITERIA:
- Titles: {", ".join(criteria.get("target_titles",[]))}
- Min salary: {criteria.get("min_salary","Not specified")}
- Location: {criteria.get("location_preference","Remote")}
- Industries: {", ".join(criteria.get("industry_focus",[]))}
- Experience: {criteria.get("experience_level","Senior")}
- Requirements: {criteria.get("special_instructions","")}
- Exclude: {", ".join(criteria.get("exclude_keywords",[]))}
- Max age: {criteria.get("recency_days",7)} days
SEARCH THESE SOURCES:
{chr(10).join(f"  - {s}" for s in srcs)}
TODAY: {today_str}
Search each source. Prioritize niche boards over LinkedIn.
Return ONLY valid JSON:
{{"positive_message":"2-3 warm sentences for {profile['name']}.","jobs":[{{"title":"","organization":"","type":"Full-time","location":"","salary":"","posted":"","source":"","source_url":"","description":"","why_fit":"","network_angle":"","apply_url":""}}],"proactive_targets":[{{"organization":"","sector":"","why":"","approach":"","contact_type":""}}]}}
Find 3-5 roles and 3-5 proactive targets.""", web=True))

# ── Email templates ────────────────────────────────────────────────────────────
HTML_WRAP = """<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
body{{margin:0;background:#f5f4f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;color:#2c2c2a}}
.w{{max-width:680px;margin:0 auto;padding:24px 16px}}
.hd{{background:#2c2c2a;border-radius:12px 12px 0 0;padding:28px 32px}}
.hd h1{{color:#fff;font-size:20px;font-weight:500;margin:0 0 4px}}
.hd p{{color:#b4b2a9;font-size:13px;margin:0}}
.pos{{background:#E1F5EE;padding:20px 32px;border-bottom:.5px solid #9FE1CB}}
.pos p{{color:#085041;font-size:15px;line-height:1.7;margin:0}}
.bd{{background:#fff;padding:24px 32px;border-radius:0 0 12px 12px}}
.sec{{font-size:11px;font-weight:500;color:#888780;text-transform:uppercase;letter-spacing:.06em;margin:0 0 16px;border-bottom:.5px solid #D3D1C7;padding-bottom:8px}}
.card{{border:.5px solid #D3D1C7;border-radius:10px;padding:18px 20px;margin-bottom:16px}}
.ct{{font-size:16px;font-weight:500;margin:0 0 3px}}.co{{font-size:14px;color:#5F5E5A;margin:0 0 10px}}
.b{{display:inline-block;font-size:11px;padding:2px 8px;border-radius:4px;font-weight:500;margin:0 4px 4px 0}}
.b1{{background:#E1F5EE;color:#0F6E56}}.b2{{background:#EEEDFE;color:#3C3489}}.b3{{background:#F1EFE8;color:#444441}}.b4{{background:#FEF9E7;color:#7D6008}}
.fl{{font-size:11px;font-weight:500;color:#888780;text-transform:uppercase;letter-spacing:.04em;margin:10px 0 3px}}
.ft{{font-size:14px;line-height:1.6}}
.pre{{background:#FAFAF8;border:.5px solid #D3D1C7;border-radius:8px;padding:14px 18px;margin-top:8px;font-size:13px;line-height:1.8;color:#3a3a38;white-space:pre-wrap}}
.ag{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}}
.ac{{background:#F8F8F6;border-radius:6px;padding:8px 12px}}
.al{{font-size:10px;color:#888780;text-transform:uppercase;letter-spacing:.05em;margin-bottom:2px}}
.av{{font-size:13px}}
.ab{{display:inline-block;margin-top:14px;background:#2c2c2a;color:#fff!important;text-decoration:none;padding:9px 18px;border-radius:6px;font-size:13px;font-weight:500}}
.sl2{{display:inline-block;margin-top:8px;margin-left:10px;font-size:12px;color:#185FA5}}
.dv{{border:none;border-top:.5px solid #D3D1C7;margin:24px 0}}
.pi{{padding:14px 0;border-bottom:.5px solid #F1EFE8}}.pi:last-child{{border-bottom:none}}
.po{{font-size:15px;font-weight:500;margin:0 0 2px}}.ps{{font-size:12px;color:#888780;margin:0 0 6px}}.pt{{font-size:13px;line-height:1.6;color:#5F5E5A}}
.ft2{{text-align:center;padding:20px 0 0;font-size:12px;color:#888780}}
</style></head><body><div class="w">
<div class="hd"><h1>{name}'s Job Search Digest</h1><p>{today} &middot; {jc} roles &middot; {pc} proactive targets</p></div>
<div class="pos"><p>{pm}</p></div>
<div class="bd">
<p class="sec" style="margin-top:0">Matched roles — tailored resume &amp; cover letter included</p>
{jobs_html}
<hr class="dv"><p class="sec">Proactive outreach</p>{pro_html}
<hr class="dv"><div class="ft2"><p>Sources: {src}</p><p style="margin-top:4px;color:#aaa">{sal}+ &middot; {loc} &middot; Last {rd} days</p></div>
</div></div></body></html>"""

def build_html(profile, data, today_str, srcs):
    c = profile.get("criteria",{})
    jobs_html = ""
    for j in data.get("jobs",[]):
        app = j.get("_app",{})
        jobs_html += f"""<div class="card">
<div class="ct">{j.get('title','')}</div><div class="co">{j.get('organization','')}</div>
<div><span class="b b1">{j.get('location','')}</span><span class="b b2">{j.get('salary','Not listed')}</span><span class="b b3">{j.get('posted','')}</span><span class="b b4">{j.get('source','')}</span></div>
<div class="fl">Role overview</div><div class="ft">{j.get('description','')}</div>
<div class="fl">Why it fits you</div><div class="ft">{j.get('why_fit','')}</div>
<div class="fl">Network angle</div><div class="ft">{j.get('network_angle','')}</div>
<hr style="border:none;border-top:.5px solid #eee;margin:12px 0">
<div class="fl">Tailored resume — copy &amp; paste for this application</div>
<div class="pre">{(j.get('_resume','') or '').replace(chr(10),'<br>')}</div>
<hr style="border:none;border-top:.5px solid #eee;margin:12px 0">
<div class="fl">Cover letter — ready to send</div>
<div class="pre">{(j.get('_cl','') or '').replace(chr(10),'<br>')}</div>
<hr style="border:none;border-top:.5px solid #eee;margin:12px 0">
<div class="fl">Application quick-fill</div>
<div class="ag">
<div class="ac"><div class="al">Desired salary</div><div class="av">{app.get('desired_salary',c.get('min_salary',''))}</div></div>
<div class="ac"><div class="al">Availability</div><div class="av">{app.get('availability','2 weeks')}</div></div>
<div class="ac"><div class="al">Years experience</div><div class="av">{app.get('years_of_experience','')}</div></div>
<div class="ac"><div class="al">Work auth</div><div class="av">{app.get('work_authorization','Yes — US Citizen')}</div></div>
</div>
<div class="fl" style="margin-top:10px">Why interested (pre-written)</div><div class="ft" style="font-style:italic">{app.get('why_interested','')}</div>
<div class="fl">Biggest achievement (pre-written)</div><div class="ft" style="font-style:italic">{app.get('biggest_achievement','')}</div>
<a class="ab" href="{j.get('apply_url','#')}">Apply at {j.get('organization','')} &rarr;</a>
<a class="sl2" href="{j.get('source_url','#')}">View on {j.get('source','')}</a></div>"""

    pro_html = "".join(f"""<div class="pi">
<div class="po">{p.get('organization','')}</div><div class="ps">{p.get('sector','')}</div>
<div class="pt">{p.get('why','')}</div>
<div class="pt" style="margin-top:4px"><strong>Approach:</strong> {p.get('approach','')}</div>
<div class="pt"><strong>Contact:</strong> {p.get('contact_type','')}</div></div>"""
    for p in data.get("proactive_targets",[]))

    src_str = ", ".join(srcs[:5]) + (f" +{len(srcs)-5} more" if len(srcs)>5 else "")
    return HTML_WRAP.format(
        name=profile["name"], today=today_str,
        jc=len(data.get("jobs",[])), pc=len(data.get("proactive_targets",[])),
        pm=data.get("positive_message",""), jobs_html=jobs_html, pro_html=pro_html,
        src=src_str, sal=c.get("min_salary",""), loc=c.get("location_preference",""), rd=c.get("recency_days",7))

def send_email(profile, subject, html, plain):
    r = profile.get("email")
    if not all([GMAIL_SENDER, GMAIL_APP_PASSWORD, r]):
        raise ValueError(f"Missing email config for {profile['name']}")
    msg = MIMEMultipart("alternative")
    msg["Subject"]=subject; msg["From"]=GMAIL_SENDER; msg["To"]=r
    msg.attach(MIMEText(plain,"plain")); msg.attach(MIMEText(html,"html"))
    with smtplib.SMTP_SSL("smtp.gmail.com",465) as s:
        s.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
        s.sendmail(GMAIL_SENDER, r, msg.as_string())
    log.info(f"  Sent to {r}")

def should_run(schedule):
    today = datetime.now(timezone.utc)
    day = today.strftime("%A").lower()
    wk = (today.day-1)//7+1
    s = (schedule or "weekly").lower().strip()
    if s=="daily": return True
    if s=="weekly": return day=="monday"
    if s=="biweekly": return day=="monday" and wk in (1,3)
    return day==s

def process_user(client, slug, today_str):
    log.info(f"\n{'='*50}\nUser slug: {slug}")
    profile = load_user(slug)
    if not profile: log.error(f"  Could not load {slug}"); return
    name = profile.get("name", slug)
    if not should_run(profile.get("schedule","weekly")):
        log.info(f"  Skipping {name} — schedule doesn't match today"); return
    log.info(f"  Processing: {name} | resume: {'yes' if profile['_resume'] else 'no'} | CL: {'yes' if profile['_cover_letter'] else 'no'}")
    try:
        data = search_jobs(client, profile, today_str)
        for j in data.get("jobs",[]):
            log.info(f"  → {j.get('title')} @ {j.get('organization')}")
            j["_resume"] = tailor_resume(client, profile, j)
            j["_cl"]     = write_cover_letter(client, profile, j)
            j["_app"]    = prefill_app(client, profile, j)
        srcs  = sources_for(profile.get("criteria",{}))
        html  = build_html(profile, data, today_str, srcs)
        plain = "\n".join([f"{profile['name'].upper()} — {today_str}","="*60,
                           data.get("positive_message","")]+
                          [f"\n{i+1}. {j.get('title')} @ {j.get('organization')}\n   {j.get('apply_url','')}"
                           for i,j in enumerate(data.get("jobs",[]))])
        send_email(profile, f"{name}'s Job Search Digest — {datetime.now().strftime('%b %d')}", html, plain)
    except Exception as e:
        log.error(f"  Failed for {name}: {e}", exc_info=True)

def main():
    today_str = datetime.now().strftime("%A, %B %d, %Y")
    log.info(f"=== Job Search Agent — {today_str} ===")
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    if GITHUB_DATA_REPO and GITHUB_TOKEN:
        slugs = list_user_slugs()
        log.info(f"Data repo: {GITHUB_DATA_REPO} | Users: {slugs}")
    else:
        slugs = [os.path.basename(os.path.dirname(p)) for p in glob.glob("users/*/profile.json")]
        log.info(f"Local dev — users: {slugs}")
    for slug in slugs:
        process_user(client, slug, today_str)
    log.info("=== Done ===")

if __name__ == "__main__":
    main()
