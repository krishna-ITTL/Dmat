"""Build bank.json: select verified questions into disjoint ACTUAL / PRACTICE pools, crop + embed images."""
import json, base64, hashlib, random, re, os, sys
import pymupdf
from common import SRC, DOCNAME, ROOT
import me, ls, fs, ga, ga_expl, official

DPI = 160
_docs, ASSETS = {}, {}


def doc(tag):
    if tag not in _docs: _docs[tag] = pymupdf.open(SRC[tag])
    return _docs[tag]


def crop(tag, page, box, dpi=DPI, pad=2):
    p = doc(tag)[page - 1]
    r = pymupdf.Rect(box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad) & p.rect
    png = p.get_pixmap(clip=r, dpi=dpi).tobytes('png')
    h = hashlib.sha1(png).hexdigest()[:12]
    ASSETS.setdefault(h, 'data:image/png;base64,' + base64.b64encode(png).decode())
    return h


DMAP = {'low': 'Easy', 'basic': 'Easy', 'easy': 'Easy', 'medium': 'Medium', 'moderate': 'Medium',
        'high': 'Hard', 'difficult': 'Hard', 'most difficult': 'Hard', 'hard': 'Hard'}


def dnorm(label, fallback): return DMAP.get((label or '').strip().lower(), fallback)


def ref(tag, page, section): return {'document': DOCNAME[tag], 'page': page, 'section': section}


# ---------------- Figure Sequences ----------------
def fs_items():
    items = []
    good, rej = fs.collect()
    for g in good:
        b = g['boxes']
        if 'strip' in b: strip = b['strip']
        else:
            allb = b['seq'] + b['q']
            strip = (min(x[0] for x in allb), min(x[1] for x in allb), max(x[2] for x in allb), max(x[3] for x in allb))
        items.append({'tag': g['src'], 'n': g['n'], 'page': g['page'], 'diff': dnorm(g['diff'], 'Medium'), 'strip': strip,
                      'o5': b['o5'], 'o6': b['o6'], 'ans': list(g['ans']), 'expl': g['expl'],
                      'section': f"Question {g['n']}" + (f" ({g['diff']})" if g['diff'] else '')})
    for o in official.fs_official():
        b = o['boxes']
        items.append({'tag': 'official', 'n': o['n'], 'page': o['page'], 'diff': o['diff'], 'strip': b['strip'], 'o5': b['o5'],
                      'o6': b['o6'], 'ans': list(o['ans']), 'expl': o['expl'] + f" (Official solution: page {o['sol_page']}.)",
                      'section': f"Figure Sequences – Exercise {o['n']}"})
    return items, rej


def fs_q(it, qid):
    return {'id': qid, 'module': 'core', 'section': 'FS', 'type': 'Figure Sequence', 'difficulty': it['diff'],
            'question': 'Study Matrices 1–4, work out the rules, then choose the correct matrix for BOTH question marks (Matrix 5 and Matrix 6).',
            'image': crop(it['tag'], it['page'], it['strip']),
            'options': {'blank1': [crop(it['tag'], it['page'], b) for b in it['o5']],
                        'blank2': [crop(it['tag'], it['page'], b) for b in it['o6']]},
            'correctAnswer': it['ans'], 'explanation': it['expl'],
            'sourceReference': ref(it['tag'], it['page'], it['section'])}


# ---------------- Latin Squares ----------------
LBL = set('αβγδε12345')


def ls_crop_box(it):
    """Grid bbox, extended only to real row/column labels (α–ε above, 1–5 left) when the source has them."""
    x0, y0, x1, y1 = it['bbox']; cw = (x1 - x0) / 5
    p = doc(it['src'])[it['page'] - 1]
    words = p.get_text('words')
    top = [w for w in words if w[4].strip() in 'αβγδε' and w[4].strip() and y0 - 1.3 * cw < w[3] <= y0 + 1 and x0 - 2 < w[0] < x1]
    left = [w for w in words if w[4].strip() in '12345' and len(w[4].strip()) == 1 and x0 - 1.3 * cw < w[2] <= x0 + 1 and y0 < w[1] < y1]
    bx = [x0, y0, x1, y1]
    if len(top) == 5:
        bx[1] = min(w[1] for w in top)
        if len(left) == 5: bx[0] = min(w[0] for w in left)
    return bx


