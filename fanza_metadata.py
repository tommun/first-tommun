from title_utils import clean_game_name
import os
import re
import json
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional, List, Tuple
from icon_helper import QUALITY_DLSITE_OFFICIAL

class FANZAMetadataFetcher:
    """FANZA (DMM) 公式からゲーム・同人作品のメタデータ（タイトル、メーカー、ジャンル、タグ、公式パッケージ画像）を取得"""

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Cookie": "age_check_done=1; m_age_check=1"
    }

    @classmethod
    def fetch_by_cid(cls, cid: str) -> Optional[Dict[str, Any]]:
        """CID（コンテンツID、例: d_186424）からFANZA公式ページを検索/取得"""
        if not cid:
            return None
        clean_cid = cid.strip().lower()
        return cls._execute_search(clean_cid)

    @classmethod
    def search_by_title(cls, title: str, maker_hint: str = "") -> Optional[Dict[str, Any]]:
        """タイトル名（＋メーカー名ヒント）からFANZAを検索し、最適な公式メタデータを取得"""
        if not title:
            return None

        # クリーンアップ: 角括弧、ver表記、fanza、製品版等の文字を除去
        clean = re.sub(r'\[[^\]]*\]|【[^】]*】|\([^)]*\)|（[^）]*）', '', title)
        clean = re.sub(r'[-_ ]*fanza.*$', '', clean, flags=re.IGNORECASE).strip()
        clean = re.sub(r'[-_ ]*(v|ver|version)?[._ ]*\d+.*$', '', clean, flags=re.IGNORECASE).strip()
        clean = re.sub(r'(製品版|体験版|DL版|パッケージ版|ダウンロード版)', '', clean).strip()

        candidates = []
        if clean:
            candidates.append(clean)
        for sep in ['〜', '～', ' - ', '-']:
            if sep in clean:
                part = clean.split(sep)[0].strip()
                if part and part not in candidates:
                    candidates.append(part)
        if title not in candidates:
            candidates.append(title)

        for query in candidates:
            res = cls._execute_search(query)
            if res:
                return res

        return None

    @classmethod
    def _execute_search(cls, query: str) -> Optional[Dict[str, Any]]:
        encoded = urllib.parse.quote(query)
        url = f"https://www.dmm.co.jp/search/=/searchstr={encoded}/"
        try:
            req = urllib.request.Request(url, headers=cls.HEADERS)
            with urllib.request.urlopen(req, timeout=8) as resp:
                html = resp.read().decode("utf-8", errors="ignore")

            idx = html.find('backendResponse\\":')
            if idx != -1:
                sub = html[idx + len('backendResponse\\":'):]
                bracket_count = 0
                end_idx = -1
                for i, c in enumerate(sub):
                    if c == '{':
                        bracket_count += 1
                    elif c == '}':
                        bracket_count -= 1
                        if bracket_count == 0:
                            end_idx = i + 1
                            break
                if end_idx != -1:
                    raw_json_str = sub[:end_idx].replace('\\"', '"').replace('\\\\', '\\')
                    b_json = json.loads(raw_json_str)
                    contents = b_json.get('contents', {})
                    items = contents.get('data', [])
                    if items:
                        first = items[0]
                        content_id = first.get('content_id', '')
                        p_title = clean_game_name(first.get('title', ''))
                        detail_url = first.get('detail_url', '')
                        makers = first.get('makers', [])
                        maker_name = makers[0] if makers else "不明"
                        keywords = first.get('keywords', [])

                        thumb = first.get('thumbnail_image_url', '')
                        high_res_img = ""
                        if thumb and content_id:
                            high_res_img = re.sub(r'-\d+x\d+\.jpg$', '.jpg', thumb)
                        elif thumb:
                            high_res_img = thumb

                        primary_genre = "その他"
                        genre_candidates = [
                            "ロールプレイング", "アクション", "アドベンチャー", "シミュレーション",
                            "パズル", "シューティング", "クイズ", "ノベル", "デジタルノベル"
                        ]
                        tags = []
                        for kw in keywords:
                            if kw in genre_candidates and primary_genre == "その他":
                                primary_genre = kw
                            elif kw not in tags:
                                tags.append(kw)

                        return {
                            "content_id": content_id,
                            "title": p_title,
                            "maker": maker_name,
                            "genre": primary_genre,
                            "tags": tags,
                            "image_url": high_res_img,
                            "url": detail_url or f"https://www.dmm.co.jp/dc/doujin/-/detail/=/cid={content_id}/"
                        }
        except Exception:
            pass

        return None


