"""General Academic practice set (20 passages, 140 Q): passages -> HTML (sup/sub, tables), questions, keys."""
import re, html
import pymupdf
from common import SRC, norm

# stems whose superscripts were lost in the source PDF itself (plain text there) -> corrected
FIX = {
    15: [('log(a3 x b)', 'log(a<sup>3</sup> × b)')],
    16: [('2x = 32', '2<sup>x</sup> = 32')],
    58: [('10-3 mol', '10<sup>−3</sup> mol')],
}


def span_html(s, base):
    t = html.escape(norm(s['text']).replace('−', '−'))
    if s['flags'] & 1: return f'<sup>{t}</sup>'
    if s['size'] < base - 1.2 and t.strip(): return f'<sub>{t}</sub>'
    if s['flags'] & 16: return f'<b>{t}</b>'
    if s['flags'] & 2: return f'<i>{t}</i>'
    return t


def page_lines(page, skip_rects):
    out = []
    for b in page.get_text('dict')['blocks']:
        for l in b.get('lines', []):
            r = pymupdf.Rect(l['bbox'])
            if any(r.intersects(x) for x in skip_rects): continue
            base = max(s['size'] for s in l['spans'])
            h = ''.join(span_html(s, base) for s in l['spans'])
            raw = ''.join(s['text'] for s in l['spans'])
            out.append({'y': r.y0, 'y1': r.y1, 'x': r.x0, 'html': h, 'raw': norm(raw), 'bold': all(s['flags'] & 16 for s in l['spans'] if s['text'].strip()), 'size': base})
    out.sort(key=lambda l: (round(l['y']), l['x']))
    # merge spans on the same baseline (superscripts come out as separate lines)
    merged = []
    for l in out:
        if merged and abs(l['y'] - merged[-1]['y']) < 4 and l['x'] > merged[-1]['x']:
            merged[-1]['html'] += l['html']; merged[-1]['raw'] += l['raw']; merged[-1]['y1'] = max(merged[-1]['y1'], l['y1'])
        else: merged.append(dict(l))
    return merged


def table_html(page, tab):
    rows = []
    for row in tab.rows:
        cells = []
        for c in row.cells:
            if c is None: continue
            r = pymupdf.Rect(c)
            parts = []
            for b in page.get_text('dict', clip=r)['blocks']:
                for l in b.get('lines', []):
                    base = max(s['size'] for s in l['spans'])
                    parts.append((l['bbox'][1], l['bbox'][0], ''.join(span_html(s, base) for s in l['spans'])))
            parts.sort()
            txt = ''
            for i, p in enumerate(parts):
                if i and abs(p[0] - parts[i - 1][0]) > 5 and not p[2].startswith('<su'): txt += ' '
                txt += p[2]
            cells.append(txt.strip())
        rows.append(cells)
    head = '<tr>' + ''.join(f'<th>{c}</th>' for c in rows[0]) + '</tr>'
    body = ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in r) + '</tr>' for r in rows[1:])
    return f'<table class="ptable">{head}{body}</table>'


def collect():
    doc = pymupdf.open(SRC['gaprac'])
    stream = []  # sequence of ('line', l) / ('table', html, caption) in reading order
    for pno in range(2, 42):  # pages 3..42 hold exercises 1..20
        page = doc[pno]
        tabs = page.find_tables().tables
        items = [('line', l, pno + 1) for l in page_lines(page, [pymupdf.Rect(t.bbox) for t in tabs])]
        for t in tabs: items.append(('table', {'y': t.bbox[1], 'html': table_html(page, t)}, pno + 1))
        items.sort(key=lambda it: it[1]['y'])
        stream += items
    passages, cur, mode, q = [], None, None, None
    for kind, it, pg in stream:
        raw = it.get('raw', '') if kind == 'line' else ''
        m = re.match(r'Exercise (\d+)\s+(.*)', raw)
        if m and it['bold']:
            cur = {'n': int(m.group(1)), 'title': m.group(2).strip(), 'page': pg, 'paras': [], 'questions': []}
            passages.append(cur); mode = 'passage'; continue
        if cur is None: continue
        if kind == 'line' and it['bold'] and cur['title'] and raw.strip() and mode == 'passage' and len(cur['paras']) == 0 and not raw.startswith('Question'):
            cur['title'] += ' ' + raw.strip(); continue  # wrapped title
        if raw.startswith('Questions ') and '·' in raw: continue
        if raw.strip() == 'QUESTIONS': mode = 'q'; continue
        if mode == 'passage':
            if kind == 'table': cur['paras'].append(('table', it['html']))
            elif raw.startswith('Table ') or raw.startswith('Table\xa0'): cur['paras'].append(('caption', it['html']))
            else: cur['paras'].append(('line', it))
        else:
            mq = re.match(r'Question (\d+)$', raw.strip())
            if mq and it['bold']:
                q = {'n': int(mq.group(1)), 'stem': '', 'opts': [], 'page': pg}; cur['questions'].append(q); continue
            if q is None or kind != 'line': continue
            mo = re.match(r'([a-d])\) ?(.*)', raw)
            if mo and len(q['opts']) < 4 and ord(mo.group(1)) - 97 == len(q['opts']):
                q['opts'].append(re.sub(r'^[a-d]\)\s?', '', it['html']))
            elif q['opts']: q['opts'][-1] += ' ' + it['html']
            else: q['stem'] += (' ' if q['stem'] else '') + it['html']
    # paragraphs: join passage lines, split on vertical gaps
    for p in passages:
        out, buf, prev = [], [], None
        for kind, v in p['paras']:
            if kind != 'line':
                if buf: out.append('<p>' + ' '.join(buf) + '</p>'); buf = []
                out.append(v if kind == 'table' else f'<p class="cap">{v}</p>'); prev = None; continue
            if prev is not None and v['y'] - prev['y1'] > 7 and buf: out.append('<p>' + ' '.join(buf) + '</p>'); buf = []
            buf.append(v['html']); prev = v
        if buf: out.append('<p>' + ' '.join(buf) + '</p>')
        p['html'] = '\n'.join(out); del p['paras']
    # answer key
    full = norm('\n'.join(doc[i].get_text() for i in range(42, 47)))
    key = {}
    for m in re.finditer(r'\n(\d{1,3})\n([abcd])\n(.*?)(?=\n\d{1,3}\n[abcd]\n|\nExercise \d|\nDistribution|\n=+|$)', full, re.S):
        key[int(m.group(1))] = (m.group(2), ' '.join(m.group(3).split()))
    for p in passages:
        for q in p['questions']:
            for a, b in FIX.get(q['n'], []): q['stem'] = q['stem'].replace(a, b)
            q['ans'], q['short'] = 'abcd'.index(key[q['n']][0]), key[q['n']][1]
            # "Question 1" inside later passages refers to the first question of that exercise
            q['stem'] = re.sub(r'(of|in|under the conditions of|the car of) Question 1\b', r'\1 the first question of this passage', q['stem'])
    return passages


if __name__ == '__main__':
    ps = collect()
    print(len(ps), sum(len(p['questions']) for p in ps))
    for p in ps: assert len(p['questions']) == 7, (p['n'], len(p['questions']))
    for p in ps:
        for q in p['questions']: assert len(q['opts']) == 4, (q['n'], q['opts'])
    print(ps[2]['title']); print(ps[2]['html'][:1500]); print(ps[2]['questions'][1])
    print(ps[4]['html'][-900:])
    print('OK')
