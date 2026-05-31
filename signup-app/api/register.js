/**
 * POST /api/register
 *
 * Receives a user profile, commits it to the private job-agent-users repo.
 *
 * Vercel env vars required:
 *   GITHUB_TOKEN       — PAT with write access to the private data repo
 *   GITHUB_DATA_REPO   — "owner/job-agent-users"
 *   ANTHROPIC_API_KEY  — for parsing natural language criteria server-side
 */

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const GITHUB_TOKEN     = process.env.GITHUB_TOKEN;
  const GITHUB_DATA_REPO = process.env.GITHUB_DATA_REPO;
  const ANTHROPIC_KEY    = process.env.ANTHROPIC_API_KEY;

  // Surface config errors clearly
  if (!GITHUB_TOKEN)     return res.status(500).json({ error: 'GITHUB_TOKEN not set in Vercel environment variables.' });
  if (!GITHUB_DATA_REPO) return res.status(500).json({ error: 'GITHUB_DATA_REPO not set in Vercel environment variables.' });

  try {
    const {
      name, email, schedule,
      naturalLanguageRequest,
      resumeBase64, resumeFilename,
      coverLetters,        // array of { b: base64, f: filename }
      existingSlug,
    } = req.body || {};

    if (!name)  return res.status(400).json({ error: 'Name is required.' });
    if (!email) return res.status(400).json({ error: 'Email is required.' });

    // Parse criteria — use whatever we have (chat text, or empty fallback)
    const criteria = await parseCriteria(naturalLanguageRequest || '', name, ANTHROPIC_KEY);

    const slug = existingSlug || name.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '');

    const clArray = Array.isArray(coverLetters) ? coverLetters : [];
    const profile = {
      name,
      email,
      schedule: schedule || 'weekly',
      resume_file:         resumeFilename || null,
      cover_letter_files:  clArray.map(f => f.f),  // array of filenames
      criteria,
      registered_at: new Date().toISOString(),
    };

    // Commit profile.json first (always)
    await commitFile(
      GITHUB_TOKEN, GITHUB_DATA_REPO,
      `users/${slug}/profile.json`,
      JSON.stringify(profile, null, 2),
      `Add/update profile for ${name}`
    );

    // Commit resume if uploaded — strip data URL prefix if present
    if (resumeBase64 && resumeFilename) {
      const cleanB64 = stripDataUrlPrefix(resumeBase64);
      await commitFile(
        GITHUB_TOKEN, GITHUB_DATA_REPO,
        `users/${slug}/${resumeFilename}`,
        cleanB64,
        `Upload resume for ${name}`,
        true
      );
    }

    // Commit all cover letters
    for (const cl of clArray) {
      if (!cl.b || !cl.f) continue;
      const cleanB64 = stripDataUrlPrefix(cl.b);
      await commitFile(
        GITHUB_TOKEN, GITHUB_DATA_REPO,
        `users/${slug}/${cl.f}`,
        cleanB64,
        `Upload cover letter for ${name}: ${cl.f}`,
        true
      );
    }

    return res.status(200).json({ success: true, slug, criteria });

  } catch (err) {
    // Return the ACTUAL error so it's visible in the UI during testing
    console.error('Register error:', err);
    return res.status(500).json({
      error: err.message || 'Unknown error',
    });
  }
}

// Strip "data:application/pdf;base64," prefix if the browser included it
function stripDataUrlPrefix(b64) {
  const comma = b64.indexOf(',');
  return comma !== -1 ? b64.slice(comma + 1) : b64;
}

async function parseCriteria(naturalLanguage, name, apiKey) {
  // If no API key or no text, return a safe empty criteria object
  if (!apiKey || !naturalLanguage.trim()) {
    return {
      target_titles: [],
      min_salary: 'Not specified',
      location_preference: 'Remote',
      industry_focus: [],
      experience_level: 'Senior',
      special_instructions: naturalLanguage || '',
      recency_days: 7,
      exclude_keywords: ['Entry Level', 'Intern', 'Assistant'],
    };
  }

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
      messages: [{
        role: 'user',
        content: `Extract structured job search criteria from this description. Return ONLY valid JSON.

User: ${name}
Description: ${naturalLanguage}

Return exactly this structure, no markdown, no explanation:
{"target_titles":["title1"],"min_salary":"$X00,000","location_preference":"Remote/Hybrid/City","industry_focus":["Industry"],"experience_level":"Senior (X years)","special_instructions":"any nuance","recency_days":7,"exclude_keywords":["Entry Level","Intern"]}`,
      }],
    }),
  });

  const data = await response.json();
  if (!response.ok) throw new Error(`Anthropic error: ${data.error?.message || JSON.stringify(data)}`);

  const text = data.content?.[0]?.text || '{}';
  const clean = text.replace(/```json|```/g, '').trim();
  const start = clean.indexOf('{');
  const end   = clean.lastIndexOf('}') + 1;
  if (start === -1) throw new Error('Claude did not return valid JSON for criteria');
  return JSON.parse(clean.slice(start, end));
}

async function commitFile(token, repo, path, content, message, isAlreadyBase64 = false) {
  const url = `https://api.github.com/repos/${repo}/contents/${path}`;
  const headers = {
    Authorization: `token ${token}`,
    Accept: 'application/vnd.github+json',
    'Content-Type': 'application/json',
  };

  // Get existing SHA if file already exists (required for updates)
  let sha;
  const existing = await fetch(url, { headers });
  if (existing.ok) {
    sha = (await existing.json()).sha;
  } else if (existing.status !== 404) {
    // 404 = file doesn't exist yet (fine). Anything else = real problem.
    const errBody = await existing.json().catch(() => ({}));
    throw new Error(`GitHub read failed for ${path}: ${existing.status} ${JSON.stringify(errBody)}`);
  }

  const encoded = isAlreadyBase64 ? content : Buffer.from(content).toString('base64');
  const body = { message, content: encoded };
  if (sha) body.sha = sha;

  const put = await fetch(url, { method: 'PUT', headers, body: JSON.stringify(body) });
  if (!put.ok) {
    const errBody = await put.json().catch(() => ({}));
    throw new Error(`GitHub write failed for ${path}: ${put.status} ${JSON.stringify(errBody)}`);
  }
}
