"""Figure Sequences (vector sources): find grids, extract elements, fit movement/rotation rules,
verify the answer key, write per-question explanations, compute crop boxes."""
import re, math, itertools
import pymupdf
from common import SRC, norm

COLS = 'αβγδεζη'


# ---------------- geometry extraction ----------------
def _segs(page):
    out = []
    for d in page.get_drawings():
        for it in d['items']:
            if it[0] == 'l':
                a, b = it[1], it[2]
                if abs(a.y - b.y) < .8 or abs(a.x - b.x) < .8:
                    out.append((min(a.x, b.x), min(a.y, b.y), max(a.x, b.x), max(a.y, b.y)))
            elif it[0] == 're':
                r = it[1]
                if r.width < 1.6 or r.height < 1.6: out.append((r.x0, r.y0, r.x1, r.y1))
                elif d.get('color') is not None and not d.get('fill'):  # stroked frame -> 4 edges
                    out += [(r.x0, r.y0, r.x1, r.y0), (r.x0, r.y1, r.x1, r.y1), (r.x0, r.y0, r.x0, r.y1), (r.x1, r.y0, r.x1, r.y1)]
    return out


def _cluster(vals, tol=2.0):
    out = []
    for v, ln in sorted(vals):
        if not out or v - out[-1][-1][0] > tol: out.append([(v, ln)])
        else: out[-1].append((v, ln))
    return [(sum(p for p, _ in c) / len(c), sum(l for _, l in c)) for c in out]


def find_grids(page):
    """Return list of grids: dict(bbox, xs, ys, n). Uses long horizontal/vertical strokes."""
    segs = _segs(page)
    H = [s for s in segs if s[3] - s[1] < 1.6 and s[2] - s[0] > 20]
    V = [s for s in segs if s[2] - s[0] < 1.6 and s[3] - s[1] > 20]
    # group verticals by (y-span) and horizontals by (x-span) into candidate boxes
    boxes = {}
    for h in H:
        key = (round(h[0] / 3), round(h[2] / 3))
        boxes.setdefault(key, []).append(h)
    grids = []
    for (_, _), hs in boxes.items():
        x0 = min(h[0] for h in hs); x1 = max(h[2] for h in hs)
        # split horizontals of this x-span into vertically contiguous groups
        ys = sorted({round(h[1], 1) for h in hs})
        groups, cur = [], [ys[0]]
        for y in ys[1:]:
            if y - cur[-1] < (x1 - x0) * 0.4: cur.append(y)
            else: groups.append(cur); cur = [y]
        groups.append(cur)
        for g in groups:
            if len(g) < 4: continue
            y0, y1 = g[0], g[-1]
            if abs((y1 - y0) - (x1 - x0)) > 0.15 * (x1 - x0): continue  # grids are square
            vs = [v for v in V if abs(v[1] - y0) < 3 and abs(v[3] - y1) < 3 and x0 - 2 < v[0] < x1 + 2]
            xs = sorted({round(v[0], 1) for v in vs})
            xs = [c for c, _ in _cluster([(x, 1) for x in xs])]
            yy = [c for c, _ in _cluster([(y, 1) for y in g])]
            if len(xs) == len(yy) >= 4:
                grids.append({'bbox': pymupdf.Rect(x0, y0, x1, y1), 'xs': xs, 'ys': yy, 'n': len(xs) - 1})
    # de-duplicate
    out = []
    for g in sorted(grids, key=lambda g: (g['bbox'].y0, g['bbox'].x0)):
        if not any(abs(g['bbox'].x0 - o['bbox'].x0) < 3 and abs(g['bbox'].y0 - o['bbox'].y0) < 3 for o in out): out.append(g)
    return out


def _pts(items):
    p = []
    for it in items:
        if it[0] == 'l': p += [it[1], it[2]]
        elif it[0] == 'c': p += [it[1], it[2], it[3], it[4]]
        elif it[0] == 're': r = it[1]; p += [r.tl, r.tr, r.br, r.bl]
        elif it[0] == 'qu': q = it[1]; p += [q.ul, q.ur, q.lr, q.ll]
    return p


def _kind(items):
    ks = [it[0] for it in items]
    if all(k == 'c' for k in ks): return 'circle'
    if ks == ['re']: return 'square'
    if 'c' in ks: return 'pac-man'
    n = len(ks)
    if n == 3: return 'triangle'
    if n == 4:
        pts = _pts(items)
        if len({round(p.x) for p in pts}) <= 3 and len({round(p.y) for p in pts}) <= 3: return 'diamond'
        if all(abs(it[1].x - it[2].x) < .5 or abs(it[1].y - it[2].y) < .5 for it in items): return 'square'
        return 'kite'
    return {5: 'pentagon', 6: 'L-shape', 7: 'arrow', 8: 'T-shape', 10: 'star'}.get(n, f'{n}-gon')


