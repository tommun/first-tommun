import os
import sys
import time
import subprocess
import threading
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

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class ModernLauncherApp(ctk.CTk):
    """DLsite Sound スタイル (Image 2 準拠) ＋ 全画面対応 ＋ レスポンシブグリッド exeランチャー"""

    def __init__(self):
        super().__init__()

        self.config_mgr = ConfigManager()
        self.icon_helper = IconHelper()

        self.title("🎵 GameLauncher - DLsite Sound Style")
        window_w = self.config_mgr.config.get("settings", {}).get("window_width", 1200)
        window_h = self.config_mgr.config.get("settings", {}).get("window_height", 800)
        self.geometry(f"{window_w}x{window_h}")
        self.minsize(840, 560)
        self.configure(fg_color="#09071a")  # DLsite Sound Midnight Dark

        # 状態変数
        self.is_fullscreen = False
        self.current_nav = "ライブラリ"    # "今すぐ遊ぶ", "ライブラリ", "お気に入り"
        self.current_category = "すべて"
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

        # 左側: ロゴ ＆ リアルタイム検索バー
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
        logo_lbl.pack(side="left", padx=(0, 16), pady=20)

        self.search_entry = ctk.CTkEntry(
            left_box,
            placeholder_text="🔍 作品名・作者・サークル名で検索...",
            placeholder_text_color="#737099",
            text_color="#ffffff",
            fg_color="#171233",
            border_color="#2c2357",
            border_width=1,
            width=280,
            height=36,
            corner_radius=18,
            font=get_mac_font(size=11)
        )
        self.search_entry.pack(side="left", pady=16)
        self.search_entry.bind("<KeyRelease>", self._on_search_changed)
        self.search_entry.bind("<Return>", self._on_search_enter)

        # 中央: DLsite Sound カプセルナビゲーションバー (Image 2 トップバー再現)
        self.center_nav_frame = ctk.CTkFrame(
            self.header_frame,
            height=40,
            corner_radius=20,
            fg_color="#151030",
            border_width=1,
            border_color="#2b2257"
        )
        self.center_nav_frame.pack(side="left", expand=True, pady=14)

        self.nav_buttons = {}
        nav_items = [
            ("今すぐ遊ぶ", "🎮 今すぐ遊ぶ"),
            ("ライブラリ", "📚 ライブラリ"),
            ("お気に入り", "⭐ お気に入り"),
        ]

        for nav_key, label in nav_items:
            is_active = (self.current_nav == nav_key)
            btn = ctk.CTkButton(
                self.center_nav_frame,
                text=label,
                width=110,
                height=32,
                corner_radius=16,
                fg_color="#3e316d" if is_active else "transparent",
                hover_color="#4f3f8c" if is_active else "#221a47",
                text_color="#ffffff" if is_active else "#9d98c2",
                font=get_mac_font(size=11, weight="bold" if is_active else "normal"),
                command=lambda k=nav_key: self._on_nav_clicked(k)
            )
            btn.pack(side="left", padx=3, pady=4)
            self.nav_buttons[nav_key] = btn

        # 右側: ツールボタン群 (全画面, 最適化, 追加, フォルダ, テーマ)
        right_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        right_box.pack(side="right", padx=(10, 18), fill="y")

        self.fullscreen_btn = ctk.CTkButton(
            right_box,
            text="⛶ 全画面",
            width=84,
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
        self.fullscreen_btn.pack(side="left", padx=4, pady=17)

        self.optimize_btn = ctk.CTkButton(
            right_box,
            text="✨ サムネ最適化",
            width=108,
            height=34,
            corner_radius=17,
            fg_color="#241e4f",
            hover_color="#352c73",
            text_color="#9dc2f8",
            border_width=1,
            border_color="#3e337d",
            font=get_mac_font(size=11, weight="bold"),
            command=self._trigger_optimize_now
        )
        self.optimize_btn.pack(side="left", padx=4, pady=17)

        self.add_app_btn = ctk.CTkButton(
            right_box,
            text="＋ 追加",
            width=76,
            height=34,
            corner_radius=17,
            fg_color="#3a86ff",
            hover_color="#2b68cb",
            text_color="#ffffff",
            font=get_mac_font(size=12, weight="bold"),
            command=self._open_add_dialog
        )
        self.add_app_btn.pack(side="left", padx=4, pady=17)

        self.folder_btn = ctk.CTkButton(
            right_box,
            text="📁 フォルダ",
            width=90,
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
        self.folder_btn.pack(side="left", padx=4, pady=17)

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
        self.theme_btn.pack(side="left", padx=4, pady=17)

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
            text="※ [F11] で全画面表示切り替え | exeやフォルダのドラッグ＆ドロップ登録に対応",
            font=get_mac_font(size=11),
            text_color="#737099"
        )
        self.dnd_lbl.pack(side="right", padx=16)

    def _on_nav_clicked(self, nav_key: str):
        self.current_nav = nav_key
        for k, btn in self.nav_buttons.items():
            is_active = (k == nav_key)
            btn.configure(
                fg_color="#3e316d" if is_active else "transparent",
                hover_color="#4f3f8c" if is_active else "#221a47",
                text_color="#ffffff" if is_active else "#9d98c2",
                font=get_mac_font(size=11, weight="bold" if is_active else "normal")
            )
        if nav_key == "お気に入り":
            self.current_category = "お気に入り"
        elif nav_key in ["今すぐ遊ぶ", "ライブラリ"]:
            if self.current_category == "お気に入り":
                self.current_category = "すべて"
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

            if p.is_dir():
                found = FolderScanner.scan_library_folder(str(p), default_category="ゲーム")
                if found:
                    for item in found:
                        self.config_mgr.add_or_update_game(item)
                    self.refresh_games()
                    messagebox.showinfo("登録完了", f"フォルダから {len(found)} 件のゲームを登録しました！")
                    break
                else:
                    messagebox.showinfo("通知", f"フォルダ「{p.name}」内に実行可能ファイルが見つかりませんでした。")
            elif p.is_file() and p.suffix.lower() in [".exe", ".lnk"]:
                game_data = {
                    "name": p.stem,
                    "path": str(p),
                    "work_dir": str(p.parent),
                    "folder_path": str(p.parent),
                    "category": self.current_category if self.current_category != "すべて" else "ゲーム",
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
                cat_name = "ゲーム" if "ゲーム" in folder else "download"
                detected = FolderScanner.scan_library_folder(folder, default_category=cat_name)
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
                        if (not existing.get("author") or existing.get("author") == "不明") and item.get("author") and item.get("author") != "不明":
                            existing["author"] = item["author"]
                            changed = True
                        if changed:
                            self.config_mgr.save()
            self.after(0, lambda: self._on_background_scan_done(new_count))

        threading.Thread(target=worker, daemon=True).start()

    def _on_background_scan_done(self, new_count: int):
        self.status_lbl.configure(text=f"自動スキャン完了: {len(self.config_mgr.games)} 件登録中", text_color="#2b7a4b")
        for f in self.config_mgr.scan_folders:
            cat_name = "ゲーム" if "ゲーム" in f else "download"
            self.config_mgr.add_category(cat_name)
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

    def _select_category(self, cat: str):
        self.current_category = cat
        self.refresh_games()

    def _get_filtered_games(self) -> List[Dict[str, Any]]:
        all_games = self.config_mgr.games
        filtered = []

        for g in all_games:
            # 1. カテゴリ絞り込み
            if self.current_category != "すべて":
                if self.current_category == "お気に入り":
                    if not g.get("favorite", False) and not g.get("icon_locked", False):
                        continue
                else:
                    if g.get("category") != self.current_category:
                        continue

            # 2. 作者・サークル絞り込み
            if self.current_author != "すべての作者・サークル":
                g_author = g.get("author", "不明")
                if g_author != self.current_author:
                    continue

            # 3. リアルタイム検索クエリ絞り込み
            if self.search_query:
                name = g.get("name", "").lower()
                author = g.get("author", "").lower()
                path = g.get("path", "").lower()
                rj = (g.get("rj_code") or "").lower()
                if (self.search_query not in name and 
                    self.search_query not in author and 
                    self.search_query not in path and 
                    self.search_query not in rj):
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
        """キャッシュ済みのCTkImageを再利用、なければ生成して保持"""
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
        """DLsite Sound スタイル (Image 2) のセクション構成 ＋ 全画面レスポンシブグリッドを再描画"""
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

        # 列幅 約210px + 余白による動的カラム計算（全画面・最大化で右側に余白を残さず埋める）
        cols = max(3, canvas_w // 210)

        # 検索中ではない時のみ「最近プレイした作品」および「ジャンル」セクションを表示
        is_searching = bool(self.search_query.strip())

        if not is_searching and self.current_nav in ["今すぐ遊ぶ", "ライブラリ"]:
            # ============================================================
            # セクション 1: 最近聴いた作品 / 最近プレイした作品 〉
            # ============================================================
            recent_games = [g for g in self.config_mgr.games if g.get("last_launched")]
            recent_games.sort(key=lambda x: x.get("last_launched", 0), reverse=True)
            if not recent_games:
                # まだ起動履歴がない場合は先頭作品をフィーチャー表示
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
            # セクション 2: ジャンル / カテゴリ 〉
            # ============================================================
            sec2_header = ctk.CTkFrame(self.scroll_canvas, fg_color="transparent")
            sec2_header.pack(fill="x", padx=10, pady=(6, 10))

            ctk.CTkLabel(
                sec2_header,
                text="ジャンル 〉",
                font=get_mac_font(size=17, weight="bold"),
                text_color="#ffffff"
            ).pack(side="left")

            genre_row = ctk.CTkFrame(self.scroll_canvas, fg_color="transparent")
            genre_row.pack(fill="x", padx=6, pady=(0, 24))

            categories = self.config_mgr.categories
            for idx, cat in enumerate(categories):
                is_active = (cat == self.current_category)
                genre_card = ctk.CTkButton(
                    genre_row,
                    text=cat,
                    width=135,
                    height=52,
                    corner_radius=14,
                    fg_color="#362963" if is_active else "#161133",
                    hover_color="#493885" if is_active else "#241c52",
                    border_width=2 if is_active else 1,
                    border_color="#77aaf6" if is_active else "#2d245c",
                    text_color="#ffffff" if is_active else "#c0bcd9",
                    font=get_mac_font(size=13, weight="bold"),
                    command=lambda c=cat: self._select_category(c)
                )
                genre_card.pack(side="left", padx=6, pady=4)

        # ============================================================
        # セクション 3: すべての作品 / 最近の購入 / ライブラリグリッド 〉
        # ============================================================
        sec3_header = ctk.CTkFrame(self.scroll_canvas, fg_color="transparent")
        sec3_header.pack(fill="x", padx=10, pady=(6, 12))

        # タイトル
        title_text = f"すべての作品 〉 ({len(filtered)}件)"
        if self.current_category != "すべて":
            title_text = f"「{self.current_category}」の作品 〉 ({len(filtered)}件)"
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
                text="一致するゲームがありません",
                font=get_mac_font(size=16, weight="bold"),
                text_color="gray60"
            ).pack()
            ctk.CTkLabel(
                empty_box,
                text="「＋ 追加」または「フォルダ管理」からゲームを追加してください。",
                font=get_mac_font(size=12),
                text_color="gray50"
            ).pack(pady=5)
            return

        # レスポンシブグリッドコンテナ（画面幅いっぱいに列ウェイトを設定）
        grid_container = ctk.CTkFrame(self.scroll_canvas, fg_color="transparent")
        grid_container.pack(fill="both", expand=True, padx=4, pady=(0, 20))

        for c in range(cols):
            grid_container.grid_columnconfigure(c, weight=1)

        for idx, game in enumerate(filtered):
            row = idx // cols
            col = idx % cols
            self._create_game_tile(grid_container, game, row, col)

    def _create_recent_card(self, parent, game: Dict[str, Any], row: int, col: int):
        """「最近プレイした作品」用の大型ワイドジャケットカード (Image 2 上段再現)"""
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

        # 作者・サークル名
        author_text = game.get("author", "不明")
        author_lbl = ctk.CTkLabel(
            card,
            text=author_text,
            font=get_mac_font(size=10),
            text_color="#8d89b0",
            wraplength=190,
            justify="left",
            anchor="w"
        )
        author_lbl.pack(padx=10, pady=(0, 10), fill="x")

        # ホバーエフェクト
        self._bind_card_hover(card, [img_frame, icon_btn, name_lbl, author_lbl])
        for w in [card, img_frame, icon_btn, name_lbl, author_lbl]:
            w.bind("<Button-3>", lambda e, g=game: self._show_context_menu(e, g))

    def _create_game_tile(self, parent, game: Dict[str, Any], row: int, col: int):
        """グリッド内のDLsite Soundジャケットカード (Image 2 下段再現)"""
        game_id = game.get("id")

        # カードフレーム (DLsite Sound midnight #13102b, 微細な夜空境界線 #241e4d)
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

        # バッジバー (サムネ確定 ＆ 重複)
        badge_bar = ctk.CTkFrame(card, fg_color="transparent", height=22)
        badge_bar.pack(fill="x", padx=8, pady=(2, 2))

        is_locked = game.get("icon_locked", False)
        lock_btn = ctk.CTkButton(
            badge_bar,
            text="🔒 確定" if is_locked else "✨ 自動探索",
            width=68,
            height=18,
            corner_radius=9,
            fg_color="#1b7a32" if is_locked else "#1a1538",
            hover_color="#239a40" if is_locked else "#26204f",
            text_color="#ffffff" if is_locked else "#77aaf6",
            border_width=0 if is_locked else 1,
            border_color="#362c6e",
            font=get_mac_font(size=9, weight="bold"),
            command=lambda g=game: self._toggle_icon_lock(g)
        )
        lock_btn.pack(side="left")

        if group_key:
            dup_count = len(self.grouped_games[group_key])
            dup_btn = ctk.CTkButton(
                badge_bar,
                text=f"🔁 重複 {dup_count}",
                width=64,
                height=18,
                corner_radius=9,
                fg_color="#9e6d00",
                hover_color="#b88002",
                text_color="#ffffff",
                font=get_mac_font(size=9, weight="bold"),
                command=lambda k=group_key: self._open_comparison_dialog(k)
            )
            dup_btn.pack(side="right")

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

        # 作者・サークル名
        author_text = game.get("author", "不明")
        author_lbl = ctk.CTkLabel(
            card,
            text=author_text,
            font=get_mac_font(size=10),
            text_color="#8d89b0",
            wraplength=180,
            justify="left",
            anchor="w"
        )
        author_lbl.pack(padx=8, pady=(0, 4), fill="x")

        # フォルダを開くボタン (DLsite Sound 洗練された小型ピル)
        folder_btn = ctk.CTkButton(
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
        folder_btn.pack(pady=(2, 8))

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
        """カード全体にマウスホバー時の発光フィードバックを付与"""
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

        # キャッシュのクリア
        for key in list(self.card_images.keys()):
            if key.startswith(f"{game_id}_"):
                del self.card_images[key]

        if game_id in self.card_widgets:
            new_img = self._get_ctk_image(updated_game, target_size=(180, 125))
            if new_img and "icon_btn" in self.card_widgets[game_id]:
                self.card_widgets[game_id]["icon_btn"].configure(image=new_img)
                self.status_lbl.configure(text=f"✨ サムネイルを最適化しました: {updated_game.get('name')}", text_color="#4361ee")

    def _trigger_optimize_now(self):
        self.status_lbl.configure(text="✨ 最適なサムネイルをバックグラウンド探索中...", text_color="#4361ee")
        threading.Thread(target=self._optimize_all_worker, daemon=True).start()

    def _optimize_all_worker(self):
        improved_count = 0
        for game in self.config_mgr.games:
            cur_q = game.get("icon_quality", 0)
            if cur_q < QUALITY_DLSITE_OFFICIAL:
                new_path, new_q = self.icon_helper.resolve_best_thumbnail(game, allow_web_search=True)
                if new_q > cur_q:
                    game["icon_path"] = new_path
                    game["icon_quality"] = new_q
                    improved_count += 1
                    self.after(0, lambda g=game: self._apply_improved_icon(g))
        self.after(0, lambda: self.status_lbl.configure(text=f"✨ 最適化完了: {improved_count} 件のサムネイルを更新しました", text_color="#2b7a4b"))

    def _toggle_icon_lock(self, game: Dict[str, Any]):
        cur = game.get("icon_locked", False)
        game["icon_locked"] = not cur
        self.config_mgr.save()
        game_id = game.get("id")
        if game_id in self.card_widgets and "lock_btn" in self.card_widgets[game_id]:
            is_locked = game["icon_locked"]
            self.card_widgets[game_id]["lock_btn"].configure(
                text="🔒 確定" if is_locked else "✨ 自動探索",
                fg_color="#1b7a32" if is_locked else "#1a1538",
                hover_color="#239a40" if is_locked else "#26204f",
                text_color="#ffffff" if is_locked else "#77aaf6",
                border_width=0 if is_locked else 1,
                border_color="#362c6e"
            )
        status_msg = "🔒 サムネイルを確定しました" if game["icon_locked"] else "✨ サムネイル自動最適化を再開しました"
        self.status_lbl.configure(text=f"{status_msg}: {game.get('name')}", text_color="#77aaf6" if game['icon_locked'] else "#4361ee")

    def _show_context_menu(self, event, game: Dict[str, Any]):
        menu = tk.Menu(self, tearoff=0, font=(get_mac_font_family(), 10))
        menu.add_command(label="▶ 起動する", command=lambda: self._launch_game(game))
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
        menu.add_command(label="✏️ 情報を編集", command=lambda: self._open_edit_dialog(game))
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

            # 起動履歴の記録（DLsite Sound 最近プレイした作品 への自動反映）
            game["last_launched"] = time.time()
            game["play_count"] = game.get("play_count", 0) + 1
            self.config_mgr.save()

            self.status_lbl.configure(text=f"起動しました: {game.get('name')}", text_color="#2b7a4b")
        except Exception as e:
            messagebox.showerror("起動エラー", f"起動に失敗しました:\n{e}")

    def _open_game_folder(self, game: Dict[str, Any]):
        folder = game.get("folder_path") or os.path.dirname(game.get("path", ""))
        if os.path.exists(folder):
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
