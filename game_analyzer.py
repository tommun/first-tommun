import os
import re
import json
import base64
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

def normalize_title(name: str) -> str:
    """バージョン表記や記号、拡張子を除去してベースとなるゲームタイトルを生成"""
    s = name.strip()
    # 拡張子除去
    s = re.sub(r'\.(exe|zip|rar|7z)$', '', s, flags=re.IGNORECASE)
    # RJ番号/VJ番号を除去
    s = re.sub(r'\b(RJ|VJ)\d{6,8}\b', '', s, flags=re.IGNORECASE)
    # バージョン表記の除去 (v1.2.3, ver.2.0, _0.132.0, V2.35, - Public, etc.)
    s = re.sub(r'[-_ ]*(v|ver|version)?[._ ]*\d+(\.\d+)+([a-zA-Z0-9_-]*)?', '', s, flags=re.IGNORECASE)
    s = re.sub(r'[-_ ]*public', '', s, flags=re.IGNORECASE)
    # 記号をスペースに変換
    s = re.sub(r'[-_.]+', ' ', s)
    # 余分な空白を削除し小文字化
    s = re.sub(r'\s+', ' ', s).strip().lower()
    return s

def extract_version_str(text: str) -> Optional[str]:
    """文字列からバージョン番号（例: v1.12, 0.132.0, 2.35）を抽出"""
    m = re.search(r'\b(?:v|ver|version)?[._ ]*(\d+(?:\.\d+)+(?:[a-zA-Z0-9_-]*)?)\b', text, re.IGNORECASE)
    if m:
        return m.group(1)
    # V2.35 のような大文字V直結パターン
    m2 = re.search(r'[vV](\d+(?:\.\d+)+)', text)
    if m2:
        return m2.group(1)
    return None