def ls_items():
    good, rej = ls.collect()
    out = []
    for g in good:
        diff = dnorm(g['diff'], g['rated']) if g['src'] == 'official' else g['rated']
        sec = f"Latin Squares – Exercise {g['n']}" if g['src'] == 'official' else f"Question {g['n']}"
        out.append(dict(g, diffn=diff, section=sec))
    return out, rej


def ls_q(g, qid):
    expl = g['expl'] + (' (Official solution path: pages 27–31.)' if g['src'] == 'official' else '')
    return {'id': qid, 'module': 'core', 'section': 'LS', 'type': 'Latin Square', 'difficulty': g['diffn'],
            'question': 'Each letter may appear only once in every row and every column. Which letter belongs in the field marked with “?”',
            'image': crop(g['src'], g['page'], ls_crop_box(g), dpi=180, pad=4),
            'options': list('ABCDE'), 'correctAnswer': g['ans'], 'explanation': expl,
            'sourceReference': ref(g['src'], g['page'], g['section'])}


# ---------------- Mathematical Equations ----------------
def me_items():
    good, rej = me.collect()
    for g in good:
        k = len(g['sol'])
        g['diffn'] = dnorm(g['diff'], 'Easy' if k <= 2 else 'Medium' if k == 3 else 'Hard')
        g['section'] = f"Mathematical Equations – Exercise {g['n']}" if g['src'] == 'official' else f"Question {g['n']}"
    return good, rej


def me_q(g, qid):
    return {'id': qid, 'module': 'core', 'section': 'ME', 'type': 'Mathematical Equation', 'difficulty': g['diffn'],
            'question': 'Find the numbers the letters stand for so that all equations are correct. Each letter is an integer from 1 to 20.',
            'equations': g['lines'], 'letters': sorted(g['sol']), 'options': list(range(1, 21)),
            'correctAnswer': g['sol'], 'explanation': g['expl'], 'sourceReference': ref(g['src'], g['page'], g['section'])}


# ---------------- selection ----------------
def pick(pool, n, rng, used, pref=()):
    """Pick n distinct items; prefer sources in `pref` order round-robin for variety."""
    avail = [x for x in pool if id(x) not in used]
    rng.shuffle(avail)
    by = {}
    for x in avail: by.setdefault(x.get('tag') or x.get('src'), []).append(x)
    order = [s for s in pref if s in by] + [s for s in by if s not in pref]
    out = []
    while len(out) < n and any(by.values()):
        for s in order:
            if by.get(s) and len(out) < n: out.append(by[s].pop())
    if len(out) < n: raise SystemExit(f'not enough items: wanted {n}, got {len(out)}')
    for x in out: used.add(id(x))
    return out


def order_by_diff(xs, rng, key):
    rank = {'Easy': 0, 'Medium': 1, 'Hard': 2}
    rng.shuffle(xs); return sorted(xs, key=lambda x: rank[x[key]])


