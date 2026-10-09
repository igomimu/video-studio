#!/usr/bin/env python3
"""
Whisper文字起こし → Ollama LLM補正 → 囲碁用語修正 → ASS縦書き字幕生成

使い方:
  python generate_ass.py transcript.json -o output.ass

  # LLM補正なし（高速、辞書ルールのみ）
  python generate_ass.py transcript.json -o output.ass --no-llm

  # Ollamaホスト指定
  python generate_ass.py transcript.json -o output.ass --ollama-host http://localhost:11434

入力: faster-whisperで生成したJSON ([{start, end, text}, ...])
出力: ASS字幕ファイル（縦書き、左端、半透明暗背景）

ffmpegで焼き込み:
  # プレビュー（30秒）
  ffmpeg -y -ss 0 -t 30 -i input.mp4 -vf "ass=output.ass" \
    -c:v libx264 -preset fast -crf 23 -c:a aac -b:a 128k preview.mp4

  # 本番エンコード
  ffmpeg -y -i input.mp4 -vf "ass=output.ass" \
    -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 192k output.mp4
"""
import json
import re
import csv
import argparse
import sys
import time
from pathlib import Path

import llm_gemini

# --- 棋士名辞書ベース修正（pykakasi読み→正字変換） ---

def fix_kishi_names(transcript):
    """pykakasiで読みに変換し、棋士辞書から正しい漢字表記に修正"""
    try:
        import pykakasi
    except ImportError:
        print("Warning: pykakasi not installed, skipping kishi name fix")
        return transcript

    kishi_path = Path.home() / "kishi-data" / "kishi_dictionary_final.txt"
    if not kishi_path.exists():
        # LEGIONのprojects配下も試す
        kishi_path = Path.home() / "projects" / "kishi-data" / "kishi_dictionary_final.txt"
    if not kishi_path.exists():
        print("Warning: kishi_dictionary_final.txt not found, skipping kishi name fix")
        return transcript

    kishi = {}
    with open(kishi_path, encoding="utf-8") as f:
        for line in f:
            cols = line.strip().split("\t")
            if len(cols) >= 2:
                kishi[cols[0]] = cols[1]

    kks = pykakasi.kakasi()
    fix_count = 0

    for seg in transcript:
        text = seg['text']
        result = kks.convert(text)
        tokens = [(item['orig'], item['hira']) for item in result]

        # 長い一致を優先するため、置換リストを先に収集
        replacements = []
        i = 0
        while i < len(tokens):
            matched = False
            # 6トークンから1トークンまで試す（最長一致）
            for length in range(min(6, len(tokens) - i), 0, -1):
                reading = ''.join(tokens[j][1] for j in range(i, i + length))
                orig = ''.join(tokens[j][0] for j in range(i, i + length))
                if reading in kishi and orig != kishi[reading]:
                    replacements.append((orig, kishi[reading]))
                    i += length
                    matched = True
                    break
            if not matched:
                i += 1

        # テキストに置換を適用
        for orig, correct in replacements:
            text = text.replace(orig, correct, 1)
            fix_count += 1
        seg['text'] = text

    print(f"棋士名修正: {fix_count}件")
    return transcript


# --- 囲碁用語修正辞書（ルールベース、LLM前後どちらでも効く） ---

# 固定文字列置換（Whisperの誤認識を修正）
# 順序: 長いフレーズ→短い語。dictなので重複キー注意
GO_CORRECTIONS = {
    # --- 長い文脈依存フレーズ（先にマッチさせたい） ---
    '柴野一力、柴野一力': '芝野、一力。芝野、一力',
    '賞金の高い規制と低い規制': '賞金の高い棋戦と低い棋戦',
    '規制が一番大きくて': '棋聖が一番大きくて',
    # --- 棋士名（辞書 or 三村さん確認済み） ---
    '三村智康': '三村智保',
    'みむらくだん': '三村九段',
    'みむらともやす': '三村智保',
    '藤沢里奈': '藤沢里菜',
    '上野浅見': '上野愛咲美',
    '龍志くんさん': '柳時熏さん',
    '龍志くん': '柳時熏',
    '長知くん': '趙治勲',
    '超奥団': '趙治勲',
    '大立成': '王立誠',
    '関山穂野歌': '関山穂香',
    '甲原野の': '香原野乃',
    '本田光彦': '本田満彦',
    '後藤真奈': '五藤眞奈',
    '張千恵': '張心治',
    '高尾新宿弾': '高尾紳路九段',
    '優卓弾': '裕太九段',
    '柴野': '芝野',
    # --- 囲碁用語（確認済み） ---
    '三村文化': '三村門下',
    'ホミボー戦': '本因坊戦',
    '名人リグ': '名人リーグ',
    '規制戦': '棋聖戦',
    '日本金': '日本棋院',
    '関西金': '関西棋院',
    '関西菌': '関西棋院',
    '指導後': '指導碁',
    '球場中': '休場中',
    '早子': '早碁',
    '異号': '囲碁',
    '以後': '囲碁',
    '視聴': 'シチョウ',
    # --- 段位 ---
    '初弾': '初段',
    '二弾': '二段', '2弾': '二段',
    '三弾': '三段', '3弾': '三段',
    '四弾': '四段', '4弾': '四段',
    '五弾': '五段', '5弾': '五段',
    '六弾': '六段', '6弾': '六段',
    '七弾': '七段', '7弾': '七段',
    '八弾': '八段', '8弾': '八段',
    '九弾': '九段', '9弾': '九段',
    '十弾': '十段', '10弾': '十段',
    # --- 一般 ---
    '騎士': '棋士',
    '入団': '入段',
    '彼これ': 'かれこれ',
    '字は': '地は',
    '特になりません': '得になりません',
    'うへん': '右辺',
    'かへん': '下辺',
    # --- 裂かれ形 ---
    '逆れがたち': '裂かれ形',
    '逆れが立ち': '裂かれ形',
    '裂かたち': '裂かれ形',
    '逆れ形': '裂かれ形',
    '盛れ形': '裂かれ形',
    '逆れ': '裂かれ',
}

