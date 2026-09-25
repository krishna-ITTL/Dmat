"""Mathematical Equations: parse systems from source PDFs, solve exactly, verify keys, write explanations."""
import re, itertools
from fractions import Fraction as F
import pymupdf
from common import SRC, norm

EQ_RE = re.compile(r'^[A-Z0-9 +\-×÷=()/]+$')


class Lin:
    """Linear form: {var: coef, '': const} with Fraction coefficients."""
    def __init__(s, d=None): s.d = {k: v for k, v in (d or {}).items() if v != 0}
    @staticmethod
    def c(v): return Lin({'': F(v)})
    def __add__(s, o): o = o if isinstance(o, Lin) else Lin.c(o); r = dict(s.d); [r.__setitem__(k, r.get(k, 0) + v) for k, v in o.d.items()]; return Lin(r)
    __radd__ = __add__
    def __neg__(s): return Lin({k: -v for k, v in s.d.items()})
    def __sub__(s, o): return s + (-(o if isinstance(o, Lin) else Lin.c(o)))
    def __rsub__(s, o): return Lin.c(o) - s
    def __mul__(s, o):
        if isinstance(o, Lin):
            if set(o.d) <= {''}: o = o.d.get('', F(0))
            elif set(s.d) <= {''}: return o * s.d.get('', F(0))
            else: raise ValueError('non-linear')
        return Lin({k: v * F(o) for k, v in s.d.items()})
    __rmul__ = __mul__
    def __truediv__(s, o):
        if isinstance(o, Lin):
            assert set(o.d) <= {''}, 'division by variable'
            o = o.d.get('', F(0))
        return Lin({k: v / F(o) for k, v in s.d.items()})
    def vars(s): return sorted(k for k in s.d if k)
    def sub(s, env):  # substitute var -> Lin
        r = Lin.c(s.d.get('', 0))
        for k, v in s.d.items():
            if k: r = r + (env[k] * v if k in env else Lin({k: v}))
        return r


def parse_eq(line):
    t = norm(line).replace('×', '*').replace('÷', '/')
    lhs, rhs = t.split('=')
    env = {v: Lin({v: F(1)}) for v in 'ABCDEFGH'}
    ev = lambda x: eval(re.sub(r'(\d+)', r'Lin.c(\1)', x), {'Lin': Lin}, env)
    return ev(lhs) - ev(rhs)  # == 0


def solve(eqs):
    """Gaussian elimination over Fractions. Returns dict or None if not unique."""
    vs = sorted({v for e in eqs for v in e.vars()})
    rows = [[e.d.get(v, F(0)) for v in vs] + [-e.d.get('', F(0))] for e in eqs]
    n, r = len(vs), 0
    for c in range(n):
        p = next((i for i in range(r, len(rows)) if rows[i][c] != 0), None)
        if p is None: return None
        rows[r], rows[p] = rows[p], rows[r]
        rows[r] = [x / rows[r][c] for x in rows[r]]
        for i in range(len(rows)):
            if i != r and rows[i][c] != 0: rows[i] = [a - rows[i][c] * b for a, b in zip(rows[i], rows[r])]
        r += 1
    if any(all(x == 0 for x in row[:-1]) and row[-1] != 0 for row in rows): return None
    sol = {v: rows[i][-1] for i, v in enumerate(vs)}
    return sol


def fmt_lin(l, piv):
    a, b = l.d.get(piv, F(0)), l.d.get('', F(0))
    fa = lambda x: str(int(x)) if x.denominator == 1 else f'{x.numerator}/{x.denominator}'
    parts = []
    t = piv if abs(a) == 1 else (f'{fa(abs(a))}{piv}' if abs(a).denominator == 1 else f'({fa(abs(a))})·{piv}')
    if a == 0: return fa(b)
    if a > 0: return t + (f' + {fa(b)}' if b > 0 else f' − {fa(-b)}' if b < 0 else '')
    return (f'{fa(b)} − {t}' if b else f'−{t}')


