import os
import sys
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
from typing import List, Dict, Any, Optional

import customtkinter as ctk
from PIL import Image

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
    """Mac準拠デザイン ＋ リアルタイム検索 ＋ 継続的サムネイル最適化 exeランチャー"""

    def __init__(self):
        super().__init__()

        self.config_mgr = ConfigManager()
        self.icon_helper = IconHelper()

        self.title("🎵 GameLauncher - DLsite Sound Style")
        window_w = self.config_mgr.config.get("settings", {}).get("window_width", 1140)
        window_h = self.config_mgr.config.get("settings", {}).get("window_height", 760)
        self.geometry(f"{window_w}x{window_h}")
        self.minsize(840, 520)
        self.configure(fg_color="#080617")  # DLsite Sound Midnight Dark

        # 状態変数
        self.current_category = "すべて"
        self.current_author = "すべての作者・サークル"
        self.search_query = ""
        self.sort_order = "作品名 (昇順)"  # 作品名 (昇順), 作者・サークル名 (昇順), 登録順
        self.card_images = {}      # CTkImageのキャッシュ保持用
        self.card_widgets = {}     # game_id -> {"card": card, "btn": icon_btn}
        self.grouped_games = {}    # 同一ゲームのグループ情報

        self._build_ui()
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

    def _build_ui(self):
        # 1. 最上部ヘッダー (DLsite Sound midnight bar with subtle border)
        self.header_frame = ctk.CTkFrame(
            self,
            height=68,
            corner_radius=0,
            fg_color="#100e24",
            border_width=1,
            border_color="#1f1b40"
        )
        self.header_frame.pack(fill="x", side="top")

        # タイトルロゴ（DLsite Sound / Mac風モダンラウンドタイポグラフィ）
        logo_container = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        logo_container.pack(side="left", padx=(20, 10))

        logo_badge = ctk.CTkLabel(
            logo_container,
            text="SOUND",
            font=get_mac_font(size=9, weight="bold"),
            text_color="#080617",
            fg_color="#77aaf6",
            corner_radius=4,
            width=46,
            height=18
        )
        logo_badge.pack(side="left", padx=(0, 8))

        logo_lbl = ctk.CTkLabel(
            logo_container,
            text="GameLauncher",
            font=get_mac_font(size=18, weight="bold"),
            text_color="#ffffff"
        )
        logo_lbl.pack(side="left")

        # リアルタイム検索バー（DLsite Sound ピル型検索バー）
        self.search_entry = ctk.CTkEntry(
            self.header_frame,
            placeholder_text="🔍 作品名・作者・サークル名で検索... (Enterで即起動)",
            placeholder_text_color="#737099",
            text_color="#ffffff",
            fg_color="#181533",
            border_color="#2c2858",
            border_width=1,
            width=360,
            height=38,
            corner_radius=19,
            font=get_mac_font(size=12)
        )
        self.search_entry.pack(side="left", padx=15, fill="x", expand=True)
        self.search_entry.bind("<KeyRelease>", self._on_search_changed)
        self.search_entry.bind("<Return>", self._on_search_enter)

        # アクションボタン群 (DLsite Sound ネオンブルー/エメラルド/スレート)
        btn_container = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        btn_container.pack(side="right", padx=15)

        self.optimize_btn = ctk.CTkButton(
            btn_container,
            text="✨ サムネ最適化",
            width=110,
            height=34,
            corner_radius=17,
            fg_color="#2c2759",
            hover_color="#3a3473",
            text_color="#77aaf6",
            border_width=1,
            border_color="#453e8c",
            font=get_mac_font(size=11, weight="bold"),
            command=self._trigger_optimize_now
        )
        self.optimize_btn.pack(side="left", padx=4)

        self.add_app_btn = ctk.CTkButton(
            btn_container,
            text="＋ 追加",
            width=80,
            height=34,
            corner_radius=17,
            fg_color="#3a86ff",
            hover_color="#2b68cb",
            text_color="#ffffff",
            font=get_mac_font(size=12, weight="bold"),
            command=self._open_add_dialog
        )
        self.add_app_btn.pack(side="left", padx=4)

        self.folder_btn = ctk.CTkButton(
            btn_container,
            text="📁 フォルダ管理",
            width=114,
            height=34,
            corner_radius=17,
            fg_color="#1e1a3d",
            hover_color="#2a2554",
            text_color="#e2e0ff",
            border_width=1,
            border_color="#36306e",
            font=get_mac_font(size=12, weight="bold"),
            command=self._open_folder_manager
        )
        self.folder_btn.pack(side="left", padx=4)

        self.theme_btn = ctk.CTkButton(
            btn_container,
            text="🌓",
            width=36,
            height=34,
            corner_radius=17,
            fg_color="#181533",
            hover_color="#25214e",
            text_color="#a5a1c9",
            border_width=1,
            border_color="#2c2858",
            font=get_mac_font(size=13),
            command=self._toggle_theme
        )
        self.theme_btn.pack(side="left", padx=4)

        # 2. カテゴリ選択バー (DLsite Sound カプセル・タブ)
        self.cat_frame = ctk.CTkFrame(self, height=48, corner_radius=0, fg_color="#0b081e")
        self.cat_frame.pack(fill="x", side="top", padx=15, pady=(8, 0))

        self._refresh_category_bar()

        # 3. メイングリッドエリア（スクロール可能）
        self.scroll_canvas = ctk.CTkScrollableFrame(self, corner_radius=14, fg_color="#080617")
        self.scroll_canvas.pack(fill="both", expand=True, padx=15, pady=8)

        # 4. 最下部ステータスバー
        self.footer_bar = ctk.CTkFrame(self, height=28, corner_radius=0, fg_color="#100e24")
        self.footer_bar.pack(fill="x", side="bottom")

        self.status_lbl = ctk.CTkLabel(
            self.footer_bar,
            text="準備完了",
            font=get_mac_font(size=11),
            text_color="#77aaf6"
        )
        self.status_lbl.pack(side="left", padx=15)

        self.dnd_lbl = ctk.CTkLabel(
            self.footer_bar,
            text="※ exeやフォルダをドラッグ＆ドロップして即座にライブラリ登録できます",
            font=get_mac_font(size=11),
            text_color="#737099"
        )
        self.dnd_lbl.pack(side="right", padx=15)

    def _setup_drag_and_drop(self):
        """ドラッグ＆ドロップの受付設定 (windnd)"""
        if HAS_WINDND:
            try:
                windnd.hook_dropfiles(self, func=self._on_files_dropped)
            except Exception as e:
                print(f"[DnD] ドラッグ＆ドロップ初期化エラー: {e}")

    def _on_files_dropped(self, file_paths):
        """ファイルやフォルダがドロップされた時のハンドラ"""
        if not file_paths:
            return

        for raw_p in file_paths:
            path_str = raw_p.decode("utf-8", errors="ignore") if isinstance(raw_p, bytes) else str(raw_p)
            p = Path(path_str)

            if p.is_dir():
                # フォルダ内のexeを全探索
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

    def _refresh_category_bar(self):
        for w in self.cat_frame.winfo_children():
            w.destroy()

        # 左側：カテゴリピルボタン
        cat_box = ctk.CTkFrame(self.cat_frame, fg_color="transparent")
        cat_box.pack(side="left", fill="y")

        categories = self.config_mgr.categories
        for cat in categories:
            is_active = (cat == self.current_category)
            btn = ctk.CTkButton(
                cat_box,
                text=cat,
                width=84,
                height=32,
                corner_radius=16,
                fg_color="#3a86ff" if is_active else "#181533",
                hover_color="#2b68cb" if is_active else "#25214e",
                text_color="#ffffff" if is_active else "#9e9abf",
                border_width=0 if is_active else 1,
                border_color="#2c2858",
                font=get_mac_font(size=12, weight="bold" if is_active else "normal"),
                command=lambda c=cat: self._select_category(c)
            )
            btn.pack(side="left", padx=4, pady=8)

        # 右側コントロール群（作者絞り込み ＋ ソートメニュー）
        right_controls = ctk.CTkFrame(self.cat_frame, fg_color="transparent")
        right_controls.pack(side="right", padx=6, pady=8)

        # 1. 作者・サークル絞り込みメニュー
        author_lbl = ctk.CTkLabel(
            right_controls,
            text="👤 サークル:",
            font=get_mac_font(size=11, weight="bold"),
            text_color="#77aaf6"
        )
        author_lbl.pack(side="left", padx=(0, 4))

        # 登録ゲームから作者一覧を抽出
        authors = set()
        for g in self.config_mgr.games:
            a = g.get("author")
            if a and a != "不明":
                authors.add(a)
        author_list = ["すべての作者・サークル"] + sorted(list(authors), key=lambda s: s.lower())

        if self.current_author not in author_list:
            self.current_author = "すべての作者・サークル"

        self.author_menu = ctk.CTkOptionMenu(
            right_controls,
            values=author_list,
            width=180,
            height=32,
            corner_radius=16,
            fg_color="#181533",
            button_color="#2c2759",
            button_hover_color="#3a3473",
            dropdown_fg_color="#181533",
            dropdown_hover_color="#2c2759",
            dropdown_text_color="#ffffff",
            text_color="#ffffff",
            font=get_mac_font(size=11),
            command=self._on_author_filter_changed
        )
        self.author_menu.set(self.current_author)
        self.author_menu.pack(side="left", padx=(0, 14))

        # 2. ソート選択メニュー
        sort_lbl = ctk.CTkLabel(
            right_controls,
            text="並び替え:",
            font=get_mac_font(size=11, weight="bold"),
            text_color="#77aaf6"
        )
        sort_lbl.pack(side="left", padx=(0, 4))

        sort_menu = ctk.CTkOptionMenu(
            right_controls,
            values=["作品名 (昇順)", "作者・サークル名 (昇順)", "登録順"],
            width=160,
            height=32,
            corner_radius=16,
            fg_color="#181533",
            button_color="#2c2759",
            button_hover_color="#3a3473",
            dropdown_fg_color="#181533",
            dropdown_hover_color="#2c2759",
            dropdown_text_color="#ffffff",
            text_color="#ffffff",
            font=get_mac_font(size=11),
            command=self._on_sort_changed
        )
        sort_menu.set(self.sort_order)
        sort_menu.pack(side="left")

    def _on_author_filter_changed(self, choice: str):
        self.current_author = choice
        self.refresh_games()

    def _on_sort_changed(self, choice: str):
        self.sort_order = choice
        self.refresh_games()

    def _select_category(self, cat: str):
        self.current_category = cat
        self._refresh_category_bar()
        self.refresh_games()

    def _toggle_theme(self):
        cur = ctk.get_appearance_mode()
        new_mode = "Light" if cur == "Dark" else "Dark"
        ctk.set_appearance_mode(new_mode)
        self.config_mgr.config["theme"] = new_mode
        self.config_mgr.save()

    def _initial_check_and_load(self):
        """初回ロード：登録ゲームが0件かつスキャンフォルダが存在する場合、自動スキャンを実行"""
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
        self._refresh_category_bar()
        self.refresh_games()

    def _on_search_changed(self, event=None):
        self.search_query = self.search_entry.get().strip().lower()
        self.refresh_games()

    def _on_search_enter(self, event=None):
        filtered = self._get_filtered_games()
        if filtered:
            first_game = filtered[0]
            self._launch_game(first_game)

    def _get_filtered_games(self) -> List[Dict[str, Any]]:
        all_games = self.config_mgr.games
        filtered = []

        for g in all_games:
            # 1. カテゴリ絞り込み
            if self.current_category != "すべて":
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
        if self.sort_order == "作品名 (昇順)":
            filtered.sort(key=lambda x: x.get("name", "").lower())
        elif self.sort_order == "作者・サークル名 (昇順)":
            # 不明は末尾に配置
            filtered.sort(key=lambda x: (1 if x.get("author", "不明") == "不明" else 0, x.get("author", "不明").lower(), x.get("name", "").lower()))
        elif self.sort_order == "登録順":
            pass

        return filtered

    def refresh_games(self):
        """ゲームカードグリッドを再描画"""
        for w in self.scroll_canvas.winfo_children():
            w.destroy()

        self.card_images.clear()
        self.card_widgets.clear()

        # 作者リストの動的更新
        if hasattr(self, "author_menu"):
            authors = set()
            for g in self.config_mgr.games:
                a = g.get("author")
                if a and a != "不明":
                    authors.add(a)
            author_list = ["すべての作者・サークル"] + sorted(list(authors), key=lambda s: s.lower())
            self.author_menu.configure(values=author_list)
            if self.current_author not in author_list:
                self.current_author = "すべての作者・サークル"
                self.author_menu.set(self.current_author)

        filtered = self._get_filtered_games()

        # 同一ゲームグループの解析
        self.grouped_games = GameAnalyzer.group_identical_games(self.config_mgr.games)

        self.status_lbl.configure(text=f"登録数: {len(self.config_mgr.games)} 件 (表示中: {len(filtered)} 件)")

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

        cols = 5
        for idx, game in enumerate(filtered):
            row = idx // cols
            col = idx % cols
            self._create_game_tile(self.scroll_canvas, game, row, col)

    def _create_game_tile(self, parent, game: Dict[str, Any], row: int, col: int):
        """DLsite Sound スタイルの洗練されたカードウィジェットを生成"""
        game_id = game.get("id")
        # DLsite Sound カード (丸み 16, 深い夜空色 #14112e, 微細境界線 #25204d)
        card = ctk.CTkFrame(
            parent,
            corner_radius=16,
            fg_color="#14112e",
            border_width=1,
            border_color="#25204d",
            width=200,
            height=274
        )
        card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
        card.grid_propagate(False)

        # 重複ゲーム判定
        group_key = None
        for k, g_list in self.grouped_games.items():
            if any(item.get("id") == game.get("id") for item in g_list):
                if len(g_list) > 1:
                    group_key = k
                break

        # サムネイル解決（元画像優先 -> DLsite -> キャッシュ -> Web -> exe）
        resolved_icon = game.get("icon_path")
        if not resolved_icon or not os.path.exists(resolved_icon):
            resolved_icon, quality = self.icon_helper.resolve_best_thumbnail(game, allow_web_search=True)
            game["icon_path"] = resolved_icon
            game["icon_quality"] = quality
            self.config_mgr.save()

        # PIL画像からCTkImage生成 (DLsite Sound アートワークサイズ 114x114)
        try:
            pil_img = Image.open(resolved_icon).convert("RGBA")
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(114, 114))
            self.card_images[game_id] = ctk_img
        except Exception:
            ctk_img = None

        # トップバー（サムネイル確定ロックボタン ＆ 重複バッジ）
        top_bar = ctk.CTkFrame(card, fg_color="transparent", height=24)
        top_bar.pack(fill="x", padx=8, pady=(8, 2))

        is_locked = game.get("icon_locked", False)
        lock_btn = ctk.CTkButton(
            top_bar,
            text="🔒 確定済" if is_locked else "🔓 自動探索中",
            width=78,
            height=20,
            corner_radius=10,
            fg_color="#1b7a32" if is_locked else "#1e1a3d",
            hover_color="#239a40" if is_locked else "#2a2554",
            text_color="#ffffff" if is_locked else "#77aaf6",
            border_width=0 if is_locked else 1,
            border_color="#36306e",
            font=get_mac_font(size=9, weight="bold"),
            command=lambda g=game: self._toggle_icon_lock(g)
        )
        lock_btn.pack(side="left")

        if group_key:
            dup_count = len(self.grouped_games[group_key])
            dup_btn = ctk.CTkButton(
                top_bar,
                text=f"🔁 重複 {dup_count}",
                width=66,
                height=20,
                corner_radius=10,
                fg_color="#9e6d00",
                hover_color="#b88002",
                text_color="#ffffff",
                font=get_mac_font(size=9, weight="bold"),
                command=lambda k=group_key: self._open_comparison_dialog(k)
            )
            dup_btn.pack(side="right")

        # アイコンボタン (ジャケット画像フレーム)
        img_frame = ctk.CTkFrame(card, corner_radius=12, fg_color="#0d0a20", border_width=1, border_color="#201b44")
        img_frame.pack(pady=(2, 4), padx=10)

        icon_btn = ctk.CTkButton(
            img_frame,
            image=ctk_img,
            text="",
            width=116,
            height=116,
            corner_radius=12,
            fg_color="transparent",
            hover_color="#211c47",
            command=lambda g=game: self._launch_game(g)
        )
        icon_btn.pack()

        # 作品名（DLsite Sound / Mac Rounded タイトル表示）
        name = game.get("name", "Game")
        name_lbl = ctk.CTkLabel(
            card,
            text=name,
            font=get_mac_font(size=12, weight="bold"),
            text_color="#ffffff",
            wraplength=180,
            cursor="hand2"
        )
        name_lbl.pack(padx=8, pady=(0, 2))
        name_lbl.bind("<Button-1>", lambda e, g=game: self._launch_game(g))

        # 作者・サークル名表示 (DLsite Sound パステルバイオレット)
        author_text = f"👤 {game.get('author', '不明')}"
        author_lbl = ctk.CTkLabel(
            card,
            text=author_text,
            font=get_mac_font(size=10),
            text_color="#8d89b0",
            wraplength=180
        )
        author_lbl.pack(padx=8, pady=(0, 4))

        # ファイルの場所確認・フォルダを開くボタン (DLsite Sound mini player aesthetic)
        folder_btn = ctk.CTkButton(
            card,
            text="📂 フォルダを開く",
            width=128,
            height=22,
            corner_radius=11,
            fg_color="#1a1738",
            hover_color="#272252",
            text_color="#a5a1c9",
            border_width=1,
            border_color="#2c2759",
            font=get_mac_font(size=10),
            command=lambda g=game: self._open_game_folder(g)
        )
        folder_btn.pack(pady=(0, 8))

        # 右クリックメニューのバインド
        for w in [card, img_frame, icon_btn, name_lbl, author_lbl]:
            w.bind("<Button-3>", lambda e, g=game: self._show_context_menu(e, g))

        self.card_widgets[game_id] = {
            "card": card,
            "icon_btn": icon_btn,
            "lock_btn": lock_btn,
            "game": game
        }

    def _on_game_icon_improved(self, updated_game: Dict[str, Any]):
        """バックグラウンドオプティマイザーでより最適な画像が見つかった時のリアルタイム更新"""
        self.after(0, lambda: self._apply_improved_icon(updated_game))

    def _apply_improved_icon(self, updated_game: Dict[str, Any]):
        game_id = updated_game.get("id")
        self.config_mgr.save()

        # 表示中のカードがあれば画像を差し替え
        if game_id in self.card_widgets:
            new_path = updated_game.get("icon_path")
            if new_path and os.path.exists(new_path):
                try:
                    pil_img = Image.open(new_path).convert("RGBA")
                    ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(108, 108))
                    self.card_images[game_id] = ctk_img
                    self.card_widgets[game_id]["icon_btn"].configure(image=ctk_img)
                    self.status_lbl.configure(text=f"✨ サムネイルを最適化しました: {updated_game.get('name')}", text_color="#4361ee")
                except Exception:
                    pass

    def _trigger_optimize_now(self):
        """手動で全サムネイルの最適化探索をリフレッシュ"""
        self.status_lbl.configure(text="✨ 最適なサムネイルをバックグラウンド探索中...", text_color="#4361ee")
        # 未達成ゲームの探索を即時リスタート
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
        """ユーザーがサムネイルを確定（ロック）または自動探索再開を切り替え"""
        cur = game.get("icon_locked", False)
        game["icon_locked"] = not cur
        self.config_mgr.save()
        game_id = game.get("id")
        if game_id in self.card_widgets and "lock_btn" in self.card_widgets[game_id]:
            is_locked = game["icon_locked"]
            self.card_widgets[game_id]["lock_btn"].configure(
                text="🔒 確定済" if is_locked else "🔓 自動探索中",
                fg_color="#1b7a32" if is_locked else "#1e1a3d",
                hover_color="#239a40" if is_locked else "#2a2554",
                text_color="#ffffff" if is_locked else "#77aaf6",
                border_width=0 if is_locked else 1,
                border_color="#36306e"
            )
        status_msg = "🔒 サムネイルを確定しました" if game["icon_locked"] else "🔓 サムネイル自動最適化を再開しました"
        self.status_lbl.configure(text=f"{status_msg}: {game.get('name')}", text_color="#77aaf6" if game['icon_locked'] else "#4361ee")

    def _show_context_menu(self, event, game: Dict[str, Any]):
        """右クリックコンテキストメニュー（Macフォント適用）"""
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
        """単体ゲームのサムネイル最適化を再試行"""
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
