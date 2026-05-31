/**
 * POST /api/register
 *
 * Receives a user profile (with base64-encoded resume + cover letter files),
 * commits them to the private job-agent-users GitHub repo, and returns success.
 *
 * Environment variables required on Vercel:
 *   GITHUB_TOKEN        - Personal access token with repo write access to the private data repo
 *   GITHUB_DATA_REPO    - e.g. "yourusername/job-agent-users"
 *   ANTHROPIC_API_KEY   - Used server-side to parse the natural language intake
 */

export default async function handler(req, res) {
  // CORS for local dev
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const GITHUB_TOKEN     = process.env.GITHUB_TOKEN;
  const GITHUB_DATA_REPO = process.env.GITHUB_DATA_REPO; // "owner/repo"
  const ANTHROPIC_KEY    = process.env.ANTHROPIC_API_KEY;

  if (!GITHUB_TOKEN || !GITHUB_DATA_REPO) {
    return res.status(500).json({ error: 'Server misconfigured — contact the admin.' });
  }

  try {
    const body = req.body;
    const { name, email, schedule, naturalLanguageRequest, resumeBase64, resumeFilename, coverLetterBase64, coverLetterFilename, existingSlug } = body;

    if (!name || !email || !naturalLanguageRequest) {
      return res.status(400).json({ error: 'Name, email, and job description are required.' });
    }

    // 1. Parse natural language → structured criteria (server-side, API key never exposed)
    const criteria = await parseCriteria(naturalLanguageRequest, name, ANTHROPIC_KEY);

    // 2. Build the user profile object
    // Use existingSlug if this is an update from a returning user
    const slug = existingSlug || name.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '');
    const profile = {
      name,
      email,
      schedule: schedule || 'weekly',
      resume_file: resumeFilename || null,       // filename stored alongside
      cover_letter_file: coverLetterFilename || null,
      criteria,
      registered_at: new Date().toISOString(),
    };

    // 3. Commit files to the private data repo
    const commits = [];

    // Profile JSON
    commits.push(commitFile(
      GITHUB_TOKEN,
      GITHUB_DATA_REPO,
      `users/${slug}/profile.json`,
      JSON.stringify(profile, null, 2),
      `Add/update profile for ${name}`
    ));

    // Resume file (if provided)
    if (resumeBase64 && resumeFilename) {
      commits.push(commitFile(
        GITHUB_TOKEN,
        GITHUB_DATA_REPO,
        `users/${slug}/${resumeFilename}`,
        resumeBase64,
        `Upload resume for ${name}`,
        true // already base64
      ));
    }

    // Cover letter file (if provided)
    if (coverLetterBase64 && coverLetterFilename) {
      commits.push(commitFile(
        GITHUB_TOKEN,
        GITHUB_DATA_REPO,
        `users/${slug}/${coverLetterFilename}`,
        coverLetterBase64,
        `Upload cover letter for ${name}`,
        true
      ));
    }

    await Promise.all(commits);

    return res.status(200).json({
      success: true,
      message: `Profile saved for ${name}. You'll receive your first digest on your next scheduled run.`,
      slug,
      criteria, // send back so the UI can show a preview
    });

  } catch (err) {
    console.error('Register error:', err);
    return res.status(500).json({ error: 'Failed to save profile. Please try again.' });
  }
}

/**
 * Call Claude Haiku server-side to parse natural language into structured criteria.
 */
async function parseCriteria(naturalLanguage, name, apiKey) {
  if (!apiKey) {
    // Fallback: return minimal criteria if no API key configured
    return {
      target_titles: [],
      min_salary: 'Not specified',
      location_preference: 'Remote',
      industry_focus: [],
      experience_level: 'Senior',
      special_instructions: naturalLanguage,
      recency_days: 7,
      exclude_keywords: ['Entry Level', 'Intern', 'Assistant'],
    };
  }

  const prompt = `Extract structured job search criteria from this description. Return ONLY valid JSON, no markdown, no explanation.

User: ${name}
Description: ${naturalLanguage}

Return this exact structure:
{
  "target_titles": ["title1", "title2"],
  "min_salary": "$XXX,000",
  "location_preference": "Remote / Hybrid / On-site and city",
  "industry_focus": ["Industry1", "Industry2"],
  "experience_level": "Senior (X years)",
  "special_instructions": "Any specific requirements, company types, must-haves",
  "recency_days": 7,
  "exclude_keywords": ["Entry Level", "Intern"]
}

Rules:
- target_titles: include all mentioned + obvious variations (VP Events → also Director of Events, Head of Events)
- min_salary: use lower bound if range given, format as "$X00,000"
- industry_focus: use standard categories: Tech, Healthcare, Finance, Associations, Hospitality, Nonprofit, Media, Education, Government, Events, Corporate, Consulting, Legal, Fintech, Real Estate
- exclude_keywords: always include Entry Level and Intern, add others implied
- special_instructions: capture nuance — company size, must-haves, deal-breakers, preferences`;

  const response = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
    },
    body: JSON.stringify({
      model: 'claude-haiku-4-5',
      max_tokens: 800,
      messages: [{ role: 'user', content: prompt }],
    }),
  });

  const data = await response.json();
  const text = data.content?.[0]?.text || '{}';
  const clean = text.replace(/```json|```/g, '').trim();
  const start = clean.indexOf('{');
  const end = clean.lastIndexOf('}') + 1;
  return JSON.parse(clean.slice(start, end));
}

/**
 * Commit a single file to GitHub via the Contents API.
 * If the file already exists, fetches its SHA and updates it.
 */
async function commitFile(token, repo, path, content, message, isAlreadyBase64 = false) {
  const base = `https://api.github.com/repos/${repo}/contents/${path}`;
  const headers = {
    Authorization: `token ${token}`,
    Accept: 'application/vnd.github+json',
    'Content-Type': 'application/json',
  };

  // Check if file exists (need SHA to update)
  let sha;
  try {
    const existing = await fetch(base, { headers });
    if (existing.ok) {
      const data = await existing.json();
      sha = data.sha;
    }
  } catch (_) {}

  const encoded = isAlreadyBase64 ? content : Buffer.from(content).toString('base64');

  const body = { message, content: encoded };
  if (sha) body.sha = sha;

  const res = await fetch(base, {
    method: 'PUT',
    headers,
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const err = await res.json();
    throw new Error(`GitHub API error for ${path}: ${JSON.stringify(err)}`);
  }
}
