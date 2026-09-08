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
]

def clean_game_title(folder_name: str) -> str:
    """フォルダ名から余分な記号や拡張子を整理して綺麗なタイトルにする"""
    title = folder_name
    # zipなどの拡張子除去
    title = re.sub(r'\.(zip|rar|7z)$', '', title, flags=re.IGNORECASE)
    # 先頭・末尾のスペース
    return title.strip()

def extract_rj_code(text: str) -> Optional[str]:
    """テキストからRJ番号/VJ番号（例: RJ01014404）を抽出"""
    m = re.search(r'\b(RJ|VJ)\d{6,8}\b', text, re.IGNORECASE)
    if m:
        return m.group(0).upper()
    return None

class FolderScanner:
    """指定されたフォルダ配下のゲームをスマートにスキャン・検出するクラス"""

    @staticmethod
    def is_excluded_exe(filename: str) -> bool:
        lower = filename.lower()
        for pat in EXCLUDE_EXE_PATTERNS:
            if re.match(pat, lower):
                return True
        return False

    @classmethod
    def find_main_exe_in_folder(cls, folder_path: str, max_depth: int = 3) -> Optional[str]:
        """フォルダ配下からもっともゲーム本体と思われるexeを特定"""
        root_path = Path(folder_path)
        if not root_path.exists() or not root_path.is_dir():
            return None

        candidates = []
        folder_name_clean = root_path.name.lower().replace(" ", "").replace("_", "").replace("-", "")

        for current_dir, dirs, files in os.walk(folder_path):
            rel_depth = len(Path(current_dir).relative_to(root_path).parts)
            if rel_depth > max_depth:
                dirs.clear()
                continue

            for f in files:
                if f.lower().endswith(".exe") and not cls.is_excluded_exe(f):
                    full_path = os.path.join(current_dir, f)
                    try:
                        size = os.path.getsize(full_path)
                    except Exception:
                        size = 0

                    score = 0
                    base_name = f[:-4].lower()
                    base_clean = base_name.replace(" ", "").replace("_", "").replace("-", "")

                    # 1. フォルダ名とexe名の一致
                    if base_clean in folder_name_clean or folder_name_clean in base_clean:
                        score += 50

                    # 2. Unityデータフォルダ（{name}_Data）が存在するか
                    data_dir = os.path.join(current_dir, f"{f[:-4]}_Data")
                    if os.path.exists(data_dir):
                        score += 60

                    # 3. 一般的なゲーム起動名
                    if base_name in ["game", "start", "起動", "main", "play"]:
                        score += 40

                    # 4. 階層の浅さ（浅いほど優先）
                    score -= (rel_depth * 10)

                    # 5. ファイルサイズ（ある程度大きい方が本体の可能性大）
                    if size > 10 * 1024 * 1024:  # 10MB以上
                        score += 30
                    elif size > 2 * 1024 * 1024: # 2MB以上
                        score += 15
                    elif size < 200 * 1024:       # 200KB未満は小さすぎる可能性
                        score -= 10

                    candidates.append({
                        "path": full_path,
                        "name": f,
                        "score": score,
                        "size": size,
                        "depth": rel_depth
                    })

        if not candidates:
            return None

        # スコア最大のものを選択
        candidates.sort(key=lambda x: (x["score"], x["size"]), reverse=True)
        return candidates[0]["path"]

    @classmethod
    def scan_library_folder(cls, root_folder: str, default_category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        ライブラリフォルダ（例: D:\\ゲーム や D:\\download）直下の各ゲームをスキャン。
        """
        root_path = Path(root_folder)
        if not root_path.exists() or not root_path.is_dir():
            return []

        if not default_category:
            default_category = root_path.name  # "ゲーム" または "download"

        results = []

        try:
            entries = list(root_path.iterdir())
        except Exception as e:
            print(f"[FolderScanner] フォルダ走査エラー ({root_folder}): {e}")
            return []

        for entry in entries:
            # フォルダ直下のディレクトリをゲーム単位として処理
            if entry.is_dir():
                main_exe = cls.find_main_exe_in_folder(str(entry))
                if main_exe:
                    folder_name = entry.name
                    rj_code = extract_rj_code(folder_name) or extract_rj_code(main_exe)
                    clean_name = clean_game_title(folder_name)

                    results.append({
                        "name": clean_name,
                        "path": os.path.normpath(main_exe),
                        "work_dir": os.path.normpath(os.path.dirname(main_exe)),
                        "folder_path": os.path.normpath(str(entry)),
                        "category": default_category,
                        "rj_code": rj_code,
                        "root_library": str(root_path)
                    })
            elif entry.is_file() and entry.suffix.lower() == ".exe" and not cls.is_excluded_exe(entry.name):
                # 直下にexeがある場合（単体exe）
                results.append({
                    "name": clean_game_title(entry.stem),
                    "path": os.path.normpath(str(entry)),
                    "work_dir": os.path.normpath(str(root_path)),
                    "folder_path": os.path.normpath(str(entry.parent)),
                    "category": default_category,
                    "rj_code": extract_rj_code(entry.name),
                    "root_library": str(root_path),
                    "is_standalone": True
                })

        return results
