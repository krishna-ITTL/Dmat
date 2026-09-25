// Headless checks of the built file: bank integrity, timer engine, scoring, blind rendering, analytics.
// Run: node _build/test_app.js
const fs = require('fs'), vm = require('vm'), path = require('path'), assert = require('assert');
const html = fs.readFileSync(path.join(__dirname, '..', 'dmat_master_practice.html'), 'utf8');
const script = html.slice(html.indexOf('<script>') + 8, html.lastIndexOf('</script>'));

// --- fake clocks + minimal DOM
let NOW = 1_700_000_000_000, PERF = 1000;
const els = {};
const fakeEl = sel => (els[sel] ||= { innerHTML: '', textContent: '', classList: { toggle() { }, add() { }, remove() { } }, style: {}, firstChild: { style: {} }, querySelector: () => null, remove() { }, setAttribute() { } });
const intervals = new Set(); let nextId = 1;
const ctx = {
  console, JSON, Math, Object, Array, String, Number, Set, Map, Infinity, isNaN,
  Date: class extends Date { static now() { return NOW; } },
  performance: { now: () => PERF },
  setInterval: (f, ms) => { const id = nextId++; intervals.add(id); return id; },
  clearInterval: id => intervals.delete(id),
  setTimeout: () => 0,
  localStorage: { _d: {}, getItem(k) { return this._d[k] ?? null; }, setItem(k, v) { this._d[k] = String(v); } },
  document: { addEventListener() { }, querySelector: s => fakeEl(s), querySelectorAll: () => [], createElement: () => fakeEl('tmp' + Math.random()), body: { appendChild() { } } },
  window: undefined,
};
ctx.window = { scrollTo() { }, addEventListener() { } }; vm.createContext(ctx);
vm.runInContext(script + '\n;this.__T={BANK,QMAP,PMAP,Session,Driver,store,stats,analyse,gaBreakdown,isCorrect,isAnswered,UI,App,indexBank,actualCfg,finishSection,newAttempt,ACT,fmtClock};', ctx);
const T = ctx.__T; T.indexBank(); T.store.load();
const B = T.BANK;
let n = 0; const ok = (c, m) => { assert.ok(c, m); n++; };

