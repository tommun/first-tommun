import os
import re
import json
import http.cookiejar
import urllib.request
import urllib.parse
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from dlsite_metadata import DLsiteMetadataFetcher
from icon_helper import QUALITY_DLSITE_OFFICIAL

class DLsitePurchaseImporter:
    """DLsiteの購入履歴（ログイン自動取得・HTML・テキスト・RJ番号一覧）を解析・取り込み・ローカルゲームと照合"""

    @classmethod
    def login_and_fetch_purchased_rjs(cls, login_id: str, password: str, progress_callback=None) -> Tuple[bool, str, List[str]]:
        """
        DLsiteにログインしてマイページ（購入履歴）から自動で全購入RJコードをスクレイピング取得
        """
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8'
        }
        
        if progress_callback:
            progress_callback("ログイン認証中...")

        # 1. ログイン画面取得 & CSRFトークン抽出
        try:
            req = urllib.request.Request('https://login.dlsite.com/login?user=self', headers=headers)
            html = opener.open(req).read().decode('utf-8', errors='ignore')
        except Exception as e:
            return False, f"DLsite接続エラー: {e}", []

        token_m = re.search(r'name="_token"\s+value="([^"]+)"', html)
        if not token_m:
            return False, "CSRFトークンの取得に失敗しました。サイト仕様が変更された可能性があります。", []
        token = token_m.group(1)

        # 2. ログインPOST送信
        post_data = urllib.parse.urlencode({
            '_token': token,
            'login_id': login_id.strip(),
            'password': password.strip(),
            'remember': 'true'
        }).encode('utf-8')

        post_req = urllib.request.Request(
            'https://login.dlsite.com/login',
            data=post_data,
            headers={
                'User-Agent': headers['User-Agent'],
                'Referer': 'https://login.dlsite.com/login?user=self',
                'Content-Type': 'application/x-www-form-urlencoded'
            }
        )

        try:
            resp = opener.open(post_req)
            res_html = resp.read().decode('utf-8', errors='ignore')
        except Exception as e:
            return False, f"ログイン通信エラー: {e}", []

        # ログイン判定
        if 'login.dlsite.com' in resp.geturl() and ('ログインIDまたはパスワード' in res_html or '一致しません' in res_html or 'エラー' in res_html):
            err_m = re.search(r'<div class="formError"[^>]*>(.*?)</div>', res_html, re.DOTALL)
            err_text = re.sub(r'<[^>]+>', '', err_m.group(1)).strip() if err_m else "ログインIDまたはパスワードが正しくありません。"
            return False, err_text, []

        if progress_callback:
            progress_callback("ログイン成功！ 購入履歴をスクレイピング中...")

        # 3. 購入履歴ページをスクレイピング (各区分を巡回)
        all_rjs = set()
        sections = ['maniax', 'home', 'pro', 'books']

        for sec in sections:
            page = 1
            while page <= 30: # 1区分最大30ページ (約900作品)
                if progress_callback:
                    progress_callback(f"購入履歴取得中: {sec.upper()} (ページ {page})")
                
                url = f'https://www.dlsite.com/{sec}/mypage/userbuy/=/page/{page}'
                buy_req = urllib.request.Request(url, headers=headers)
                try:
                    b_resp = opener.open(buy_req)
                    b_html = b_resp.read().decode('utf-8', errors='ignore')

                    if 'login.dlsite.com' in b_resp.geturl():
                        break

                    found = re.findall(r'(RJ\d{6,8}|VJ\d{6,8}|BJ\d{6,8})', b_html, re.IGNORECASE)
                    if not found:
                        break

                    added_in_page = 0
                    for rj in found:
                        u = rj.upper()
                        if u not in all_rjs:
                            all_rjs.add(u)
                            added_in_page += 1

                    if added_in_page == 0:
                        break

                    page += 1
                except Exception:
                    break

        result_list = sorted(list(all_rjs))
        if not result_list:
            return True, "ログインに成功しましたが、購入履歴作品が見つかりませんでした。", []

        return True, f"DLsiteから {len(result_list)} 件の購入作品を自動検出しました！", result_list

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
                    
                    # 同期できた作品のサムネイルをDLsite公式商品画像に差し替え＆メタデータ補完
                    meta = DLsiteMetadataFetcher.fetch_by_rj(rj)
                    if meta:
                        g["dlsite_url"] = meta.get("url")
                        if meta.get("genre") and meta["genre"] != "その他":
                            g["genre"] = meta["genre"]
                            g["category"] = meta["genre"]
                        if meta.get("tags"):
                            for t in meta["tags"]:
                                if t not in g.get("tags", []):
                                    g.setdefault("tags", []).append(t)
                        if meta.get("maker") and meta["maker"] != "不明":
                            g["author"] = meta["maker"]
                        if g.get("name", "").upper().startswith("RJ") or not g.get("name"):
                            g["name"] = meta["title"]
                        
                        # 公式サムネイル画像に差し替え（ロックされていない場合）
                        if meta.get("image_url") and not g.get("icon_locked"):
                            img = icon_helper.download_image(meta["image_url"])
                            if img:
                                p = icon_helper.cache_image(f"dlsite_{rj}", img)
                                if p:
                                    g["icon_path"] = p
                                    g["icon_quality"] = QUALITY_DLSITE_OFFICIAL
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
