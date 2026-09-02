/**
 * Tests for the onboarding helpers. No network, no deps: node --test.
 *   node --test test/
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import crypto from "node:crypto";
import {
  canon, matchBuilder, ownershipProof, verifyStripeSignature, updateJsonFile,
  licenceMatchesCompany, safeUrl,
} from "../lib/onboarding.mjs";

const SECRET = "whsec_testsecret";
function signed(body, { secret = SECRET, ts = Math.floor(Date.now() / 1000), scheme = "v1" } = {}) {
  const sig = crypto.createHmac("sha256", secret)
    .update(`${ts}.${body}`).digest("hex");
  return `t=${ts},${scheme}=${sig}`;
}

test("canon strips entity suffixes and punctuation", () => {
  assert.equal(canon("Waltier Homes LLC"), "WALTIER HOMES");
  assert.equal(canon("Bellshire Homes, Inc."), "BELLSHIRE HOMES");
  assert.equal(canon("MyKabin LLC"), "MYKABIN");
  assert.equal(canon("A & B Builders Co."), "A & B BUILDERS");
  // repeated suffixes, as in real registry data
  assert.equal(canon("Foo Builders LLC INC"), "FOO BUILDERS");
});

test("matchBuilder reports ambiguity instead of guessing", () => {
  const builders = [
    { slug: "a", name: "Modern Homes LLC" },
    { slug: "b", name: "Modern Homes Inc" },
    { slug: "c", name: "Waltier Homes LLC" },
  ];
  assert.equal(matchBuilder(builders, "Waltier Homes").builder.slug, "c");
  assert.equal(matchBuilder(builders, "Modern Homes").ambiguous.length, 2);
  assert.equal(matchBuilder(builders, "Nobody At All").none, true);
  assert.equal(matchBuilder(builders, "").none, true);
});

test("ownershipProof accepts matching domain, rejects free mail", () => {
  assert.equal(ownershipProof({
    email: "zach@waltierhomesinc.com", website: "https://waltierhomesinc.com",
  }), "email-domain");
  assert.equal(ownershipProof({
    email: "zach@waltierhomesinc.com", website: "waltierhomesinc.com",
  }), "email-domain");
  // free mail never proves ownership even if the website is given
  assert.equal(ownershipProof({
    email: "someone@gmail.com", website: "https://waltierhomesinc.com",
  }), null);
  // different domain entirely
  assert.equal(ownershipProof({
    email: "me@attacker.com", website: "https://waltierhomesinc.com",
  }), null);
});

test("ownershipProof accepts a phone matching the L&I record", () => {
  assert.equal(ownershipProof({
    email: "someone@gmail.com", phone: "(206) 437-2273",
    lniRecord: { phonenumber: "2064372273" },
  }), "lni-phone");
  assert.equal(ownershipProof({
    email: "someone@gmail.com", phone: "12064372273",
    lniRecord: { phonenumber: "2064372273" },
  }), "lni-phone");
  assert.equal(ownershipProof({
    email: "someone@gmail.com", phone: "5551234567",
    lniRecord: { phonenumber: "2064372273" },
  }), null);
  assert.equal(ownershipProof({ email: "a@gmail.com" }), null);
});

test("verifyStripeSignature accepts a valid signature", () => {
  const body = JSON.stringify({ type: "checkout.session.completed", id: "evt_1" });
  const event = verifyStripeSignature(body, signed(body), SECRET);
  assert.equal(event.id, "evt_1");
});

test("verifyStripeSignature rejects tampering and forgery", () => {
  const body = JSON.stringify({ amount: 100 });
  const header = signed(body);
  const tampered = JSON.stringify({ amount: 999999 });
  assert.throws(() => verifyStripeSignature(tampered, header, SECRET), /mismatch/);
  assert.throws(() => verifyStripeSignature(body, header, "whsec_wrong"), /mismatch/);
  assert.throws(() => verifyStripeSignature(body, null, SECRET), /missing/);
  assert.throws(() => verifyStripeSignature(body, header, ""), /missing/);
});

test("verifyStripeSignature rejects replays but tolerates clock skew", () => {
  const body = JSON.stringify({ id: "evt_old" });
  const stale = Math.floor(Date.now() / 1000) - 3600;
  assert.throws(() => verifyStripeSignature(body, signed(body, { ts: stale }), SECRET),
    /too old/);
  const future = Math.floor(Date.now() / 1000) + 120;
  assert.doesNotThrow(() => verifyStripeSignature(body, signed(body, { ts: future }), SECRET));
});

test("verifyStripeSignature ignores v0 and malformed hex without throwing on parse", () => {
  const body = JSON.stringify({ id: "evt_x" });
  // v0-only header must not authenticate (downgrade attempt)
  assert.throws(() => verifyStripeSignature(body, signed(body, { scheme: "v0" }), SECRET),
    /no v1 signature/);
  // malformed hex candidate alongside a valid one must still verify
  const ts = Math.floor(Date.now() / 1000);
  const good = crypto.createHmac("sha256", SECRET).update(`${ts}.${body}`).digest("hex");
  const header = `t=${ts},v1=zzzz,v1=${good}`;
  assert.doesNotThrow(() => verifyStripeSignature(body, header, SECRET));
  // malformed only → mismatch, not a crash
  assert.throws(() => verifyStripeSignature(body, `t=${ts},v1=nothex`, SECRET), /mismatch/);
});

test("verifyStripeSignature handles multi-byte UTF-8 bodies", () => {
  const body = JSON.stringify({ name: "Café — Ünïcode ✅" });
  assert.doesNotThrow(() => verifyStripeSignature(body, signed(body), SECRET));
});

test("updateJsonFile retries a raced sha then succeeds", async () => {
  const state = { builders: [] };
  let puts = 0;
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url, init = {}) => {
    if ((init.method || "GET") === "GET") {
      return new Response(JSON.stringify({
        sha: `sha${puts}`,
        content: Buffer.from(JSON.stringify(state)).toString("base64"),
      }), { status: 200 });
    }
    puts++;
    if (puts === 1) return new Response("conflict", { status: 409 });
    return new Response(JSON.stringify({ commit: { sha: "abc1234" } }), { status: 200 });
  };
  try {
    const res = await updateJsonFile({
      path: "data/featured.json", token: "t", message: "m",
      mutate: (d) => { d.builders.push({ slug: "x" }); return d; },
    });
    assert.equal(res.committed, true);
    assert.equal(puts, 2, "should have retried exactly once");
  } finally {
    globalThis.fetch = realFetch;
  }
});

test("updateJsonFile skips the write when mutate returns null", async () => {
  const realFetch = globalThis.fetch;
  let puts = 0;
  globalThis.fetch = async (url, init = {}) => {
    if ((init.method || "GET") === "GET") {
      return new Response(JSON.stringify({
        sha: "s", content: Buffer.from(JSON.stringify({ builders: [] })).toString("base64"),
      }), { status: 200 });
    }
    puts++;
    return new Response("{}", { status: 200 });
  };
  try {
    const res = await updateJsonFile({
      path: "p", token: "t", message: "m", mutate: () => null,
    });
    assert.equal(res.skipped, true);
    assert.equal(puts, 0, "must not PUT when skipping");
  } finally {
    globalThis.fetch = realFetch;
  }
});

test("licenceMatchesCompany blocks pairing a valid licence with another company", () => {
  const rec = { businessname: "WALTIER HOMES LLC", contractorlicensenumber: "WALTIHL824RS" };
  const victim = { name: "Mykabin LLC", slug: "mykabin", license: { number: "MYKABL*819BU" } };
  // the attack: real active licence + a competitor's name
  const bad = licenceMatchesCompany(rec, "Mykabin LLC", victim);
  assert.equal(bad.ok, false);
  assert.match(bad.reason, /belongs to/);
  // honest case
  const self = { name: "Waltier Homes LLC", slug: "waltier-homes-llc" };
  assert.equal(licenceMatchesCompany(rec, "Waltier Homes LLC", self).ok, true);
});

test("licenceMatchesCompany rejects a licence that disagrees with our own record", () => {
  const rec = { businessname: "WALTIER HOMES LLC", contractorlicensenumber: "OTHER123XX" };
  const b = { name: "Waltier Homes LLC", license: { number: "WALTIHL824RS" } };
  const r = licenceMatchesCompany(rec, "Waltier Homes LLC", b);
  assert.equal(r.ok, false);
  assert.match(r.reason, /!= licence/);
});

test("safeUrl strips dangerous schemes and keeps http(s)", () => {
  assert.equal(safeUrl("javascript:alert(1)"), "");
  assert.equal(safeUrl("data:text/html,<script>alert(1)</script>"), "");
  assert.equal(safeUrl("  "), "");
  assert.equal(safeUrl("waltierhomesinc.com"), "https://waltierhomesinc.com/");
  assert.equal(safeUrl("https://waltierhomesinc.com/x"), "https://waltierhomesinc.com/x");
});

test("cancellation removes only the matching subscription's card", async () => {
  const state = { builders: [
    { slug: "a", city: "Seattle", _subscription: "sub_keep" },
    { slug: "b", city: "Bellevue", _subscription: "sub_gone" },
  ] };
  const realFetch = globalThis.fetch;
  let written = null;
  globalThis.fetch = async (url, init = {}) => {
    if ((init.method || "GET") === "GET") {
      return new Response(JSON.stringify({
        sha: "s", content: Buffer.from(JSON.stringify(state)).toString("base64"),
      }), { status: 200 });
    }
    written = JSON.parse(Buffer.from(JSON.parse(init.body).content, "base64").toString());
    return new Response(JSON.stringify({ commit: { sha: "x" } }), { status: 200 });
  };
  try {
    await updateJsonFile({
      path: "data/featured.json", token: "t", message: "m",
      mutate: (d) => {
        const i = d.builders.findIndex(f => f._subscription === "sub_gone");
        if (i === -1) return null;
        d.builders.splice(i, 1);
        return d;
      },
    });
    assert.deepEqual(written.builders.map(f => f.slug), ["a"], "only the cancelled card goes");
  } finally { globalThis.fetch = realFetch; }
});

test("cancellation for an unknown subscription writes nothing", async () => {
  const realFetch = globalThis.fetch;
  let puts = 0;
  globalThis.fetch = async (url, init = {}) => {
    if ((init.method || "GET") === "GET") {
      return new Response(JSON.stringify({
        sha: "s",
        content: Buffer.from(JSON.stringify({ builders: [{ slug: "a", _subscription: "sub_x" }] })).toString("base64"),
      }), { status: 200 });
    }
    puts++; return new Response("{}", { status: 200 });
  };
  try {
    const r = await updateJsonFile({
      path: "p", token: "t", message: "m",
      mutate: (d) => {
        const i = d.builders.findIndex(f => f._subscription === "sub_unknown");
        if (i === -1) return null;
        d.builders.splice(i, 1); return d;
      },
    });
    assert.equal(r.skipped, true);
    assert.equal(puts, 0);
  } finally { globalThis.fetch = realFetch; }
});
