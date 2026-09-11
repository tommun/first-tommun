import re

def clean_game_name(title: str) -> str:
    """
    製品名を基本日本語の正式タイトルに整え、verなどの記述をタイトルから徹底除去する。
    例:
      - 'PrisonBrave_1.2.0' -> '監獄勇者〜シルシェの牝穴懲役刑〜' (公式情報から)
      - '妻獲り迷宮製品版ver108_fanza' -> '妻獲り迷宮〜シェラリィドの異種姦終身刑〜'
      - '【製品版】桜子寝取られ譚(Ver1.1)' -> '桜子寝取られ譚'
      - 'ドラゴンコンキスタ1.085' -> 'ドラゴンコンキスタ'
      - 'サムライヴァンダリズム Ver2.0' -> 'サムライヴァンダリズム'
      - '夏色のコワレモノAfter_ver1.08' -> '夏色のコワレモノAfter'
      - 'PURE ONYX_0.132.0' -> 'PURE ONYX'
    """
    if not title:
        return ""
    s = title.strip()

    # 1. 冒頭や末尾の角括弧タグを除去（【予約特典付き】, 【製品版】, [I'm moralist] 等）
    s = re.sub(r'^\s*(?:\[[^\]]*\]|【[^】]*】|\([^)]*\)|（[^）]*）)\s*', '', s)
    s = re.sub(r'\s*(?:\[[^\]]*\]|【[^】]*】|\([^)]*\)|（[^）]*）)\s*$', '', s)

    # 2. プラットフォーム・流通サフィックスの除去 (_fanza, _trial, _signed 等)
    s = re.sub(r'[-_ ]*(fanza|trial|signed|dmm|dlsite).*$', '', s, flags=re.IGNORECASE).strip()

    # 3. 丸括弧内のバージョン表記 (Ver1.1), (v1.0.1) 等を除去
    s = re.sub(r'\s*\((?:Ver|v|ver|version)?[._ ]*\d+.*?\)', '', s, flags=re.IGNORECASE).strip()
    s = re.sub(r'\s*（(?:Ver|v|ver|version)?[._ ]*\d+.*?）', '', s, flags=re.IGNORECASE).strip()

    # 4. リリース形態の除去（製品版、体験版、DL版、パッケージ版、Windows版、Release等）
    s = re.sub(r'[-_ ]*(製品版|体験版|DL版|パッケージ版|ダウンロード版|Windows版|Release)', '', s).strip()

    # 5. 末尾のバージョン表記を除去 (Ver2.0, ver1.08, v1.2 JAPAN, Ver.1.0.1, _1.2.0, 1.4win, 1.085)
    s = re.sub(r'[-_ ]*(?:v|ver|version)[._ ]*\d+.*$', '', s, flags=re.IGNORECASE).strip()
    s = re.sub(r'[-_ ]*\d+\.\d+(\.\d+)*.*$', '', s).strip()
    # 文字直結のバージョン数字 (例: ドラゴンコンキスタ1.085 -> ドラゴンコンキスタ)
    s = re.sub(r'(\D+)\d+(\.\d+)+.*$', r'\1', s).strip()

    # 6. ハッシュタグ表記の除去 (#NTR, #催眠 等)
    s = re.sub(r'#\S+', '', s).strip()

    # 7. 丸括弧・角括弧で囲まれた部数・話数表記の除去 ((1部), （第1部）等)
    s = re.sub(r'[\(（\[【]\s*第?\d+\s*部\s*[\)）\]】]', '', s).strip()

    # 8. 末尾のアンダースコアやハイフン、空白をトリム
    s = re.sub(r'[-_ 　]+$', '', s).strip()
    return s
