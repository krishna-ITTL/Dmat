"""Latin Squares: locate 5x5 grids in source PDFs, read givens from text coordinates, solve, explain, crop."""
import re
import pymupdf
from common import SRC, norm

L = 'ABCDE'
COLS = 'αβγδε'


def segments(page):
    """All straight horizontal/vertical strokes as rects (lines, thin rects, and edges of cell rects)."""
    out = []
    for d in page.get_drawings():
        for it in d['items']:
            if it[0] == 'l':
                a, b = it[1], it[2]
                if abs(a.y - b.y) < .8 or abs(a.x - b.x) < .8:
                    out.append(pymupdf.Rect(min(a.x, b.x), min(a.y, b.y), max(a.x, b.x), max(a.y, b.y)))
            elif it[0] == 're':
                r = it[1]
                if r.width > 400 or r.height > 400: continue  # page backgrounds / bands
                if r.width < 1.6 or r.height < 1.6: out.append(pymupdf.Rect(r))
                elif 15 < r.width < 60 and 15 < r.height < 60:  # a cell rect: add its edges
                    out += [pymupdf.Rect(r.x0, r.y0, r.x1, r.y0), pymupdf.Rect(r.x0, r.y1, r.x1, r.y1),
                            pymupdf.Rect(r.x0, r.y0, r.x0, r.y1), pymupdf.Rect(r.x1, r.y0, r.x1, r.y1)]
                elif 150 < r.width < 300 and 150 < r.height < 300:  # outer frame
                    out += [pymupdf.Rect(r.x0, r.y0, r.x1, r.y0), pymupdf.Rect(r.x0, r.y1, r.x1, r.y1),
                            pymupdf.Rect(r.x0, r.y0, r.x0, r.y1), pymupdf.Rect(r.x1, r.y0, r.x1, r.y1)]
    return out


def grid_around(segs, pt):
    """Connected component of touching segments that encloses pt -> bbox."""
    tol = 2.5
    near = [s for s in segs]
    n = len(near); parent = list(range(n))
    def f(i):
        while parent[i] != i: parent[i] = parent[parent[i]]; i = parent[i]
        return i
    ex = [pymupdf.Rect(s.x0 - tol, s.y0 - tol, s.x1 + tol, s.y1 + tol) for s in near]
    for i in range(n):
        for j in range(i + 1, n):
            if ex[i].intersects(ex[j]): parent[f(i)] = f(j)
    comps = {}
    for i in range(n): comps.setdefault(f(i), []).append(near[i])
    best = None
    for c in comps.values():
        bb = pymupdf.Rect(min(s.x0 for s in c), min(s.y0 for s in c), max(s.x1 for s in c), max(s.y1 for s in c))
        if not (bb.contains(pt) and 80 < bb.width < 360 and 60 < bb.height < 360): continue
        xs = _cluster([(s.x0, s.height) for s in c if s.width < 1.6], bb.height)
        ys = _cluster([(s.y0, s.width) for s in c if s.height < 1.6], bb.width)
        if len(xs) == 6 and len(ys) == 6 and (best is None or bb.width < best[0].width): best = (bb, xs, ys)
    return best


def _cluster(v, span, tol=3):
    """Group line positions; keep only lines whose summed length covers most of the grid."""
    out = []
    for x, ln in sorted(v):
        if not out or x - out[-1][-1][0] > tol: out.append([(x, ln)])
        else: out[-1].append((x, ln))
    return [sum(p for p, _ in c) / len(c) for c in out if sum(l for _, l in c) >= .6 * span]


def read_grid(page, gb):
    bb, xs, ys = gb
    g = [[None] * 5 for _ in range(5)]; q = None
    for w in page.get_text('words'):
        t = w[4].strip()
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        if not (xs[0] < cx < xs[-1] and ys[0] < cy < ys[-1]): continue
        c = max(i for i in range(5) if xs[i] < cx); r = max(i for i in range(5) if ys[i] < cy)
        if t == '?': q = (r, c)
        elif t in L: g[r][c] = t
        elif t: return None, None  # numbers / other symbols -> not a dMAT A-E grid
    return g, q


# ---------- solving ----------
def completions_value(g, q, limit=200000):
    """Set of values the '?' cell takes over all valid completions."""
    cells = [(r, c) for r in range(5) for c in range(5) if not g[r][c] and (r, c) != q] + [q]
    vals, cnt = set(), [0]
    for v in L:
        grid = [row[:] for row in g]
        if all(grid[q[0]][k] != v for k in range(5)) and all(grid[k][q[1]] != v for k in range(5)):
            grid[q[0]][q[1]] = v
            cnt[0] = 0
            order = [x for x in cells if x != q]
            def bt2(i):
                cnt[0] += 1
                if cnt[0] > limit: raise RuntimeError('search limit')
                if i == len(order): return True
                r, c = order[i]
                for w in L:
                    if all(grid[r][k] != w for k in range(5)) and all(grid[k][c] != w for k in range(5)):
                        grid[r][c] = w
                        if bt2(i + 1): return True
                        grid[r][c] = None
                return False
            if bt2(0): vals.add(v)
    return vals


