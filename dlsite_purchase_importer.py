import os
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from dlsite_metadata import DLsiteMetadataFetcher
from icon_helper import QUALITY_DLSITE_OFFICIAL

class DLsitePurchaseImporter:
    """DLsiteの購入履歴（HTML、テキスト、RJ番号一覧）を解析・取り込み・ローカルゲームと照合"""

    @classmethod
    def extract_rj_codes_from_text(cls, content: str) -> List[str]:
        """HTMLやテキストからすべてのRJ/VJ/BJ番号を重複なく抽出"""
        matches = re.findall(r'(RJ\d{6,8}|VJ\d{6,8}|BJ\d{6,8})', content, re.IGNORECASE)
        unique_rjs = []
        for m in matches:
            u = m.upper()
            if u not in unique_rjs:
                unique_rjs.append(u)
        return unique_rjs

    @classmethod
    def extract_from_html_file(cls, file_path: str) -> List[str]:
        """保存されたHTMLファイルからRJコードを抽出"""
        if not os.path.exists(file_path):
            return []
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            return cls.extract_rj_codes_from_text(content)
        except Exception:
            return []

    @classmethod
    def sync_purchased_games(
        cls,
        rj_codes: List[str],
        config_mgr,
        icon_helper,
        progress_callback=None
    ) -> Tuple[int, int]:
        """
        購入済みRJコード一覧をもとに、ライブラリを同期。
        1. 既存のローカルゲームに該当RJがあれば platform="DLsite", is_purchased=True を付与
        2. 未インストールの購入作品があれば、未インストールゲームとして登録 (DLsiteリンク付き)
        """
        existing_games = config_mgr.games
        matched_local_count = 0
        newly_added_count = 0

        total = len(rj_codes)
        for idx, rj in enumerate(rj_codes):
            if progress_callback:
                progress_callback(idx + 1, total, rj)

            # 既存のローカルゲームと照合
            found_local = False
            for g in existing_games:
                g_rj = (g.get("rj_code") or "").upper()
                if g_rj == rj:
                    g["platform"] = "DLsite"
                    g["is_purchased"] = True
                    found_local = True
                    matched_local_count += 1
                    break

            if not found_local:
                # ローカルにまだない購入作品を登録（未インストール作品）
                meta = DLsiteMetadataFetcher.fetch_by_rj(rj)
                title = meta["title"] if meta else rj
                maker = meta["maker"] if meta else "不明"
                genre = meta["genre"] if meta else "その他"
                tags = meta["tags"] if meta else []
                dlsite_url = meta["url"] if meta else f"https://www.dlsite.com/maniax/work/=/product_id/{rj}.html"

                icon_path = ""
                if meta and meta.get("image_url"):
                    img = icon_helper.download_image(meta["image_url"])
                    if img:
                        icon_path = icon_helper.cache_image(f"dlsite_{rj}", img)

                new_game = {
                    "name": title,
                    "author": maker,
                    "platform": "DLsite",
                    "genre": genre,
                    "category": genre,
                    "tags": tags,
                    "rj_code": rj,
                    "dlsite_url": dlsite_url,
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
        return matched_local_count, newly_added_count
