# Telop Master

動画テロップ生成ツール群。囲碁動画制作の効率化パイプライン（収録後の仕上げ工程）。

## 全体ワークフロー

```
録画(OBS) → 自動カット(auto-editor: 音も動きも無い区間, LEGION) → Camtasiaで仕上げ編集 → 文字起こし+テロップ(LEGION) → BGM/サムネ/概要欄
```

## カット編集: auto-editor で「音も動きも無い区間」を自動カット

Camtasia 2019には無音自動削除機能が無い（TechSmithの Remove Silence は Camtasia Audiate との連携機能で、2022年以降のバージョン向け）。代わりに無料OSSツール [auto-editor](https://auto-editor.com/) を使う。

```bash
pip install --user --break-system-packages auto-editor  # 導入済みならスキップ

./cut_silence.sh -n raw_recording.mp4          # まずカット量だけ確認
./cut_silence.sh raw_recording.mp4 cut.mp4     # 書き出し
```

### 判定は「音 or 動き」（囲碁解説では音だけでは足りない）

囲碁の解説動画には、**無音のまま碁盤に石を並べて手順を見せる区間**がある。音量だけで判定するとここが丸ごと消える。`cut_silence.sh` は音と画面変化のどちらかがあれば残す設定を既定にしている。

```
--edit "(or audio:threshold=0.04 motion:threshold=0.02)"
```

`audio or motion` のような書き方は構文エラーになる。**括弧付きのS式でないと動かない**（auto-editor 29.3.1 で確認）。

実測（30秒のテスト動画: 解説音声10秒 + 無音で石を置く10秒 + 解説音声10秒）:

| 判定方法 | 出力 | 結果 |
|---|---|---|
| `audio` のみ | 13.0秒 | 手順を見せる10秒が丸ごと消滅 |
| `(or audio motion)` | 26.7秒 | 手順は全部残り、死に時間だけカット |

### 碁石を置く音は当てにできない

**0.1秒（3フレーム）未満の音は無視される**。実測で35msの打音は音量ピーク0.53（しきい値0.04の13倍）でも完全に落ちた。100ms以上あれば残る。実物の碁盤の打音は余韻があるので通る見込みだが、碁盤ソフトのクリック効果音は短く拾われないことがある。動き判定を併用する理由。

逆に、画面に時計・検討ソフトのアニメーション・マウス移動があると常に「動きあり」になり、カット量は減る（＝安全側に外れる）。

### Windows(YOGAPro)でターミナルを使わずに実行する

録画・編集は YOGAPro の Camtasia で行うため、生録画(数GB)を LEGION に送らず **Windows 側だけで完結**させられる。auto-editor には Python 不要のスタンドアロン .exe がある。

```
無音カット.bat   ← このリポジトリのファイル
auto-editor.exe  ← https://github.com/WyattBlue/auto-editor/releases
                    の auto-editor-windows-x86_64.exe をリネームして同じフォルダに置く
```

動画ファイルを `無音カット.bat` のアイコンにドラッグ＆ドロップすると、カット量を表示してから同じフォルダに `〜_cut.mp4` を書き出す。複数ファイルの同時ドロップにも対応。しきい値は .bat 冒頭の `AUDIO_TH` / `MOTION_TH` / `MARGIN` をメモ帳で書き換えて調整する。

Windows実機で確認済み(2026-08-19, auto-editor 31.5.0): 判定式・カット結果はLinux版と同一(テスト動画30秒→26.7秒)、既存の出力先は上書きせず中断、引数なし起動はドロップを促して終了。

### margin と運用上の注意

`--margin 1.5sec` は「音/動きの前後1.5秒は残す」。1.5秒未満の間（次の一手を考える間など）は自動的に残り、それより長い空白だけがカットされる。環境変数 `AUDIO_TH` / `MOTION_TH` / `MARGIN` で調整できる。

- 生録画に対してCamtasiaで編集する**前**にかける。Camtasia側でタイムラインをいじった後だとカット区間がズレやすいため
- auto-editor は**実データを切る**ので誤カットは戻せない。元ファイルは必ず残す（スクリプトは既存の出力先を上書きしない）

## ツール一覧

### 1. 自動字幕生成パイプライン

動画音声 → Whisper文字起こし → LLM補正(Gemini/Ollama) → 囲碁用語修正 → ASS縦書き字幕 → ffmpeg焼き込み

```bash
# Step 1: 文字起こし
python transcribe.py input.mp4 -o transcript.json

# Step 2: ASS字幕生成（Gemini補正がデフォルト。--save-refined-json で横書きJSONも保存）
python generate_ass.py transcript.json -o telops.ass -t "石の形講座" \
  --llm-backend gemini --save-refined-json refined.json

# Step 3: プレビュー（30秒）
ffmpeg -y -ss 0 -t 30 -i input.mp4 -vf "ass=telops.ass" \
  -c:v libx264 -preset fast -crf 23 -c:a aac -b:a 128k preview.mp4

# Step 4: 本番エンコード
ffmpeg -y -i input.mp4 -vf "ass=telops.ass" \
  -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 192k output.mp4
```

#### LLM補正バックエンド

`--llm-backend gemini|ollama|none`（デフォルト: `gemini`）

- **gemini**（デフォルト）: `~/.secrets/gemini.env` のAPIキー（Google AI Pro無料枠、従量課金なし）を使用。棋士名・専門用語の文脈補正力が高い。利用不可・失敗時は自動で Ollama にフォールバックする（`--ollama-host` 指定時）
- **ollama**: ローカルの Ollama（Nemotron-Nano-9B）のみで補正。Geminiが使えない環境向け
- **none**: LLM補正なし、辞書ルールのみ（旧 `--no-llm` と同義）

無料枠のレート制限対策として、Geminiバッチ間に `--gemini-sleep`(デフォルト7秒)の待機を入れている。長尺動画では `--batch-size` を20〜30程度に増やすと1バッチあたりの辞書送信コストを償却できる。

#### 依存

```bash
pip install faster-whisper google-genai
```

#### 囲碁用語修正

`generate_ass.py` 内の2つの辞書で Whisper の誤認識を修正:

- **GO_CORRECTIONS** / **GO_CORRECTIONS_AUTO**: 固定置換（例: 視聴→シチョウ、異号→囲碁）
- **GO_VERB_RULES**: 正規表現ベースの活用形変換（例: 切り→キリ、繋が→ツナが）

LLM補正の後に適用される最後の砦。新しい動画で誤認識を見つけたら辞書に追加していく。

### 2. メタデータ生成 (`generate_metadata.py`)

`--save-refined-json` で保存した横書きtranscriptから、YouTube用のタイトル案・概要欄・章立てをGeminiで自動生成する。

```bash
python generate_metadata.py refined.json -o metadata.json
cat metadata.txt  # 概要欄にそのまま貼れる本文+チャプター
```

### 3. サムネイル生成 (`generate_thumbnail.py`)

動画から碁盤フレームを切り出し、棋士名・テーマ文言を合成する。

```bash
ffmpeg -y -ss 00:08:42 -i input.mp4 -frames:v 1 -q:v 2 frame.png
python generate_thumbnail.py frame.png -o thumbnail.jpg --kishi "三村智保九段" --theme "裂かれ形の急所"
```

### 4. BGM自動ミックス (`mix_bgm.py`)

```bash
python mix_bgm.py with_telops.mp4 ~/bgm/sample.mp3 -o with_bgm.mp4 --bgm-volume -20 [--duck]
```

`--duck` でナレーション時にBGM音量を自動で下げる（sidechaincompress）。

### 5. テロップ画像生成 (`text_generator.py`)

白フチ＋赤/黒文字のPNG画像を生成（旧方式、`generate_thumbnail.py`のテキスト合成ロジックの元ネタ）。

```bash
./gen_text.sh
```

## examples/

実際の生成例（石の形講座 裂かれ形）:
- `whisper_transcript.json` — Whisper文字起こし結果
- `telops.ass` — 生成されたASS字幕

## 碁盤を左端に寄せ、右上に横書き字幕（2026-10〜 標準）

縦書き字幕は左端の細い余白に入れていたが、碁盤を左端まで寄せると右側に幅約820pxの空きができる。
そこに横書きの字幕を出す。**碁盤の大きさは変えない**。録画（OBS）の配置もそのままでよい。

```
python3 generate_ass.py transcript.json --right -o telops.ass        # 右上・横書き 72px・13字×2行
python3 layout_right.py cut.mp4 --detect                            # 碁盤の位置を確認（5コマの多数決）
python3 layout_right.py cut.mp4 telops.ass -o s.mp4 --ss 600 -t 20  # 20秒だけ試す
python3 layout_right.py cut.mp4 telops.ass -o final.mp4             # 全編
```

- 行の区切りは BudouX（Chrome の `word-break: auto-phrase` と同じ文節区切り）で決める。無ければ字種の規則で代用（`pip install budoux`）
- 画面の割り付け（1920x1080）: 碁盤 x=0〜約1044 ／ 字幕 x=1080〜・上端 ／ **情報カード x=1066, y=230, 幅820, 高さ520以内**（字幕の下・顔の上）／ 顔は右下のまま
- 情報カードの文字は本文28px以上（→ 字幕・カードは大きく）。カードの overlay は `--extra-filter` で足す
