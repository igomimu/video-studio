"""（2026-11-07 囲碁は分かりにくい。元は11-05 中国ルール改正 1本目）テロップを refined_final.json から作る。元は10-29 ランキング番外編用。
三村さん指示「画面の最下部に、いつもよりも大きめフォントで」→ 84px（通常72）・下端。顔ワイプ（右下 x1420〜）を避けて x40〜1400 の中で中央寄せ、1行15字・最大2行。
"""
import json, re, unicodedata
from janome.tokenizer import Tokenizer
TOK = Tokenizer()
CONTENT = {'名詞', '動詞', '形容詞', '副詞', '連体詞', '接続詞', '感動詞', '接頭詞'}
FS, KFS = 84, 34           # 本文と読みの文字サイズ
MAXW = 16 * FS             # 1行の幅(px)。今回は右上の空きが広いので12字（10-29）
MAXC = 24                    # 1画面の字数（読みは数えない）
KANA = {}
BLUE, RED, WHITE = '{\\c&HFF9B7F&}', '{\\c&H5C6AFF&}', '{\\c&HFFFFFF&}'
# AI塗りの場面で色を付ける数字（開始秒の範囲, 文字列, 色）
COLOR = []
# 途中で改行しない語
UNIT = ['中国ルール', '日本ルール', '純碁ルール', '応昌期ルール', '19路盤', '6路盤', '19路', 'ファクトリ囲碁', '囲碁シル', '王銘琬九段', '日本囲碁規約', '呼吸点', '2026年', '10月15日', '430万回', '225万回', '300万回', '1,076', '3,500', '2,000', '2.8倍', 'みむいご通信', 'チャンネル登録', '三村智保', 'ニュースレター', 'ホットトピック', 'サブセット', 'Twitter']

def cw(c):
    return FS // 2 if unicodedata.east_asian_width(c) in 'NaH' else FS

def tokens(text):
    """表示単位に分ける。人名＋読みは1単位（途中で改行しない）"""
    out, i = [], 0
    while i < len(text):
        for k, v in KANA.items():
            if text.startswith(k, i):
                if v:
                    out.append((k, len(k) * FS + (len(v) + 2) * KFS, k + '{\\fs%d}（%s）{\\fs%d}' % (KFS, v, FS)))
                else:  # 尹初段・権道場は1字目にだけ読み
                    kk = {'尹': 'ユン', '権': 'クォン'}[k[0]]
                    out.append((k, 3 * FS + (len(kk) + 2) * KFS, k[0] + '{\\fs%d}（%s）{\\fs%d}' % (KFS, kk, FS) + k[1:]))
                i += len(k); break
        else:
            u = next((u for u in UNIT if text.startswith(u, i)), None)
            if u:
                out.append((u, sum(cw(c) for c in u), u)); i += len(u)
            else:
                out.append((text[i], cw(text[i]), text[i])); i += 1
    return out

NOBREAK_BEFORE = set('、。，．？！）」』ゃゅょっぁぃぅぇぉャュョッァィゥェォー')

MAXLINES = 2

def okbreak(t, i):
    if t[i][0][0] in NOBREAK_BEFORE: return False
    # 「でしょう\Nか。」「んです\Nが、」のように文末の1字だけ次の行に落とさない（10-28）
    if t[i][0] in ('か', 'が', 'ね', 'よ', 'な') and (i + 1 == len(t) or t[i + 1][0][0] in '、。？！'): return False
    a, b = t[i - 1][0][-1], t[i][0][0]
    if a.isdigit() and (b.isdigit() or b == '.'): return False
    return True

def kind(c):
    if c in '、。？！，': return 'P'
    if re.match(r'[ぁ-ゖ]', c): return 'H'
    if re.match(r'[ァ-ヶー]', c): return 'K'
    if re.match(r'[0-9.]', c): return 'D'
    return 'J'  # 漢字など

def brk_cost(a, b):
    """a|b で改行するときの罰点。句読点の後はほぼ無料、語の途中は高い"""
    ka, kb = kind(a), kind(b)
    if ka == 'P': return -200
    if ka == 'H' and kb in 'JKD': return 40      # 助詞の後で次の語へ
    if ka in 'JKD' and kb == 'H': return 400     # 送り仮名・活用の途中
    if ka == kb: return 600                     # 同じ字種の途中＝語の途中
    return 150

