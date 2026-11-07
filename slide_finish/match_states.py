"""録画の各時刻（1fps）が紙芝居のどの段階か（倍率1.28・ずれ(-12,-8)）。合わないとき（拡大中など）は -1"""
import numpy as np, cv2, json
F = np.memmap('frames_480.rgb', np.uint8, 'r').reshape(-1, 270, 480, 3)
SC, DX, DY = 1.28, -12, -8
names = json.load(open('states/list.json'))
acc = np.load('content_rate.npy')
core = acc > 0.7; core[:, :300] = False; core[:60, :] = False
face = cv2.dilate(core.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
use = ~face; use[:, 466:] = False
def place(img):
    T = cv2.resize(img, (round(1920 * SC), round(1080 * SC)), interpolation=cv2.INTER_AREA)
    c = np.full((1080, 1920, 3), (234, 242, 245), np.uint8)   # BGR
    c[:, :] = T[-DY:-DY + 1080, -DX:-DX + 1920]
    return c
V = []
for n in names:
    c = place(cv2.imread(n))
    V.append(cv2.resize(c, (480, 270), interpolation=cv2.INTER_AREA)[..., ::-1].astype(np.int16))
V = np.stack(V)
res = []
for t in range(len(F)):   # 1秒4回（11-07: 1秒ごとだと、めくった瞬間と重ね絵の切り替えが最大1秒ずれた）
    f = F[t].astype(np.int16)
    e = np.abs(V - f[None]).mean(-1)[:, use].mean(1)
    k = int(e.argmin()); res.append((t, k, round(float(e[k]), 1)))
json.dump(res, open('state_by_q.json', 'w'))
bad = [r for r in res if r[2] >= 9]
print('秒数', len(res), '合わない秒', len(bad))
cur = None
for t, k, e in res:
    lab = names[k].split('/')[-1][:-4] + ('' if e < 9 else '?')
    if lab != cur: print(f'{t/4:.2f}', lab); cur = lab
