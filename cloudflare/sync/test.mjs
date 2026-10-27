// node --test cloudflare/sync/test.mjs   (Node 22+: uses the built-in node:sqlite as a stand-in for D1)
import test from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { readFileSync } from "node:fs";
import worker from "./src/index.js";

function d1() {
  const db = new DatabaseSync(":memory:");
  db.exec(readFileSync(new URL("./schema.sql", import.meta.url), "utf8"));
  return {
    prepare(sql) {
      let args = [];
      const statement = {
        bind(...values) { args = values; return statement; },
        async first() { return db.prepare(sql).get(...args) ?? null; },
        async run() { db.prepare(sql).run(...args); return {}; },
      };
      return statement;
    },
    raw: db,
  };
}

const ID = "a".repeat(32), SECRET = "b".repeat(64), OTHER = "c".repeat(64);
const call = (env, method, secret = SECRET, body, id = ID) =>
  worker.fetch(new Request(`https://x.test/v1/${id}`, {
    method, headers: { authorization: `Bearer ${secret}`, "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  }), env);

test("first copy, read it back, wrong secret refused", async () => {
  const env = { DB: d1() };
  assert.equal((await call(env, "GET")).status, 404);
  const put = await call(env, "PUT", SECRET, { blob: "abc_DEF-123", base: 0 });
  assert.equal(put.status, 200);
  const got = await (await call(env, "GET")).json();
  assert.equal(got.blob, "abc_DEF-123");
  assert.equal((await call(env, "GET", OTHER)).status, 401);
  assert.equal((await call(env, "PUT", OTHER, { blob: "x", base: -1 })).status, 401);
  assert.equal((await call(env, "DELETE", OTHER)).status, 401);
});

test("a stale base is a conflict, -1 overwrites, writes are spaced", async () => {
  const env = { DB: d1() };
  const first = await (await call(env, "PUT", SECRET, { blob: "one", base: 0 })).json();
  assert.equal((await call(env, "PUT", SECRET, { blob: "two", base: first.updated })).status, 429);
  env.DB.raw.exec("UPDATE syncs SET updated = updated - 10000");
  const stale = await call(env, "PUT", SECRET, { blob: "two", base: first.updated });
  assert.equal(stale.status, 409);
  const fresh = (await stale.json()).updated;
  assert.equal((await call(env, "PUT", SECRET, { blob: "two", base: fresh })).status, 200);
  env.DB.raw.exec("UPDATE syncs SET updated = updated - 10000");
  assert.equal((await call(env, "PUT", SECRET, { blob: "three", base: -1 })).status, 200);
});

test("bad ids, bad blobs and big blobs", async () => {
  const env = { DB: d1() };
  assert.equal((await call(env, "GET", SECRET, undefined, "zz")).status, 404);
  assert.equal((await call(env, "GET", "short")).status, 401);
  assert.equal((await call(env, "PUT", SECRET, { blob: "has spaces", base: 0 })).status, 400);
  assert.equal((await call(env, "PUT", SECRET, { blob: "a".repeat(512 * 1024 + 1), base: 0 })).status, 413);
  assert.equal((await call(env, "PUT", SECRET, { blob: "a".repeat(512 * 1024), base: 0 })).status, 200);
});

test("delete, and the nightly cleanup of year-old copies", async () => {
  const env = { DB: d1() };
  await call(env, "PUT", SECRET, { blob: "one", base: 0 });
  assert.equal((await call(env, "DELETE")).status, 200);
  assert.equal((await call(env, "GET")).status, 404);
  await call(env, "PUT", SECRET, { blob: "one", base: 0 });
  env.DB.raw.exec("UPDATE syncs SET updated = 1000");
  await worker.scheduled({}, env);
  assert.equal(env.DB.raw.prepare("SELECT COUNT(*) AS n FROM syncs").get().n, 0);
});

test("it stops taking saves long before D1's free daily limit", async () => {
  const env = { DB: d1() };
  assert.equal((await call(env, "PUT", SECRET, { blob: "one", base: 0 })).status, 200);
  const day = new Date().toISOString().slice(0, 10);
  assert.equal(env.DB.raw.prepare("SELECT writes FROM usage WHERE day = ?").get(day).writes, 1);
  env.DB.raw.exec(`UPDATE usage SET writes = 18000`);
  env.DB.raw.exec("UPDATE syncs SET updated = updated - 10000");
  assert.equal((await call(env, "PUT", SECRET, { blob: "two", base: -1 })).status, 503);
  assert.equal((await call(env, "DELETE")).status, 503);
  assert.equal((await call(env, "GET")).status, 200);                  // reading is still fine
  env.DB.raw.exec(`UPDATE usage SET day = '2000-01-01|' || day`);              // a new day: the budget is back
  assert.equal((await call(env, "PUT", SECRET, { blob: "two", base: -1 })).status, 200);
  await worker.scheduled({}, env);
  assert.equal(env.DB.raw.prepare("SELECT COUNT(*) AS n FROM usage WHERE day LIKE '2000-01-01%'").get().n, 0);
});

test("one network address cannot spend the day for everybody", async () => {
  const env = { DB: d1() };
  const from = (ip) => (method, id, body) => worker.fetch(new Request(`https://x.test/v1/${id}`, {
    method, headers: { authorization: `Bearer ${SECRET}`, "cf-connecting-ip": ip }, body: JSON.stringify(body),
  }), env);
  const a = from("203.0.113.7"), b = from("198.51.100.9");
  const code = (n) => n.toString(16).padStart(32, "0");
  for (let n = 1; n <= 10; n++) assert.equal((await a("PUT", code(n), { blob: "x", base: 0 })).status, 200);
  assert.equal((await a("PUT", code(11), { blob: "x", base: 0 })).status, 429);          // the 11th new code today from that address
  assert.equal((await b("PUT", code(11), { blob: "x", base: 0 })).status, 200);          // somebody else is not affected
  env.DB.raw.exec("UPDATE usage SET writes = 1000 WHERE day LIKE '%|%' AND day NOT LIKE '%|new'");
  env.DB.raw.exec("UPDATE syncs SET updated = updated - 10000");
  assert.equal((await a("PUT", code(1), { blob: "y", base: -1 })).status, 429);          // too many saves today from that address
  const stored = env.DB.raw.prepare("SELECT group_concat(day) AS d FROM usage").get().d;
  assert.ok(!stored.includes("203.0.113.7"));                                           // addresses are never kept
});
