"""「コウ（囲碁・低→高）」と「こう（指示語・平ら）」が声の高さで分かれるかを、公開版の答えつきで確かめる（2026-10-29 三村さんの指摘）。
語の時刻（words）のある動画すべてで測る。"""
import re, subprocess, sys
import numpy as np, parselmouth
sys.path.insert(0, '.')
import telop_ledger as L, telop_questions as Q

PAT = re.compile(r'こう|コウ|劫')


def span(seg, pos, n):
    """本文の pos から n 文字を話している時刻 (始, 終)。"""
    c, st, en = 0, None, None
    for a, b, w in [x[:3] for x in seg['words']]:
        if st is None and c + len(w) > pos:
            st = a
        if c + len(w) >= pos + n:
            en = b
            break
        c += len(w)
    return st, en


def measure(snd, st, en):
    p = snd.extract_part(st - 0.02, en + 0.02).to_pitch(time_step=0.005, pitch_floor=60, pitch_ceiling=400)
    f = p.selected_array['frequency']
    f = f[f > 0]
    if len(f) < 6:
        return None
    semi = 12 * np.log2(f / 100)
    semi = semi[np.abs(semi - np.median(semi)) < 5]
    if len(semi) < 6:
        return None
    x = np.linspace(0, 1, len(semi))
    return np.polyfit(x, semi, 1)[0]



def f0(snd, a, b):
    p = snd.extract_part(max(a, 0), b).to_pitch(time_step=0.005, pitch_floor=60, pitch_ceiling=400)
    f = p.selected_array['frequency']
    f = f[f > 0]
    return 12 * np.log2(f / 100) if len(f) >= 4 else None


def features(snd, st, en):
    """語の前半・後半・直後0.25秒・前0.25秒の高さ（半音、区切りの中央値からの差）と、全体の傾き。"""
    whole = f0(snd, st - 0.3, en + 0.3)
    if whole is None:
        return None
    med = np.median(whole)
    mid = (st + en) / 2
    parts = [f0(snd, st - 0.25, st), f0(snd, st, mid), f0(snd, mid, en), f0(snd, en, en + 0.25)]
    if any(x is None for x in parts[1:3]):
        return None
    v = [float(np.median(x)) - med if x is not None else 0.0 for x in parts]
    return {'前': v[0], '前半': v[1], '後半': v[2], '後': v[3], '上がり': v[2] - v[1], '後との差': v[3] - v[1],
            '傾き': float(measure(snd, st, en) or 0)}


rows = []
for vid, tr, final in Q.videos():
    segs = L.load(tr)
    if not any(s.get('words') for s in segs):
        continue
    media = Q.find_media(tr, segs[-1]['end'])
    if media is None:
        continue
    if media.suffix != '.wav':   # Praat は mp4 を読めないので、16kHz の wav にして手元に置く
        wav = L.LEDGER / 'page' / 'tmp' / (vid.replace('/', '_') + '_16k.wav')
        if not wav.exists():
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(media), '-vn', '-ac', '1', '-ar', '16000', str(wav)], check=True)
        media = wav
    snd = parselmouth.Sound(str(media))
    for k, s in enumerate(segs):
        if not final.get(k) or not s.get('words'):
            continue
        ms = list(PAT.finditer(s['text']))
        go, gen = len(re.findall(r'コウ|劫', final[k])), final[k].count('こう')
        if len(ms) != 1 or go + gen != 1:
            continue
        st, en = span(s, ms[0].start(), 2)
        if st is None or en is None or en - st < 0.12:
            continue
        feats = features(snd, st, en)
        if feats is not None:
            rows.append(('コウ' if go else 'こう', feats, vid, k, final[k][:30]))

for name in rows[0][1]:
    go = sorted(r[1][name] for r in rows if r[0] == 'コウ')
    ge = sorted(r[1][name] for r in rows if r[0] == 'こう')
    best = max(((th, s, sum(((r[1][name] - th) * s > 0) == (r[0] == 'コウ') for r in rows))
                for th in np.arange(-6, 6, 0.1) for s in (1, -1)), key=lambda x: x[2])
    # 当てずっぽう（全部「こう」）の正解数と比べる
    print(f"{name}: コウ中央値 {np.median(go):+.2f} / こう中央値 {np.median(ge):+.2f}  最良 {best[2]}/{len(rows)}（全部こうなら {len(ge)}）")
