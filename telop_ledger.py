"""テロップの直しの台帳。Whisper 原文と確認済みの本文を突き合わせ、直した語を動画をまたいで積む。

誤りの中心は人名ではなく「囲碁用語の表記」と「囲碁用語か一般語かの判別」（2026-10-29 三村さん）。
一律置換は一般語を壊す（出る→デる・羽根→ハネの事故）ので、直した例だけでなく**直さずに残した例**も数える。
  - 一度も残された例が無い語（2本以上で直した・2字以上）… go_text_common.apply() が自動で直す
  - 残された例もある語（文脈しだい）………………………… 自動では直さない。flag で該当区切りを用例つきで拾う

使い方（video-studio の .venv で）:
  telop_ledger.py add work/20261028_suhyup2/finish   # その動画の直しを台帳に入れる（入れ直しても重複しない）
  telop_ledger.py add-all                           # work/ 以下を全部入れ直す
  telop_ledger.py report                            # ledger/report.md を作る
  telop_ledger.py flag work/xxx/transcript.json     # 文脈しだいの語を含む区切りを一覧（直す前の確認用）
  telop_ledger.py deny 主張 シチョウ                 # この組は自動で直さない
"""
import json, re, sys, difflib
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / 'ledger'
CHANGES = LEDGER / 'changes.jsonl'   # 直した組（動画・区切りごと）
SOURCES = LEDGER / 'sources.json'    # 台帳に入れた動画 → 確認済み本文のファイル
DENY = LEDGER / 'deny.tsv'           # 自動で直さない組（誤\t正）
AUTO = LEDGER / 'auto.tsv'           # 自動で直す組（report が書き出す。go_text_common が読む）

MIN_VIDEOS = 2   # 何本の動画で直したら自動にするか（三村さん「同じ指摘が2回来た語は共通へ」）
MAX_LEN = 12     # これより長い差分は言い直しの書き換えとみなし、語の直しに数えない
PUNCT = re.compile(r'[、。，．,.!?！？…・「」『』（）()\s]')

_tok = None


def tokens(text):
    global _tok
    if _tok is None:
        from janome.tokenizer import Tokenizer
        _tok = Tokenizer()
    return [w.surface for w in _tok.tokenize(text)]


def reading(text):
    tokens(text)
    return ''.join(w.reading if w.reading != '*' else w.surface for w in _tok.tokenize(text))


def load(p):
    s = json.load(open(p))
    return s if isinstance(s, list) else s['segments']


def pair_up(work):
    """確認済みの各区切りに Whisper 原文を対応づける。'i' があれば番号、なければ開始時刻で。"""
    final = load(work / 'refined_final.json')
    best = []
    for name in ('transcript.json', 'transcript_cut.json'):
        if not (work / name).exists():
            continue
        src = load(work / name)
        by_start = {round(s['start'], 2): s for s in src}
        pairs = []
        for f in final:
            s = src[f['i']] if 'i' in f and f['i'] < len(src) else by_start.get(round(f['start'], 2))
            if s is not None:
                pairs.append((s['text'], f['text']))
        if len(pairs) > len(best):
            best = pairs
    return final, best


def diffs(a, b):
    """原文 a → 本文 b の語単位の差分。句読点だけの違いは捨てる。prev/next は原文側の前後の語（文脈の目印）。"""
    ta, tb = tokens(a), tokens(b)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes():
        if op == 'equal':
            continue
        w, r = PUNCT.sub('', ''.join(ta[i1:i2])), PUNCT.sub('', ''.join(tb[j1:j2]))
        if not w or not r or w == r:
            continue
        out.append({'wrong': w, 'right': r, 'rewrite': max(len(w), len(r)) > MAX_LEN,
                    'prev': ta[i1 - 1] if i1 else '', 'next': ta[i2] if i2 < len(ta) else '',
                    'before': ''.join(tb[max(0, j1 - 3):j1]), 'after': ''.join(tb[j2:j2 + 3])})
    return out


