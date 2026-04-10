# LaTonya's Job Search Agent — Setup Guide

## What this does
Every evening at 7 PM Eastern, GitHub's servers automatically:
1. Call the Anthropic API (with web search) to find senior event executive roles posted in the last 7 days
2. Filter by LaTonya's criteria ($150K+, remote/hybrid near Winston-Salem, right titles/sectors)
3. Build a beautiful HTML email with job descriptions, why each role fits, network angles, and apply links
4. Add 5 proactive outreach targets — organizations worth contacting even with no open role
5. Send it all to LaTonya's Gmail inbox

Your computer does not need to be on. GitHub hosts and runs everything for free.

---

## What you need before starting

- A **GitHub account** (free) — github.com
- An **Anthropic API key** — console.anthropic.com
- A **Gmail App Password** for the sending account (instructions below)

Total setup time: ~15 minutes.

---

## Step 1 — Get your Anthropic API key

1. Go to https://console.anthropic.com
2. Click **API Keys** in the left sidebar
3. Click **Create Key**, name it `LaTonya Job Agent`
4. Copy the key (starts with `sk-ant-...`) — save it somewhere, you'll use it in Step 4

---

## Step 2 — Set up a Gmail App Password

Gmail requires a special App Password instead of your real password for scripted sending.

1. Go to https://myaccount.google.com/security
2. Make sure **2-Step Verification** is turned ON (required)
3. Search "App Passwords" in the Google account search bar and click it
4. Under "Select app" choose **Mail**, "Select device" choose **Other** → type `Job Agent`
5. Click **Generate** — you get a 16-character password like `abcd efgh ijkl mnop`
6. Copy it — you'll use it in Step 4

> The SENDING Gmail (GMAIL_SENDER) needs the App Password. This can be your Gmail or any Gmail account.
> It does NOT have to be LaTonya's Gmail. The digest will be delivered to her inbox regardless.

---

## Step 3 — Create a private GitHub repository and upload files

1. Go to https://github.com/new
2. Name it something like `latonya-job-agent`
3. Set it to **Private** (important — keeps your code and config hidden)
4. Click **Create repository**
5. Upload these two files from the zip you downloaded:
   - `job_agent.py` → upload to the root of the repo
   - `.github/workflows/daily_job_search.yml` → this must be at exactly that path

**Easiest way to upload with the correct folder structure:**

On the repo page, click **Add file** → **Upload files**.
- Drag `job_agent.py` in and commit it first.
- Then click **Add file** → **Create new file**, type the path `.github/workflows/daily_job_search.yml` in the filename box (GitHub will auto-create the folders), paste in the contents of that file, and commit.

---

## Step 4 — Add your secrets to GitHub

Your API keys and passwords are stored as encrypted GitHub Secrets — they are never visible in your code or logs.

1. In your GitHub repo, click **Settings** (top menu)
2. In the left sidebar, click **Secrets and variables** → **Actions**
3. Click **New repository secret** and add each of these four:

| Secret name | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Your key from Step 1 (e.g. `sk-ant-...`) |
| `GMAIL_SENDER` | The Gmail you're sending FROM (e.g. `youremail@gmail.com`) |
| `GMAIL_APP_PASSWORD` | The 16-char App Password from Step 2 (e.g. `abcd efgh ijkl mnop`) |
| `RECIPIENT_EMAIL` | LaTonya's Gmail: `mslatonyabroome@gmail.com` |

---

## Step 5 — Test it manually

Before waiting for the 7 PM schedule, trigger a manual run to confirm everything works:

1. In your GitHub repo, click the **Actions** tab
2. In the left sidebar, click **LaTonya Daily Job Search**
3. Click **Run workflow** → **Run workflow** (the green button)
4. Watch the run — click on it to see live logs
5. Check LaTonya's inbox — the digest should arrive within 2–3 minutes

If it succeeds, you're done. It will now run automatically every evening at 7 PM Eastern.

---

## Timing note

The workflow runs at `0 23 * * *` UTC = 7:00 PM Eastern Standard Time.

To change the delivery time, edit the `cron:` line in `daily_job_search.yml`:

| Desired time (Eastern) | Cron value |
|---|---|
| 6:00 PM | `0 22 * * *` |
| 7:00 PM | `0 23 * * *` |
| 8:00 PM | `0 0 * * *` |
| 9:00 PM | `0 1 * * *` |

Use https://crontab.guru to find the right UTC value for any time.

Note: GitHub Actions uses UTC and does not auto-adjust for Daylight Saving Time. You may want to shift by 1 hour in March and November.

---

## Ongoing cost

- **GitHub Actions**: Free — the free tier gives 2,000 minutes/month; this script uses ~2 minutes/day
- **Anthropic API**: ~$0.05–0.15 per run depending on search results and web search usage

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Run fails with `Authentication failed` | Double-check the `GMAIL_APP_PASSWORD` secret — re-generate one in Google if needed |
| Run fails with `No JSON found` | Rare API hiccup — re-run manually from the Actions tab. Usually self-resolves |
| Email goes to LaTonya's spam | Add the sending Gmail address to her contacts |
| Workflow not running at 7 PM | GitHub sometimes delays scheduled runs up to 15 min. Check the Actions tab for error badges |
| Need to update search criteria | Edit `job_agent.py` directly on GitHub (click the file → pencil icon) and commit |
| Want to pause it | Actions tab → click the workflow → **...** menu → **Disable workflow** |
