"""台帳が迷った箇所の正誤を、三村さんに聞かずに機械（LEGION のローカルモデル）が決める。
「私が何回も手作業したら無意味」「時間がかかっても良いので自動で精度向上していく仕組みを」（2026-10-29 三村さん）。

仕組み
- 機械には、同じ語を三村さんが**ほかの動画でどう書いたか**を前後の文ごと見本として渡す（公開版と、確認ページの答え）。
  囲碁用語の意味は go-dictionary-registration の辞書から添える。
- 語ごとに「その動画を除いた見本」で判断させて採点する（一つ抜き）。原則は機械に任せ、
  何も直さないより外れが多かった語だけ任せない（直さない方が当たる語が多い。2026-10-29 実測: 機械だけ 214/320・直さない 228/320）。
- 動画を公開するたびに見本と採点の材料が増え、任せられる語が増えていく。三村さんの作業は増えない。

  telop_judge.py eval [--cached]   # 採点して ledger/judge_score.json（任せる語の一覧）を書く
  telop_judge.py                   # 確認ページの全箇所を判断（ledger/judged.jsonl に追記。続きから）
1回で BATCH か所をまとめ、判断はすべて記録して続きから進める（時間がかかってもよい）。
"""
import csv, json, re, sys
from collections import defaultdict
from pathlib import Path
import telop_ledger as L

QS = L.LEDGER / 'page' / 'questions.json'
CACHE = L.LEDGER / 'judged.jsonl'
SCORE = L.LEDGER / 'judge_score.json'
VERSION = 4                    # 頼み方を変えたら上げる（古い判断は使わない）
# 判定役は LEGION のローカルモデル。Gemini 無料枠（1日20回）は字幕づくり（generate_ass.py）と取り合うので使わない。
# 遅くてよい（「時間がかかっても良い」2026-10-29 三村さん）。モデルを替えたら VERSION も上げる
import os
# 2026-10-29 同じ455か所で比較: Nemotron 日本語 283・qwen2.5:14b 256・gemma4 262（何も直さない 288）
DEFAULT = 'hf.co/mmnga-o/NVIDIA-Nemotron-Nano-9B-v2-Japanese-gguf:Q4_K_M'
OLLAMA, MODEL = 'http://localhost:11434', os.environ.get('TELOP_JUDGE_MODEL', DEFAULT)
if MODEL != DEFAULT:   # 比べるためのモデルは、本番の任せる語の一覧を上書きしない
    SCORE = L.LEDGER / f"judge_score_{re.sub(r'[^A-Za-z0-9.]+', '_', MODEL)}.json"
BATCH = 30
SHOTS = 8                      # 1語あたりの見本の数
MIN_N = 2                      # 任せないと決めるのに要る件数
PUNCT = re.compile(r'[、。，．,.!?！？…・「」『』（）()\s]')

SYSTEM = """囲碁の解説動画（話し手は囲碁棋士の三村智保九段）の字幕の校正をします。
音声認識の結果で【】で囲んだ所を、候補から1つ選んでください。
- いちばんの手がかりは「三村さんの過去の書き方」の見本です。同じ使われ方なら、見本と同じ書き方にそろえます
- 囲碁の意味で使っているときは、公開済みの字幕で多く使われている書き方にそろえます（三村さんの表記の決まり）
- 囲碁の手・盤上の話として使っているか、ふつうの言葉かを前後の文から判断します
- 見本と辞書のどちらからも決め手がなければ、【】の中身をそのまま選びます
- 自信の度合いを 0〜1 で添えます
"""


def norm(s):
    return PUNCT.sub('', s)


def glossary(words):
    p = Path.home() / 'projects' / 'go-dictionary-registration' / 'data' / 'master.csv'
    out = {}
    for r in csv.DictReader(open(p, encoding='utf-8')):
        if r['term_ja'] in words and r['category'] != 'person':
            out[r['term_ja']] = r['note'] or r['category']
    return out


def answers_from_page():
    folder = L.LEDGER / 'answers' / 'page'
    return {p.stem: json.load(open(p)) for p in folder.glob('*.json')} if folder.exists() else {}