def occurrences(text, words):
    """text の中で、語の切れ目にぴったり重なる words の出現を (語, 前の語, 次の語, 位置) で返す。"""
    tk = tokens(text)
    starts, pos = {}, 0
    for k, t in enumerate(tk):
        starts[pos] = k
        pos += len(t)
    starts[pos] = len(tk)
    out = []
    for w in words:
        i = text.find(w)
        while i >= 0:
            if i in starts and i + len(w) in starts:
                a, b = starts[i], starts[i + len(w)]
                out.append((w, tk[a - 1] if a else '', tk[b] if b < len(tk) else '', i))
            i = text.find(w, i + 1)
    return out


def read_changes():
    if not CHANGES.exists():
        return []
    return [json.loads(l) for l in CHANGES.open() if l.strip()]


def add(work):
    work = Path(work).resolve()
    vid = str(work.relative_to(ROOT / 'work'))
    final, pairs = pair_up(work)
    rows = [r for r in read_changes() if r['video'] != vid]
    n = 0
    for k, (a, b) in enumerate(pairs):
        for d in diffs(a, b):
            rows.append({'video': vid, 'seg': k, **d})
            n += 1
    LEDGER.mkdir(exist_ok=True)
    with CHANGES.open('w') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    src = json.load(open(SOURCES)) if SOURCES.exists() else {}
    src[vid] = str((work / 'refined_final.json').relative_to(ROOT))
    json.dump(src, open(SOURCES, 'w'), ensure_ascii=False, indent=1)
    print(f'{vid}: {len(final)}区切り中 {len(pairs)} を照合、直し {n} 件')


def add_all():
    for p in sorted((ROOT / 'work').glob('**/refined_final.json')):
        add(p.parent)


TAUGHT = LEDGER / 'taught.jsonl'  # 三村さんに聞いて教わった答え（いちばん強い）
MIN_SAME = 2                       # 同じ文脈で同じ扱いが何回あれば聞かずに従うか
LOW, HIGH = 0.1, 0.8               # 過去に直した割合がこれ以下なら残す／これ以上（直し先もそろう）なら直す。間は聞く


def taught(exclude=None):
    if not TAUGHT.exists():
        return []
    return [t for t in (json.loads(l) for l in TAUGHT.open() if l.strip()) if t.get('video') != exclude]


def examples(exclude=None):
    """語 → [(前の語, 次の語, 結果)]。結果は直した形、または一般語として残した形（＝語そのもの）。"""
    ex = defaultdict(list)
    for r in read_changes():
        if not r['rewrite'] and r['video'] != exclude:
            ex[r['wrong']].append((r['prev'], r['next'], r['right']))
    src = json.load(open(SOURCES)) if SOURCES.exists() else {}
    words = list(ex)
    for vid, p in src.items():
        if vid == exclude:
            continue
        for seg in load(ROOT / p):
            for w, a, b, _ in occurrences(seg['text'], words):
                ex[w].append((a, b, w))
    return ex


NUM = re.compile(r'^[0-9０-９一二三四五六七八九十百千]+$')


def key(tok):
    """文脈の目印。数字はまとめる（「8目」で教わった答えを「7目」にも効かせる）。"""
    return '#' if NUM.match(tok or '') else tok


def decide(w, prev, nxt, ex, tg):
    """(答え, 理由)。答えが None なら三村さんに聞く。"""
    k = (key(prev), key(nxt))
    for t in reversed(tg):
        if t['wrong'] == w and (t['scope'] == 'always' or (key(t['prev']), key(t['next'])) == k):
            return t['answer'], '教わった'
    same = [r for a, b, r in ex[w] if (key(a), key(b)) == k]
    if len(same) >= MIN_SAME and len(set(same)) == 1:
        return same[0], '同じ文脈'
    allr = [r for _, _, r in ex[w]]
    fixed = [r for r in allr if r != w]
    if len(fixed) <= len(allr) * LOW:
        return w, 'ほぼ残す'
    top = max(set(fixed), key=fixed.count)
    if len(allr) >= 3 and len(fixed) >= len(allr) * HIGH and fixed.count(top) >= len(fixed) * HIGH:
        return top, 'ほぼ直す'
    return None, ''


