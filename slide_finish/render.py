"""raw_20261107.mp4 ＋ 顔に隠れた紙芝居の描き直し ＋ 名札 ＋ 締めの案内2枚 ＋ テロップ → final.mp4（2026-11-07 囲碁は分かりにくい）"""
import json, subprocess, sys
seg = {x['i']: x for x in json.load(open('refined_final.json'))}
END = 1446.43
CARDS = [tuple(c) for c in json.load(open('face_cards.json'))]
CARDS += [('overlay/name.png', 1500, 520, 0.3, 10.0)]
SUB = json.load(open('end_cards_pos.json'))     # 締めの案内の置き場（紙芝居と顔を避けた位置）
CARDS += [('overlay/04_subscribe_dark.png', SUB[0], SUB[1], seg[448]['start'], seg[449]['start']),
          ('overlay/03_newsletter_dark.png', SUB[0], SUB[1], seg[449]['start'], END)]
f = ["[0:v]fps=30[c0]"]
for j, (_, x, y, a, b) in enumerate(CARDS):
    f.append(f"[{j + 1}:v]format=rgba[i{j}];[c{j}][i{j}]overlay={x}:{y}:eof_action=repeat:enable='between(t,{a:.2f},{b:.2f})'[c{j + 1}]")
f.append(f"[c{len(CARDS)}]ass=telops.ass:shaping=complex[v]")
open('render_filter.txt', 'w').write(";".join(f))
out = sys.argv[1] if len(sys.argv) > 1 else 'final.mp4'
inputs = sum((["-loop", "1", "-i", p] for p, *_ in CARDS), [])
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", "../raw_20261107.mp4"] + inputs +
               ["-filter_complex_script", "render_filter.txt", "-map", "[v]", "-map", "0:a", "-t", f"{END}"] + sys.argv[2:] +
               ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", out], check=True)
print(len(CARDS), 'cards')