COLORS = {'red': (0.8, 0.2, 0.2), 'orange': (0.9, 0.5, 0.15), 'yellow': (0.88, 0.7, 0.0), 'green': (0.2, 0.7, 0.3),
          'teal': (0.1, 0.6, 0.55), 'blue': (0.2, 0.4, 0.8), 'purple': (0.55, 0.3, 0.65), 'pink': (0.85, 0.2, 0.45),
          'navy': (0.17, 0.24, 0.31), 'brown': (0.4, 0.25, 0.2), 'indigo': (0.3, 0.35, 0.75)}


def cname(rgb):
    return min(COLORS, key=lambda k: sum((a - b) ** 2 for a, b in zip(COLORS[k], rgb)))


def elements(page, grid):
    """Elements inside a grid: [{key, color, kind, cell(c,r), pts(rel. to cell centre, in cell units)}]"""
    bb = grid['bbox']; n = grid['n']; cw = bb.width / n
    raw = []
    for d in page.get_drawings():
        f = d.get('fill')
        if not f: continue
        r = d['rect']
        c = pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
        if not bb.contains(c) or r.width > cw * .95: continue
        sat = max(f) - min(f)
        if sat < .08 and max(f) > .85: continue  # white/grey backgrounds
        raw.append({'rgb': tuple(f), 'rect': r, 'items': d['items'], 'c': c})
    big = [x for x in raw if x['rect'].width * x['rect'].height > (cw * .22) ** 2]
    small = [x for x in raw if x not in big]
    out = []
    for x in big:
        col = min(n - 1, int((x['c'].x - bb.x0) / cw)); row = min(n - 1, int((x['c'].y - bb.y0) / cw))
        cc = pymupdf.Point(bb.x0 + (col + .5) * cw, bb.y0 + (row + .5) * cw)
        pts = [((p.x - cc.x) / cw, (p.y - cc.y) / cw) for p in _pts(x['items'])]
        out.append({'rgb': x['rgb'], 'color': cname(x['rgb']), 'kind': _kind(x['items']), 'cell': (col, row),
                    'pts': pts, 'cc': cc, 'marker': None})
    for m in small:  # orientation markers -> attach to nearest element
        if not out: break
        e = min(out, key=lambda e: (e['cc'].x - m['c'].x) ** 2 + (e['cc'].y - m['c'].y) ** 2)
        e['marker'] = ((m['c'].x - e['cc'].x) / cw, (m['c'].y - e['cc'].y) / cw)
        e['pts'] = e['pts'] + [e['marker']] * 3  # weight marker so rotation must move it
    for e in out: e['key'] = (e['color'], e['kind'])
    return out


# ---------------- rules ----------------
def rot(pts, deg):
    t = math.radians(deg); c, s = math.cos(t), math.sin(t)
    return [(x * c - y * s, x * s + y * c) for x, y in pts]  # screen coords: +deg = clockwise


def same_shape(a, b, tol=.07):
    if len(a) != len(b): return False
    return all(min((x - u) ** 2 + (y - v) ** 2 for u, v in b) < tol ** 2 for x, y in a) and \
           all(min((x - u) ** 2 + (y - v) ** 2 for u, v in a) < tol ** 2 for x, y in b)


def step_bounce(p, v, n):
    x, y = p[0] + v[0], p[1] + v[1]; vx, vy = v
    if x < 0: x, vx = -x, -vx
    if x > n - 1: x, vx = 2 * (n - 1) - x, -vx
    if y < 0: y, vy = -y, -vy
    if y > n - 1: y, vy = 2 * (n - 1) - y, -vy
    return (x, y), (vx, vy)


def border_cells(n):
    top = [(i, 0) for i in range(n)]; right = [(n - 1, i) for i in range(1, n)]
    bottom = [(i, n - 1) for i in range(n - 2, -1, -1)]; left = [(0, i) for i in range(n - 2, 0, -1)]
    return top + right + bottom + left  # clockwise


DIRN = {(1, 0): 'right', (-1, 0): 'left', (0, 1): 'down', (0, -1): 'up', (1, 1): 'down-right', (-1, 1): 'down-left',
        (1, -1): 'up-right', (-1, -1): 'up-left'}


