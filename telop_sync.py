"""テロップの台帳を毎晩ひと回りさせる（LEGION の telop-sync.timer）。三村さんの手は確認ページで答えることだけ。

  1. 確認ページ（Cloudflare の telop-check）から答えを取ってくる → taught.jsonl
  2. 公開版（refined_final.json）が増えた・直った動画を台帳に入れ直す → changes.jsonl
  3. 一つ抜き評価をして ledger/history.tsv に1行足す
  4. まだ聞いていない箇所でページを作り直して配る
  5. 台帳を commit & push
鍵は ~/.secrets/telop-check.env（TELOP_KEY・TELOP_URL）と ~/.secrets/cloudflare-ai.env。
"""
import json, os, subprocess, sys, time, urllib.request
from pathlib import Path
import telop_ledger as L
import telop_questions as Q

ANS = L.LEDGER / 'answers' / 'page'
HISTORY = L.LEDGER / 'history.tsv'


def env(path):
    out = {}
    for line in Path(path).expanduser().read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k, v = line.split('=', 1)
            out[k.strip()] = v.strip().strip('"')
    return out


def fetch_answers(cfg):
    req = urllib.request.Request(cfg['TELOP_URL'] + '/api/answers', headers={'X-Key': cfg['TELOP_KEY'], 'User-Agent': 'telop-sync/1'})
    data = json.load(urllib.request.urlopen(req, timeout=60))
    ANS.mkdir(parents=True, exist_ok=True)
    for p in ANS.glob('*.json'):
        p.unlink()
    for i, d in data.items():
        json.dump(d, open(ANS / f'{i}.json', 'w'), ensure_ascii=False)
    return data


def git(*a):
    return subprocess.run(['git', '-C', str(L.ROOT), *a], capture_output=True, text=True)


def main():
    cfg = env('~/.secrets/telop-check.env')
    answers = fetch_answers(cfg)
    print(f'答え {len(answers)} 件を取得')
    L.import_answers(ANS)
    L.add_all()
    # 公開版ができた動画は「仕上げ前」から外す
    if Q.PENDING.exists():
        src = json.load(open(L.SOURCES))
        pend = {k: v for k, v in json.load(open(Q.PENDING)).items() if k not in src}
        json.dump(pend, open(Q.PENDING, 'w'), ensure_ascii=False, indent=1)
    r = L.evaluate()
    Q.build()
    qs = Q.page(answered={i for i, d in answers.items() if d.get('answer')})
    new = not HISTORY.exists()
    with HISTORY.open('a') as f:
        if new:
            f.write('日時\t動画数\t教わった答え\t誤り率(原文)\t誤り率(台帳後)\t悪化\t聞く(評価)\t確認ページ\n')
        f.write(f"{time.strftime('%Y-%m-%d %H:%M')}\t{len(json.load(open(L.SOURCES)))}\t{len(answers)}\t"
                f"{r['before']:.2%}\t{r['after']:.2%}\t{r['worse']}\t{r['asks']}\t{len(qs)}\n")
    subprocess.run([str(L.LEDGER / 'worker' / 'deploy.sh')], check=True)
    git('add', 'ledger/changes.jsonl', 'ledger/sources.json', 'ledger/taught.jsonl', 'ledger/history.tsv',
        'ledger/page/questions.json', 'ledger/pending.json')
    if git('diff', '--cached', '--quiet').returncode:
        msg = (f"テロップ台帳: 夜の一巡（答え{len(answers)}件・誤り率 {r['after']:.1%}・悪化{r['worse']}・確認{len(qs)}か所）\n\n"
               'telop_sync.py による自動の記録')
        git('commit', '-m', msg)
        git('pull', '--rebase', '--autostash')
        p = git('push')
        print('push', 'OK' if p.returncode == 0 else 'NG: ' + p.stderr)


if __name__ == '__main__':
    os.chdir(L.ROOT)
    sys.exit(main())
