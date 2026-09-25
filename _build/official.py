"""Official g.a.s.t. material: General Academic passages/questions and Figure-Sequence exercises (cropped)."""
import re
import pymupdf
from common import SRC

TOP, FOOT = 84, 790  # content band on official pages (below logo, above running footer)

GA = [  # (passage id, title, topic, passage pages, question pages, qtype per question)
    ('vec', 'Vector Calculations', 'Mathematics', [34], [35, 36, 37],
     ['figure-based calculation', 'concept', 'table reading', 'formula application', 'formula application', 'formula application', 'figure-based calculation', 'concept']),
    ('hyd', 'Hydrostatics', 'Physics / Engineering', [40, 41], [42, 43, 44, 45],
     ['estimation', 'formula application', 'figure-based reasoning', 'figure-based reasoning', 'figure-based reasoning', 'figure-based reasoning']),
    ('eoq', 'Optimal Order Quantity', 'Business Administration', [48], [49, 50],
     ['text comprehension', 'formula reasoning', 'formula reasoning', 'formula application', 'formula reasoning', 'transfer', 'graph reading']),
    ('res', 'Research Strategies in Social Sciences', 'Social Sciences', [53], [54, 55],
     ['text comprehension', 'text comprehension', 'text comprehension', 'transfer / scenario', 'transfer / scenario', 'transfer / scenario']),
]
KEYS = {'vec': 'acbbabda', 'hyd': 'dbbaba', 'eoq': 'aabbdab', 'res': 'cbacaa'}

