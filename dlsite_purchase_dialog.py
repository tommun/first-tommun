import os
import re
import threading
import webbrowser
from tkinter import filedialog, messagebox
import customtkinter as ctk
from font_manager import get_mac_font
from dlsite_purchase_importer import DLsitePurchaseImporter

class DLsitePurchaseDialog(ctk.CTkToplevel):
    """DLsiteの購入履歴（直接ログイン自動スクレイピング・HTML・RJ番号一覧）を取り込むダイアログ"""

    def __init__(self, master, config_mgr, icon_helper, on_complete):
        super().__init__(master)
        self.config_mgr = config_mgr
        self.icon_helper = icon_helper
        self.on_complete = on_complete

        self.title("📥 DLsite購入履歴の自動同期・取り込み")
        self.geometry("660x640")
        self.minsize(620, 560)
        self.configure(fg_color="#09071a")

        self.grab_set()
        self.focus_set()

        self._build_ui()

    def _build_ui(self):
        container = ctk.CTkFrame(
            self,
            corner_radius=16,
            fg_color="#120e2a",
            border_width=1,
            border_color="#241d52"
        )
        container.pack(fill="both", expand=True, padx=20, pady=20)

        # タイトル
        ctk.CTkLabel(
            container,
            text="📥 DLsite購入作品の自動スクレイピング・取り込み",
            font=get_mac_font(size=17, weight="bold"),
            text_color="#ffffff"
        ).pack(anchor="w", padx=16, pady=(16, 4))

        # 説明文
        desc = (
            "DLsiteアカウントで直接ログインして購入済み作品を全自動で取得・同期します。\n"
            "※ パスワード等は保存されず、購入履歴の取得通信のみに使用されます。"
        )
        ctk.CTkLabel(
            container,
            text=desc,
            font=get_mac_font(size=11),
            text_color="#9e9abf",
            justify="left"
        ).pack(anchor="w", padx=16, pady=(0, 12))

        # === タブビュー (ログインして自動スクレイピング / HTML・手動入力) ===
        tabview = ctk.CTkTabview(
            container,
            fg_color="#181335",
            segmented_button_fg_color="#100c26",
            segmented_button_selected_color="#3a86ff",
            segmented_button_selected_hover_color="#2b68cb",
            segmented_button_unselected_color="#181335",
            segmented_button_unselected_hover_color="#231b4d"
        )
        tabview.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        tab_login = tabview.add("🔑 ログインして全自動取得 (推奨)")
        tab_manual = tabview.add("📄 HTMLファイル / テキスト貼り付け")

        # --- タブ1: ログイン自動取得 ---
        ctk.CTkLabel(
            tab_login,
            text="DLsiteのログイン情報を入力して「自動取得を開始」を押してください：",
            font=get_mac_font(size=11, weight="bold"),
            text_color="#ffffff"
        ).pack(anchor="w", padx=10, pady=(10, 8))

        form_box = ctk.CTkFrame(tab_login, fg_color="transparent")
        form_box.pack(fill="x", padx=10, pady=(0, 10))

        # ログインID
        ctk.CTkLabel(
            form_box,
            text="ログインID / メールアドレス:",
            font=get_mac_font(size=11),
            text_color="#9e9abf"
        ).grid(row=0, column=0, sticky="w", pady=4)

        self.login_id_entry = ctk.CTkEntry(
            form_box,
            width=320,
            height=32,
            corner_radius=8,
            fg_color="#0c0920",
            border_color="#2c2258",
            text_color="#ffffff",
            font=get_mac_font(size=11),
            placeholder_text="example@email.com"
        )
        self.login_id_entry.grid(row=0, column=1, sticky="w", padx=10, pady=4)

        # パスワード
        ctk.CTkLabel(
            form_box,
            text="パスワード:",
            font=get_mac_font(size=11),
            text_color="#9e9abf"
        ).grid(row=1, column=0, sticky="w", pady=4)

        self.password_entry = ctk.CTkEntry(
            form_box,
            width=320,
            height=32,
            corner_radius=8,
            fg_color="#0c0920",
            border_color="#2c2258",
            text_color="#ffffff",
            show="●",
            font=get_mac_font(size=11),
            placeholder_text="パスワード"
        )
        self.password_entry.grid(row=1, column=1, sticky="w", padx=10, pady=4)

        self.auto_fetch_btn = ctk.CTkButton(
            tab_login,
            text="🚀 ログインして購入履歴を自動スクレイピング",
            height=36,
            corner_radius=18,
            fg_color="#ff007a",
            hover_color="#d60066",
            text_color="#ffffff",
            font=get_mac_font(size=12, weight="bold"),
            command=self._start_auto_login_scraping
        )
        self.auto_fetch_btn.pack(anchor="w", padx=10, pady=(6, 8))

        # --- タブ2: HTML / 手動貼り付け ---
        row_browse = ctk.CTkFrame(tab_manual, fg_color="transparent")
        row_browse.pack(fill="x", padx=10, pady=(8, 8))

        ctk.CTkButton(
            row_browse,
            text="🌐 ブラウザで購入履歴を開く",
            width=180,
            height=30,
            corner_radius=8,
            fg_color="#2c2266",
            hover_color="#3d308c",
            text_color="#ffffff",
            font=get_mac_font(size=11),
            command=lambda: webbrowser.open("https://www.dlsite.com/maniax/mypage/userbuy")
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            row_browse,
            text="📄 保存したHTMLファイルを選択...",
            width=200,
            height=30,
            corner_radius=8,
            fg_color="#3a86ff",
            hover_color="#2b68cb",
            text_color="#ffffff",
            font=get_mac_font(size=11),
            command=self._browse_html_file
        ).pack(side="left")

        self.text_area = ctk.CTkTextbox(
            tab_manual,
            height=120,
            corner_radius=10,
            fg_color="#0c0920",
            border_width=1,
            border_color="#271f54",
            text_color="#ffffff",
            font=get_mac_font(size=11)
        )
        self.text_area.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self.text_area.insert("1.0", "ここにRJ番号（例: RJ01360185）またはHTMLを直接貼り付けも可能です")

        # プログレスバー & ステータス
        self.progress_bar = ctk.CTkProgressBar(container, height=6, corner_radius=3, fg_color="#181335", progress_color="#3a86ff")
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=16, pady=(0, 4))

        self.status_lbl = ctk.CTkLabel(
            container,
            text="準備完了",
            font=get_mac_font(size=11),
            text_color="#737099"
        )
        self.status_lbl.pack(anchor="w", padx=16, pady=(0, 10))

        # 下部ボタン
        btn_box = ctk.CTkFrame(container, fg_color="transparent")
        btn_box.pack(fill="x", padx=16, pady=(0, 12))

        self.start_import_btn = ctk.CTkButton(
            btn_box,
            text="📥 ライブラリ同期を実行",
            height=36,
            corner_radius=18,
            fg_color="#3a86ff",
            hover_color="#2b68cb",
            text_color="#ffffff",
            font=get_mac_font(size=12, weight="bold"),
            command=self._start_import
        )
        self.start_import_btn.pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            btn_box,
            text="閉じる",
            width=80,
            height=36,
            corner_radius=18,
            fg_color="#1e183d",
            hover_color="#2c2357",
            text_color="#a5a1c9",
            font=get_mac_font(size=11),
            command=self.destroy
        ).pack(side="right")

    def _start_auto_login_scraping(self):
        login_id = self.login_id_entry.get().strip()
        password = self.password_entry.get().strip()

        if not login_id or not password:
            messagebox.showwarning("入力エラー", "ログインIDとパスワードを入力してください。")
            return

        self.auto_fetch_btn.configure(state="disabled")
        self.start_import_btn.configure(state="disabled")
        self.progress_bar.set(0.1)
        self.status_lbl.configure(text="DLsiteに接続中...", text_color="#3a86ff")

        def worker():
            def on_progress(msg):
                self.after(0, lambda: self.status_lbl.configure(text=msg, text_color="#77aaf6"))

            success, msg, rjs = DLsitePurchaseImporter.login_and_fetch_purchased_rjs(
                login_id, password, progress_callback=on_progress
            )

            def on_login_done():
                self.auto_fetch_btn.configure(state="normal")
                self.start_import_btn.configure(state="normal")

                if not success:
                    self.status_lbl.configure(text=f"ログイン失敗: {msg}", text_color="#f87171")
                    messagebox.showerror("ログイン失敗", f"DLsiteへのログインに失敗しました:\n\n{msg}")
                    return

                if not rjs:
                    self.status_lbl.configure(text=msg, text_color="#facc15")
                    messagebox.showinfo("情報", msg)
                    return

                # RJコードが取得できたら手動エリアにも反映し、同期開始
                self.text_area.delete("1.0", "end")
                self.text_area.insert("1.0", "\n".join(rjs))
                self.status_lbl.configure(text=f"{len(rjs)} 件の作品を検出しました。ライブラリ同期を開始します...", text_color="#3a86ff")

                # 自動でライブラリ同期へ移行
                self._run_sync_worker(rjs)

            self.after(0, on_login_done)

        threading.Thread(target=worker, daemon=True).start()

    def _browse_html_file(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="DLsite購入履歴のHTMLファイルを選択",
            filetypes=[("HTML Files", "*.html;*.htm"), ("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if path:
            rjs = DLsitePurchaseImporter.extract_from_html_file(path)
            if rjs:
                self.text_area.delete("1.0", "end")
                self.text_area.insert("1.0", "\n".join(rjs))
                self.status_lbl.configure(text=f"HTMLから {len(rjs)} 件の購入RJコードを検出しました！", text_color="#77aaf6")
            else:
                messagebox.showwarning("警告", "選択されたファイルからRJコードが見つかりませんでした。")

    def _start_import(self):
        raw_text = self.text_area.get("1.0", "end").strip()
        rjs = DLsitePurchaseImporter.extract_rj_codes_from_text(raw_text)

        if not rjs:
            messagebox.showwarning("入力不足", "有効なRJ番号が見つかりませんでした。「ログインして全自動取得」を行うか、RJコードを入力してください。")
            return

        self._run_sync_worker(rjs)

    def _run_sync_worker(self, rjs):
        self.start_import_btn.configure(state="disabled")
        self.auto_fetch_btn.configure(state="disabled")
        self.status_lbl.configure(text=f"{len(rjs)} 件の作品情報をDLsiteから取得・同期中...", text_color="#3a86ff")

        def worker():
            def on_progress(cur, total, rj):
                val = cur / max(1, total)
                self.after(0, lambda: self.progress_bar.set(val))
                self.after(0, lambda: self.status_lbl.configure(text=f"同期中: {cur}/{total} ({rj})", text_color="#77aaf6"))

            matched, added = DLsitePurchaseImporter.sync_purchased_games(
                rjs,
                self.config_mgr,
                self.icon_helper,
                progress_callback=on_progress
            )
            self.after(0, lambda: self._on_finished(matched, added, len(rjs)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_finished(self, matched: int, added: int, total: int):
        self.progress_bar.set(1.0)
        self.status_lbl.configure(
            text=f"完了！ PC内照合: {matched} 件 | 未ダウンロード登録: {added} 件",
            text_color="#2b7a4b"
        )
        messagebox.showinfo(
            "取り込み完了",
            f"DLsite購入履歴の同期が完了しました！\n\n"
            f"・取得した購入作品: {total} 件\n"
            f"・PC内ゲームと照合済み: {matched} 件\n"
            f"・新規登録（未ダウンロード作品）: {added} 件"
        )
        if self.on_complete:
            self.on_complete()
        self.destroy()
