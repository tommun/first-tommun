import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image
from typing import Optional, Callable
from icon_helper import IconHelper

class IconPickerDialog(ctk.CTkToplevel):
    """Web検索結果のサムネイル一覧からアイコンを選択、またはローカルファイルを指定するダイアログ"""

    def __init__(self, master, current_name: str, current_exe: str, icon_helper: IconHelper, on_icon_selected: Callable[[str], None]):
        super().__init__(master)
        self.current_name = current_name
        self.current_exe = current_exe
        self.icon_helper = icon_helper
        self.on_icon_selected = on_icon_selected

        self.title("🔍 アイコン・カバー画像を選択")
        self.geometry("740x560")
        self.minsize(640, 480)

        self.grab_set()
        self.focus_set()

        self.thumbnail_images = []
        self._build_ui()
        # 初回検索を自動実行
        self.after(200, self._start_search)

    def _build_ui(self):
        main_frame = ctk.CTkFrame(self, corner_radius=12)
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)

        # 検索バー行
        search_row = ctk.CTkFrame(main_frame, fg_color="transparent")
        search_row.pack(fill="x", padx=15, pady=(15, 10))

        ctk.CTkLabel(search_row, text="検索ワード:", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left", padx=(0, 10))

        self.search_entry = ctk.CTkEntry(search_row, placeholder_text="ゲーム名、アニメ名、RJ番号など", height=35)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.search_entry.insert(0, self.current_name)
        self.search_entry.bind("<Return>", lambda e: self._start_search())

        self.search_btn = ctk.CTkButton(
            search_row,
            text="Web検索",
            width=90,
            height=35,
            command=self._start_search
        )
        self.search_btn.pack(side="left", padx=(0, 10))

        self.local_file_btn = ctk.CTkButton(
            search_row,
            text="📁 ローカル画像",
            width=110,
            height=35,
            fg_color="gray30",
            hover_color="gray40",
            command=self._select_local_file
        )
        self.local_file_btn.pack(side="left")

        # ステータス表示
        self.status_lbl = ctk.CTkLabel(main_frame, text="", font=ctk.CTkFont(size=12), text_color="gray70")
        self.status_lbl.pack(anchor="w", padx=15, pady=(0, 5))

        # サムネイル表示エリア（スクロール）
        self.scroll_frame = ctk.CTkScrollableFrame(main_frame, corner_radius=8)
        self.scroll_frame.pack(fill="both", expand=True, padx=15, pady=(5, 15))

        # 下部アクションバー
        footer_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        footer_frame.pack(fill="x", padx=15, pady=(0, 10))

        ctk.CTkLabel(footer_frame, text="※ クリックした画像がアプリアイコンに即座に設定されます", font=ctk.CTkFont(size=11), text_color="gray60").pack(side="left")

        cancel_btn = ctk.CTkButton(
            footer_frame,
            text="キャンセル",
            width=100,
            fg_color="gray35",
            hover_color="gray45",
            command=self.destroy
        )
        cancel_btn.pack(side="right")

    def _start_search(self):
        query = self.search_entry.get().strip()
        if not query:
            return

        self.status_lbl.configure(text=f"「{query}」で画像を検索中...", text_color="#3a86ff")
        self.search_btn.configure(state="disabled")

        # 既存サムネイル消去
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self.thumbnail_images.clear()

        # スレッドで検索実行
        threading.Thread(target=self._search_worker, args=(query,), daemon=True).start()

    def _search_worker(self, query: str):
        urls = self.icon_helper.search_web_icons(query, max_results=8)
        downloaded = []
        for url in urls:
            img = self.icon_helper.download_image(url, target_size=(140, 140))
            if img:
                downloaded.append((url, img))

        self.after(0, lambda: self._on_search_completed(downloaded, query))

    def _on_search_completed(self, downloaded_list, query):
        self.search_btn.configure(state="normal")
        if not downloaded_list:
            self.status_lbl.configure(text=f"「{query}」の画像が見つかりませんでした。別の単語で検索してみてください。", text_color="#e63946")
            return

        self.status_lbl.configure(text=f"{len(downloaded_list)} 件の画像候補が見つかりました。好きな画像をクリックしてください。", text_color="gray80")

        # 4列のグリッドで配置
        cols = 4
        for idx, (url, pil_img) in enumerate(downloaded_list):
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(120, 120))
            self.thumbnail_images.append(ctk_img)  # 参照保持

            row = idx // cols
            col = idx % cols

            item_btn = ctk.CTkButton(
                self.scroll_frame,
                image=ctk_img,
                text="",
                width=135,
                height=135,
                fg_color=("gray85", "gray25"),
                hover_color=("gray75", "gray35"),
                corner_radius=8,
                command=lambda p_img=pil_img: self._select_image(p_img)
            )
            item_btn.grid(row=row, column=col, padx=8, pady=8)

    def _select_image(self, pil_img: Image.Image):
        """Webで取得した画像を選択して保存・コールバック"""
        cache_path = self.icon_helper.cache_image(f"{self.current_name}_{self.current_exe}_{os.urandom(4).hex()}", pil_img)
        self.on_icon_selected(cache_path)
        self.destroy()

    def _select_local_file(self):
        """ローカル画像ファイルの選択"""
        file_path = filedialog.askopenfilename(
            title="画像ファイルを選択",
            filetypes=[("画像ファイル", "*.png;*.jpg;*.jpeg;*.ico;*.bmp;*.webp"), ("すべてのファイル", "*.*")]
        )
        if file_path and os.path.exists(file_path):
            try:
                img = Image.open(file_path).convert("RGBA")
                cache_path = self.icon_helper.cache_image(f"{self.current_name}_{self.current_exe}_{os.urandom(4).hex()}", img)
                self.on_icon_selected(cache_path)
                self.destroy()
            except Exception as e:
                messagebox.showerror("エラー", f"画像の読み込みに失敗しました:\n{e}")
