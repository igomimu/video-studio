"""顔ワイプに隠れた紙芝居の字・図だけを、録画と同じ倍率で描き直して顔の上に重ねる（11-07 三村さん「可能な限り、紙芝居をきれいに見せる」）。
顔全体は覆わない: 隠れた中身の周りに背景色の縁を付けた部分だけを重ねる。"""
import numpy as np, cv2, json
SC, DX, DY = 1.28, -12, -8
names = json.load(open('states/list.json'))
res = json.load(open('state_by_q.json'))   # 1秒4回
acc = np.load('content_rate.npy')
core = acc > 0.7; core[:, :300] = False; core[:60, :] = False
fz = cv2.resize(cv2.dilate(core.astype(np.uint8), np.ones((11, 11), np.uint8)), (1920, 1080), interpolation=cv2.INTER_NEAREST) > 0
ys, xs = np.where(fz); X0, Y0 = int(xs.min()), int(ys.min())
BG = np.array([234, 242, 245], np.int16)   # BGR
def place(img):
    T = cv2.resize(img, (round(1920 * SC), round(1080 * SC)), interpolation=cv2.INTER_AREA)
    return T[-DY:-DY + 1080, -DX:-DX + 1920]
patch = {}
for k, n in enumerate(names):
    c = place(cv2.imread(n))
    m = (np.abs(c.astype(np.int16) - BG).max(-1) > 25) & fz
    if m.sum() < 300: continue
    halo = cv2.dilate(m.astype(np.uint8), np.ones((25, 25), np.uint8))
    halo = cv2.GaussianBlur(halo.astype(np.float32), (9, 9), 0)
    a = (np.clip(halo, 0, 1) * 255).astype(np.uint8)
    rgba = np.dstack([c, a])[Y0:, X0:]
    p = f'overlay/face_{k:02d}.png'; cv2.imwrite(p, rgba); patch[k] = p
# 秒ごとの段階 → 区間。合いが悪い秒（拡大中など e>=12）は重ねない
segs = []
for q, k, e in res:
    t = q / 4
    k = k if (e < 12 and k in patch) else None
    if segs and segs[-1][0] == k and abs(segs[-1][2] - t) < 1e-6: segs[-1][2] = t + 0.25
    else: segs.append([k, t, t + 0.25])
segs = [s for s in segs if s[0] is not None and s[2] - s[1] >= 0.5]   # 1秒でも重ねる（11-07 三村さん「顔を消しすぎても紙芝居が見えないよりは良い」）
cards = [[patch[k], X0, Y0, a, b] for k, a, b in segs]
json.dump(cards, open('face_cards.json', 'w'), ensure_ascii=False)
print('重ねる絵', len(patch), '区間', len(cards), '合計秒', sum(b - a for *_, a, b in cards), '位置', X0, Y0)
