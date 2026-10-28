"""三村さんに聞く確認ページの中身を作る。台帳にある動画（ledger/sources.json）と、仕上げ前の動画（ledger/pending.json）
について、台帳が「聞く」とした箇所と、台帳の自動の直しが公開版と食い違った箇所を集め、1か所ずつ音声を切り出す。

  telop_questions.py            # 全部の動画で作り直す → ledger/page/site/（index.html と clips.mp3）
  telop_questions.py VID ...    # その動画だけ
配るのは ledger/worker/deploy.sh。毎晩の一巡は telop_sync.py。
音声は作業フォルダの中から、文字起こしと長さの合うもの（audio.wav・raw.mp4 など）を自分で探す。
"""
import hashlib, json, subprocess, sys, wave
from pathlib import Path
import telop_ledger as L

PAGE = L.LEDGER / 'page'
SITE = PAGE / 'site'
PENDING = L.LEDGER / 'pending.json'   # 仕上げ前の動画 → 台帳をかけた文字起こし（generate_ass.py が書く）
MEDIA = ('audio.wav', 'rec/audio.wav', 'raw.mp4', 'cut.mp4', 'rec.mp4', '*_full.mp4', '*.mp4')


def duration(p):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(p)],
                         capture_output=True, text=True).stdout.strip()
    return float(out) if out else 0.0


def find_media(transcript, end):
    """文字起こしと同じ時間軸の音声。長さが文字起こしの終わり〜15秒後に収まるもの。"""
    for d in (transcript.parent, transcript.parent.parent):
        for pat in MEDIA:
            for p in sorted(d.glob(pat)):
                if end - 1 <= duration(p) <= end + 15:
                    return p
    return None


def published(vid):
    """公開版のある動画: (文字起こし, {区切り番号: 公開版の本文})。原文と最も多く対応のつく文字起こしを使う。"""
    work = L.ROOT / 'work' / vid
    final = L.load(work / 'refined_final.json')
    best = (None, {})
    for name in ('transcript.json', 'transcript_cut.json'):
        if not (work / name).exists():
            continue
        src = L.load(work / name)
        idx = {round(s['start'], 2): k for k, s in enumerate(src)}
        m = {}
        for f in final:
            k = f['i'] if 'i' in f and f['i'] < len(src) else idx.get(round(f['start'], 2))
            if k is not None:
                m[k] = f['text']
        if len(m) > len(best[1]):
            best = (work / name, m)
    return best


def word_time(seg, pos):
    """本文の pos 文字目を話している時刻。words が無ければ None。"""
    n = 0
    for st, en, w in seg.get('words', []):
        if n + len(w) > pos:
            return st
        n += len(w)
    return None


def clip(media, t, seg, out):
    if out.exists():
        return
    if t is None:   # 語の時刻が無い文字起こしは区切りごと（長すぎる区切りは頭の10秒）
        a, b = seg['start'] - 0.2, min(seg['end'] + 0.3, seg['start'] + 10)
    else:
        a = max(seg['start'] - 0.2, t - 2.5)
        b = max(min(seg['end'] + 0.3, t + 3.0), a + 2.0)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{max(a, 0):.2f}', '-to', f'{b:.2f}', '-i', str(media),
                    '-vn', '-ac', '1', '-c:a', 'aac', '-b:a', '48k', str(out)], check=True)


def videos():
    """(動画の名前, 文字起こし, {区切り: 公開版 or None})。公開版が None の区切りは仕上げ前＝「聞く」だけ出す。"""
    for vid in json.load(open(L.SOURCES)):
        tr, final = published(vid)
        if tr:
            yield vid, tr, final
    for vid, p in (json.load(open(PENDING)) if PENDING.exists() else {}).items():
        tr = L.ROOT / p
        if tr.exists():
            yield vid, tr, {k: None for k in range(len(L.load(tr)))}