def nm(r, c): return f'{COLS[c]}{r+1}'


def deduce(g, q):
    """Human-style propagation (naked + hidden singles) with minimal dependency chains.
    Returns (answer, chain_of_steps_needed_for_q, rounds)."""
    grid = [row[:] for row in g]
    step_of = {}      # cell -> index into steps (deduced cells only)
    steps = []        # (cell, value, why, deps)

    def cost(cells):
        seen, st = set(), list(cells)
        while st:
            x = st.pop()
            if x in step_of and x not in seen: seen.add(x); st += steps[step_of[x]][3]
        return len(seen)

    def pick(cells):  # prefer given cells, then earliest deduced
        return min(cells, key=lambda x: (x in step_of, step_of.get(x, -1)))

    def singles():
        out = []
        for r in range(5):
            for c in range(5):
                if grid[r][c]: continue
                cs = [v for v in L if v not in grid[r] and all(grid[k][c] != v for k in range(5))]
                if len(cs) == 1:
                    deps = [pick([x for x in [(r, k) for k in range(5)] + [(k, c) for k in range(5)] if grid[x[0]][x[1]] == u])
                            for u in L if u != cs[0]]
                    seen_r = ', '.join(sorted(v for v in grid[r] if v)) or 'nothing'
                    seen_c = ', '.join(sorted(grid[k][c] for k in range(5) if grid[k][c])) or 'nothing'
                    out.append(((r, c), cs[0], f'row {r+1} shows {seen_r} and column {COLS[c]} shows {seen_c} → only {cs[0]} is missing from both', deps))
        for v in L:
            for r in range(5):
                if v in grid[r]: continue
                spots = [c for c in range(5) if not grid[r][c] and all(grid[k][c] != v for k in range(5))]
                if len(spots) == 1:
                    c = spots[0]; others = [cc for cc in range(5) if cc != c and not grid[r][cc]]
                    deps = [pick([(k, cc) for k in range(5) if grid[k][cc] == v]) for cc in others] +                            [(r, cc) for cc in range(5) if grid[r][cc]]
                    why = (f'row {r+1} still needs {v}, and its other empty cells ({", ".join(nm(r, cc) for cc in others) or "none"}) '
                           f'already have {v} in their columns → {v} must go in {nm(r, c)}')
                    out.append(((r, c), v, why, deps))
            for c in range(5):
                if any(grid[k][c] == v for k in range(5)): continue
                spots = [r for r in range(5) if not grid[r][c] and v not in grid[r]]
                if len(spots) == 1:
                    r = spots[0]; others = [rr for rr in range(5) if rr != r and not grid[rr][c]]
                    deps = [pick([(rr, k) for k in range(5) if grid[rr][k] == v]) for rr in others] +                            [(rr, c) for rr in range(5) if grid[rr][c]]
                    why = (f'column {COLS[c]} still needs {v}, and its other empty cells ({", ".join(nm(rr, c) for rr in others) or "none"}) '
                           f'already have {v} in their rows → {v} must go in {nm(r, c)}')
                    out.append(((r, c), v, why, deps))
        return out

    rounds = 0
    while True:
        rounds += 1
        found = singles()
        if not found: return None, [], rounds
        hit = [x for x in found if x[0] == q]
        if hit:
            best = min(hit, key=lambda x: (cost(x[3]), len(x[2])))
            steps.append(best); step_of[q] = len(steps) - 1
            break
        for cell, v, why, deps in sorted(found, key=lambda x: cost(x[3])):
            if grid[cell[0]][cell[1]]: continue
            if v in grid[cell[0]] or any(grid[k][cell[1]] == v for k in range(5)): continue
            grid[cell[0]][cell[1]] = v; steps.append((cell, v, why, deps)); step_of[cell] = len(steps) - 1
    need, st = set(), [q]
    while st:
        x = st.pop()
        if x in step_of and x not in need: need.add(x); st += steps[step_of[x]][3]
    chain = [s for s in steps if s[0] in need]
    return chain[-1][1], chain, rounds


def explanation(g, q, chain):
    r, c = q
    row = sorted(v for v in g[r] if v); col = sorted(g[k][c] for k in range(5) if g[k][c])
    parts = [f'The "?" is cell {nm(r, c)} (column {COLS[c]}, row {r+1}). '
             f'Row constraint: row {r+1} shows {", ".join(row) or "no letters"}. '
             f'Column constraint: column {COLS[c]} shows {", ".join(col) or "no letters"}.']
    helpers = [s for s in chain if s[0] != q]
    if helpers:
        parts.append(f'That is not enough on its own, so fill {len(helpers)} helper cell{"s" if len(helpers) > 1 else ""} mentally first:')
        for i, (cell, v, why, _) in enumerate(helpers, 1):
            parts.append(f'({i}) {nm(*cell)} = {v}: {why}.')
    last = chain[-1]
    parts.append(f'Finally {nm(r, c)}: {last[2]}. Answer: {last[1]}.')
    return ' '.join(parts)


