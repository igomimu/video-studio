"""韓国棋士の名前を、文字起こしのカタカナ読みから漢字に直す（「キム・ウンジ・クダン」→「金恩持九段」）。
材料は kishi-data のハングル名と漢字名の対応（data/world/korea_players.json × data/world_kishi.csv）。
カタカナ読みはハングルから機械的に作るので、棋士が増えても手で表を足さなくてよい。"""
import csv, json, re
from pathlib import Path

KISHI = Path.home() / 'projects' / 'kishi-data' / 'data'
INI = ['k', 'kk', 'n', 't', 'tt', 'r', 'm', 'p', 'pp', 's', 'ss', '', 'ch', 'jj', 'CH', 'K', 'T', 'P', 'h']  # 大文字＝息の強い音（濁らない）
VOW = ['a', 'e', 'ya', 'ye', 'o', 'e', 'yo', 'ye', 'o', 'wa', 'we', 'we', 'yo', 'u', 'wo', 'we', 'wi', 'yu', 'u', 'ui', 'i']
FIN = ['', 'k', 'k', 'k', 'n', 'n', 'n', 't', 'l', 'k', 'm', 'l', 'l', 'l', 'p', 'l', 'm', 'p', 'p', 't', 't', 'ng', 't', 't', 'k', 't', 'p', 't']
FIN_KANA = {'': '', 'k': 'ク', 'n': 'ン', 't': 'ッ', 'l': 'ル', 'm': 'ム', 'p': 'プ', 'ng': 'ン'}
VOICED = {'k': 'g', 't': 'd', 'ch': 'j', 'p': 'b'}   # 名前の2字目以降は濁る（ジン・ジョン・ウンジ）
ROW = {'': 'アイウエオ', 'k': 'カキクケコ', 'g': 'ガギグゲゴ', 's': 'サシスセソ', 'n': 'ナニヌネノ', 'h': 'ハヒフヘホ',
       'p': 'パピプペポ', 'b': 'バビブベボ', 'm': 'マミムメモ', 'r': 'ラリルレロ'}
SPECIAL = {  # 行の表で作れないもの（子音, 母音）
    ('ch', 'a'): 'チャ', ('ch', 'i'): 'チ', ('ch', 'u'): 'チュ', ('ch', 'e'): 'チェ', ('ch', 'o'): 'チョ',
    ('j', 'a'): 'ジャ', ('j', 'i'): 'ジ', ('j', 'u'): 'ジュ', ('j', 'e'): 'ジェ', ('j', 'o'): 'ジョ',
    ('t', 'a'): 'タ', ('t', 'i'): 'ティ', ('t', 'u'): 'トゥ', ('t', 'e'): 'テ', ('t', 'o'): 'ト',
    ('d', 'a'): 'ダ', ('d', 'i'): 'ディ', ('d', 'u'): 'ドゥ', ('d', 'e'): 'デ', ('d', 'o'): 'ド',
    ('ch', 'we'): 'チェ', ('j', 'we'): 'ジェ', ('ch', 'wa'): 'チャ', ('j', 'wa'): 'ジャ',
    ('h', 'wa'): 'ファ', ('h', 'we'): 'フェ', ('h', 'wi'): 'フィ', ('h', 'wo'): 'フォ', ('s', 'i'): 'シ',
    ('', 'wa'): 'ワ', ('', 'wo'): 'ウォ', ('', 'we'): 'ウェ', ('', 'wi'): 'ウィ', ('', 'ui'): 'ウィ',
    ('', 'ya'): 'ヤ', ('', 'yu'): 'ユ', ('', 'yo'): 'ヨ', ('', 'ye'): 'イェ',
}
Y_KANA = {'a': 'ャ', 'u': 'ュ', 'o': 'ョ', 'e': 'ェ'}


def syllable(c, v):
    if (c, v) in SPECIAL:
        return SPECIAL[(c, v)]
    if v in ('ya', 'yu', 'yo', 'ye'):   # キャ・ヒョ など
        base = SPECIAL.get((c, 'i')) or ROW.get(c, ROW[''])[1]
        return base.rstrip('ィ') + Y_KANA[v[1]] if not base.endswith('ィ') else base[:-1] + Y_KANA[v[1]]
    if v in ('wa', 'wo', 'we', 'wi', 'ui'):  # クァ・グォ など
        return ROW.get(c, ROW[''])[2] + {'wa': 'ァ', 'wo': 'ォ', 'we': 'ェ', 'wi': 'ィ', 'ui': 'ィ'}[v]
    return ROW.get(c, ROW[''])['aiueo'.index(v)]


