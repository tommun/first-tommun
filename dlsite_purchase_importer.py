from title_utils import clean_game_name
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
        """保存されたHTMLファイルから正確な購入作品RJコードを抽出"""
        if not os.path.exists(file_path):
            return []
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            # 1. product_id や download リンク、サムネイルリンクからの厳密な作品RJ抽出
            p_matches = re.findall(r'(?:product_id/|_link_|workno=)(RJ\d{6,8}|VJ\d{6,8}|BJ\d{6,8})', content, re.IGNORECASE)
            if p_matches:
                seen = set()
                results = []
                for m in p_matches:
                    u = m.upper()
                    if u not in seen:
                        seen.add(u)
                        results.append(u)
                return results
            return cls.extract_rj_codes_from_text(content)
        except Exception:
            return []

    @classmethod
    def build_local_pc_rj_index(cls, scan_folders: Optional[List[str]] = None) -> Tuple[Dict[str, Tuple[str, str, str]], Dict[str, str]]:
        r"""
        PC内（D:\ゲーム, D:\download, Downloads, スキャン対象フォルダ等）を1度だけ走査し、
        RJコードごとの解凍済みexe情報マップと、zipアーカイブマップを事前構築する。
        戻り値: (installed_map, zip_map)
        installed_map: rj -> (exe_path, work_dir, folder_path)
        zip_map: rj -> zip_path
        """
        import re

        search_dirs = [
            r"D:\ゲーム",
            r"D:\download",
            r"D:\Users\owner\Downloads",
            r"C:\Users\owner\Downloads"
        ]
        if scan_folders:
            for sf in scan_folders:
                if sf and sf not in search_dirs and os.path.exists(sf):
                    search_dirs.append(sf)

        SKIP_DIRS = {"$recycle.bin", "system volume information", "_files", "node_modules", ".git", "__pycache__"}
        
        installed_map: Dict[str, Tuple[str, str, str]] = {}
        zip_map: Dict[str, str] = {}

        rj_regex = re.compile(r'\b(RJ\d{6,8}|VJ\d{6,8}|BJ\d{6,8})\b', re.IGNORECASE)

        for sdir in search_dirs:
            if not os.path.exists(sdir):
                continue
            for root, dirs, files in os.walk(sdir):
                if any(sk in root.lower() for sk in SKIP_DIRS):
                    continue
                dirs[:] = [d for d in dirs if not any(sk in d.lower() for sk in SKIP_DIRS)]

                # フォルダ名にRJコードが含まれるか
                m_dir = rj_regex.search(root)
                if m_dir:
                    found_rj = m_dir.group(1).upper()
                    if found_rj not in installed_map:
                        valid_exes = [
                            os.path.join(root, f) for f in files
                            if f.lower().endswith(".exe") and not any(x in f.lower() for x in ["crash", "setup", "uninstall", "unitycrash", "update"])
                        ]
                        if valid_exes:
                            exe_p = valid_exes[0]
                            installed_map[found_rj] = (exe_p, os.path.dirname(exe_p), root)

                # ファイル名にRJコードが含まれるか
                for f in files:
                    fl = f.lower()
                    m_f = rj_regex.search(f)
                    if m_f:
                        found_rj = m_f.group(1).upper()
                        if fl.endswith(".zip") and found_rj not in zip_map:
                            zip_map[found_rj] = os.path.join(root, f)
                        elif fl.endswith(".exe") and not any(x in fl for x in ["crash", "setup", "uninstall", "unitycrash", "update"]):
                            if found_rj not in installed_map:
                                exe_p = os.path.join(root, f)
                                installed_map[found_rj] = (exe_p, root, root)

        return installed_map, zip_map

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
        2. 未登録の購入作品について、事前構築したPC内インデックスから探索（exeまたはzip）。
           - 見つかった場合: is_installed=True でインストール済みとして登録
           - 見つからなかった場合: is_installed=False, dlsite_url付きでダウンロードボタンとして登録
        """
        import zipfile

        if progress_callback:
            progress_callback(0, len(rj_codes), "PC内ストレージを高速インデックス走査中...")

        scan_folders = getattr(config_mgr, "scan_folders", [])
        installed_map, zip_map = cls.build_local_pc_rj_index(scan_folders)

        # HTML付属の_filesフォルダがあれば、ローカル画像パスを事前取得
        local_img_map = {}
        html_files_dir = r"D:\ゲーム\zip\購入履歴 _ DLsite 同人 - R18_files"
        if os.path.exists(html_files_dir):
            for f in os.listdir(html_files_dir):
                m = re.search(r'(RJ\d{6,8}|VJ\d{6,8}|BJ\d{6,8})', f, re.IGNORECASE)
                if m:
                    local_img_map[m.group(1).upper()] = os.path.join(html_files_dir, f)

        existing_games = config_mgr.games
        matched_local_count = 0
        newly_added_count = 0

        total = len(rj_codes)
        for idx, rj in enumerate(rj_codes):
            if progress_callback:
                progress_callback(idx + 1, total, rj)

            # 既存のローカルゲームと照合 (rj_code, dlsite_id, またはパス内に含まれるRJ)
            found_local = False
            for g in existing_games:
                g_rj = (g.get("rj_code") or g.get("dlsite_id") or "").upper()
                if not g_rj:
                    m = re.search(r'(RJ\d{6,8}|VJ\d{6,8}|BJ\d{6,8})', (g.get("path", "") + " " + g.get("folder_path", "")), re.IGNORECASE)
                    if m:
                        g_rj = m.group(1).upper()
                        g["dlsite_id"] = g_rj

                if g_rj == rj:
                    g["platform"] = "DLsite"
                    g["is_purchased"] = True
                    g["rj_code"] = rj
                    g["dlsite_id"] = rj
                    found_local = True
                    matched_local_count += 1
                    
                    # メタデータ補完 & サムネイル差し替え
                    meta = DLsiteMetadataFetcher.fetch_by_rj(rj)
                    if meta:
                        g["dlsite_url"] = meta.get("url") or f"https://www.dlsite.com/maniax/work/=/product_id/{rj}.html"
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
                            g["name"] = clean_game_name(meta["title"])
                        
                        # 公式サムネイル画像に差し替え
                        if not g.get("icon_locked"):
                            # 1. ローカルHTML付属画像があれば最速キャッシュ
                            if rj in local_img_map and os.path.exists(local_img_map[rj]):
                                try:
                                    img = Image.open(local_img_map[rj])
                                    p = icon_helper.cache_image(f"dlsite_{rj}", img)
                                    if p:
                                        g["icon_path"] = p
                                        g["icon_quality"] = QUALITY_DLSITE_OFFICIAL
                                except Exception:
                                    pass
                            elif meta.get("image_url"):
                                img = icon_helper.download_image(meta["image_url"])
                                if img:
                                    p = icon_helper.cache_image(f"dlsite_{rj}", img)
                                    if p:
                                        g["icon_path"] = p
                                        g["icon_quality"] = QUALITY_DLSITE_OFFICIAL
                    break

            if not found_local:
                # 事前インデックスから探索
                found_on_pc = False
                exe_p, work_d, fold_p = "", "", ""

                if rj in installed_map:
                    found_on_pc = True
                    exe_p, work_d, fold_p = installed_map[rj]
                elif rj in zip_map:
                    # zipアーカイブが存在する場合、自動解凍してexeを検出
                    zip_path = zip_map[rj]
                    try:
                        with zipfile.ZipFile(zip_path, 'r') as z:
                            namelist = z.namelist()
                            has_exe = any(
                                n.lower().endswith(".exe") and not any(x in n.lower() for x in ["crash", "setup", "uninstall", "unitycrash", "update"])
                                for n in namelist
                            )
                            if has_exe:
                                extract_dir = os.path.join(os.path.dirname(zip_path), rj.upper())
                                if not os.path.exists(extract_dir):
                                    os.makedirs(extract_dir, exist_ok=True)
                                    for member in z.infolist():
                                        fn = member.filename
                                        try:
                                            fn = fn.encode('cp437').decode('cp932')
                                        except Exception:
                                            try:
                                                fn = fn.encode('cp437').decode('utf-8')
                                            except Exception:
                                                pass
                                        target_path = os.path.join(extract_dir, fn)
                                        if member.is_dir():
                                            os.makedirs(target_path, exist_ok=True)
                                        else:
                                            os.makedirs(os.path.dirname(target_path), exist_ok=True)
                                            with z.open(member) as source, open(target_path, "wb") as target:
                                                target.write(source.read())

                                # 解凍先からexeを検出
                                for eroot, edirs, efiles in os.walk(extract_dir):
                                    for ef in efiles:
                                        efl = ef.lower()
                                        if efl.endswith(".exe") and not any(x in efl for x in ["crash", "setup", "uninstall", "unitycrash", "update"]):
                                            exe_p = os.path.join(eroot, ef)
                                            work_d = os.path.dirname(exe_p)
                                            fold_p = extract_dir
                                            found_on_pc = True
                                            break
                                    if found_on_pc:
                                        break
                    except Exception:
                        pass

                meta = DLsiteMetadataFetcher.fetch_by_rj(rj)
                title = clean_game_name(meta["title"]) if meta else rj
                maker = meta["maker"] if meta else "不明"
                genre = meta["genre"] if meta else "その他"
                tags = meta["tags"] if meta else []
                dlsite_url = meta["url"] if meta else f"https://www.dlsite.com/maniax/download/=/product_id/{rj}.html"

                icon_path = ""
                if rj in local_img_map and os.path.exists(local_img_map[rj]):
                    try:
                        from PIL import Image
                        img = Image.open(local_img_map[rj])
                        p = icon_helper.cache_image(f"dlsite_{rj}", img)
                        if p:
                            icon_path = p
                    except Exception:
                        pass
                if not icon_path and meta and meta.get("image_url"):
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
                    "dlsite_id": rj,
                    "dlsite_url": dlsite_url,
                    "path": exe_p if found_on_pc else "",
                    "work_dir": work_d if found_on_pc else "",
                    "folder_path": fold_p if found_on_pc else "",
                    "is_purchased": True,
                    "is_installed": found_on_pc,
                    "icon_path": icon_path,
                    "icon_quality": QUALITY_DLSITE_OFFICIAL if icon_path else 0
                }
                config_mgr.add_or_update_game(new_game)
                newly_added_count += 1

        config_mgr.save()
        return matched_local_count, newly_added_count
