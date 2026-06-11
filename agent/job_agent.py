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

import sys
_stream_handler = logging.StreamHandler(sys.stdout)
_stream_handler.stream.reconfigure(encoding='utf-8', errors='replace') if hasattr(_stream_handler.stream, 'reconfigure') else None
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("job_agent.log", encoding="utf-8"),
        _stream_handler,
    ]
)
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
def gh_get_bytes(path):
    """Fetch raw bytes of a file from the private data repo."""
    import urllib.parse
    encoded = '/'.join(urllib.parse.quote(p, safe='') for p in path.split('/'))
    url = f"https://api.github.com/repos/{GITHUB_DATA_REPO}/contents/{encoded}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read())
            b64 = data.get("content", "").replace("\n", "")
            return base64.b64decode(b64)
    except urllib.error.HTTPError as e:
        if e.code == 404: return None
        raise

def extract_text_from_file(file_bytes, filename):
    """Extract plain text from PDF, DOCX, or TXT bytes."""
    if not file_bytes:
        return ""
    ext = filename.lower().rsplit('.', 1)[-1] if '.' in filename else 'txt'

    if ext == 'pdf':
        try:
            # Pure-python PDF text extraction — no dependencies needed
            import re
            text = file_bytes.decode('latin-1', errors='replace')
            # Extract text between BT/ET markers (PDF text objects)
            chunks = re.findall(r'BT.*?ET', text, re.DOTALL)
            extracted = []
            for chunk in chunks:
                # Get strings in parentheses and hex strings
                strings = re.findall(r'\(([^)]*?)\)', chunk)
                for s in strings:
                    s = s.replace('\\n', ' ').replace('\\r', ' ').replace('\\t', ' ')
                    s = re.sub(r'\\(.)', r'\1', s)
                    extracted.append(s)
            result = ' '.join(extracted)
            # If we got very little, try a simpler raw text scan
            if len(result.strip()) < 100:
                raw = file_bytes.decode('latin-1', errors='replace')
                result = re.sub(r'[^\x20-\x7E\n]', ' ', raw)
                result = re.sub(r' {3,}', '\n', result)
                result = '\n'.join(line.strip() for line in result.splitlines() if len(line.strip()) > 20)
            return result[:8000]  # cap to avoid token explosion
        except Exception as e:
            log.warning(f"PDF extraction failed for {filename}: {e}")
            return ""

    elif ext == 'docx':
        try:
            import zipfile, io
            from xml.etree import ElementTree as ET
            zf = zipfile.ZipFile(io.BytesIO(file_bytes))
            xml = zf.read('word/document.xml')
            root = ET.fromstring(xml)
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            paragraphs = []
            for para in root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
                texts = [t.text or '' for t in para.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t')]
                line = ''.join(texts).strip()
                if line:
                    paragraphs.append(line)
            return '\n'.join(paragraphs)[:8000]
        except Exception as e:
            log.warning(f"DOCX extraction failed for {filename}: {e}")
            return ""

    else:
        # Plain text / TXT
        try:
            return file_bytes.decode('utf-8', errors='replace')[:8000]
        except Exception:
            return ""

def gh_get_text(path):
    """Fetch a file and return its text content, handling PDF/DOCX/TXT."""
    filename = path.split('/')[-1]
    file_bytes = gh_get_bytes(path)
    if file_bytes is None:
        return None
    return extract_text_from_file(file_bytes, filename)


def list_user_slugs():
    import urllib.parse
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

    # Store resume as base64 for direct Claude API consumption
    rf = profile.get("resume_file")
    if rf:
        resume_bytes = gh_get_bytes(f"users/{slug}/{rf}")
        if resume_bytes:
            profile["_resume_b64"] = base64.b64encode(resume_bytes).decode('utf-8')
            profile["_resume_filename"] = rf
            profile["_resume_mediatype"] = get_media_type(rf)
        else:
            profile["_resume_b64"] = None
            profile["_resume_filename"] = rf
            profile["_resume_mediatype"] = None
    else:
        profile["_resume_b64"] = None
        profile["_resume_filename"] = None
        profile["_resume_mediatype"] = None

    # Store cover letters as base64 list
    cl_files = profile.get("cover_letter_files") or []
    if not cl_files and profile.get("cover_letter_file"):
        cl_files = [profile["cover_letter_file"]]
    cl_docs = []
    for clf in cl_files:
        cl_bytes = gh_get_bytes(f"users/{slug}/{clf}")
        if cl_bytes:
            cl_docs.append({
                "b64": base64.b64encode(cl_bytes).decode('utf-8'),
                "filename": clf,
                "mediatype": get_media_type(clf),
            })
    profile["_cover_letter_docs"] = cl_docs
    return profile

def get_media_type(filename):
    """Return the correct MIME type for Claude document API."""
    ext = filename.lower().rsplit('.', 1)[-1] if '.' in filename else 'txt'
    return {
        'pdf':  'application/pdf',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'doc':  'application/msword',
        'txt':  'text/plain',
    }.get(ext, 'text/plain')


def claude_with_retry(client, prompt, web=False, max_tokens=2000, docs=None):
    """Call Claude with automatic backoff on rate limit errors."""
    import time
    delays = [30, 60, 120]
    for attempt, delay in enumerate(delays + [None]):
        try:
            return claude(client, prompt, web=web, max_tokens=max_tokens, docs=docs)
        except Exception as e:
            if "rate_limit" in str(e).lower() or "429" in str(e):
                if delay is None:
                    raise
                log.warning(f"  Rate limited — waiting {delay}s before retry {attempt + 1}...")
                time.sleep(delay)
            else:
                raise

def claude(client, prompt, web=False, max_tokens=2000, docs=None):
    """
    Call Claude. docs is an optional list of dicts: [{b64, mediatype, filename}]
    Claude reads PDF and DOCX natively — no text extraction needed.
    """
    if docs:
        content = []
        for doc in docs:
            if not doc.get("b64"):
                continue
            mt = doc.get("mediatype", "application/pdf")
            # Claude supports PDF natively; for DOCX send as text/plain fallback
            if mt in ("application/pdf",):
                content.append({
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": mt,
                        "data": doc["b64"],
                    }
                })
            else:
                # For DOCX/DOC, extract text using zipfile (built-in, works well)
                try:
                    import zipfile, io
                    from xml.etree import ElementTree as ET
                    zf = zipfile.ZipFile(io.BytesIO(base64.b64decode(doc["b64"])))
                    xml = zf.read('word/document.xml')
                    root = ET.fromstring(xml)
                    paras = []
                    for para in root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
                        texts = [t.text or '' for t in para.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t')]
                        line = ''.join(texts).strip()
                        if line:
                            paras.append(line)
                    text = '\n'.join(paras)[:8000]
                    content.append({"type": "text", "text": f"[{doc.get('filename','document')}]:\n{text}"})
                except Exception as e:
                    log.warning(f"DOCX extract failed: {e}")
        content.append({"type": "text", "text": prompt})
        messages = [{"role": "user", "content": content}]
    else:
        messages = [{"role": "user", "content": prompt}]

    kwargs = dict(model=MODEL, max_tokens=max_tokens, messages=messages)
    if web: kwargs["tools"] = [{"type":"web_search_20250305","name":"web_search"}]
    r = client.messages.create(**kwargs)
    return "".join(b.text for b in r.content if hasattr(b,"text")).strip()

def parse_json(text):
    import re as _re
    c = text.replace("```json", "").replace("```", "").strip()
    s = c.find("{")
    if s < 0:
        raise ValueError(f"No JSON found in response.\nGot:\n{text[:400]}")

    raw = c[s:]

    # First attempt: find the last valid closing brace
    # Try progressively shorter substrings if full parse fails
    for end_idx in range(len(raw), 0, -1):
        if raw[end_idx-1] != '}':
            continue
        candidate = raw[:end_idx]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    # If that failed entirely, try common fixes on the full string
    e = raw.rfind("}") + 1
    raw = raw[:e]

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        char = exc.pos
        snippet = raw[max(0, char - 150):char + 150]
        log.error(f"JSON parse error at char {char}: {exc.msg}")
        log.error(f"Context around error: ...{snippet}...")

        # Fix 1: smart quotes
        fixed = raw
        fixed = fixed.replace("\u201c", '"').replace("\u201d", '"')
        fixed = fixed.replace("\u2018", "'").replace("\u2019", "'")

        # Fix 2: trailing commas before ] or }
        fixed = _re.sub(r',\s*([}\]])', r'\1', fixed)

        # Fix 3: newlines inside string values
        fixed = _re.sub(
            r'"([^"]*)"',
            lambda m: '"' + m.group(1).replace("\n", " ").replace("\r", "") + '"',
            fixed
        )

        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            # Last resort: extract just the jobs and proactive_targets arrays
            # so we get partial results rather than total failure
            try:
                jobs_match = _re.search(r'"jobs"\s*:\s*(\[.*?\])(?=\s*,|\s*})', fixed, _re.DOTALL)
                pro_match  = _re.search(r'"proactive_targets"\s*:\s*(\[.*?\])(?=\s*})', fixed, _re.DOTALL)
                msg_match  = _re.search(r'"positive_message"\s*:\s*"([^"]*)"', fixed)
                result = {
                    "positive_message": msg_match.group(1) if msg_match else "Great opportunities found today!",
                    "jobs": json.loads(jobs_match.group(1)) if jobs_match else [],
                    "proactive_targets": json.loads(pro_match.group(1)) if pro_match else [],
                }
                log.warning(f"Used partial JSON recovery — got {len(result['jobs'])} jobs")
                return result
            except Exception:
                pass

            raise ValueError(
                f"Could not parse JSON after all repair attempts.\n"
                f"Error at char {char}: {exc.msg}\n"
                f"Context: ...{snippet}..."
            )


def tailor_resume(client, profile, job):
    if not profile.get("_resume_b64"):
        return "No resume uploaded — visit the signup form to add yours."
    docs = [{"b64": profile["_resume_b64"], "mediatype": profile["_resume_mediatype"], "filename": profile["_resume_filename"]}]
    return claude(client, f"""The attached document is the candidate's resume. Tailor it for the target role below. Keep all facts exact — reorder and reframe, never fabricate.

TARGET: {job.get('title')} at {job.get('organization')}
DESCRIPTION: {job.get('description')}

Instructions: Move the most relevant accomplishments to the top. Strengthen the summary to speak to this role. Keep the same length and format. Return the full tailored resume text only.""", docs=docs)

def write_cover_letter(client, profile, job):
    cl_docs = profile.get("_cover_letter_docs", [])
    resume_doc = {"b64": profile.get("_resume_b64"), "mediatype": profile.get("_resume_mediatype"), "filename": profile.get("_resume_filename")} if profile.get("_resume_b64") else None

    docs = []
    if resume_doc:
        docs.append(resume_doc)
    docs.extend(cl_docs)

    sample_note = ""
    if cl_docs:
        sample_note = f"The first {len(docs)-1} attached document(s) are the candidate's existing cover letters — study their voice, tone, sentence rhythm, and word choices. Match this style exactly. Do not copy content, only style."

    prompt = f"""Write a cover letter for {profile['name']} applying to {job.get('title')} at {job.get('organization')}.

{sample_note}
{"The final attached document is their resume — use specific accomplishments and numbers from it." if resume_doc else "Use the why_fit context below for accomplishments."}

ROLE: {job.get('description')}
WHY THEY FIT: {job.get('why_fit')}

Requirements:
- 3 paragraphs: compelling hook, specific value proof with real numbers, confident close
- Never open with "I am excited to apply" or any cliché
- {"Match voice and phrasing from the cover letter samples attached" if cl_docs else "Professional confident register"}
- Under 260 words
- End with the candidate's name only

Return only the cover letter text."""

    return claude(client, prompt, docs=docs if docs else None)

def prefill_app(client, profile, job):
    try:
        return parse_json(claude(client, f"""Pre-fill a job application for {profile['name']} applying to {job.get('title')} at {job.get('organization')}.
RESUME: [See attached resume file: {profile.get('_resume_filename','not uploaded')}]
Return ONLY valid JSON: {{"desired_salary":"","availability":"2 weeks notice","years_of_experience":"","work_authorization":"Yes — US Citizen","willing_to_relocate":"","why_interested":"2-3 strong sentences","biggest_achievement":"2-3 sentences with real numbers","leadership_style":"2-3 sentences","salary_expectations":"Confident professional answer"}}"""))
    except: return {}

def search_jobs(client, profile, today_str):
    criteria = profile.get("criteria", {})
    name = profile["name"]
    # Build docs list for passing to Claude calls
    resume_doc = {
        "b64": profile["_resume_b64"],
        "mediatype": profile["_resume_mediatype"],
        "filename": profile["_resume_filename"],
    } if profile.get("_resume_b64") else None
    resume_docs = [resume_doc] if resume_doc else []

    titles_str   = ", ".join(criteria.get("target_titles", []))
    salary_str   = criteria.get("min_salary", "not specified")
    location_str = criteria.get("location_preference", "Remote")
    sectors_str  = ", ".join(criteria.get("industry_focus", []))
    special_str  = criteria.get("special_instructions", "")
    exclude_str  = ", ".join(criteria.get("exclude_keywords", []))

    # ── STEP 1: Identify specific target companies ──────────────────────────
    # Ask Claude to reason about WHO should hire this person — not to scrape boards
    company_prompt = f"""You are a senior recruiter helping {name} find their next role.

CANDIDATE BACKGROUND:
{f"Resume provided above." if resume_docs else "No resume uploaded."}

WHAT THEY WANT:
- Titles: {titles_str}
- Min salary: {salary_str}
- Location: {location_str}
- Industries: {sectors_str}
- Requirements: {special_str}
- Exclude: {exclude_str}

Your job: identify 8-12 SPECIFIC, NAMED companies or organizations that:
1. Actively hire people with this exact background
2. Are known to pay {salary_str}+ for these roles
3. Fit the location preference
4. Match the industries

Think carefully about the candidate's specific background. Don't suggest generic large employers — suggest organizations where THIS person's specific combination of skills is genuinely valuable.

For each company write one line: Company Name | Why they're a fit | Type (startup/nonprofit/enterprise/gov)

Then separately list 3-4 specific niche job boards or communities where these roles are actually posted (not LinkedIn/Indeed — think specific industry boards, Slack communities, newsletters, etc.)"""

    log.info("  Step 1: Identifying target companies...")
    company_findings = claude(client, company_prompt, web=False, max_tokens=1000, docs=resume_docs)
    log.info(f"  Step 1 complete — identified companies")

    # ── STEP 2: Search those specific companies for open roles ──────────────
    search_prompt = f"""You are searching for real, current job openings for {name}.

TODAY: {today_str}

TARGET COMPANIES identified as strong fits:
{company_findings}

SEARCH TASK:
For each company above, search their actual careers page and any job boards for current openings matching:
- Titles like: {titles_str}
- Location: {location_str}
- Posted within the last 14 days

For each real opening you find, note:
- Exact job title
- Company name
- Location / remote status
- Salary if listed
- Direct URL to the job posting (careers.company.com/jobs/... NOT a search results URL)
- Date posted
- 2-3 sentence description

If a company has no current openings, note that — don't make up a URL.
If you find a real job, the URL must go directly to THAT specific job posting, not a search page.

Also note which of these companies seem to be actively hiring right now vs quiet."""

    log.info("  Step 2: Searching target companies for open roles...")
    raw_findings = claude(client, search_prompt, web=True, max_tokens=2000, docs=resume_docs)
    log.info(f"  Step 2 complete — got {len(raw_findings)} chars")

    # ── STEP 3: Format into JSON ─────────────────────────────────────────────
    format_prompt = f"""Convert these job search findings into JSON. Output ONLY the JSON — no text before or after.

CANDIDATE: {name}
TODAY: {today_str}

COMPANY RESEARCH:
{company_findings}

JOB FINDINGS:
{raw_findings}

IMPORTANT RULES FOR QUALITY:
- Only include jobs where you found a REAL, SPECIFIC job posting URL (not a search page like indeed.com/jobs?q=...)
- If a URL is a search results page, put it in proactive_targets instead, not jobs
- "Not listed" is acceptable for salary — never make one up
- For companies with no open roles, put them in proactive_targets
- proactive_targets should be companies worth monitoring or reaching out to cold

Output this exact JSON:
{{
  "positive_message": "2-3 warm sentences for {name} referencing their specific background and today's date.",
  "jobs": [
    {{
      "title": "Exact job title from posting",
      "organization": "Company name",
      "type": "Full-time",
      "location": "Remote / Hybrid / On-site + city",
      "salary": "$X — $Y or Not listed",
      "posted": "X days ago or Month Day",
      "source": "Company careers page / LinkedIn / etc",
      "source_url": "https://direct-link-to-this-specific-job",
      "description": "What this role actually does — one paragraph, no newlines",
      "why_fit": "How this candidate's specific background maps to this role — one paragraph",
      "network_angle": "Who they might know or how to get a warm intro",
      "apply_url": "https://direct-application-link"
    }}
  ],
  "proactive_targets": [
    {{
      "organization": "Company name",
      "sector": "Industry",
      "why": "Why this company is a strong fit for this candidate specifically",
      "approach": "How to reach out — email, LinkedIn, mutual connection, etc",
      "contact_type": "Title of the right person to contact"
    }}
  ]
}}

Include whatever real jobs were found (0-5). Fill proactive_targets with the remaining strong-fit companies (3-6 total).
Every string value must be on ONE line. No trailing commas. Straight double quotes only."""

    log.info("  Step 3: Formatting as JSON...")
    return parse_json(claude_with_retry(client, format_prompt, web=False, max_tokens=4000))


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
<p class="sec" style="margin-top:0">Matched roles &mdash; tailored resume &amp; cover letter included</p>
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
    log.info(f"  Processing: {name} | resume: {'yes' if profile.get('_resume_b64') else 'no'} | CLs: {len(profile.get('_cover_letter_docs', []))}")
    try:
        data = search_jobs(client, profile, today_str)
        for j in data.get("jobs",[]):
            log.info(f"  -> {j.get('title')} @ {j.get('organization')}")
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
