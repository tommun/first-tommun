import os
import glob
from datetime import datetime
from typing import Dict, Any, List, Optional

class SaveScriptDetector:
    """ゲームフォルダ内のセーブデータおよびスクリプト/MODファイルを自動検出・解析"""

    @classmethod
    def detect_saves(cls, game_path: str, folder_path: str = "") -> Dict[str, Any]:
        """
        セーブデータを検出してスロット数、最新セーブ日時、セーブディレクトリを返す
        """
        base_dir = folder_path or (os.path.dirname(game_path) if game_path else "")
        if not base_dir or not os.path.exists(base_dir):
            return {
                "count": 0,
                "latest_date": None,
                "save_dir": None,
                "files": []
            }

        save_patterns = [
            # RPG Maker MV/MZ
            os.path.join(base_dir, "save", "*.rpgsave"),
            os.path.join(base_dir, "www", "save", "*.rpgsave"),
            # RPG Maker VX/Ace/XP
            os.path.join(base_dir, "Save*.rvdata2"),
            os.path.join(base_dir, "Save*.rvdata"),
            os.path.join(base_dir, "Save*.rxdata"),
            # RPG Maker 2000/2003
            os.path.join(base_dir, "Save*.lsd"),
            # WOLF RPG
            os.path.join(base_dir, "Save", "Save*.dat"),
            os.path.join(base_dir, "Save*.dat"),
            # 一般 / Unity
            os.path.join(base_dir, "savedata", "*"),
            os.path.join(base_dir, "save", "*"),
            os.path.join(base_dir, "*.sav"),
            os.path.join(base_dir, "*.save"),
        ]

        found_files = []
        for pat in save_patterns:
            for f in glob.glob(pat):
                if os.path.isfile(f) and not f.endswith(".exe") and not f.endswith(".dll"):
                    if f not in found_files:
                        found_files.append(f)

        if not found_files:
            return {
                "count": 0,
                "latest_date": None,
                "save_dir": base_dir,
                "files": []
            }

        # 最新更新日時を探索
        latest_mtime = 0
        latest_file = None
        for f in found_files:
            try:
                mtime = os.path.getmtime(f)
                if mtime > latest_mtime:
                    latest_mtime = mtime
                    latest_file = f
            except Exception:
                pass

        latest_str = ""
        if latest_mtime > 0:
            latest_str = datetime.fromtimestamp(latest_mtime).strftime("%Y/%m/%d %H:%M")

        save_dir = os.path.dirname(found_files[0]) if found_files else base_dir

        return {
            "count": len(found_files),
            "latest_date": latest_str,
            "save_dir": save_dir,
            "files": found_files
        }

    @classmethod
    def detect_scripts_and_engine(cls, game_path: str, folder_path: str = "") -> Dict[str, Any]:
        """
        ゲームエンジンおよびスクリプト/データディレクトリを検出
        """
        base_dir = folder_path or (os.path.dirname(game_path) if game_path else "")
        if not base_dir or not os.path.exists(base_dir):
            return {
                "engine": "Unknown",
                "script_dir": None,
                "can_edit": False,
                "description": "フォルダが見つかりません"
            }

        # 1. RPG Maker MV / MZ
        mv_mz_js = os.path.join(base_dir, "www", "js") if os.path.exists(os.path.join(base_dir, "www", "js")) else os.path.join(base_dir, "js")
        mv_mz_data = os.path.join(base_dir, "www", "data") if os.path.exists(os.path.join(base_dir, "www", "data")) else os.path.join(base_dir, "data")
        if os.path.exists(mv_mz_js) or os.path.exists(mv_mz_data):
            engine = "RPGツクール MV/MZ"
            target_dir = mv_mz_js if os.path.exists(mv_mz_js) else mv_mz_data
            return {
                "engine": engine,
                "script_dir": target_dir,
                "can_edit": True,
                "description": "JavaScript プラグイン / JSON データ"
            }

        # 2. RPG Maker VX Ace / VX / XP
        data_dir = os.path.join(base_dir, "Data")
        if os.path.exists(data_dir):
            if any(os.path.exists(os.path.join(data_dir, f)) for f in ["Scripts.rvdata2", "System.rvdata2"]):
                return {
                    "engine": "RPGツクール VX Ace",
                    "script_dir": data_dir,
                    "can_edit": True,
                    "description": "Ruby (RGSS3) スクリプトデータ"
                }
            elif any(os.path.exists(os.path.join(data_dir, f)) for f in ["Scripts.rxdata"]):
                return {
                    "engine": "RPGツクール XP",
                    "script_dir": data_dir,
                    "can_edit": True,
                    "description": "Ruby (RGSS) スクリプトデータ"
                }

        # 3. WOLF RPG エディタ
        wolf_data = os.path.join(base_dir, "Data")
        wolf_ini = os.path.join(base_dir, "WolfRPG.ini")
        if os.path.exists(wolf_ini) or (os.path.exists(wolf_data) and os.path.exists(os.path.join(wolf_data, "BasicData"))):
            return {
                "engine": "WOLF RPGエディター",
                "script_dir": wolf_data if os.path.exists(wolf_data) else base_dir,
                "can_edit": True,
                "description": "WOLF コマンドデータ"
            }

        # 4. Unity
        try:
            for item in os.listdir(base_dir):
                if item.endswith("_Data") and os.path.isdir(os.path.join(base_dir, item)):
                    managed_dir = os.path.join(base_dir, item, "Managed")
                    if os.path.exists(managed_dir):
                        return {
                            "engine": "Unity",
                            "script_dir": managed_dir,
                            "can_edit": True,
                            "description": "C# Managed アセンブリ / MOD"
                        }
        except Exception:
            pass

        # 5. 吉里吉里 (KAG / TVP)
        try:
            for item in os.listdir(base_dir):
                if item.endswith(".xp3"):
                    return {
                        "engine": "吉里吉里 / KAG",
                        "script_dir": base_dir,
                        "can_edit": True,
                        "description": "TJS2 / KAG スクリプト"
                    }
        except Exception:
            pass

        return {
            "engine": "ネイティブ / その他",
            "script_dir": base_dir,
            "can_edit": True,
            "description": "ゲームルートディレクトリ"
        }
