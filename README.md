# Professional Lead Generation Agent (FOR MY MOM)

A custom automated pipeline designed to scrape niche industry job boards and deliver a curated, weekly digest of senior-level opportunities.

## Project Overview

Many senior-level roles in specialized industries, such as high-end event planning, are never posted on major aggregators like LinkedIn. This project automates the manual process of monitoring a specific list of high-value career portals. I created this specifically for my mom, so the prompt is made for her. If you clone, please update the prompt accordingly.

Every Monday morning, the agent generates a personalized HTML report containing:

**Role Descriptions:** Summarized for quick reading.

**AI-Generated Fit Analysis:** An assessment of why the candidate is a strong match for each specific role.

## Technical Architecture
The core logic resides in job_agent.py, which orchestrates the following flow:

**Web Scraping:** Targets a pre-defined list of boutique job boards and career pages.

**LLM Processing:** Utilizes Claude to parse unstructured site data, extract relevant job details, and perform a qualitative match analysis.

**Delivery:** Compiles the data into a clean, mobile-responsive HTML email for easy navigation.

## Getting Started
Prerequisites
Python 3.x

I run this using the YAML file in `.github\workflows`. 

Set this up in GitHub actions. 

This project works with the following GitHub secrets: 

Anthropic API Key (for Claude-based analysis)
SENDER_EMAIL (email address of the person sending the job search update)
RECIPIENT_EMAIL (email address of the person receiving the update, both emails can be the same)
RESUME_CONTENT (your resume)
CRITERIA_CONTENT(criteria of what to search for in json format)

Installation
Clone the repository:

Bash
git clone https://github.com/chanelrichardson/job-agent.git

Install dependencies:

As the only requiremnent for this project is the Anthropic Python library, run 
pip install anthropic 

directly.

Configure your environment variables in a .env file (see .env.example).
