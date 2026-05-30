# Job Search Agent

Automated job search pipeline that emails curated roles with AI-written cover letters and pre-filled application answers. Runs on GitHub Actions — zero hosting cost.

---

## Privacy setup — read this first

**Make your repo private.** User data (resumes, emails, salaries) is stored as GitHub Secrets, not committed files. But the repo itself should still be private.

Go to: **Settings → General → Danger Zone → Change repository visibility → Private**

---

## How to add a user

### Option A — Use the signup form (recommended for non-technical users)

Share the signup artifact (the Claude link) with anyone who needs to use the agent. They fill out a 4-step form:
1. Name and email
2. Resume (plain text)
3. Describe what they're looking for in plain English — AI extracts titles, salary, location, industries, and which specific job boards to search
4. Download their `yourname.json` file

Then you (the repo owner) add their profile as a GitHub Secret:

1. Open Settings → Secrets and variables → Actions → New repository secret
2. Name it `USER_YOURNAME` (e.g. `USER_LATONYA`, `USER_MARCUS`) — all caps, no spaces
3. Paste the entire contents of their JSON file as the value
4. Save

That's it. The agent automatically finds all secrets starting with `USER_` and processes each one.

### Option B — Add directly as a secret (technical users)

Create a JSON profile following this structure and add it as a `USER_<NAME>` secret:

```json
{
  "name": "LaTonya Broome",
  "email": "latonya@example.com",
  "schedule": "weekly",
  "resume": "Full resume text here...",
  "criteria": {
    "target_titles": ["Director of Global Events", "VP of Conferences"],
    "min_salary": "$150,000",
    "location_preference": "Remote or Hybrid within 30 miles of Winston-Salem, NC",
    "industry_focus": ["Associations", "Events", "Hospitality", "Tech"],
    "experience_level": "Senior Executive (30+ years)",
    "special_instructions": "Focus on roles with strategic ownership and multi-million dollar budget management.",
    "recency_days": 7,
    "exclude_keywords": ["Entry Level", "Intern", "Assistant", "Coordinator"]
  }
}
```

---

## Required GitHub Secrets

| Secret | Value |
|--------|-------|
| `ANTHROPIC_API_KEY` | From console.anthropic.com |
| `GMAIL_SENDER` | Gmail address that sends digests |
| `GMAIL_APP_PASSWORD` | Gmail App Password (not your login password) |
| `USER_LATONYA` | LaTonya's full JSON profile |
| `USER_YOURNAME` | Your full JSON profile |

**Getting a Gmail App Password:**
1. Enable 2-factor auth on the sending Gmail account
2. Go to myaccount.google.com/apppasswords
3. Create one called "Job Agent" — copy the 16-character code

---

## Schedule options

Each user's `"schedule"` field controls when they get digests. The GitHub Action runs every weekday morning (8am ET) but only emails users whose schedule matches today.

| Value | When it runs |
|-------|-------------|
| `"daily"` | Every weekday |
| `"weekly"` | Every Monday |
| `"biweekly"` | 1st and 3rd Monday |
| `"monday"` / `"tuesday"` / etc. | That specific day |

---

## What's in each digest

For each matched role:
- Role summary and fit analysis tied to the candidate's specific background
- Network angle — who they might know, how to get a warm intro
- Cover letter — custom-written, 3 paragraphs, ready to paste
- Application quick-fill — pre-written answers for common application questions
- Direct apply link + source board link

Plus 5 proactive outreach targets — organizations without open postings but strong fit.

---

## Which job boards does it search?

The agent builds a source list from the user's industries. For example:
- **Associations** → asaecenter.org, associationcareernetwork.com, nonprofitjobs.org
- **Events/Meetings** → mpiweb.org, pcma.org, bizbash.com, smartmeetings.com, meetingsnet.com
- **Hospitality** → hcareers.com, hospitalityonline.com, pcma.org
- **Tech** → LinkedIn, Greenhouse, Lever, Wellfound, Hacker News Jobs
- **Nonprofit** → idealist.org, devex.com, bridgespan.org
- **General** → LinkedIn, Indeed, Glassdoor, ZipRecruiter (always included)

The AI searches these sources specifically, not just "the web" — which means niche roles that never appear on aggregators get surfaced.

---

## Cost

| Item | Cost |
|------|------|
| Claude Haiku per user per run | ~$0.05–0.15 |
| GitHub Actions | Free (each run uses ~2–4 min of the 2,000 free min/month) |
| Gmail SMTP | Free |

Two users running weekly = ~$0.10–0.30/week = roughly $5–15/month total.

---

## Project structure

```
job-agent/
├── agent/
│   └── job_agent.py      ← main agent (reads USER_* secrets)
├── users/
│   └── .gitkeep          ← placeholder; real profiles go in Secrets
├── .github/
│   └── workflows/
│       └── job_agent.yml ← runs Mon–Fri 8am ET
└── README.md
```

---

## Why GitHub Pages won't work for a private repo

GitHub Pages requires a public repo on the free plan. Since user data must stay private, the signup form is distributed as a Claude artifact instead — no hosting required. Anyone with the link can use it to generate their profile JSON, then send it to the repo owner to add as a secret.