def truth(q, answers):
    """答えの分かっている箇所の正解。確認ページの答え → 公開版で前後ごと一致する候補が1つだけ、の順。"""
    a = answers.get(q['id'])
    if a and a.get('answer') and a['answer'] in q['candidates'] + [q['wrong']]:
        return a['answer']
    if not q.get('published'):
        return None
    pub = norm(q['published'])
    hit = [c for c in q['candidates'] if norm(q['before'][-4:] + c + q['after'][:4]) in pub]
    return hit[0] if len(hit) == 1 else None


def shot_bank(qs, answers):
    """語 → [(動画, 見本の一文, 書き方)]。三村さんが決めた書き方の実例。"""
    bank = defaultdict(list)
    for q in qs:
        t = truth(q, answers)
        if t:
            bank[q['wrong']].append((q['video'], f"{q['before'][-30:]}【{t}】{q['after'][:20]}", t))
    return bank


_texts = None


def usage(form, exclude):
    """公開版でその書き方を使った回数（判断する動画は除く）。三村さんの表記の決まりを数で表す。"""
    global _texts
    if _texts is None:
        _texts = {v: ''.join(s['text'] for s in L.load(L.ROOT / p)) for v, p in json.load(open(L.SOURCES)).items()}
    return sum(x.count(form) for v, x in _texts.items() if v not in exclude)


def ask(items, bank):
    words = {q['wrong'] for q in items}
    gl = glossary({c for q in items for c in q['candidates']})
    parts = []
    if gl:
        parts.append('辞書の囲碁用語:\n' + '\n'.join(f'- {k}: {v}' for k, v in gl.items()))
    for w in sorted(words):
        vids = {q['video'] for q in items if q['wrong'] == w}
        ex = [s for s in bank.get(w, []) if s[0] not in vids][:SHOTS]   # 判断する動画そのものの答えは見せない
        if ex:
            parts.append(f'「{w}」の三村さんの過去の書き方:\n' + '\n'.join(f'- {s[1]}' for s in ex))
        forms = dict.fromkeys([w] + [c for q in items if q['wrong'] == w for c in q['candidates']])
        parts.append(f'「{w}」の候補を公開済みの字幕で使った回数: ' + ' / '.join(f'{c} {usage(c, vids)}回' for c in forms))
    lines = [f"{n}. {q['before'][-80:]}【{q['wrong']}】{q['after'][:60]}\n   候補: {' / '.join(dict.fromkeys([q['wrong']] + q['candidates']))}"
             for n, q in enumerate(items)]
    user = '\n\n'.join(parts + ['判断する箇所:\n' + '\n'.join(lines)])
    schema = {'type': 'array', 'items': {'type': 'object', 'properties': {
        'n': {'type': 'integer'}, 'answer': {'type': 'string'}, 'confidence': {'type': 'number'}},
        'required': ['n', 'answer', 'confidence']}}
    text = chat(user, {'type': 'object', 'properties': {'results': schema}, 'required': ['results']})
    if not text:
        return {}
    out = {}
    try:
        res = json.loads(text)['results']
    except (ValueError, KeyError, TypeError):
        return {}
    for r in res:
        if not isinstance(r, dict) or not {'n', 'answer', 'confidence'} <= r.keys() or not isinstance(r['n'], int):
            continue
        if 0 <= r['n'] < len(items):
            q = items[r['n']]
            if r['answer'] in q['candidates'] + [q['wrong']]:
                out[q['id']] = {'answer': r['answer'], 'confidence': r['confidence']}
    return out


