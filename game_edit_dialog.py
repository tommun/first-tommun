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
    """ゲーム・アプリの追加・編集を行うモーダルダイアログ（購入元プラットフォーム・ジャンル・タグ対応）"""

    def __init__(self, master, game_data: Optional[Dict[str, Any]], categories: list, icon_helper: IconHelper, on_save: Callable[[Dict[str, Any]], None]):
        super().__init__(master)
        self.game_data = game_data.copy() if game_data else {}
        self.categories = [c for c in categories if c != "すべて"]
        if not self.categories:
            self.categories = ["ロールプレイング", "アクション", "アドベンチャー", "シミュレーション", "パズル", "その他"]
        self.icon_helper = icon_helper
        self.on_save = on_save

        is_new = not bool(game_data)
        self.title("＋ アプリ・ゲームを追加" if is_new else "✏️ ゲーム情報の編集")
        self.geometry("660x680")
        self.minsize(600, 600)
        self.configure(fg_color="#080617")

        self.grab_set()
        self.focus_set()

        self.current_icon_path = self.game_data.get("icon_path")
        self.preview_ctk_img = None

        self._build_ui()
        self._update_icon_preview()

    def _build_ui(self):
        main_frame = ctk.CTkFrame(
            self,
            corner_radius=16,
            fg_color="#121028",
            border_width=1,
            border_color="#221e4a"
        )
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # タイトル
        title_text = "＋ 新しいアプリ・ゲームの登録" if not self.game_data.get("id") else "✏️ ゲーム情報の編集"
        ctk.CTkLabel(
            main_frame,
            text=title_text,
            font=get_mac_font(size=18, weight="bold"),
            text_color="#ffffff"
        ).pack(anchor="w", padx=15, pady=(15, 12))

        # フォームグリッド
        form_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        form_frame.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        # 0. 名前
        ctk.CTkLabel(form_frame, text="作品名・タイトル:", font=get_mac_font(size=12, weight="bold")).grid(row=0, column=0, sticky="w", pady=4)
        self.name_entry = ctk.CTkEntry(form_frame, placeholder_text="例: 監獄勇者, Nakara", height=32, font=get_mac_font(size=12))
        self.name_entry.grid(row=0, column=1, sticky="ew", pady=4, padx=(10, 0))
        self.name_entry.insert(0, self.game_data.get("name", ""))

        # 1. 作者・サークル名
        ctk.CTkLabel(form_frame, text="作者・サークル名:", font=get_mac_font(size=12, weight="bold")).grid(row=1, column=0, sticky="w", pady=4)
        self.author_entry = ctk.CTkEntry(form_frame, placeholder_text="例: I'm moralist, Redspike", height=32, font=get_mac_font(size=12))
        self.author_entry.grid(row=1, column=1, sticky="ew", pady=4, padx=(10, 0))
        self.author_entry.insert(0, self.game_data.get("author", "不明"))

        # 2. 購入元プラットフォーム (DLsite / FANZA / その他)
        ctk.CTkLabel(form_frame, text="購入元・プラットフォーム:", font=get_mac_font(size=12, weight="bold")).grid(row=2, column=0, sticky="w", pady=4)
        plat_row = ctk.CTkFrame(form_frame, fg_color="transparent")
        plat_row.grid(row=2, column=1, sticky="ew", pady=4, padx=(10, 0))

        cur_plat = self.game_data.get("platform", "DLsite" if self.game_data.get("rj_code") else "その他")
        self.plat_option = ctk.CTkOptionMenu(
            plat_row,
            values=["DLsite", "FANZA", "その他"],
            height=32,
            corner_radius=8,
            fg_color="#181335",
            button_color="#2b2355",
            button_hover_color="#3d3278",
            font=get_mac_font(size=12)
        )
        self.plat_option.set(cur_plat)
        self.plat_option.pack(side="left", fill="x", expand=True)

        # 3. ゲームジャンル (ロールプレイング, アクション, etc.)
        ctk.CTkLabel(form_frame, text="ゲームジャンル:", font=get_mac_font(size=12, weight="bold")).grid(row=3, column=0, sticky="w", pady=4)
        genre_row = ctk.CTkFrame(form_frame, fg_color="transparent")
        genre_row.grid(row=3, column=1, sticky="ew", pady=4, padx=(10, 0))

        cur_genre = self.game_data.get("genre") or self.game_data.get("category", "ロールプレイング")
        self.genre_entry = ctk.CTkEntry(genre_row, placeholder_text="例: ロールプレイング, アクション, アドベンチャー", height=32, font=get_mac_font(size=12))
        self.genre_entry.pack(side="left", fill="x", expand=True)
        self.genre_entry.insert(0, cur_genre)

        # 4. タグ (カンマ区切り)
        ctk.CTkLabel(form_frame, text="タグ (カンマ区切り):", font=get_mac_font(size=12, weight="bold")).grid(row=4, column=0, sticky="w", pady=4)
        self.tags_entry = ctk.CTkEntry(form_frame, placeholder_text="例: 女主人公, 拘束, ドット, ファンタジー", height=32, font=get_mac_font(size=12))
        self.tags_entry.grid(row=4, column=1, sticky="ew", pady=4, padx=(10, 0))
        cur_tags = ", ".join(self.game_data.get("tags", []))
        self.tags_entry.insert(0, cur_tags)

        # 5. RJ番号 / 商品コード
        ctk.CTkLabel(form_frame, text="RJ番号 / 商品コード:", font=get_mac_font(size=12)).grid(row=5, column=0, sticky="w", pady=4)
        self.rj_entry = ctk.CTkEntry(form_frame, placeholder_text="例: RJ01360185", height=32, font=get_mac_font(size=12))
        self.rj_entry.grid(row=5, column=1, sticky="ew", pady=4, padx=(10, 0))
        self.rj_entry.insert(0, self.game_data.get("rj_code", "") or "")

        # 6. 実行ファイルパス (.exe)
        ctk.CTkLabel(form_frame, text="実行ファイル (.exe):", font=get_mac_font(size=12, weight="bold")).grid(row=6, column=0, sticky="w", pady=4)
        exe_row = ctk.CTkFrame(form_frame, fg_color="transparent")
        exe_row.grid(row=6, column=1, sticky="ew", pady=4, padx=(10, 0))

        self.exe_entry = ctk.CTkEntry(exe_row, placeholder_text="C:\\path\\to\\game.exe", height=32, font=get_mac_font(size=12))
        self.exe_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.exe_entry.insert(0, self.game_data.get("path", ""))

        browse_exe_btn = ctk.CTkButton(exe_row, text="参照...", width=70, height=32, corner_radius=8, font=get_mac_font(size=12), command=self._browse_exe)
        browse_exe_btn.pack(side="right")

        # 7. フォルダの場所
        ctk.CTkLabel(form_frame, text="ファイルの場所:", font=get_mac_font(size=12)).grid(row=7, column=0, sticky="w", pady=4)
        fld_row = ctk.CTkFrame(form_frame, fg_color="transparent")
        fld_row.grid(row=7, column=1, sticky="ew", pady=4, padx=(10, 0))

        initial_folder = self.game_data.get("folder_path") or (os.path.dirname(self.game_data.get("path", "")) if self.game_data.get("path") else "")
        self.folder_entry = ctk.CTkEntry(fld_row, placeholder_text="フォルダの場所", height=32, font=get_mac_font(size=12))
        self.folder_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.folder_entry.insert(0, initial_folder)

        open_fld_btn = ctk.CTkButton(
            fld_row,
            text="📂 フォルダを開く",
            width=110,
            height=32,
            corner_radius=8,
            fg_color="#1f183d",
            hover_color="#2b2355",
            font=get_mac_font(size=11),
            command=self._open_current_folder
        )
        open_fld_btn.pack(side="right")

        # 8. アイコンプレビューと画像選択
        ctk.CTkLabel(form_frame, text="ジャケット・アイコン:", font=get_mac_font(size=12, weight="bold")).grid(row=8, column=0, sticky="nw", pady=8)
        icon_box = ctk.CTkFrame(form_frame, fg_color="transparent")
        icon_box.grid(row=8, column=1, sticky="ew", pady=8, padx=(10, 0))

        self.icon_preview_lbl = ctk.CTkLabel(icon_box, text="", width=72, height=72, corner_radius=8, fg_color=("gray80", "gray25"))
        self.icon_preview_lbl.pack(side="left", padx=(0, 15))

        btn_box = ctk.CTkFrame(icon_box, fg_color="transparent")
        btn_box.pack(side="left", fill="y", expand=True)

        web_search_btn = ctk.CTkButton(
            btn_box,
            text="🔍 Webから画像を探す",
            height=30,
            corner_radius=8,
            fg_color="#1f538d",
            font=get_mac_font(size=11),
            command=self._open_web_search
        )
        web_search_btn.pack(anchor="w", pady=(0, 4))

        file_icon_btn = ctk.CTkButton(
            btn_box,
            text="📁 画像ファイルを選択",
            height=30,
            corner_radius=8,
            fg_color="gray35",
            hover_color="gray45",
            font=get_mac_font(size=11),
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
            corner_radius=18,
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
            corner_radius=18,
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
            if not self.name_entry.get().strip():
                stem = os.path.splitext(os.path.basename(file_path))[0]
                self.name_entry.insert(0, stem)
            if not self.folder_entry.get().strip():
                self.folder_entry.insert(0, os.path.dirname(file_path))
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
        IconPickerDialog(self, name, exe, self.icon_helper, self._on_icon_selected)

    def _on_icon_selected(self, new_icon_path: str):
        self.current_icon_path = new_icon_path
        self._update_icon_preview()

    def _update_icon_preview(self):
        if self.current_icon_path and os.path.exists(self.current_icon_path):
            try:
                pil_img = Image.open(self.current_icon_path)
                self.preview_ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(64, 64))
                self.icon_preview_lbl.configure(image=self.preview_ctk_img, text="")
                return
            except Exception:
                pass
        self.icon_preview_lbl.configure(image=None, text="No Image")

    def _open_current_folder(self):
        fld = self.folder_entry.get().strip()
        if fld and os.path.exists(fld):
            os.startfile(fld)
        else:
            messagebox.showwarning("警告", "指定されたフォルダが存在しません。")

    def _save(self):
        name = self.name_entry.get().strip()
        exe = self.exe_entry.get().strip()
        author = self.author_entry.get().strip() or "不明"
        platform = self.plat_option.get()
        genre = self.genre_entry.get().strip() or "その他"
        tags_raw = self.tags_entry.get().strip()
        tags = [t.strip() for t in re.split(r'[,、/]+', tags_raw) if t.strip()]
        rj = self.rj_entry.get().strip()
        folder = self.folder_entry.get().strip()

        if not name:
            messagebox.showerror("入力エラー", "作品名・タイトルを入力してください。")
            return

        self.game_data["name"] = name
        self.game_data["path"] = exe
        self.game_data["author"] = author
        self.game_data["platform"] = platform
        self.game_data["genre"] = genre
        self.game_data["category"] = genre
        self.game_data["tags"] = tags
        if rj:
            self.game_data["rj_code"] = rj.upper()
        if folder:
            self.game_data["folder_path"] = folder
            self.game_data["work_dir"] = folder
        elif exe and os.path.exists(exe):
            self.game_data["work_dir"] = os.path.dirname(exe)

        if self.current_icon_path:
            self.game_data["icon_path"] = self.current_icon_path
            self.game_data["icon_locked"] = True

        self.on_save(self.game_data)
        self.destroy()
