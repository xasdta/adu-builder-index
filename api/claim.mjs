/**
 * POST /api/claim — free profile claim from the site form.
 *
 * Validates the WA L&I license, then requires a second factor proving the
 * submitter actually represents the company (a public registry number proves
 * nothing on its own). Verified claims commit to data/claims.json and publish;
 * everything else emails the operator.
 *
 * Needs env: GITHUB_TOKEN, RESEND_API_KEY, OPERATOR_EMAIL
 */
import {
  lniByLicense, lniByName, loadBuilders, matchBuilder, ownershipProof,
  licenceMatchesCompany, safeUrl, notify, DIVIDER,
} from "../lib/onboarding.mjs";

export const config = { api: { bodyParser: false } };

const CLAIMS_NOTE =
  "(Claims are never auto-published: the ownership signals are derived from " +
  "public data, so a human approves each one.)";

async function rawBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  return Buffer.concat(chunks).toString("utf8");
}

export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return res.status(405).send("method not allowed");
  }
  const seeOther = (path) => { res.writeHead(303, { Location: path }); res.end(); };

  // Accept a plain form post (no JS) or JSON.
  let f = {};
  const body = await rawBody(req);
  if ((req.headers["content-type"] || "").includes("application/json")) {
    try { f = JSON.parse(body); } catch { f = {}; }
  } else {
    f = Object.fromEntries(new URLSearchParams(body));
  }

  const company = String(f.company || "").trim();
  const license = String(f.license_number || "").trim();
  const email = String(f.email || "").trim();
  const website = safeUrl(f.website);
  const phone = String(f.phone || "").trim();
  const message = String(f.message || "").trim();
  const wants = String(f.request_type || "").trim();

  if (f.botcheck || !company || !email) return seeOther("/thanks.html");

  const send = (subject, lines) => notify({
    subject, lines, apiKey: process.env.RESEND_API_KEY,
    to: process.env.OPERATOR_EMAIL,
  }).catch(err => console.error("notify failed:", err.message));

  const head = [
    `Company:  ${company}`,
    `Email:    ${email}`,
    `License:  ${license || "(not provided)"}`,
    `Website:  ${website || "(none)"}`,
    `Phone:    ${phone || "(none)"}`,
    `Wants:    ${wants || "claim"}`,
    ...(message ? ["", `Message:  ${message}`] : []),
    DIVIDER,
  ];

  try {
    const lni = license ? await lniByLicense(license) : await lniByName(company);
    if (!lni.active.length) {
      // No email: bogus submissions never reach the inbox, real typos self-correct.
      return seeOther("/claim-error.html");
    }
    const rec = lni.active[0];

    const builders = await loadBuilders();
    const m = matchBuilder(builders, company);
    if (m.none || m.ambiguous) {
      await send(`⚠ Claim needs manual match: ${company}`, [
        ...head,
        `License ${rec.contractorlicensenumber} ACTIVE ✅`,
        m.ambiguous
          ? `⚠ ${m.ambiguous.length} profiles match: ${m.ambiguous.map(b => b.slug).join(", ")}`
          : "⚠ No builder profile matches that business name.",
      ]);
      return seeOther("/thanks.html");
    }
    const b = m.builder;

    // The licence must belong to the company being claimed. Without this, any
    // active licence number — all public, and printed on our own pages — could
    // be paired with a competitor's name to take over their profile.
    const bind = licenceMatchesCompany(rec, company, b);
    if (!bind.ok) {
      await send(`✗ Claim rejected — licence/company mismatch: ${company}`, [
        ...head,
        `✗ ${bind.reason}`,
        "",
        "Nothing was published. This is the shape of a profile-hijack attempt,",
        "though it can also be an honest typo.",
      ]);
      return seeOther("/claim-error.html");
    }

    const proof = ownershipProof({ email, website, phone, lniRecord: rec });

    // Deliberately NOT auto-published. Neither factor is a possession proof:
    // the email/website pair is two strings from the same request, and the L&I
    // phone is a public field of the same open dataset. Publishing on that
    // basis would let a stranger put their own contact details on a
    // competitor's page. A human confirms; the email below has everything.
    const claimed = CLAIMS_NOTE;
    await send(
      proof ? `✅ Claim verified — approve to publish: ${b.name}`
            : `⚠ Claim needs your check: ${b.name}`,
      [
        ...head,
        `Licence ${rec.contractorlicensenumber} ACTIVE ✅`,
        `Licence name matches the company ✅`,
        `Profile: ${b.slug} (${b.permits_total} permits)`,
        proof ? `Supporting signal: ${proof} ✅` : "No supporting signal ✗",
        "",
        `L&I on file — phone ${rec.phonenumber || "(none)"}, ${rec.city || "?"}`,
        DIVIDER,
        proof
          ? "Everything checks out. To publish, reply to Claude with:"
          : "Confirm they really represent this company (a quick call to the L&I",
        proof ? "" : "number above is the reliable test), then reply to Claude with:",
        `  claim verified: ${company}, website ${website || "?"}, phone ${phone || "?"}`,
        "",
        claimed,
      ].filter(Boolean));
    return seeOther("/thanks.html");
  } catch (err) {
    console.error("claim failed:", err);
    await send(`✗ Claim endpoint error: ${company}`, [
      ...head, `The endpoint threw: ${err.message}`,
      "The submission was NOT saved. Follow up manually.",
    ]);
    return seeOther("/thanks.html");
  }
}
