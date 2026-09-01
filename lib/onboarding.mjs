/**
 * Shared helpers for the onboarding endpoints (api/stripe.mjs, api/claim.mjs).
 * Node builtins + fetch only — no dependencies, per the project constitution.
 *
 * Lives outside /api/ so Vercel never routes it as an endpoint.
 */
import crypto from "node:crypto";

export const OWNER = "xasdta";
export const REPO = "adu-builder-index";
export const BRANCH = "master";
export const FEATURED_SLOTS = 3;
const UA = "adu-builder-index/1.0";
const LNI = "https://data.wa.gov/resource/m8qx-ubtq.json";
const RAW = `https://raw.githubusercontent.com/${OWNER}/${REPO}/${BRANCH}`;
const GH = "https://api.github.com";

const FREE_MAIL = new Set([
  "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "aol.com",
  "icloud.com", "proton.me", "protonmail.com", "live.com", "msn.com",
  "comcast.net", "me.com", "mac.com",
]);

/** Mirror of canon() in pipeline/build_rankings.py — keep the two in lockstep. */
const SUFFIX = /,?\s+(LLC|L L C|INC|CORP|CORPORATION|CO|COMPANY|LTD|LP|PLLC|P\.?S\.?)\.?$/i;
export function canon(name) {
  let n = String(name || "").toUpperCase().replace(/[^A-Z0-9& ]/g, " ")
    .replace(/\s+/g, " ").trim();
  let prev = null;
  while (prev !== n) {
    prev = n;
    n = n.replace(SUFFIX, "").trim();
  }
  return n;
}

export function slugify(name) {
  return String(name || "").toLowerCase().replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "") || "builder";
}

async function soda(where) {
  const url = `${LNI}?${new URLSearchParams({ $where: where, $limit: "10" })}`;
  const r = await fetch(url, {
    headers: { "User-Agent": UA },
    signal: AbortSignal.timeout(8000),
  });
  if (!r.ok) throw new Error(`L&I ${r.status}`);
  return r.json();
}