class FANZAPurchaseImporter:
    """FANZA (DMM) の購入履歴や所持作品（HTML / CIDリスト / タイトル一覧）を取り込み・照合"""

    @classmethod
    def extract_cids_and_titles(cls, text_content: str) -> List[Dict[str, str]]:
        """HTMLやテキストからCID (例: d_186424, 5036d_001, etc.) や商品リンク、タイトルを抽出"""
        results = []
        seen = set()

        # 1. CIDリンク (https://www.dmm.co.jp/.../cid=xxx/)
        cid_links = re.findall(r'cid=([a-zA-Z0-9_\-]+)', text_content)
        for cid in cid_links:
            cid_lower = cid.lower()
            if cid_lower not in seen and not cid_lower.startswith('rank'):
                seen.add(cid_lower)
                results.append({"type": "cid", "value": cid_lower})

        # 2. テキスト各行（作品名やCIDが並んでいる場合）
        for line in text_content.splitlines():
            line_s = line.strip()
            if not line_s or line_s.startswith("<") or len(line_s) < 2:
                continue
            # 単一CID形式
            if re.match(r'^[a-zA-Z0-9_\-]+$', line_s) and len(line_s) >= 4:
                c_low = line_s.lower()
                if c_low not in seen:
                    seen.add(c_low)
                    results.append({"type": "cid", "value": c_low})
            elif line_s not in seen and not line_s.startswith("http"):
                seen.add(line_s)
                results.append({"type": "title", "value": line_s})

        return results

    @classmethod
    def extract_from_html_file(cls, file_path: str) -> List[Dict[str, str]]:
        if not os.path.exists(file_path):
            return []
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            return cls.extract_cids_and_titles(content)
        except Exception:
            return []

    @classmethod
    def sync_fanza_games(
        cls,
        items: List[Dict[str, str]],
        config_mgr,
        icon_helper,
        progress_callback=None
    ) -> Tuple[int, int]:
        """
        FANZA購入作品一覧をローカルライブラリと同期。
        マッチした既存作品には公式パッケージ画像やタイトル・サークル・ジャンル・タグを即座に更新。
        未インストール作品は新規登録。
        """
        existing_games = config_mgr.games
        matched_count = 0
        newly_added_count = 0

        total = len(items)
        for idx, item in enumerate(items):
            val = item["value"]
            if progress_callback:
                progress_callback(idx + 1, total, val)

            meta = None
            if item["type"] == "cid":
                meta = FANZAMetadataFetcher.fetch_by_cid(val)
            else:
                meta = FANZAMetadataFetcher.search_by_title(val)

            if not meta:
                continue

            content_id = meta.get("content_id", "")
            title = clean_game_name(meta.get("title", val))
            maker = meta.get("maker", "不明")
            genre = meta.get("genre", "その他")
            tags = meta.get("tags", [])
            fanza_url = meta.get("url", "")
            img_url = meta.get("image_url", "")

            # 既存ローカルゲームとの照合
            found_game = None
            for g in existing_games:
                # CID一致またはタイトル部分一致
                g_fanza_cid = g.get("fanza_cid", "")
                g_name = g.get("name", "")
                g_path = g.get("path", "")
                if content_id and g_fanza_cid and g_fanza_cid.lower() == content_id.lower():
                    found_game = g
                    break
                # タイトルの主要部分が一致
                clean_title = re.sub(r'\[.*?\]|【.*?】|\(.*?\)|（.*?）', '', title).strip()
                clean_g = re.sub(r'\[.*?\]|【.*?】|\(.*?\)|（.*?）', '', g_name).strip()
                clean_g = re.sub(r'[-_ ]*(v|ver|version)?[._ ]*\d+(\.\d+)+.*', '', clean_g, flags=re.IGNORECASE).strip()
                clean_g = re.sub(r'[-_ ]*fanza.*$', '', clean_g, flags=re.IGNORECASE).strip()
                if clean_title and clean_g and (clean_title in clean_g or clean_g in clean_title):
                    found_game = g
                    break

            # サムネイル画像のキャッシュ＆更新
            icon_path = ""
            if img_url:
                img = icon_helper.download_image(img_url)
                if img:
                    cache_id = f"fanza_{content_id}" if content_id else f"fanza_{abs(hash(title))}"
                    icon_path = icon_helper.cache_image(cache_id, img)

            if found_game:
                # 既存ゲームの情報をFANZA公式情報＆公式画像に差し替え！
                found_game["platform"] = "FANZA"
                found_game["is_purchased"] = True
                found_game["fanza_cid"] = content_id
                found_game["fanza_url"] = fanza_url
                if genre and genre != "その他":
                    found_game["genre"] = genre
                    found_game["category"] = genre
                if tags:
                    for t in tags:
                        if t not in found_game.get("tags", []):
                            found_game.setdefault("tags", []).append(t)
                if maker and maker != "不明":
                    found_game["author"] = maker
                # 商品ページ画像に差し替え (icon_locked でない場合)
                if icon_path and not found_game.get("icon_locked"):
                    found_game["icon_path"] = icon_path
                    found_game["icon_quality"] = QUALITY_DLSITE_OFFICIAL
                matched_count += 1
            else:
                # 未インストールのFANZA購入作品として新規登録
                new_game = {
                    "name": title,
                    "author": maker,
                    "platform": "FANZA",
                    "genre": genre,
                    "category": genre,
                    "tags": tags,
                    "fanza_cid": content_id,
                    "fanza_url": fanza_url,
                    "path": "",
                    "work_dir": "",
                    "folder_path": "",
                    "is_purchased": True,
                    "is_installed": False,
                    "icon_path": icon_path,
                    "icon_quality": QUALITY_DLSITE_OFFICIAL if icon_path else 0
                }
                config_mgr.add_or_update_game(new_game)
                newly_added_count += 1

        config_mgr.save()
        return matched_count, newly_added_count
