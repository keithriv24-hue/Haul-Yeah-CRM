/* Stage 5 acceptance — JS-side engine parity.
   Proves, for every case, that threading the estimating parameters (EP) changes
   NOTHING versus (a) the same engine with NO EP and (b) a FROZEN copy of the
   engine captured before Stage 5. Compares rounded dollars (0-cent tolerance),
   man-hours (<=0.01), and the crew / truck / blocker recommendations.

   Data in:  /tmp/stage5_data.json  ({ cases:[{id,label,kind,inputs,pricing,saved,replayable}], seededEP })
   Data out: /tmp/stage5_js_results.json ([{ id, schedMH, billMH, onsite, crew, crewRec, trucks, blockers, bandLo, bandHi, finalTotal, deposit }])
   Exit 0 = all JS parity checks pass, 1 = at least one mismatch. */
import { readFileSync, writeFileSync, copyFileSync } from "node:fs";

// regenerate the live engine copy from source (same mechanism the other test scripts use)
copyFileSync(new URL("../src/lib/scopeEngine.js", import.meta.url), new URL("./_engine.mjs", import.meta.url));
const mod = await import("./_engine.mjs");
const frozen = await import("./_engine_frozen_pre_stage5.mjs");

const data = JSON.parse(readFileSync("/tmp/stage5_data.json", "utf8"));
const EP = data.seededEP || {};

const HR = 0.01;                 // man-hour tolerance
const CENT = 1e-9;               // dollars must be identical
const dollarEq = (a, b) => (a == null && b == null) || Math.abs(Number(a) - Number(b)) <= CENT;
const hourEq = (a, b) => Math.abs(Number(a || 0) - Number(b || 0)) <= HR;
const blockersSig = (r) => JSON.stringify((r.blockers || []).map((b) => b.code).sort());

function outSig(o) {
  const r = o.r;
  return {
    bandLo: o.bandLo, bandHi: o.bandHi, finalTotal: o.finalTotal, deposit: o.deposit,
    schedMH: r.schedMH, billMH: r.billMH, onsite: r.onsite,
    crew: r.crew, crewRec: r.crewRec, trucks: r.displayTrucks, blockers: blockersSig(r),
  };
}

const results = [];
const fails = [];
const unreplayableList = [];
let replayable = 0, unreplayable = 0;

// which saved fields to compare, only where the saved doc actually stored a value
function matchesSaved(sig, s) {
  const bad = [];
  for (const k of ["bandLo", "bandHi", "finalTotal", "deposit"])
    if (s[k] != null && !dollarEq(sig[k], s[k])) bad.push(`$${k} ${sig[k]}!=${s[k]}`);
  if (s.schedMH != null && !hourEq(sig.schedMH, s.schedMH)) bad.push(`schedMH ${sig.schedMH}!=${s.schedMH}`);
  if (s.crew != null && sig.crew !== s.crew) bad.push(`crew ${sig.crew}!=${s.crew}`);
  return bad;
}

for (const c of data.cases) {
  const P = c.pricing || {};
  const withEP = outSig(mod.scopeOutputs(c.inputs, P, EP));
  const noEP = outSig(mod.scopeOutputs(c.inputs, P, {}));
  const froz = outSig(frozen.scopeOutputs(c.inputs, P));

  const problems = [];
  // 3-way (ALWAYS): withEP === noEP === frozen — the core "EP changes nothing" proof
  const three = [["withEP-vs-noEP", withEP, noEP], ["withEP-vs-frozen", withEP, froz]];
  for (const [tag, a, b] of three) {
    for (const k of ["bandLo", "bandHi", "finalTotal", "deposit"])
      if (!dollarEq(a[k], b[k])) problems.push(`${tag}: $${k} ${a[k]} != ${b[k]}`);
    for (const k of ["schedMH", "billMH", "onsite"])
      if (!hourEq(a[k], b[k])) problems.push(`${tag}: ${k} ${a[k]} != ${b[k]}`);
    for (const k of ["crew", "crewRec", "trucks", "blockers"])
      if (a[k] !== b[k]) problems.push(`${tag}: ${k} ${a[k]} != ${b[k]}`);
  }

  // recompute === originally-saved dollars — a saved scope is REPLAYABLE only if the
  // FROZEN (pre-Stage-5) engine itself reproduces it. If the frozen engine can't, the
  // stored result was hand-seeded / from an older formula: unreplayable, NOT a pass, NOT a fail.
  let isReplayable = false;
  if (c.kind === "saved") {
    const s = c.saved || {};
    const frozenBad = matchesSaved(froz, s);
    if (c.replayable && frozenBad.length === 0) {
      isReplayable = true; replayable++;
      matchesSaved(withEP, s).forEach((m) => problems.push(`saved: ${m}`));
    } else {
      unreplayable++;
      const reason = !c.replayable ? "no stored pricing snapshot"
        : `pre-Stage-5 engine also does not reproduce the stored result (${frozenBad.join(", ")})`;
      unreplayableList.push({ id: c.id, label: c.label, reason });
    }
  }

  results.push({ id: c.id, label: c.label, kind: c.kind, replayable: isReplayable,
    schedMH: withEP.schedMH, billMH: withEP.billMH, onsite: withEP.onsite,
    crew: withEP.crew, crewRec: withEP.crewRec, trucks: withEP.trucks, blockers: withEP.blockers,
    bandLo: withEP.bandLo, bandHi: withEP.bandHi, finalTotal: withEP.finalTotal, deposit: withEP.deposit });

  const status = problems.length ? "FAIL" : "PASS";
  if (problems.length) fails.push({ id: c.id, label: c.label, problems });
  const money = withEP.finalTotal != null ? `$${withEP.finalTotal}` : `$${withEP.bandLo}-${withEP.bandHi}`;
  const tag = c.kind === "saved" ? (isReplayable ? "replay" : "EP-inv") : "edge";
  console.log(`${status.padEnd(4)} | ${tag.padEnd(7)} | ${(c.label || c.id).slice(0, 42).padEnd(42)} | ${money.padEnd(12)} | schedMH ${withEP.schedMH} | crew ${withEP.crew} | trucks ${withEP.trucks}`);
}

writeFileSync("/tmp/stage5_js_results.json", JSON.stringify(results, null, 2));

console.log(`\n3-way engine parity (withEP === noEP === frozen) ran on ALL ${data.cases.length} cases.`);
console.log(`saved-dollar replay: ${replayable} reproducible · ${unreplayable} unreplayable (not counted as passes)`);
if (unreplayableList.length) {
  console.log(`\nUNREPLAYABLE saved scopes (honest — proven EP-invariant but stored dollars not engine-reproducible):`);
  for (const u of unreplayableList) console.log(`  • ${(u.label || u.id)}: ${u.reason}`);
}
if (fails.length) {
  console.log(`\n${fails.length} MISMATCH(es):`);
  for (const f of fails) { console.log(`  ✗ ${f.label || f.id}`); f.problems.forEach((p) => console.log(`      - ${p}`)); }
  process.exit(1);
}
console.log(`\nJS parity: ${data.cases.length}/${data.cases.length} PASS — EP threading changed no quote.`);