EXPL = {
 'vec': [
  "Read the components from the diagram: a = (1, 3), b = (5, 1), c = (1, −2). Add/subtract component-wise (passage, paragraph 2): s = (1+5−1, 3+1−(−2)) = (5, 6). (b) and (c) get the y-component wrong by treating −c as +c or dropping a term; (d) gets the x-component wrong.",
  "Paragraph 2: multiplying by a scalar multiplies every component; |−2| = 2 doubles the length and the negative sign reverses the direction. (a) ignores the sign; (b) and (d) confuse −2 with ½.",
  "Table 1: the scalar product gives a number (scalar), the vector product gives a vector, and the triple product a·(b×c) is a scalar product again → scalar. (a) calls the triple product a vector; (c) calls the scalar product a vector; (d) calls the vector product a scalar.",
  "Table 1, scalar product: aₓbₓ + a_yb_y + a_zb_z = 1·4 + 2·5 + 3·6 = 4 + 10 + 18 = 32. (a) 21 adds all six numbers; (c) adds the two lengths; (d) multiplies instead of summing.",
  "Table 1, 'further relationships': a·b = |a||b|cos φ. a·b = 1·2 + 2·1 = 4, |a| = |b| = √5, so cos φ = 4/(√5·√5) = 4/5 → φ = arccos(4/5). (b) and (d) use a wrong denominator; (c) inverts the fraction (cos cannot exceed 1).",
  "Table 1, vector product: (a_yb_z − a_zb_y, a_zbₓ − aₓb_z, aₓb_y − a_ybₓ) = (2·4 − 1·5, 1·6 − 3·4, 3·5 − 2·6) = (3, −6, 3). (a) loses the minus sign of the middle component; (c) adds the vectors; (d) multiplies component-wise.",
  "The parallelogram area equals |a × b|. From the figure a = (3, 4) and b = (1, −2) (z = 0), so |a × b| = |3·(−2) − 4·1| = |−6 − 4| = 10 square units. (a)/(c) take a square root that does not belong here; (b) halves the area (that would be the triangle).",
  "The triple product is the volume spanned by the three vectors; a value of 0 means zero volume, i.e. the vectors lie in one plane (coplanar) – true for ALL such cases. (b) perpendicular vectors give the maximal volume; (c) parallel vectors are only one special case of coplanarity; (d) is not required.",
 ],
 'hyd': [
  "Passage: pressure rises by about 1 bar every 10 m. 10,000 m / 10 m = 1000 → about 1000 bar (the extra 1 bar of air pressure is negligible). (a)–(c) are 1000×, 100× and 10× too small.",
  "Passage: a floating (fully submerged) body displaces a mass of water equal to its own mass. Volume 2 m³ × 1000 kg/m³ = 2000 kg. The depths 3 m and 4 m are distractors – they do not change the displaced volume. (a), (c), (d) misuse the depths.",
  "The air in room R cannot escape, so it is compressed by the water pressure at 10 m depth (≈ 2 bar total instead of 1 bar). By p·V = const the air volume halves, so water rises to about half the room height, 2.4 m / 2 = 1.2 m (official solution: ≈1.13 m precisely, so 'about 1.2 m' fits). (a) ignores the trapped air; (c) takes the tear height; (d) ignores that air is compressible.",
  "Only the air bubble in the object is compressible. Pressing on the membrane raises the pressure everywhere (passage: external pressure adds), the bubble shrinks, the object displaces less water, buoyancy falls → it sinks. (b) water is incompressible, its density does not rise; (c) forgets the bubble; (d) invents a pressure wave.",
  "A suction pump can only use the pressure difference to the atmosphere (≈1 bar). 1 bar supports a water column of about 10 m (passage: 1 bar per 10 m), so the height h of the suction port above sea level must not exceed 10 m. (a), (c), (d) name limits that do not follow from atmospheric pressure; the depth t does not limit suction.",
  "Moving the box by d creates the same tilting moment in all ships (same mass, same shift). The restoring effect depends on how far the centre of buoyancy moves when the ship heels – a wider hull shifts it more. Ship A is the narrowest, so it has the smallest restoring moment and tilts the furthest. (b)/(c) are wider; (d) ignores the cross-section.",
 ],
 'eoq': [
  "Bullet 'Constant Demand': demand is constant, known and evenly distributed over the year. (b) contradicts it (safety stocks are not part of the model); (c) contradicts 'No Quantity Discounts'; (d) the goal is minimal total cost, not minimal space.",
  "Q* = √(2DS/H): Q* rises when D or S rise or when H falls. So a reduction in holding cost H increases Q*. (b) and (c) would decrease Q*; (d) is false because (a) works.",
  "'Constant Demand': inventory is Q right after an order and falls steadily to 0 → average inventory = Q/2, and holding cost = average stock × H. (a) Q is the maximum, not Q/2; (c) all stored units cost holding; (d) the number of orders is D/Q.",
  "Q* = √(2·1800·50/2) = √90,000 = 300 units. (a) 150 halves it; (c) and (d) do not satisfy the formula (e.g. 600² = 360,000).",
  "S appears under the square root: doubling S multiplies Q* by √2 ≈ 1.41. (b) forgets the root; (c) squares instead of rooting; (a) goes the wrong direction.",
  "The passage says holding costs depend on the value of the stored goods (capital costs). A higher unit value → higher H → H is in the denominator → Q* could decrease. (b) gets the direction wrong; (c) contradicts the passage; (d) S does not depend on the unit value.",
  "Total fixed ordering costs = (D/Q)·S, which FALLS as Q increases (fewer orders). In the figure that is the steadily decreasing curve, line B. The rising straight line is holding cost, the U-shaped curve is total cost and D marks the optimum – so (a), (c), (d) show other quantities.",
 ],
 'res': [
  "Paragraphs 1–2: the deductive (quantitative) strategy identifies causal relationships – whether a factor relates to an outcome. (a) sample size depends on the design; (b) and (d) describe the qualitative (inductive) strategy.",
  "Paragraphs 1 and 3: the inductive (qualitative) strategy seeks causal mechanisms – HOW factors lead to consequences. (a) and (d) are what the passage says it does NOT provide (spread/generalisation); (c) 'a few cases' are also possible, not only one.",
  "Paragraph 6: qualitative projects can include circular elements; the approach or question may be changed during the process if documented. (b) quantitative changes must be documented and are limited; (c) changes must be documented; (d) quantitative projects run linearly, so order matters.",
  "Paragraphs 4–5: in the ideal-typical quantitative process the hypothesis is fixed in the design before analysis; changing it afterwards to fit the results contradicts this. (a) and (b) are qualitative studies (circular elements allowed); (d) follows a previously defined, documented plan.",
  "Mixed approach: the 1,000 borrowing records give quantitative data on WHAT literature is read, and interviews give qualitative insight into WHY young people use the library. (b) is only qualitative and asks the wrong people; (c) ignores titles; (d) says nothing about literature interests.",
  "He starts from an existing theory and tests its reach and transferability statistically → deductive (theory-testing) approach (paragraphs 1–2). (b) causal mechanisms belong to the inductive strategy; (c) targeted individual surveys are qualitative; (d) nothing prevents statistical tests.",
 ],
}


