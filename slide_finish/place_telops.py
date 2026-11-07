"""テロップを、出ている間ずっと紙芝居の中身と重ならない場所へ動かす（2026-11-07 三村さん「空いている部分に適宜移動」）。
既定は下端（Shita2）。重なるときは、下から上へ帯を探し、最初に空いている所に \\an2\\pos で置く。
判定は録画（テロップ無し）を 4fps・480×270 で見て、背景色から外れた画素（顔・スクロールバーは除く）。"""
import re, numpy as np
from PIL import ImageFont
import cv2
F = np.memmap('frames_480.rgb', np.uint8, 'r').reshape(-1, 270, 480, 3)
FPS, S = 4, 4                      # 480座標 → 1920座標は ×4
acc = np.load('content_rate.npy')
core = acc > 0.7
core[:, :300] = False; core[:60, :] = False   # 顔は右下だけ（紙芝居でよく字が出る場所を顔と取り違えない）
face = cv2.dilate(core.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
face[:, 466:] = True               # 右端のスクロールバー
BG = np.array([245, 242, 234], np.int16)
BM = np.load('busy_mask.npy', mmap_mode='r')   # busy_mask.py で作る
FONT = ImageFont.truetype('/home/mimura/.local/share/fonts/NotoSansCJKjp-Bold.otf', 84)
PAD, H = 16, 84 + 2 * 18           # 箱の余白と高さ（1920座標）
# 重ねる名札・案内カード（1920座標 x0,y0,x1,y1, 開始, 終了）
import json
_e = json.load(open('end_cards_pos.json'))   # 締めの案内の置き場（render.py と同じ）
CARDS = [(1500, 520, 1830, 670, 0.3, 10.0), (_e[0], _e[1], _e[0] + 858, _e[1] + 340, 1428.98, 1446.5)]

def ts(s):
    h, m, x = s.split(':'); return int(h) * 3600 + int(m) * 60 + float(x)

def plain(t):
    return re.sub(r'\{[^}]*\}', '', t).replace('\\N', '')

def busy(x0, y0, x1, y1, a, b):
    i0, i1 = int(a * FPS), max(int(a * FPS) + 1, int(b * FPS))
    X0, Y0, X1, Y1 = x0 // S, y0 // S, -(-x1 // S), -(-y1 // S)
    fz = face[Y0:Y1, X0:X1]
    if fz.sum() > 0: return 1e6 + fz.sum()      # 顔にもかけない（11-07 三村さん「顔が重なっているところも」）
    c = BM[i0:i1, Y0:Y1, X0:X1].astype(bool)
    worst = c.reshape(len(c), -1).sum(1).max()
    for cx0, cy0, cx1, cy1, ca, cb in CARDS:
        if ca < b and cb > a and x0 < cx1 and x1 > cx0 and y0 < cy1 and y1 > cy0: worst += 1e6
    return worst

lines = open('telops_bottom.ass').read().split('\n')
out, moved, stuck = [], 0, []
prev = (720, 1056)
M = 16      # テロップの周りの余白（1920座標）
FREE = 8    # カーソル等の小さな塊は busy_mask.py で外してあるので、ほぼ0で判定
for ln in lines:
    if not ln.startswith('Dialogue'):
        out.append(ln); continue
    p = ln.split(',', 9)
    a, b, text = ts(p[1]), ts(p[2]), p[9]
    w = FONT.getlength(plain(text)) + 2 * PAD
    cands = [(720, 1056), prev] + [(720, y) for y in range(1032, 150, -24)] + [(960, y) for y in range(1056, 150, -24)]
    found, least = None, None
    for cx, by in cands:
        x0, x1 = int(cx - w / 2), int(cx + w / 2)
        if x0 < 10 or x1 > 1910: continue
        v = busy(x0 - M, by - H - M, x1 + M, by + 6 + M, a, b)   # 周りに余白を取る（見出しやカードに貼り付かない）
        if v <= FREE: found = (cx, by); break
        if least is None or v < least[2]: least = (cx, by, v)
    if found:
        cx, by = found
    else:   # どこも埋まっている → 重なりが一番少ない所
        # どこにも入らない → このテロップは出さない（11-07 三村さん「入らない部分だけ、テロップを消す」。SRT字幕には残る）
        stuck.append((p[1], plain(text), int(least[2]), least[:2])); continue
    prev = (cx, by)
    if (cx, by) != (720, 1056):
        moved += 1
        p[9] = '{\\an2\\pos(%d,%d)}' % (cx, by) + text
    out.append(','.join(p))
open('telops.ass', 'w').write('\n'.join(out))
print('消した', len(stuck), '動かした', moved, '／', sum(1 for l in lines if l.startswith('Dialogue')), '置き場が無かった', len(stuck))
for s in stuck[:20]: print('  ', s)
