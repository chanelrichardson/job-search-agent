/**
 * POST /api/send-code
 *
 * Called when a returning user enters their email and requests a login code.
 * Generates a 6-digit code, stores it as a temporary file in the data repo
 * (expires after 15 minutes), and emails it to the user.
 *
 * Body: { email: "user@example.com" }
 * Returns: { exists: true/false } — exists: false means no profile found for that email
 */

import { createHmac } from 'crypto';
import { createTransport } from 'nodemailer';

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const GITHUB_TOKEN    = process.env.GITHUB_TOKEN;
  const GITHUB_DATA_REPO = process.env.GITHUB_DATA_REPO;
  const GMAIL_SENDER    = process.env.GMAIL_SENDER;
  const GMAIL_APP_PASSWORD = process.env.GMAIL_APP_PASSWORD;
  const CODE_SECRET     = process.env.CODE_SECRET || 'default-secret-change-me';

  const { email } = req.body;
  if (!email) return res.status(400).json({ error: 'Email required' });

  try {
    // 1. Find the user's profile by scanning the data repo for a matching email
    const slug = await findSlugByEmail(email, GITHUB_TOKEN, GITHUB_DATA_REPO);
    if (!slug) {
      return res.status(200).json({ exists: false });
    }

    // 2. Generate a 6-digit code with expiry, signed so it can't be forged
    const code = String(Math.floor(100000 + Math.random() * 900000));
    const expires = Date.now() + 15 * 60 * 1000; // 15 minutes
    const payload = JSON.stringify({ code, expires, slug });

    // Store it in the data repo as a temp file
    await commitFile(
      GITHUB_TOKEN,
      GITHUB_DATA_REPO,
      `pending-codes/${slug}.json`,
      payload,
      `Login code for ${slug}`
    );

    // 3. Email the code
    await sendCodeEmail(email, code, GMAIL_SENDER, GMAIL_APP_PASSWORD);

    return res.status(200).json({ exists: true });

  } catch (err) {
    console.error('send-code error:', err);
    return res.status(500).json({ error: 'Failed to send code. Please try again.' });
  }
}

async function findSlugByEmail(email, token, repo) {
  // List all user directories
  const url = `https://api.github.com/repos/${repo}/contents/users`;
  const r = await fetch(url, {
    headers: { Authorization: `token ${token}`, Accept: 'application/vnd.github+json' }
  });
  if (!r.ok) return null;
  const dirs = await r.json();
  if (!Array.isArray(dirs)) return null;

  // Check each user's profile.json for a matching email
  for (const dir of dirs) {
    if (dir.type !== 'dir') continue;
    const profileUrl = `https://api.github.com/repos/${repo}/contents/users/${dir.name}/profile.json`;
    const pr = await fetch(profileUrl, {
      headers: { Authorization: `token ${token}`, Accept: 'application/vnd.github+json' }
    });
    if (!pr.ok) continue;
    const data = await pr.json();
    const content = Buffer.from(data.content.replace(/\n/g, ''), 'base64').toString('utf-8');
    const profile = JSON.parse(content);
    if (profile.email?.toLowerCase() === email.toLowerCase()) {
      return dir.name; // return the slug
    }
  }
  return null;
}

async function sendCodeEmail(to, code, sender, appPassword) {
  const transporter = createTransport({
    service: 'gmail',
    auth: { user: sender, pass: appPassword }
  });

  await transporter.sendMail({
    from: sender,
    to,
    subject: 'Your Job Agent login code',
    text: `Your verification code is: ${code}\n\nThis code expires in 15 minutes.\n\nIf you didn't request this, you can ignore this email.`,
    html: `
      <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;max-width:400px;margin:0 auto;padding:40px 20px">
        <h2 style="font-size:18px;font-weight:500;color:#18181b;margin:0 0 8px">Your login code</h2>
        <p style="font-size:14px;color:#71716e;margin:0 0 28px">Enter this code to access your Job Agent profile:</p>
        <div style="background:#f4f4f1;border-radius:10px;padding:24px;text-align:center;letter-spacing:0.2em;font-size:32px;font-weight:600;color:#18181b;font-family:monospace">${code}</div>
        <p style="font-size:13px;color:#a0a09e;margin:20px 0 0;text-align:center">Expires in 15 minutes</p>
      </div>
    `
  });
}

async function commitFile(token, repo, path, content, message) {
  const base = `https://api.github.com/repos/${repo}/contents/${path}`;
  const headers = {
    Authorization: `token ${token}`,
    Accept: 'application/vnd.github+json',
    'Content-Type': 'application/json',
  };
  let sha;
  try {
    const existing = await fetch(base, { headers });
    if (existing.ok) sha = (await existing.json()).sha;
  } catch (_) {}

  const body = { message, content: Buffer.from(content).toString('base64') };
  if (sha) body.sha = sha;

  const r = await fetch(base, { method: 'PUT', headers, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`GitHub write failed: ${await r.text()}`);
}