def _lines(page):
    out = []
    for b in page.get_text('dict')['blocks']:
        for l in b.get('lines', []):
            t = ''.join(s['text'] for s in l['spans']).strip()
            if t: out.append((l['bbox'][1], l['bbox'][3], l['bbox'][0], t))
    return sorted(out)


def _bottom(page):
    ys = [l[1] for l in _lines(page) if l[0] < FOOT - 2]
    ims = [i['bbox'][3] for i in page.get_image_info() if i['bbox'][1] > TOP]
    return max(ys + ims) + 4


def ga_official():
    doc = pymupdf.open(SRC['official'])
    passages = []
    for pid, title, topic, ppages, qpages, qtypes in GA:
        # passage crops: from the title (first page) / top band (later pages) to the last content line
        crops = []
        for i, pg in enumerate(ppages):
            page = doc[pg - 1]
            y0 = [l[0] for l in _lines(page) if l[3] == title][0] - 4 if i == 0 else TOP
            crops.append((pg, (60, y0, 540, _bottom(page))))
        # anchors across question pages
        anchors = []  # (page, y0, kind, idx)
        for pg in qpages:
            page = doc[pg - 1]
            for y0, y1, x, t in _lines(page):
                if y0 > FOOT: continue
                m = re.match(r'Question (\d)$', t)
                if m and x < 80: anchors.append((pg, y0, 'q', int(m.group(1))))
                m = re.match(r'([a-d])\)', t)
                if m and x < 80: anchors.append((pg, y0, 'o', 'abcd'.index(m.group(1))))
        anchors.append((qpages[-1], None, 'end', 0))
        qs, cur = [], None
        def seg(a, b):  # crop list from anchor a to anchor b (may cross a page)
            (pa, ya), (pb, yb) = a, b
            if yb is None: yb = _bottom(doc[pb - 1])
            if pa == pb: return [(pa, (60, ya - .5, 540, yb - .5))]
            out = [(pa, (60, ya - .5, 540, _bottom(doc[pa - 1])))]
            for p in range(pa + 1, pb): out.append((p, (60, TOP, 540, _bottom(doc[p - 1]))))
            if yb > TOP + 15: out.append((pb, (60, TOP, 540, yb - .5)))
            return out
        for i, (pg, y, kind, idx) in enumerate(anchors[:-1]):
            nxt = anchors[i + 1]
            if kind == 'q':
                cur = {'n': idx, 'stem': seg((pg, y), (nxt[0], nxt[1])), 'opts': []}; qs.append(cur)
            else:
                cur['opts'].append(seg((pg, y), (nxt[0], nxt[1])))
        for i, q in enumerate(qs):
            assert len(q['opts']) == 4, (pid, q['n'], len(q['opts']))
            q['ans'] = 'abcd'.index(KEYS[pid][i]); q['expl'] = EXPL[pid][i]; q['qtype'] = qtypes[i]
        passages.append({'id': pid, 'title': title, 'topic': topic, 'crops': crops, 'questions': qs,
                         'sol_page': {'vec': 38, 'hyd': 46, 'eoq': 51, 'res': 56}[pid]})
    return passages


# ---------------- official Figure Sequences (raster exercises, identical template) ----------------
FS_PAGES = [(9, 0), (10, 0), (10, 1), (11, 0), (11, 1), (12, 0)]   # (page, image index) for exercises 1..6
FS_KEYS = [(0, 1), (2, 1), (1, 1), (0, 2), (2, 2), (1, 0)]           # official solution: Image1 / Image2 = Matrix n
FS_DIFF = ['Easy', 'Easy', 'Medium', 'Medium', 'Hard', 'Hard']
FS_SOL_PAGE = [13, 14, 14, 15, 15, 16]
# template in image fractions (measured on the 1569x1072 official images)
_W, _H = 1096, 749
_T = {'strip': (0, 0, 1096, 200), 'o5': [(740, 208, 911, 378), (740, 394, 911, 564), (740, 580, 911, 749)],
      'o6': [(926, 208, 1096, 378), (926, 394, 1096, 564), (926, 580, 1096, 749)]}
