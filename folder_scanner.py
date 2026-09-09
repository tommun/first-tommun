import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

# 除外する実行ファイル名のパターン
EXCLUDE_EXE_PATTERNS = [
    r"^unitycrashhandler.*\.exe$",
    r"^crashreport.*\.exe$",
    r"^unins\d*\.exe$",
    r"^uninstall.*\.exe$",
    r"^dxwebsetup\.exe$",
    r"^vcredist.*\.exe$",
    r"^setup.*\.exe$",
    r"^update.*\.exe$",
    r"^updater.*\.exe$",
    r"^install.*\.exe$",
    r"^.*installer.*\.exe$",
    r"^vlc.*\.exe$",
    r"^chrome.*\.exe$",
    r"^7z.*\.exe$",
    r"^winrar.*\.exe$",
    r"^ffmpeg\.exe$",
    r"^ffprobe\.exe$",
    r"^nwjc\.exe$",
    r"^chromedriver\.exe$",
    r"^notification_helper\.exe$",
    r"^ueprereqsetup.*\.exe$",
    r"^.*\.part\d+\.exe$",   # 分割rar/7z自己解凍書庫
    r"^.*\.sfx\.exe$",
]

# イラスト画像として除外する単語（マニュアル、チャート、移行方法など）
IGNORE_IMG_KEYWORDS = [
    "manual", "howtoplay", "chart", "フローチャート", "チャート",
    "移行", "howto", "guide", "ガイド", "説明", "注意", "error", "log"
]

def clean_game_title(name: str) -> str:
    """フォルダ名やexe名から余分な記号や拡張子を整理して綺麗なタイトルにする"""
    title = name.strip()
    title = re.sub(r'\.(exe|zip|rar|7z)$', '', title, flags=re.IGNORECASE)
    # フォルダ名が RJ01014404 などの場合はそのまま返す
    return title.strip()

def extract_rj_code(text: str) -> Optional[str]:
    """テキストからRJ番号/VJ番号（例: RJ01014404）を抽出"""
    m = re.search(r'\b(RJ|VJ)\d{6,8}\b', text, re.IGNORECASE)
    if m:
        return m.group(0).upper()
    return None

def extract_author_from_path(path_str: str, root_lib: str = "") -> str:
    """パスやフォルダ階層からサークル名・作者名を推定抽出"""
    p = Path(path_str)
    parts = list(p.parts)

    # 1. [サークル名] や 【サークル名】 の抽出
    for part in parts:
        m = re.search(r'[\[【]([^\]】]+)[\]】]', part)
        if m:
            cand = m.group(1).strip()
            # RJ/VJ番号やバージョン表記、汎用単語は除外
            if (not re.match(r'^(RJ|VJ)\d+', cand, re.I) and 
                not re.match(r'^\d+(\.\d+)*', cand) and 
                cand not in ['製品版', '体験版', 'DL版', 'WIN', 'PC', 'Ver1.1', '1.2.0', 'オフライン版']):
                return cand

    # 2. 相対パス階層のチェック
    try:
        rel_parts = list(p.relative_to(root_lib).parts) if root_lib else parts
    except Exception:
        rel_parts = parts

    # 著名・代表的なサークル名パターンの優先認識
    known_authors = ['ONEONE1', 'Remtairy', '当方丸宝堂', '粗製', 'モンスター研', 'BanameiR', 'まじかみ']
    for part in rel_parts:
        for ka in known_authors:
            if ka.lower() in part.lower():
                return ka
        if 'moralist' in part.lower():
            return "I'm moralist"

    # 3. ライブラリ直下の第1階層フォルダ名が作品特有フォルダの場合
    generic_folders = ['zip', 'ほんぺん', 'のーとにはいってたやつとりあえず', 'download', 'game', 'bin', 'win64']
    if len(rel_parts) >= 2:
        top = rel_parts[0]
        if (not re.match(r'^(RJ|VJ)\d+', top, re.I) and 
            top.lower() not in generic_folders and 
            not top.lower().endswith('.exe')):
            return top

    return "不明"

