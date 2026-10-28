"""全動画に共通する文字起こしの直しと、出してはいけない字の検査。
動画ごとの fix_text.py は、自分の直しのあとに必ず apply() と check() を通す。
（2026-10-19 三村さん「曲は絶対囲碁では使わない」「何度直しても出てくる」→ 動画ごとの表に頼らずここに置く）"""
import re

# (正規表現, 置き換え) 上から順に適用
COMMON = [
    (r'([0-9０-９一二三四五六七八九十]|本|対|終|大|名|好|全|当|今|同|次|前|後|この|その|あの|反則負けの|勝負の)曲', r'\1局'),  # 一曲・1曲・本曲 → 局
    (r'曲(?![がげ])', '局'),       # 残った「曲」も局（「曲がり四目」「曲がる」「曲げる」は残す）
    (r'1局', '一局'),
    (r'危機', '利き'),            # 2026-10-28「危機☓ 利き◯」（Whisper が「キキ」を危機と書く）
    (r'キキ', '利き'),
    (r'(?<![ァ-ヶー])キリ(?![ァ-ヶー])', '切り'),  # 2026-10-28「切りに関しては何故か漢字がしっくり来る」名詞も漢字（ハッキリ・スッキリは残す）
    (r'キラ(?=れ)', '切ら'),
    (r'キ(?=[らりるれろっ])', '切'),  # 動詞は漢字（台帳: キリ／切る）。キる・キって → 切る・切って
]

# 出たら止める（直し忘れ）
BANNED = [
    (r'曲(?![がげ])', '「曲」は囲碁では使わない → 局'),
]


def taught_always():
    """telop_ledger.py の台帳で三村さんが「いつも」と答えた語（確認ページ・直接の指示）。"""
    import json, pathlib
    p = pathlib.Path(__file__).resolve().parent / 'ledger' / 'taught.jsonl'
    if not p.exists():
        return []
    rows = [json.loads(l) for l in p.open() if l.strip()]
    return [(r['wrong'], r['answer']) for r in rows if r['scope'] == 'always' and r['answer'] != r['wrong']]


def apply(t):
    for a, b in COMMON:
        t = re.sub(a, b, t)
    for a, b in taught_always():
        t = t.replace(a, b)
    return t


def check(texts):
    bad = [(i, t, why) for i, t in enumerate(texts) for pat, why in BANNED if re.search(pat, t)]
    for i, t, why in bad:
        print(f'NG #{i}: {t}  … {why}')
    if bad:
        raise SystemExit(f'禁止の字が {len(bad)} か所残っています')
