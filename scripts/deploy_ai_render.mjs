#!/usr/bin/env node
// Node-only deploy script for Render (no jq needed)
// Requires: Node 18+, env vars RENDER_API_KEY and GEMINI_API_KEY

import { execSync } from 'node:child_process';

const API = 'https://api.render.com/v1';
const SERVICE_NAME = process.env.SERVICE_NAME || 'ai-waifu';
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
};

async function main() {
  console.log(`Deploying service '${SERVICE_NAME}' from ${REPO_URL} (branch ${BRANCH})`);
  const svcId = await findServiceByName(SERVICE_NAME);
  if (svcId) {
    console.log(`Service exists (id=${svcId}). Updating env and triggering deploy...`);
    await putEnvVars(svcId, [{ key: 'GEMINI_API_KEY', value: GEMINI_API_KEY }]);
    await triggerDeploy(svcId);
    console.log('Deploy triggered. Visit Render dashboard for status.');
    return;
  }
  console.log('Creating new service...');
  const created = await createService({ name: SERVICE_NAME, repo: REPO_URL, branch: BRANCH });
  console.log(`Created service id=${created.id}`);
  if (created.serviceDetails?.url) {
    console.log(`Once live: ${created.serviceDetails.url}`);
  }
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

async function createService({ name, repo, branch }) {
  const body = {
    type: 'web',
    name,
    env: 'node',
    repo,
    branch,
    buildCommand: 'echo no build',
    startCommand: 'node server_ai.js',
    healthCheckPath: '/health',
    autoDeploy: true,
    envVars: [
      { key: 'NODE_VERSION', value: '18' },
      { key: 'GEMINI_API_KEY', value: GEMINI_API_KEY },
    ],
  };
  const res = await fetch(`${API}/services`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => '');
    throw new Error(`Create service failed: ${res.status} ${txt}`);
  }
  return await res.json();
}

main().catch((e) => {
  console.error(e?.stack || String(e));
  process.exit(1);
});