# Whisper誤変換パターン（自動収集 2026-03-22, build_dictionary.py で生成）
# master.csv 601語をTTS→Whisper往復で検出。単文字キー・手動辞書重複は除外済み
GO_CORRECTIONS_AUTO = {
    # 2026-10-04: 日常語と区別できない項目を削除（注目→十目・思い→重い・中で→ナカデ 等が
    # Gemini補正済みの正しい文を壊していた）。漢字→カタカナ表記の統一も文脈依存なので外した
    # --- action ---
    '大兆候': '大長考',
    # --- ai ---
    'アルファ語': 'アルファ碁',
    # --- app ---
    '囲碁で遊ぼ': '囲碁であそぼ！',
    '抜得ポップ': 'BadukPop',
    '囲碁王子': '囲碁ウォーズ',
    # --- behavior ---
    '口じゃみ線': '口三味線',
    '剥がす': 'はがす',
    # --- board ---
    '三踊り地': '三々',
    '13路盤': '十三路盤',
    '19路盤': '十九路盤',
    '転元した': '天元下',
    '急路盤': '九路盤',
    '保守化': '星下',
    # --- book ---
    '定石時点': '定石事典',
    '手筋時点': '手筋事典',
    '死活時点': '死活事典',
    '以後年間': '囲碁年鑑',
    # --- commentary ---
    '語型': '碁形',
    # --- counts ---
    '100目': '百目',
    '二重目': '二十目',
    '判目': '半目',
    '誤目': '五目',
    # --- endgame ---
    '反目勝負': 'ハンモクショウブ',
    '代寄せ': '大ヨセ',
    '小寄せ': '小ヨセ',
    '寄せ': 'ヨセ',
    # --- equipment ---
    '対極時計': '対局時計',
    'ご意志': '碁石',
    # --- eval ---
    '筋がいい': '筋が良い',
    # --- game ---
    '七路の語': 'ななろのご',
    '順後': '純碁',
    # --- general ---
    '切り違える': 'キリチガエる',
    '振り変わる': 'フリカワる',
    '形成判断': '形勢判断',
    'ポンヌク': 'ポンヌく',
    '突っ張る': 'ツッパる',
    '持たれる': 'モタレる',
    '打ち込む': 'ウチコむ',
    '割り打つ': 'ワリウつ',
    '放り込む': 'ホウリコむ',
    '割り込む': 'ワリコむ',
    'ご手寄せ': '後手寄せ',
    '仲押し': '中押し',
    '高争い': 'コウ争い',
    'コスム': 'コスむ',
    'ハネル': 'ハネる',
    'つなぐ': 'ツナぐ',
    '当てる': 'アテる',
    'アテル': '当てる',
    '抑える': 'オサエる',
    'カマス': 'カマす',
    '曲がる': 'マガる',
    '伸びる': 'ノビる',
    '下がる': 'サガる',
    'アラス': 'アラす',
    '受ける': 'ウケる',
    '抱える': 'カカエる',
    '生きる': '活きる',
    '手返し': 'て返し',
    '型先手': '片先手',
    '確定値': '確定地',
    'ai': 'AI',
    '名手': '妙手',
    '握手': '悪手',
    '寄付': '棋譜',
    'オス': '押す',  # 2026-10-09 三村さん「押す は漢字がよい」
    'キル': '切る',
    '開く': 'ヒラく',
    '加工': 'カコう',
    '除く': 'ノゾく',
    '渡る': 'ワタる',
    '覇王': 'ハウ',
    '出る': 'デる',
    '砂漠': 'サバく',
    '滑る': 'スベる',
    '並ぶ': 'ナラぶ',
    '叩く': 'タタく',
    '飛ぶ': 'トぶ',
    '死ぬ': 'シぬ',
    '絞る': 'シボる',
    '迫る': 'セマる',
    '軌道': '棋道',
    '後手': '兩後手',
    # --- history ---
    'トヨタ&デンソーハイ': 'トヨタ＆デンソー杯',
    'プロジュー決戦': 'プロ十傑戦',
    'bc カード杯': 'BCカード杯',
    '次亜化の一手': '耳赤の一手',
    '日本金選手権': '日本棋院選手権',
    'ジャルパイ': 'JAL杯',
    'NECパイ': 'NEC杯',
    '吐血の曲': '吐血の局',
    '最高位線': '最高位戦',
    '富士通廃': '富士通杯',
    '首相敗': '首相杯',
    '中間杯': '中環杯',
    # --- idiom ---
    'イゴの鶴の一声': 'ツルの一声',
    'おかめ8目': '岡目八目',
    'ダメ押し': '駄目押し',
    'ステージ': '捨て石',
    'クロート': '玄人',
    # --- life_death ---
    '掛け目': '欠け眼',
    '花見講': 'ハナミコウ',
    '石域': 'セキ生き',
    '本校': 'ホンコウ',
    # --- mistake ---
    '未存じ': '見損じ',
    # --- organization ---
    '日本起因': '日本棋院',
    '関西起因': '関西棋院',
    '韓国起因': '韓国棋院',
    '中国起因': '中国棋院',
    '台湾起因': '台湾棋院',
    # --- person ---
    'パクジョンファン': '朴廷桓',
    '世を叶え新た': '楊鼎新',
    '中村すみれ': '仲邑菫',
    'イチャーホ': '李昌鎬',
    'コアズサ号': '辜梓豪',
    'あきらてい': '羋昱廷',
    '三村友康': '三村智保',
    '北に実る': '木谷實',
    '逆た栄養': '坂田栄男',
    '居山雄太': '井山裕太',
    '芝の虎丸': '芝野虎丸',
    '藤沢理奈': '藤沢里菜',
    '上の浅身': '上野愛咲美',
    '元アキラ': '元晟溱',
    'ゆるき用': '許嘉陽',
    'ご制限': '呉清源',
    '長治訓': '趙治勲',
    '一力量': '一力遼',
    '正移民': '謝依旻',
    '申し診': '申真諝',
    '関東雲': '姜東潤',
    '禁止鈴': '金志錫',
    '層訓言': '曹薫鉉',
    '金明君': '金明訓',
    '靖国弦': '安國鉉',
    '構成詞': '洪性志',
    '理試験': '李志賢',
    '利権号': '李軒豪',
    '陶器比': '党毅飛',
    '両元角': '廖元赫',
    '大成功': '王星昊',
    '超深雨': '趙晨宇',
    '兆候': '長考',
    '創意': '卞相壹',
    '毛瓶': '申旻埈',
    '再生': '崔精',
    '理性': '李世乭',
    '釈迦': '謝科',
    '可決': '柯潔',
    '判定': '范廷鈺',
    # --- platform ---
    'ネット語': 'ネット碁',
    'ヤギツネ': '野狐',
    '有限の間': '幽玄の間',
    # --- poetic ---
    'ウロ': '烏鷺',
    '手段': '手談',
    '欄下': '爛柯',
    '在院': '坐隠',
    '方園': '方円',
    # --- position ---
    '心腹石': '新布石',
    # --- practice ---
    '乾燥線': '感想戦',
    '詰碁': '詰め碁',
    # --- rank ---
    '女流本陰謀': '女流本因坊',
    '女流規制': '女流棋聖',
    '本陰謀': '本因坊',
    '転元': '天元',
    '誤性': '碁聖',
    '縦断': '十段',
    # --- role ---
    '封じ手がかり': '封じ手係',
    '立ち会い人': '立会人',
    '感染記者': '観戦記者',
    '計測系': '計測係',
    # --- rule ---
    '待ち時間': '持ち時間',
    '打ちかけ': '打ち掛け',
    '病読み': '秒読み',
    '1分後': '1分碁',
    # --- rules ---
    '死に意思': '死に石',
    '込み出し': 'コミ出し',
    '置き語': '置碁',
    '多外線': '互先',
    '相互先': '総互先',
    '事後': '持碁',
    '旋盤': '先番',
    # --- shape ---
    '大ゲーまじまり': 'オオゲイマジマリ',
    '古芸まじまり': 'コゲイマジマリ',
    'ぐるぐる回し': 'グルグルマワシ',
    '一件締まり': 'イッケンジマリ',
    '二件締まり': 'ニケンジマリ',
    '効果たち': '好形',
    '一見飛び': 'イッケントビ',
    '大ゲーマ': 'オオゲイマ',
    '当て込み': 'アテコミ',
    '放り込み': 'ホウリコミ',
    '緩み主張': 'ユルミシチョウ',
    '赤糖絞り': '石塔シボリ',
    '亀の功': '亀の甲',
    '下がり': 'サガリ',
    '裁き方': 'サバキ形',
    '重複形': 'チョウフクケイ',
    '具形': '愚形',
    # --- skill ---
    '対局感': '大局観',
    '弾球員': '段級位',
    # --- software ---
    'クレイジーストーン': 'クレイジー・ストーン',
    'アーキュー号': 'Ah Q Go',
    '店長の囲碁': '天頂の囲碁',
    '吟声囲碁': '銀星囲碁',
    '理地位': 'Lizzie',
    '豪食い': 'GoGui',
    '大型区': 'Ogatak',
    '裁き': 'サバキ',
    '型語': 'カタゴ',
    # --- strategy ---
    '割り打ち': 'ワリウチ',
    'しのぎ': 'シノギ',
    '締まり': 'シマリ',
    '仮名詞': '要石',
    '研究種': '研究手',
    '流行点': '流行手',
    '廃れて': '廃れ手',
    '開き': 'ヒラキ',
    '係り': 'カカリ',
    '数詞': 'カスシ',
    '受け': 'ウケ',
    '危機': '利き',
    # --- style ---
    'ai 流': 'AI流',
    '昭和の語': '昭和の碁',
    '強腕': '剛腕',
    # --- technical ---
    'バタバタトントン追い落とし節不遂': 'バタバタ トントン 追い落とし 接不 追',
    'イゴのケーマネバギ': '桂馬粘ぎ',
    '隅の曲がり4目': '隅の曲がり四目',
    '桂馬係、桂馬係': 'けいまかかり 桂馬掛かり',
    '大桂馬かかり台': '大桂馬掛かり 大',
    'サルスベリリ': '猿滑り',
    'ステーシスク': '捨石作戰',
    'イゴの羽殺す': '跳ね殺す',
    '曲がり4目': '曲がり四目',
    '裂いて出る': '割いて出る',
    '裁きしのぎ': '捌き 凌ぎ',
    '切り違う': 'キリチガう',
    '付けコス': '付け越す',
    'こときか': '琴棋書畵',
    'セメトル': '攻め取る',
    '走り滑り': '走り 滑り',
    '台中焼酎': '大中小中',
    '2件が仮': '二間掛かり',
    '2件飛び': '二間飛び',
    'オーギル': '扇る',
    'カラスミ': '空隅',
    '生き生き': '生き活き',
    'おさむ丸': '收まる',
    'かつらり': '兩桂り',
    'ラッパギ': 'ラッパぎ',
    'ネバギギ': '粘ぎぎ',
    '二段バネ': '二段ばね',
    '目詰まり': '馱目ずまり',
    '一件が仮': '一間掛かり',
    '当たり': 'アタリ',
    'つける': 'ツケる',
    'かかる': 'カカる',
    'シマル': 'シマる',
    '緩み性': '緩み征',
    '飛び見': '飛びみ',
    '舌付け': '下ツケ',
    '外の目': '外目',
    '戦勝先': '先相先',
    '花5目': '花五目',
    '絶対項': '絶對劫',
    'ハネム': '跳ねむ',
    '準選手': '準先手',
    '添加工': '天下劫',
    '正たり': '征たり',
    'スキル': '突きる',
    '打ち身': '打ちみ',
    'えぐる': '抉る',
    '目崩れ': '眼崩れ',
    'ハサミ': '挾み',
    '真似語': '眞似碁',
    '主張': 'シチョウ',
    '下駄': 'ゲタ',
    '賭け': 'カケ',
    '不快': '深い',
    '肩着': '堅ぎ',
    '余生': '寄せ劫',
    '覗き': '望き',
    '古戦': '小尖',
    '推し': '押し',
    '的比': '狹間飛ひ',
    '排斥': '配石',
    '陣傘': '陣笠',
    '実る': '實戰',
    '工事': '劫持',
    '鉄柱': '鐵柱',
    # --- terms ---
    '追い落とし': 'オイオトシ',
    '打手返し': 'ウッテガエシ',
    '万年功': 'マンネンコウ',
    '循環項': '循環劫',
    '良好': '両コウ',
    '参考': '三コウ',
    '調整': '長生',
    '絞り': 'シボリ',
    # --- title ---
    '規制': '棋聖',
    # --- tournament ---
    'ワールド5チャンピオンシップ': 'ワールド碁チャンピオンシップ',
    'アフクキリヤマハイ': '阿含桐山杯',
    'nhk パイ': 'NHK杯',
    '三ッ星化栽培': '三星火災杯',
    'グロービス肺': 'グロービス杯',
    '夢ゆりはい': '夢百合杯',
    '先行カップ': 'センコーカップ',
    '本陰謀戦': '本因坊戦',
    '新人汚染': '新人王戦',
    'LGパイ': 'LG杯',
    '規制線': '棋聖戦',
    '転元戦': '天元戦',
    '御聖戦': '碁聖戦',
    '縦断線': '十段戦',
    '流星線': '竜星戦',
    '若恋戦': '若鯉戦',
    '大支配': '応氏杯',
    '瞬断杯': '春蘭杯',
    '脳心肺': '農心杯',
    # --- trick ---
    'はめて': 'ハメ手',
    # --- variant ---
    '目隠し語': '目隠し碁',
    '10秒後': '10秒語',
    'ペア語': 'ペア碁',
    '連語': '連碁',
}

