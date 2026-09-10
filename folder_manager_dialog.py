import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from typing import Callable, List
from config_manager import ConfigManager
from folder_scanner import FolderScanner
from font_manager import get_mac_font

class FolderManagerDialog(ctk.CTkToplevel):
    """スキャン対象フォルダの追加・削除・一括スキャンを管理するダイアログ"""

    def __init__(self, master, config_mgr: ConfigManager, on_scan_complete: Callable):
        super().__init__(master)
        self.config_mgr = config_mgr
        self.on_scan_complete = on_scan_complete

        self.title("📁 ライブラリフォルダ管理")
        self.geometry("680x500")
        self.minsize(580, 400)
        self.configure(fg_color="#080617")

        self.grab_set()
        self.focus_set()

        self._build_ui()
        self._refresh_list()

    def _build_ui(self):
        main_frame = ctk.CTkFrame(
            self,
            corner_radius=16,
            fg_color="#121028",
            border_width=1,
            border_color="#221e4a"
        )
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)

        # ヘッダー
        ctk.CTkLabel(
            main_frame,
            text="📁 スキャン対象フォルダ一覧",
            font=get_mac_font(size=18, weight="bold"),
            text_color="#ffffff"
        ).pack(anchor="w", padx=15, pady=(15, 5))

        ctk.CTkLabel(
            main_frame,
            text="登録されたフォルダ配下のゲームを自動探索・追加します。新しいフォルダを自由に追加できます。",
            font=get_mac_font(size=12),
            text_color="#8d89b0"
        ).pack(anchor="w", padx=15, pady=(0, 15))

        # ツールバー（追加・一括スキャン）
        toolbar = ctk.CTkFrame(main_frame, fg_color="transparent")
        toolbar.pack(fill="x", padx=15, pady=(0, 10))

        add_btn = ctk.CTkButton(
            toolbar,
            text="＋ フォルダを追加",
            width=140,
            corner_radius=8,
            fg_color="#2b7a4b",
            hover_color="#1e5835",
            font=get_mac_font(size=12, weight="bold"),
            command=self._add_folder
        )
        add_btn.pack(side="left", padx=(0, 10))

        self.scan_all_btn = ctk.CTkButton(
            toolbar,
            text="🔄 全フォルダを一括再スキャン",
            width=180,
            corner_radius=8,
            font=get_mac_font(size=12, weight="bold"),
            command=self._scan_all
        )
        self.scan_all_btn.pack(side="left")

        # フォルダ一覧リスト（スクロールフレーム）
        self.list_frame = ctk.CTkScrollableFrame(main_frame, corner_radius=8)
        self.list_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        # プログレスバー & ステータス
        self.status_lbl = ctk.CTkLabel(main_frame, text="", font=get_mac_font(size=12))
        self.status_lbl.pack(anchor="w", padx=15, pady=(0, 5))

        self.prog_bar = ctk.CTkProgressBar(main_frame)
        self.prog_bar.set(0)
        self.prog_bar.pack(fill="x", padx=15, pady=(0, 10))
        self.prog_bar.pack_forget()

        # フッター
        footer = ctk.CTkFrame(main_frame, fg_color="transparent")
        footer.pack(fill="x", padx=15, pady=(0, 10))

        close_btn = ctk.CTkButton(
            footer,
            text="閉じる",
            width=100,
            corner_radius=8,
            fg_color="gray30",
            hover_color="gray40",
            font=get_mac_font(size=12),
            command=self.destroy
        )
        close_btn.pack(side="right")

    def _refresh_list(self):
        for w in self.list_frame.winfo_children():
            w.destroy()

        folders = self.config_mgr.scan_folders
        if not folders:
            empty_lbl = ctk.CTkLabel(
                self.list_frame,
                text="登録されたフォルダがありません。「フォルダを追加」から追加してください。",
                font=get_mac_font(size=12),
                text_color="gray60"
            )
            empty_lbl.pack(pady=30)
            return

        for folder in folders:
            item_card = ctk.CTkFrame(self.list_frame, corner_radius=8, fg_color=("gray85", "gray22"))
            item_card.pack(fill="x", pady=5, padx=5)

            path_lbl = ctk.CTkLabel(
                item_card,
                text=f"📂 {folder}",
                font=get_mac_font(size=13, weight="bold"),
                anchor="w"
            )
            path_lbl.pack(side="left", padx=12, pady=10, fill="x", expand=True)

            # 個別スキャンボタン
            scan_btn = ctk.CTkButton(
                item_card,
                text="スキャン",
                width=80,
                height=28,
                corner_radius=6,
                font=get_mac_font(size=11),
                command=lambda f=folder: self._scan_single_folder(f)
            )
            scan_btn.pack(side="right", padx=(5, 10))

            # 削除ボタン
            del_btn = ctk.CTkButton(
                item_card,
                text="削除",
                width=60,
                height=28,
                corner_radius=6,
                fg_color="#b22222",
                hover_color="#8b0000",
                font=get_mac_font(size=11),
                command=lambda f=folder: self._remove_folder(f)
            )
            del_btn.pack(side="right", padx=5)

    def _add_folder(self):
        folder = filedialog.askdirectory(title="ゲームが保存されているフォルダを選択")
        if folder:
            if not os.path.exists(folder):
                messagebox.showerror("エラー", "指定されたフォルダが存在しません。")
                return
            if self.config_mgr.add_scan_folder(folder):
                self._refresh_list()
                # カテゴリにも追加
                folder_name = os.path.basename(os.path.normpath(folder))
                self.config_mgr.add_category(folder_name)
                # 即時スキャンするか質問
                if messagebox.askyesno("スキャン確認", f"追加したフォルダ「{folder}」内のゲームを今すぐスキャンしますか？"):
                    self._scan_single_folder(folder)
            else:
                messagebox.showinfo("通知", "そのフォルダは既に登録されています。")

    def _remove_folder(self, folder: str):
        if messagebox.askyesno("削除確認", f"スキャン対象から「{folder}」を削除しますか？\n（実際のファイルは削除されません）"):
            self.config_mgr.remove_scan_folder(folder)
            self._refresh_list()

    def _scan_single_folder(self, folder: str):
        self._run_scan_thread([folder])

    def _scan_all(self):
        folders = self.config_mgr.scan_folders
        if not folders:
            messagebox.showinfo("情報", "スキャン対象フォルダが登録されていません。")
            return
        self._run_scan_thread(folders)

    def _run_scan_thread(self, folders: List[str]):
        self.scan_all_btn.configure(state="disabled")
        self.prog_bar.pack(fill="x", padx=15, pady=(0, 10))
        self.prog_bar.start()
        self.status_lbl.configure(text="フォルダをスキャン中...", text_color="#3a86ff")

        threading.Thread(target=self._scan_worker, args=(folders,), daemon=True).start()

    def _scan_worker(self, folders: List[str]):
        new_count = 0
        total_found = 0
        for folder in folders:
            cat_name = os.path.basename(os.path.normpath(folder))
            detected = FolderScanner.scan_library_folder(folder, default_category=cat_name)
            total_found += len(detected)
            for item in detected:
                existing = self.config_mgr.get_game_by_path(item["path"])
                if not existing:
                    self.config_mgr.add_or_update_game(item)
                    new_count += 1
                else:
                    # 既存ゲームも最新のローカル画像やRJ番号で強化
                    changed = False
                    if not existing.get("local_illustration") and item.get("local_illustration"):
                        existing["local_illustration"] = item["local_illustration"]
                        changed = True
                    if not existing.get("rj_code") and item.get("rj_code"):
                        existing["rj_code"] = item["rj_code"]
                        changed = True
                    if changed:
                        self.config_mgr.save()

        self.after(0, lambda: self._on_scan_finish(new_count, total_found))

    def _on_scan_finish(self, new_count: int, total_found: int):
        self.prog_bar.stop()
        self.prog_bar.pack_forget()
        self.scan_all_btn.configure(state="normal")
        self.status_lbl.configure(
            text=f"スキャン完了: {total_found} 件を検出 ({new_count} 件を新規登録)",
            text_color="#2b7a4b"
        )
        self.on_scan_complete()