/** Exact license-number lookup — the authoritative check. */
export async function lniByLicense(number) {
  const n = String(number || "").trim().toUpperCase().replace(/'/g, "''");
  if (!n) return { records: [], active: [] };
  const records = await soda(`upper(contractorlicensenumber)='${n}'`);
  return { records, active: records.filter(r => r.contractorlicensestatus === "ACTIVE") };
}

/** Name lookup — fallback when no license number was supplied. */
export async function lniByName(name) {
  const q = String(name || "").trim().toUpperCase().replace(/'/g, "''");
  if (!q) return { records: [], active: [] };
  const all = await soda(`upper(businessname) like '${q}%'`);
  const records = all.filter(r => canon(r.businessname) === canon(name));
  return { records, active: records.filter(r => r.contractorlicensestatus === "ACTIVE") };
}

export async function loadBuilders() {
  const r = await fetch(`${RAW}/data/builders.json`, {
    headers: { "User-Agent": UA }, signal: AbortSignal.timeout(15000),
  });
  if (!r.ok) throw new Error(`builders.json ${r.status}`);
  return (await r.json()).builders;
}

/** Canon-keyed match. Returns ambiguity rather than guessing. */
export function matchBuilder(builders, name) {
  const key = canon(name);
  if (!key) return { none: true };
  const hits = builders.filter(b => canon(b.name) === key);
  if (hits.length === 1) return { builder: hits[0] };
  if (hits.length > 1) return { ambiguous: hits };
  return { none: true };
}

/**
 * Bind a verified L&I record to the company being published.
 *
 * Without this, the two lookups are independent: "is SOME license active" AND
 * "does this name exist in our data". An attacker could pair any active
 * license number (the registry is public, and we print numbers on every
 * profile) with a competitor's company name and publish against their page.
 */
export function licenceMatchesCompany(lniRecord, submittedName, builder) {
  const reg = canon(lniRecord?.businessname);
  if (!reg) return { ok: false, reason: "L&I record has no business name" };
  if (reg !== canon(submittedName)) {
    return {
      ok: false,
      reason: `licence belongs to "${lniRecord.businessname}", not "${submittedName}"`,
    };
  }
  if (builder && reg !== canon(builder.name)) {
    return {
      ok: false,
      reason: `licence "${lniRecord.businessname}" does not match profile "${builder.name}"`,
    };
  }
  // When our own permit data already knows this builder's licence, it must agree.
  const known = builder?.license?.number;
  if (known && String(known).toUpperCase() !==
      String(lniRecord.contractorlicensenumber || "").toUpperCase()) {
    return {
      ok: false,
      reason: `submitted licence ${lniRecord.contractorlicensenumber} != licence ${known} on record for this profile`,
    };
  }
  return { ok: true };
}

/** Only http(s) links are ever published — blocks javascript:/data: payloads. */
export function safeUrl(raw) {
  const s = String(raw || "").trim();
  if (!s) return "";
  const withScheme = /^[a-z][a-z0-9+.-]*:/i.test(s) ? s : `https://${s}`;
  try {
    const u = new URL(withScheme);
    return (u.protocol === "http:" || u.protocol === "https:") ? u.toString() : "";
  } catch {
    return "";
  }
}

/**
 * Second factor for free claims: a valid license number proves nothing about
 * who typed it, since the registry is public.
 *
 * NOTE: neither branch is a possession proof — email-domain compares two
 * strings from the same request, and the L&I phone is a public field of the
 * same open dataset. Callers must treat a truthy result as "worth a look",
 * never as authorisation to publish. See api/claim.mjs.
 */
export function ownershipProof({ email, website, phone, lniRecord }) {
  const domain = String(email || "").split("@")[1]?.toLowerCase().trim();
  if (domain && !FREE_MAIL.has(domain) && website) {
    let host = "";
    try {
      host = new URL(/^https?:\/\//i.test(website) ? website : `https://${website}`)
        .hostname.toLowerCase().replace(/^www\./, "");
    } catch { /* unparseable website */ }
    if (host && (host === domain || host.endsWith(`.${domain}`) || domain.endsWith(`.${host}`))) {
      return "email-domain";
    }
  }
  const digits = s => String(s || "").replace(/\D/g, "").replace(/^1(?=\d{10}$)/, "");
  if (phone && lniRecord?.phonenumber && digits(phone) &&
      digits(phone) === digits(lniRecord.phonenumber)) {
    return "lni-phone";
  }
  return null;
}

/* ---------------------------------------------------------------- GitHub */

async function ghFetch(path, token, init = {}) {
  return fetch(`${GH}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": UA,
      ...(init.headers || {}),
    },
    signal: AbortSignal.timeout(15000),
  });
}

/**
 * Read-modify-write a JSON file with compare-and-swap on the blob sha.
 * `mutate` receives the parsed value and returns the new value, or null to
 * skip the write (used for idempotency).
 */
export async function updateJsonFile({ path, token, message, mutate }) {
  let lastErr;
  for (let attempt = 0; attempt < 5; attempt++) {
    const get = await ghFetch(
      `/repos/${OWNER}/${REPO}/contents/${path}?ref=${BRANCH}`, token);
    if (!get.ok) throw new Error(`read ${path}: ${get.status} ${await get.text()}`);
    const meta = await get.json();
    const current = JSON.parse(
      Buffer.from(meta.content, "base64").toString("utf8"));

    const next = await mutate(structuredClone(current));
    if (next === null) return { skipped: true };

    const put = await ghFetch(`/repos/${OWNER}/${REPO}/contents/${path}`, token, {
      method: "PUT",
      body: JSON.stringify({
        message,
        branch: BRANCH,
        sha: meta.sha,
        content: Buffer.from(JSON.stringify(next, null, 1) + "\n", "utf8")
          .toString("base64"),
      }),
    });
    if (put.ok) return { committed: true, commit: (await put.json()).commit?.sha };

    const status = put.status;
    lastErr = new Error(`write ${path}: ${status} ${await put.text()}`);
    // 409 = sha raced; 422 can also be a stale sha. Both are retryable.
    if (![409, 422, 429, 500, 502, 503].includes(status)) throw lastErr;
    await new Promise(r => setTimeout(r, 800 + Math.random() * 700));
  }
  throw lastErr;
}

/* ---------------------------------------------------------------- Stripe */

/**
 * Verify a Stripe-Signature header against the raw request body.
 * Throws on any failure. Mirrors stripe-node's constructEvent semantics.
 */
export function verifyStripeSignature(rawBody, header, secret, tolerance = 300) {
  if (!header) throw new Error("missing stripe-signature header");
  if (!secret) throw new Error("missing webhook secret");

  let timestamp = null;
  const candidates = [];
  for (const part of String(header).split(",")) {
    const i = part.indexOf("=");
    if (i < 0) continue;
    const k = part.slice(0, i).trim();
    const v = part.slice(i + 1).trim();
    if (k === "t") timestamp = v;
    else if (k === "v1") candidates.push(v);
  }
  if (!timestamp || !/^\d+$/.test(timestamp)) throw new Error("no timestamp in signature");
  if (!candidates.length) throw new Error("no v1 signature present");

  const expected = crypto
    .createHmac("sha256", secret)
    .update(Buffer.concat([
      Buffer.from(timestamp, "utf8"),
      Buffer.from(".", "utf8"),
      Buffer.isBuffer(rawBody) ? rawBody : Buffer.from(rawBody, "utf8"),
    ]))
    .digest();

  let ok = false;
  for (const c of candidates) {
    if (!/^[0-9a-f]{64}$/i.test(c)) continue;      // malformed hex must not throw
    const got = Buffer.from(c, "hex");
    if (got.length === expected.length && crypto.timingSafeEqual(got, expected)) {
      ok = true;                                    // no early break: constant work
    }
  }
  if (!ok) throw new Error("signature mismatch");

  // One-sided age check: future timestamps are tolerated (clock skew), stale ones are not.
  const age = Math.floor(Date.now() / 1000) - Number(timestamp);
  if (age > tolerance) throw new Error(`timestamp too old (${age}s)`);

  return JSON.parse(Buffer.isBuffer(rawBody) ? rawBody.toString("utf8") : rawBody);
}

/* ----------------------------------------------------------------- Email */

/** Structured plain-text notification to the operator (Resend). */
export async function notify({ subject, lines, apiKey, to, from }) {
  if (!apiKey) throw new Error("missing RESEND_API_KEY");
  const body = Array.isArray(lines) ? lines.join("\n") : String(lines);
  const r = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
      "User-Agent": UA,                    // Resend 403s requests without one
    },
    body: JSON.stringify({
      from: from || "ADU Builder Index <onboarding@resend.dev>",
      to: [to],
      subject,
      text: body,
    }),
    signal: AbortSignal.timeout(10000),
  });
  if (!r.ok) throw new Error(`resend ${r.status}: ${await r.text()}`);
  return r.json();
}

export const DIVIDER = "──────────────────────────";