def katakana(hangul):
    out = []
    for n, ch in enumerate(hangul):
        code = ord(ch) - 0xAC00
        if not 0 <= code < 11172:
            return None
        i, v, f = code // 588, (code % 588) // 28, code % 28
        c = {'kk': 'k', 'tt': 't', 'pp': 'p', 'ss': 's', 'jj': 'ch'}.get(INI[i], INI[i])
        if n and c in VOICED:
            c = VOICED[c]
        c = c.lower()
        out.append(syllable(c, VOW[v]) + FIN_KANA[FIN[f]])
    return out


_map = None


def names():
    """カタカナ読み（つなげた形）→ 漢字名。姓だけ・2字だけの短い読みは一般語とぶつかるので入れない。"""
    global _map
    if _map is None:
        _map = {}
        pairs = []
        try:
            kanji = {r['id']: r['名前'] for r in csv.DictReader(open(KISHI / 'world_kishi.csv', encoding='utf-8'))}
            for p in json.load(open(KISHI / 'world' / 'korea_players.json', encoding='utf-8'))['players']:
                if kanji.get('korea_' + p['id']):
                    pairs.append((p.get('name_kr') or '', kanji['korea_' + p['id']]))
        except (OSError, ValueError, KeyError):
            pass
        try:   # 次に韓国棋院の全棋士（眞・勳など旧字体が多いので、字幕で使ってきた上の表を優先）（ハングル・漢字）。同名の区別に (大)(小) が付いたものは読みが同じになるので外す
            for r in csv.DictReader(open(KISHI / 'baduk_all_players.csv', encoding='utf-8')):
                if '(' not in r['name_kr'] and r['kanji']:
                    pairs.append((r['name_kr'].replace(' ', ''), r['kanji']))
        except OSError:
            pass
        for hg, kj in pairs:
            k = katakana(hg)
            if k and len(''.join(k)) >= 4:
                _map.setdefault(''.join(k), kj.translate(NEW_FORM))
    return _map


KANJI_NUM = str.maketrans('123456789１２３４５６７８９', '一二三四五六七八九一二三四五六七八九')
NEW_FORM = str.maketrans('吳眞勳', '呉真勲')   # 字幕は新字体（公開版: 呉侑珍 7・吳侑珍 0）


DAN = {'ショダン': '初段', 'ニダン': '二段', 'サンダン': '三段', 'ヨダン': '四段', 'ゴダン': '五段', 'ロクダン': '六段',
       'ナナダン': '七段', 'ハチダン': '八段', 'クダン': '九段', 'キュウダン': '九段'}


def apply(t):
    m = names()
    if not m:
        return t
    # カタカナの並び（中黒・空白をはさむ）を1つの塊として見て、棋士名の読みで始まる所を漢字にする
    def fix(mt):
        run = re.sub(r'[・･\s、]', '', mt.group(0))
        for k in sorted(m, key=len, reverse=True):
            if run.startswith(k):
                rest = run[len(k):]
                return m[k] + DAN.get(rest, rest)
        return mt.group(0)
    # 区切りは中黒・空白に加え読点も（Whisper は「キム、ウンジ、クダン」と書く）。公開版を変えないことは全動画で確認済み
    t = re.sub(r'[ァ-ヶー]+(?:[・･\s、][ァ-ヶー]+)*', fix, t)
    # 名前のすぐ後の段位（「李晶媛、初弾」「許瑞玹、5段」「崔序妃ー3弾」）。「第3弾」など名前の後でないものは触らない
    who = '|'.join(map(re.escape, sorted(set(m.values()), key=len, reverse=True)))
    return re.sub(rf'({who})(、?)ー?([初二三四五六七八九1-9１-９])[弾談段]',
                  lambda x: x.group(1) + x.group(2) + x.group(3).translate(KANJI_NUM) + '段', t)


if __name__ == '__main__':
    m = names()
    print(len(m), '人')
    for k, v in list(m.items())[:3]:
        print(k, v)
    for k in ('金恩持', '申真諝', '朴廷桓', '崔精', '卞相壹'):
        print(k, [a for a, b in m.items() if b == k])
    for s in ('キム・ウンジ・クダン', 'キムウンジさん', 'シンジンソさんが', 'パク・ジョンファン九段', 'チェ・ジョンさん', 'コウダテ'):
        print(s, '→', apply(s))
