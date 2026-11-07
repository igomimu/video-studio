"""全フレーム（4fps・480×270）の「中身がある画素」を先に作る。ページの背景色から少しでも外れたら中身（画像の白地・カードも含む）。
全画面で見て小さく孤立した塊（480座標で幅28×高さ34以下＝マウスのカーソル（動くとぶれる）など）だけ外す。"""
import numpy as np, cv2
F = np.memmap('frames_480.rgb', np.uint8, 'r').reshape(-1, 270, 480, 3)
BG = np.array([245, 242, 234], np.int16)
M = np.lib.format.open_memmap('busy_mask.npy', 'w+', np.uint8, (len(F), 270, 480))
k = np.ones((3, 3), np.uint8)
for i in range(len(F)):
    c = (np.abs(F[i].astype(np.int16) - BG).max(-1) > 7).astype(np.uint8)   # カードの地 (255,253,247) も拾う
    d = cv2.dilate(c, k)
    n, lab, st, _ = cv2.connectedComponentsWithStats(d, connectivity=8)
    small = np.zeros(n, bool); small[1:] = (st[1:, 2] <= 28) & (st[1:, 3] <= 34)   # 動いているカーソルはぶれて 26×31 になる
    c[small[lab]] = 0
    M[i] = c
M.flush(); print(len(F))
