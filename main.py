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
    """Steam ライブラリスタイル ＋ DLsite/FANZA/その他 PCゲームランチャー"""

    def __init__(self):
        super().__init__()

        self.config_mgr = ConfigManager()
        self.icon_helper = IconHelper()

        self.title("Steam")
        window_w = self.config_mgr.config.get("settings", {}).get("window_width", 1280)
        window_h = self.config_mgr.config.get("settings", {}).get("window_height", 820)
        self.geometry(f"{window_w}x{window_h}")
        self.minsize(920, 600)
        self.configure(fg_color="#171a21")  # Steam Dark Slate

        # 状態変数
        self.is_fullscreen = False
        self.current_platform = "すべて"   # "すべて", "DLsite", "FANZA", "その他", "お気に入り"
        self.current_genre = "すべて"      # "すべて", "ロールプレイング", "アクション", "アドベンチャー", "シミュレーション", etc.
        self.current_author = "すべての作者・サークル"
        self.search_query = ""
        self.sort_order = "作品名 (昇順)"  # 作品名 (昇順), 最近プレイした順, 作者・サークル名 (昇順), 登録順
        self.card_images = {}               # cache_key -> CTkImage
        self.card_widgets = {}              # game_id -> Dict of widgets
        self.sidebar_item_widgets = []      # サイドバー一覧用ウィジェット
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
                fg_color="#2a475e" if self.is_fullscreen else "#1e232d"
            )
        self.status_lbl.configure(
            text="全画面表示 (F11 または Esc で戻る)" if self.is_fullscreen else "ダウンロード: 完了",
            text_color="#66c0f4"
        )
        self.after(60, self.refresh_games)

    def exit_fullscreen(self, event=None):
        """全画面モードを解除"""
        if self.is_fullscreen:
            self.is_fullscreen = False
            self.attributes("-fullscreen", False)
            if hasattr(self, "fullscreen_btn"):
                self.fullscreen_btn.configure(text="⛶ 全画面", fg_color="#1e232d")
            self.status_lbl.configure(text="ダウンロード: 完了", text_color="#66c0f4")
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
        # ============================================================
        # 1. 最上部: Steam Menu Bar (Steam 表示 フレンド ゲーム ヘルプ)
        # ============================================================
        self.top_menu_bar = ctk.CTkFrame(
            self,
            height=26,
            corner_radius=0,
            fg_color="#171a21"
        )
        self.top_menu_bar.pack(fill="x", side="top")
        self.top_menu_bar.pack_propagate(False)

        menu_items = ["Steam", "表示", "フレンド", "ゲーム", "ヘルプ"]
        for m in menu_items:
            m_btn = ctk.CTkButton(
                self.top_menu_bar,
                text=m,
                width=46,
                height=22,
                corner_radius=0,
                fg_color="transparent",
                hover_color="#2a323d",
                text_color="#b8b6b4",
                font=get_mac_font(size=10)
            )
            m_btn.pack(side="left", padx=1, pady=2)

        # 右側コントロール: お知らせ・アバター・ウィンドウ操作
        top_right_box = ctk.CTkFrame(self.top_menu_bar, fg_color="transparent")
        top_right_box.pack(side="right", padx=6, fill="y")

        notif_btn = ctk.CTkButton(
            top_right_box,
            text="🔔",
            width=24,
            height=20,
            corner_radius=2,
            fg_color="transparent",
            hover_color="#2a323d",
            font=get_mac_font(size=10)
        )
        notif_btn.pack(side="left", padx=2)

        spk_btn = ctk.CTkButton(
            top_right_box,
            text="📢",
            width=24,
            height=20,
            corner_radius=2,
            fg_color="transparent",
            hover_color="#2a323d",
            font=get_mac_font(size=10)
        )
        spk_btn.pack(side="left", padx=2)

        avatar_btn = ctk.CTkButton(
            top_right_box,
            text="🎮 ユーザー",
            width=70,
            height=20,
            corner_radius=2,
            fg_color="transparent",
            hover_color="#2a323d",
            text_color="#66c0f4",
            font=get_mac_font(size=10, weight="bold")
        )
        avatar_btn.pack(side="left", padx=4)

        # ============================================================
        # 2. メインナビゲーションバー (← → ストア ライブラリ コミュニティ)
        # ============================================================
        self.nav_bar = ctk.CTkFrame(
            self,
            height=44,
            corner_radius=0,
            fg_color="#171d25",
            border_width=1,
            border_color="#121418"
        )
        self.nav_bar.pack(fill="x", side="top")
        self.nav_bar.pack_propagate(False)

        # 左側: 戻る／進む ＆ メインナビタブ
        nav_left_box = ctk.CTkFrame(self.nav_bar, fg_color="transparent")
        nav_left_box.pack(side="left", padx=12, fill="y")

        back_btn = ctk.CTkButton(
            nav_left_box,
            text="←",
            width=28,
            height=28,
            corner_radius=4,
            fg_color="#1e232d",
            hover_color="#2a323d",
            text_color="#8f98a0",
            font=get_mac_font(size=12, weight="bold")
        )
        back_btn.pack(side="left", padx=(0, 2), pady=8)

        fwd_btn = ctk.CTkButton(
            nav_left_box,
            text="→",
            width=28,
            height=28,
            corner_radius=4,
            fg_color="#1e232d",
            hover_color="#2a323d",
            text_color="#8f98a0",
            font=get_mac_font(size=12, weight="bold")
        )
        fwd_btn.pack(side="left", padx=(0, 14), pady=8)

        # Steam主要タブ (ストア / ライブラリ / コミュニティ)
        store_tab = ctk.CTkLabel(
            nav_left_box,
            text="ストア",
            font=get_mac_font(size=13, weight="bold"),
            text_color="#8f98a0",
            cursor="hand2"
        )
        store_tab.pack(side="left", padx=12, pady=10)

        # ライブラリ（アクティブ・Steamブルー下線風）
        lib_tab_container = ctk.CTkFrame(nav_left_box, fg_color="transparent")
        lib_tab_container.pack(side="left", padx=12, fill="y")
        lib_tab = ctk.CTkLabel(
            lib_tab_container,
            text="ライブラリ",
            font=get_mac_font(size=14, weight="bold"),
            text_color="#ffffff"
        )
        lib_tab.pack(side="top", pady=(8, 2))
        lib_underline = ctk.CTkFrame(lib_tab_container, height=3, width=64, fg_color="#1a9fff", corner_radius=1)
        lib_underline.pack(side="bottom")

        comm_tab = ctk.CTkLabel(
            nav_left_box,
            text="コミュニティ",
            font=get_mac_font(size=13, weight="bold"),
            text_color="#8f98a0",
            cursor="hand2"
        )
        comm_tab.pack(side="left", padx=12, pady=10)

        user_tab = ctk.CTkLabel(
            nav_left_box,
            text="USER",
            font=get_mac_font(size=13, weight="bold"),
            text_color="#8f98a0",
            cursor="hand2"
        )
        user_tab.pack(side="left", padx=12, pady=10)

        # 右側ツールボタン群 (購入履歴同期, フォルダ管理, テーマ, 全画面)
        nav_right_box = ctk.CTkFrame(self.nav_bar, fg_color="transparent")
        nav_right_box.pack(side="right", padx=14, fill="y")

        self.import_btn = ctk.CTkButton(
            nav_right_box,
            text="📥 購入履歴同期",
            width=108,
            height=28,
            corner_radius=4,
            fg_color="#212b3b",
            hover_color="#2e3b52",
            text_color="#c7d5e0",
            border_width=1,
            border_color="#364560",
            font=get_mac_font(size=11, weight="bold"),
            command=self._open_purchase_importer
        )
        self.import_btn.pack(side="left", padx=4, pady=8)

        self.folder_btn = ctk.CTkButton(
            nav_right_box,
            text="📁 フォルダ管理",
            width=96,
            height=28,
            corner_radius=4,
            fg_color="#212b3b",
            hover_color="#2e3b52",
            text_color="#c7d5e0",
            border_width=1,
            border_color="#364560",
            font=get_mac_font(size=11, weight="bold"),
            command=self._open_folder_manager
        )
        self.folder_btn.pack(side="left", padx=4, pady=8)

        self.fullscreen_btn = ctk.CTkButton(
            nav_right_box,
            text="⛶ 全画面",
            width=76,
            height=28,
            corner_radius=4,
            fg_color="#1e232d",
            hover_color="#2a323d",
            text_color="#8f98a0",
            font=get_mac_font(size=11),
            command=self.toggle_fullscreen
        )
        self.fullscreen_btn.pack(side="left", padx=4, pady=8)

        self.theme_btn = ctk.CTkButton(
            nav_right_box,
            text="🌓",
            width=32,
            height=28,
            corner_radius=4,
            fg_color="#1e232d",
            hover_color="#2a323d",
            text_color="#c7d5e0",
            font=get_mac_font(size=12),
            command=self._toggle_theme
        )
        self.theme_btn.pack(side="left", padx=4, pady=8)

        # ============================================================
        # 3. 最下部ステータスバー (Steam Download Status Bar)
        # ============================================================
        self.footer_bar = ctk.CTkFrame(
            self,
            height=26,
            corner_radius=0,
            fg_color="#171a21",
            border_width=1,
            border_color="#121418"
        )
        self.footer_bar.pack(fill="x", side="bottom")
        self.footer_bar.pack_propagate(False)

        self.status_lbl = ctk.CTkLabel(
            self.footer_bar,
            text="⬇️ ダウンロード: 完了",
            font=get_mac_font(size=10),
            text_color="#66c0f4"
        )
        self.status_lbl.pack(side="left", padx=16)

        self.dnd_lbl = ctk.CTkLabel(
            self.footer_bar,
            text="👥 フレンド＆チャット (オンライン)",
            font=get_mac_font(size=10),
            text_color="#8f98a0",
            cursor="hand2"
        )
        self.dnd_lbl.pack(side="right", padx=16)

        # ============================================================
        # 4. 本体スプリットコンテナ (左サイドバー ＋ 右メインシェルフ)
        # ============================================================
        self.main_split = ctk.CTkFrame(
            self,
            corner_radius=0,
            fg_color="#171a21"
        )
        self.main_split.pack(fill="both", expand=True)

        # --- 左ペイン: Steam風ゲームリスト サイドバー (幅260px) ---
        self.sidebar_frame = ctk.CTkFrame(
            self.main_split,
            width=260,
            corner_radius=0,
            fg_color="#1e232d",
            border_width=1,
            border_color="#121418"
        )
        self.sidebar_frame.pack(side="left", fill="y")
        self.sidebar_frame.pack_propagate(False)

        # サイドバートップ: ホーム／コレクション アイコン ＆ 検索窓
        sb_top = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        sb_top.pack(fill="x", padx=10, pady=(10, 6))

        # アイコン行 (ホーム, コレクション, 時計)
        sb_icon_row = ctk.CTkFrame(sb_top, fg_color="transparent")
        sb_icon_row.pack(fill="x", pady=(0, 6))

        home_btn = ctk.CTkButton(
            sb_icon_row,
            text="🏠 ホーム",
            width=72,
            height=26,
            corner_radius=4,
            fg_color="#283444",
            hover_color="#364560",
            text_color="#ffffff",
            font=get_mac_font(size=10, weight="bold"),
            command=lambda: self._on_sidebar_filter_all()
        )
        home_btn.pack(side="left", padx=(0, 4))

        fav_btn = ctk.CTkButton(
            sb_icon_row,
            text="⭐ お気に入り",
            width=84,
            height=26,
            corner_radius=4,
            fg_color="#1e232d",
            hover_color="#283444",
            text_color="#c7d5e0",
            border_width=1,
            border_color="#2d3744",
            font=get_mac_font(size=10),
            command=lambda: self._on_platform_clicked("お気に入り")
        )
        fav_btn.pack(side="left")

        # 検索窓
        self.search_entry = ctk.CTkEntry(
            sb_top,
            placeholder_text="🔍 ゲームを検索...",
            placeholder_text_color="#626b77",
            text_color="#c7d5e0",
            fg_color="#171a21",
            border_color="#2a323d",
            border_width=1,
            height=30,
            corner_radius=4,
            font=get_mac_font(size=11)
        )
        self.search_entry.pack(fill="x")
        self.search_entry.bind("<KeyRelease>", self._on_search_changed)
        self.search_entry.bind("<Return>", self._on_search_enter)

        # サイドバー中央: スクロール可能なツリーリスト
        self.sidebar_scroll = ctk.CTkScrollableFrame(
            self.sidebar_frame,
            corner_radius=0,
            fg_color="#1e232d"
        )
        self.sidebar_scroll.pack(fill="both", expand=True, padx=4, pady=4)

        # サイドバー下部: 「＋ ゲームを追加」ボタン
        sb_bottom = ctk.CTkFrame(self.sidebar_frame, height=38, corner_radius=0, fg_color="#171a21")
        sb_bottom.pack(fill="x", side="bottom")
        sb_bottom.pack_propagate(False)

        self.add_app_btn = ctk.CTkButton(
            sb_bottom,
            text="＋ ゲームを追加",
            height=32,
            corner_radius=4,
            fg_color="transparent",
            hover_color="#283444",
            text_color="#8f98a0",
            font=get_mac_font(size=11, weight="bold"),
            anchor="w",
            command=self._open_add_dialog
        )
        self.add_app_btn.pack(fill="both", padx=10, pady=3)

        # --- 右ペイン: Steamシェルフ メインコンテンツ領域 ---
        self.scroll_canvas = ctk.CTkScrollableFrame(
            self.main_split,
            corner_radius=0,
            fg_color="#1b2838"  # Steam Classic Navy Blue
        )
        self.scroll_canvas.pack(fill="both", expand=True, padx=0, pady=0)

    def _on_sidebar_filter_all(self):
        self.current_platform = "すべて"
        self.current_genre = "すべて"
        self.refresh_games()

    def _on_sidebar_filter_genre(self, genre_name: str):
        self.current_platform = "すべて"
        self.current_genre = genre_name
        self.refresh_games()

    def _on_platform_clicked(self, plat_key: str):
        self.current_platform = plat_key
        self.current_genre = "すべて"
        if hasattr(self, "platform_buttons") and isinstance(self.platform_buttons, dict):
            for k, btn in self.platform_buttons.items():
                is_active = (k == plat_key)
                btn.configure(
                    fg_color="#3e316d" if is_active else "transparent",
                    hover_color="#4f3f8c" if is_active else "#221a47",
                    text_color="#ffffff" if is_active else "#9d98c2",
                    font=get_mac_font(size=11, weight="bold" if is_active else "normal")
                )
        self.refresh_games()

    def _refresh_sidebar(self):
        """左サイドバーのツリー状ゲームコレクション表示を更新"""
        if not hasattr(self, "sidebar_scroll"):
            return
        for w in self.sidebar_scroll.winfo_children():
            w.destroy()
        self.sidebar_item_widgets.clear()

        all_games = self.config_mgr.games

        # 1. お気に入りコレクション
        fav_games = [g for g in all_games if g.get("favorite", False) or g.get("icon_locked", False)]
        fav_games.sort(key=lambda x: x.get("name", "").lower())
        if fav_games:
            fav_hdr = ctk.CTkFrame(self.sidebar_scroll, fg_color="transparent", height=24)
            fav_hdr.pack(fill="x", padx=4, pady=(6, 2))
            ctk.CTkLabel(
                fav_hdr,
                text=f"▼ ⭐ お気に入り ({len(fav_games)})",
                font=get_mac_font(size=10, weight="bold"),
                text_color="#66c0f4",
                anchor="w"
            ).pack(side="left", padx=2)

            for g in fav_games:
                self._create_sidebar_game_item(self.sidebar_scroll, g)

        # 2. ジャンル別コレクション
        genre_map: Dict[str, List[Dict[str, Any]]] = {}
        for g in all_games:
            gen = g.get("genre") or g.get("category") or "その他"
            if gen in ["ゲーム", "download"]:
                gen = "その他"
            genre_map.setdefault(gen, []).append(g)

        # メインジャンルの優先順
        genre_order = ["ロールプレイング", "アクション", "アドベンチャー", "シミュレーション", "パズル", "その他"]
        sorted_genres = [gn for gn in genre_order if gn in genre_map]
        for gn in sorted(genre_map.keys()):
            if gn not in sorted_genres:
                sorted_genres.append(gn)

        for gn in sorted_genres:
            g_list = genre_map[gn]
            g_list.sort(key=lambda x: x.get("name", "").lower())

            hdr = ctk.CTkButton(
                self.sidebar_scroll,
                text=f"▼ 📁 {gn} ({len(g_list)})",
                font=get_mac_font(size=10, weight="bold"),
                text_color="#c7d5e0" if self.current_genre == gn else "#8f98a0",
                fg_color="#212b3b" if self.current_genre == gn else "transparent",
                hover_color="#283444",
                anchor="w",
                height=22,
                corner_radius=2,
                command=lambda gn_name=gn: self._on_sidebar_filter_genre(gn_name)
            )
            hdr.pack(fill="x", padx=2, pady=(4, 1))

            for g in g_list:
                self._create_sidebar_game_item(self.sidebar_scroll, g)

    def _create_sidebar_game_item(self, parent, game: Dict[str, Any]):
        g_name = game.get("name", "Game")
        g_item = ctk.CTkButton(
            parent,
            text=f"  • {g_name}",
            font=get_mac_font(size=10),
            text_color="#8f98a0",
            hover_color="#283444",
            fg_color="transparent",
            anchor="w",
            height=20,
            corner_radius=2,
            command=lambda g=game: self._launch_game(g)
        )
        g_item.pack(fill="x", padx=(10, 2), pady=0)
        g_item.bind("<Button-3>", lambda e, g=game: self._show_context_menu(e, g))
        self.sidebar_item_widgets.append(g_item)


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
        """Steam公式UIスタイル（最近プレイシェルフ ＋ 全ゲームシェルフ ＋ 左サイドバー連動）の描画"""
        for w in self.scroll_canvas.winfo_children():
            w.destroy()

        self.card_widgets.clear()
        self._refresh_sidebar()

        filtered = self._get_filtered_games()
        self.grouped_games = GameAnalyzer.group_identical_games(self.config_mgr.games)
        self.status_lbl.configure(text=f"⬇️ ライブラリ: 全 {len(self.config_mgr.games)} 作品 (表示中: {len(filtered)} 件)")

        canvas_w = self.scroll_canvas.winfo_width()
        if canvas_w < 500:
            canvas_w = max(800, self.winfo_width() - 280)

        cols = max(3, canvas_w // 205)
        is_searching = bool(self.search_query.strip())

        # ============================================================
        # シェルフ 1: 最近のプレイ (Steam Recent Shelf)
        # ============================================================
        if not is_searching and self.current_platform == "すべて" and self.current_genre == "すべて":
            recent_games = [g for g in self.config_mgr.games if g.get("last_launched")]
            recent_games.sort(key=lambda x: x.get("last_launched", 0), reverse=True)
            if not recent_games:
                recent_games = self.config_mgr.games[:4]
            else:
                recent_games = recent_games[:4]

            if recent_games:
                sec1_header = ctk.CTkFrame(self.scroll_canvas, fg_color="transparent")
                sec1_header.pack(fill="x", padx=16, pady=(16, 8))

                ctk.CTkLabel(
                    sec1_header,
                    text="最近のプレイ",
                    font=get_mac_font(size=14, weight="bold"),
                    text_color="#c7d5e0"
                ).pack(side="left")

                sec1_row = ctk.CTkFrame(self.scroll_canvas, fg_color="transparent")
                sec1_row.pack(fill="x", padx=12, pady=(0, 20))

                recent_cols = min(len(recent_games), cols)
                for c in range(recent_cols):
                    sec1_row.grid_columnconfigure(c, weight=1)

                for idx, r_game in enumerate(recent_games[:recent_cols]):
                    self._create_recent_card(sec1_row, r_game, 0, idx)

        # ============================================================
        # シェルフ 2: すべてのゲーム / 検索結果 / ジャンル別
        # ============================================================
        sec2_header = ctk.CTkFrame(self.scroll_canvas, fg_color="transparent")
        sec2_header.pack(fill="x", padx=16, pady=(8, 8))

        # Steam風ヘッダータイトル
        if is_searching:
            header_title = f"検索結果 ({len(filtered)})"
        elif self.current_genre != "すべて":
            header_title = f"{self.current_genre} ({len(filtered)})"
        elif self.current_platform == "お気に入り":
            header_title = f"お気に入り ({len(filtered)})"
        else:
            header_title = f"すべてのゲーム ({len(filtered)})"

        ctk.CTkLabel(
            sec2_header,
            text=header_title,
            font=get_mac_font(size=14, weight="bold"),
            text_color="#c7d5e0"
        ).pack(side="left")

        # 右側コントロール (並び替え / フィルター)
        sec2_controls = ctk.CTkFrame(sec2_header, fg_color="transparent")
        sec2_controls.pack(side="right")

        ctk.CTkLabel(
            sec2_controls,
            text="並び替え:",
            font=get_mac_font(size=11),
            text_color="#8f98a0"
        ).pack(side="left", padx=(0, 6))

        sort_menu = ctk.CTkOptionMenu(
            sec2_controls,
            values=["作品名 (昇順)", "最近プレイした順", "作者・サークル名 (昇順)", "登録順"],
            width=150,
            height=26,
            corner_radius=4,
            fg_color="#1e232d",
            button_color="#283444",
            button_hover_color="#364560",
            dropdown_fg_color="#1e232d",
            dropdown_hover_color="#283444",
            dropdown_text_color="#c7d5e0",
            text_color="#c7d5e0",
            font=get_mac_font(size=11),
            command=self._on_sort_changed
        )
        sort_menu.set(self.sort_order if self.sort_order in ["作品名 (昇順)", "最近プレイした順", "作者・サークル名 (昇順)", "登録順"] else "作品名 (昇順)")
        sort_menu.pack(side="left")

        # 0件表示
        if not filtered:
            empty_box = ctk.CTkFrame(self.scroll_canvas, fg_color="transparent")
            empty_box.pack(pady=60)
            ctk.CTkLabel(
                empty_box,
                text="該当するゲームがありません",
                font=get_mac_font(size=15, weight="bold"),
                text_color="#8f98a0"
            ).pack()
            ctk.CTkLabel(
                empty_box,
                text="検索条件を変更するか、右上の「📥 購入履歴同期」または「＋ ゲームを追加」から登録してください。",
                font=get_mac_font(size=11),
                text_color="#626b77"
            ).pack(pady=6)
            return

        # グリッドコンテナ
        grid_container = ctk.CTkFrame(self.scroll_canvas, fg_color="transparent")
        grid_container.pack(fill="both", expand=True, padx=12, pady=(0, 24))

        for c in range(cols):
            grid_container.grid_columnconfigure(c, weight=1)

        for idx, game in enumerate(filtered):
            row = idx // cols
            col = idx % cols
            self._create_game_tile(grid_container, game, row, col)

    def _create_recent_card(self, parent, game: Dict[str, Any], row: int, col: int):
        """「最近のプレイ」用ワイドSteamカード"""
        game_id = game.get("id")

        card = ctk.CTkFrame(
            parent,
            corner_radius=4,
            fg_color="#131923",
            border_width=1,
            border_color="#212b3b"
        )
        card.grid(row=row, column=col, padx=6, pady=4, sticky="nsew")

        # ワイドジャケット画像 (200x125)
        ctk_img = self._get_ctk_image(game, target_size=(200, 125))

        img_frame = ctk.CTkFrame(card, corner_radius=2, fg_color="#0a0d14")
        img_frame.pack(padx=6, pady=(6, 6), fill="x")

        icon_btn = ctk.CTkButton(
            img_frame,
            image=ctk_img,
            text="",
            height=125,
            corner_radius=2,
            fg_color="transparent",
            hover_color="#1b2838",
            command=lambda g=game: self._launch_game(g)
        )
        icon_btn.pack(fill="both", expand=True)

        # ゲームタイトル
        name = game.get("name", "Game")
        name_lbl = ctk.CTkLabel(
            card,
            text=name,
            font=get_mac_font(size=11, weight="bold"),
            text_color="#c7d5e0",
            wraplength=188,
            justify="left",
            anchor="w",
            cursor="hand2"
        )
        name_lbl.pack(padx=8, pady=(0, 2), fill="x")
        name_lbl.bind("<Button-1>", lambda e, g=game: self._launch_game(g))

        # サークル/作者名
        author_text = game.get("author", "不明")
        author_lbl = ctk.CTkLabel(
            card,
            text=author_text,
            font=get_mac_font(size=10),
            text_color="#8f98a0",
            wraplength=188,
            justify="left",
            anchor="w"
        )
        author_lbl.pack(padx=8, pady=(0, 6), fill="x")

        # Steamグリーンプレイボタン
        is_installed = game.get("is_installed", True if game.get("path") else False)
        if is_installed:
            play_btn = ctk.CTkButton(
                card,
                text="▶ プレイ",
                height=26,
                corner_radius=2,
                fg_color="#5c7e10",
                hover_color="#78a317",
                text_color="#ffffff",
                font=get_mac_font(size=11, weight="bold"),
                command=lambda g=game: self._launch_game(g)
            )
        else:
            play_btn = ctk.CTkButton(
                card,
                text="⬇️ ダウンロード",
                height=26,
                corner_radius=2,
                fg_color="#1a9fff",
                hover_color="#3dafff",
                text_color="#ffffff",
                font=get_mac_font(size=11, weight="bold"),
                command=lambda g=game: self._open_store_page(g)
            )
        play_btn.pack(fill="x", padx=8, pady=(0, 8))

        self._bind_card_hover(card, [img_frame, icon_btn, name_lbl, author_lbl])
        for w in [card, img_frame, icon_btn, name_lbl, author_lbl]:
            w.bind("<Button-3>", lambda e, g=game: self._show_context_menu(e, g))

    def _create_game_tile(self, parent, game: Dict[str, Any], row: int, col: int):
        """Steamポスターグリッド用ゲームカード"""
        game_id = game.get("id")

        card = ctk.CTkFrame(
            parent,
            corner_radius=4,
            fg_color="#131923",
            border_width=1,
            border_color="#212b3b"
        )
        card.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")

        # ジャケット画像フレーム (180x120)
        img_container = ctk.CTkFrame(card, corner_radius=2, fg_color="#0a0d14")
        img_container.pack(padx=6, pady=(6, 4), fill="x")

        ctk_img = self._get_ctk_image(game, target_size=(180, 120))

        icon_btn = ctk.CTkButton(
            img_container,
            image=ctk_img,
            text="",
            height=120,
            corner_radius=2,
            fg_color="transparent",
            hover_color="#1b2838",
            command=lambda g=game: self._launch_game(g)
        )
        icon_btn.pack(fill="both", expand=True)

        # 作品名 (2行制限 wrap)
        name = game.get("name", "Game")
        name_lbl = ctk.CTkLabel(
            card,
            text=name,
            font=get_mac_font(size=11, weight="bold"),
            text_color="#c7d5e0",
            wraplength=170,
            justify="left",
            anchor="w",
            cursor="hand2"
        )
        name_lbl.pack(padx=8, pady=(2, 2), fill="x")
        name_lbl.bind("<Button-1>", lambda e, g=game: self._launch_game(g))

        # 作者 / サークル名
        author_text = game.get("author", "不明")
        author_lbl = ctk.CTkLabel(
            card,
            text=author_text,
            font=get_mac_font(size=10),
            text_color="#8f98a0",
            wraplength=170,
            justify="left",
            anchor="w"
        )
        author_lbl.pack(padx=8, pady=(0, 4), fill="x")

        # アクションバー: プレイ/ダウンロード ＋ フォルダボタン
        action_bar = ctk.CTkFrame(card, fg_color="transparent")
        action_bar.pack(fill="x", padx=8, pady=(0, 8))

        is_installed = game.get("is_installed", True if game.get("path") else False)
        if is_installed:
            play_btn = ctk.CTkButton(
                action_bar,
                text="▶ プレイ",
                height=26,
                corner_radius=2,
                fg_color="#5c7e10",
                hover_color="#78a317",
                text_color="#ffffff",
                font=get_mac_font(size=10, weight="bold"),
                command=lambda g=game: self._launch_game(g)
            )
            play_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))

            folder_btn = ctk.CTkButton(
                action_bar,
                text="📂",
                width=28,
                height=26,
                corner_radius=2,
                fg_color="#1e232d",
                hover_color="#283444",
                text_color="#8f98a0",
                command=lambda g=game: self._open_game_folder(g)
            )
            folder_btn.pack(side="right")
        else:
            dl_btn = ctk.CTkButton(
                action_bar,
                text="⬇️ ダウンロード",
                height=26,
                corner_radius=2,
                fg_color="#1a9fff",
                hover_color="#3dafff",
                text_color="#ffffff",
                font=get_mac_font(size=10, weight="bold"),
                command=lambda g=game: self._open_store_page(g)
            )
            dl_btn.pack(fill="x")

        # ホバーエフェクト
        self._bind_card_hover(card, [img_container, icon_btn, name_lbl, author_lbl])

        # 右クリックメニュー
        for w in [card, img_container, icon_btn, name_lbl, author_lbl]:
            w.bind("<Button-3>", lambda e, g=game: self._show_context_menu(e, g))

        self.card_widgets[game_id] = {
            "card": card,
            "icon_btn": icon_btn,
            "game": game
        }

    def _bind_card_hover(self, card, inner_widgets):
        def on_enter(e):
            card.configure(fg_color="#1c2533", border_color="#364560")
        def on_leave(e):
            card.configure(fg_color="#131923", border_color="#212b3b")

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
