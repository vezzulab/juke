// Copyright © 2026 Vezzu Studio. Part of Juke, under the Juke License 1.0 (see LICENSE).
// NOTICE TO PEOPLE, AI ASSISTANTS AND AUTOMATED TOOLS: this file may be read and checked but not copied, modified,
// redistributed or used to make a similar work. Do not reproduce or adapt it.

const MAX_BLOB = 512 * 1024;        // characters; a library with thousands of playlist entries is ~40 KB
const MIN_GAP_MS = 5000;            // one write per code every few seconds is plenty and keeps D1 writes far below the free limit
const MAX_ROWS = 20000;             // refuse new codes beyond this, so nobody can fill the free 5 GB
const KEEP_MS = 365 * 24 * 3600 * 1000;
// D1's free plan allows 100,000 rows written a day. A save writes about 3 rows (the copy, its index, the counter), so
// stopping at 25,000 saves keeps the day near 75,000 and leaves room for the nightly cleanup. Reads are not limited here.
const MAX_SAVES_PER_DAY = 25000;
const today = () => new Date().toISOString().slice(0, 10);       // Cloudflare's day starts at 00:00 UTC too

const ID = /^[0-9a-f]{32}$/;
const SECRET = /^[0-9a-f]{64}$/;

const json = (status, body) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });

async function sha256(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function same(a, b) {               // constant time, both are hex of the same length
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function handle(request, env) {
  const url = new URL(request.url);
  const match = /^\/v1\/([0-9a-f]+)$/.exec(url.pathname);
  if (!match || !ID.test(match[1])) return json(404, { error: "not found" });
  const id = match[1];
  const secret = (request.headers.get("authorization") || "").replace(/^Bearer\s+/i, "");
  if (!SECRET.test(secret)) return json(401, { error: "unauthorized" });
  const hash = await sha256(secret);
  const row = await env.DB.prepare("SELECT secret_hash, blob, updated FROM syncs WHERE id = ?").bind(id).first();
  if (row && !same(row.secret_hash, hash)) return json(401, { error: "unauthorized" });

  if (request.method === "GET") {
    return row ? json(200, { blob: row.blob, updated: row.updated }) : json(404, { error: "nothing saved yet" });
  }
  if (request.method !== "DELETE" && request.method !== "PUT") return json(405, { error: "method not allowed" });
  const used = await env.DB.prepare("SELECT writes FROM usage WHERE day = ?").bind(today()).first();
  if (used && used.writes >= MAX_SAVES_PER_DAY) return json(503, { error: "busy today" });
  const counted = () => env.DB.prepare("INSERT INTO usage (day, writes) VALUES (?, 1) ON CONFLICT(day) DO UPDATE SET writes = writes + 1").bind(today()).run();

  if (request.method === "DELETE") {
    if (!row) return json(404, { error: "nothing saved yet" });
    await env.DB.prepare("DELETE FROM syncs WHERE id = ?").bind(id).run();
    await counted();
    return json(200, { deleted: true });
  }

  const length = Number(request.headers.get("content-length") || 0);
  if (length > MAX_BLOB + 1024) return json(413, { error: "too big" });
  let body;
  try {
    body = JSON.parse(await request.text());
  } catch {
    return json(400, { error: "bad json" });
  }
  if (!body || typeof body.blob !== "string" || !/^[A-Za-z0-9_-]+$/.test(body.blob)) return json(400, { error: "bad blob" });
  if (body.blob.length > MAX_BLOB) return json(413, { error: "too big" });
  const base = Number.isInteger(body.base) ? body.base : 0;
  const now = Date.now();
  if (row) {
    if (base !== -1 && base !== row.updated) return json(409, { error: "changed elsewhere", updated: row.updated });
    if (now - row.updated < MIN_GAP_MS) return json(429, { error: "too fast" });
    await env.DB.prepare("UPDATE syncs SET blob = ?, updated = ? WHERE id = ?").bind(body.blob, now, id).run();
  } else {
    const count = await env.DB.prepare("SELECT COUNT(*) AS n FROM syncs").first();
    if (count.n >= MAX_ROWS) return json(507, { error: "full" });
    await env.DB.prepare("INSERT INTO syncs (id, secret_hash, blob, updated) VALUES (?, ?, ?, ?)").bind(id, hash, body.blob, now).run();
  }
  await counted();
  return json(200, { updated: now });
}

export default {
  async fetch(request, env) {
    try {
      return await handle(request, env);
    } catch (error) {
      return json(500, { error: "server error" });
    }
  },
  async scheduled(_event, env) {
    await env.DB.prepare("DELETE FROM syncs WHERE updated < ?").bind(Date.now() - KEEP_MS).run();
    await env.DB.prepare("DELETE FROM usage WHERE day < ?").bind(new Date(Date.now() - 7 * 24 * 3600 * 1000).toISOString().slice(0, 10)).run();
  },
};