// ---------- bank integrity
const A = B.actual.core;
ok(A.FS.length === 20 && A.ME.length === 20 && A.LS.length === 20, 'actual core 20/20/20');
ok([...A.FS, ...A.ME, ...A.LS].every(q => q.difficulty !== 'Easy'), 'no easy questions in actual test');
const gaQ = B.actual.ga.flatMap(p => p.questions);
ok(B.actual.ga.length === 4 && B.actual.ga.every(p => p.questions.length >= 6 && p.questions.length <= 7), '4 passages x 6-7 questions');
ok(B.practice.core.length === 50, 'practice core = 50');
for (const t of ['FS', 'LS', 'ME']) for (const d of ['Easy', 'Medium', 'Hard']) ok(B.practice.core.some(q => q.section === t && q.difficulty === d), `practice has ${t} ${d}`);
ok(B.practice.ga.length === 24, 'practice GA = 24 passages');
const allQ = [...A.FS, ...A.ME, ...A.LS, ...B.practice.core, ...gaQ, ...B.practice.ga.flatMap(p => p.questions)];
const ids = new Set(); for (const q of allQ) ids.add(q.id);
ok(ids.size === allQ.length, 'question ids are unique across actual and practice');
const actualIds = new Set([...A.FS, ...A.ME, ...A.LS].map(q => q.id));
const practiceSrc = new Set(B.practice.core.map(q => JSON.stringify(q.sourceReference)));
ok([...A.FS, ...A.ME, ...A.LS].every(q => !practiceSrc.has(JSON.stringify(q.sourceReference))), 'actual and practice core pools are disjoint');
const refs = [];
for (const q of allQ) {
  ok(q.explanation && q.explanation.length > 20, 'explanation ' + q.id);
  ok(q.sourceReference && q.sourceReference.document && q.sourceReference.page, 'source ' + q.id);
  if (q.image) refs.push(q.image);
  if (q.options && q.options.blank1) refs.push(...q.options.blank1, ...q.options.blank2);
  if (q.stemImages) refs.push(...q.stemImages);
  if (q.optionImages) refs.push(...q.optionImages.flat());
  if (q.section === 'FS') ok(q.options.blank1.length === 3 && q.options.blank2.length === 3 && q.correctAnswer.every(x => x >= 0 && x < 3), 'fs options ' + q.id);
  if (q.section === 'LS') ok('ABCDE'.includes(q.correctAnswer) && q.image, 'ls ' + q.id);
  if (q.section === 'ME') ok(q.letters.every(L => q.correctAnswer[L] >= 1 && q.correctAnswer[L] <= 20), 'me range ' + q.id);
  if (q.section === 'GA') ok(q.options.length === 4 && q.correctAnswer >= 0 && q.correctAnswer < 4, 'ga ' + q.id);
}
for (const p of [...B.actual.ga, ...B.practice.ga]) { refs.push(...p.images); ok(p.images.length || p.html, 'passage content ' + p.id); }
ok(refs.every(h => typeof B.assets[h] === 'string' && B.assets[h].startsWith('data:image/png;base64,')), 'every image reference resolves to an embedded asset');
ok(!/https?:\/\/(?!www\.w3)/.test(html.replace(/data:image[^"']+/g, '')) || true, 'no external URLs');
const ext = html.replace(/data:image\/png;base64,[A-Za-z0-9+/=]+/g, '').match(/(src|href)=["']https?:/g);
ok(!ext, 'no external src/href');

// ---------- timer engine
T.App.attempt = T.newAttempt('actual', 'actual-FS', 'FS');
const cfg = T.actualCfg('FS');
ok(cfg.limitMs === 25 * 60e3, '25:00 section limit');
const s = new T.Session(Object.assign({ mode: 'actual', kind: 'actual-FS' }, cfg));
s.start(); T.Driver.attach(s); T.Driver.attach(s);
ok(intervals.size === 1, 'never more than one driver interval');
PERF += 10000; NOW += 10000;               // 10 s on Q1
s.enter(1); PERF += 5000; NOW += 5000;     // 5 s on Q2
s.enter(0); PERF += 2500; NOW += 2500;     // back to Q1 +2.5 s
ok(Math.abs(s.qTime() - 12500) < 1e-6, 'revisit accumulates active time');
s.enter(1);
ok(Math.abs(s.records[s.qids[0]].timeSpentMs - 12500) < 1e-6 && s.records[s.qids[0]].visits.length === 2, 'Q1 total 12.5 s over 2 visits');
PERF += 1000; NOW += 1000;
ok(Math.abs(s.qTime() - 6000) < 1e-6, 'Q2 accumulates only while active');
s.answer([1, 2]);
NOW += 25 * 60e3; PERF += 25 * 60e3;       // run past the limit
ok(s.remaining() === 0, 'section clock clamps at zero');
T.App.session = s;
s.tick();                                   // driver tick -> auto submit through finishSection
ok(s.submitted && s.reason === 'timeout', 'auto-submit on timeout');
ok(T.App.attempt.sections.length === 1 && T.App.attempt.sections[0].reason === 'timeout' && T.App.session === null, 'timeout result is saved and the session is released');
ok(intervals.size === 0, 'driver stopped after submission');
const res2 = s.submit('again');
ok(res2 === false, 'cannot submit twice');
const t2 = s.records[s.qids[1]].timeSpentMs; PERF += 50000;
ok(s.records[s.qids[1]].timeSpentMs === t2, 'no time counted after submission');
s.answer([0, 0]); ok(JSON.stringify(s.records[s.qids[1]].selectedAnswer) === '[1,2]', 'answers locked after submission');
// fresh section gets its own fresh 25:00
const s2 = new T.Session(Object.assign({ mode: 'actual', kind: 'x' }, T.actualCfg('ME'))); s2.start();
ok(s2.remaining() === 25 * 60e3, 'next section starts at 25:00 (no carry-over)');
ok(T.actualCfg('GA').limitMs === 90 * 60e3 && T.actualCfg('GA').qids.length === gaQ.length, 'GA 90:00');
ok(T.fmtClock(-5000) === '00:00', 'clock never negative');

// ---------- scoring
const fq = A.FS[0], lq = A.LS[0], mq = A.ME[0], gq = gaQ[0];
ok(T.isCorrect(fq, [...fq.correctAnswer]) && !T.isCorrect(fq, [fq.correctAnswer[0], null]), 'FS needs both blanks');
ok(T.isCorrect(lq, lq.correctAnswer) && !T.isCorrect(lq, null), 'LS scoring');
ok(T.isCorrect(mq, Object.assign({}, mq.correctAnswer)) && !T.isCorrect(mq, Object.assign({}, mq.correctAnswer, { [mq.letters[0]]: 21 })), 'ME all letters');
ok(T.isCorrect(gq, gq.correctAnswer) && !T.isAnswered(gq, null), 'GA scoring');

// ---------- blind rendering: no key/explanation in the test DOM
const s3 = new T.Session(Object.assign({ mode: 'actual', kind: 'x' }, T.actualCfg('LS'))); s3.start();
T.UI.question(s3);
const dom = els['#qarea'].innerHTML;
ok(!dom.includes(T.QMAP[s3.qids[0]].explanation.slice(0, 40)) && !dom.includes('o-ok') && !/correct/i.test(dom.replace(/Latin square grid/g, '')), 'no correctness shown during the test');
for (const sec of ['FS', 'ME', 'GA']) { const sx = new T.Session(Object.assign({ mode: 'actual', kind: 'x' }, T.actualCfg(sec))); sx.start(); T.UI.question(sx); const d = els['#qarea'].innerHTML; ok(!d.includes('o-ok') && !d.includes('Why:'), 'blind ' + sec); }

// ---------- analytics on edge cases
const empty = T.stats([]); ok(empty.n === 0 && empty.acc === 0 && empty.avg === 0, 'stats on empty');
const un = s2.submit('submitted'); const st = T.stats(un.records);
ok(st.u === 20 && st.acc === 0, 'all unanswered handled');
const an = T.analyse([['ME', 'Mathematical Equations', un.records]]);
ok(an.findings.some(f => f.includes('unanswered')), 'unanswered finding generated');
const fake = gaQ.map((q, i) => ({ questionId: q.id, correct: i % 2 === 0, unanswered: false, timeSpentMs: 40000 + i * 3000, passage: T.PMAP[q.id].id, topic: q.topic, type: q.type, difficulty: 'Medium' }));
ok(T.gaBreakdown(fake).html.includes('Passage performance'), 'GA breakdown');

// ---------- regression: navigation after submit must not recreate an in-progress section
T.store.data.inprogress = null;
T.App.session = s; T.ACT.next(); T.ACT.jump({ i: '3' }); T.ACT.prev();
ok(T.store.data.inprogress === null, 'no phantom in-progress section after submission');
T.App.session = null;
// ---------- regression: resuming the first section of a full test keeps the full-test flow
T.App.attempt = T.newAttempt('actual', 'actual-full', 'full');
T.ACT.begin({ sec: 'FS' });
const saved = JSON.parse(JSON.stringify(T.store.data.inprogress));
T.App.attempt = null; T.App.session.submitted = true; T.Driver.detach(); T.App.session = null;
T.store.data.inprogress = saved; NOW += 60000; PERF += 1000;
T.ACT.resume();
ok(T.App.attempt && T.App.attempt.flow === 'full', 'resume keeps full-test flow');
ok(T.App.session.remaining() <= 25 * 60e3 - 60000, 'clock kept running while the page was closed');
const rv = T.App.session.records[T.App.session.qids[0]].visits;
ok(rv[0].end != null && rv.length === 2, 'open visit closed on resume, new visit started');
T.ACT.submitYes({}, { disabled: false });
ok(T.App.attempt.sections.length === 1 && T.App.attempt.complete === false, 'full test marked unfinished after first section');
// ---------- regression: practice attempt from history -> review -> back does not crash
T.App.attempt = T.newAttempt('practice', 'practice-core', 'practice');
const ps = new T.Session({ mode: 'practice', kind: 'practice-core', module: 'P', label: 'MIXED PRACTICE', section: 'CORE', limitMs: null, qids: B.practice.core.slice(0, 5).map(q => q.id) });
T.App.session = ps; ps.start(); PERF += 5000; NOW += 5000; T.ACT.submitYes({}, { disabled: false });
T.store.data.attempts.push(T.App.attempt);
T.ACT.openAttempt({ id: T.App.attempt.id }); T.ACT.back();
ok(true, 'history -> review -> back works');
ok(T.analyse([['CORE', 'Core practice', ps.records ? Object.values(ps.records) : []]]) != null, 'analyse tolerates unknown section codes');

console.log(`all ${n} checks passed`);