class GameAnalyzer:
    """同一ゲームの検出、バージョンの差異比較、セーブデータ進行度解析を担当するクラス"""

    @classmethod
    def get_game_internal_id(cls, folder_path: str, exe_path: str, is_standalone: bool = False) -> Dict[str, Any]:
        """Unity app.info, ツクール package.json, GameMaker options.ini 等から内部情報を取得"""
        info = {
            "unity_company": None,
            "unity_product": None,
            "rpgmaker_title": None,
            "gamemaker_title": None,
            "rj_code": None
        }

        # RJ番号
        m = re.search(r'\b(RJ|VJ)\d{6,8}\b', folder_path + " " + exe_path, re.IGNORECASE)
        if m:
            info["rj_code"] = m.group(0).upper()

        if is_standalone:
            return info

        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            return info

        # 1. Unity app.info (直属の *_Data フォルダまたは直下)
        exe_stem = Path(exe_path).stem
        target_data_dir = folder / f"{exe_stem}_Data"
        search_dirs = [target_data_dir] if target_data_dir.exists() else [folder]

        for sdir in search_dirs:
            for app_info_file in sdir.glob("**/app.info"):
                try:
                    with open(app_info_file, "r", encoding="utf-8", errors="ignore") as f:
                        lines = [line.strip() for line in f if line.strip()]
                        if len(lines) >= 2:
                            info["unity_company"] = lines[0]
                            info["unity_product"] = lines[1]
                            break
                except Exception:
                    pass
            if info["unity_company"]:
                break

        # 2. RPGツクール package.json
        for pkg_file in folder.glob("package.json"):
            try:
                with open(pkg_file, "r", encoding="utf-8", errors="ignore") as f:
                    data = json.load(f)
                    if "name" in data or "description" in data:
                        info["rpgmaker_title"] = data.get("description") or data.get("name")
                        break
            except Exception:
                pass

        # 3. GameMaker options.ini
        for opt_file in folder.glob("options.ini"):
            try:
                with open(opt_file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    m_title = re.search(r'DisplayName="?([^"\r\n]+)"?', content)
                    if m_title:
                        info["gamemaker_title"] = m_title.group(1)
                        break
            except Exception:
                pass

        return info

    @classmethod
    def group_identical_games(cls, games: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """登録ゲーム一覧から、同一ゲーム（バージョン違いや重複コピー）をグループ化して返す"""
        groups: Dict[str, List[Dict[str, Any]]] = {}

        for game in games:
            name = game.get("name", "")
            folder_path = game.get("folder_path", os.path.dirname(game.get("path", "")))
            exe_path = game.get("path", "")
            is_standalone = game.get("is_standalone", False)

            internal = cls.get_game_internal_id(folder_path, exe_path, is_standalone=is_standalone)

            # グループキーの決定優先度:
            # 1. RJコード
            # 2. Unity (Company + Product)
            # 3. RPGMaker / GameMaker タイトル
            # 4. 正規化タイトル名
            group_key = None
            if internal.get("rj_code"):
                group_key = f"RJ:{internal['rj_code']}"
            elif internal.get("unity_product"):
                group_key = f"UNITY:{internal['unity_company']}_{internal['unity_product']}"
            elif internal.get("rpgmaker_title"):
                group_key = f"RPGM:{normalize_title(internal['rpgmaker_title'])}"
            elif internal.get("gamemaker_title"):
                group_key = f"GM:{normalize_title(internal['gamemaker_title'])}"
            else:
                norm = normalize_title(name)
                if not norm:
                    norm = normalize_title(os.path.basename(exe_path))
                group_key = f"TITLE:{norm}"

            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(game)

        return groups

    @classmethod
    def analyze_save_progress(cls, folder_path: str, exe_path: str, is_standalone: bool = False) -> Dict[str, Any]:
        """
        指定されたゲームフォルダ配下のセーブデータを探索し、プレイ進行度・最終セーブ日時を解析。
        """
        res = {
            "has_save": False,
            "save_count": 0,
            "latest_save_time": None,
            "latest_save_str": "セーブデータなし (未プレイ)",
            "save_files": [],
            "save_dir": None,
            "details": ""
        }

        if is_standalone:
            # 単体exeの場合は同名の.sav等のみ探索
            exe_p = Path(exe_path)
            cand_save = exe_p.with_suffix(".sav")
            if cand_save.exists():
                res["has_save"] = True
                res["save_count"] = 1
                res["save_files"] = [str(cand_save)]
                mtime = cand_save.stat().st_mtime
                res["latest_save_time"] = mtime
                dt = datetime.fromtimestamp(mtime)
                res["latest_save_str"] = f"プレイ進行中 ({dt.strftime('%Y/%m/%d %H:%M')})"
            return res

        folder = Path(folder_path)
        if not folder.exists():
            return res

        save_files = []
        save_patterns = [
            "**/*.rpgsave",    # RPGツクール MV/MZ
            "**/*.rvdata2",    # RPGツクール VX Ace
            "**/*.rxdata",     # RPGツクール XP
            "**/Save*.dat",    # WOLF RPGエディタ
            "**/save/*.dat",
            "**/savedata/*",
            "**/Save/*",
            "**/save/*",
            "**/*save*.bin",
            "**/*Save*.sav",
        ]

        for pat in save_patterns:
            for p in folder.glob(pat):
                if p.is_file() and not p.name.startswith("config") and not p.name.startswith("global"):
                    save_files.append(p)

        # 重複削除
        unique_save_files = list({str(p.resolve()): p for p in save_files}.values())

        # Unity等でローカルAppDataに保存されるケースの探索
        internal = cls.get_game_internal_id(folder_path, exe_path)
        if not unique_save_files and internal.get("unity_company") and internal.get("unity_product"):
            appdata_low = Path(os.environ.get("USERPROFILE", "")) / "AppData" / "LocalLow" / internal["unity_company"] / internal["unity_product"]
            if appdata_low.exists():
                for p in appdata_low.glob("**/*"):
                    if p.is_file() and not p.name.endswith(".log") and not p.name.endswith(".txt"):
                        unique_save_files.append(p)
                        res["details"] = f"AppData/LocalLow 内で検出"

        if not unique_save_files:
            return res

        res["has_save"] = True
        res["save_count"] = len(unique_save_files)
        res["save_files"] = [str(p) for p in unique_save_files]
        if unique_save_files:
            res["save_dir"] = str(unique_save_files[0].parent)

        # 最新のセーブ日時を特定
        latest_time = 0
        latest_file = None
        for p in unique_save_files:
            try:
                mtime = p.stat().st_mtime
                if mtime > latest_time:
                    latest_time = mtime
                    latest_file = p
            except Exception:
                pass

        if latest_time > 0:
            dt = datetime.fromtimestamp(latest_time)
            res["latest_save_time"] = latest_time
            res["latest_save_str"] = f"プレイ進行中 ({dt.strftime('%Y/%m/%d %H:%M')})"
            
            # RPGツクールMV/MZのセーブなら中身を簡易解析
            if latest_file and latest_file.suffix.lower() == ".rpgsave":
                try:
                    with open(latest_file, "r", encoding="utf-8", errors="ignore") as sf:
                        content = sf.read().strip()
                        # LZString圧縮解除または素のJSON
                        if content.startswith("{") and content.endswith("}"):
                            sdata = json.loads(content)
                            playtime = sdata.get("system", {}).get("playtime")
                            if playtime:
                                hrs = int(playtime) // 3600
                                mins = (int(playtime) % 3600) // 60
                                res["details"] = f"プレイ時間: {hrs}時間{mins}分"
                except Exception:
                    pass

        return res

    @classmethod
    def compare_game_versions(cls, game_a: Dict[str, Any], game_b: Dict[str, Any]) -> Dict[str, Any]:
        """2つのゲームインスタンスの差異（バージョン、更新日時、サイズ、セーブ進行度）を詳細比較"""
        folder_a = game_a.get("folder_path", os.path.dirname(game_a.get("path", "")))
        folder_b = game_b.get("folder_path", os.path.dirname(game_b.get("path", "")))
        exe_a = game_a.get("path", "")
        exe_b = game_b.get("path", "")

        stat_a = os.stat(exe_a) if os.path.exists(exe_a) else None
        stat_b = os.stat(exe_b) if os.path.exists(exe_b) else None

        time_a = stat_a.st_mtime if stat_a else 0
        time_b = stat_b.st_mtime if stat_b else 0
        size_a = stat_a.st_size if stat_a else 0
        size_b = stat_b.st_size if stat_b else 0

        ver_a = extract_version_str(game_a.get("name", "")) or extract_version_str(folder_a) or "不明"
        ver_b = extract_version_str(game_b.get("name", "")) or extract_version_str(folder_b) or "不明"

        # どちらが新しいか（タイムスタンプとバージョン文字列の総合判定）
        newer = "A" if time_a >= time_b else "B"

        # セーブ進行度解析
        save_a = cls.analyze_save_progress(folder_a, exe_a)
        save_b = cls.analyze_save_progress(folder_b, exe_b)

        return {
            "game_a": {
                "name": game_a.get("name"),
                "path": exe_a,
                "folder": folder_a,
                "version": ver_a,
                "mtime": datetime.fromtimestamp(time_a).strftime("%Y/%m/%d %H:%M") if time_a else "-",
                "size_mb": round(size_a / (1024 * 1024), 2),
                "save": save_a
            },
            "game_b": {
                "name": game_b.get("name"),
                "path": exe_b,
                "folder": folder_b,
                "version": ver_b,
                "mtime": datetime.fromtimestamp(time_b).strftime("%Y/%m/%d %H:%M") if time_b else "-",
                "size_mb": round(size_b / (1024 * 1024), 2),
                "save": save_b
            },
            "newer_version": newer,
            "can_migrate_save": (save_a["has_save"] and not save_b["has_save"]) or (save_b["has_save"] and not save_a["has_save"]) or (save_a["latest_save_time"] != save_b["latest_save_time"])
        }

    @classmethod
    def migrate_saves(cls, src_folder: str, dst_folder: str) -> Tuple[bool, str]:
        """古いバージョンのセーブデータフォルダを新しいバージョンのゲームフォルダにバックアップコピー"""
        src_path = Path(src_folder)
        dst_path = Path(dst_folder)

        if not src_path.exists() or not dst_path.exists():
            return False, "フォルダが見つかりません"

        # 代表的なセーブフォルダ候補
        copied_any = False
        candidates = ["save", "Save", "savedata", "SaveData", "www/save"]

        for cand in candidates:
            src_save = src_path / cand
            if src_save.exists() and src_save.is_dir():
                dst_save = dst_path / cand
                try:
                    dst_save.parent.mkdir(parents=True, exist_ok=True)
                    # 既存の移行先セーブがあればバックアップ
                    if dst_save.exists():
                        backup_dir = dst_path / f"{cand}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                        shutil.copytree(dst_save, backup_dir)
                        shutil.rmtree(dst_save)
                    shutil.copytree(src_save, dst_save)
                    copied_any = True
                except Exception as e:
                    return False, f"コピー中にエラーが発生しました: {e}"

        # 直下に *.rpgsave や Save*.dat がある場合
        for f in src_path.glob("Save*.dat"):
            try:
                shutil.copy2(f, dst_path / f.name)
                copied_any = True
            except Exception:
                pass

        for f in src_path.glob("*.rpgsave"):
            try:
                shutil.copy2(f, dst_path / f.name)
                copied_any = True
            except Exception:
                pass

        if copied_any:
            return True, "セーブデータの移行が正常に完了しました！"
        else:
            return False, "移行対象のセーブデータが見つかりませんでした。"
