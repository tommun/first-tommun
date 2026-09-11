import os
import re
import threading
import webbrowser
from tkinter import filedialog, messagebox
import customtkinter as ctk
from font_manager import get_mac_font
from dlsite_purchase_importer import DLsitePurchaseImporter
from fanza_metadata import FANZAPurchaseImporter, FANZAMetadataFetcher

class DLsitePurchaseDialog(ctk.CTkToplevel):
    """DLsite & FANZA の購入履歴・所持作品の取り込み＆同期ダイアログ"""

    def __init__(self, master, config_mgr, icon_helper, on_complete):
        super().__init__(master)
        self.config_mgr = config_mgr
        self.icon_helper = icon_helper
        self.on_complete = on_complete

        self.title("📥 購入作品・ライブラリの自動同期・取り込み")
        self.geometry("680x670")
        self.minsize(640, 580)
        self.configure(fg_color="#080b11")

        self.grab_set()
        self.focus_set()

        self._build_ui()

    def _build_ui(self):
        container = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color="#0d121d",
            border_width=1,
            border_color="#1e293b"
        )
        container.pack(fill="both", expand=True, padx=20, pady=20)

        # タイトル
        ctk.CTkLabel(
            container,
            text="📥 DLsite / FANZA 購入作品の同期・サムネイル更新",
            font=get_mac_font(size=16, weight="bold"),
            text_color="#00f0ff"
        ).pack(anchor="w", padx=16, pady=(16, 4))

        # 説明文
        desc = (
            "DLsiteやFANZAの購入作品を同期し、公式商品ページの画像（ジャケット）や\n"
            "ジャンル・タグ情報を自動適用します。未インストール作品も登録・管理できます。"
        )
        ctk.CTkLabel(
            container,
            text=desc,
            font=get_mac_font(size=11),
            text_color="#94a3b8",
            justify="left"
        ).pack(anchor="w", padx=16, pady=(0, 12))

        # === タブビュー ===
        self.tabview = ctk.CTkTabview(
            container,
            fg_color="#080b11",
            segmented_button_fg_color="#0d121d",
            segmented_button_selected_color="#00f0ff",
            segmented_button_selected_hover_color="#00c8d7",
            segmented_button_unselected_color="#111827",
            segmented_button_unselected_hover_color="#1e293b"
        )
        self.tabview.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        tab_dlsite_login = self.tabview.add("🔵 DLsite ログイン自動取得")
        tab_fanza = self.tabview.add("🟣 FANZA 同期・取り込み")
        tab_manual = self.tabview.add("📄 HTMLファイル / テキスト貼り付け")

        # --- タブ1: DLsite ログイン自動取得 ---
        ctk.CTkLabel(
            tab_dlsite_login,
            text="DLsiteのログイン情報を入力して購入履歴を一括スクレイピング：",
            font=get_mac_font(size=11, weight="bold"),
            text_color="#ffffff"
        ).pack(anchor="w", padx=10, pady=(10, 8))

        form_box = ctk.CTkFrame(tab_dlsite_login, fg_color="transparent")
        form_box.pack(fill="x", padx=10, pady=(0, 10))

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
            tab_dlsite_login,
            text="🚀 DLsiteにログインして自動スクレイピング・画像同期",
            height=36,
            corner_radius=18,
            fg_color="#ff007a",
            hover_color="#d60066",
            text_color="#ffffff",
            font=get_mac_font(size=12, weight="bold"),
            command=self._start_dlsite_auto_login
        )
        self.auto_fetch_btn.pack(anchor="w", padx=10, pady=(6, 8))

        ctk.CTkLabel(
            tab_dlsite_login,
            text="※ パスワードは保存されず、購入履歴取得の通信のみに安全に使用されます。",
            font=get_mac_font(size=10),
            text_color="#737099"
        ).pack(anchor="w", padx=10)

        # --- タブ2: FANZA 同期・取り込み ---
        ctk.CTkLabel(
            tab_fanza,
            text="FANZAの購入作品を取り込み、公式画像・ジャンル・タグに差し替えます：",
            font=get_mac_font(size=11, weight="bold"),
            text_color="#ffffff"
        ).pack(anchor="w", padx=10, pady=(10, 8))

        fanza_row1 = ctk.CTkFrame(tab_fanza, fg_color="transparent")
        fanza_row1.pack(fill="x", padx=10, pady=(0, 8))

        ctk.CTkButton(
            fanza_row1,
            text="🌐 FANZA購入済み一覧を開く (ブラウザ)",
            width=230,
            height=30,
            corner_radius=8,
            fg_color="#4f1d6b",
            hover_color="#6e2b94",
            text_color="#ffffff",
            font=get_mac_font(size=11, weight="bold"),
            command=lambda: webbrowser.open("https://www.dmm.co.jp/digital/-/mylibrary/")
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            fanza_row1,
            text="📄 FANZA購入HTMLを選択...",
            width=180,
            height=30,
            corner_radius=8,
            fg_color="#8338ec",
            hover_color="#6c2bd9",
            text_color="#ffffff",
            font=get_mac_font(size=11),
            command=self._browse_fanza_html
        ).pack(side="left")

        self.fanza_text_area = ctk.CTkTextbox(
            tab_fanza,
            height=90,
            corner_radius=10,
            fg_color="#0c0920",
            border_width=1,
            border_color="#271f54",
            text_color="#ffffff",
            font=get_mac_font(size=11)
        )
        self.fanza_text_area.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self.fanza_text_area.insert("1.0", "ここにFANZAの作品名やCID（例: d_186424、妻獲り迷宮）またはHTMLソースを貼り付けてください")

        self.fanza_sync_btn = ctk.CTkButton(
            tab_fanza,
            text="🟣 FANZA作品を同期＆商品画像に差し替え",
            height=34,
            corner_radius=17,
            fg_color="#8338ec",
            hover_color="#6c2bd9",
            text_color="#ffffff",
            font=get_mac_font(size=11, weight="bold"),
            command=self._start_fanza_sync
        )
        self.fanza_sync_btn.pack(anchor="w", padx=10, pady=(0, 8))

        # --- タブ3: HTML / 手動貼り付け (汎用 / DLsite) ---
        row_browse = ctk.CTkFrame(tab_manual, fg_color="transparent")
        row_browse.pack(fill="x", padx=10, pady=(8, 8))

        ctk.CTkButton(
            row_browse,
            text="🌐 DLsite購入履歴を開く",
            width=170,
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
            width=190,
            height=30,
            corner_radius=8,
            fg_color="#3a86ff",
            hover_color="#2b68cb",
            text_color="#ffffff",
            font=get_mac_font(size=11),
            command=self._browse_dlsite_html
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
        self.text_area.insert("1.0", "ここにRJ番号（例: RJ01360185）またはHTMLを直接貼り付けてください")

        # プログレスバー & ステータス
        self.progress_bar = ctk.CTkProgressBar(container, height=6, corner_radius=3, fg_color="#111827", progress_color="#00f0ff")
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=16, pady=(0, 4))

        self.status_lbl = ctk.CTkLabel(
            container,
            text="準備完了",
            font=get_mac_font(size=11),
            text_color="#64748b"
        )
        self.status_lbl.pack(anchor="w", padx=16, pady=(0, 10))

        # 下部ボタン
        btn_box = ctk.CTkFrame(container, fg_color="transparent")
        btn_box.pack(fill="x", padx=16, pady=(0, 12))

        self.start_import_btn = ctk.CTkButton(
            btn_box,
            text="📥 DLsite同期を実行",
            height=36,
            corner_radius=4,
            fg_color="#00f0ff",
            hover_color="#00c8d7",
            text_color="#080b11",
            font=get_mac_font(size=12, weight="bold"),
            command=self._start_dlsite_import
        )
        self.start_import_btn.pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            btn_box,
            text="閉じる",
            width=80,
            height=36,
            corner_radius=4,
            fg_color="#111827",
            hover_color="#1e293b",
            text_color="#94a3b8",
            border_width=1,
            border_color="#1e293b",
            font=get_mac_font(size=11),
            command=self.destroy
        ).pack(side="right")

    # === DLsite 処理 ===
    def _start_dlsite_auto_login(self):
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

                self.text_area.delete("1.0", "end")
                self.text_area.insert("1.0", "\n".join(rjs))
                self.status_lbl.configure(text=f"{len(rjs)} 件の作品を検出しました。画像・メタデータ同期を開始します...", text_color="#3a86ff")
                self._run_dlsite_sync_worker(rjs)

            self.after(0, on_login_done)

        threading.Thread(target=worker, daemon=True).start()

    def _browse_dlsite_html(self):
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

    def _start_dlsite_import(self):
        raw_text = self.text_area.get("1.0", "end").strip()
        rjs = DLsitePurchaseImporter.extract_rj_codes_from_text(raw_text)

        if not rjs:
            messagebox.showwarning("入力不足", "有効なRJ番号が見つかりませんでした。「DLsite ログイン自動取得」を行うか、RJコードを入力してください。")
            return

        self._run_dlsite_sync_worker(rjs)

    def _run_dlsite_sync_worker(self, rjs):
        self.start_import_btn.configure(state="disabled")
        self.auto_fetch_btn.configure(state="disabled")
        self.status_lbl.configure(text=f"{len(rjs)} 件の公式画像・メタデータを同期中...", text_color="#3a86ff")

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
            self.after(0, lambda: self._on_dlsite_finished(matched, added, len(rjs)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_dlsite_finished(self, matched: int, added: int, total: int):
        self.progress_bar.set(1.0)
        self.status_lbl.configure(
            text=f"完了！ PC内照合・画像更新: {matched} 件 | 未ダウンロード登録: {added} 件",
            text_color="#2b7a4b"
        )
        messagebox.showinfo(
            "DLsite取り込み完了",
            f"DLsite作品の同期が完了しました！\n\n"
            f"・対象作品数: {total} 件\n"
            f"・PC内ゲームと照合（公式画像差し替え済み）: {matched} 件\n"
            f"・新規登録（未ダウンロード作品）: {added} 件"
        )
        if self.on_complete:
            self.on_complete()
        self.destroy()

    # === FANZA 処理 ===
    def _browse_fanza_html(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="FANZA購入履歴・マイライブラリのHTMLファイルを選択",
            filetypes=[("HTML Files", "*.html;*.htm"), ("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if path:
            items = FANZAPurchaseImporter.extract_from_html_file(path)
            if items:
                lines = [it["value"] for it in items]
                self.fanza_text_area.delete("1.0", "end")
                self.fanza_text_area.insert("1.0", "\n".join(lines))
                self.status_lbl.configure(text=f"HTMLから {len(items)} 件のFANZA作品を検出しました！", text_color="#a855f7")
            else:
                messagebox.showwarning("警告", "選択されたファイルからFANZA作品情報が見つかりませんでした。")

    def _start_fanza_sync(self):
        raw_text = self.fanza_text_area.get("1.0", "end").strip()
        items = FANZAPurchaseImporter.extract_cids_and_titles(raw_text)

        if not items:
            messagebox.showwarning("入力不足", "有効なCIDまたは作品名が見つかりませんでした。HTMLまたは作品名を入力してください。")
            return

        self.fanza_sync_btn.configure(state="disabled")
        self.progress_bar.set(0)
        self.status_lbl.configure(text=f"{len(items)} 件のFANZA公式画像・メタデータを同期中...", text_color="#a855f7")

        def worker():
            def on_progress(cur, total, val):
                val_prog = cur / max(1, total)
                self.after(0, lambda: self.progress_bar.set(val_prog))
                self.after(0, lambda: self.status_lbl.configure(text=f"FANZA同期中: {cur}/{total} ({val})", text_color="#c084fc"))

            matched, added = FANZAPurchaseImporter.sync_fanza_games(
                items,
                self.config_mgr,
                self.icon_helper,
                progress_callback=on_progress
            )
            self.after(0, lambda: self._on_fanza_finished(matched, added, len(items)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_fanza_finished(self, matched: int, added: int, total: int):
        self.progress_bar.set(1.0)
        self.fanza_sync_btn.configure(state="normal")
        self.status_lbl.configure(
            text=f"FANZA完了！ PC内照合・画像更新: {matched} 件 | 未ダウンロード登録: {added} 件",
            text_color="#2b7a4b"
        )
        messagebox.showinfo(
            "FANZA取り込み完了",
            f"FANZA作品の同期が完了しました！\n\n"
            f"・照合対象数: {total} 件\n"
            f"・PC内ゲームと照合（公式パッケージ画像に更新）: {matched} 件\n"
            f"・新規登録（未ダウンロード作品）: {added} 件"
        )
        if self.on_complete:
            self.on_complete()
        self.destroy()