# 正規表現ベースの活用形変換（囲碁用語をカタカナ統一）
GO_VERB_RULES = [
    # カケツギ系
    # かける／込み は囲碁の意味のときだけ（2026-10-08: 追いかける→追いカケる、込み入った→コミ入った、
    # 織り込み済み→織りコミ と化けていた。単純置換の表から移した）
    (r'(?<![いしみ見をにで])かける', 'カケる'),
    (r'(?<![一-龥ぁ-ん])込み(?!入)', 'コミ'),
    (r'かけ継ぎ', 'カケツギ'),
    (r'かけつぎ', 'カケツギ'),
    (r'かけつ([ぐがぎげご])', r'カケツ\1'),
    # ツナギ系
    (r'繋が', 'ツナが'),
    (r'繋ぎ', 'ツナギ'),
    (r'繋い', 'ツナい'),
    (r'つなが', 'ツナが'),
    (r'つなぎ', 'ツナギ'),
    (r'つない', 'ツナい'),
    (r'つなげ', 'ツナげ'),
    (r'つなぐ', 'ツナぐ'),
    # ノゾキ系
    (r'覗き', 'ノゾキ'),
    (r'覗い', 'ノゾい'),
    (r'覗く', 'ノゾく'),
    (r'のぞき', 'ノゾキ'),
    (r'のぞい', 'ノゾい'),
    (r'のぞく', 'ノゾく'),
    # オサエ系
    (r'抑え', 'オサエ'),
    (r'おさえ', 'オサエ'),
    # アタリ系
    (r'当たり', 'アタリ'),
    # 「このあたり」を壊さないよう、指示語の後は変換しない
    (r'(?<![のこそあど])あたり', 'アタリ'),
    # ハネ系
    (r'跳ね', 'ハネ'),
    # 「というのはね」「今回はね」を壊さないよう、動詞の活用が続く時だけ
    (r'はね(?=[てたるらりれろ返出])', 'ハネ'),
    # ノビ系
    (r'伸び', 'ノビ'),
    (r'のび', 'ノビ'),
    # キリ系
    (r'切り', 'キリ'),
    # 石の数は算用数字（2026-10-08 三村さん「2目の頭、3目以上、算用数字で」）。一つ・二つ は変えない
    (r'(?:(?<=[黒白])|(?<![一-龥]))([二三四五六七八九])(目|子|本)',
     lambda m: str('一二三四五六七八九'.index(m.group(1)) + 1) + m.group(2)),
    (r'(?:(?<=[黒白])|(?<![一-龥]))一(目|子|本)(?=[^いがでるれ見]|$)', r'1\1'),   # 一目でわかる は残す
    # カタカナで聞き取られた「キられ」「マモる」「マモリ」も漢字に（名詞のキリは残す）2026-10-08
    (r'(?<![ァ-ヶー])キ(?=[らりるれろっ])', '切'),
    (r'マモリ', '守り'),
    (r'マモ(?=[らりるれろっ])', '守'),
    # 「取る」も漢字（2026-10-08 指摘「トる☓ 取る◯」）。カタカナで聞き取られたものも戻す
    (r'ト(?=[るらりれっろ])(?<![ア-ン]ト)', '取'),
    # 「節を付ける」は囲碁のツケではない（2026-10-08 指摘）
    (r'節をツケ', '節を付け'),
    # 「攻める」は漢字（2026-10-08 指摘）。名詞の攻め合いだけ「セメアイ」
    (r'(?:攻め合い|セメ合い|攻めアイ)', 'セメアイ'),   # 2026-10-08「全てセメアイに統一」
    (r'イキ(?=[るらりれっろ])', '活き'),   # 「イキる」ではなく「活きる」(同日)
    # 動詞の「切る」は漢字（2026-10-08 三村さん「キるではなく切るに統一」）。名詞のキリだけカタカナ
    # 「守る」も囲碁用語ではないので漢字（同日）。「〜を当て」はアテ（正解を「当てる」は変えない）
    (r'(?<=を)当て', 'アテ'),
    # 「はっきり」「すっきり」「思いきり」を壊さない
    (r'(?<![っんいし])きり', 'キリ'),
    # ワタリ系
    (r'渡り', 'ワタリ'),
    (r'渡る', 'ワタる'),
    (r'わたり', 'ワタリ'),
    # サガリ系
    (r'下がり', 'サガリ'),
    (r'下がる', 'サガる'),
    (r'さがり', 'サガリ'),
    # ツケ系
    # 「力をつけて」「気をつけて」「見つけ」を壊さない。石に付ける時(にツケ・をツケ以外)は文脈依存なのでLLM補正に任せる
    (r'(?<=[にっ])つけ', 'ツケ'),
    # マガリ系
    (r'曲が', 'マガ'),
    (r'まが', 'マガ'),
    # カカリ系
    (r'かかり', 'カカリ'),
    # ケイマ
    (r'けいま', 'ケイマ'),
    # ウチコミ系
    (r'うちこみ', 'ウチコミ'),
    (r'打ち込み', 'ウチコミ'),
    (r'打ち込[むんめ]', lambda m: 'ウチコ' + m.group(0)[-1]),
    # ワリコミ系
    (r'わりこみ', 'ワリコミ'),
    (r'割り込み', 'ワリコミ'),
    # ヌキ系は廃止（2026-10-09 三村さん「手をヌく は使わない。抜くとするのがよい」）。
    # 表記の判断は go-term-style.md（表記台帳）が正本
]