FS_EXPL = [
 "The green diamond moves vertically one field at a time in the second column (β) and bounces off the upper and lower border: β2 → β1 → β2 → β3, so Grid 5 = β4 (option A) and Grid 6 = β3 after bouncing off the bottom (option B). Nothing else changes. The other options put the diamond in the wrong column or skip the bounce.",
 "The yellow square moves diagonally up-right one field per image (α3 → β2 → γ1), bounces off the upper border and returns the same way (β2). Continuing down-left: Grid 5 = α3 (option C); it then bounces off the lower-left start and moves up-right again: Grid 6 = β2 (option B). The other options continue in a straight line through the border or move the square the wrong way.",
 "Three independent rules (official solution): the arrow moves clockwise along the outer border by TWO fields per image and alternates colour black ↔ pink; the white hook symbol stays in its cell and rotates 90° to the right each image; the yellow hexagon moves counter-clockwise along the outer border ONE field per image. Applying all three gives option B for Grid 5 and option B for Grid 6; each other option breaks at least one rule (wrong arrow colour/position or wrong hook orientation).",
 "Three rules (official solution): the green flag/triangle moves horizontally along the fourth row one field per image, bounces off the side borders and rotates 90° to the right each image; the pink square moves one field per image in the repeating order left, up, right, down; the white hexagon moves diagonally down-left from the top-right corner to the bottom-left corner and then back. Grid 5 = option A, Grid 6 = option C; the other options misplace the square or give the flag the wrong orientation.",
 "Four rules (official solution): the yellow triangle moves clockwise along the outer border by x+1 fields (1, 2, 3, …); the L-shaped symbol moves horizontally in the third row, bounces off the borders, turns 90° to the left each image and cycles colour white → pink → yellow; the arch symbol moves one field per image in the order down, right, up, left, turns 90° left and alternates orange ↔ black; the white hexagon moves diagonally up-right, bounces off the right border and returns. Grid 5 = option C, Grid 6 = option C; the other options break the colour cycle, the rotation or the x+1 step count.",
 "Four rules (official solution): the orange arrow moves diagonally down-right, bounces off the lower border and returns, and rotates x+1 times by 90° to the right (1×, 2×, 3× …); the white L-shape moves vertically in the third column, bounces, and rotates 90° to the left each image; the white diamond symbol moves counter-clockwise along the outer border one field per image; the triangle moves clockwise along the outer border two fields per image and cycles colour yellow → green → orange. Grid 5 = option B, Grid 6 = option A; the other options fail the accelerating rotation or the colour cycle.",
]


def fs_official():
    doc = pymupdf.open(SRC['official'])
    out = []
    for i, (pg, k) in enumerate(FS_PAGES):
        page = doc[pg - 1]
        info = [x for x in page.get_image_info() if x['width'] > 1000][k]
        ib = pymupdf.Rect(info['bbox']); sx, sy = ib.width / _W, ib.height / _H
        P = lambda b: (ib.x0 + b[0] * sx, ib.y0 + b[1] * sy, ib.x0 + b[2] * sx, ib.y0 + b[3] * sy)
        out.append({'n': i + 1, 'page': pg, 'ans': FS_KEYS[i], 'diff': FS_DIFF[i], 'expl': FS_EXPL[i], 'sol_page': FS_SOL_PAGE[i],
                    'boxes': {'strip': P(_T['strip']), 'o5': [P(b) for b in _T['o5']], 'o6': [P(b) for b in _T['o6']]}})
    return out


if __name__ == '__main__':
    ps = ga_official()
    for p in ps:
        print(p['id'], len(p['questions']), p['crops'])
        for q in p['questions']: print('   Q', q['n'], 'stem', q['stem'], 'ans', 'abcd'[q['ans']])
    print(len(fs_official()))
