"""Drive整理の対応表を作る。--run で実行（移動と改名のみ。削除しない）"""
import json, re, subprocess, sys, os

D = os.path.dirname(os.path.abspath(__file__))
A = ["--account", "lucky.mim@gmail.com"]
Y = "1aOkAI-7ZtqGx5gYOYeRLQwGfVd52Xx8B"          # YouTube投稿
ORG = {"01": "1SQGNot_f97fMLQ62ARHq2hQ-qG8p0qSQ", "02": "1tpQxwnbw7yM0bnGKBH9_eTqk9HbCcj9Z",
       "03": "1Xxkzft7Fwt4kFijnjJZFl27C37p0cTif", "06": "1Zb4ALikFs5loMBVmB5vXRFR0qIrIngih",
       "07": "1ZAg8pnX7DzOY7CrFkrv1Yb4XEN6lCs4z", "99": "1DnHTZmCRXkUqDtIZUPgGGk2InZXeIS0v"}
INSTA = "18jPeELa5PaGHby-CqmU9vjie-5ZSRuWh"

yt = json.load(open(f"{D}/yt.json"))
root = json.load(open(f"{D}/root.json"))
org = json.load(open(f"{D}/org.json"))

IBK = "20261004_IBK杯_上野vs仲邑"
RANK = "ranking-2026-10_棋士ランキング10月"
SUI1 = "20261008_水協杯準決勝_仲邑vs呉侑珍"
HK4 = "20261011_hikaru_ヒカルの碁④_洪秀英戦"
NAK = "20261014_nakamura_女子棋聖戦_仲邑vs崔序妃"
HK5 = "20261019_hikaru5_ヒカルの碁⑤_伊角vsヒカル"
RULE = "20261020_igo-rules_囲碁のルール"
HAR = "20261022_harim_ハリム杯準決勝_仲邑vs金恩持"
SUI2 = "20261027_suhyup1_水協杯決勝第1局"

# 既存フォルダの改名（YouTube投稿直下）
RENAME = {"20261027_suhyup1": SUI2, "finish": HAR, "20261020_igo-rules": RULE,
          "20261019_hikaru5": HK5, "20261014_nakamura": NAK, "20261011_hikaru": HK4,
          "20261008": SUI1, "ranking-2026-10": RANK,
          "short": "ショート_洪秀英の名前の由来"}

def rule_yt(path, name):
    """YouTube投稿内の項目 → 行き先（Y からの相対パス or ('ORG',key)）"""
    p = path.split("/")
    if len(p) == 2:  # 直下
        if name == "2026-10-27 08-34-30.mp4": return f"{SUI2}/収録元"
        if name == "2026-10-19 10-40-07.mp4": return f"{HK5}/収録元"
        if name == "2026-10-14 06-50-19.mp4": return f"{NAK}/収録元"
        if name == "2026-10-08 07-49-05.mp4": return f"{SUI1}/収録元"
        if name == "2026-10-04 12-31-17.mp4": return f"{IBK}/収録元"
        if name.startswith("20261004_IBK杯解説_"): return IBK
        if name.startswith("20261004_IBK杯_ショート") or name.startswith("20261004_IBK杯_切り抜き"): return f"{IBK}/ショート・切り抜き"
        if name == "20261004_IBK杯_ラジオ": return IBK
        if name.startswith("20261005_"): return "_テスト・見本"
        if name == "「志」通信224号": return ("ORG", "02")
        if name == "広告の確認_20261014": return "_チャンネル運営"
        if name == "仲邑菫_崔序妃_女子棋聖戦": return f"{NAK}/旧版"
        if name == "short": return HK4
        if name == "ヒカルの碁": return f"{HK4}/旧版"
        return None
    if p[1] == "ヒカルの碁" and len(p) == 3:
        if name == "2026-10-11 11-05-56.mp4": return f"{HK4}/収録元"
        if name.startswith("20261011_ヒカルの碁④"): return f"{HK4}/旧版"
        return f"{HK5}/旧版"
    return None

