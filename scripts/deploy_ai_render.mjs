#!/usr/bin/env node
// Node-only deploy script for Render (no jq needed)
// Requires: Node 18+, env vars RENDER_API_KEY and GEMINI_API_KEY

import { execSync } from 'node:child_process';

const API = 'https://api.render.com/v1';
let SERVICE_NAME = process.env.SERVICE_NAME || 'tts-waifu';
const BRANCH = process.env.BRANCH || 'main';
const RENDER_API_KEY = process.env.RENDER_API_KEY || '';
const GEMINI_API_KEY = process.env.GEMINI_API_KEY || '';

if (!RENDER_API_KEY) {
  console.error('Set RENDER_API_KEY in your environment');
  process.exit(2);
}
if (!GEMINI_API_KEY) {
  console.error('Set GEMINI_API_KEY in your environment');
  process.exit(2);
}

let REPO_URL = process.env.REPO_URL || '';
if (!REPO_URL) {
  try {
    REPO_URL = execSync('git config --get remote.origin.url', { encoding: 'utf8' }).trim();
  } catch {}
}
if (!REPO_URL) {
  console.error('Could not determine REPO_URL. Set env REPO_URL to your repo git URL');
  process.exit(2);
}

const headers = {
  Authorization: `Bearer ${RENDER_API_KEY}`,
  'Content-Type': 'application/json',
  Accept: 'application/json',
};

async function main() {
  // Allow overriding service via CLI: --service <name>
  const idx = process.argv.indexOf('--service');
  if (idx !== -1 && process.argv[idx+1]) {
    SERVICE_NAME = process.argv[idx+1];
  }
  console.log(`Deploying service '${SERVICE_NAME}' from ${REPO_URL} (branch ${BRANCH})`);
  const svcId = await findServiceByName(SERVICE_NAME);
  if (svcId) {
    console.log(`Service exists (id=${svcId}). Updating env and triggering deploy...`);
    await putEnvVars(svcId, [{ key: 'GEMINI_API_KEY', value: GEMINI_API_KEY }]);
    await triggerDeploy(svcId);
    console.log('Deploy triggered. Visit Render dashboard for status.');
    return;
  }
  console.log('Service not found. Use blueprint deploy instead:');
  console.log('  ./scripts/deploy_via_blueprint.sh');
  process.exit(2);
}

function normalizeRepo(url) {
  if (!url) return url;
  // Convert SSH form git@github.com:user/repo.git to https://github.com/user/repo.git
  const sshMatch = url.match(/^git@([^:]+):(.+)$/);
  if (sshMatch) {
    const host = sshMatch[1];
    const path = sshMatch[2];
    return `https://${host}/${path}`;
  }
  return url;
}

async function findServiceByName(name) {
  const res = await fetch(`${API}/services?limit=100`, { headers });
  if (!res.ok) throw new Error(`List services failed: ${res.status}`);
  const arr = await res.json();
  const svc = (arr || []).find((s) => s?.name === name);
  return svc?.id || '';
}

async function putEnvVars(id, vars) {
  const res = await fetch(`${API}/services/${id}/env-vars`, {
    method: 'PUT',
    headers,
    body: JSON.stringify(vars),
  });
  if (!res.ok) throw new Error(`PUT env failed: ${res.status}`);
}

async function triggerDeploy(id) {
  const res = await fetch(`${API}/services/${id}/deploys`, {
    method: 'POST',
    headers,
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error(`Trigger deploy failed: ${res.status}`);
}

// createService removed to encourage using blueprint flow

main().catch((e) => {
  console.error(e?.stack || String(e));
  process.exit(1);
});
