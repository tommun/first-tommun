from title_utils import clean_game_name
import os
import sys
import time
import subprocess
import threading
import webbrowser
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import customtkinter as ctk
from PIL import Image, ImageOps

try:
    import windnd
    HAS_WINDND = True
except ImportError:
    HAS_WINDND = False

from config_manager import ConfigManager
from icon_helper import IconHelper, ContinuousIconOptimizer, QUALITY_DLSITE_OFFICIAL, QUALITY_LOCAL_ORIGINAL
from folder_scanner import FolderScanner
from game_analyzer import GameAnalyzer
from comparison_dialog import ComparisonDialog
from icon_picker_dialog import IconPickerDialog
from folder_manager_dialog import FolderManagerDialog
from game_edit_dialog import GameEditDialog
from font_manager import get_mac_font, get_mac_font_family
from dlsite_metadata import DLsiteMetadataFetcher
from dlsite_purchase_dialog import DLsitePurchaseDialog
from fanza_metadata import FANZAMetadataFetcher

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class ModernLauncherApp(ctk.CTk):
    """DLsite Sound スタイル ＋ 3大プラットフォーム区分 (DLsite / FANZA / その他) ＋ 独立ジャンル・タグ識別 exeランチャー"""

    def __init__(self):
        super().__init__()

        self.config_mgr = ConfigManager()
        self.icon_helper = IconHelper()

        self.title("🎵 GameLauncher - DLsite Sound Style")
        window_w = self.config_mgr.config.get("settings", {}).get("window_width", 1240)
        window_h = self.config_mgr.config.get("settings", {}).get("window_height", 800)
        self.geometry(f"{window_w}x{window_h}")
        self.minsize(860, 560)
        self.configure(fg_color="#09071a")  # DLsite Sound Midnight Dark

        # 状態変数
        self.is_fullscreen = False
        self.current_platform = "すべて"   # "すべて", "DLsite", "FANZA", "その他", "お気に入り"
        self.current_genre = "すべて"      # "すべて", "ロールプレイング", "アクション", "アドベンチャー", "シミュレーション", etc.
        self.current_author = "すべての作者・サークル"
        self.search_query = ""
        self.sort_order = "最近プレイした順"  # 最近プレイした順, 作品名 (昇順), 作者・サークル名 (昇順), 登録順
        self.card_images = {}               # cache_key -> CTkImage
        self.card_widgets = {}              # game_id -> Dict of widgets
        self.grouped_games = {}             # 重複ゲームグループ
        self._last_window_width = 0
        self._resize_timer = None

        self._build_ui()
        self._setup_window_events()
        self._setup_drag_and_drop()

        # 継続的サムネイル最適化ワーカーの初期化と開始
        self.optimizer = ContinuousIconOptimizer(
            self.icon_helper,
            get_games_fn=lambda: self.config_mgr.games,
            on_updated_callback=self._on_game_icon_improved
        )
        self.optimizer.start()

        # 起動時処理
        self.after(200, self._initial_check_and_load)

    def _setup_window_events(self):
        """全画面切り替えキーバインドおよびリサイズ検知イベント"""
        self.bind("<F11>", lambda e: self.toggle_fullscreen())
        self.bind("<Escape>", lambda e: self.exit_fullscreen())
        self.bind("<Configure>", self._on_window_configure)

    def toggle_fullscreen(self, event=None):
        """全画面モードのオン・オフ切り替え"""
        self.is_fullscreen = not self.is_fullscreen
        self.attributes("-fullscreen", self.is_fullscreen)
        if hasattr(self, "fullscreen_btn"):
            self.fullscreen_btn.configure(
                text="🗗 縮小" if self.is_fullscreen else "⛶ 全画面",
                fg_color="#3a86ff" if self.is_fullscreen else "#1b163b"
            )
        self.status_lbl.configure(
            text="全画面表示 (F11 または Esc で戻る)" if self.is_fullscreen else "通常ウィンドウ表示",
            text_color="#77aaf6"
        )
        self.after(60, self.refresh_games)

    def exit_fullscreen(self, event=None):
        """全画面モードを解除"""
        if self.is_fullscreen:
            self.is_fullscreen = False
            self.attributes("-fullscreen", False)
            if hasattr(self, "fullscreen_btn"):
                self.fullscreen_btn.configure(text="⛶ 全画面", fg_color="#1b163b")
            self.status_lbl.configure(text="通常ウィンドウ表示", text_color="#77aaf6")
            self.after(60, self.refresh_games)

    def _on_window_configure(self, event):
        """ウィンドウサイズ変更時のレスポンシブ再配置 (Debounce処理)"""
        if event.widget == self:
            new_w = event.width
            if abs(new_w - self._last_window_width) > 35:
                self._last_window_width = new_w
                if self._resize_timer:
                    self.after_cancel(self._resize_timer)
                self._resize_timer = self.after(120, self._on_resize_debounced)

    def _on_resize_debounced(self):
        self._resize_timer = None
        self.refresh_games()

    def _build_ui(self):
        # 1. 最上部ヘッダー (DLsite Sound Midnight Navigation Bar)
        self.header_frame = ctk.CTkFrame(
            self,
            height=68,
            corner_radius=0,
            fg_color="#0d0a22",
            border_width=1,
            border_color="#1d1742"
        )
        self.header_frame.pack(fill="x", side="top")
        self.header_frame.pack_propagate(False)

        # 左側: ロゴ ＆ リアルタイム検索バー (作品名・サークル・ジャンル・タグ全対応)
        left_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        left_box.pack(side="left", padx=(18, 10), fill="y")

        logo_badge = ctk.CTkLabel(
            left_box,
            text="SOUND",
            font=get_mac_font(size=9, weight="bold"),
            text_color="#080617",
            fg_color="#77aaf6",
            corner_radius=4,
            width=46,
            height=18
        )
        logo_badge.pack(side="left", padx=(0, 6), pady=24)

        logo_lbl = ctk.CTkLabel(
            left_box,
            text="GameLauncher",
            font=get_mac_font(size=17, weight="bold"),
            text_color="#ffffff"
        )
        logo_lbl.pack(side="left", padx=(0, 14), pady=20)

        self.search_entry = ctk.CTkEntry(
            left_box,
            placeholder_text="🔍 作品名・作者・ジャンル・タグで検索...",
            placeholder_text_color="#737099",
            text_color="#ffffff",
            fg_color="#171233",
            border_color="#2c2357",
            border_width=1,
            width=290,
            height=36,
            corner_radius=18,
            font=get_mac_font(size=11)
        )
        self.search_entry.pack(side="left", pady=16)
        self.search_entry.bind("<KeyRelease>", self._on_search_changed)
        self.search_entry.bind("<Return>", self._on_search_enter)

        # 中央: 3大プラットフォーム区分ピルナビゲーション (DLsite / FANZA / その他)
        self.center_nav_frame = ctk.CTkFrame(
            self.header_frame,
            height=40,
            corner_radius=20,
            fg_color="#151030",
            border_width=1,
            border_color="#2b2257"
        )
        self.center_nav_frame.pack(side="left", expand=True, pady=14)

        self.platform_buttons = {}
        nav_items = [
            ("すべて", "🎮 すべて"),
            ("DLsite", "🔵 DLsite"),
            ("FANZA", "🟣 FANZA"),
            ("その他", "⚪ その他"),
            ("お気に入り", "⭐ お気に入り"),
        ]

        for plat_key, label in nav_items:
            is_active = (self.current_platform == plat_key)
            btn = ctk.CTkButton(
                self.center_nav_frame,
                text=label,
                width=92,
                height=32,
                corner_radius=16,
                fg_color="#3e316d" if is_active else "transparent",
                hover_color="#4f3f8c" if is_active else "#221a47",
                text_color="#ffffff" if is_active else "#9d98c2",
                font=get_mac_font(size=11, weight="bold" if is_active else "normal"),
                command=lambda k=plat_key: self._on_platform_clicked(k)
            )
            btn.pack(side="left", padx=2, pady=4)
            self.platform_buttons[plat_key] = btn

        # 右側: ツールボタン群 (購入履歴取り込み, DLsite同期, 全画面, フォルダ, 追加)
        right_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        right_box.pack(side="right", padx=(10, 18), fill="y")

        self.import_btn = ctk.CTkButton(
            right_box,
            text="📥 購入履歴",
            width=88,
            height=34,
            corner_radius=17,
            fg_color="#2b2266",
            hover_color="#3d308c",
            text_color="#ffffff",
            border_width=1,
            border_color="#423499",
            font=get_mac_font(size=11, weight="bold"),
            command=self._open_purchase_importer
        )
        self.import_btn.pack(side="left", padx=3, pady=17)

        self.dlsite_sync_btn = ctk.CTkButton(
            right_box,
            text="🌐 ストア同期",
            width=92,
            height=34,
            corner_radius=17,
            fg_color="#1d1742",
            hover_color="#2d2366",
            text_color="#9dc2f8",
            border_width=1,
            border_color="#342b6e",
            font=get_mac_font(size=11, weight="bold"),
            command=self._trigger_dlsite_sync_all
        )
        self.dlsite_sync_btn.pack(side="left", padx=3, pady=17)

        self.fullscreen_btn = ctk.CTkButton(
            right_box,
            text="⛶ 全画面",
            width=80,
            height=34,
            corner_radius=17,
            fg_color="#1b163b",
            hover_color="#2a225c",
            text_color="#77aaf6",
            border_width=1,
            border_color="#342b6e",
            font=get_mac_font(size=11, weight="bold"),
            command=self.toggle_fullscreen
        )
        self.fullscreen_btn.pack(side="left", padx=3, pady=17)

        self.add_app_btn = ctk.CTkButton(
            right_box,
            text="＋ 追加",
            width=68,
            height=34,
            corner_radius=17,
            fg_color="#3a86ff",
            hover_color="#2b68cb",
            text_color="#ffffff",
            font=get_mac_font(size=12, weight="bold"),
            command=self._open_add_dialog
        )
        self.add_app_btn.pack(side="left", padx=3, pady=17)

        self.folder_btn = ctk.CTkButton(
            right_box,
            text="📁 フォルダ",
            width=80,
            height=34,
            corner_radius=17,
            fg_color="#1b163b",
            hover_color="#2a225c",
            text_color="#e2e0ff",
            border_width=1,
            border_color="#342b6e",
            font=get_mac_font(size=11, weight="bold"),
            command=self._open_folder_manager
        )
        self.folder_btn.pack(side="left", padx=3, pady=17)

        self.theme_btn = ctk.CTkButton(
            right_box,
            text="🌓",
            width=36,
            height=34,
            corner_radius=17,
            fg_color="#171233",
            hover_color="#251c4e",
            text_color="#a5a1c9",
            border_width=1,
            border_color="#2c2357",
            font=get_mac_font(size=13),
            command=self._toggle_theme
        )
        self.theme_btn.pack(side="left", padx=3, pady=17)

        # 2. メインスクロールエリア（DLsite Sound 全画面対応キャンバス）
        self.scroll_canvas = ctk.CTkScrollableFrame(
            self,
            corner_radius=0,
            fg_color="#09071a"
        )
        self.scroll_canvas.pack(fill="both", expand=True, padx=20, pady=(10, 4))

        # 3. 最下部ステータスバー
        self.footer_bar = ctk.CTkFrame(self, height=28, corner_radius=0, fg_color="#0d0a22")
        self.footer_bar.pack(fill="x", side="bottom")

        self.status_lbl = ctk.CTkLabel(
            self.footer_bar,
            text="準備完了",
            font=get_mac_font(size=11),
            text_color="#77aaf6"
        )
        self.status_lbl.pack(side="left", padx=16)

        self.dnd_lbl = ctk.CTkLabel(
            self.footer_bar,
            text="※ [F11] で全画面表示切り替え | DLsite / FANZA / その他 の3プラットフォーム自動識別対応",
            font=get_mac_font(size=11),
            text_color="#737099"
        )
        self.dnd_lbl.pack(side="right", padx=16)

    def _on_platform_clicked(self, plat_key: str):
        self.current_platform = plat_key
        for k, btn in self.platform_buttons.items():
            is_active = (k == plat_key)
            btn.configure(
                fg_color="#3e316d" if is_active else "transparent",
                hover_color="#4f3f8c" if is_active else "#221a47",
                text_color="#ffffff" if is_active else "#9d98c2",
                font=get_mac_font(size=11, weight="bold" if is_active else "normal")
            )
        self.refresh_games()

    def _setup_drag_and_drop(self):
        if HAS_WINDND:
            try:
                windnd.hook_dropfiles(self, func=self._on_files_dropped)
            except Exception as e:
                print(f"[DnD] ドラッグ＆ドロップ初期化エラー: {e}")

    def _on_files_dropped(self, file_paths):
        if not file_paths:
            return

        for raw_p in file_paths:
            path_str = raw_p.decode("utf-8", errors="ignore") if isinstance(raw_p, bytes) else str(raw_p)
            p = Path(path_str)

            if p.is_file() and p.suffix.lower() in [".html", ".htm"]:
                # HTMLドロップ時は購入履歴インポーターを自動起動
                from dlsite_purchase_importer import DLsitePurchaseImporter
                rjs = DLsitePurchaseImporter.extract_from_html_file(str(p))
                if rjs:
                    msg = f"DLsite購入履歴HTMLを検出しました！\n{len(rjs)} 件の購入作品をライブラリに取り込みますか？"
                    if messagebox.askyesno("購入履歴の検出", msg):
                        DLsitePurchaseImporter.sync_purchased_games(rjs, self.config_mgr, self.icon_helper)
                        self.refresh_games()
                        messagebox.showinfo("取り込み完了", f"{len(rjs)} 件の購入作品を同期しました！")
                        return

            if p.is_dir():
                found = FolderScanner.scan_library_folder(str(p), default_category="その他")
                if found:
                    for item in found:
                        self.config_mgr.add_or_update_game(item)
                    self.refresh_games()
                    messagebox.showinfo("登録完了", f"フォルダから {len(found)} 件のゲームを登録しました！")
                    break
            elif p.is_file() and p.suffix.lower() in [".exe", ".lnk"]:
                game_data = {
                    "name": p.stem,
                    "path": str(p),
                    "work_dir": str(p.parent),
                    "folder_path": str(p.parent),
                    "platform": "その他",
                    "genre": "その他",
                    "category": "その他",
                    "is_standalone": True
                }
                self._open_edit_dialog_for_new(game_data)
                break

    def _open_edit_dialog_for_new(self, initial_data: Dict[str, Any]):
        def on_save(saved_data):
            self.config_mgr.add_or_update_game(saved_data)
            self.refresh_games()

        GameEditDialog(self, initial_data, self.config_mgr.categories, self.icon_helper, on_save)

    def _toggle_theme(self):
        cur = ctk.get_appearance_mode()
        new_mode = "Light" if cur == "Dark" else "Dark"
        ctk.set_appearance_mode(new_mode)
        self.config_mgr.config["theme"] = new_mode
        self.config_mgr.save()

    def _initial_check_and_load(self):
        if len(self.config_mgr.games) == 0 and len(self.config_mgr.scan_folders) > 0:
            msg = (
                "ライブラリフォルダが見つかりました：\n"
                + "\n".join([f" - {f}" for f in self.config_mgr.scan_folders])
                + "\n\nこれらのフォルダ内の全ゲームを自動スキャンして登録しますか？"
            )
            if messagebox.askyesno("初回自動スキャン", msg):
                self._run_background_scan(self.config_mgr.scan_folders)
                return

        self.refresh_games()

    def _run_background_scan(self, folders: List[str]):
        self.status_lbl.configure(text="ゲームを全探索スキャン中...", text_color="#3a86ff")

        def worker():
            new_count = 0
            for folder in folders:
                detected = FolderScanner.scan_library_folder(folder, default_category="その他")
                for item in detected:
                    existing = self.config_mgr.get_game_by_path(item["path"])
                    if not existing:
                        self.config_mgr.add_or_update_game(item)
                        new_count += 1
                    else:
                        changed = False
                        if not existing.get("local_illustration") and item.get("local_illustration"):
                            existing["local_illustration"] = item["local_illustration"]
                            changed = True
                        if not existing.get("rj_code") and item.get("rj_code"):
                            existing["rj_code"] = item["rj_code"]
                            changed = True
                        if changed:
                            self.config_mgr.save()
            self.after(0, lambda: self._on_background_scan_done(new_count))

        threading.Thread(target=worker, daemon=True).start()

    def _on_background_scan_done(self, new_count: int):
        self.status_lbl.configure(text=f"自動スキャン完了: {len(self.config_mgr.games)} 件登録中", text_color="#2b7a4b")
        self.refresh_games()

    def _on_search_changed(self, event=None):
        self.search_query = self.search_entry.get().strip().lower()
        self.refresh_games()

    def _on_search_enter(self, event=None):
        filtered = self._get_filtered_games()
        if filtered:
            first_game = filtered[0]
            self._launch_game(first_game)

    def _on_author_filter_changed(self, choice: str):
        self.current_author = choice
        self.refresh_games()

    def _on_sort_changed(self, choice: str):
        self.sort_order = choice
        self.refresh_games()

    def _select_genre(self, genre_name: str):
        self.current_genre = genre_name
        self.refresh_games()

    def _get_filtered_games(self) -> List[Dict[str, Any]]:
        all_games = self.config_mgr.games
        filtered = []

        for g in all_games:
            # 1. プラットフォーム絞り込み (DLsite / FANZA / その他 / お気に入り)
            if self.current_platform != "すべて":
                if self.current_platform == "お気に入り":
                    if not g.get("favorite", False) and not g.get("icon_locked", False):
                        continue
                else:
                    g_plat = g.get("platform", "その他")
                    if g_plat != self.current_platform:
                        continue

            # 2. ゲームジャンル絞り込み (ロールプレイング, アクション, etc. - 独立軸)
            if self.current_genre != "すべて":
                g_genre = g.get("genre") or g.get("category") or ""
                g_tags = g.get("tags", [])
                if g_genre != self.current_genre and self.current_genre not in g_tags:
                    continue

            # 3. 作者・サークル絞り込み
            if self.current_author != "すべての作者・サークル":
                g_author = g.get("author", "不明")
                if g_author != self.current_author:
                    continue

            # 4. リアルタイム検索クエリ絞り込み（作品名、作者、パス、RJコード、ジャンル、タグ全対象）
            if self.search_query:
                name = g.get("name", "").lower()
                author = g.get("author", "").lower()
                path = g.get("path", "").lower()
                rj = (g.get("rj_code") or "").lower()
                genre = (g.get("genre") or g.get("category") or "").lower()
                tags = [t.lower() for t in g.get("tags", [])]
                if (self.search_query not in name and 
                    self.search_query not in author and 
                    self.search_query not in path and 
                    self.search_query not in rj and
                    self.search_query not in genre and
                    not any(self.search_query in t for t in tags)):
                    continue

            filtered.append(g)

        # 並び替え（ソート）
        if self.sort_order == "最近プレイした順":
            filtered.sort(key=lambda x: (x.get("last_launched", 0), x.get("name", "").lower()), reverse=True)
        elif self.sort_order == "作品名 (昇順)":
            filtered.sort(key=lambda x: x.get("name", "").lower())
        elif self.sort_order == "作者・サークル名 (昇順)":
            filtered.sort(key=lambda x: (1 if x.get("author", "不明") == "不明" else 0, x.get("author", "不明").lower(), x.get("name", "").lower()))
        elif self.sort_order == "登録順":
            pass

        return filtered

    def _get_ctk_image(self, game: Dict[str, Any], target_size: Tuple[int, int]) -> Optional[ctk.CTkImage]:
        game_id = game.get("id")
        cache_key = f"{game_id}_{target_size[0]}x{target_size[1]}"
        if cache_key in self.card_images:
            return self.card_images[cache_key]

        resolved_icon = game.get("icon_path")
        if not resolved_icon or not os.path.exists(resolved_icon):
            resolved_icon, quality = self.icon_helper.resolve_best_thumbnail(game, allow_web_search=True)
            game["icon_path"] = resolved_icon
            game["icon_quality"] = quality
            self.config_mgr.save()

        if not resolved_icon or not os.path.exists(resolved_icon):
            return None

        try:
            pil_img = Image.open(resolved_icon).convert("RGBA")
            fitted_img = ImageOps.fit(pil_img, target_size, method=Image.Resampling.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=fitted_img, dark_image=fitted_img, size=target_size)
            self.card_images[cache_key] = ctk_img
            return ctk_img
        except Exception:
            return None

    def refresh_games(self):
        """DLsite Sound スタイル ＋ プラットフォーム区分 ＋ 独立ジャンル・タグの再描画"""
        for w in self.scroll_canvas.winfo_children():
            w.destroy()

        self.card_widgets.clear()

        filtered = self._get_filtered_games()
        self.grouped_games = GameAnalyzer.group_identical_games(self.config_mgr.games)
        self.status_lbl.configure(text=f"登録数: {len(self.config_mgr.games)} 件 (表示中: {len(filtered)} 件)")

        # 利用可能幅の取得と動的列数 (cols) の算出
        canvas_w = self.scroll_canvas.winfo_width()
        if canvas_w < 500:
            canvas_w = max(800, self.winfo_width() - 50)

        cols = max(3, canvas_w // 210)
        is_searching = bool(self.search_query.strip())

        if not is_searching and self.current_platform in ["すべて", "DLsite"]:
            # ============================================================
            # セクション 1: 最近プレイした作品 〉
            # ============================================================
            recent_games = [g for g in self.config_mgr.games if g.get("last_launched")]
            recent_games.sort(key=lambda x: x.get("last_launched", 0), reverse=True)
            if not recent_games:
                recent_games = self.config_mgr.games[:5]
            else:
                recent_games = recent_games[:5]

            if recent_games:
                sec1_header = ctk.CTkFrame(self.scroll_canvas, fg_color="transparent")
                sec1_header.pack(fill="x", padx=10, pady=(8, 12))

                ctk.CTkLabel(
                    sec1_header,
                    text="最近プレイした作品 〉",
                    font=get_mac_font(size=17, weight="bold"),
                    text_color="#ffffff"
                ).pack(side="left")

                sec1_row = ctk.CTkFrame(self.scroll_canvas, fg_color="transparent")
                sec1_row.pack(fill="x", padx=6, pady=(0, 20))

                recent_cols = min(len(recent_games), cols)
                for c in range(recent_cols):
                    sec1_row.grid_columnconfigure(c, weight=1)

                for idx, r_game in enumerate(recent_games[:recent_cols]):
                    self._create_recent_card(sec1_row, r_game, 0, idx)

        # ============================================================
        # セクション 2: ゲームジャンル 〉 (プラットフォームとは完全に独立した分類軸)
        # ============================================================
        sec2_header = ctk.CTkFrame(self.scroll_canvas, fg_color="transparent")
        sec2_header.pack(fill="x", padx=10, pady=(6, 10))

        ctk.CTkLabel(
            sec2_header,
            text="ゲームジャンル 〉",
            font=get_mac_font(size=17, weight="bold"),
            text_color="#ffffff"
        ).pack(side="left")

        genre_row = ctk.CTkFrame(self.scroll_canvas, fg_color="transparent")
        genre_row.pack(fill="x", padx=6, pady=(0, 20))

        # 登録ゲームから公式ゲームジャンルを動的に集約
        dynamic_genres = set()
        for g in self.config_mgr.games:
            gen = g.get("genre") or g.get("category")
            if gen and gen not in ["ゲーム", "download", "すべて"]:
                dynamic_genres.add(gen)

        genre_order = ["ロールプレイング", "アドベンチャー", "アクション", "シミュレーション", "パズル", "その他"]
        sorted_genres = [g for g in genre_order if g in dynamic_genres]
        for g in sorted(list(dynamic_genres)):
            if g not in sorted_genres:
                sorted_genres.append(g)

        genres_to_show = ["すべて"] + sorted_genres

        for idx, g_name in enumerate(genres_to_show):
            is_active = (g_name == self.current_genre)
            g_btn = ctk.CTkButton(
                genre_row,
                text=g_name,
                width=130,
                height=44,
                corner_radius=14,
                fg_color="#362963" if is_active else "#161133",
                hover_color="#493885" if is_active else "#241c52",
                border_width=2 if is_active else 1,
                border_color="#77aaf6" if is_active else "#2d245c",
                text_color="#ffffff" if is_active else "#c0bcd9",
                font=get_mac_font(size=12, weight="bold"),
                command=lambda gn=g_name: self._select_genre(gn)
            )
            g_btn.pack(side="left", padx=5, pady=4)

        # ============================================================
        # セクション 3: 作品一覧グリッド 〉
        # ============================================================
        sec3_header = ctk.CTkFrame(self.scroll_canvas, fg_color="transparent")
        sec3_header.pack(fill="x", padx=10, pady=(6, 12))

        # タイトル表示（プラットフォーム ＋ ジャンル）
        title_parts = []
        if self.current_platform != "すべて":
            title_parts.append(f"[{self.current_platform}]")
        if self.current_genre != "すべて":
            title_parts.append(f"「{self.current_genre}」")
        if not title_parts:
            title_text = f"すべての作品 〉 ({len(filtered)}件)"
        else:
            title_text = f"{' '.join(title_parts)} の作品 〉 ({len(filtered)}件)"
        if is_searching:
            title_text = f"検索結果 〉 ({len(filtered)}件)"

        ctk.CTkLabel(
            sec3_header,
            text=title_text,
            font=get_mac_font(size=17, weight="bold"),
            text_color="#ffffff"
        ).pack(side="left")

        # 右側コントロール（作者絞り込み ＆ ソート）
        sec3_controls = ctk.CTkFrame(sec3_header, fg_color="transparent")
        sec3_controls.pack(side="right")

        ctk.CTkLabel(
            sec3_controls,
            text="👤 サークル:",
            font=get_mac_font(size=11, weight="bold"),
            text_color="#77aaf6"
        ).pack(side="left", padx=(0, 4))

        authors = set()
        for g in self.config_mgr.games:
            a = g.get("author")
            if a and a != "不明":
                authors.add(a)
        author_list = ["すべての作者・サークル"] + sorted(list(authors), key=lambda s: s.lower())

        if self.current_author not in author_list:
            self.current_author = "すべての作者・サークル"

        self.author_menu = ctk.CTkOptionMenu(
            sec3_controls,
            values=author_list,
            width=175,
            height=32,
            corner_radius=16,
            fg_color="#161233",
            button_color="#271f54",
            button_hover_color="#3a2f7a",
            dropdown_fg_color="#161233",
            dropdown_hover_color="#271f54",
            dropdown_text_color="#ffffff",
            text_color="#ffffff",
            font=get_mac_font(size=11),
            command=self._on_author_filter_changed
        )
        self.author_menu.set(self.current_author)
        self.author_menu.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(
            sec3_controls,
            text="並び替え:",
            font=get_mac_font(size=11, weight="bold"),
            text_color="#77aaf6"
        ).pack(side="left", padx=(0, 4))

        sort_menu = ctk.CTkOptionMenu(
            sec3_controls,
            values=["最近プレイした順", "作品名 (昇順)", "作者・サークル名 (昇順)", "登録順"],
            width=160,
            height=32,
            corner_radius=16,
            fg_color="#161233",
            button_color="#271f54",
            button_hover_color="#3a2f7a",
            dropdown_fg_color="#161233",
            dropdown_hover_color="#271f54",
            dropdown_text_color="#ffffff",
            text_color="#ffffff",
            font=get_mac_font(size=11),
            command=self._on_sort_changed
        )
        sort_menu.set(self.sort_order)
        sort_menu.pack(side="left")

        # 0件表示
        if not filtered:
            empty_box = ctk.CTkFrame(self.scroll_canvas, fg_color="transparent")
            empty_box.pack(pady=60)
            ctk.CTkLabel(
                empty_box,
                text="該当する作品がありません",
                font=get_mac_font(size=16, weight="bold"),
                text_color="gray60"
            ).pack()
            ctk.CTkLabel(
                empty_box,
                text="プラットフォームやジャンルフィルターを変更するか、「📥 購入履歴」から作品を追加してください。",
                font=get_mac_font(size=12),
                text_color="gray50"
            ).pack(pady=5)
            return

        # レスポンシブグリッドコンテナ
        grid_container = ctk.CTkFrame(self.scroll_canvas, fg_color="transparent")
        grid_container.pack(fill="both", expand=True, padx=4, pady=(0, 20))

        for c in range(cols):
            grid_container.grid_columnconfigure(c, weight=1)

        for idx, game in enumerate(filtered):
            row = idx // cols
            col = idx % cols
            self._create_game_tile(grid_container, game, row, col)

    def _create_recent_card(self, parent, game: Dict[str, Any], row: int, col: int):
        """「最近プレイした作品」用の大型ワイドジャケットカード"""
        game_id = game.get("id")

        card = ctk.CTkFrame(
            parent,
            corner_radius=14,
            fg_color="#13102b",
            border_width=1,
            border_color="#241e4d"
        )
        card.grid(row=row, column=col, padx=8, pady=4, sticky="nsew")

        # ワイドジャケット画像 (200x135)
        ctk_img = self._get_ctk_image(game, target_size=(200, 135))

        img_frame = ctk.CTkFrame(card, corner_radius=10, fg_color="#0a081a")
        img_frame.pack(padx=8, pady=(8, 6), fill="x")

        icon_btn = ctk.CTkButton(
            img_frame,
            image=ctk_img,
            text="",
            height=135,
            corner_radius=10,
            fg_color="transparent",
            hover_color="#221b4a",
            command=lambda g=game: self._launch_game(g)
        )
        icon_btn.pack(fill="both", expand=True)

        # 作品名 (2行制限 wrap)
        name = game.get("name", "Game")
        name_lbl = ctk.CTkLabel(
            card,
            text=name,
            font=get_mac_font(size=12, weight="bold"),
            text_color="#ffffff",
            wraplength=190,
            justify="left",
            anchor="w",
            cursor="hand2"
        )
        name_lbl.pack(padx=10, pady=(2, 2), fill="x")
        name_lbl.bind("<Button-1>", lambda e, g=game: self._launch_game(g))

        # プラットフォーム・サークル名表示
        author_text = game.get("author", "不明")
        plat = game.get("platform", "DLsite" if game.get("rj_code") else "その他")
        author_line = f"[{plat}] 👤 {author_text}"

        author_lbl = ctk.CTkLabel(
            card,
            text=author_line,
            font=get_mac_font(size=10),
            text_color="#8d89b0",
            wraplength=190,
            justify="left",
            anchor="w"
        )
        author_lbl.pack(padx=10, pady=(0, 10), fill="x")

        self._bind_card_hover(card, [img_frame, icon_btn, name_lbl, author_lbl])
        for w in [card, img_frame, icon_btn, name_lbl, author_lbl]:
            w.bind("<Button-3>", lambda e, g=game: self._show_context_menu(e, g))

    def _create_game_tile(self, parent, game: Dict[str, Any], row: int, col: int):
        """グリッド内のジャケットカード（3大プラットフォームバッジ ＆ 独立ジャンル・タグ付き）"""
        game_id = game.get("id")

        card = ctk.CTkFrame(
            parent,
            corner_radius=14,
            fg_color="#13102b",
            border_width=1,
            border_color="#241e4d"
        )
        card.grid(row=row, column=col, padx=6, pady=8, sticky="nsew")

        # 重複ゲーム判定
        group_key = None
        for k, g_list in self.grouped_games.items():
            if any(item.get("id") == game.get("id") for item in g_list):
                if len(g_list) > 1:
                    group_key = k
                break

        # ジャケット画像フレーム (180x125 4:3ワイド比率)
        img_container = ctk.CTkFrame(card, corner_radius=10, fg_color="#0a081a")
        img_container.pack(padx=8, pady=(8, 4), fill="x")

        ctk_img = self._get_ctk_image(game, target_size=(180, 125))

        icon_btn = ctk.CTkButton(
            img_container,
            image=ctk_img,
            text="",
            height=125,
            corner_radius=10,
            fg_color="transparent",
            hover_color="#221b4a",
            command=lambda g=game: self._launch_game(g)
        )
        icon_btn.pack(fill="both", expand=True)

        # トップバッジバー: プラットフォーム区分 (DLsite / FANZA / その他) ＆ ロック ＆ 重複
        badge_bar = ctk.CTkFrame(card, fg_color="transparent", height=22)
        badge_bar.pack(fill="x", padx=8, pady=(2, 2))

        plat = game.get("platform", "DLsite" if game.get("rj_code") else "その他")
        if plat == "DLsite":
            plat_color = "#152445"
            plat_border = "#2a4380"
            plat_text = "#77aaf6"
        elif plat == "FANZA":
            plat_color = "#381024"
            plat_border = "#6e1d44"
            plat_text = "#ff5c8a"
        else:
            plat_color = "#1a1733"
            plat_border = "#332c66"
            plat_text = "#b5b0d8"

        plat_badge = ctk.CTkLabel(
            badge_bar,
            text=plat,
            font=get_mac_font(size=9, weight="bold"),
            fg_color=plat_color,
            text_color=plat_text,
            corner_radius=6,
            width=50,
            height=18
        )
        plat_badge.pack(side="left", padx=(0, 4))

        is_locked = game.get("icon_locked", False)
        lock_btn = ctk.CTkButton(
            badge_bar,
            text="🔒" if is_locked else "✨",
            width=24,
            height=18,
            corner_radius=9,
            fg_color="#1b7a32" if is_locked else "#1a1538",
            hover_color="#239a40" if is_locked else "#26204f",
            text_color="#ffffff" if is_locked else "#77aaf6",
            border_width=0 if is_locked else 1,
            border_color="#362c6e",
            font=get_mac_font(size=9),
            command=lambda g=game: self._toggle_icon_lock(g)
        )
        lock_btn.pack(side="left")

        if group_key:
            dup_count = len(self.grouped_games[group_key])
            dup_btn = ctk.CTkButton(
                badge_bar,
                text=f"🔁 {dup_count}",
                width=42,
                height=18,
                corner_radius=9,
                fg_color="#9e6d00",
                hover_color="#b88002",
                text_color="#ffffff",
                font=get_mac_font(size=9, weight="bold"),
                command=lambda k=group_key: self._open_comparison_dialog(k)
            )
            dup_btn.pack(side="right")

        # ストアリンクボタン (DLsite または FANZA)
        store_label = "🌐 DLsite" if plat == "DLsite" else ("🌐 FANZA" if plat == "FANZA" else "🌐 検索")
        store_btn = ctk.CTkButton(
            badge_bar,
            text=store_label,
            width=56,
            height=18,
            corner_radius=9,
            fg_color="#1d1742",
            hover_color="#2c2266",
            text_color="#9dc2f8",
            border_width=1,
            border_color="#392d73",
            font=get_mac_font(size=9, weight="bold"),
            command=lambda g=game: self._open_store_page(g)
        )
        store_btn.pack(side="right", padx=(0, 4))

        # 作品名（2行wrap）
        name = game.get("name", "Game")
        name_lbl = ctk.CTkLabel(
            card,
            text=name,
            font=get_mac_font(size=12, weight="bold"),
            text_color="#ffffff",
            wraplength=180,
            justify="left",
            anchor="w",
            cursor="hand2"
        )
        name_lbl.pack(padx=8, pady=(2, 2), fill="x")
        name_lbl.bind("<Button-1>", lambda e, g=game: self._launch_game(g))

        # 独立したゲームジャンル ＆ 公式タグ表示
        genre_text = game.get("genre") or game.get("category", "")
        tags = game.get("tags", [])
        tag_parts = []
        if genre_text and genre_text not in ["ゲーム", "download", "その他"]:
            tag_parts.append(f"🏷️ {genre_text}")
        if tags:
            tag_parts.extend(tags[:2])

        if tag_parts:
            tag_lbl = ctk.CTkLabel(
                card,
                text=" • ".join(tag_parts),
                font=get_mac_font(size=9),
                text_color="#77aaf6",
                wraplength=180,
                justify="left",
                anchor="w"
            )
            tag_lbl.pack(padx=8, pady=(0, 1), fill="x")

        # 作者・サークル名
        author_text = game.get("author", "不明")
        author_lbl = ctk.CTkLabel(
            card,
            text=f"👤 {author_text}",
            font=get_mac_font(size=10),
            text_color="#8d89b0",
            wraplength=180,
            justify="left",
            anchor="w"
        )
        author_lbl.pack(padx=8, pady=(0, 4), fill="x")

        # アクションボタン（インストール済ならフォルダを開く、未インストールならDLsiteでダウンロード）
        is_installed = game.get("is_installed", True if game.get("path") else False)
        if is_installed:
            action_btn = ctk.CTkButton(
                card,
                text="📂 フォルダを開く",
                width=130,
                height=24,
                corner_radius=12,
                fg_color="#181335",
                hover_color="#271f54",
                text_color="#a5a1c9",
                border_width=1,
                border_color="#2b2257",
                font=get_mac_font(size=10),
                command=lambda g=game: self._open_game_folder(g)
            )
        else:
            action_btn = ctk.CTkButton(
                card,
                text="⬇️ DLsiteでダウンロード",
                width=138,
                height=24,
                corner_radius=12,
                fg_color="#2c1f54",
                hover_color="#3e2c7a",
                text_color="#77aaf6",
                border_width=1,
                border_color="#4f389e",
                font=get_mac_font(size=10, weight="bold"),
                command=lambda g=game: self._open_store_page(g)
            )
        action_btn.pack(pady=(2, 8))

        # ホバーエフェクト
        self._bind_card_hover(card, [img_container, icon_btn, name_lbl, author_lbl])

        # 右クリックメニューのバインド
        for w in [card, img_container, icon_btn, name_lbl, author_lbl]:
            w.bind("<Button-3>", lambda e, g=game: self._show_context_menu(e, g))

        self.card_widgets[game_id] = {
            "card": card,
            "icon_btn": icon_btn,
            "lock_btn": lock_btn,
            "game": game
        }

    def _bind_card_hover(self, card, inner_widgets):
        def on_enter(e):
            card.configure(fg_color="#191538", border_color="#3d3378")
        def on_leave(e):
            card.configure(fg_color="#13102b", border_color="#241e4d")

        card.bind("<Enter>", on_enter)
        card.bind("<Leave>", on_leave)

    def _on_game_icon_improved(self, updated_game: Dict[str, Any]):
        self.after(0, lambda: self._apply_improved_icon(updated_game))

    def _apply_improved_icon(self, updated_game: Dict[str, Any]):
        game_id = updated_game.get("id")
        self.config_mgr.save()

        for key in list(self.card_images.keys()):
            if key.startswith(f"{game_id}_"):
                del self.card_images[key]

        if game_id in self.card_widgets:
            new_img = self._get_ctk_image(updated_game, target_size=(180, 125))
            if new_img and "icon_btn" in self.card_widgets[game_id]:
                self.card_widgets[game_id]["icon_btn"].configure(image=new_img)

    def _open_purchase_importer(self):
        """DLsite購入履歴インポートダイアログを開く"""
        DLsitePurchaseDialog(self, self.config_mgr, self.icon_helper, on_complete=self.refresh_games)

    def _trigger_dlsite_sync_all(self):
        """全ゲームのDLsiteおよびFANZA公式情報・商品画像を一括同期"""
        self.status_lbl.configure(text="🌐 全ゲームの公式商品画像・ジャンル・タグを一括取得中...", text_color="#3a86ff")

        def worker():
            updated_count = 0
            for game in self.config_mgr.games:
                plat = game.get("platform", "DLsite")
                if plat == "FANZA":
                    meta = FANZAMetadataFetcher.search_by_title(game.get("name", ""))
                    if meta:
                        game["fanza_cid"] = meta.get("content_id", "")
                        game["fanza_url"] = meta.get("url", "")
                        if meta.get("genre") and meta["genre"] != "その他":
                            game["genre"] = meta["genre"]
                            game["category"] = meta["genre"]
                        if meta.get("tags"):
                            for t in meta["tags"]:
                                if t not in game.get("tags", []):
                                    game.setdefault("tags", []).append(t)
                        if meta.get("maker") and meta["maker"] != "不明":
                            game["author"] = meta["maker"]
                        if meta.get("image_url") and not game.get("icon_locked"):
                            img = self.icon_helper.download_image(meta["image_url"])
                            if img:
                                p = self.icon_helper.cache_image(f"fanza_{meta.get('content_id', abs(hash(game.get('name'))))}", img)
                                if p:
                                    game["icon_path"] = p
                                    game["icon_quality"] = QUALITY_DLSITE_OFFICIAL
                        updated_count += 1
                        self.after(0, lambda n=game.get('name'): self.status_lbl.configure(
                            text=f"🟣 FANZA同期中: {updated_count}件完了 ({n})", text_color="#a855f7"
                        ))
                else:
                    meta = DLsiteMetadataFetcher.get_metadata_for_game(game)
                    if meta:
                        game["rj_code"] = meta["rj_code"]
                        game["dlsite_url"] = meta["url"]
                        game["platform"] = "DLsite"
                        game["genre"] = meta["genre"]
                        game["category"] = meta["genre"]
                        game["tags"] = meta["tags"]

                        if game.get("name", "").upper().startswith("RJ") or not game.get("name"):
                            game["name"] = clean_game_name(meta["title"])
                        if game.get("author") in ["不明", None, "", "download"]:
                            game["author"] = meta["maker"]

                        if meta.get("image_url") and not game.get("icon_locked"):
                            img = self.icon_helper.download_image(meta["image_url"])
                            if img:
                                p = self.icon_helper.cache_image(f"dlsite_{meta['rj_code']}", img)
                                if p:
                                    game["icon_path"] = p
                                    game["icon_quality"] = QUALITY_DLSITE_OFFICIAL

                        updated_count += 1
                        self.after(0, lambda n=game.get('name'): self.status_lbl.configure(
                            text=f"🌐 DLsite同期中: {updated_count}件完了 ({n})", text_color="#3a86ff"
                        ))
            self.config_mgr.save()
            self.after(0, lambda: self._on_dlsite_sync_done(updated_count))

        threading.Thread(target=worker, daemon=True).start()

    def _on_dlsite_sync_done(self, count: int):
        self.status_lbl.configure(text=f"✨ DLsite情報の同期完了: {count} 件のジャンル・タグ・サークル情報を更新しました", text_color="#2b7a4b")
        self.refresh_games()

    def _open_store_page(self, game: Dict[str, Any]):
        """プラットフォームに応じた商品ページ（DLsite / FANZA）を開く"""
        plat = game.get("platform", "DLsite")
        if plat == "FANZA":
            title = game.get("name", "")
            enc = urllib.parse.quote(title)
            url = f"https://www.dmm.co.jp/search/=/searchstr={enc}/"
        else:
            url = game.get("dlsite_url")
            rj = game.get("rj_code")
            if not url and rj:
                url = f"https://www.dlsite.com/maniax/work/=/product_id/{rj}.html"
            if not url:
                title = game.get("name", "")
                enc = urllib.parse.quote(title)
                url = f"https://www.dlsite.com/maniax/fsr/=/language/jp/keyword/{enc}"
        webbrowser.open(url)
        self.status_lbl.configure(text=f"ブラウザで商品ページを開きました: {game.get('name')}", text_color="#77aaf6")

    def _fetch_single_game_fanza_metadata(self, game: Dict[str, Any]):
        """単体ゲームのFANZA情報を取得し公式画像・ジャンル・タグに差し替え"""
        name = game.get("name", "")
        self.status_lbl.configure(text=f"🟣 FANZAから情報取得中: {name}...", text_color="#a855f7")

        def worker():
            meta = FANZAMetadataFetcher.search_by_title(name)
            if meta:
                game["fanza_cid"] = meta.get("content_id", "")
                game["fanza_url"] = meta.get("url", "")
                game["platform"] = "FANZA"
                if meta.get("genre") and meta["genre"] != "その他":
                    game["genre"] = meta["genre"]
                    game["category"] = meta["genre"]
                if meta.get("tags"):
                    for t in meta["tags"]:
                        if t not in game.get("tags", []):
                            game.setdefault("tags", []).append(t)
                if meta.get("maker") and meta["maker"] != "不明":
                    game["author"] = meta["maker"]

                # 公式商品画像に差し替え
                if meta.get("image_url") and not game.get("icon_locked"):
                    img = self.icon_helper.download_image(meta["image_url"])
                    if img:
                        p = self.icon_helper.cache_image(f"fanza_{meta.get('content_id', abs(hash(name)))}", img)
                        if p:
                            game["icon_path"] = p
                            game["icon_quality"] = QUALITY_DLSITE_OFFICIAL
                self.config_mgr.save()
                self.after(0, lambda: self._on_single_fanza_done(game))
            else:
                self.after(0, lambda: self.status_lbl.configure(text=f"FANZA情報が見つかりませんでした: {name}", text_color="#d9534f"))

        threading.Thread(target=worker, daemon=True).start()

    def _on_single_fanza_done(self, game: Dict[str, Any]):
        self.status_lbl.configure(text=f"✨ FANZA公式情報・画像を反映しました: {game.get('name')} [{game.get('genre')}]", text_color="#2b7a4b")
        self.refresh_games()

    def _fetch_single_game_dlsite_metadata(self, game: Dict[str, Any]):
        """単体ゲームのDLsite情報を取得・反映"""
        self.status_lbl.configure(text=f"🌐 DLsiteから情報取得中: {game.get('name')}...", text_color="#3a86ff")

        def worker():
            meta = DLsiteMetadataFetcher.get_metadata_for_game(game)
            if meta:
                game["rj_code"] = meta["rj_code"]
                game["dlsite_url"] = meta["url"]
                game["platform"] = "DLsite"
                game["genre"] = meta["genre"]
                game["category"] = meta["genre"]
                game["tags"] = meta["tags"]

                if game.get("name", "").upper().startswith("RJ") or not game.get("name"):
                    game["name"] = clean_game_name(meta["title"])
                if game.get("author") in ["不明", None, "", "download"]:
                    game["author"] = meta["maker"]

                if meta.get("image_url") and not game.get("icon_locked"):
                    img = self.icon_helper.download_image(meta["image_url"])
                    if img:
                        p = self.icon_helper.cache_image(f"dlsite_{meta['rj_code']}", img)
                        if p:
                            game["icon_path"] = p
                            game["icon_quality"] = QUALITY_DLSITE_OFFICIAL
                self.config_mgr.save()
                self.after(0, lambda: self._on_single_dlsite_done(game))
            else:
                self.after(0, lambda: self.status_lbl.configure(text=f"DLsite情報が見つかりませんでした: {game.get('name')}", text_color="#d9534f"))

        threading.Thread(target=worker, daemon=True).start()

    def _on_single_dlsite_done(self, game: Dict[str, Any]):
        self.status_lbl.configure(text=f"✨ DLsite情報を反映しました: {game.get('name')} [{game.get('genre')}]", text_color="#2b7a4b")
        self.refresh_games()

    def _toggle_icon_lock(self, game: Dict[str, Any]):
        cur = game.get("icon_locked", False)
        game["icon_locked"] = not cur
        self.config_mgr.save()
        game_id = game.get("id")
        if game_id in self.card_widgets and "lock_btn" in self.card_widgets[game_id]:
            is_locked = game["icon_locked"]
            self.card_widgets[game_id]["lock_btn"].configure(
                text="🔒" if is_locked else "✨",
                fg_color="#1b7a32" if is_locked else "#1a1538",
                hover_color="#239a40" if is_locked else "#26204f",
                text_color="#ffffff" if is_locked else "#77aaf6"
            )
        status_msg = "🔒 サムネイルを確定しました" if game["icon_locked"] else "✨ サムネイル自動最適化を再開しました"
        self.status_lbl.configure(text=f"{status_msg}: {game.get('name')}", text_color="#77aaf6" if game['icon_locked'] else "#4361ee")

    def _show_context_menu(self, event, game: Dict[str, Any]):
        menu = tk.Menu(self, tearoff=0, font=(get_mac_font_family(), 10))
        plat = game.get("platform", "DLsite")

        menu.add_command(label="▶ 起動する", command=lambda: self._launch_game(game))
        menu.add_separator()

        store_title = "🌐 DLsite商品ページを開く (ブラウザ)" if plat == "DLsite" else ("🌐 FANZA商品ページを開く (ブラウザ)" if plat == "FANZA" else "🌐 Web検索で作品を探す")
        menu.add_command(label=store_title, command=lambda: self._open_store_page(game))
        if plat == "FANZA":
            menu.add_command(label="🔄 FANZAから最新情報を取得 (公式画像/ジャンル/タグ)", command=lambda: self._fetch_single_game_fanza_metadata(game))
        else:
            menu.add_command(label="🔄 DLsiteから最新情報を取得 (ジャンル/タグ/サークル)", command=lambda: self._fetch_single_game_dlsite_metadata(game))
        menu.add_separator()

        group_key = None
        for k, g_list in self.grouped_games.items():
            if any(item.get("id") == game.get("id") for item in g_list) and len(g_list) > 1:
                group_key = k
                break
        if group_key:
            menu.add_command(label=f"🔁 重複・進行度を比較 ({len(self.grouped_games[group_key])}件)", command=lambda: self._open_comparison_dialog(group_key))
            menu.add_separator()

        is_locked = game.get("icon_locked", False)
        lock_label = "🔓 サムネイル確定を解除 (自動探索に戻す)" if is_locked else "🔒 サムネイルを確定 (現在の画像で固定)"
        menu.add_command(label=lock_label, command=lambda: self._toggle_icon_lock(game))
        menu.add_command(label="✨ 最適なサムネイルを再検索", command=lambda: self._re_optimize_single_game(game))
        menu.add_command(label="🔍 Webから画像を探す", command=lambda: self._open_icon_picker(game))
        menu.add_command(label="📂 ファイルの場所を開く", command=lambda: self._open_game_folder(game))
        menu.add_command(label="✏️ 情報を編集 (プラットフォーム/ジャンル/タグ)", command=lambda: self._open_edit_dialog(game))
        menu.add_separator()
        menu.add_command(label="🗑️ ランチャーから削除", command=lambda: self._remove_game(game))

        menu.tk_popup(event.x_root, event.y_root)

    def _re_optimize_single_game(self, game: Dict[str, Any]):
        self.status_lbl.configure(text=f"🔍 「{game.get('name')}」の最適サムネイルを探索中...", text_color="#4361ee")
        def worker():
            new_path, new_q = self.icon_helper.resolve_best_thumbnail(game, allow_web_search=True)
            game["icon_path"] = new_path
            game["icon_quality"] = new_q
            self.after(0, lambda: self._apply_improved_icon(game))
        threading.Thread(target=worker, daemon=True).start()

    def _launch_game(self, game: Dict[str, Any]):
        exe_path = game.get("path", "")
        if not exe_path:
            # 未インストールの場合、ストアページを開いて案内
            self._open_store_page(game)
            messagebox.showinfo("未インストール", f"「{game.get('name')}」は未インストールです。\nブラウザで作品ページを開きました。ダウンロード後、ファイルをランチャーにドロップしてください。")
            return

        work_dir = game.get("work_dir") or os.path.dirname(exe_path)
        args = game.get("args", "")

        if not os.path.exists(exe_path):
            messagebox.showerror("エラー", f"実行ファイルが見つかりません:\n{exe_path}")
            return

        cmd = [exe_path]
        if args:
            cmd.extend(args.split())

        try:
            cwd = work_dir if os.path.exists(work_dir) else os.path.dirname(exe_path)
            subprocess.Popen(cmd, cwd=cwd)

            game["last_launched"] = time.time()
            game["play_count"] = game.get("play_count", 0) + 1
            self.config_mgr.save()

            self.status_lbl.configure(text=f"起動しました: {game.get('name')}", text_color="#2b7a4b")
        except Exception as e:
            messagebox.showerror("起動エラー", f"起動に失敗しました:\n{e}")

    def _open_game_folder(self, game: Dict[str, Any]):
        folder = game.get("folder_path") or os.path.dirname(game.get("path", ""))
        if folder and os.path.exists(folder):
            os.startfile(folder)
        else:
            messagebox.showerror("エラー", f"フォルダが存在しません:\n{folder}")

    def _open_comparison_dialog(self, group_key: str):
        group_list = self.grouped_games.get(group_key, [])
        if group_list:
            ComparisonDialog(self, group_list, on_refresh=self.refresh_games)

    def _open_icon_picker(self, game: Dict[str, Any]):
        def on_selected(new_icon_path):
            game["icon_path"] = new_icon_path
            game["icon_quality"] = QUALITY_LOCAL_ORIGINAL
            game["icon_locked"] = True
            self.config_mgr.save()
            self.refresh_games()

        IconPickerDialog(self, game.get("name", ""), game.get("path", ""), self.icon_helper, on_selected)

    def _open_add_dialog(self):
        def on_save(saved_data):
            self.config_mgr.add_or_update_game(saved_data)
            self.refresh_games()

        GameEditDialog(self, None, self.config_mgr.categories, self.icon_helper, on_save)

    def _open_edit_dialog(self, game: Dict[str, Any]):
        def on_save(saved_data):
            self.config_mgr.add_or_update_game(saved_data)
            self.refresh_games()

        GameEditDialog(self, game, self.config_mgr.categories, self.icon_helper, on_save)

    def _remove_game(self, game: Dict[str, Any]):
        if messagebox.askyesno("削除確認", f"「{game.get('name')}」をランチャーから削除しますか？\n（実際のファイルは削除されません）"):
            self.config_mgr.remove_game(game.get("id"))
            self.refresh_games()

    def _open_folder_manager(self):
        FolderManagerDialog(self, self.config_mgr, on_scan_complete=self.refresh_games)

def main():
    app = ModernLauncherApp()
    app.mainloop()

if __name__ == "__main__":
    main()