def explain(lines, eqs, sol):
    """Shortest reliable route: direct isolation / chain, else pivot substitution (master equation)."""
    vs = sorted(sol)
    known, steps = {}, []
    # 1) chain of directly solvable equations
    changed = True
    while changed:
        changed = False
        for i, e in enumerate(eqs):
            s = e.sub({k: Lin.c(v) for k, v in known.items()})
            if len(s.vars()) == 1:
                v = s.vars()[0]; val = -s.d.get('', 0) / s.d[v]
                if v not in known:
                    known[v] = val
                    steps.append(f'Equation {i+1} ({lines[i]}) has only one unknown once known values are inserted → {v} = {fmt(val)}.')
                    changed = True
    if len(known) == len(vs):
        return 'Method: direct isolation / chain. ' + ' '.join(steps)
    # 2) pivot: express other letters via the pivot, then substitute into the remaining equation
    best = None
    for piv in [v for v in vs if v not in known]:
        expr, used, st = {piv: Lin({piv: F(1)})}, set(), []
        base = {k: Lin.c(v) for k, v in known.items()}
        for _ in range(len(eqs)):
            for i, e in enumerate(eqs):
                if i in used: continue
                s = e.sub(base).sub(expr)
                unk = [v for v in s.vars() if v != piv]
                if len(unk) == 1:
                    u = unk[0]; ex = (-(s - Lin({u: s.d[u]}))) / s.d[u]
                    expr[u] = ex; used.add(i)
                    st.append(f'Eq {i+1} ({lines[i]}) → {u} = {fmt_lin(ex, piv)}')
        rest = [i for i in range(len(eqs)) if i not in used]
        cand = [(i, eqs[i].sub(base).sub(expr)) for i in rest]
        cand = [(i, s) for i, s in cand if s.vars() == [piv]]
        if not cand: continue
        i, s = cand[0]
        frac = any(v.denominator != 1 for ex in expr.values() for v in ex.d.values())
        occ = sum(piv in e.vars() for e in eqs)
        key = (frac, -occ, len(st))
        if best is None or key < best[0]: best = (key, piv, st, i, s)
    _, piv, st, i, s = best
    a, b = s.d[piv], s.d.get('', F(0))
    out = []
    if steps: out.append(' '.join(steps))
    out.append(f'Method: pivot substitution with pivot {piv}. Write the other letters in terms of {piv}: ' + '; '.join(st) + '.')
    if a < 0: a, b = -a, -b
    lhs = fmt_lin(Lin({piv: a}), piv)
    tail = '' if a == 1 else f' → {piv} = {fmt(sol[piv])}'
    out.append(f'Substitute everything into Eq {i+1} ({lines[i]}): {lhs} = {fmt(-b)}{tail}.')
    out.append('Back-substitute: ' + ', '.join(f'{v} = {fmt(sol[v])}' for v in vs if v != piv) + '.')
    return ' '.join(out)


def fmt(x): return str(int(x)) if x.denominator == 1 else str(x)


def verify(lines):
    eqs = [parse_eq(l) for l in lines]
    sol = solve(eqs)
    if sol is None: return None, 'no unique solution'
    if not all(x.denominator == 1 and 1 <= x <= 20 for x in sol.values()): return None, f'out of 1..20: {sol}'
    return (eqs, {k: int(v) for k, v in sol.items()}), None


# ---------- source parsers: yield (lines, key|None, difficulty_label, doc, page, label) ----------
def _eq_lines(block):
    out = []
    for l in block:
        l = norm(l).strip()
        if '=' in l and EQ_RE.match(l) and '?' not in l: out.append(l)
    return out


def _pages(path):
    d = pymupdf.open(path)
    return [(i + 1, p.get_text()) for i, p in enumerate(d)]


def parse_generic(path, header_re, stop_re, key_re=None):
    """Walk the text; each header starts a question; collect equation lines until stop_re."""
    items, cur = [], None
    for pg, txt in _pages(path):
        for line in txt.splitlines():
            m = header_re.search(norm(line))
            if m:
                if cur: items.append(cur)
                cur = {'n': int(m.group('n')), 'diff': (m.groupdict().get('d') or '').strip(), 'page': pg, 'raw': []}
                continue
            if cur is not None:
                if stop_re.search(norm(line)): items.append(cur); cur = None; continue
                cur['raw'].append(line)
    if cur: items.append(cur)
    for it in items: it['lines'] = _eq_lines(it['raw'])
    return items