def process(text, ex, tg, log=None):
    """台帳で直した本文と、聞くことのリスト。長い語を優先し、重なりは取らない。log に自動の判断を積む。
    先に go_text_common（局←曲・教わった「いつも」）を通す＝決まっていることは聞かない。"""
    import go_text_common
    text = go_text_common.apply(text)
    occ, used = [], set()
    for o in sorted(occurrences(text, list(ex)), key=lambda o: -len(o[0])):
        span = set(range(o[3], o[3] + len(o[0])))
        if not span & used:
            used |= span
            occ.append(o)
    asks = []
    for w, a, b, i in sorted(occ, key=lambda o: -o[3]):
        ans, why = decide(w, a, b, ex, tg)
        if ans is None:
            cands = sorted({r for _, _, r in ex[w]}, key=lambda r: -sum(x[2] == r for x in ex[w]))
            asks.append({'wrong': w, 'prev': a, 'next': b, 'pos': i, 'candidates': cands})
        elif ans != w:
            text = text[:i] + ans + text[i + len(w):]
            if log is not None:
                log.append({'wrong': w, 'right': ans, 'why': why, 'prev': a, 'next': b, 'pos': i})
    return text, asks[::-1]


def cer(a, b):
    from rapidfuzz.distance import Levenshtein
    a, b = PUNCT.sub('', a), PUNCT.sub('', b)
    return Levenshtein.distance(a, b), max(len(b), 1)


def evaluate():
    """一つ抜き評価: その動画以外の台帳で、その動画の Whisper 原文をどこまで確認済みの本文に近づけられるか。"""
    src = json.load(open(SOURCES))
    print('動画 | 区切り | 誤り率 原文→台帳後 | 直りすぎ | 聞く数')
    tot = [0, 0, 0, 0, 0]
    for vid in src:
        ex, tg = examples(exclude=vid), taught(exclude=vid)
        _, pairs = pair_up(ROOT / 'work' / vid)
        e0 = e1 = n = worse = q = 0
        for a, b in pairs:
            fixed, asks = process(a, ex, tg)
            d0, m = cer(a, b)
            d1, _ = cer(fixed, b)
            e0, e1, n, q = e0 + d0, e1 + d1, n + m, q + len(asks)
            worse += d1 > d0
        tot = [tot[0] + e0, tot[1] + e1, tot[2] + n, tot[3] + worse, tot[4] + q]
        print(f'{vid} | {len(pairs)} | {e0 / n:.1%} → {e1 / n:.1%} | {worse} | {q}')
    print(f'合計 | | {tot[0] / tot[2]:.1%} → {tot[1] / tot[2]:.1%} | {tot[3]} | {tot[4]}')
    return {'before': tot[0] / tot[2], 'after': tot[1] / tot[2], 'worse': tot[3], 'asks': tot[4]}


def ask(transcript):
    """台帳で直した本文を *_ledger.json に書き、聞くことを ledger/questions.json に出す。"""
    ex, tg = examples(), taught()
    segs = load(transcript)
    qs = []
    for k, s in enumerate(segs):
        s['text'], asks = process(s['text'], ex, tg)
        for x in asks:
            t = s['text']
            qs.append({'seg': k, 'start': s['start'], **x,
                       'show': t[:x['pos']] + '【' + x['wrong'] + '】' + t[x['pos'] + len(x['wrong']):]})
    out = Path(transcript).with_name(Path(transcript).stem + '_ledger.json')
    json.dump(segs, open(out, 'w'), ensure_ascii=False, indent=1)
    json.dump(qs, open(LEDGER / 'questions.json', 'w'), ensure_ascii=False, indent=1)
    print(f'{out.name} を書いた。聞くこと {len(qs)} 件 → ledger/questions.json')