def main():
    rng = random.Random(20260925)
    report = {}
    # FS
    fsi, fsrej = fs_items(); used = set()
    off = [x for x in fsi if x['tag'] == 'official']
    A_fs = [x for x in off if x['diff'] != 'Easy'] + \
        pick([x for x in fsi if x['tag'] == 'doubt' and x['diff'] == 'Hard'], 6, rng, used) + \
        pick([x for x in fsi if x['tag'] == 'fsexp'], 5, rng, used) + \
        pick([x for x in fsi if x['tag'] == 'fsadv' and x['diff'] == 'Hard'], 2, rng, used) + \
        pick([x for x in fsi if x['tag'] in ('fsadv', 'doubt') and x['diff'] == 'Medium'], 3, rng, used)
    for x in A_fs: used.add(id(x))
    for x in off: used.add(id(x))
    P_fs = [x for x in off if x['diff'] == 'Easy'] + pick([x for x in fsi if x['diff'] == 'Easy'], 4, rng, used) + \
        pick([x for x in fsi if x['diff'] == 'Medium'], 6, rng, used, ('doubt', 'fsadv', 'fs50')) + \
        pick([x for x in fsi if x['diff'] == 'Hard'], 5, rng, used, ('fsexp', 'doubt', 'fs50'))
    # LS
    lsi, lsrej = ls_items(); usedl = set()
    offl = [x for x in lsi if x['src'] == 'official']
    A_ls = [x for x in offl if x['diffn'] != 'Easy'] + \
        pick([x for x in lsi if x['src'] != 'official' and x['diffn'] == 'Hard'], 9, rng, usedl, ('ls3', 'masters', 'ls2')) + \
        pick([x for x in lsi if x['src'] != 'official' and x['diffn'] == 'Medium'], 7, rng, usedl, ('masters', 'ls3', 'ls2', 'core150'))
    for x in A_ls: usedl.add(id(x))
    P_ls = [x for x in offl if x['diffn'] == 'Easy'] + \
        pick([x for x in lsi if x['diffn'] == 'Easy'], 4, rng, usedl, ('ls1', 'masters', 'core150', 'ls2')) + \
        pick([x for x in lsi if x['diffn'] == 'Medium'], 6, rng, usedl) + \
        pick([x for x in lsi if x['diffn'] == 'Hard'], 5, rng, usedl)
    # ME
    mei, merej = me_items(); usedm = set()
    offm = [x for x in mei if x['src'] == 'official']
    A_me = [x for x in offm if x['diffn'] != 'Easy'] + \
        pick([x for x in mei if x['src'] != 'official' and x['diffn'] == 'Hard'], 9, rng, usedm, ('c4', 'doubt', 'core150', 'masters', 'c3')) + \
        pick([x for x in mei if x['src'] != 'official' and x['diffn'] == 'Medium' and len(x['sol']) >= 3], 7, rng, usedm, ('c3', 'doubt', 'c2'))
    for x in A_me: usedm.add(id(x))
    P_me = [x for x in offm if x['diffn'] == 'Easy'] + \
        pick([x for x in mei if x['diffn'] == 'Easy'], 3, rng, usedm, ('c2', 'core150')) + \
        pick([x for x in mei if x['diffn'] == 'Medium'], 6, rng, usedm) + \
        pick([x for x in mei if x['diffn'] == 'Hard'], 5, rng, usedm)
    assert (len(A_fs), len(A_ls), len(A_me)) == (20, 20, 20), (len(A_fs), len(A_ls), len(A_me))
    assert len(P_fs) + len(P_ls) + len(P_me) == 50, (len(P_fs), len(P_ls), len(P_me))

    A_fs = order_by_diff(A_fs, rng, 'diff'); A_ls = order_by_diff(A_ls, rng, 'diffn'); A_me = order_by_diff(A_me, rng, 'diffn')
    actual = {'FS': [fs_q(x, f'A-FS-{i+1:02d}') for i, x in enumerate(A_fs)],
              'ME': [me_q(x, f'A-ME-{i+1:02d}') for i, x in enumerate(A_me)],
              'LS': [ls_q(x, f'A-LS-{i+1:02d}') for i, x in enumerate(A_ls)]}
    pq = [fs_q(x, f'P-FS-{i+1:02d}') for i, x in enumerate(P_fs)] + [ls_q(x, f'P-LS-{i+1:02d}') for i, x in enumerate(P_ls)] + \
         [me_q(x, f'P-ME-{i+1:02d}') for i, x in enumerate(P_me)]
    # interleave types, easy -> hard
    rank = {'Easy': 0, 'Medium': 1, 'Hard': 2}
    rng.shuffle(pq); pq.sort(key=lambda q: rank[q['difficulty']])
    by = {d: [q for q in pq if q['difficulty'] == d] for d in rank}
    inter = []
    for d in rank:
        g = {t: [q for q in by[d] if q['section'] == t] for t in ('FS', 'LS', 'ME')}
        while any(g.values()):
            for t in ('LS', 'FS', 'ME'):
                if g[t]: inter.append(g[t].pop())
    practice_core = inter

    # ---------------- General Academic ----------------
    offga = official.ga_official()
    def ga_off_passage(p, trim=None, pre='P'):
        qs = [q for q in p['questions'] if q['n'] != trim]
        return {'id': f"{pre}-OFF-{p['id']}", 'title': p['title'], 'topic': p['topic'], 'format': 'figures/formulas (original pages)',
                'images': [crop('official', pg, box, dpi=150, pad=0) for pg, box in p['crops']], 'html': None,
                'source': ref('official', p['crops'][0][0], f"Subject Module – {p['title']}"),
                'questions': [{'id': f"{pre}-OFF-{p['id']}-{q['n']}", 'module': 'ga', 'section': 'GA', 'type': q['qtype'],
                               'topic': p['topic'], 'difficulty': 'Medium',
                               'stemImages': [crop('official', pg, b, dpi=150, pad=0) for pg, b in q['stem']],
                               'optionImages': [[crop('official', pg, b, dpi=150, pad=0) for pg, b in o] for o in q['opts']],
                               'options': ['a', 'b', 'c', 'd'], 'correctAnswer': q['ans'],
                               'explanation': q['expl'] + f" (Official solution: page {p['sol_page']}.)",
                               'sourceReference': ref('official', q['stem'][0][0], f"{p['title']} – Question {q['n']}")} for q in qs]}
    actual_ga = [ga_off_passage(offga[0], trim=3, pre='A')] + [ga_off_passage(p, pre='A') for p in offga[1:]]
    prac = ga.collect()
    TOPIC = {1: 'Mathematics', 2: 'Mathematics', 3: 'Mathematics', 4: 'Computational Sciences', 5: 'Computational Sciences',
             6: 'Computational Sciences', 7: 'Physics', 8: 'Physics', 9: 'Chemistry', 10: 'Biology', 11: 'Engineering',
             12: 'Engineering', 13: 'Engineering', 14: 'Business Administration', 15: 'Business Administration',
             16: 'Economics', 17: 'Economics', 18: 'Statistics', 19: 'Social Sciences', 20: 'Humanities'}
    def qtype(stem):
        s = re.sub('<[^>]+>', '', stem)
        if re.search(r'\d', s) and re.search(r'(How (high|large|much|many)|What (is|mass|profit|volume|velocity|distance)|Which (current|force|stress|data rate|sampling interval|decimal|absolute)|dimension|determinant|inverse|probability|ways|solution is correct)', s): return 'calculation'
        if re.search(r'What happens|What (effect|is the consequence|follows)|How (does|do)|is expected', s): return 'transfer / effect'
        return 'concept / definition'
    practice_ga = [{'id': f"PR-{p['n']:02d}", 'title': p['title'], 'topic': TOPIC[p['n']], 'format': 'text + reference table',
                    'images': [], 'html': p['html'], 'source': ref('gaprac', p['page'], f"Exercise {p['n']}"),
                    'questions': [{'id': f"PR-{p['n']:02d}-{q['n']}", 'module': 'ga', 'section': 'GA', 'type': qtype(q['stem']),
                                   'topic': TOPIC[p['n']], 'difficulty': 'Medium', 'question': q['stem'], 'options': q['opts'],
                                   'correctAnswer': q['ans'], 'explanation': ga_expl.E[q['n']],
                                   'sourceReference': ref('gaprac', q['page'], f"Exercise {p['n']} – Question {q['n']}")}
                                  for q in p['questions']]} for p in prac]
    practice_ga = [ga_off_passage(p) for p in offga] + practice_ga

    bank = {'built': '2026-09-25', 'assets': ASSETS,
            'actual': {'core': actual, 'ga': actual_ga}, 'practice': {'core': practice_core, 'ga': practice_ga},
            'qc': {'fs_verified': len(fsi), 'fs_rejected': len(fsrej), 'ls_verified': len(lsi), 'ls_rejected': len(lsrej),
                   'me_verified': len(mei), 'me_rejected': len(merej),
                   'rejects': {'fs': [f"{r['src']} Q{r['n']}: {r['err']}" for r in fsrej],
                               'ls': [f'{a} Q{b}: {c}' for a, b, c in lsrej], 'me': [f'{a} Q{b}: {c}' for a, b, c in merej]}}}
    out = os.path.join(os.path.dirname(__file__), 'bank.json')
    json.dump(bank, open(out, 'w', encoding='utf-8'), ensure_ascii=False)
    print('assets', len(ASSETS), 'bank MB', round(os.path.getsize(out) / 1e6, 2))
    print('actual', {k: len(v) for k, v in actual.items()}, 'ga', [len(p['questions']) for p in actual_ga])
    print('practice core', len(practice_core), [(t, sum(q['section'] == t for q in practice_core)) for t in ('FS', 'LS', 'ME')],
          [(d, sum(q['difficulty'] == d for q in practice_core)) for d in rank])
    print('practice ga passages', len(practice_ga), sum(len(p['questions']) for p in practice_ga))
    for k, v in actual.items(): print(' actual', k, [q['difficulty'][0] for q in v], sorted({q['sourceReference']['document'][:14] for q in v}))


if __name__ == '__main__':
    main()