def collect():
    """Return list of verified ME question dicts."""
    out, rejects = [], []

    def add(src, doc, it, diff, key=None):
        lines = it['lines']
        if len(lines) < 2: rejects.append((src, it['n'], 'no equations')); return
        res, err = verify(lines)
        if err: rejects.append((src, it['n'], err)); return
        eqs, sol = res
        if key and key != sol: rejects.append((src, it['n'], f'key mismatch {key} vs {sol}')); return
        out.append({'src': src, 'doc': doc, 'page': it['page'], 'n': it['n'], 'lines': lines, 'sol': sol,
                    'diff': diff, 'expl': explain(lines, eqs, {k: F(v) for k, v in sol.items()})})

    # official
    doc = SRC['official']
    txt = {pg: t for pg, t in _pages(doc)}
    body = norm(txt[18] + txt[19])
    for m in re.finditer(r'Exercise (\d) - Difficulty: (\w+)\s*\n(.*?)(?=Exercise \d|Core Module|$)', body, re.S):
        n = int(m.group(1)); lines = _eq_lines(m.group(3).splitlines())
        add('official', doc, {'n': n, 'page': 18 if n <= 5 else 19, 'lines': lines}, m.group(2))
    # c2/c3/c4 practice sets: key lines "Solution:  A = 14 · B = 5"
    for tag in ('c2', 'c3', 'c4'):
        doc = SRC[tag]
        its = parse_generic(doc, re.compile(r'^Question (?P<n>\d+)\s+—\s+\d unknowns\s+·\s+Difficulty: (?P<d>\w+)'),
                            re.compile(r'Space for explanation'))
        keys = {}
        full = norm('\n'.join(t for _, t in _pages(doc)))
        for m in re.finditer(r'Question (\d+)\s+\(\d unknowns, \w+\)\n.*?Solution:\s+([^\n]+)', full, re.S):
            keys[int(m.group(1))] = {a: int(b) for a, b in re.findall(r'([A-E]) = (\d+)', m.group(2))}
        for it in its: add(tag, doc, it, it['diff'], keys.get(it['n']))
    # doubt session part 2
    doc = SRC['doubt']
    full = norm('\n'.join(t for _, t in _pages(doc)))
    keys = {int(m.group(1)): {a: int(b) for a, b in re.findall(r'([A-E]) = (\d+)', m.group(2))}
            for m in re.finditer(r'Q(\d+) \((?:Moderate|Difficult|Most Difficult), \d unknowns\) — ([^\n]+)', full)}
    its = parse_generic(doc, re.compile(r'\[ (?P<d>MODERATE|DIFFICULT|MOST DIFFICULT) \]\s+Question (?P<n>\d+) · \d unknowns'),
                        re.compile(r'Space for explanation'))
    for it in its: add('doubt', doc, it, it['diff'].title(), keys.get(it['n']))
    # masters (only ME pages); key "Correct Answer: A = 10, B = 2, ..."
    doc = SRC['masters']
    full = norm('\n'.join(t for _, t in _pages(doc)))
    keys = {int(m.group(1)): {a: int(b) for a, b in re.findall(r'([A-E]) = (\d+)', m.group(2))}
            for m in re.finditer(r'Explanation for Question (\d+)\nCorrect Answer: ([A-E] = [^\n]+)', full)}
    its = parse_generic(doc, re.compile(r'^Question (?P<n>\d+): Mathematical Equations'), re.compile(r'===|^Question \d+:'))
    for it in its: add('masters', doc, it, '', keys.get(it['n']))
    # core150 (no key: solver answer only)
    doc = SRC['core150']
    its = parse_generic(doc, re.compile(r'^Question (?P<n>\d+) of 150'), re.compile(r'= \?'))
    for it in its:
        if it['lines']: add('core150', doc, it, '')
    return out, rejects


if __name__ == '__main__':
    out, rej = collect()
    import collections
    print('verified', len(out), collections.Counter(o['src'] for o in out))
    print('rejected', len(rej), collections.Counter(r[0] for r in rej))
    for r in rej[:40]: print('  REJ', r)
    for o in out[:3] + [o for o in out if o['src'] == 'doubt'][-2:]: print(o['src'], o['n'], o['diff'], o['lines'], o['sol'], '\n   ', o['expl'])
    # self-check: official exercise 5 must be A=5,B=1,C=10,D=12
    ex5 = [o for o in out if o['src'] == 'official' and o['n'] == 5][0]
    assert ex5['sol'] == {'A': 5, 'B': 1, 'C': 10, 'D': 12}, ex5
    print('OK')