def motion_models(n):
    """Yield (description, simulate(p1, k) -> position at frame k (0-based))."""
    yield ('stays fixed in the same cell', lambda p, k: p)
    for v in [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx, dy) != (0, 0)]:
        for sp in (1, 2):
            def sim(p, k, v=v, sp=sp):
                vv = v
                for _ in range(k):
                    for _ in range(sp): p, vv = step_bounce(p, vv, n)
                return p
            kind = 'diagonally' if v[0] and v[1] else ('horizontally' if v[0] else 'vertically')
            yield (f'moves {kind} {sp} cell{"s" if sp > 1 else ""} per frame (starting {DIRN[v]}) and bounces off the border', sim)
        def sim_acc(p, k, v=v):
            vv = v
            for j in range(k):
                for _ in range(j + 1): p, vv = step_bounce(p, vv, n)
            return p
        yield (f'moves {DIRN[v]} by x+1 cells (1, 2, 3 …) per frame, bouncing off the border', sim_acc)
    B = border_cells(n)
    for dirn, s in (('clockwise', 1), ('counter-clockwise', -1)):
        for sp in (1, 2, 3):
            def simb(p, k, s=s, sp=sp):
                return B[(B.index(p) + s * sp * k) % len(B)] if p in B else None
            yield (f'moves {dirn} along the outer border, {sp} cell{"s" if sp > 1 else ""} per frame', simb)
        def simba(p, k, s=s):
            return B[(B.index(p) + s * k * (k + 1) // 2) % len(B)] if p in B else None
        yield (f'moves {dirn} along the outer border by x+1 cells (1, 2, 3 …) per frame', simba)


def fit_motion(ps, n):
    sg = lambda v: (v > 0) - (v < 0)
    first = DIRN.get((sg(ps[1][0] - ps[0][0]), sg(ps[1][1] - ps[0][1])))
    fits = _fit_motion(ps, n)
    return sorted(fits, key=lambda f: 0 if (first and f'starting {first})' in f[0]) or f[0].startswith('stays') else 1)


def _fit_motion(ps, n):
    fits = []
    for desc, sim in motion_models(n):
        try:
            if all(sim(ps[0], k) == ps[k] for k in range(len(ps))): fits.append((desc, sim(ps[0], 4), sim(ps[0], 5)))
        except Exception: pass
    return fits


def fit_rotation(shapes):
    """shapes: list of point lists for frames 1..4. Return list of (desc, deltas-fn) fits -> predicted shapes 5,6."""
    fits = []
    cands = list(range(0, 360, 45))
    for d in cands:  # constant rotation
        if all(same_shape(rot(shapes[k], d), shapes[k + 1]) for k in range(3)):
            fits.append((d, 'const', rot(shapes[3], d), rot(shapes[3], 2 * d)))
    for d in cands[1:]:  # x+1 rotation: d, 2d, 3d, ...
        if all(same_shape(rot(shapes[k], d * (k + 1)), shapes[k + 1]) for k in range(3)):
            fits.append((d, 'acc', rot(shapes[3], 4 * d), rot(rot(shapes[3], 4 * d), 5 * d)))
    return fits


def rot_desc(d, mode):
    if d == 0: return 'keeps its orientation'
    cw = d if d <= 180 else 360 - d
    way = 'clockwise' if d <= 180 else 'anticlockwise'
    if d == 180: way = ''
    s = f'turns {cw}° {way}'.strip()
    return s + (' more each frame (x+1: 1×, 2×, 3× …)' if mode == 'acc' else ' every frame')


def cellname(c): return f'{COLS[c[0]]}{c[1] + 1}'


def analyse(seq, opts5, opts6, n):
    """seq: 4 element lists; opts: 3 element lists each. Returns (ans5, ans6, rules, why_wrong) or raises."""
    keys = [sorted(e['key'] for e in f) for f in seq]
    if any(k != keys[0] for k in keys) or len(set(keys[0])) != len(keys[0]):
        raise ValueError('element identity not trackable')
    rules, pred5, pred6 = [], {}, {}
    for key in keys[0]:
        es = [[e for e in f if e['key'] == key][0] for f in seq]
        mfits = fit_motion([e['cell'] for e in es], n)
        rfits = fit_rotation([e['pts'] for e in es])
        if not mfits: raise ValueError(f'no motion rule for {key}')
        if not rfits: raise ValueError(f'no rotation rule for {key}')
        pred5[key] = (mfits[0][1], [r[2] for r in rfits]); pred6[key] = (mfits[0][2], [r[3] for r in rfits])
        mdesc = mfits[0][0]
        rdesc = rot_desc(rfits[0][0], rfits[0][1]) if len({r[0] for r in rfits}) == 1 or all(r[0] == 0 for r in rfits) else None
        sym = len(rfits) > 1
        rules.append({'key': key, 'motion': mdesc, 'rot': None if sym and rfits[0][0] == 0 else rdesc, 'cells': [e['cell'] for e in es],
                      'p5': mfits[0][1], 'p6': mfits[0][2], 'marker': es[0]['marker'] is not None})

    def match(opt, pred):
        if sorted(e['key'] for e in opt) != sorted(pred): return ['has different elements']
        errs = []
        for key, (cell, shapes) in pred.items():
            e = [x for x in opt if x['key'] == key][0]
            if e['cell'] != cell: errs.append(f'the {key[0]} {key[1]} is in {cellname(e["cell"])} instead of {cellname(cell)}')
            elif not any(same_shape(e['pts'], s) for s in shapes): errs.append(f'the {key[0]} {key[1]} is in the right cell but wrongly rotated')
        return errs
    r5 = [match(o, pred5) for o in opts5]; r6 = [match(o, pred6) for o in opts6]
    ok5 = [i for i, e in enumerate(r5) if not e]; ok6 = [i for i, e in enumerate(r6) if not e]
    if len(ok5) != 1 or len(ok6) != 1: raise ValueError(f'options matching prediction: {ok5} {ok6}')
    return ok5[0], ok6[0], rules, (r5, r6)


def explain(rules, ans5, ans6, why):
    L = 'ABC'
    lines = []
    for r in rules:
        k = f'The {r["key"][0]} {r["key"][1]}'
        path = ' → '.join(cellname(c) for c in r['cells'])
        s = f'{k} {r["motion"]} ({path}, so Grid 5: {cellname(r["p5"])}, Grid 6: {cellname(r["p6"])})'
        if r['rot'] and 'keeps' not in r['rot']:
            s += f'; it also {r["rot"]}' + (' (read the small orientation marker)' if r['marker'] else '')
        elif r['rot']: s += '; its orientation never changes'
        lines.append(s + '.')
    fixed = [r for r in rules if r['motion'].startswith('stays')]
    head = 'Track each element separately. ' + ('Constant: ' + ', '.join(f'the {r["key"][0]} {r["key"][1]}' for r in fixed) + ' never moves (distractor). ' if fixed else '')
    wrong = []
    for label, errs, ans in (('Grid 5', why[0], ans5), ('Grid 6', why[1], ans6)):
        for i, e in enumerate(errs):
            if i != ans: wrong.append(f'{label} option {L[i]} is wrong: ' + '; '.join(e) + '.')
    return head + ' '.join(lines) + f' Therefore Grid 5 = {L[ans5]} and Grid 6 = {L[ans6]}. ' + ' '.join(wrong)


# ---------------- page layout -> questions ----------------
def layout(page):
    """Split grids on a page into questions: [(seq[4], qboxes[2], opts5[3], opts6[3])]."""
    gs = find_grids(page)
    qwords = [w for w in page.get_text('words') if w[4].strip() == '?']
    def has_q(g): return any(g['bbox'].contains(pymupdf.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)) for w in qwords)
    # question boxes may have no lattice -> also accept stroked squares containing '?'
    qb = [g for g in gs if has_q(g)]
    if len(qb) < 2:
        for d in page.get_drawings():
            r = d['rect']
            if 20 < r.width < 200 and abs(r.width - r.height) < 3 and any(r.contains(pymupdf.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)) for w in qwords):
                if not any(abs(r.x0 - g['bbox'].x0) < 3 and abs(r.y0 - g['bbox'].y0) < 3 for g in qb):
                    qb.append({'bbox': r, 'n': 0, 'xs': [], 'ys': []})
    qb.sort(key=lambda g: (round(g['bbox'].y0 / 20), g['bbox'].x0))
    grids = [g for g in gs if not has_q(g)]
    out = []
    rows = [qb[i:i + 2] for i in range(0, len(qb) - 1, 2)]
    for i, (q5, q6) in enumerate(rows):
        ytop = q5['bbox'].y0; ynext = rows[i + 1][0]['bbox'].y0 if i + 1 < len(rows) else 1e9
        seq = sorted([g for g in grids if abs(g['bbox'].y0 - ytop) < 25 and g['bbox'].x1 < q5['bbox'].x0 + 2], key=lambda g: g['bbox'].x0)[-4:]
        below = [g for g in grids if q5['bbox'].y1 - 2 < g['bbox'].y0 < ynext - 5]
        o5 = sorted([g for g in below if abs((g['bbox'].x0 + g['bbox'].x1) / 2 - (q5['bbox'].x0 + q5['bbox'].x1) / 2) < q5['bbox'].width * .6], key=lambda g: g['bbox'].y0)
        o6 = sorted([g for g in below if abs((g['bbox'].x0 + g['bbox'].x1) / 2 - (q6['bbox'].x0 + q6['bbox'].x1) / 2) < q6['bbox'].width * .6], key=lambda g: g['bbox'].y0)
        out.append((seq, (q5, q6), o5, o6))
    return out


