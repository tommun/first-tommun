import os
import re
import html
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional, List

class DLsiteMetadataFetcher:
    """RJコードやタイトルからDLsite公式のメタデータ（タイトル、サークル、作品形式ジャンル、タグ、ジャケット等）を取得"""

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Cookie": "adultchecked=1"
    }

    @classmethod
    def fetch_by_rj(cls, rj_code: str) -> Optional[Dict[str, Any]]:
        if not rj_code:
            return None
        rj = rj_code.upper().strip()
        urls = [
            f"https://www.dlsite.com/maniax/work/=/product_id/{rj}.html",
            f"https://www.dlsite.com/home/work/=/product_id/{rj}.html",
            f"https://www.dlsite.com/pro/work/=/product_id/{rj}.html",
        ]

        for url in urls:
            try:
                req = urllib.request.Request(url, headers=cls.HEADERS)
                with urllib.request.urlopen(req, timeout=6) as res:
                    content = res.read().decode("utf-8", errors="ignore")

                # タイトル取得
                m_title = re.search(r'id="work_name"[^>]*>(.*?)</h1>', content, re.DOTALL)
                title = html.unescape(re.sub(r'<[^>]+>', '', m_title.group(1)).strip()) if m_title else ""
                if not title:
                    m_og = re.search(r'<meta property="og:title" content="([^"]+)"', content)
                    if m_og:
                        og_t = html.unescape(m_og.group(1))
                        title = re.sub(r'\s*\[.*?\]\s*\|\s*DLsite.*$', '', og_t).strip()

                if not title:
                    continue

                # サークル名 / メーカー名
                m_maker = re.search(r'class="maker_name"[^>]*>(.*?)</span>', content, re.DOTALL)
                maker = html.unescape(re.sub(r'<[^>]+>', '', m_maker.group(1)).strip()) if m_maker else ""
                if not maker:
                    m_dm = re.search(r'data-maker_name="([^"]+)"', content)
                    if m_dm:
                        maker = html.unescape(m_dm.group(1).strip())

                # メイン画像URL
                m_img = re.search(r'<meta property="og:image" content="([^"]+)"', content)
                img_url = m_img.group(1) if m_img else ""

                # 作品アウトラインテーブル解析
                outline = {}
                tables = re.findall(r'<table[^>]*>(.*?)</table>', content, re.DOTALL)
                for t in tables:
                    rows = re.findall(r'<tr[^>]*>\s*<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>\s*</tr>', t, re.DOTALL)
                    for th, td in rows:
                        th_clean = re.sub(r'<[^>]+>', '', th).strip()
                        td_clean = html.unescape(re.sub(r'<[^>]+>', ' ', td).strip())
                        td_clean = re.sub(r'\s+', ' ', td_clean)
                        outline[th_clean] = td_clean

                # 公式ジャンルタグ一覧 (/from/work.genre)
                tags = []
                genre_links = re.findall(r'/from/work\.genre/ana_flg/all">([^<]+)</a>', content)
                for g in genre_links:
                    g_clean = html.unescape(g.strip())
                    if g_clean and g_clean not in tags:
                        tags.append(g_clean)

                # ゲームの主ジャンル判定（作品形式から抽出）
                # 例: ロールプレイング, アクション, アドベンチャー, シミュレーション, パズル, etc.
                raw_fmt = outline.get("作品形式", "")
                primary_genre = "その他"
                genre_candidates = [
                    "ロールプレイング", "アクション", "アドベンチャー", "シミュレーション",
                    "パズル", "シューティング", "クイズ", "音ゲー", "ストラテジー",
                    "ノベル", "デジタルノベル", "3Dゲーム"
                ]
                for cand in genre_candidates:
                    if cand in raw_fmt:
                        primary_genre = cand
                        break

                # ゲームかどうかの厳密判定（ボイス・ASMR、マンガ、CG集、動画等は除外）
                is_game = any(cand in raw_fmt for cand in genre_candidates) or "ゲーム" in raw_fmt
                if any(non_game in raw_fmt for non_game in ["ボイス・ASMR", "同人音声", "ボイスドラマ", "マンガ", "CG・イラスト", "動画"]):
                    if not any(g in raw_fmt for g in ["ゲーム", "RPG", "ADV", "ACT", "SLG"]):
                        is_game = False

                return {
                    "rj_code": rj,
                    "title": title,
                    "maker": maker or "不明",
                    "genre": primary_genre,
                    "tags": tags,
                    "image_url": img_url,
                    "work_format": raw_fmt,
                    "is_game": is_game,
                    "voice_actors": outline.get("声優"),
                    "release_date": outline.get("販売日"),
                    "series": outline.get("シリーズ名"),
                    "url": url
                }
            except Exception:
                continue
        return None

    @classmethod
    def search_rj_by_title(cls, title: str) -> Optional[str]:
        """タイトルからDLsiteを検索してRJ番号を取得"""
        if not title:
            return None

        # クリーンアップ
        clean = re.sub(r'\[[^\]]*\]|【[^】]*】|\([^)]*\)|（[^）]*）', '', title).strip()
        clean = re.sub(r'[-_ ]*(v|ver|version)?[._ ]*\d+(\.\d+)+.*', '', clean, flags=re.IGNORECASE).strip()
        clean = re.sub(r'[-_ ]*(製品版|体験版|完全版|先行版|trial|signed|fanza|dl)', '', clean, flags=re.IGNORECASE).strip()
        if not clean:
            clean = title.strip()

        enc = urllib.parse.quote(clean)
        urls = [
            f"https://www.dlsite.com/maniax/fsr/=/language/jp/keyword/{enc}",
            f"https://www.dlsite.com/home/fsr/=/language/jp/keyword/{enc}",
        ]

        for u in urls:
            try:
                req = urllib.request.Request(u, headers=cls.HEADERS)
                with urllib.request.urlopen(req, timeout=6) as res:
                    content = res.read().decode("utf-8", errors="ignore")

                m_rj = re.findall(r'/product_id/(RJ\d+|VJ\d+|BJ\d+)\.html', content, re.IGNORECASE)
                if m_rj:
                    return m_rj[0].upper()
            except Exception:
                continue
        return None

    @classmethod
    def get_metadata_for_game(cls, game: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """ゲーム辞書からRJコードまたはタイトルをもとにDLsiteメタデータを取得"""
        rj = game.get("rj_code")
        if not rj or not re.match(r'^(RJ|VJ|BJ)\d+$', rj, re.IGNORECASE):
            # タイトルから探索
            name = game.get("name", "")
            rj = cls.search_rj_by_title(name)
            if not rj and game.get("folder_path"):
                f_name = os.path.basename(game["folder_path"])
                rj = cls.search_rj_by_title(f_name)

        if rj:
            return cls.fetch_by_rj(rj)
        return None