# --- ASS字幕テンプレート ---

# BorderStyle 3 = opaque box background
# Alignment 7 = top-left
# BackColour alpha: 80 (hex) = 50% transparent
ASS_HEADER = """\ufeff[Script Info]
Title: {title}
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Tategaki,IPAGothic,{tate_fs},&H00FFFFFF,&H000000FF,&H00000000,&H80384030,-1,0,0,0,100,100,8,0,3,2,0,7,25,0,20,1
Style: Yokogaki,IPAGothic,72,&H00FFFFFF,&H000000FF,&H00000000,&H80384030,-1,0,0,0,100,100,0,0,3,2,0,1,30,30,30,1
Style: Migiue,Noto Sans CJK JP,{right_fs},&H00FFFFFF,&H000000FF,&H00384030,&H00384030,-1,0,0,0,100,100,0,0,3,14,0,7,{right_x},0,{right_y},1
Style: Shita,Noto Sans CJK JP,{right_fs},&H00FFFFFF,&H000000FF,&H00384030,&H00384030,-1,0,0,0,100,100,0,0,3,14,0,1,44,0,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

# --- 辞書ロード ---

def load_kishi_dictionary() -> str:
    """棋士名辞書（491人）"""
    kishi_path = Path.home() / "projects" / "kishi-data" / "kishi_dictionary_final.txt"
    if not kishi_path.exists():
        return ""
    lines = []
    with open(kishi_path, "r", encoding="utf-8") as f:
        for line in f:
            cols = line.strip().split("\t")
            if len(cols) >= 2:
                lines.append(f"{cols[0]} → {cols[1]}")
    return "\n".join(lines)


def load_go_terms() -> str:
    """囲碁用語辞書（601語）"""
    master_path = Path.home() / "projects" / "go-dictionary-registration" / "data" / "master.csv"
    if not master_path.exists():
        return ""
    lines = []
    with open(master_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            term = row.get("term_ja", "")
            reading = row.get("reading_ja", "")
            cat = row.get("category", "")
            if term and reading:
                lines.append(f"{reading} → {term}（{cat}）")
            elif term:
                lines.append(f"{term}（{cat}）")
    return "\n".join(lines)

# --- LLM補正（Gemini / Ollama 共通） ---

REFINE_SYSTEM_PROMPT = """\
囲碁の字幕校正者です。音声認識（Whisper）で生成された日本語テキストの誤変換を修正してください。

