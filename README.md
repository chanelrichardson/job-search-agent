# Job Search Agent

An automated, AI-powered job search pipeline. Candidates sign up once via a hosted web form, upload their resume and cover letter, and receive a personalized weekly digest — matched roles, a tailored resume version, a custom cover letter, and pre-filled application answers — directly to their inbox.

**Stack:** Python · Claude API · GitHub Actions · Vercel · GitHub (private data repo)  
**Cost:** ~$0.10–0.20 per user per weekly digest · Zero infrastructure cost

---

## Architecture

```
Candidate visits job-agent.vercel.app/signup
  │  fills 4-step form: name/email, uploads resume + cover letter,
  │  describes what they want in plain English, picks schedule
  │
  ▼
Vercel serverless function (api/register.js)
  │  ├─ Claude Haiku parses natural language → structured criteria (server-side)
  │  └─ Commits profile.json + files to private data repo via GitHub API
  │
  ▼
Private GitHub repo: job-agent-users/
  └─ users/
      ├─ alex_jordan/profile.json
      ├─ alex_jordan/resume.pdf
      └─ alex_jordan/cover_letter.pdf
  
GitHub Actions (public code repo, runs Mon–Fri 8am ET)
  │  reads GITHUB_DATA_REPO secret → fetches all user folders
  │  for each user whose schedule matches today:
  │    ├─ Claude + web_search → 3-5 matched roles from industry-specific boards
  │    ├─ Claude → tailored resume highlights per role
  │    ├─ Claude → custom cover letter per role (matches candidate's voice)
  │    ├─ Claude → pre-filled application answers per role
  │    └─ Gmail SMTP → HTML digest to candidate's inbox
  ▼
Candidate's inbox
```

---

## Repository structure

This is the **public code repo** — it contains zero user data.

```
job-agent/                      ← public (safe for portfolio)
├─ agent/
│   └─ job_agent.py             ← main agent
├─ signup-app/
│   ├─ public/index.html        ← hosted signup form (Vercel)
│   ├─ api/register.js          ← serverless API endpoint
│   └─ vercel.json
├─ .github/workflows/
│   └─ job_agent.yml
└─ README.md

job-agent-users/                ← PRIVATE (never made public)
└─ users/
    ├─ alex_jordan/
    │   ├─ profile.json
    │   ├─ resume.pdf
    │   └─ cover_letter.pdf
    └─ ...
```

---

## Setup

### Step 1 — Create two GitHub repos

| Repo | Visibility | Purpose |
|------|-----------|---------|
| `job-agent` | Public | Code, signup form, GitHub Actions |
| `job-agent-users` | **Private** | User profiles, resumes, cover letters |

### Step 2 — Deploy the signup form to Vercel

1. Import `job-agent` into [vercel.com](https://vercel.com) (free plan)
2. Set root directory to `signup-app`
3. Add these environment variables in Vercel dashboard:

| Variable | Value |
|----------|-------|
| `GITHUB_TOKEN` | PAT with write access to `job-agent-users` |
| `GITHUB_DATA_REPO` | `yourusername/job-agent-users` |
| `ANTHROPIC_API_KEY` | From console.anthropic.com |

4. Deploy — your signup URL is `yourproject.vercel.app`

### Step 3 — Add secrets to the public code repo

Go to `job-agent` → Settings → Secrets and variables → Actions:

| Secret | Value |
|--------|-------|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `GMAIL_SENDER` | Gmail address that sends digests |
| `GMAIL_APP_PASSWORD` | [Gmail App Password](https://myaccount.google.com/apppasswords) |
| `DATA_REPO_TOKEN` | Same PAT as above (read access to `job-agent-users`) |
| `GITHUB_DATA_REPO` | `yourusername/job-agent-users` |

### Step 4 — Share the signup link

Send `yourproject.vercel.app` to anyone who should receive digests. That's it — no manual JSON editing, no code changes, no GitHub account required from candidates.

---

## What each digest contains

For every matched role:
- Role summary and fit analysis tied to the candidate's specific background
- **Tailored resume** — same facts, reordered and reframed for this role
- **Custom cover letter** — written in the candidate's voice using their uploaded sample
- **Pre-filled application answers** — why interested, biggest achievement, leadership style, salary expectations
- Direct apply link + source board link
- Network angle — who they might know, how to get a warm intro

Plus 5 proactive outreach targets — organizations without open postings but strong fit.

---

## Industry-specific job board targeting

The agent builds a source list from each user's industry preferences and tells Claude exactly which boards to search — not just "the web."

| Industry | Key boards |
|----------|-----------|
| Associations | asaecenter.org, associationcareernetwork.com, nonprofitjobs.org |
| Events / Meetings | mpiweb.org, pcma.org, bizbash.com, meetingsnet.com, smartmeetings.com |
| Hospitality | hcareers.com, hospitalityonline.com, hospitalityjobbase.com |
| Tech | LinkedIn, Greenhouse, Lever, Wellfound, Builtin |
| Nonprofit | idealist.org, devex.com, workforgood.org, bridgespan.org |
| Finance / Fintech | efinancialcareers.com, wellfound.com, buysidehiring.com |
| Education | higheredjobs.com, chronicle.com/jobs, edjoin.org |
| Government | usajobs.gov, governmentjobs.com |
| All users | LinkedIn, Indeed, Glassdoor, ZipRecruiter (always included) |

---

## Cost breakdown

| Component | Cost |
|-----------|------|
| Claude Haiku — job search + resume tailoring + cover letter + app fill per user | ~$0.10–0.20 |
| GitHub Actions | Free (2,000 min/month; each run ~3–5 min) |
| Vercel hosting | Free |
| Gmail SMTP | Free |

**10 users on weekly schedules:** ~$1–2/week (~$50–100/year total)

---

## Local development

```bash
git clone https://github.com/yourusername/job-agent
cd job-agent
pip install anthropic

# Create a local test user (never commit real data)
mkdir -p users/test_user
echo '{"name":"Test User","email":"test@example.com","schedule":"daily","resume_file":"resume.txt","cover_letter_file":null,"criteria":{"target_titles":["Director of Events"],"min_salary":"$130,000","location_preference":"Remote","industry_focus":["Associations","Tech"],"experience_level":"Senior (15 years)","special_instructions":"","recency_days":7,"exclude_keywords":["Entry Level","Intern"]}}' > users/test_user/profile.json
echo "Name: Test User | 15 years events experience" > users/test_user/resume.txt

export ANTHROPIC_API_KEY=sk-ant-...
export GMAIL_SENDER=you@gmail.com
export GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
# Leave GITHUB_DATA_REPO unset → agent reads from local users/ folder

python agent/job_agent.py
```
