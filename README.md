AI Agent for My mom

This is a simple project that sends my mom job opportunities from various websites (and yes, this really goes to her, and this is her main source of jobs that she's applying to).

My mom is an expert event planner, but she's found out through network connections that most senior event planning jobs never make it to LinkedIn. She had a decently long list of places that she would have to manually check. This instead, scrapes all of those sites, and she gets an email each Monday morning with a link to apply, a description of the job, and why she's a good match for it. 

The main logic is in job_agent.py, which uses Claude to scrape websites, and then creates an HTML output of this search that's easy for my mom to navigate. 
