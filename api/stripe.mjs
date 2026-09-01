/**
 * POST /api/stripe — Stripe webhook receiver.
 *
 * A builder subscribes via the Payment Link → we validate their WA L&I license
 * → a verified builder is committed to data/featured.json (which rebuilds the
 * site) and the operator is emailed. Anything unverified is emailed only, so
 * the operator can refund per the guarantee printed on the site.
 *
 * Needs env: STRIPE_WEBHOOK_SECRET, GITHUB_TOKEN, RESEND_API_KEY, OPERATOR_EMAIL
 */
import {
  verifyStripeSignature, lniByLicense, lniByName, loadBuilders, matchBuilder,
  updateJsonFile, notify, FEATURED_SLOTS, DIVIDER,
} from "../lib/onboarding.mjs";

const field = (session, key) =>
  (session.custom_fields || [])
    .find(f => (f.key || "").toLowerCase().includes(key))?.text?.value?.trim() || "";

/** Raw body is required for HMAC verification, so body parsing stays off. */
export const config = { api: { bodyParser: false } };

async function rawBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  return Buffer.concat(chunks);
}

export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return res.status(405).send("method not allowed");
  }

  const raw = await rawBody(req);
  let event;
  try {
    event = verifyStripeSignature(
      raw, req.headers["stripe-signature"],
      process.env.STRIPE_WEBHOOK_SECRET);
  } catch (err) {
    console.error("signature rejected:", err.message);
    return res.status(400).send("invalid signature");
  }

  if (event.type !== "checkout.session.completed") {
    return res.status(200).json({ ignored: event.type });
  }
  const s = event.data.object;
  if (s.mode !== "subscription" || s.payment_status === "unpaid") {
    return res.status(200).json({ ignored: "not a paid subscription" });
  }

  const email = s.customer_details?.email || "";
  const business =
    field(s, "business") ||
    s.collected_information?.business_name ||
    s.customer_details?.business_name ||
    s.customer_details?.name || "";
  const license = field(s, "licen");
  const website = field(s, "web") || field(s, "site");
  const blurb = field(s, "blurb") || field(s, "descri");

  const money = ((s.amount_total ?? 0) / 100).toFixed(2);
  const head = [
    `Company:  ${business || "(not provided)"}`,
    `Email:    ${email || "(none)"}`,
    `License:  ${license || "(not provided)"}`,
    `Website:  ${website || "(none)"}`,
    `Paid:     $${money} ${String(s.currency || "usd").toUpperCase()}`,
    `Session:  ${s.id}`,
    DIVIDER,
  ];

  const send = (subject, lines) => notify({
    subject, lines, apiKey: process.env.RESEND_API_KEY,
    to: process.env.OPERATOR_EMAIL,
  });

  try {
    // 1. License must be ACTIVE in the WA registry.
    const lni = license ? await lniByLicense(license) : await lniByName(business);
    if (!lni.active.length) {
      const status = lni.records[0]?.contractorlicensestatus || "no record found";
      await send(`✗ Paid but license not active — ${business || email}`, [
        ...head,
        `✗ WA L&I license is NOT active (${status}).`,
        "",
        "Per the guarantee on the site, refund and cancel:",
        "Stripe → Payments → find the charge → Refund, then cancel the subscription.",
        "Reply template 3 in outreach/reply-templates.md.",
      ]);
      return res.status(200).json({ ok: true, action: "flagged" });
    }
    const rec = lni.active[0];

    // 2. They must correspond to a builder profile on the site.
    const builders = await loadBuilders();
    const m = matchBuilder(builders, business);
    if (m.none || m.ambiguous) {
      await send(`⚠ Paid — needs manual match: ${business || email}`, [
        ...head,
        `License ${rec.contractorlicensenumber} is ACTIVE ✅`,
        m.ambiguous
          ? `⚠ ${m.ambiguous.length} profiles match that name: ${m.ambiguous.map(b => b.slug).join(", ")}`
          : "⚠ No builder profile matches that business name.",
        "",
        "Tell Claude: \"featured verified: <company>, city <X>, blurb <Y>, website <Z>\"",
      ]);
      return res.status(200).json({ ok: true, action: "needs-match" });
    }

    // 3. Publish.
    const b = m.builder;
    const city = Object.keys(b.cities || { Seattle: 1 }).sort()[0];
    let outcome = "committed";
    const result = await updateJsonFile({
      path: "data/featured.json",
      token: process.env.GITHUB_TOKEN,
      message: `Featured: ${b.name} (${city}) via Stripe ${s.id}`,
      mutate: (data) => {
        if (data.builders.some(f => f._stripe_session === s.id)) return null; // replay
        if (data.builders.some(f => f.slug === b.slug)) return null;          // already live
        const taken = data.builders.filter(f => f.city === city).length;
        if (taken >= FEATURED_SLOTS) { outcome = "city-full"; return null; }
        data.builders.push({
          slug: b.slug, city,
          blurb: blurb || `${b.permits_total} ADU permits on record in ${city}.`,
          website, _stripe_session: s.id,
          _license: rec.contractorlicensenumber,
        });
        return data;
      },
    });

    if (result.skipped && outcome === "city-full") {
      await send(`⚠ Paid but ${city} is full — ${b.name}`, [
        ...head,
        `License ${rec.contractorlicensenumber} ACTIVE ✅, profile ${b.slug} ✅`,
        `✗ All ${FEATURED_SLOTS} ${city} slots are taken.`,
        "",
        "Either raise FEATURED_SLOTS, offer another city, or refund.",
      ]);
      return res.status(200).json({ ok: true, action: "city-full" });
    }
    if (result.skipped) {
      return res.status(200).json({ ok: true, action: "duplicate" });
    }

    await send(`✅ New featured builder: ${b.name}`, [
      ...head,
      `License ${rec.contractorlicensenumber} ACTIVE ✅`,
      `Profile matched: ${b.slug} (${b.permits_total} permits) ✅`,
      `Published to ${city} — live in ~1 minute:`,
      `https://adubuilderindex.com/builders/${b.slug}.html`,
      DIVIDER,
      "Nothing further needed. To edit their card, change data/featured.json.",
    ]);
    return res.status(200).json({ ok: true, action: "published" });
  } catch (err) {
    // 500 → Stripe retries for up to 3 days; the commit step is idempotent.
    console.error("onboarding failed:", err);
    return res.status(500).send(`error: ${err.message}`);
  }
}
