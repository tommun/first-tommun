import os
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from typing import Dict, Any, Optional, Callable
from PIL import Image
from icon_helper import IconHelper
from icon_picker_dialog import IconPickerDialog
from font_manager import get_mac_font

class GameEditDialog(ctk.CTkToplevel):
    """ゲーム・アプリの追加・編集を行うモーダルダイアログ"""

    def __init__(self, master, game_data: Optional[Dict[str, Any]], categories: list, icon_helper: IconHelper, on_save: Callable[[Dict[str, Any]], None]):
        super().__init__(master)
        self.game_data = game_data.copy() if game_data else {}
        self.categories = [c for c in categories if c != "すべて"]
        if not self.categories:
            self.categories = ["ゲーム", "download", "お気に入り"]
        self.icon_helper = icon_helper
        self.on_save = on_save

        is_new = not bool(game_data)
        self.title("＋ アプリ・ゲームを追加" if is_new else "✏️ ゲーム情報の編集")
        self.geometry("620x520")
        self.minsize(560, 460)

        self.grab_set()
        self.focus_set()

        self.current_icon_path = self.game_data.get("icon_path")
        self.preview_ctk_img = None

        self._build_ui()
        self._update_icon_preview()

    def _build_ui(self):
        main_frame = ctk.CTkFrame(self, corner_radius=12)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # タイトル
        title_text = "＋ 新しいアプリ・ゲームの登録" if not self.game_data.get("id") else "✏️ ゲーム情報の編集"
        ctk.CTkLabel(main_frame, text=title_text, font=get_mac_font(size=18, weight="bold")).pack(anchor="w", padx=15, pady=(15, 15))

        # フォームグリッド
        form_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        form_frame.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        # 名前
        ctk.CTkLabel(form_frame, text="ゲーム・アプリ名:", font=get_mac_font(size=13, weight="bold")).grid(row=0, column=0, sticky="w", pady=6)
        self.name_entry = ctk.CTkEntry(form_frame, placeholder_text="例: PURE ONYX", height=32, font=get_mac_font(size=12))
        self.name_entry.grid(row=0, column=1, sticky="ew", pady=6, padx=(10, 0))
        self.name_entry.insert(0, self.game_data.get("name", ""))

        # 実行ファイルパス
        ctk.CTkLabel(form_frame, text="実行ファイル (.exe):", font=get_mac_font(size=13, weight="bold")).grid(row=1, column=0, sticky="w", pady=6)
        exe_row = ctk.CTkFrame(form_frame, fg_color="transparent")
        exe_row.grid(row=1, column=1, sticky="ew", pady=6, padx=(10, 0))

        self.exe_entry = ctk.CTkEntry(exe_row, placeholder_text="C:\\path\\to\\game.exe", height=32, font=get_mac_font(size=12))
        self.exe_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.exe_entry.insert(0, self.game_data.get("path", ""))

        browse_exe_btn = ctk.CTkButton(exe_row, text="参照...", width=70, height=32, corner_radius=8, font=get_mac_font(size=12), command=self._browse_exe)
        browse_exe_btn.pack(side="right")

        # カテゴリ
        ctk.CTkLabel(form_frame, text="カテゴリ:", font=get_mac_font(size=13, weight="bold")).grid(row=2, column=0, sticky="w", pady=6)
        cat_row = ctk.CTkFrame(form_frame, fg_color="transparent")
        cat_row.grid(row=2, column=1, sticky="ew", pady=6, padx=(10, 0))

        cur_cat = self.game_data.get("category", self.categories[0] if self.categories else "ゲーム")
        if cur_cat not in self.categories:
            self.categories.append(cur_cat)
        self.cat_option = ctk.CTkOptionMenu(cat_row, values=self.categories, height=32, corner_radius=8, font=get_mac_font(size=12))
        self.cat_option.set(cur_cat)
        self.cat_option.pack(side="left", fill="x", expand=True, padx=(0, 6))

        # 起動引数（オプション）
        ctk.CTkLabel(form_frame, text="起動引数 (任意):", font=get_mac_font(size=13)).grid(row=3, column=0, sticky="w", pady=6)
        self.args_entry = ctk.CTkEntry(form_frame, placeholder_text="例: -window-mode", height=32, font=get_mac_font(size=12))
        self.args_entry.grid(row=3, column=1, sticky="ew", pady=6, padx=(10, 0))
        self.args_entry.insert(0, self.game_data.get("args", ""))

        # アイコンプレビューと画像選択
        ctk.CTkLabel(form_frame, text="アイコン・画像:", font=get_mac_font(size=13, weight="bold")).grid(row=4, column=0, sticky="nw", pady=12)
        icon_box = ctk.CTkFrame(form_frame, fg_color="transparent")
        icon_box.grid(row=4, column=1, sticky="ew", pady=12, padx=(10, 0))

        self.icon_preview_lbl = ctk.CTkLabel(icon_box, text="", width=72, height=72, corner_radius=8, fg_color=("gray80", "gray25"))
        self.icon_preview_lbl.pack(side="left", padx=(0, 15))

        btn_box = ctk.CTkFrame(icon_box, fg_color="transparent")
        btn_box.pack(side="left", fill="y", expand=True)

        web_search_btn = ctk.CTkButton(
            btn_box,
            text="🔍 Webから画像を探す",
            height=32,
            corner_radius=8,
            fg_color="#1f538d",
            font=get_mac_font(size=12),
            command=self._open_web_search
        )
        web_search_btn.pack(anchor="w", pady=(0, 6))

        file_icon_btn = ctk.CTkButton(
            btn_box,
            text="📁 画像ファイルを選択",
            height=32,
            corner_radius=8,
            fg_color="gray35",
            hover_color="gray45",
            font=get_mac_font(size=12),
            command=self._browse_icon_file
        )
        file_icon_btn.pack(anchor="w")

        form_frame.columnconfigure(1, weight=1)

        # フッターボタン
        footer = ctk.CTkFrame(main_frame, fg_color="transparent")
        footer.pack(fill="x", padx=15, pady=(10, 10))

        save_btn = ctk.CTkButton(
            footer,
            text="保存する",
            width=120,
            height=36,
            corner_radius=8,
            fg_color="#2b7a4b",
            hover_color="#1e5835",
            font=get_mac_font(size=13, weight="bold"),
            command=self._save
        )
        save_btn.pack(side="left")

        cancel_btn = ctk.CTkButton(
            footer,
            text="キャンセル",
            width=100,
            height=36,
            corner_radius=8,
            fg_color="gray30",
            hover_color="gray40",
            font=get_mac_font(size=12),
            command=self.destroy
        )
        cancel_btn.pack(side="right")

    def _browse_exe(self):
        file_path = filedialog.askopenfilename(
            title="起動するEXEファイルを選択",
            filetypes=[("実行ファイル", "*.exe"), ("ショートカット", "*.lnk"), ("すべてのファイル", "*.*")]
        )
        if file_path:
            self.exe_entry.delete(0, "end")
            self.exe_entry.insert(0, file_path)
            # 名前が未入力ならファイル名から自動設定
            if not self.name_entry.get().strip():
                stem = os.path.splitext(os.path.basename(file_path))[0]
                self.name_entry.insert(0, stem)
            self._update_icon_preview()

    def _browse_icon_file(self):
        file_path = filedialog.askopenfilename(
            title="アイコン画像ファイルを選択",
            filetypes=[("画像ファイル", "*.png;*.jpg;*.jpeg;*.ico;*.webp"), ("すべてのファイル", "*.*")]
        )
        if file_path and os.path.exists(file_path):
            self.current_icon_path = file_path
            self._update_icon_preview()

    def _open_web_search(self):
        name = self.name_entry.get().strip() or "ゲーム"
        exe = self.exe_entry.get().strip()
        dialog = IconPickerDialog(self, name, exe, self.icon_helper, self._on_icon_selected)

    def _on_icon_selected(self, new_icon_path: str):
        self.current_icon_path = new_icon_path
        self._update_icon_preview()

    def _update_icon_preview(self):
        icon_p = self.current_icon_path
        exe_p = self.exe_entry.get().strip()
        name_str = self.name_entry.get().strip() or "アプリ"

        final_path = self.icon_helper.get_or_create_icon(exe_p, name_str, preferred_icon_path=icon_p, allow_web_search=False)
        if final_path and os.path.exists(final_path):
            try:
                pil_img = Image.open(final_path).convert("RGBA")
                self.preview_ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(64, 64))
                self.icon_preview_lbl.configure(image=self.preview_ctk_img, text="")
                self.current_icon_path = final_path
            except Exception:
                self.icon_preview_lbl.configure(text="No Icon")
        else:
            self.icon_preview_lbl.configure(text="No Icon")

    def _save(self):
        name = self.name_entry.get().strip()
        exe = self.exe_entry.get().strip()
        cat = self.cat_option.get()
        args = self.args_entry.get().strip()

        if not name:
            messagebox.showerror("入力エラー", "ゲーム・アプリ名を入力してください。")
            return
        if not exe:
            messagebox.showerror("入力エラー", "実行ファイル (.exe) のパスを指定してください。")
            return

        self.game_data["name"] = name
        self.game_data["path"] = exe
        self.game_data["work_dir"] = os.path.dirname(exe)
        self.game_data["category"] = cat
        self.game_data["args"] = args
        self.game_data["icon_path"] = self.current_icon_path

        self.on_save(self.game_data)
        self.destroy()
