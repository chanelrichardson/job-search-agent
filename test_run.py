#!/usr/bin/env python3
"""
Full end-to-end test — runs the agent for ALL users in your data repo,
prints the complete digest output to the console, and saves each digest
as an HTML file you can open in a browser.

No emails are sent. No Claude calls are skipped.
This is the real thing, just with email replaced by console output.

Usage (PowerShell):
  $env:DATA_REPO_TOKEN="github_pat_..."
  $env:GH_DATA_REPO="chanelrichardson/job-agent-users"
  $env:ANTHROPIC_API_KEY="sk-ant-..."
  python test_run.py

Or to test a single user:
  python test_run.py chanelrichardson  (pass the folder slug)

Output:
  - Console: full plain-text digest for each user
  - digest_<slug>.html: open in browser to see exactly what the email looks like
"""

import os, sys, json
from datetime import datetime
from anthropic import Anthropic

# ── Pull env vars ─────────────────────────────────────────────────────────────
os.environ["GITHUB_TOKEN"]     = os.getenv("DATA_REPO_TOKEN") or os.getenv("GITHUB_TOKEN") or ""
os.environ["GITHUB_DATA_REPO"] = os.getenv("GH_DATA_REPO")   or os.getenv("GITHUB_DATA_REPO") or ""
ANTHROPIC_API_KEY              = os.getenv("ANTHROPIC_API_KEY")

if not os.environ["GITHUB_TOKEN"]:
    print("ERROR: Set DATA_REPO_TOKEN env var")
    sys.exit(1)
if not os.environ["GITHUB_DATA_REPO"]:
    print("ERROR: Set GH_DATA_REPO env var")
    sys.exit(1)
if not ANTHROPIC_API_KEY:
    print("ERROR: Set ANTHROPIC_API_KEY env var")
    sys.exit(1)

# ── Load the agent ────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'agent'))
import job_agent

# ── Patch send_email to print + save HTML instead ────────────────────────────
def fake_send_email(profile, subject, html, plain):
    slug = profile.get("name","user").lower().replace(" ","_")
    print("\n" + "█"*70)
    print(f"  DIGEST FOR: {profile.get('name')}")
    print(f"  Would email: {profile.get('email')}")
    print(f"  Subject: {subject}")
    print("█"*70)
    print(plain)

    # Save HTML so you can open it in a browser
    filename = f"digest_{slug}.html"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"\n  → HTML saved to {filename} — open in browser to preview the email")
    print("█"*70 + "\n")

job_agent.send_email = fake_send_email

# ── Run ───────────────────────────────────────────────────────────────────────
today_str = datetime.now().strftime("%A, %B %d, %Y")
client    = Anthropic(api_key=ANTHROPIC_API_KEY)

# If a slug is passed as argument, only run that user
filter_slug = sys.argv[1] if len(sys.argv) > 1 else None

print(f"\nJob Search Agent — Test Run")
print(f"Date: {today_str}")
print(f"Repo: {os.environ['GITHUB_DATA_REPO']}")
if filter_slug:
    print(f"User filter: {filter_slug}")
print("="*70 + "\n")

# Load users
slugs = job_agent.list_user_slugs()
if not slugs:
    print("ERROR: No users found in data repo. Check DATA_REPO_TOKEN and GH_DATA_REPO.")
    sys.exit(1)

if filter_slug:
    if filter_slug not in slugs:
        print(f"ERROR: Slug '{filter_slug}' not found. Available: {slugs}")
        sys.exit(1)
    slugs = [filter_slug]

print(f"Found {len(slugs)} user(s): {slugs}\n")

# Force all schedules to run today regardless of day
original_should_run = job_agent.should_run
job_agent.should_run = lambda schedule: True

for slug in slugs:
    job_agent.process_user(client, slug, today_str)

print("\nTest complete.")
print("Open the digest_*.html files in your browser to review each email.")