def chat(user, schema):
    import urllib.request
    body = json.dumps({'model': MODEL, 'stream': False, 'format': schema, 'options': {'temperature': 0, 'num_ctx': 16384},
                       'messages': [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': user}]}).encode()
    try:
        r = urllib.request.urlopen(urllib.request.Request(OLLAMA + '/api/chat', body, {'Content-Type': 'application/json'}),
                                   timeout=900)
        return json.load(r)['message']['content']
    except Exception as e:
        print('  ローカルモデルの呼び出し失敗:', e)
        return None


def cached():
    if not CACHE.exists():
        return {}
    return {d['id']: d for d in (json.loads(l) for l in CACHE.open() if l.strip()) if d.get('v') == VERSION and d.get('m', 'qwen2.5:14b') == MODEL}


def judge(qs, limit=None):
    """まだ判断していない箇所を判断して追記する。同じ語をまとめて頼む（見本を共有できる）。limit は呼び出し回数の上限。"""
    bank = shot_bank(json.load(open(QS)), answers_from_page())
    done = cached()
    todo = sorted([q for q in qs if q['id'] not in done], key=lambda q: (q['wrong'], q['video']))
    calls = 0
    for i in range(0, len(todo), BATCH):
        if limit is not None and calls >= limit:
            break
        got = ask(todo[i:i + BATCH], bank)
        calls += 1
        if not got:
            print('判定役が答えなかった。続きは次回')
            break
        with CACHE.open('a') as f:
            for qid, d in got.items():
                d = {'id': qid, 'v': VERSION, 'm': MODEL, **d}
                done[qid] = d
                f.write(json.dumps(d, ensure_ascii=False) + '\n')
        print(f'{min(i + BATCH, len(todo))}/{len(todo)}', flush=True)
    return done


def excluded():
    """機械に任せない語（何も直さないより外れが多かった語）。採点がまだ無ければ None＝何も任せない。"""
    if not SCORE.exists():
        return None
    return {w for w, s in json.load(open(SCORE))['words'].items() if not s['delegate']}


def decide_now(items, video=''):
    """仕上げ中の動画の迷う箇所をその場で判断する。任せてよい語の判断だけ {id: 答え} で返す。"""
    ng = excluded()
    if ng is None:
        return {}
    items = [dict(q, video=video) for q in items if q['wrong'] not in ng]
    if not items:
        return {}
    bank = shot_bank(json.load(open(QS)), answers_from_page())
    out = {}
    for i in range(0, len(items), BATCH):
        out.update({k: d['answer'] for k, d in ask(items[i:i + BATCH], bank).items()})
    return out


def evaluate(fresh=True, limit=None):
    qs = json.load(open(QS))
    answers = answers_from_page()
    known = [(q, truth(q, answers)) for q in qs]
    known = [(q, t) for q, t in known if t]
    j = judge([q for q, _ in known], limit) if fresh else cached()
    rows = [(j[q['id']], t, q) for q, t in known if q['id'] in j]
    def tally(rs):
        words = defaultdict(lambda: {'n': 0, 'machine': 0, 'keep': 0})
        for d, tr, q in rs:
            s = words[q['wrong']]
            s['n'] += 1
            s['machine'] += d['answer'] == tr
            s['keep'] += q['wrong'] == tr
        for s in words.values():
            # 原則は機械に任せる。件数が足りていて、何も直さないより外れが多い語だけ任せない
            s['delegate'] = not (s['n'] >= MIN_N and s['machine'] < s['keep'])
        return words

    words = tally(rows)
    ng = {w for w, s in words.items() if not s['delegate']}
    m = sum(d['answer'] == tr for d, tr, q in rows)
    keep = sum(q['wrong'] == tr for d, tr, q in rows)
    # 正直な数字: その動画を除いた答えで任せる語を決め、その動画で当たるか（決めるのに使った答えで採点しない）
    mixed = 0
    for v in {q['video'] for _, _, q in rows}:
        ng = {w for w, s in tally([r for r in rows if r[2]['video'] != v]).items() if not s['delegate']}
        mixed += sum((d['answer'] if q['wrong'] not in ng else q['wrong']) == tr for d, tr, q in rows if q['video'] == v)
    json.dump({'version': VERSION, 'model': MODEL, 'known': len(known), 'judged': len(rows), 'machine': m, 'keep': keep,
               'mixed': mixed, 'words': dict(words)}, open(SCORE, 'w'), ensure_ascii=False, indent=1)
    print(f'正解の分かる箇所 {len(known)}・判断済み {len(rows)}')
    print(f'  全部機械 {m}・全部直さない {keep}・外れの多い語を除いて機械 {mixed}（任せない語 {len(ng)}: {"・".join(sorted(ng))}）')
    for w, s in sorted(words.items(), key=lambda x: -x[1]['n'])[:20]:
        print(f"  {w}: {s['n']}件 機械{s['machine']} 直さない{s['keep']}{'' if s['delegate'] else ' ← 任せない'}")
    return {'known': len(known), 'judged': len(rows), 'machine': m, 'keep': keep, 'mixed': mixed, 'excluded': len(ng)}


if __name__ == '__main__':
    if sys.argv[1:2] == ['eval']:
        evaluate(fresh='--cached' not in sys.argv)
    else:
        judge(json.load(open(QS)))