## ルール
1. 棋士名辞書にある名前は正確な漢字表記に修正する
2. 囲碁用語は正しい表記に修正する
3. 「騎士」→「棋士」「入団」→「入段」「規制戦」→「棋聖戦」「金」→「棋院」など音声認識特有の誤変換を修正する
4. 段位表記を統一する（初段、二段、三段...九段。「初弾」「2弾」等は段位に修正）
5. 文章の意味は変えない。修正が不要なら原文をそのまま返す
6. 修正結果のテキストのみ出力する（説明や注釈は不要）

## 棋士名辞書（読み → 正確な漢字表記）
{kishi_dictionary}

## 囲碁用語辞書
{go_terms}
"""

OLLAMA_MODEL = "hf.co/mmnga-o/NVIDIA-Nemotron-Nano-9B-v2-Japanese-gguf:Q4_K_M"


def _ollama_refine_batch(system_prompt, batch_texts, ollama_host):
    """Ollamaに1バッチ送信し、補正結果テキストを返す（失敗時はNone）"""
    import requests
    try:
        resp = requests.post(
            f"{ollama_host}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"以下の字幕テキストを修正してください:\n\n{batch_texts}"},
                ],
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()
    except Exception as e:
        print(f"  Warning: Ollama補正失敗: {e}")
        return None


def refine_with_ollama(segments, ollama_host, batch_size=10):
    """Ollama LLMでWhisper出力を補正（バッチ処理）"""
    try:
        import requests
    except ImportError:
        print("Warning: requests not installed, skipping LLM refinement")
        return segments

    # 辞書ロード
    kishi_dict = load_kishi_dictionary()
    go_terms = load_go_terms()

    if not kishi_dict and not go_terms:
        print("Warning: 辞書が見つかりません、LLM補正をスキップ")
        return segments

    system_prompt = REFINE_SYSTEM_PROMPT.format(
        kishi_dictionary=kishi_dict,
        go_terms=go_terms,
    )
    print(f"LLM補正(Ollama): 棋士{len(kishi_dict.splitlines())}人 + 囲碁用語{len(go_terms.splitlines())}語")

    # Ollama接続テスト
    try:
        r = requests.get(f"{ollama_host}/api/tags", timeout=5)
        r.raise_for_status()
    except Exception as e:
        print(f"Warning: Ollama接続失敗 ({ollama_host}): {e}")
        return segments

    refined = []
    total = len(segments)

    for i in range(0, total, batch_size):
        batch = segments[i:i + batch_size]
        batch_texts = "\n".join(
            f"[{j+1}] {seg['text']}" for j, seg in enumerate(batch)
        )

        result = _ollama_refine_batch(system_prompt, batch_texts, ollama_host)

        if result:
            # [1] ... [2] ... 形式をパース
            corrected = parse_numbered_response(result, len(batch))
            for j, seg in enumerate(batch):
                new_seg = dict(seg)
                if j < len(corrected) and corrected[j]:
                    new_seg["text"] = corrected[j]
                refined.append(new_seg)
        else:
            refined.extend(batch)

        progress = min(i + batch_size, total)
        print(f"  LLM補正: {progress}/{total} segments")

    return refined


def refine_with_gemini(segments, batch_size=10, ollama_host=None, sleep_sec=7.0):
    """GeminiでWhisper出力を補正（バッチ処理）。

    Gemini自体が使えない場合はOllamaにまるごと委譲。個別バッチだけGeminiが
    失敗した場合は、そのバッチのみOllamaにフォールバックする。
    """
    if not llm_gemini.gemini_available():
        print("Warning: Gemini利用不可 (~/.secrets/gemini.env未設定 or SDK未インストール)")
        if ollama_host:
            print("  → Ollamaにフォールバック")
            return refine_with_ollama(segments, ollama_host, batch_size)
        return segments

    kishi_dict = load_kishi_dictionary()
    go_terms = load_go_terms()

    if not kishi_dict and not go_terms:
        print("Warning: 辞書が見つかりません、LLM補正をスキップ")
        return segments

    system_prompt = REFINE_SYSTEM_PROMPT.format(
        kishi_dictionary=kishi_dict,
        go_terms=go_terms,
    )
    print(f"LLM補正(Gemini): 棋士{len(kishi_dict.splitlines())}人 + 囲碁用語{len(go_terms.splitlines())}語")

    refined = []
    total = len(segments)

    for i in range(0, total, batch_size):
        batch = segments[i:i + batch_size]
        batch_texts = "\n".join(
            f"[{j+1}] {seg['text']}" for j, seg in enumerate(batch)
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"以下の字幕テキストを修正してください:\n\n{batch_texts}"},
        ]
        result = llm_gemini.chat(messages, temperature=0.1)

        if result is None and ollama_host:
            print(f"  Gemini失敗 (batch {i//batch_size + 1}) → このバッチのみOllamaにフォールバック")
            result = _ollama_refine_batch(system_prompt, batch_texts, ollama_host)

        if result:
            corrected = parse_numbered_response(result, len(batch))
            for j, seg in enumerate(batch):
                new_seg = dict(seg)
                if j < len(corrected) and corrected[j]:
                    new_seg["text"] = corrected[j]
                refined.append(new_seg)
        else:
            refined.extend(batch)

        progress = min(i + batch_size, total)
        print(f"  LLM補正: {progress}/{total} segments")

        if i + batch_size < total:
            time.sleep(sleep_sec)  # 無料枠 RPM/TPM 対策

    return refined


def parse_numbered_response(text, expected_count):
    """[1] ... [2] ... 形式のレスポンスをパース"""
    lines = text.strip().split("\n")
    results = {}

    for line in lines:
        line = line.strip()
        m = re.match(r'\[(\d+)\]\s*(.*)', line)
        if m:
            idx = int(m.group(1)) - 1
            results[idx] = m.group(2).strip()

    # 番号なしの場合（1行ずつ返ってきた場合）
    if not results and len(lines) == expected_count:
        return [l.strip() for l in lines]

    # 番号ありの場合
    return [results.get(i, "") for i in range(expected_count)]


# --- テキスト処理 ---

_KATAKANA = re.compile(r'[ァ-ヶー]')


def correct_text(text, go_terms=True):
    """囲碁用語の修正: 手動辞書 → 自動収集辞書 → 正規表現活用形変換（長いキー優先）

    go_terms=False: 漢字をカタカナの囲碁用語に変える置き換え（抑え→オサエ・下がる→サガる 等）を止める。
    ランキング動画のように手筋の話がほぼ無い動画では「順位が下がる」まで壊すため。聞き間違いの修正は残す
    """
    # 手動辞書（優先）+ 自動収集辞書をマージ（手動側が優先）
    merged = {**GO_CORRECTIONS_AUTO, **GO_CORRECTIONS}
    if not go_terms:
        merged = {k: v for k, v in merged.items() if _KATAKANA.search(k) or not _KATAKANA.search(v)}
    for wrong in sorted(merged.keys(), key=len, reverse=True):
        text = text.replace(wrong, merged[wrong])
    if not go_terms:
        return text
    for pattern, repl in GO_VERB_RULES:
        if callable(repl):
            text = re.sub(pattern, repl, text)
        else:
            text = re.sub(pattern, repl, text)
    return text


def time_to_ass(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def to_vertical(text):
    """横書き→縦書き変換: 各文字を\\Nで区切る（数字・カタカナ考慮）"""
    vertical_map = {
        '（': '︵', '）': '︶',
        '「': '﹁', '」': '﹂',
        '、': '︑', '。': '︒',
        'ー': '︱', '—': '︱', '─': '︱',
        '？': '？', '！': '！',
        '・': '・',
    }

    # 数字（1〜2桁）を縦中横にまとめる
    # カタカナ連続はそのまま縦に並べる（個別文字で問題ない）
    chars = list(text)
    result = []
    i = 0
    while i < len(chars):
        ch = chars[i]
        # 半角数字2桁をまとめる
        if ch.isdigit() and i + 1 < len(chars) and chars[i + 1].isdigit():
            result.append(ch + chars[i + 1])
            i += 2
            continue
        # 全角数字2桁をまとめる
        if '\uff10' <= ch <= '\uff19' and i + 1 < len(chars) and '\uff10' <= chars[i + 1] <= '\uff19':
            result.append(ch + chars[i + 1])
            i += 2
            continue
        result.append(vertical_map.get(ch, ch))
        i += 1

    return '\\N'.join(result)


def review_names(transcript):
    """人名が含まれそうなセグメントを抽出して表示"""
    # 人名を示唆するパターン（囲碁用語カタカナは除外）
    name_patterns = [
        r'[一-龥]{2,4}[一二三四五六七八九十]?段',  # X段
        r'[一-龥]{2,4}さん',  # Xさん
        r'[一-龥]{2,4}先生',  # X先生
        r'[一-龥]{2,4}名人',  # X名人
        r'[一-龥]{2,4}棋聖',  # X棋聖
        r'[一-龥]{2,4}本因坊',  # X本因坊
    ]
    combined = re.compile('|'.join(name_patterns))

    found = []
    for i, seg in enumerate(transcript):
        text = seg['text'].strip()
        matches = combined.findall(text)
        if matches:
            m = int(seg['start'] // 60)
            s = int(seg['start'] % 60)
            found.append((i, f"{m:02d}:{s:02d}", text, matches))

    if not found:
        print("\n人名候補: なし")
        return

    print(f"\n=== 人名候補: {len(found)}箇所 ===")
    for i, ts, text, matches in found:
        print(f"  [{i+1}] {ts}  {text}")
        print(f"         検出: {', '.join(matches)}")
    print("=" * 40)
    print("修正が必要なら GO_CORRECTIONS に追加してください\n")


# 縦書き1列に入る字数の目安（1080px - 上下余白 を 1字あたり fs*1.1px で割る。実測で決めた係数）
def tate_max_chars(fs):
    return max(8, int((1080 - 60) / (fs * 1.07)))


# 区切ってよい位置の強さ。3=句読点の後 2=助詞の後で次が漢字/カタカナ 1=ひらがな→漢字/カタカナ 0=語の途中
_PUNCT = '、。？！'
_PARTICLES = ('から', 'けど', 'ので', 'けれども', 'ても', 'では', 'には', 'のが', 'のは',
              'は', 'が', 'を', 'に', 'で', 'と', 'も', 'ね', 'よ', 'て', 'ば', 'へ')
_LONG_PARTICLES = ('から', 'けど', 'ので', 'けれども', 'ても', 'には')  # 「では」は「ではなく」を割るので入れない


def _kind(ch):
    if '\u3040' <= ch <= '\u309f':
        return 'hira'
    if '\u30a0' <= ch <= '\u30ff':
        return 'kata'
    if '\u4e00' <= ch <= '\u9fff' or ch in '々〆':
        return 'kanji'
    return 'other'


def _break_score(text, i):
    """text[:i] と text[i:] の間で切るときの良さ"""
    a, b = text[i - 1], text[i]
    head = text[:i]
    if a in _PUNCT:
        return 3
    if _kind(a) == 'hira' and _kind(b) in ('kanji', 'kata', 'other'):
        return 2 if head.endswith(_PARTICLES) else 1
    if head.endswith(_LONG_PARTICLES) and _kind(b) == 'hira':
        return 1   # 「〜けれども｜いい」など。1字の助詞は語の一部と区別できないので切らない
    return 0


_CUT_PENALTY = {3: 0, 2: 1, 1: 4, 0: 40, -1: 1000}  # -1: 数字・英字の途中（「20｜26年」）は切らない

try:  # 文節区切り（Chrome の auto-phrase と同じ BudouX）。無ければ上の字種の規則で代用
    import budoux
    _BUDOUX = budoux.load_default_japanese_parser()
except ImportError:
    _BUDOUX = None


def _scores(text):
    """各位置 i (1..len-1) で切るときの良さ。BudouX があれば文節の境目=2、句読点の後=3"""
    if _BUDOUX is None:
        return {i: _break_score(text, i) for i in range(1, len(text))}
    bounds, pos = set(), 0
    for ph in _BUDOUX.parse(text)[:-1]:
        pos += len(ph)
        bounds.add(pos)
    return {i: 3 if text[i - 1] in _PUNCT else 2 if i in bounds else _inside_score(text, i) for i in range(1, len(text))}


def _inside_score(text, i):
    """文節の中で切るときの良さ。数字・英字の途中は不可(-1)、字種が変わる所（ランキング｜2026）はまし(1)"""
    def word(c):  # 数字・英字・小数点（9.963）をひと続きとみなす
        return c.isascii() and (c.isalnum() or c == ".")
    a, b = text[i - 1], text[i]
    if word(a) and word(b):
        return -1
    return 1 if word(a) != word(b) else 0


def split_phrases(text, max_chars, chunk_cost=12):
    """max_chars 字以内の塊に分ける。塊の数を少なく、語の途中では切らず、長さを揃える（動的計画法）"""
    n = len(text)
    if n <= max_chars:
        return [text]
    INF = float('inf')
    best = [INF] * (n + 1)
    prev = [0] * (n + 1)
    best[0] = 0
    score = _scores(text)
    for i in range(1, n + 1):
        cut = 0 if i == n else _CUT_PENALTY[score[i]]
        for j in range(max(0, i - max_chars), i):
            if best[j] == INF:
                continue
            short = max_chars - (i - j)
            cost = best[j] + chunk_cost + cut + 0.05 * short * short
            if cost < best[i]:
                best[i], prev[i] = cost, j
    out, i = [], n
    while i > 0:
        out.append(text[prev[i]:i])
        i = prev[i]
    return out[::-1]


def split_for_column(text, max_chars):
    """1列に収まらない文を、意味の切れ目で分ける"""
    return split_phrases(text, max_chars)


def wrap_lines(text, per_line):
    """1画面分の文を per_line 字以内の行に、意味の切れ目で折る"""
    return split_phrases(text, per_line)


def generate_ass(transcript, output_path, title="囲碁講座", horizontal=False, tate_fs=72,
                 right=False, right_fs=72, right_x=1080, right_y=40, right_chars=13, right_lines=2,
                 bottom=False):
    """Whisper JSONからASS字幕ファイルを生成

    right=True: 碁盤を左端に寄せた画面向け。右上に横書きで right_chars 字×right_lines 行まで出す
    bottom=True: 表が横幅いっぱいの画面（ランキング動画）向け。左下に同じ折り返しで出す（右下の顔ワイプを避けて字数を決める）
    """
    style = "Shita" if bottom else "Migiue" if right else "Yokogaki" if horizontal else "Tategaki"
    with open(output_path, 'w', encoding='utf-8') as f:  # ASS_HEADER の先頭に BOM があるので utf-8-sig だと二重になり libass が読めない
        f.write(ASS_HEADER.format(title=title, tate_fs=tate_fs,
                                  right_fs=right_fs, right_x=right_x, right_y=right_y))
        count = 0
        for seg in transcript:
            text = seg['text'].strip()
            if not text:
                continue
            if right or bottom:
                # 意味の切れ目で行に折り、right_lines 行ずつ1画面にする。時間は字数で按分
                lines = wrap_lines(text, right_chars)
                screens = [lines[k:k + right_lines] for k in range(0, len(lines), right_lines)]
                t, dur = seg['start'], seg['end'] - seg['start']
                for scr in screens:
                    ce = t + dur * sum(map(len, scr)) / len(text)
                    f.write(f"Dialogue: 0,{time_to_ass(t)},{time_to_ass(ce)},{style},,0,0,0,,{'\\N'.join(scr)}\n")
                    t = ce
                    count += 1
            elif horizontal:
                # 長いテロップは25文字ごとに分割し、時間を按分
                max_chars = 25
                if len(text) <= max_chars:
                    f.write(f"Dialogue: 0,{time_to_ass(seg['start'])},{time_to_ass(seg['end'])},{style},,0,0,0,,{text}\n")
                    count += 1
                else:
                    chunks = [text[i:i+max_chars] for i in range(0, len(text), max_chars)]
                    duration = seg['end'] - seg['start']
                    chunk_dur = duration / len(chunks)
                    for ci, chunk in enumerate(chunks):
                        cs = seg['start'] + chunk_dur * ci
                        ce = seg['start'] + chunk_dur * (ci + 1)
                        f.write(f"Dialogue: 0,{time_to_ass(cs)},{time_to_ass(ce)},{style},,0,0,0,,{chunk}\n")
                        count += 1
            else:
                # 1列に入らない分は分割し、字数で時間を按分する
                chunks = split_for_column(text, tate_max_chars(tate_fs))
                t, dur = seg['start'], seg['end'] - seg['start']
                for chunk in chunks:
                    ce = t + dur * len(chunk) / len(text)
                    f.write(f"Dialogue: 0,{time_to_ass(t)},{time_to_ass(ce)},{style},,0,0,0,,{to_vertical(chunk)}\n")
                    t = ce
                    count += 1
    kind = '左下横書き' if bottom else '右上横書き' if right else '横書き' if horizontal else '縦書き'
    print(f"Generated: {output_path} ({count} entries, {kind})")


def main():
    parser = argparse.ArgumentParser(
        description='Whisper文字起こし → LLM補正 → 囲碁用語修正 → ASS縦書き字幕生成'
    )
    parser.add_argument('transcript', help='Whisper JSON file ([{start, end, text}, ...])')
    parser.add_argument('-o', '--output', default='/tmp/telops.ass', help='出力ASSファイルパス')
    parser.add_argument('-t', '--title', default='囲碁講座', help='字幕タイトル')
    parser.add_argument('--no-llm', action='store_true', help='LLM補正をスキップ（辞書ルールのみ。--llm-backend none と同義）')
    parser.add_argument('--llm-backend', choices=['gemini', 'ollama', 'none'], default='gemini',
                         help='LLM補正バックエンド（デフォルト: gemini。利用不可/失敗時はOllamaに自動フォールバック）')
    parser.add_argument('--gemini-sleep', type=float, default=7.0,
                         help='Geminiバッチ間の待機秒数（無料枠 RPM/TPM 対策）')
    parser.add_argument('--save-refined-json', help='LLM補正+辞書補正後のtranscriptをJSON保存（メタデータ生成の入力に使う）')
    parser.add_argument('--ollama-host', default='http://localhost:11434', help='Ollamaホスト')
    parser.add_argument('--batch-size', type=int, default=10, help='LLMバッチサイズ')
    parser.add_argument('--review-names', action='store_true', help='人名候補を表示して確認')
    parser.add_argument('--horizontal', action='store_true', help='横書き字幕（最下段左揃え）')
    parser.add_argument('--right', action='store_true',
                        help='右上に横書き（碁盤を左端へ寄せた画面用。layout_right.py と組で使う）')
    parser.add_argument('--no-go-terms', action='store_true',
                        help='囲碁用語のカタカナ化（抑え→オサエ等）をしない。ランキング動画など手筋の話が無い動画用')
    parser.add_argument('--bottom', action='store_true',
                        help='左下に横書き（表が横幅いっぱいのランキング動画用。右下の顔ワイプを避けて1行17字）')
    parser.add_argument('--right-size', type=int, default=72, help='右上・左下横書きの文字サイズ(px)')
    parser.add_argument('--right-x', type=int, default=1080, help='右上横書きの左端x(px)。碁盤の右端+余白')
    parser.add_argument('--right-y', type=int, default=40,
                        help='右上横書きの上端y(px)。右上に題字やロゴがある画面ではその下に下げる（石の形講座は360）')
    parser.add_argument('--right-chars', type=int, default=None,
                        help='横書き1行の字数（既定: 右上13・左下17）。右の空きが狭いとき減らす（72pxで810px幅なら11）')
    parser.add_argument('--tate-size', type=int, default=72, help='縦書き字幕の文字サイズ(px)。38では小さすぎると指摘あり')
    parser.add_argument('--kishi-fix', action='store_true', help='棋士名辞書で自動修正（pykakasi）')
    args = parser.parse_args()

    if args.no_llm:
        args.llm_backend = 'none'

    with open(args.transcript) as f:
        transcript = json.load(f)

    print(f"Transcript: {len(transcript)} segments")

    # LLM補正
    if args.llm_backend == 'ollama':
        transcript = refine_with_ollama(transcript, args.ollama_host, args.batch_size)
    elif args.llm_backend == 'gemini':
        transcript = refine_with_gemini(transcript, args.batch_size, ollama_host=args.ollama_host, sleep_sec=args.gemini_sleep)

    # ルールベース修正を適用
    for seg in transcript:
        seg['text'] = correct_text(seg['text'].strip(), go_terms=not args.no_go_terms)

    # 棋士名辞書修正（pykakasi読み→正字）
    if args.kishi_fix:
        transcript = fix_kishi_names(transcript)

    # 人名レビュー
    if args.review_names:
        review_names(transcript)

    if args.save_refined_json:
        with open(args.save_refined_json, 'w', encoding='utf-8') as f:
            json.dump(transcript, f, ensure_ascii=False, indent=2)
        print(f"Refined transcript saved: {args.save_refined_json}")

    # ASS生成
    generate_ass(transcript, args.output, args.title, horizontal=args.horizontal, tate_fs=args.tate_size,
                 right=args.right, right_fs=args.right_size, right_x=args.right_x, right_y=args.right_y,
                 bottom=args.bottom, right_chars=args.right_chars or (17 if args.bottom else 13))


if __name__ == '__main__':
    main()
