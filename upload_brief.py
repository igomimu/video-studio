#!/usr/bin/env python3
"""仕上がった動画を Google Drive に置き、デスクトップアプリのAIに渡す「投稿の指示書」を作る

使い方:
  python upload_brief.py work/20261004 --title 2          # タイトル案の2番で作り、Driveへ上げる
  python upload_brief.py work/20261004 --title 2 --no-upload   # 指示書だけ作って中身を見る

作業フォルダから拾うもの（無ければ止まる）:
  動画   final*.mp4 のうち一番新しいもの（--video で指定可）
  サムネ thumbnail*.jpg のうち一番新しいもの（--thumb で指定可）
  タイトル titles.txt の番号つきの行（--title 番号、または --title-text で直接）
  説明欄 description.txt の全文

AIはYouTube Studioをブラウザで操作して上げる。APIの「非公開固定」にはかからない。
最初は必ず限定公開。三村さんが中身を見てから公開に切り替える。
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ACCOUNT = "lucky.mim@gmail.com"
DRIVE_ROOT_NAME = "YouTube投稿"


def newest(folder: Path, pattern: str) -> Path:
    files = sorted(folder.glob(pattern), key=lambda p: p.stat().st_mtime)
    if not files:
        sys.exit(f"{folder} に {pattern} が見つからない")
    return files[-1]


def pick_title(folder: Path, number: int) -> str:
    for line in (folder / "titles.txt").read_text(encoding="utf-8").splitlines():
        m = re.match(rf"\s*{number}\.\s*(.+)", line)
        if m:
            return m.group(1).strip()
    sys.exit(f"titles.txt に {number}. の行が無い")


def gog(*args) -> dict:
    out = subprocess.run(["gog", "drive", *args, "--account", ACCOUNT, "--json", "--results-only"],
                         check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def folder_id(name: str, parent: str | None = None) -> str:
    q = f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if parent:
        q += f" and '{parent}' in parents"
    found = gog("search", q, "--raw-query")
    if found:
        return found[0]["id"]
    return gog("mkdir", name, *(["--parent", parent] if parent else []))["id"]


def brief_text(title: str, description: str, video: str, thumb: str, drive_url: str) -> str:
    return f"""# YouTube 投稿の指示書

みむ囲碁ちゃんねる（@mimuigo）に動画を1本上げてください。
**この指示書に書いてあること以外の操作はしないでください。** 他の動画やチャンネル設定には触れないこと。

## 1. ファイルを手元に落とす
Google Drive のフォルダを開き、次の2つをダウンロードする。
{drive_url}

- 動画: `{video}`
- サムネイル: `{thumb}`

## 2. YouTube Studio で上げる
1. https://studio.youtube.com を開く（三村さんのアカウントでログイン済みのはず）
2. 右上の「作成」→「動画をアップロード」→ さきほどの動画ファイルを選ぶ
3. 「詳細」の画面で、下の「タイトル」と「説明」を**一字も変えずに**貼る
4. 「サムネイル」に、さきほどのサムネイル画像を上げる
5. 「視聴者」は「いいえ、子ども向けではありません」
6. 「動画の要素」（終了画面・カード）は**何もしない**
7. 「公開設定」は **「限定公開」** を選んで保存する。**「公開」は選ばない**

## 3. 終わったら
動画のURL（https://youtu.be/…）を三村さんに伝える。途中で止まったら、どの画面で何が出たかを伝える。

---

## タイトル
```
{title}
```

## 説明
```
{description}
```
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workdir", type=Path)
    ap.add_argument("--title", type=int, help="titles.txt の何番の案を使うか")
    ap.add_argument("--title-text", help="タイトルを直接書く")
    ap.add_argument("--video", type=Path)
    ap.add_argument("--thumb", type=Path)
    ap.add_argument("--no-upload", action="store_true", help="Driveに上げず、指示書だけ作る")
    a = ap.parse_args()

    folder = a.workdir.resolve()
    if a.title_text:
        title = a.title_text
    elif a.title:
        title = pick_title(folder, a.title)
    else:
        sys.exit("--title 番号 か --title-text を指定する")
    if len(title) > 100:
        sys.exit(f"タイトルが{len(title)}文字。YouTubeの上限は100文字")
    description = (folder / "description.txt").read_text(encoding="utf-8").strip()
    if len(description.encode("utf-8")) > 5000:
        sys.exit("説明欄がYouTubeの上限5000バイトを超えている")
    video = a.video or newest(folder, "final*.mp4")
    thumb = a.thumb or newest(folder, "thumbnail*.jpg")
    if thumb.stat().st_size > 2 * 1024 * 1024:
        sys.exit(f"サムネイル {thumb.name} が2MBを超えている（YouTubeの上限）")

    drive_url = "（--no-upload のため未作成）"
    if not a.no_upload:
        sub = folder_id(folder.name, folder_id(DRIVE_ROOT_NAME))
        drive_url = f"https://drive.google.com/drive/folders/{sub}"
        for f in (video, thumb):
            print(f"Driveへ上げています: {f.name}", flush=True)
            gog("upload", str(f), "--parent", sub)

    brief = folder / "投稿指示書.md"
    brief.write_text(brief_text(title, description, video.name, thumb.name, drive_url), encoding="utf-8")
    if not a.no_upload:
        gog("upload", str(brief), "--parent", sub)
    print(f"指示書: {brief}")
    print(f"Drive: {drive_url}")


if __name__ == "__main__":
    main()
