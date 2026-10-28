"""「アタリ（平板）」と「辺り（頭高）」が声の高さで分かれるかを、公開版の答えつきで確かめる（2026-10-29 三村さんの指摘）。"""
import json, re, sys
import numpy as np, parselmouth
sys.path.insert(0, '.')
import telop_ledger as L

PAT = re.compile(r'あたり|当たり|アタリ|辺り')


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


rows = []
for vid in ['20261027_suhyup1', '20261028_suhyup2']:
    snd = parselmouth.Sound(f'work/{vid}/audio.wav')
    segs = L.load(f'work/{vid}/finish/transcript.json')
    final = {f['i']: f['text'] for f in L.load(f'work/{vid}/finish/refined_final.json') if 'i' in f}
    for k, s in enumerate(segs):
        if k not in final:
            continue
        ms = list(PAT.finditer(s['text']))
        go, gen = final[k].count('アタリ'), len(re.findall(r'あたり|辺り', final[k]))
        if len(ms) != 1 or go + gen != 1:   # 1区切りに1つだけ＝答えが一意な所だけ
            continue
        st, en = span(s, ms[0].start(), len(ms[0].group()))
        if st is None or en is None or en - st < 0.15:
            continue
        p = snd.extract_part(st - 0.02, en + 0.02).to_pitch(time_step=0.005, pitch_floor=60, pitch_ceiling=400)
        f = p.selected_array['frequency']
        f = f[f > 0]
        if len(f) < 6:
            continue
        semi = 12 * np.log2(f / 100)
        semi = semi[np.abs(semi - np.median(semi)) < 5]   # 倍音の取り違え（オクターブ飛び）を捨てる
        if len(semi) < 6:
            continue
        x = np.linspace(0, 1, len(semi))
        slope = np.polyfit(x, semi, 1)[0]                  # 区間全体の傾き（頭高＝下がる）
        peak = x[np.argmax(semi)]                          # いちばん高い所の位置（頭高＝前寄り）
        rows.append(('アタリ' if go else '辺り', round(slope, 2), round(peak, 2), vid[-1], k, s['text'][:30]))

for lab in ['アタリ', '辺り']:
    d = [r for r in rows if r[0] == lab]
    print(lab, len(d), '傾き 中央値', np.median([r[1] for r in d]), '山の位置 中央値', np.median([r[2] for r in d]))
    print('   傾き', sorted(float(r[1]) for r in d))
    print('   山', sorted(float(r[2]) for r in d))
