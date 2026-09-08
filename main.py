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
from icon_helper import IconHelper
from folder_scanner import FolderScanner
from game_analyzer import GameAnalyzer
from comparison_dialog import ComparisonDialog
from icon_picker_dialog import IconPickerDialog
from folder_manager_dialog import FolderManagerDialog
from game_edit_dialog import GameEditDialog

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class ModernLauncherApp(ctk.CTk):
    """モダンなカード型 ＋ リアルタイム検索 exeランチャー"""

    def __init__(self):
        super().__init__()

        self.config_mgr = ConfigManager()
        self.icon_helper = IconHelper()

        self.title("🎮 Game & EXE Launcher")
        window_w = self.config_mgr.config.get("settings", {}).get("window_width", 1120)
        window_h = self.config_mgr.config.get("settings", {}).get("window_height", 740)
        self.geometry(f"{window_w}x{window_h}")
        self.minsize(800, 500)

        # 状態変数
        self.current_category = "すべて"
        self.search_query = ""
        self.card_images = {}   # CTkImageのキャッシュ保持用
        self.grouped_games = {} # 同一ゲームのグループ情報

        self._build_ui()
        self._setup_drag_and_drop()

        # 起動時処理
        self.after(200, self._initial_check_and_load)

    def _build_ui(self):
        # 1. 最上部ヘッダー
        self.header_frame = ctk.CTkFrame(self, height=64, corner_radius=0, fg_color=("gray90", "gray15"))
        self.header_frame.pack(fill="x", side="top")

        # タイトルロゴ
        logo_lbl = ctk.CTkLabel(
            self.header_frame,
            text="🎮 GameLauncher",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        logo_lbl.pack(side="left", padx=20)

        # リアルタイム検索バー（ハイブリッドUIの中核）
        self.search_entry = ctk.CTkEntry(
            self.header_frame,
            placeholder_text="🔍 ゲーム・アプリを即座に検索... (Enterで先頭起動)",
            width=360,
            height=36,
            corner_radius=18,
            font=ctk.CTkFont(size=13)
        )
        self.search_entry.pack(side="left", padx=15, fill="x", expand=True)
        self.search_entry.bind("<KeyRelease>", self._on_search_changed)
        self.search_entry.bind("<Return>", self._on_search_enter)

        # アクションボタン群
        btn_container = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        btn_container.pack(side="right", padx=15)

        self.add_app_btn = ctk.CTkButton(
            btn_container,
            text="＋ 追加",
            width=80,
            height=34,
            fg_color="#2b7a4b",
            hover_color="#1e5835",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._open_add_dialog
        )
        self.add_app_btn.pack(side="left", padx=4)

        self.folder_btn = ctk.CTkButton(
            btn_container,
            text="📁 フォルダ管理",
            width=110,
            height=34,
            fg_color="#1f538d",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._open_folder_manager
        )
        self.folder_btn.pack(side="left", padx=4)

        self.theme_btn = ctk.CTkButton(
            btn_container,
            text="🌓",
            width=38,
            height=34,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(size=14),
            command=self._toggle_theme
        )
        self.theme_btn.pack(side="left", padx=4)

        # 2. カテゴリ選択バー
        self.cat_frame = ctk.CTkFrame(self, height=44, corner_radius=0, fg_color=("gray95", "gray12"))
        self.cat_frame.pack(fill="x", side="top", padx=15, pady=(8, 0))

        self._refresh_category_bar()

        # 3. メイングリッドエリア（スクロール可能）
        self.scroll_canvas = ctk.CTkScrollableFrame(self, corner_radius=10, fg_color="transparent")
        self.scroll_canvas.pack(fill="both", expand=True, padx=15, pady=10)

        # 4. 最下部ステータスバー
        self.footer_bar = ctk.CTkFrame(self, height=28, corner_radius=0, fg_color=("gray90", "gray15"))
        self.footer_bar.pack(fill="x", side="bottom")

        self.status_lbl = ctk.CTkLabel(
            self.footer_bar,
            text="準備完了",
            font=ctk.CTkFont(size=11),
            text_color="gray60"
        )
        self.status_lbl.pack(side="left", padx=15)

        self.dnd_lbl = ctk.CTkLabel(
            self.footer_bar,
            text="※ exeやフォルダをウィンドウにドラッグ＆ドロップして即登録できます",
            font=ctk.CTkFont(size=11),
            text_color="gray50"
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
            # windndの返り値はバイト列または文字列
            path_str = raw_p.decode("utf-8", errors="ignore") if isinstance(raw_p, bytes) else str(raw_p)
            p = Path(path_str)

            if p.is_dir():
                # フォルダがドロップされた場合はそのフォルダ配下のメインexeを検出
                main_exe = FolderScanner.find_main_exe_in_folder(str(p))
                if main_exe:
                    game_data = {
                        "name": p.name,
                        "path": main_exe,
                        "work_dir": os.path.dirname(main_exe),
                        "folder_path": str(p),
                        "category": self.current_category if self.current_category != "すべて" else "ゲーム"
                    }
                    self._open_edit_dialog_for_new(game_data)
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

        categories = self.config_mgr.categories
        for cat in categories:
            is_active = (cat == self.current_category)
            btn = ctk.CTkButton(
                self.cat_frame,
                text=cat,
                width=80,
                height=30,
                corner_radius=6,
                fg_color="#1f538d" if is_active else ("gray80", "gray22"),
                hover_color="#163e69" if is_active else ("gray70", "gray30"),
                text_color="white" if is_active else ("gray10", "gray80"),
                font=ctk.CTkFont(size=12, weight="bold" if is_active else "normal"),
                command=lambda c=cat: self._select_category(c)
            )
            btn.pack(side="left", padx=4, pady=6)

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
        """初回ロード：登録ゲームが0件かつスキャンフォルダが存在する場合、自動スキャンを提案・実行"""
        if len(self.config_mgr.games) == 0 and len(self.config_mgr.scan_folders) > 0:
            msg = (
                "ライブラリフォルダが見つかりました：\n"
                + "\n".join([f" - {f}" for f in self.config_mgr.scan_folders])
                + "\n\nこれらのフォルダ内のゲームを自動スキャンしてランチャーに登録しますか？"
            )
            if messagebox.askyesno("初回自動スキャン", msg):
                self._run_background_scan(self.config_mgr.scan_folders)
                return

        self.refresh_games()

    def _run_background_scan(self, folders: List[str]):
        self.status_lbl.configure(text="ゲームを自動スキャン中...", text_color="#3a86ff")

        def worker():
            new_count = 0
            for folder in folders:
                cat_name = os.path.basename(os.path.normpath(folder))
                detected = FolderScanner.scan_library_folder(folder, default_category=cat_name)
                for item in detected:
                    if not self.config_mgr.get_game_by_path(item["path"]):
                        self.config_mgr.add_or_update_game(item)
                        new_count += 1
            self.after(0, lambda: self._on_background_scan_done(new_count))

        threading.Thread(target=worker, daemon=True).start()

    def _on_background_scan_done(self, new_count: int):
        self.status_lbl.configure(text=f"自動スキャン完了: {new_count} 件登録しました", text_color="#2b7a4b")
        # カテゴリバーも更新（フォルダ名がカテゴリになっているため）
        for f in self.config_mgr.scan_folders:
            self.config_mgr.add_category(os.path.basename(os.path.normpath(f)))
        self._refresh_category_bar()
        self.refresh_games()

    def _on_search_changed(self, event=None):
        self.search_query = self.search_entry.get().strip().lower()
        self.refresh_games()

    def _on_search_enter(self, event=None):
        """Enterキーで現在表示されている一番最初のゲームを即起動"""
        filtered = self._get_filtered_games()
        if filtered:
            first_game = filtered[0]
            self._launch_game(first_game)

    def _get_filtered_games(self) -> List[Dict[str, Any]]:
        all_games = self.config_mgr.games
        filtered = []

        for g in all_games:
            # カテゴリフィルタ
            if self.current_category != "すべて":
                if g.get("category") != self.current_category:
                    continue

            # 検索クエリフィルタ
            if self.search_query:
                name = g.get("name", "").lower()
                path = g.get("path", "").lower()
                rj = (g.get("rj_code") or "").lower()
                if self.search_query not in name and self.search_query not in path and self.search_query not in rj:
                    continue

            filtered.append(g)

        return filtered

    def refresh_games(self):
        """ゲームカードグリッドを再描画"""
        for w in self.scroll_canvas.winfo_children():
            w.destroy()

        self.card_images.clear()
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
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color="gray60"
            ).pack()
            ctk.CTkLabel(
                empty_box,
                text="「＋ 追加」または「フォルダ管理」からゲームを追加してください。",
                font=ctk.CTkFont(size=12),
                text_color="gray50"
            ).pack(pady=5)
            return

        # グリッド配置（ウィンドウ幅に応じて自動計算、カード幅約180px）
        cols = 5
        for idx, game in enumerate(filtered):
            row = idx // cols
            col = idx % cols
            self._create_game_tile(self.scroll_canvas, game, row, col)

    def _create_game_tile(self, parent, game: Dict[str, Any], row: int, col: int):
        """タイル/カード型ウィジェットを生成"""
        card = ctk.CTkFrame(parent, corner_radius=12, fg_color=("gray85", "gray20"), width=180, height=210)
        card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
        card.grid_propagate(False)

        # 重複ゲーム判定
        group_key = None
        for k, g_list in self.grouped_games.items():
            if any(item.get("id") == game.get("id") for item in g_list):
                if len(g_list) > 1:
                    group_key = k
                break

        # アイコン取得（ローカルキャッシュまたはWebから）
        icon_path = game.get("icon_path")
        exe_path = game.get("path", "")
        name = game.get("name", "Game")

        resolved_icon = self.icon_helper.get_or_create_icon(
            exe_path, name, preferred_icon_path=icon_path, allow_web_search=True
        )
        # 設定に書き戻し（永続化）
        if resolved_icon != icon_path:
            game["icon_path"] = resolved_icon
            self.config_mgr.save()

        # PIL画像からCTkImage生成
        try:
            pil_img = Image.open(resolved_icon).convert("RGBA")
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(100, 100))
            self.card_images[game["id"]] = ctk_img
        except Exception:
            ctk_img = None

        # アイコンボタン（クリックで即起動）
        icon_btn = ctk.CTkButton(
            card,
            image=ctk_img,
            text="",
            width=110,
            height=110,
            fg_color="transparent",
            hover_color=("gray75", "gray30"),
            command=lambda g=game: self._launch_game(g)
        )
        icon_btn.pack(pady=(12, 4))

        # 重複バッジ（重複がある場合）
        if group_key:
            dup_count = len(self.grouped_games[group_key])
            dup_btn = ctk.CTkButton(
                card,
                text=f"🔁 重複 {dup_count}件 比較",
                width=120,
                height=20,
                fg_color="#b8860b",
                hover_color="#8c6609",
                font=ctk.CTkFont(size=10, weight="bold"),
                command=lambda k=group_key: self._open_comparison_dialog(k)
            )
            dup_btn.pack(pady=(0, 4))

        # ゲームタイトル表示
        name_lbl = ctk.CTkLabel(
            card,
            text=name,
            font=ctk.CTkFont(size=12, weight="bold"),
            wraplength=160,
            cursor="hand2"
        )
        name_lbl.pack(padx=8, pady=(0, 6))
        name_lbl.bind("<Button-1>", lambda e, g=game: self._launch_game(g))

        # 右クリックメニューのバインド
        for w in [card, icon_btn, name_lbl]:
            w.bind("<Button-3>", lambda e, g=game: self._show_context_menu(e, g))

    def _show_context_menu(self, event, game: Dict[str, Any]):
        """右クリックコンテキストメニュー"""
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="▶ 起動する", font=("Meiryo", 10, "bold"), command=lambda: self._launch_game(game))
        menu.add_separator()

        # 重複比較
        group_key = None
        for k, g_list in self.grouped_games.items():
            if any(item.get("id") == game.get("id") for item in g_list) and len(g_list) > 1:
                group_key = k
                break
        if group_key:
            menu.add_command(label=f"🔁 重複・進行度を比較 ({len(self.grouped_games[group_key])}件)", command=lambda: self._open_comparison_dialog(group_key))
            menu.add_separator()

        menu.add_command(label="🔍 Webから画像を探す", command=lambda: self._open_icon_picker(game))
        menu.add_command(label="📂 ファイルの場所を開く", command=lambda: self._open_game_folder(game))
        menu.add_command(label="✏️ 情報を編集", command=lambda: self._open_edit_dialog(game))
        menu.add_separator()
        menu.add_command(label="🗑️ ランチャーから削除", command=lambda: self._remove_game(game))

        menu.tk_popup(event.x_root, event.y_root)

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
