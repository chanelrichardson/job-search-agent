/**
 * POST /api/verify-code
 *
 * Verifies the 6-digit code and returns the user's existing profile data
 * so the signup form can pre-fill it for editing.
 *
 * Body: { email: "user@example.com", code: "123456" }
 * Returns: { valid: true, profile: { name, email, schedule, criteria, ... }, slug }
 *       or { valid: false, error: "..." }
 */

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const GITHUB_TOKEN     = process.env.GITHUB_TOKEN;
  const GITHUB_DATA_REPO = process.env.GITHUB_DATA_REPO;

  const { email, code } = req.body;
  if (!email || !code) return res.status(400).json({ error: 'Email and code required' });

  try {
    // 1. Find slug by email (same scan as send-code)
    const slug = await findSlugByEmail(email, GITHUB_TOKEN, GITHUB_DATA_REPO);
    if (!slug) return res.status(200).json({ valid: false, error: 'Email not found.' });

    // 2. Fetch and validate the stored code
    const storedRaw = await getFile(GITHUB_TOKEN, GITHUB_DATA_REPO, `pending-codes/${slug}.json`);
    if (!storedRaw) return res.status(200).json({ valid: false, error: 'No code was sent. Request a new one.' });

    const { code: storedCode, expires } = JSON.parse(storedRaw);

    if (Date.now() > expires) {
      await deleteFile(GITHUB_TOKEN, GITHUB_DATA_REPO, `pending-codes/${slug}.json`);
      return res.status(200).json({ valid: false, error: 'Code expired. Request a new one.' });
    }

    if (code.trim() !== storedCode) {
      return res.status(200).json({ valid: false, error: 'Incorrect code. Try again.' });
    }

    // 3. Code is valid — delete it (one-time use) and return the profile
    await deleteFile(GITHUB_TOKEN, GITHUB_DATA_REPO, `pending-codes/${slug}.json`);
    const profileRaw = await getFile(GITHUB_TOKEN, GITHUB_DATA_REPO, `users/${slug}/profile.json`);
    const profile = JSON.parse(profileRaw);

    return res.status(200).json({ valid: true, profile, slug });

  } catch (err) {
    console.error('verify-code error:', err);
    return res.status(500).json({ error: 'Verification failed. Please try again.' });
  }
}

async function getFile(token, repo, path) {
  const r = await fetch(`https://api.github.com/repos/${repo}/contents/${path}`, {
    headers: { Authorization: `token ${token}`, Accept: 'application/vnd.github+json' }
  });
  if (!r.ok) return null;
  const data = await r.json();
  return Buffer.from(data.content.replace(/\n/g, ''), 'base64').toString('utf-8');
}

async function deleteFile(token, repo, path) {
  const base = `https://api.github.com/repos/${repo}/contents/${path}`;
  const headers = { Authorization: `token ${token}`, Accept: 'application/vnd.github+json', 'Content-Type': 'application/json' };
  const r = await fetch(base, { headers });
  if (!r.ok) return;
  const { sha } = await r.json();
  await fetch(base, {
    method: 'DELETE',
    headers,
    body: JSON.stringify({ message: `Delete used code for ${path}`, sha })
  });
}

async function findSlugByEmail(email, token, repo) {
  const r = await fetch(`https://api.github.com/repos/${repo}/contents/users`, {
    headers: { Authorization: `token ${token}`, Accept: 'application/vnd.github+json' }
  });
  if (!r.ok) return null;
  const dirs = await r.json();
  if (!Array.isArray(dirs)) return null;

  for (const dir of dirs) {
    if (dir.type !== 'dir') continue;
    const pr = await fetch(`https://api.github.com/repos/${repo}/contents/users/${dir.name}/profile.json`, {
      headers: { Authorization: `token ${token}`, Accept: 'application/vnd.github+json' }
    });
    if (!pr.ok) continue;
    const data = await pr.json();
    const content = Buffer.from(data.content.replace(/\n/g, ''), 'base64').toString('utf-8');
    const profile = JSON.parse(content);
    if (profile.email?.toLowerCase() === email.toLowerCase()) return dir.name;
  }
  return null;
}