def boundaries(text):
    """文字位置 -> 改行の罰点。文節の頭は0、句読点の後は-200、それ以外は語の途中"""
    cost, pos, prev = {}, 0, None
    for tk in TOK.tokenize(text):
        p, sub = tk.part_of_speech.split(',')[:2]
        if pos > 0 and sub in ('接尾', '非自立'): cost[pos] = 2000
        elif pos > 0:
            if prev == '記号': cost[pos] = -200
            elif p in CONTENT and prev in ('助詞', '助動詞'): cost[pos] = 0
            elif p in CONTENT and prev in CONTENT: cost[pos] = 500
            else: cost[pos] = 2000
        pos += len(tk.surface); prev = p
    return cost

def wrap(text, strict=False):
    """3行以内で、行の長さがそろい、句読点の直後で切れる改行を選ぶ"""
    t = tokens(text)
    bc = boundaries(text)
    cpos = [0]
    for k, _, _ in t: cpos.append(cpos[-1] + len(k))
    n = len(t)
    pre = [0]
    for _, w, _ in t: pre.append(pre[-1] + w)
    if pre[n] <= MAXW: return [t]
    import functools
    if not strict:
        r = wrap(text, True)
        if r: return r
    @functools.lru_cache(None)
    def best(i, k):  # t[i:] を k 行以内で組む最小コスト
        if pre[n] - pre[i] <= MAXW: return (0, (n,))
        if k == 1: return None
        res = None
        for j in range(i + 1, n):
            w = pre[j] - pre[i]
            if w > MAXW: break
            if not okbreak(t, j): continue
            if strict and bc.get(cpos[j], 2000) >= 1000: continue
            r = best(j, k - 1)
            if r is None: continue
            a = t[j - 1][0][-1]
            c = r[0] + (MAXW - w) ** 2 / 4000 + bc.get(cpos[j], 2000)
            if res is None or c < res[0]: res = (c, (j,) + r[1])
        return res
    r = best(0, MAXLINES)
    if r is None: return None
    cuts, prev, out = r[1], 0, []
    for c in cuts: out.append(t[prev:c]); prev = c
    return out

def fits1(text):
    """1枚（MAXLINES 行まで）に収まるか"""
    r = wrap(text, True)
    return bool(r) and len(r) == 1   # 極力1行（2026-10-22 三村さん「無意味に二行になるのを避ける」）


def render(lines):
    return '\\N'.join(''.join(r for _, _, r in ln) for ln in lines)

def plain_len(s):
    return len(s)

def attaches(text):
    """前の語にくっつく語（助詞・助動詞・非自立語・接尾）で始まるか"""
    tk = next(iter(TOK.tokenize(text)), None)
    if tk is None: return False
    p, sub = tk.part_of_speech.split(',')[:2]
    return p in ('助詞', '助動詞') or sub in ('非自立', '接尾')

s = json.load(open('refined_final.json'))
# 1) 短い区切りをつなぐ
ev = []
for x in s:
    x = dict(x)
    if ev:
        p = ev[-1]
        joined = p['text'] + x['text']
        if p['text'].endswith('、') and attaches(x['text']):
            joined = p['text'][:-1] + x['text']   # 「取る、しかない」→「取るしかない」
        if (x['start'] - p['end'] < 0.8 and fits1(joined)
                and not (p['text'].endswith('。') and plain_len(p['text']) >= 8)):
            p['text'] = joined; p['end'] = x['end']; continue
    ev.append(x)