def keys_from_text(tag):
    full = norm('\n'.join(p.get_text() for p in pymupdf.open(SRC[tag])))
    k = {}
    for m in re.finditer(r'Q(\d+)(?: \([^)]*\))?: (?:5th grid|Grid 5) = ([ABC]), (?:6th grid|Grid 6) = ([ABC])', full):
        k.setdefault(int(m.group(1)), ('ABC'.index(m.group(2)), 'ABC'.index(m.group(3))))
    return k


def diff_labels(tag):
    doc = pymupdf.open(SRC[tag]); lab = {}
    for i, p in enumerate(doc):
        for m in re.finditer(r'(?:Question (\d+) \(Difficulty: ([\w ]+?)[,)])|(?:\[ ([A-Z ]+?) \]\s+Question (\d+))', norm(p.get_text())):
            if m.group(1): lab[int(m.group(1))] = (m.group(2).strip(), i + 1)
            else: lab[int(m.group(4))] = (m.group(3).strip().title(), i + 1)
    return lab


def collect(tags=('doubt', 'fs50', 'fsadv', 'fsexp')):
    good, rej = [], []
    for tag in tags:
        doc = pymupdf.open(SRC[tag]); keys = keys_from_text(tag); labs = diff_labels(tag)
        # question numbering follows page order of '?' rows
        qn = 0
        for pno in range(doc.page_count):
            page = doc[pno]
            for seq, qbx, o5, o6 in layout(page):
                qn += 1
                rec = {'src': tag, 'n': qn, 'page': pno + 1}
                try:
                    if len(seq) != 4 or len(o5) != 3 or len(o6) != 3: raise ValueError(f'layout {len(seq)} {len(o5)} {len(o6)}')
                    n = seq[0]['n']
                    E = lambda g: elements(page, g)
                    a5, a6, rules, why = analyse([E(g) for g in seq], [E(g) for g in o5], [E(g) for g in o6], n)
                    key = keys.get(qn)
                    if key is None: raise ValueError('no key')
                    if key != (a5, a6): raise ValueError(f'key {key} != derived {(a5, a6)}')
                    rec.update(ans=(a5, a6), n_grid=n, diff=labs.get(qn, ('', 0))[0], rules=rules,
                               expl=explain(rules, a5, a6, why),
                               boxes={'seq': [tuple(g['bbox']) for g in seq], 'q': [tuple(g['bbox']) for g in qbx],
                                      'o5': [tuple(g['bbox']) for g in o5], 'o6': [tuple(g['bbox']) for g in o6]})
                    good.append(rec)
                except Exception as e:
                    rec['err'] = str(e); rej.append(rec)
    return good, rej


