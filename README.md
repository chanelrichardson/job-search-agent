# Job Search Agent

A **multi-user, budget-optimized** AI job search pipeline. Each user gets a weekly email with matched roles, custom cover letters, and pre-filled application answers — all generated automatically.

Built for senior executives. ~$0.05–0.15 per digest. Zero monthly hosting cost.

---

## How it works

```
users/latonya.json ──┐
users/marcus.json  ──┼──▶ GitHub Actions (Mon–Fri 8am ET)
users/jane.json    ──┘          │
                                ▼
                    job_agent.py (runs all users)
                         │
                    Claude Haiku + Web Search
                         │
                    ┌────┴──────────────────┐
                    │  Job search results   │
                    │  Cover letters        │
                    │  App pre-fill answers │
                    └────────────────────────┘
                         │
                    Gmail SMTP ──▶ Each user's inbox
```

Each user profile has a `schedule` field. The agent runs every weekday but only sends digests to users whose schedule matches today:
- `"daily"` → runs every weekday
- `"weekly"` → runs every Monday
- `"biweekly"` → runs 1st and 3rd Monday
- `"monday"`, `"tuesday"`, etc. → runs on that specific day

---

## Setup

### For non-technical users (the easy path)

1. Open `signup.html` in your browser (or the hosted version)
2. Fill out the 4-step form
3. Download your `yourname.json` file
4. Follow the 3 steps shown at the end

That's it. No coding needed.

---

### For technical users / repo owners

#### 1. Fork this repository

#### 2. Add GitHub Secrets

Go to **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
|--------|-------|
| `ANTHROPIC_API_KEY` | Your key from [console.anthropic.com](https://console.anthropic.com) |
| `GMAIL_SENDER` | Gmail address that sends the digests |
| `GMAIL_APP_PASSWORD` | Gmail App Password (not your regular password) |

**Getting a Gmail App Password:**
1. Enable 2-factor auth on the Gmail account
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Create one named "Job Agent"

#### 3. Add user profiles

Drop JSON files into the `users/` directory. One file per user.

```
users/
  latonya_broome.json
  marcus_webb.json
  your_name.json
```

#### 4. Enable GitHub Actions

The workflow is in `.github/workflows/job_agent.yml`. It runs automatically at 8am ET on weekdays. You can also trigger it manually from the Actions tab.

---

## User profile format

```json
{
  "name": "Jane Smith",
  "email": "jane@example.com",
  "schedule": "weekly",
  "resume": "Full resume text here...",
  "criteria": {
    "target_titles": ["VP of Marketing", "CMO", "Head of Growth"],
    "min_salary": "$200,000",
    "location_preference": "Remote or Hybrid — near Chicago, IL",
    "industry_focus": ["SaaS", "Fintech", "Media"],
    "experience_level": "Senior Executive (20+ years)",
    "special_instructions": "Prioritize B2B SaaS companies with Series B+",
    "recency_days": 7,
    "exclude_keywords": ["Entry Level", "Intern", "Assistant"]
  }
}
```

---

## Cost breakdown

| Component | Cost |
|-----------|------|
| Claude Haiku (job search + cover letters + app fill) | ~$0.04–0.12 per user per run |
| GitHub Actions | Free (2,000 min/month, each run takes ~2–4 min) |
| Gmail SMTP | Free |
| **Total per user per week** | **~$0.05–0.15** |

**Cost for 10 users running weekly:** ~$0.50–1.50/week (~$6–18/month)

### Model choice
The agent uses **Claude Haiku** (`claude-haiku-4-5`) by default — it's 15x cheaper than Sonnet and handles all tasks well. To switch to a more powerful model, change `MODEL` at the top of `agent/job_agent.py`.

---

## What's in each digest

For each matched role:
- **Role summary** — what the job actually is
- **Why it fits you** — tied to your specific background
- **Network angle** — who you might know or how to get a warm intro
- **Cover letter** — custom-written, ready to paste
- **Application quick-fill** — pre-written answers for common questions (Why interested? Biggest achievement? Leadership style?)
- **Apply button** — direct link

Plus **5 proactive targets** — organizations that don't have open roles but are a strong fit to reach out to cold.

---

## Project structure

```
job-agent/
├── agent/
│   └── job_agent.py          # Main agent (multi-user)
├── users/
│   ├── latonya_broome.json   # Example user profile
│   └── marcus_webb.json      # Example user profile
├── .github/
│   └── workflows/
│       └── job_agent.yml     # GitHub Actions schedule
├── signup.html               # Self-serve signup UI
└── README.md
```

---

## Adding the signup page to GitHub Pages

To host the signup form so others can self-serve:

1. Go to **Settings → Pages**
2. Set source to `main` branch, root `/`
3. Your form will be at `https://yourusername.github.io/job-agent/signup.html`

Users can fill out the form, download their JSON, and open a pull request (or email it to you) to be added.

---

## Scaling considerations

- **50+ users**: Consider splitting into multiple repositories or using a GitHub Action matrix to parallelize runs
- **Deduplication**: The agent doesn't track previously seen jobs — each run is fresh. Add a `seen_jobs.json` per user if you want to suppress repeats
- **Custom boards**: Edit the `SEARCH_PROMPT` to target specific job boards for niche industries
