# Job Search Agent

An automated, AI-powered job search pipeline that delivers personalized weekly digests — matched roles, custom cover letters, and pre-filled application answers — directly to a candidate's inbox.

Built on GitHub Actions (free tier) with zero infrastructure cost. Supports multiple users simultaneously. Each user's data is stored as an encrypted GitHub Secret and never touches the repository.

---

## What it does

Every time the agent runs, it:

1. **Searches industry-specific job boards** — not just LinkedIn. The source list is built from each user's industry preferences and includes 60+ niche boards: association career networks, hospitality job sites, meeting industry boards, tech-specific platforms, and more.
2. **Filters and ranks results** against the user's criteria: titles, salary floor, location, recency, and any custom requirements.
3. **Writes a cover letter** for each matched role — tailored to the candidate's specific background, not generic.
4. **Pre-fills application answers** for common fields (why interested, biggest achievement, leadership style, salary expectations).
5. **Sends a formatted HTML digest** to the user's inbox with everything in one place.

---

## Architecture

```
GitHub Actions (cron: Mon–Fri 8am ET)
        │
        ▼
agent/job_agent.py
        │
        ├── Reads user profiles from USER_* GitHub Secrets (encrypted)
        │
        ├── Builds industry-specific source list per user
        │   └── 60+ boards: mpiweb.org, asaecenter.org, hcareers.com,
        │       wellfound.com, idealist.org, linkedin.com, and more
        │
        ├── Claude Haiku + web_search → job matches (JSON)
        │
        ├── Claude Haiku → cover letter per role
        │
        ├── Claude Haiku → application pre-fill per role
        │
        └── Gmail SMTP → HTML email digest per user
```

**Model choice:** Claude Haiku throughout — approximately 15× cheaper than Sonnet with no meaningful quality difference for this task. Estimated cost: $0.05–0.15 per user per run.

**Multi-user:** The agent loads every environment variable starting with `USER_` and processes them in a single GitHub Actions run. Adding a new user is one new Secret — no code changes.

**Scheduling:** Each user profile has a `schedule` field (`daily`, `weekly`, `biweekly`, or a day name). The agent runs every weekday but only emails users whose schedule matches today.

---

## Setup

### 1. Fork and set the repo to public or private

The repo itself contains no user data — all profiles live in encrypted GitHub Secrets. It's safe to keep public.

### 2. Add required secrets

Go to **Settings → Secrets and variables → Actions → New repository secret**:

| Secret name | Value |
|-------------|-------|
| `ANTHROPIC_API_KEY` | From [console.anthropic.com](https://console.anthropic.com) |
| `GMAIL_SENDER` | Gmail address that sends the digests |
| `GMAIL_APP_PASSWORD` | [Gmail App Password](https://myaccount.google.com/apppasswords) — not your login password |

### 3. Add user profiles as secrets

Each user is one secret named `USER_<IDENTIFIER>` (e.g. `USER_ALEX`, `USER_JORDAN`). The value is their full profile JSON. See the profile schema below.

Profiles never appear in the repo, logs, or diffs — only in the encrypted Secrets store.

### 4. Enable GitHub Actions

The workflow file is at `.github/workflows/job_agent.yml`. It runs automatically. You can also trigger it manually from the Actions tab to test.

---

## User profile schema

```json
{
  "name": "Alex Jordan",
  "email": "alex@example.com",
  "schedule": "weekly",
  "resume": "Plain text resume — used for cover letter generation and fit analysis",
  "criteria": {
    "target_titles": ["Director of Events", "VP of Conferences"],
    "min_salary": "$130,000",
    "location_preference": "Remote or Hybrid within 30 miles of Chicago, IL",
    "industry_focus": ["Associations", "Tech", "Hospitality", "Corporate"],
    "experience_level": "Senior (15 years)",
    "special_instructions": "Prefer roles with P&L ownership. Open to 25% travel.",
    "recency_days": 7,
    "exclude_keywords": ["Entry Level", "Intern", "Assistant"]
  }
}
```

See `users/example_profile.json` for a complete example (fictional data — for local testing only).

### Generating a profile

The [signup form](signup.html) is a self-contained HTML file — open it locally in any browser. It walks through a 4-step intake:
1. Name and email
2. Resume (plain text)  
3. Describe what you're looking for in plain English — Claude extracts the structured criteria from your words, including which industries and job boards to prioritize
4. Schedule preference

The form outputs a ready-to-paste JSON profile. The repo owner adds it as a `USER_*` secret.

---

## Supported industries and job boards

The agent maintains a source map of niche boards per industry. When the search runs, it tells Claude exactly which boards to search — not just "the web." This surfaces roles that never appear on general aggregators.

| Industry | Key sources searched |
|----------|---------------------|
| Associations | asaecenter.org, associationcareernetwork.com, nonprofitjobs.org |
| Events / Meetings | mpiweb.org, pcma.org, bizbash.com, smartmeetings.com, meetingsnet.com |
| Hospitality | hcareers.com, hospitalityonline.com, hospitalityjobbase.com |
| Tech | LinkedIn, Greenhouse, Lever, Wellfound, Hacker News Jobs |
| Nonprofit | idealist.org, devex.com, bridgespan.org, workforgood.org |
| Finance / Fintech | efinancialcareers.com, wellfound.com, buysidehiring.com |
| Education | higheredjobs.com, chronicle.com/jobs, edjoin.org |
| Government | usajobs.gov, governmentjobs.com |
| All users | LinkedIn, Indeed, Glassdoor, ZipRecruiter (always included) |

---

## Cost

| Item | Cost |
|------|------|
| Claude Haiku per user per run | ~$0.05–0.15 |
| GitHub Actions | Free (2,000 min/month; each run takes ~2–4 min) |
| Gmail SMTP | Free |

Two users on weekly schedules: ~$0.20–0.60/week.

---

## Local development

```bash
git clone https://github.com/yourusername/job-agent
cd job-agent
pip install anthropic

# Create a local test profile (never commit real data)
cp users/example_profile.json users/local_test.json
# Edit local_test.json with test data

# Set env vars
export ANTHROPIC_API_KEY=sk-ant-...
export GMAIL_SENDER=you@gmail.com
export GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx

python agent/job_agent.py
```

The agent reads from `users/*.json` as a fallback when no `USER_*` env vars are present, making local iteration straightforward.

---

## Project structure

```
job-agent/
├── agent/
│   └── job_agent.py          # Core agent — multi-user, source-aware
├── users/
│   ├── .gitkeep              # Real profiles go in Secrets, not here
│   └── example_profile.json  # Fictional example for local dev
├── .github/
│   └── workflows/
│       └── job_agent.yml     # Runs Mon–Fri 8am ET
├── signup.html               # Self-contained profile generator
└── README.md
```
