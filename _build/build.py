"""Inline bank.json into app.html -> ../dmat_master_practice.html (single self-contained file)."""
import json, os
H = os.path.dirname(os.path.abspath(__file__))
bank = json.load(open(os.path.join(H, 'bank.json'), encoding='utf-8'))
js = json.dumps(bank, ensure_ascii=True, separators=(',', ':')).replace('</', '<\\/')
tpl = open(os.path.join(H, 'app.html'), encoding='utf-8').read()
assert tpl.count('/*__BANK__*/null') == 1
out = tpl.replace('/*__BANK__*/null', js)
dst = os.path.join(os.path.dirname(H), 'dmat_master_practice.html')
open(dst, 'w', encoding='utf-8').write(out)
open(os.path.join(os.path.dirname(H), 'docs', 'index.html'), 'w', encoding='utf-8').write(out)  # GitHub Pages copy
print('wrote', dst, round(os.path.getsize(dst) / 1e6, 2), 'MB')