# ---------------- raster sources (Doubt Session images, official exercises) ----------------
class Raster:
    def __init__(s, pix):
        s.W, s.H, s.n, s.s = pix.width, pix.height, pix.n, pix.samples

    def px(s, x, y):
        i = (y * s.W + x) * s.n; return s.s[i], s.s[i + 1], s.s[i + 2]

    def grids(s, min_px=200):
        W, H = s.W, s.H
        line = bytearray(W * H)
        for y in range(H):
            for x in range(W):
                r, g, b = s.px(x, y)
                if max(r, g, b) < 238 and max(r, g, b) - min(r, g, b) < 25 and min(r, g, b) > 150: line[y * W + x] = 1
        seen = bytearray(W * H); comps = []
        for i in range(W * H):
            if line[i] and not seen[i]:
                st = [i]; seen[i] = 1; x0 = y0 = 10 ** 9; x1 = y1 = -1; cnt = 0
                while st:
                    j = st.pop(); cnt += 1; x, y = j % W, j // W
                    x0, x1, y0, y1 = min(x0, x), max(x1, x), min(y0, y), max(y1, y)
                    for k in (j + 1 if x + 1 < W else -1, j - 1 if x > 0 else -1, j + W if y + 1 < H else -1, j - W if y > 0 else -1):
                        if k >= 0 and line[k] and not seen[k]: seen[k] = 1; st.append(k)
                if cnt > min_px and abs((x1 - x0) - (y1 - y0)) < 6 and x1 - x0 > 40: comps.append((x0, y0, x1, y1))
        return comps

    def lattice_n(s, box):
        """Count vertical grid lines on many rows of the box; the most common count wins."""
        x0, y0, x1, y1 = box; counts = []
        for y in range(y0 + 2, y1 - 1, 3):
            runs, prev = 0, False
            for x in range(x0, x1 + 1):
                r, g, b = s.px(x, y); isl = max(r, g, b) < 238 and max(r, g, b) - min(r, g, b) < 25 and min(r, g, b) > 150
                if isl and not prev: runs += 1
                prev = isl
            counts.append(runs - 1)
        return max(set(counts), key=counts.count)

    def elements(s, box, n, allow_black=False):
        x0, y0, x1, y1 = box; cw = (x1 - x0) / n; pad = int(cw * .3)
        col, dark = {}, set()
        for y in range(max(0, y0 - pad), min(s.H, y1 + pad)):
            for x in range(max(0, x0 - pad), min(s.W, x1 + pad)):
                r, g, b = s.px(x, y); sat = max(r, g, b) - min(r, g, b)
                if sat >= 25:
                    c = min(n - 1, max(0, int((x - x0) / cw))); rw = min(n - 1, max(0, int((y - y0) / cw)))
                    col.setdefault((c, rw), []).append((x, y, r, g, b))
                elif max(r, g, b) < 150: dark.add((x, y))
        # dark connected components: big ones are black shapes, small ones are orientation markers
        comps, seen = [], set()
        for p in dark:
            if p in seen: continue
            st, comp = [p], []; seen.add(p)
            while st:
                q = st.pop(); comp.append(q)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        u = (q[0] + dx, q[1] + dy)
                        if u in dark and u not in seen: seen.add(u); st.append(u)
            comps.append(comp)
        markers = []
        for comp in comps:
            if len(comp) >= (cw * .2) ** 2:
                if not allow_black: continue
                cx = sum(p[0] for p in comp) / len(comp); cy = sum(p[1] for p in comp) / len(comp)
                c = min(n - 1, max(0, int((cx - x0) / cw))); rw = min(n - 1, max(0, int((cy - y0) / cw)))
                col.setdefault((c, rw), []).extend((x, y, 20, 20, 20) for x, y in comp)
            elif len(comp) >= 3: markers.append(comp)
        out = []
        q = 20 / cw
        for cell, P in col.items():
            if len(P) < (cw * .12) ** 2: continue
            cx, cy = x0 + (cell[0] + .5) * cw, y0 + (cell[1] + .5) * cw
            rgb = tuple(sum(p[k] for p in P) / len(P) / 255 for k in (2, 3, 4))
            mx0 = min(p[0] for p in P); mx1 = max(p[0] for p in P); my0 = min(p[1] for p in P); my1 = max(p[1] for p in P)
            out.append({'rgb': rgb, 'color': cname(rgb) if max(rgb) - min(rgb) > .1 else 'black', 'kind': '',
                        'fill': len(P) / max(1, (mx1 - mx0 + 1) * (my1 - my0 + 1)), 'cell': cell, 'c': (cx, cy),
                        'sc': (sum(p[0] for p in P) / len(P), sum(p[1] for p in P) / len(P)),
                        'mask': frozenset((round((p[0] - cx) * q), round((p[1] - cy) * q)) for p in P), 'mk': None})
        for comp in markers:
            mx = sum(p[0] for p in comp) / len(comp); my = sum(p[1] for p in comp) / len(comp)
            if not out: break
            e = min(out, key=lambda e: (e['sc'][0] - mx) ** 2 + (e['sc'][1] - my) ** 2)
            if math.dist(e['sc'], (mx, my)) < .75 * cw: e['mk'] = ((mx - e['c'][0]) / cw, (my - e['c'][1]) / cw)
        for e in out:
            e['pts'] = (e['mask'], e['mk']); e['marker'] = e['mk'] is not None; e['key'] = (e['color'], '')
        return out


