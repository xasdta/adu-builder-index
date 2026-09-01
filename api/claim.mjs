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
  updateJsonFile, notify, DIVIDER,
} from "../lib/onboarding.mjs";

const seeOther = (path) =>
  new Response(null, { status: 303, headers: { Location: path } });

export default async function handler(request) {
  if (request.method !== "POST") {
    return new Response("method not allowed", { status: 405 });
  }

  // Accept a plain form post (no JS) or JSON.
  let f = {};
  const ct = request.headers.get("content-type") || "";
  if (ct.includes("application/json")) {
    f = await request.json().catch(() => ({}));
  } else {
    f = Object.fromEntries(new URLSearchParams(await request.text()));
  }

  const company = String(f.company || "").trim();
  const license = String(f.license_number || "").trim();
  const email = String(f.email || "").trim();
  const website = String(f.website || "").trim();
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
          : "⚠ No builder profile matches that business name (they may not be in our permit data).",
      ]);
      return seeOther("/thanks.html");
    }
    const b = m.builder;

    const proof = ownershipProof({ email, website, phone, lniRecord: rec });
    if (!proof) {
      await send(`⚠ Claim needs your check: ${company}`, [
        ...head,
        `License ${rec.contractorlicensenumber} ACTIVE ✅`,
        `Profile: ${b.slug} ✅`,
        "✗ No automatic ownership proof — the email domain doesn't match the website,",
        "  and the phone doesn't match the L&I record. Could be legitimate (a personal",
        "  address) or could be someone claiming a company they don't own.",
        "",
        `L&I phone on file: ${rec.phonenumber || "(none)"}`,
        "",
        "If it checks out, tell Claude:",
        `  claim verified: ${company}, website ${website || "?"}, phone ${phone || "?"}`,
      ]);
      return seeOther("/thanks.html");
    }

    let already = false;
    const result = await updateJsonFile({
      path: "data/claims.json",
      token: process.env.GITHUB_TOKEN,
      message: `Claim: ${b.name} (verified via ${proof})`,
      mutate: (data) => {
        if (data.builders.some(c => c.slug === b.slug)) { already = true; return null; }
        data.builders.push({
          slug: b.slug,
          website,
          phone,
          service_area: String(f.service_area || "").trim() || undefined,
          claimed_date: new Date().toISOString().slice(0, 10),
          _verified_by: proof,
          _license: rec.contractorlicensenumber,
        });
        return data;
      },
    });

    if (already) {
      await send(`⚠ Claim on an already-claimed profile: ${company}`, [
        ...head,
        `Profile ${b.slug} is already claimed. Possible correction request — or a hijack attempt.`,
      ]);
      return seeOther("/thanks.html");
    }

    await send(`✅ Verified claim published: ${b.name}`, [
      ...head,
      `License ${rec.contractorlicensenumber} ACTIVE ✅`,
      `Ownership proven via ${proof} ✅`,
      `Published — live in ~1 minute:`,
      `https://adubuilderindex.com/builders/${b.slug}.html`,
      DIVIDER,
      "Nothing further needed.",
      result.commit ? `commit ${result.commit.slice(0, 7)}` : "",
    ]);
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