def rate(chain):
    h = len(chain) - 1
    return 'Easy' if h == 0 else 'Medium' if h <= 2 else 'Hard'


# ---------- sources ----------
def scan(tag, pages=None, key_fn=None, label_fn=None):
    doc = pymupdf.open(SRC[tag]); out = []
    for pno in (pages or range(1, doc.page_count + 1)):
        page = doc[pno - 1]
        qs = [w for w in page.get_text('words') if w[4].strip() == '?']
        if not qs: continue
        segs = segments(page)
        for w in qs:
            pt = pymupdf.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)
            bb = grid_around(segs, pt)
            if not bb: continue
            g, q = read_grid(page, bb)
            if g is None or q is None: continue
            out.append({'src': tag, 'page': pno, 'bbox': tuple(bb[0]), 'grid': g, 'q': q,
                        'label': label_fn(page, bb[0]) if label_fn else '', 'key': None})
    return out


def header_above(page, bb, pat):
    best = None
    for b in page.get_text('blocks'):
        if b[3] <= bb[1] + 2 and re.search(pat, norm(b[4])):
            if best is None or b[3] > best[3]: best = b
    return norm(best[4]).replace('\n', ' ').strip() if best else ''


def collect():
    items = []
    # official exercises pp.25–27 (solution pages repeat the grids -> excluded)
    offkeys = {1: 'C', 2: 'D', 3: 'B', 4: 'D', 5: 'D', 6: 'E'}
    for it in scan('official', [25, 26, 27], label_fn=lambda p, b: header_above(p, b, r'Exercise \d')):
        m = re.search(r'Exercise (\d) - Difficulty: (\w+)', it['label']); n = int(m.group(1))
        it.update(n=n, diff=m.group(2), key=offkeys[n]); items.append(it)
    # masters: "Question N: Latin Square Design"; key "Explanation for Question N / Correct Answer: X"
    doc = pymupdf.open(SRC['masters'])
    full = norm('\n'.join(p.get_text() for p in doc))
    mk = {int(a): b for a, b in re.findall(r'Explanation for Question (\d+)\nCorrect Answer: ([A-E])\n', full)}
    for it in scan('masters', range(2, 102), label_fn=lambda p, b: header_above(p, b, r'Question \d+: Latin')):
        m = re.search(r'Question (\d+)', it['label'])
        if m: it.update(n=int(m.group(1)), diff='', key=mk.get(int(m.group(1)))); items.append(it)
    # class decks: labels "Question N — Difficulty: X", worked examples, recap examples
    for tag in ('ls1', 'ls2', 'ls3'):
        for it in scan(tag, label_fn=lambda p, b: header_above(p, b, r'Question \d+|Example')):
            m = re.search(r'Question (\d+)\s*[-—–]+\s*Difficulty:\s*(\w+)', it['label'])
            if m: it.update(n=int(m.group(1)), diff=m.group(2)); items.append(it)
    # core150 (no key)
    for it in scan('core150', label_fn=lambda p, b: header_above(p, b, r'Question \d+ of 150')):
        m = re.search(r'Question (\d+) of 150', it['label'])
        if m: it.update(n=int(m.group(1)), diff=''); items.append(it)
    good, rej = [], []
    for it in items:
        try: vals = completions_value(it['grid'], it['q'])
        except RuntimeError: rej.append((it['src'], it['n'], 'search limit')); continue
        if len(vals) != 1: rej.append((it['src'], it['n'], f'ambiguous {vals}')); continue
        ans = vals.pop()
        if it.get('key') and it['key'] != ans: rej.append((it['src'], it['n'], f'key {it["key"]} != solver {ans}')); continue
        a2, chain, _ = deduce(it['grid'], it['q'])
        if a2 != ans: rej.append((it['src'], it['n'], 'not solvable by singles')); continue
        it.update(ans=ans, chain_len=len(chain), rated=rate(chain), expl=explanation(it['grid'], it['q'], chain))
        good.append(it)
    return good, rej


if __name__ == '__main__':
    import collections
    good, rej = collect()
    print('good', len(good), collections.Counter(g['src'] for g in good))
    print('rated', collections.Counter((g['src'], g['rated']) for g in good))
    print('rej', len(rej)); [print('  ', r) for r in rej[:30]]
    for g in good:
        if g['src'] == 'official': print(g['n'], g['diff'], g['rated'], g['ans'], g['expl'][:400])
    o = {g['n']: g['ans'] for g in good if g['src'] == 'official'}
    assert o == {1: 'C', 2: 'D', 3: 'B', 4: 'D', 5: 'D', 6: 'E'}, o
    print('OK')
