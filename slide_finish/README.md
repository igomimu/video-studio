# 紙芝居＋顔ワイプの解説動画を仕上げる（2026-11-07「囲碁は分かりにくい」で作成）

作業フォルダ `work/日付_題/finish/` にコピーして、上から順に流す。仕上げの決まり（毎回入れる5点）は memory `feedback_video_finish_checklist.md`。

1. `transcribe_short.py` → `fix_text.py`（区切りごとに本文を手で直す）→ `build_telops.py`（telops.ass）→ `cp telops.ass telops_bottom.ass`
2. 録画を 4fps・480×270 で読む: `ffmpeg -i ../raw.mp4 -vf fps=4,scale=480:270 -f rawvideo -pix_fmt rgb24 frames_480.rgb`
   顔の範囲: 全フレームの中身率 `content_rate.npy`（右下で7割超が顔）
3. `busy_mask.py` … 各フレームの「中身がある画素」（背景色から差7超。カーソル程度の小さな塊は外す）
4. `place_telops.py` … テロップを紙芝居・顔・カードに重ねない場所へ。どこにも入らないテロップは出さない（SRTには残す）
5. 紙芝居を段階ごとに描き直し（states/、playwright で show(i,k)）→ `match_states.py`（録画の倍率は合わせ直す。11-07 は 1.28・(-12,-8)）→ `make_face_patches.py`（顔に隠れた字・図だけ重ねる）
6. `render.py` … 顔の重ね絵＋名札（assets/name_card.png）＋締めの案内2枚＋テロップ → final.mp4
7. 書き出したら静止画で照合 → `upload_brief.py`（冒頭の名札が無いと止まる）