# 2) 長いものは2行ずつに割る（時間は字数で按分）
out = []
for x in ev:
    text = x['text']
    if fits1(text):
        out.append(x); continue
    # 句読点で区切り、それでも長い塊は文節の切れ目で区切ってから、2〜3行ずつ詰める
    chunks = []
    for piece in re.findall(r'[^、。？！]+[、。？！]?', text):
        if fits1(piece):
            chunks.append(piece); continue
        bc = boundaries(piece)
        cuts = [0] + sorted(k for k, v in bc.items() if v <= 0) + [len(piece)]
        for c in [piece[i:j] for i, j in zip(cuts, cuts[1:]) if j > i]:
            # 文節で切っても1行に入らない塊は、語の切れ目のうち罰点が小さく長さがそろう所で2つに割る
            # （「ナンバーワンということ／で」のように1字だけ次の行に落ちるのを防ぐ。10-29）
            if fits1(c):
                chunks.append(c); continue
            b2 = boundaries(c)
            best = min(((b2.get(j, 4000) + (3000 if c[j - 1] == 'っ' else 0) + abs(len(c) - 2 * j) * 30 + (1000 if min(j, len(c) - j) < 3 else 0), j)
                        for j in range(1, len(c)) if c[j] not in NOBREAK_BEFORE and fits1(c[:j]) and fits1(c[j:])), default=None)
            if best: chunks += [c[:best[1]], c[best[1]:]]
            else: chunks.append(c)
    # 詰め方は、画面の数が最少で、長さがそろい、4字未満の画面ができない組み方を選ぶ（11-05: 貪欲に詰めると「人、」が1枚になった）
    import functools
    @functools.lru_cache(None)
    def pack(i):
        if i == len(chunks): return (0, ())
        best = None
        for j in range(i + 1, len(chunks) + 1):
            g = ''.join(chunks[i:j])
            if not fits1(g): break
            r = pack(j)
            if r is None: continue
            c = 10 ** 6 + (16 - len(g)) ** 2 * 100 + (10 ** 5 if len(g) < 4 else 0) + r[0]
            if best is None or c < best[0]: best = (c, (g,) + r[1])
        return best
    r = pack(0)
    parts = list(r[1]) if r else chunks
    t0, dur, L = x['start'], x['end'] - x['start'], sum(map(len, parts))
    for p in parts:
        d = dur * len(p) / L
        out.append({'start': t0, 'end': t0 + d, 'text': p}); t0 += d
# 3) 間を埋める・最短表示
for i, x in enumerate(out):
    nxt = out[i + 1]['start'] if i + 1 < len(out) else x['end'] + 2
    if nxt - x['end'] < 1.0: x['end'] = nxt
    x['end'] = min(max(x['end'], x['start'] + 1.0), nxt)

def ts(t):
    h, m = int(t // 3600), int(t % 3600 // 60)
    return f'{h}:{m:02d}:{t % 60:05.2f}'

FULL = (0, 0)   # 投稿版は右上。次回から碁盤が無い動画は下の中央（feedback_telop_position_no_board）
lines = []
for x in out:
    body = render(wrap(x['text']))
    for (a, b), key, col in COLOR:
        if x['start'] <= b and x['end'] >= a and key in body and WHITE + key not in body:
            if col == 'B63': body = body.replace('63対', BLUE + '63' + WHITE + '対', 1)
            elif col + key not in body: body = body.replace(key, col + key + WHITE, 1)
    st = 'Shita2'
    lines.append(f'Dialogue: 0,{ts(x["start"])},{ts(x["end"])},{st},,0,0,0,,{body}')

head = open('telops.ass').read().split('[Events]')[0]
head = re.sub(r'^Style: Migiue,Noto Sans CJK JP,\d+,', f'Style: Migiue,Noto Sans CJK JP,{FS},', head, flags=re.M)
head = re.sub(r'^(Style: Migiue,.*,3,14,0,)\d,\d+,\d+,\d+,1$', r'\g<1>8,990,30,40,1', head, flags=re.M)
head = re.sub(r'^Style: Shita2,.*\n', '', head, flags=re.M)
head = re.sub(r'(^Style: Shita,.*$)', lambda m: m.group(1) + '\nStyle: Shita2,Noto Sans CJK JP,%d,&H00FFFFFF,&H000000FF,&H00384030,&H00384030,-1,0,0,0,100,100,0,0,3,14,0,2,40,520,24,1' % FS, head, count=1, flags=re.M)
open('telops.ass', 'w').write(head + '[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n' + '\n'.join(lines) + '\n')
d = [x['end'] - x['start'] for x in out]
print(len(out), '平均表示秒', round(sum(d) / len(d), 2), '1秒未満', sum(1 for v in d if v < 1.0))
