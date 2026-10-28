"""三村さんに聞く確認ページの中身を作る。音声のある動画について、台帳が「聞く」とした箇所と、
台帳の自動の直しが公開版と食い違った箇所を集め、1か所ずつ音声を切り出す。

  telop_questions.py work/20261027_suhyup1 work/20261028_suhyup2
  → ledger/page/questions.json と ledger/page/clips/*.m4a。ページは ledger/page/index.html（同じ JSON を埋め込む）
音声は <作業>/audio.wav、文字起こしは <作業>/finish/transcript.json（同じ時間軸）、公開版は refined_final.json（'i' で対応）
"""
import json, subprocess, sys
from pathlib import Path
import telop_ledger as L

PAGE = L.LEDGER / 'page'


def word_time(seg, pos):
    """本文の pos 文字目を話している時刻。words が無ければ区切りの中央。"""
    n = 0
    for st, en, w in seg.get('words', []):
        if n + len(w) > pos:
            return st
        n += len(w)
    return (seg['start'] + seg['end']) / 2


def clip(audio, t, seg, out):
    a = max(seg['start'] - 0.2, t - 2.5)
    b = max(min(seg['end'] + 0.3, t + 3.0), a + 2.0)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{a:.2f}', '-to', f'{b:.2f}', '-i', str(audio),
                    '-ac', '1', '-c:a', 'aac', '-b:a', '48k', str(out)], check=True)


def build(works):
    (PAGE / 'clips').mkdir(parents=True, exist_ok=True)
    qs = []
    for w in works:
        w = Path(w).resolve()
        vid = str((w / 'finish').relative_to(L.ROOT / 'work'))
        ex, tg = L.examples(exclude=vid), L.taught()
        segs = L.load(w / 'finish' / 'transcript.json')
        final = {f['i']: f['text'] for f in L.load(w / 'finish' / 'refined_final.json') if 'i' in f}
        for k, s in enumerate(segs):
            if k not in final:
                continue
            log = []
            _, asks = L.process(s['text'], ex, tg, log)
            items = [{**x, 'type': 'ask'} for x in asks]
            # 台帳が直したのに、公開版にその形が無い＝どちらかが違う
            items += [{**x, 'type': 'conflict', 'candidates': [x['right'], x['wrong']]}
                      for x in log if x['right'] not in final[k]]
            for x in items:
                t = s['text']
                qid = f'q{len(qs):03d}'
                clip(w / 'audio.wav', word_time(s, x['pos']), s, PAGE / 'clips' / f'{qid}.m4a')
                qs.append({'id': qid, 'video': vid, 'seg': k, 'type': x['type'], 'wrong': x['wrong'],
                           'prev': x['prev'], 'next': x['next'], 'candidates': x['candidates'][:4],
                           'before': t[:x['pos']], 'after': t[x['pos'] + len(x['wrong']):], 'published': final[k]})
    json.dump(qs, open(PAGE / 'questions.json', 'w'), ensure_ascii=False, indent=1)
    by = {}
    for q in qs:
        by.setdefault(q['wrong'], 0)
        by[q['wrong']] += 1
    print(f'{len(qs)} か所・{len(by)} 語:', sorted(by.items(), key=lambda x: -x[1])[:30])


if __name__ == '__main__':
    build(sys.argv[1:])
    page()


def page():
    """questions.json を template.html に埋め込んで index.html を書く。"""
    qs = json.load(open(PAGE / 'questions.json'))
    ex = L.examples()
    stats = {}
    for q in qs:
        r = [x[2] for x in ex[q['wrong']]]
        stats[q['wrong']] = {'fixed': sum(x != q['wrong'] for x in r), 'kept': r.count(q['wrong'])}
    # 261個の小ファイルは公開の上限（1回255個）にかかるので、1本につないで再生位置で切り替える
    import wave
    tmp = PAGE / 'tmp'
    tmp.mkdir(exist_ok=True)
    pos, parts = 0.0, []
    for q in qs:
        w = tmp / f"{q['id']}.wav"
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(PAGE / 'clips' / f"{q['id']}.m4a"), '-ac', '1', '-ar', '24000', str(w)], check=True)
        with wave.open(str(w)) as f:
            d = f.getnframes() / f.getframerate()
        q['clip'] = [round(pos, 3), round(d, 3)]
        pos += d
        parts.append(w)
    (tmp / 'list.txt').write_text(''.join(f"file '{w.name}'\n" for w in parts))
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(tmp / 'list.txt'),
                    '-c:a', 'libmp3lame', '-b:a', '48k', str(PAGE / 'clips.mp3')], check=True)
    t = (PAGE / 'template.html').read_text()
    t = t.replace('/*DATA*/[]', json.dumps(qs, ensure_ascii=False)).replace('/*STATS*/{}', json.dumps(stats, ensure_ascii=False))
    (PAGE / 'index.html').write_text(t)
    print('ledger/page/index.html', len(t) // 1024, 'KB')
