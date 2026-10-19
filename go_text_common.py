"""全動画に共通する文字起こしの直しと、出してはいけない字の検査。
動画ごとの fix_text.py は、自分の直しのあとに必ず apply() と check() を通す。
（2026-10-19 三村さん「曲は絶対囲碁では使わない」「何度直しても出てくる」→ 動画ごとの表に頼らずここに置く）"""
import re

# (正規表現, 置き換え) 上から順に適用
COMMON = [
    (r'([0-9０-９一二三四五六七八九十]|本|対|終|大|名|好|全|当|今|同|次|前|後|この|その|あの|反則負けの|勝負の)曲', r'\1局'),  # 一曲・1曲・本曲 → 局
    (r'曲(?!が)', '局'),          # 残った「曲」も局（「曲がり四目」「曲がる」の曲がだけ残す）
    (r'1局', '一局'),
]

# 出たら止める（直し忘れ）
BANNED = [
    (r'曲(?!が)', '「曲」は囲碁では使わない → 局'),
]


def apply(t):
    for a, b in COMMON:
        t = re.sub(a, b, t)
    return t


def check(texts):
    bad = [(i, t, why) for i, t in enumerate(texts) for pat, why in BANNED if re.search(pat, t)]
    for i, t, why in bad:
        print(f'NG #{i}: {t}  … {why}')
    if bad:
        raise SystemExit(f'禁止の字が {len(bad)} か所残っています')