def _rotmask(m, deg):
    t = math.radians(deg); c, s_ = math.cos(t), math.sin(t)
    return frozenset((round(x * c - y * s_), round(x * s_ + y * c)) for x, y in m)


def _iou(a, b):
    # tolerate 1-unit jitter from anti-aliasing / rounding
    grow = lambda m: {(x + dx, y + dy) for x, y in m for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
    ga, gb = grow(a), grow(b)
    hit_a = sum(p in gb for p in a) / len(a); hit_b = sum(p in ga for p in b) / len(b)
    return min(hit_a, hit_b)


_rot_vec, _same_vec = rot, same_shape


def rot(pts, deg):
    if isinstance(pts, tuple):
        m, k = pts
        return (_rotmask(m, deg), None if k is None else _rot_vec([k], deg)[0])
    return _rot_vec(pts, deg)


def same_shape(a, b, tol=.07):
    if isinstance(a, tuple):
        if (a[1] is None) != (b[1] is None): return False
        if a[1] is not None and math.dist(a[1], b[1]) > .15: return False
        return _iou(a[0], b[0]) > .85
    return _same_vec(a, b, tol)


def _fit(frames, rotf, samef):
    out = []
    for d in range(0, 360, 45):
        if all(samef(rotf(frames[k], d), frames[k + 1]) for k in range(3)):
            out.append((d, 'const', rotf(frames[3], d), rotf(frames[3], 2 * d)))
    for d in range(45, 360, 45):
        if all(samef(rotf(frames[k], d * (k + 1)), frames[k + 1]) for k in range(3)):
            out.append((d, 'acc', rotf(frames[3], 4 * d), rotf(rotf(frames[3], 4 * d), 5 * d)))
    return out


def fit_rotation(shapes):
    if not isinstance(shapes[0], tuple): return _fit(shapes, _rot_vec, _same_vec)
    fm = _fit([s[0] for s in shapes], _rotmask, lambda a, b: _iou(a, b) > .85)
    ks = [s[1] for s in shapes]
    if all(k is None for k in ks):
        return [(d, mo, (a, None), (b, None)) for d, mo, a, b in fm]
    if any(k is None for k in ks): return []
    fk = _fit([s[1] for s in shapes], lambda p, d: _rot_vec([p], d)[0], lambda a, b: math.dist(a, b) < .15)
    # report the marker's rotation (the shape silhouette itself may be symmetric/static)
    return [(dk, mk, (a, k5), (b, k6)) for _, _, a, b in fm for dk, mk, k5, k6 in fk]


def raster_questions(tag, pages):
    """Yield (page_no, Raster-analysed question) for sources where each question is one embedded image."""
    doc = pymupdf.open(SRC[tag])
    for pno in pages:
        page = doc[pno - 1]
        infos = [i for i in page.get_image_info(xrefs=True) if i['width'] > 1000]
        for info in infos:
            pix = pymupdf.Pixmap(doc, info['xref'])
            if pix.n > 3 or pix.alpha: pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            pix.shrink(1)
            yield pno, info, pix


def raster_layout(R):
    comps = R.grids()
    top_y = min(c[1] for c in comps)
    top = sorted([c for c in comps if abs(c[1] - top_y) < 15], key=lambda c: c[0])
    if len(top) != 6: raise ValueError(f'top row has {len(top)} boxes')
    seq, q5, q6 = top[:4], top[4], top[5]
    rest = [c for c in comps if c not in top]
    o5 = sorted([c for c in rest if abs(c[0] - q5[0]) < 15], key=lambda c: c[1])
    o6 = sorted([c for c in rest if abs(c[0] - q6[0]) < 15], key=lambda c: c[1])
    return seq, (q5, q6), o5, o6


# colour -> shape names, inferred from the Doubt Session answer key (intersection of listed element names per colour)
DOUBT_NAMES = {'navy': 'square', 'orange': 'diamond', 'purple': 'pentagon', 'red': 'circle', 'blue': 'star', 'teal': 'triangle'}
DOUBT_NAMES2 = {'brown': 'T-shape', 'pink': 'arrow', 'teal': 'kite', 'yellow': 'L-shape', 'indigo': 'pac-man'}


def collect_doubt():
    good, rej = [], []
    keys = keys_from_text('doubt'); labs = diff_labels('doubt')
    for pno, info, pix in raster_questions('doubt', range(2, 42)):
        qn = pno - 1; rec = {'src': 'doubt', 'n': qn, 'page': pno}
        try:
            R = Raster(pix); seq, qb, o5, o6 = raster_layout(R); n = R.lattice_n(seq[0])
            names = DOUBT_NAMES if qn <= 20 else DOUBT_NAMES2
            def E(g):
                es = R.elements(g, n)
                for e in es: e['kind'] = names.get(e['color'], 'shape'); e['key'] = (e['color'], e['kind'])
                return es
            a5, a6, rules, why = analyse([E(g) for g in seq], [E(g) for g in o5], [E(g) for g in o6], n)
            key = keys.get(qn)
            if key != (a5, a6): raise ValueError(f'key {key} != derived {(a5, a6)}')
            # boxes in page coordinates: image pixels (after shrink x2) -> page rect
            ib = pymupdf.Rect(info['bbox']); sx = ib.width / R.W; sy = ib.height / R.H
            P = lambda c: (ib.x0 + c[0] * sx, ib.y0 + c[1] * sy, ib.x0 + (c[2] + 1) * sx, ib.y0 + (c[3] + 1) * sy)
            rec.update(ans=(a5, a6), n_grid=n, diff=labs.get(qn, ('', 0))[0], rules=rules, expl=explain(rules, a5, a6, why),
                       boxes={'seq': [P(g) for g in seq], 'q': [P(g) for g in qb], 'o5': [P(g) for g in o5], 'o6': [P(g) for g in o6]})
            good.append(rec)
        except Exception as e:
            rec['err'] = str(e); rej.append(rec)
    return good, rej


_collect_vec = collect


def collect(tags=('doubt', 'fs50', 'fsadv', 'fsexp')):
    good, rej = _collect_vec(tuple(t for t in tags if t != 'doubt'))
    if 'doubt' in tags:
        g2, r2 = collect_doubt(); good += g2; rej += r2
    return good, rej



def layout_multi(R):
    """Sequence rows (>=4 same-size grids on one line) + option columns below each row."""
    comps = [c for c in R.grids(min_px=100)]
    gs = []
    for c in comps:
        n = R.lattice_n(c)
        if n < 3: continue
        if any(abs(c[0] - g[0]) < 6 and abs(c[1] - g[1]) < 6 for g, _ in gs): continue
        gs.append((c, n))
    rows = []
    for c, n in sorted(gs, key=lambda x: (x[0][1], x[0][0])):
        for r in rows:
            if abs(r[0][0][1] - c[1]) < 15: r.append((c, n)); break
        else: rows.append([(c, n)])
    seqrows = [sorted(r, key=lambda x: x[0][0]) for r in rows if len(r) >= 4]
    out = []
    for i, r in enumerate(seqrows):
        seq = r[:4]; ytop = seq[0][0][1]; ynext = seqrows[i + 1][0][0][1] if i + 1 < len(seqrows) else 10 ** 9
        opts = [g for g in gs if ytop + 20 < g[0][1] < ynext - 10 and g[0][0] > seq[-1][0][0] + 10]
        xs = sorted({o[0][0] for o in opts})
        cols = []
        for x in xs:
            if not cols or x - cols[-1][-1] > 15: cols.append([x])
            else: cols[-1].append(x)
        if len(cols) != 2: raise ValueError(f'{len(cols)} option columns')
        o5 = sorted([o for o in opts if abs(o[0][0] - cols[0][0]) < 16], key=lambda o: o[0][1])
        o6 = sorted([o for o in opts if abs(o[0][0] - cols[1][0]) < 16], key=lambda o: o[0][1])
        out.append(([g for g, _ in seq], [g for g, _ in o5], [g for g, _ in o6], seq[0][1]))
    return out


def collect_vecraster(tag, dpi=150):
    good, rej = [], []
    doc = pymupdf.open(SRC[tag]); keys = keys_from_text(tag); labs = diff_labels(tag)
    sc = dpi / 72; qn = 0
    for pno in range(doc.page_count):
        page = doc[pno]
        try: R = Raster(page.get_pixmap(dpi=dpi)); qs = layout_multi(R)
        except Exception as e: rej.append({'src': tag, 'n': -1, 'page': pno + 1, 'err': str(e)}); continue
        vec = [d for d in page.get_drawings() if d.get('fill') and max(d['fill']) - min(d['fill']) > .1]
        labels = [(w[1], int(nx[4])) for w, nx in zip(page.get_text('words'), page.get_text('words')[1:])
                  if w[4] == 'Question' and nx[4].isdigit()]
        for seq, o5, o6, n in qs:
            above = [l for l in labels if l[0] < seq[0][1] / sc]
            if not above: rej.append({'src': tag, 'n': -1, 'page': pno + 1, 'err': 'no label'}); continue
            qn = max(above)[1]; rec = {'src': tag, 'n': qn, 'page': pno + 1}
            try:
                if len(o5) != 3 or len(o6) != 3: raise ValueError(f'layout {len(o5)} {len(o6)}')
                def E(g):
                    es = R.elements(g, n)
                    for e in es:
                        px, py = e['sc']
                        hit = [d for d in vec if d['rect'].contains(pymupdf.Point(px / sc, py / sc))]
                        e['kind'] = _kind(hit[0]['items']) if hit else 'shape'; e['key'] = (e['color'], e['kind'])
                    return es
                a5, a6, rules, why = analyse([E(g) for g in seq], [E(g) for g in o5], [E(g) for g in o6], n)
                key = keys.get(qn)
                if key != (a5, a6): raise ValueError(f'key {key} != derived {(a5, a6)}')
                P = lambda c: (c[0] / sc, c[1] / sc, (c[2] + 1) / sc, (c[3] + 1) / sc)
                right = max(o[2] for o in o5 + o6)
                strip = (seq[0][0], min(g[1] for g in seq), right, max(g[3] for g in seq))
                rec.update(ans=(a5, a6), n_grid=n, diff=labs.get(qn, ('', 0))[0], rules=rules, expl=explain(rules, a5, a6, why),
                           boxes={'seq': [P(g) for g in seq], 'strip': P(strip), 'o5': [P(g) for g in o5], 'o6': [P(g) for g in o6]})
                good.append(rec)
            except Exception as e:
                rec['err'] = str(e); rej.append(rec)
    return good, rej


def collect(tags=('doubt', 'fs50', 'fsadv', 'fsexp')):
    good, rej = [], []
    for t in tags:
        g, r = collect_doubt() if t == 'doubt' else collect_vecraster(t)
        good += g; rej += r
    return good, rej


if __name__ == '__main__':
    import collections, sys
    tags = tuple(sys.argv[1:]) or ('doubt', 'fs50', 'fsadv', 'fsexp')
    good, rej = collect(tags)
    print('good', len(good), collections.Counter((g['src'], g['diff']) for g in good))
    print('rej', len(rej), collections.Counter(r['src'] for r in rej))
    for r in rej[:25]: print('  REJ', r['src'], r['n'], r['page'], r['err'])
    for g in good[:3]: print(g['src'], g['n'], g['diff'], g['ans'], '\n  ', g['expl'])
