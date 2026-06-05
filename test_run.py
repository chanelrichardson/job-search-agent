#!/usr/bin/env python3
"""
Local test runner — runs the agent immediately for ONE user
so you can verify the email output without waiting for Monday.

Usage:
  pip install anthropic
  python test_run.py

It reads from users/ folder locally, or you can paste a profile inline below.
Set your env vars first:
  export ANTHROPIC_API_KEY=sk-ant-...
  export GMAIL_SENDER=you@gmail.com
  export GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx

To test WITHOUT sending email (just print output):
  DRY_RUN=true python test_run.py
"""

import os, json, sys
os.environ.setdefault('GITHUB_DATA_REPO', '')  # not needed for local test
os.environ.setdefault('GITHUB_TOKEN', '')

# ── Inline test profile — edit this to match your real info ──────────────────
TEST_PROFILE = {
    "name": "Chanel Richardson",
    "email": "crichardson1399@gmail.com",   # <-- where the test digest will be sent
    "schedule": "daily",               # force it to run regardless of day
    "_resume": """
Cora “Chanel” Richardson
Data strategist with a background in risk governance, data engineering, and computational redistricting. Proven track record in developing technical solutions for civil rights litigation and architecting responsible AI frameworks within global-scale cloud environments. Expert in translating technical risks for legal and executive stakeholders.
crichardson1399@gmail.com
Washington DC, 20018
(336)-749-1311

Technical Skills
NLP & ML: LLMs/SLMs (Vertex AI, Transformers), Text Representation (TF-IDF, BERT, Embeddings), Fuzzy Matching, Cosine Similarity, Sentiment Analysis
Programming: Python (Flask, NLTK, BeautifulSoup, Pandas, Geopandas, SciKitLearn, Keras, Tensorflow), Rust, SQL, Javascript / Typescript, C++, HTML
Data Ops & Cloud: Google Cloud Platform (GCP), BigQuery, AWS (EC2 & Lambda), Apache Airflow, Docker, CI/CD, Git
Professional Experience
Google, Data Strategy & Modeling Lead, Cloud Risk & Compliance (Oct 2025 – Present)
Lead the data strategy for Google Cloud’s Risk & Compliance organization, defining what data we use, how we use it, and architecting platforms using Typescript, AppScript, SQL, and Python for ease of non technical access.
Design, architect,  and improve "OneGRC," a unified data model centralizing seven years of compliance data and compliance data platforms.
Act as the primary bridge between legal and regulatory compliance leads  and engineering execution, ensuring technical roadmaps align with evolving legal mandates.
Created an API suite to control the seamless flow of data between multiple disparate internal platforms. Develop agentic AI workflows to enhance how non technical users can achieve data driven and automatic governance, risk, and compliance.
Analyze and compare various AI models for use in risk reporting, risk communication, and risk analysis.
Google, Data Analyst, Cloud Risk Reporting (June 2023 – Oct 2025)
Spearheaded "Risk Reporting 2.0," transitioning the organization from reactive reporting to a proactive, historical analysis methodology used to identify and mitigate emerging risks.
Architected suite of Looker dashboards centralizing Key Risk Indicators (KRIs) across multiple domains, providing leadership with real-time visibility into the organization’s risk posture.
Orchestrated cross-functional metric onboarding, collaborating with diverse teams to define, validate, and visualize high-impact data points for executive-level risk reports.
Designed a multi-stage data flow integrating scraped content with Vertex AI (LLM) for automated insight generation.
Metric Geometry and Gerrymandering Group, Research Analyst (August 2021 - May 2023)
Co-authored and maintained the gerrytools Python package, an open-source library used by the redistricting community and legal teams, contributing to internal GitHub workflows and external documentation.
Analyzed large voter files from Texas and North Carolina to perform ecological inference simulations, determining the statistically probable voting outcomes of districts across each state to analyze potential partisan or racial gerrymandering.
Developed and executed complex computational and statistical analyses using GIS, Python, and Rust on massive geospatial datasets used to support litigation across eight states, ensuring data integrity and reliability for high-stakes legal proceedings.
Interfaced with expert witnesses and lawyers to translate technical findings into clear narratives, demonstrating strong stakeholder communication and commitment to clear process documentation.
Education
Duke University
M.S. Electrical Engineering 
2020-2021
Tufts University
B.S. Computer Engineering
2016-2020

Talks & Publications
"Using Python to Protect Voting Rights," SciPy Conference, July 2022
"Graphs, Stats, and Math Take the Stand: The Role of Mathematics in Redistricting Litigation," Math Society Conference, Brown University, October 2022
"Ecological Inference & Voting Rights," Joint Mathematics Meetings, January 2023 
"Aggregating Community Maps," SIGSPATIAL '22: Proceedings of the 30th International Conference on Advances in Geographic Information Systems (co-authored)


""",
    "_cover_letters": ["""Greetings, 
I am writing to apply for the position of Analytics Engineer at Coinbase. Having been excited about the future of cryptocurrency since I was a teenager, I’ve been using Coinbase for years, and am still an active user of the Coinbase app. In a work environment, I’m most keen to work with data, processing data, and making reliable, automated solutions to allow others to work with data at scale. My current background, as the tooling lead for risk reporting within Google Cloud CISO and my background as a Software Developer (primarily using Python) at the Metric Geometry and Gerrymandering Group (MGGG) gives me a solid background for this role. 
In my current role, due to team resizing over the last year, I wear multiple hats. My team has ownership of all risk reports that go to Google Cloud leadership, Google Cloud General Managers, and Google Cloud Product Teams. To do this, have done work ranging from report design, dashboard design within Looker, report automation, and data tooling. Through this, I have contributed heavily to the creation of a data mart for use by my team and other partner teams that centralize the information we need for quality risk measurement. This process involved strong usage of data model design skills, SQL skills, and version controlling to collaborate with other stakeholders. We were able to officially stand this up at the end of 2024, creating a significant impact across my organization. Another relevant project I have been involved in is a risk modeling effort, using real data on Google customers, infrastructure, controls, and capacity management to determine the potential financial impact of data center outages where we have high concentrations of customers. This model was written in Python, with data collection happening through SQL querying. Finally, I want to highlight that an overall emphasis for my team is using risk metrics to create a clear story for people with a lot on their plates. Through careful, but efficient analysis, we are able to relate efforts across disparate domains to help our stakeholders understand which risks to prioritize. Myself and my team pride ourselves on a transition from a compliance based risk governance model to a risk-based risk governance model. 
In my previous role at MGGG, I primarily supported multiple clients in creating court cases to sue various proposed maps during the 2020 redistricting cycle. This job is definitely where my Python skills were enhanced. We ran a novel algorithm called “Gerry Chain” which uses Monte Carlo Markov Chains to create maps on the order of hundreds of thousands to millions.Displaying metrics about these maps was always done using matplotlib. In order to run these markov chains quickly, I worked with one other lab member to set up an EC2 instance and monitor our daily monetary usage to keep things under control for our team. During my day to day, I wrote custom Python scripts for each map, so we could analyze the essential items we cared about for the specific case (communities of interest, racial bias, partisan bias, etc.). I also helped contribute to our external GitHub library (gerrytools) which is used by many within the redistricting community. 
Currently, I’m looking to continue on with my journey from Google. While our team is restructuring, I’m finding fewer opportunities to do the technically rigorous projects that have made my journey thus far fulfilling. I’m looking for my next challenge within a field that I care about to support a company that feels a little bit more personally relevant to me. I’ve been excited about cryptocurrency innovation for over 10 years now, having completed many online courses (and a few in school) to learn about blockchain consensus and to understand the future of crypto. While I know I would not directly contribute to these items, I would feel more fulfilled knowing that I’m contributing to others' advancement in this area. 
While I cannot express everything I bring to the table within this letter, looking through the bullet points of qualifications and nice to haves, I have experience I can speak to with most bullet points. I would greatly appreciate the opportunity to embark on my next career step at Coinbase, and I look forward to hearing back from you soon. 
Best, 
Chanel Richardson

""",  
"""Greetings,
My name is Chanel Richardson, and I am applying for the Data Engineer position at DataKind. I come with a deep passion for building technology that serves communities, a foundation in equitable data practices, and over five years of software development and data engineering experience, I am eager to contribute to the success of your UDTS platform.
The balance of building efficiently at scale with enabling client or stakeholder needs perfectly aligns with my professional journey. Over the past three years at Google, my work as a Solutions Consultant and Data Strategist for Google Cloud Risk & Compliance has required me to act at the boundary of technical expertise and stakeholder coordination. Regularly, I operate as a technical team of one within my immediate team, independently designing end to end solutions, gathering stakeholder requirements, and pushing pipelines into production using Python, TypeScript, and Google Cloud Platform (GCS, GAE).
A core component of DataKind’s mission is translating complex systems into accessible value for partners, which has been the defining theme of my recent work at Google. To address regulatory requirements, I built an internal tool from scratch that uses fuzzy matching to map external customer names from regulators to internal entities. For me, this process encompassed everything from initial architecture and user acceptance testing (UAT) to production deployment. Additionally, I designed a system that ingests resilience testing data, transforms it into queryable relational tables, and exposes it via dashboards tailored to help non-technical enterprise customers seamlessly track metrics. Another project involved architecting an ontological RAG system that transforms cybersecurity risk logs into queryable answers that senior executives can understand in their own business terms. I am comfortable being the primary technical voice in the room, bringing the patience and relationship skills necessary to guide external institutional teams through using new sources and platforms for ingesting data.
Before my time at Google, I served as a Data Analyst for the Metric Geometry and Gerrymandering Group (MGGG), a redistricting lab out of Tufts University. This work was a lesson for me in the power of data narrative and measurement. Most of my collaborators had no mathematical background, and I became highly skilled at transforming raw spatial data into insights that my Principal Investigator could present as an expert witness in court. Technically, I ran deep statistical analyses using Markov Chain Monte Carlo (MCMC) simulations to establish baseline state maps, and served as the lab's ecological inference expert to evaluate voting patterns across proposed districts along racial lines.
My commitment to this work extends to my personal time. I am an active contributor to CivicTechDC, where I lead the web scraping architecture for a project called Court Scraper. Built using JavaScript, Puppeteer, and AWS, this platform aggregates housing court dockets to proactively identify tenants facing eviction, translating municipal data into actionable walk sheets for housing organizers and canvassers.
While I am incredibly proud of the automated tools I have shipped at Google, I find myself looking for an environment where data engineering is intrinsically tied to a mission I believe in. I thrive on giving people tools that simplify their work, and I want to dedicate my engineering experience to advancing equity and improving outcomes for people, in this case students, at scale.
Thank you for your time and dedication to social impact. I look forward to the possibility of discussing how my skills can serve DataKind and your partner institutions.
Sincerely,
Chanel Richardson
"""       ],

    "criteria": {
        "target_titles": ["Data Engineer", "Data Strategist", "Data Science Manager", "Reasearch Engineer"],
        "min_salary": "$120,000",
        "location_preference": "Remote, Hybrid, In Person in the Washington DC area",
        "industry_focus": ["Non Profit", "Government", "Tech"],
        "experience_level": "Up to 6 years",
        "special_instructions": "Focus on data-driven roles with a strong technical background that impact and empower people in civics, environment, or creative spaces.",
        "recency_days": 7,
        "exclude_keywords": ["Entry Level", "Intern", "Assistant"]
    }
}
# ─────────────────────────────────────────────────────────────────────────────