def rule_root(name, folder):
    if folder:
        if name == "20261026_金恩持vs仲邑菫_水協杯決勝_準備資料": return f"{SUI2}/資料"
        if name == "20261022_金恩持vs仲邑菫_準備資料": return f"{HAR}/資料"
        return None
    if name.startswith("ハリム杯準決勝_"): return f"{HAR}/旧版"
    if name == "2026-10-22 16-16-01.mp4": return f"{HAR}/収録元"
    if name.startswith("ハリム杯_勝ち上がり") or name.startswith("2人の成績と日程"): return f"{HAR}/資料"
    if name.startswith("囲碁のルール_縦_") and "_v2" in name: return f"{RULE}/縦ショート"
    if name.startswith("囲碁のルール") and name.endswith((".mp4", ".srt")): return f"{RULE}/旧版"
    if name.startswith("2分で分かる"): return f"{RULE}/旧版"
    if name.startswith("Codex指示書_囲碁のルール") or name.startswith("囲碁のルール.docx") or name.startswith("囲碁入門"): return f"{RULE}/資料"
    if name == "YouTube紹介記事_囲碁のルール_スマホ.png": return f"{RULE}/資料"
    if name in ("ヒカルの碁⑤台本.md", "打ち直し反則負け.mp4", "PXL_20261017_062240732.mp4", "YouTube紹介記事_ヒカルの碁5_PC.png"): return f"{HK5}/資料"
    if name in ("ヒカルの碁4_洪秀英戦_確認用.mp4", "ショート_洪秀英の名前の由来_確認用.mp4"): return f"{HK4}/旧版"
    if name.startswith("みむ囲碁ちゃんねる_"): return "_チャンネル運営"
    if name.startswith("呉清源杯予選_記事プレビュー") or name.startswith("20261023-tsumego-media"): return ("ORG", "06")
    if name.startswith("今月の院生") or name in ("第5回千葉県小中学生こども囲碁団体戦_チラシ.png", "page_1.png"): return ("ORG", "01")
    if name.startswith(("スキャン_", "Image_2026")) or name in ("test1-compare.jpg", "PXL_20261011_090913524.mp4", "PXL_20261011_090556269.mp4"): return ("ORG", "99")
    if name.startswith(("LEGION-Recovery", "pokekata-", "tournament-table")): return ("ORG", "07")
    if name.startswith("2目の頭_記事下書き"): return ("ORG", "02")
    if name.startswith("天元教室_"): return ("INSTA", "天元教室8本_素材")
    if name.startswith("PXL_20261010_") or name.startswith(("lesson-2026-10-10", "reel-")): return ("INSTA", "2026-10-10_リール素材")
    return "UNMAPPED"

def rule_03(name):
    if name.startswith("ranking-2026-10_チャプター"): return RANK
    if name.startswith(("ranking-2026-10_", "ランキング10月_テロップ見本")):
        return f"{RANK}/収録元" if name == "ranking-2026-10_full.mp4" else f"{RANK}/旧版"
    if name in ("2026-10-06 07-52-51.mp4", "2026-10-06 08-51-00.mp4"): return f"{RANK}/収録元"
    return None

moves = []
for f in yt:
    d = rule_yt(f["path"], f["name"])
    if d: moves.append((f["id"], f["path"], d))
for f in root:
    d = rule_root(f["name"], f["mimeType"].endswith("folder"))
    if d: moves.append((f["id"], "ROOT/" + f["name"], d))
for f in org:
    if f["path"].startswith("整理/03_") and f["path"].count("/") == 2:
        d = rule_03(f["name"])
        if d: moves.append((f["id"], f["path"], d))

if "--run" not in sys.argv:
    for m in moves: print(m[1], "→", m[2])
    print(len(moves), "件")
    sys.exit()

def gog(*a):
    r = subprocess.run(["gog", "drive", *a, "--json", *A], capture_output=True, text=True)
    if r.returncode: raise SystemExit(f"失敗: {a}\n{r.stderr}")
    return json.loads(r.stdout or "{}")

log = open(f"{D}/move_log.tsv", "a")
cache = {}
yt_top = {f["name"]: f["id"] for f in yt if f["path"].count("/") == 1 and f["mimeType"].endswith("folder")}

for old, new in RENAME.items():
    gog("rename", yt_top[old], new); log.write(f"rename\t{yt_top[old]}\t{old}\t{new}\n"); log.flush()
    cache[(Y, new)] = yt_top[old]

def ensure(parent, name):
    if (parent, name) in cache: return cache[(parent, name)]
    q = f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false and '{parent}' in parents"
    hit = gog("search", q, "--raw-query").get("files", [])
    fid = hit[0]["id"] if hit else (lambda r: r.get("folder", r.get("file", r))["id"])(gog("mkdir", name, "--parent", parent))
    if not hit: log.write(f"mkdir\t{fid}\t{parent}\t{name}\n")
    cache[(parent, name)] = fid
    return fid

def dest(d):
    if isinstance(d, tuple):
        return ORG[d[1]] if d[0] == "ORG" else ensure(INSTA, d[1])
    pid = Y
    for part in d.split("/"): pid = ensure(pid, part)
    return pid

for fid, src, d in moves:
    meta = gog("get", fid)["file"]
    to = dest(d)
    gog("move", fid, "--parent", to)
    log.write(f"move\t{fid}\t{','.join(meta['parents'])}\t{to}\t{src}\t{d}\n"); log.flush()
    print("✓", src, "→", d)