def apply_to(segs, transcript):
    """仕上げの流れ（generate_ass.py）から呼ぶ。台帳で直し、迷う箇所は確認ページに載るよう ledger/pending.json に登録する。"""
    import telop_judge
    ex, tg = examples(), taught()
    n = q = 0
    pending = []
    for k, s in enumerate(segs):
        before = s['text']
        s['text'], asks = process(s['text'], ex, tg)
        n, q = n + (s['text'] != before), q + len(asks)
        t = s['text']
        pending += [{'id': f'{k}:{x["pos"]}', 'seg': k, 'pos': x['pos'], 'wrong': x['wrong'], 'candidates': x['candidates'],
                     'before': t[:x['pos']], 'after': t[x['pos'] + len(x['wrong']):]} for x in asks]
    # 台帳が迷った箇所は機械が判断する（三村さんには聞かない）。後ろから置き換えて位置をずらさない
    got = telop_judge.decide_now(pending, video=str(Path(transcript).resolve().parent.name))
    for x in sorted(pending, key=lambda x: (x['seg'], -x['pos'])):
        a = got.get(x['id'])
        if a and a != x['wrong']:
            t = segs[x['seg']]['text']
            segs[x['seg']]['text'] = t[:x['pos']] + a + t[x['pos'] + len(x['wrong']):]
    print(f'機械の判断: {len(got)}/{len(pending)} か所を決めた（うち書き換え {sum(got[i] != x["wrong"] for x in pending for i in [x["id"]] if i in got)}）')
    tr = Path(transcript).resolve()
    if (ROOT / 'work') in tr.parents:
        pend = LEDGER / 'pending.json'
        d = json.load(open(pend)) if pend.exists() else {}
        d[str(tr.parent.relative_to(ROOT / 'work'))] = str(tr.relative_to(ROOT))
        json.dump(d, open(pend, 'w'), ensure_ascii=False, indent=1)
    print(f'台帳: {n} 区切りを直した。迷う箇所 {q} → 今夜の確認ページに載る')
    return segs


def teach(wrong, answer, scope='here', prev='', nxt='', video='', note=''):
    """三村さんの答えを入れる。scope=always（いつも）／here（この前後の語のときだけ）。answer=wrong なら「そのまま」。"""
    LEDGER.mkdir(exist_ok=True)
    with TAUGHT.open('a') as f:
        f.write(json.dumps({'wrong': wrong, 'answer': answer, 'scope': scope, 'prev': prev, 'next': nxt,
                            'video': video, 'note': note}, ensure_ascii=False) + '\n')


def import_answers(folder):
    """確認ページの答え（ArtifactData の out_dir に保存した *.json）を taught.jsonl に入れ直す。何度流しても同じになる。"""
    rows = [t for t in taught() if t.get('source') != 'page']
    context = set()   # 「いつも」の見直しで「囲碁の意味のときだけ」になった語
    for p in sorted(Path(folder).glob('**/*.json')):
        d = json.load(open(p))
        d = d.get('data', d)
        if d.get('scope') == 'review':
            if d.get('answer') == 'context':
                context.add(d['wrong'])
            continue
        if not d.get('answer'):
            continue
        rows.append({'wrong': d['wrong'], 'answer': d['answer'], 'scope': d['scope'], 'prev': d.get('prev', ''),
                     'next': d.get('next', ''), 'video': d.get('video', ''), 'note': p.stem, 'source': 'page'})
    rows = [t for t in rows if not (t['scope'] == 'always' and t['wrong'] in context)]
    LEDGER.mkdir(exist_ok=True)
    with TAUGHT.open('w') as f:
        for t in rows:
            f.write(json.dumps(t, ensure_ascii=False) + '\n')
    print(f"教わった答え {sum(t.get('source') == 'page' for t in rows)} 件（いつも {sum(t['scope'] == 'always' for t in rows)}）")


if __name__ == '__main__':
    cmd, *args = sys.argv[1:] or ['evaluate']
    {'add': add, 'add-all': add_all, 'evaluate': evaluate, 'ask': ask, 'teach': teach, 'import': import_answers}[cmd](*args)