DRY_RUN = os.getenv('DRY_RUN', '').lower() in ('true', '1', 'yes')

# Patch load_user and list_user_slugs to use our inline profile
import importlib, types

# Load the agent module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'agent'))
import job_agent

# Override the data repo functions with local versions
def mock_list_user_slugs():
    return ['test_user']

def mock_load_user(slug):
    return TEST_PROFILE

def mock_send_email(profile, subject, html, plain):
    if DRY_RUN:
        print("\n" + "="*60)
        print("DRY RUN — email NOT sent")
        print(f"To:      {profile['email']}")
        print(f"Subject: {subject}")
        print("="*60)
        print(plain[:2000])
        print("\n[HTML email also generated — open digest_preview.html to view]")
        with open('digest_preview.html', 'w') as f:
            f.write(html)
        print("Saved to digest_preview.html")
    else:
        job_agent.send_email.__wrapped__(profile, subject, html, plain)

# Apply patches
job_agent.list_user_slugs = mock_list_user_slugs
job_agent.load_user = mock_load_user

if DRY_RUN:
    # Wrap send_email to intercept
    original_send = job_agent.send_email
    original_send.__wrapped__ = original_send
    job_agent.send_email = mock_send_email

if __name__ == '__main__':
    from anthropic import Anthropic
    from datetime import datetime

    key = os.getenv('ANTHROPIC_API_KEY')
    if not key:
        print("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    if not DRY_RUN and not os.getenv('GMAIL_SENDER'):
        print("ERROR: GMAIL_SENDER not set. Use DRY_RUN=true to test without email.")
        sys.exit(1)

    today = datetime.now().strftime("%A, %B %d, %Y")
    print(f"Running test for: {TEST_PROFILE['name']}")
    print(f"Sending to: {TEST_PROFILE['email']}")
    print(f"Dry run: {DRY_RUN}")
    print(f"Date: {today}\n")

    client = Anthropic(api_key=key)
    job_agent.process_user(client, 'test_user', today)
    print("\nDone.")