class FolderScanner:
    """指定されたフォルダ配下の全ゲームを網羅的に再帰スキャン・検出するクラス"""

    @staticmethod
    def is_excluded_exe(filename: str) -> bool:
        lower = filename.lower()
        for pat in EXCLUDE_EXE_PATTERNS:
            if re.match(pat, lower):
                return True
        return False

    @staticmethod
    def find_local_illustration(folder_path: str, root_library_dir: str) -> Optional[str]:
        """
        ゲームフォルダ内からすでに存在するイラスト・ジャケット画像（元の画像）を探す。
        ライブラリ直下の画像やマニュアル画像は除外。
        """
        folder = Path(folder_path)
        root_lib = Path(root_library_dir).resolve()
        if not folder.exists() or folder.resolve() == root_lib:
            return None

        candidates = []
        # ゲームフォルダ直下およびサブフォルダ（イラスト/等）を探索
        for ext in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
            for p in folder.glob(ext):
                candidates.append(p)
            for p in folder.glob(f"イラスト/{ext}"):
                candidates.append(p)
            for p in folder.glob(f"*/{ext}"):
                candidates.append(p)

        best_img = None
        best_score = 0

        for p in candidates:
            # ライブラリ直下のファイルは除外
            if p.parent.resolve() == root_lib:
                continue

            stem = p.stem.lower()
            # マニュアルや移行方法画像は除外
            if any(ign in stem for ign in IGNORE_IMG_KEYWORDS):
                continue
            # 小さすぎるicon.png等は除外
            try:
                size = p.stat().st_size
            except Exception:
                size = 0

            if "icon" in stem and size < 20000:
                continue

            score = 0
            if "ジャケット" in stem or "jacket" in stem:
                score += 100
            elif "イラスト" in stem or "illustration" in stem:
                score += 85
            elif "cover" in stem or "パッケージ" in stem:
                score += 75
            elif "main" in stem or "thumb" in stem:
                score += 65
            elif "title" in stem or "banner" in stem:
                score += 55
            elif p.parent == folder:
                # フォルダ直下に置かれた画像
                if size > 100000: # 100KB以上
                    score += 45
                elif size > 30000: # 30KB以上
                    score += 30

            if score > best_score:
                best_score = score
                best_img = p

        return str(best_img.resolve()) if best_img and best_score >= 30 else None

    @classmethod
    def scan_library_folder(cls, root_folder: str, default_category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        ライブラリフォルダ（例: D:\\ゲーム, D:\\download）配下を全探索し、
        zipと重複している場合は解凍済みの実体を優先して全ゲームを検出。
        """
        root_path = Path(root_folder).resolve()
        if not root_path.exists() or not root_path.is_dir():
            return []

        if not default_category:
            default_category = root_path.name

        results = []
        games_by_folder = {}

        # 全探索
        for current_dir, dirs, files in os.walk(str(root_path)):
            cur_p = Path(current_dir)

            # exeファイルを探す
            exe_files = [f for f in files if f.lower().endswith(".exe") and not cls.is_excluded_exe(f)]
            if not exe_files:
                continue

            # 最もゲーム本体と思われるexeを1つ決定
            best_exe = None
            best_score = -999
            folder_clean = cur_p.name.lower().replace(" ", "").replace("_", "").replace("-", "")

            for f in exe_files:
                full_exe = cur_p / f
                try:
                    size = full_exe.stat().st_size
                except Exception:
                    size = 0

                score = 0
                base_clean = f[:-4].lower().replace(" ", "").replace("_", "").replace("-", "")

                if base_clean in folder_clean or folder_clean in base_clean:
                    score += 50
                if (cur_p / f"{f[:-4]}_Data").exists():
                    score += 60 # Unity
                if f.lower() in ["game.exe", "start.exe", "起動.exe", "main.exe", "play.exe"]:
                    score += 45
                if size > 10 * 1024 * 1024:
                    score += 30
                elif size > 2 * 1024 * 1024:
                    score += 15
                elif size < 100 * 1024:
                    score -= 20

                if score > best_score:
                    best_score = score
                    best_exe = full_exe

            if best_exe:
                # ゲーム表示名の決定
                game_name = cur_p.name
                # システム系フォルダ名（Game, bin, win64, Windows等）なら親フォルダ名を採用
                if game_name.lower() in ["game", "bin", "win64", "binaries", "release", "shipping", "x64", "windows"]:
                    game_name = cur_p.parent.name
                if game_name.lower() in ["pc", "game", "win"]:
                    game_name = cur_p.parent.parent.name

                # 作品全体の親フォルダからRJ番号を抽出
                full_path_str = str(best_exe)
                rj_code = extract_rj_code(full_path_str)

                # ローカルの元画像（イラスト）を探索
                local_img = cls.find_local_illustration(str(cur_p), str(root_path))
                if not local_img and cur_p.parent.resolve() != root_path:
                    local_img = cls.find_local_illustration(str(cur_p.parent), str(root_path))

                # サークル名・作者名の推定
                author = extract_author_from_path(full_path_str, str(root_path))

                norm_exe_path = os.path.normpath(str(best_exe))
                games_by_folder[norm_exe_path] = {
                    "name": clean_game_title(game_name),
                    "author": author,
                    "path": norm_exe_path,
                    "work_dir": os.path.normpath(str(cur_p)),
                    "folder_path": os.path.normpath(str(cur_p)),
                    "category": default_category,
                    "rj_code": rj_code,
                    "local_illustration": local_img,
                    "root_library": str(root_path),
                    "icon_locked": False
                }

        return list(games_by_folder.values())