def build(only=()):
    (PAGE / 'clips').mkdir(parents=True, exist_ok=True)
    qs, missing = [], []
    for vid, tr, final in videos():
        if only and vid not in only:
            continue
        segs = L.load(tr)
        media = find_media(tr, segs[-1]['end'])
        if media is None:
            missing.append(vid)
            continue
        ex, tg = L.examples(exclude=vid), L.taught()
        for k, s in enumerate(segs):
            if k not in final:
                continue
            log = []
            _, asks = L.process(s['text'], ex, tg, log)
            items = [{**x, 'type': 'ask'} for x in asks]
            # 台帳が直したのに、公開版にその形が無い＝どちらかが違う
            if final[k] is not None:
                items += [{**x, 'type': 'conflict', 'candidates': [x['right'], x['wrong']]}
                          for x in log if x['right'] not in final[k]]
            for x in items:
                t = s['text']
                # 作り直しても同じ箇所は同じ番号（保存済みの答えと食い違わない）
                qid = 'h' + hashlib.md5(f"{vid}|{k}|{x['wrong']}|{x['pos']}".encode()).hexdigest()[:10]
                clip(media, word_time(s, x['pos']), s, PAGE / 'clips' / f'{qid}.m4a')
                qs.append({'id': qid, 'video': vid, 'seg': k, 'type': x['type'], 'wrong': x['wrong'],
                           'prev': x['prev'], 'next': x['next'], 'candidates': x['candidates'][:4],
                           'before': t[:x['pos']], 'after': t[x['pos'] + len(x['wrong']):], 'published': final[k] or ''})
    json.dump(qs, open(PAGE / 'questions.json', 'w'), ensure_ascii=False, indent=1)
    print(f"{len(qs)} か所・{len({q['wrong'] for q in qs})} 語・{len({q['video'] for q in qs})} 本")
    if missing:
        print('音声が見つからない:', ', '.join(missing))
    return qs


def page(answered=()):
    """questions.json を template.html に埋め込んで site/index.html を書く。答えの済んだ箇所は載せない。"""
    qs = [q for q in json.load(open(PAGE / 'questions.json')) if q['id'] not in answered]
    ex = L.examples()
    stats = {}
    for q in qs:
        r = [x[2] for x in ex[q['wrong']]]
        stats[q['wrong']] = {'fixed': sum(x != q['wrong'] for x in r), 'kept': r.count(q['wrong'])}
    # 小ファイルを何百も配らず、1本につないで再生位置で切り替える
    tmp = PAGE / 'tmp'
    tmp.mkdir(exist_ok=True)
    SITE.mkdir(exist_ok=True)
    pos, parts = 0.0, []
    for q in qs:
        w = tmp / f"{q['id']}.wav"
        if not w.exists():
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(PAGE / 'clips' / f"{q['id']}.m4a"),
                            '-ac', '1', '-ar', '24000', str(w)], check=True)
        with wave.open(str(w)) as f:
            d = f.getnframes() / f.getframerate()
        q['clip'] = [round(pos, 3), round(d, 3)]
        pos += d
        parts.append(w)
    if parts:
        (tmp / 'list.txt').write_text(''.join(f"file '{w.name}'\n" for w in parts))
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(tmp / 'list.txt'),
                        '-c:a', 'libmp3lame', '-b:a', '48k', str(SITE / 'clips.mp3')], check=True)
    t = (PAGE / 'template.html').read_text()
    t = t.replace('/*DATA*/[]', json.dumps(qs, ensure_ascii=False)).replace('/*STATS*/{}', json.dumps(stats, ensure_ascii=False))\
        .replace('/*REVIEW*/[]', (PAGE / 'review.json').read_text() if (PAGE / 'review.json').exists() else '[]')
    (SITE / 'index.html').write_text(t)
    print(f'ledger/page/site/index.html {len(t) // 1024}KB・{len(qs)} か所')
    return qs


if __name__ == '__main__':
    build(sys.argv[1:])
    page()
