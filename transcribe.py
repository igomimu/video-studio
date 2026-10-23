#!/usr/bin/env python3
"""
faster-whisperで動画を文字起こし → JSON出力

使い方:
  python transcribe.py input.mp4 -o transcript.json

  # LEGION GPU + 高精度モデル（推奨）
  python transcribe.py input.mp4 -o transcript.json -m large-v3 -d cuda

出力: [{start, end, text}, ...] 形式のJSON
generate_ass.py の入力として使用する

依存: pip install faster-whisper
"""
import json
import csv
import argparse
import time
from pathlib import Path


def load_initial_prompt() -> str:
    """囲碁用語をWhisperに事前に教えるプロンプト（2500文字以内）"""
    terms = set()

    # master.csv（囲碁IME辞書）
    master_path = Path.home() / "projects" / "go-dictionary-registration" / "data" / "master.csv"
    if master_path.exists():
        with open(master_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("term_ja"):
                    terms.add(row["term_ja"])

    if not terms:
        return ""

    prompt = "囲碁の解説: " + "、".join(sorted(terms))
    # Whisperのinitial_promptは2500文字が限界
    if len(prompt) > 2500:
        prompt = prompt[:2500]
    return prompt


def transcribe(video_path, output_path, model_name="large-v3", device="cuda"):
    from faster_whisper import WhisperModel

    compute_type = "float16" if device == "cuda" else "int8"
    print(f"Loading model: {model_name} (device={device}, compute={compute_type})")
    model = WhisperModel(model_name, device=device, compute_type=compute_type)

    initial_prompt = load_initial_prompt()
    if initial_prompt:
        print(f"Initial prompt: {len(initial_prompt)} chars ({initial_prompt[:60]}...)")

    print(f"Transcribing: {video_path}")
    start_time = time.time()

    transcribe_opts = dict(
        language="ja",
        word_timestamps=True,
        vad_filter=True,
        beam_size=5,
    )
    if initial_prompt:
        transcribe_opts["initial_prompt"] = initial_prompt

    segments, info = model.transcribe(video_path, **transcribe_opts)

    # words は字幕の切り替え時刻に使う（文の途中の間で後半が先に出ないように）。形式は [開始, 終了, 語]
    result = []
    for seg in segments:
        result.append({
            "start": round(seg.start, 2),
            "end": round(seg.end, 2),
            "text": seg.text.strip(),
            "words": [[round(w.start, 2), round(w.end, 2), w.word] for w in seg.words or []],
        })

    elapsed = time.time() - start_time
    print(f"Done: {len(result)} segments in {elapsed:.0f}s")

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='faster-whisperで動画を文字起こし → JSON出力'
    )
    parser.add_argument('video', help='入力動画ファイル')
    parser.add_argument('-o', '--output', default='/tmp/whisper_transcript.json',
                        help='出力JSONファイルパス')
    parser.add_argument('-m', '--model', default='large-v3',
                        help='Whisperモデル (tiny/base/small/medium/large-v3)')
    parser.add_argument('-d', '--device', default='cuda',
                        help='デバイス (cpu/cuda)')
    args = parser.parse_args()

    transcribe(args.video, args.output, args.model, args.device)


if __name__ == '__main__':
    main()
