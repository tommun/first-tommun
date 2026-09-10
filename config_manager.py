import json
import os
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional

DEFAULT_CONFIG_FILE = "launcher_config.json"

class ConfigManager:
    """設定およびゲーム一覧の読み書き・永続化を管理するクラス"""

    def __init__(self, config_path: str = DEFAULT_CONFIG_FILE):
        self.config_path = Path(config_path).resolve()
        self.config: Dict[str, Any] = self._get_default_config()
        self.load()

    def _get_default_config(self) -> Dict[str, Any]:
        default_scan = []
        for path in ["D:\\ゲーム", "D:\\download"]:
            if os.path.exists(path):
                default_scan.append(path)
        if not default_scan:
            default_scan = ["D:\\ゲーム", "D:\\download"]

        return {
            "version": "1.0",
            "theme": "Dark",
            "scan_folders": default_scan,
            "categories": ["すべて", "ゲーム", "download", "お気に入り"],
            "games": [],
            "settings": {
                "auto_search_web_icon": True,
                "window_width": 1100,
                "window_height": 720
            }
        }

    def load(self):
        """設定ファイルからロード"""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # デフォルトキーをマージ
                    default = self._get_default_config()
                    for k, v in default.items():
                        if k not in data:
                            data[k] = v
                    self.config = data
            except Exception as e:
                print(f"[ConfigManager] ロード失敗、デフォルトを使用: {e}")
                self.config = self._get_default_config()
        else:
            self.save()

    def save(self):
        """設定ファイルへ保存"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ConfigManager] 保存失敗: {e}")

    # --- スキャンフォルダ管理 ---
    @property
    def scan_folders(self) -> List[str]:
        return self.config.get("scan_folders", [])

    def add_scan_folder(self, folder_path: str) -> bool:
        norm = os.path.normpath(folder_path)
        folders = [os.path.normpath(p) for p in self.scan_folders]
        if norm not in folders:
            self.config["scan_folders"].append(folder_path)
            self.save()
            return True
        return False

    def remove_scan_folder(self, folder_path: str):
        norm = os.path.normpath(folder_path)
        self.config["scan_folders"] = [p for p in self.scan_folders if os.path.normpath(p) != norm]
        self.save()

    # --- カテゴリ管理 ---
    @property
    def categories(self) -> List[str]:
        cats = self.config.get("categories", ["すべて"])
        if "すべて" not in cats:
            cats.insert(0, "すべて")
        return cats

    def add_category(self, name: str) -> bool:
        name = name.strip()
        if name and name not in self.categories:
            self.config["categories"].append(name)
            self.save()
            return True
        return False

    def remove_category(self, name: str):
        if name != "すべて" and name in self.config["categories"]:
            self.config["categories"].remove(name)
            # 該当カテゴリのゲームを「未分類」または「すべて」に戻す
            for game in self.games:
                if game.get("category") == name:
                    game["category"] = "すべて"
            self.save()

    # --- ゲーム管理 ---
    @property
    def games(self) -> List[Dict[str, Any]]:
        return self.config.get("games", [])

    def get_game_by_id(self, game_id: str) -> Optional[Dict[str, Any]]:
        for g in self.games:
            if g.get("id") == game_id:
                return g
        return None

    def get_game_by_path(self, exe_path: str) -> Optional[Dict[str, Any]]:
        if not exe_path or not exe_path.strip():
            return None
        norm = os.path.normcase(os.path.normpath(exe_path))
        for g in self.games:
            g_path = g.get("path", "")
            if g_path and os.path.normcase(os.path.normpath(g_path)) == norm:
                return g
        return None

    def get_game_by_rj(self, rj_code: str) -> Optional[Dict[str, Any]]:
        if not rj_code or not rj_code.strip():
            return None
        rj_upper = rj_code.strip().upper()
        for g in self.games:
            g_rj = (g.get("rj_code") or g.get("dlsite_id") or "").upper()
            if g_rj == rj_upper:
                return g
        return None

    def add_or_update_game(self, game_data: Dict[str, Any]) -> str:
        """ゲームを追加または更新"""
        if "id" not in game_data or not game_data["id"]:
            game_data["id"] = str(uuid.uuid4())

        # 1. ID照合
        existing = self.get_game_by_id(game_data["id"])
        if existing:
            existing.update(game_data)
            self.save()
            return existing["id"]

        # 2. RJコード照合 (DLsite作品の二重登録防止)
        target_rj = game_data.get("rj_code") or game_data.get("dlsite_id")
        if target_rj:
            existing_by_rj = self.get_game_by_rj(target_rj)
            if existing_by_rj:
                existing_by_rj.update(game_data)
                game_data["id"] = existing_by_rj["id"]
                self.save()
                return existing_by_rj["id"]

        # 3. 実行パス照合 (空パスでない場合のみ)
        path = game_data.get("path", "")
        if path and path.strip():
            existing_by_path = self.get_game_by_path(path)
            if existing_by_path:
                existing_by_path.update(game_data)
                game_data["id"] = existing_by_path["id"]
                self.save()
                return existing_by_path["id"]

        # 4. 新規追加
        self.config["games"].append(game_data)
        self.save()
        return game_data["id"]

    def remove_game(self, game_id: str) -> bool:
        initial_len = len(self.config["games"])
        self.config["games"] = [g for g in self.config["games"] if g.get("id") != game_id]
        if len(self.config["games"]) < initial_len:
            self.save()
            return True
        return False
