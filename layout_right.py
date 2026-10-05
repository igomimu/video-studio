#!/usr/bin/env python3
"""碁盤を左端に寄せ、右上に横書き字幕（generate_ass.py --right）を焼き込む。

録画（OBS）の碁盤の位置はそのままでよい。仕上げで碁盤の範囲だけ左へずらし、
空いた右側の上に字幕、その下に情報カード、右下は話者の顔、という配置にする。

  python3 layout_right.py input.mp4 telops.ass -o out.mp4            # 全編
  python3 layout_right.py input.mp4 telops.ass -o s.mp4 --ss 600 -t 20  # 一部だけ試す
  python3 layout_right.py input.mp4 --detect                          # 碁盤の位置を調べるだけ
"""
import argparse
import subprocess
import sys
import tempfile

from PIL import Image


def grab(video, t):
    out = tempfile.NamedTemporaryFile(suffix='.png', delete=False).name
    subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(t), '-i', video, '-frames:v', '1', '-y', out], check=True)
    return Image.open(out).convert('RGB')


def is_wood(p):
    r, g, b = p
    return r > 170 and 110 < g < 215 and b < 160 and r - b > 60


def detect_board(img):
    """碁盤（木目）の左右の端と、碁盤の外の背景色を返す。
    列ごとに木目の割合を数え、割合の高い列が続く最も長い範囲を碁盤とみなす（線の1〜2px の切れ目は許す）"""
    w, h = img.size
    small = img.resize((w, h // 8))   # 行を間引いて速くする
    px = small.load()
    frac = [sum(is_wood(px[x, y]) for y in range(small.height)) / small.height for x in range(w)]
    best, start, gap = (0, 0), None, 0
    for x in range(w + 1):
        on = x < w and frac[x] > 0.3
        if on:
            start = x if start is None else start
            gap = 0
        elif start is not None:
            gap += 1
            if gap > 8 or x == w:
                end = x - gap + 1
                if end - start > best[1] - best[0]:
                    best = (start, end)
                start, gap = None, 0
    left, right = best
    bg = img.getpixel((min(w - 1, right + 30), h // 2))
    return left, right, bg


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('video')
    ap.add_argument('ass', nargs='?')
    ap.add_argument('-o', '--output', default='out.mp4')
    ap.add_argument('--detect', action='store_true', help='碁盤の位置を表示して終わる')
    ap.add_argument('--sample-at', type=float, help='碁盤の位置を調べるコマの時刻(秒)。省略時は全体から5コマ調べて多数決')
    ap.add_argument('--board', help='碁盤の左右の端 "左,右"(px)。指定しなければ自動で調べる')
    ap.add_argument('--top', type=int, default=28, help='上の黒帯の高さ(px)。ここより下だけ塗り直す')
    ap.add_argument('--ss', type=float, help='開始(秒)。試し書き出し用')
    ap.add_argument('-t', '--duration', type=float, help='長さ(秒)。試し書き出し用')
    ap.add_argument('--extra-filter', default='', help='字幕の後に足すフィルタ（情報カードの overlay など）')
    args = ap.parse_args()

    if args.sample_at is not None:
        times = [args.sample_at]
    else:
        dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0',
                                    args.video], capture_output=True, text=True, check=True).stdout)
        times = [dur * k / 6 for k in range(1, 6)]
    found = [detect_board(grab(args.video, t)) for t in times]
    found = [f for f in found if f[1] - f[0] >= 600] or found   # 碁盤の映っていないコマ（冒頭の挨拶など）を除く
    found.sort(key=lambda f: f[1] - f[0])
    left, right, bg = found[len(found) // 2]
    if args.board:
        left, right = map(int, args.board.split(','))
    width = right - left
    print(f'碁盤: x={left}〜{right}（幅{width}px）→ x=0〜{width} へ寄せる。背景色 {bg}')
    if args.detect:
        return
    if width < 600:
        sys.exit('碁盤が見つかりません。--board "左,右" で指定してください')
    if not args.ass:
        sys.exit('字幕ファイル(.ass)を指定してください')

    # 碁盤を x=0 へ。碁盤が退いた跡（幅 left）は、碁盤のすぐ右の背景をそのまま写して埋める（単色で塗ると境目が見える）
    vf = (f"[0:v]split=3[base][src][fill];"
          f"[src]crop={width}:ih:{left}:0[board];"
          f"[fill]crop={left}:ih-{args.top}:{right}:{args.top}[patch];"
          f"[base][patch]overlay={width}:{args.top}[bg];"
          f"[bg][board]overlay=0:0,setpts=PTS+{args.ss or 0}/TB,"   # 一部だけ書き出すときも字幕の時刻を合わせる
          f"ass={args.ass}{args.extra_filter},setpts=PTS-STARTPTS[v]")
    cmd = ['ffmpeg', '-y']
    if args.ss is not None:
        cmd += ['-ss', str(args.ss)]
    if args.duration:
        cmd += ['-t', str(args.duration)]
    cmd += ['-i', args.video, '-filter_complex', vf, '-map', '[v]', '-map', '0:a?',
            '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-c:a', 'copy', args.output]
    subprocess.run(cmd, check=True)
    print(f'出力: {args.output}')


if __name__ == '__main__':
    main()
