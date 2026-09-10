import os
import re
import threading
import webbrowser
from tkinter import filedialog, messagebox
import customtkinter as ctk
from font_manager import get_mac_font
from dlsite_purchase_importer import DLsitePurchaseImporter

class DLsitePurchaseDialog(ctk.CTkToplevel):
    """DLsiteの購入履歴（HTML・テキスト・RJ番号）を取り込むダイアログ"""

    def __init__(self, master, config_mgr, icon_helper, on_complete):
        super().__init__(master)
        self.config_mgr = config_mgr
        self.icon_helper = icon_helper
        self.on_complete = on_complete

        self.title("📥 DLsite購入履歴の取り込み")
        self.geometry("640x540")
        self.minsize(580, 480)
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
            text="📥 DLsite購入済み作品の取り込み・照合",
            font=get_mac_font(size=17, weight="bold"),
            text_color="#ffffff"
        ).pack(anchor="w", padx=16, pady=(16, 6))

        # 説明文
        desc = (
            "DLsiteのマイページ「購入履歴」から購入作品をライブラリに取り込みます。\n"
            "PC内にすでにあるゲームは自動照合され、未インストールの購入作品も登録・管理できます。"
        )
        ctk.CTkLabel(
            container,
            text=desc,
            font=get_mac_font(size=11),
            text_color="#9e9abf",
            justify="left"
        ).pack(anchor="w", padx=16, pady=(0, 14))

        # 方法1: ブラウザで開くボタン ＆ HTMLファイル選択
        step1_box = ctk.CTkFrame(container, corner_radius=12, fg_color="#181335", border_width=1, border_color="#2c2258")
        step1_box.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkLabel(
            step1_box,
            text="① ブラウザで購入履歴ページを開き、HTMLを保存する",
            font=get_mac_font(size=12, weight="bold"),
            text_color="#77aaf6"
        ).pack(anchor="w", padx=12, pady=(10, 4))

        row1 = ctk.CTkFrame(step1_box, fg_color="transparent")
        row1.pack(fill="x", padx=12, pady=(0, 10))

        ctk.CTkButton(
            row1,
            text="🌐 DLsite購入履歴ページを開く (ブラウザ)",
            width=240,
            height=32,
            corner_radius=8,
            fg_color="#2c2266",
            hover_color="#3d308c",
            text_color="#ffffff",
            font=get_mac_font(size=11, weight="bold"),
            command=self._open_dlsite_mypage
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            row1,
            text="📄 保存したHTMLファイルを選択...",
            width=200,
            height=32,
            corner_radius=8,
            fg_color="#3a86ff",
            hover_color="#2b68cb",
            text_color="#ffffff",
            font=get_mac_font(size=11, weight="bold"),
            command=self._browse_html_file
        ).pack(side="left")

        # 方法2: RJ番号またはHTMLテキストを直接貼り付け
        ctk.CTkLabel(
            container,
            text="② または、RJ番号一覧やHTMLソースを直接貼り付ける:",
            font=get_mac_font(size=12, weight="bold"),
            text_color="#77aaf6"
        ).pack(anchor="w", padx=16, pady=(0, 6))

        self.text_area = ctk.CTkTextbox(
            container,
            height=160,
            corner_radius=10,
            fg_color="#0c0920",
            border_width=1,
            border_color="#271f54",
            text_color="#ffffff",
            font=get_mac_font(size=11)
        )
        self.text_area.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        self.text_area.insert("1.0", "ここにRJ番号（例: RJ01360185）やHTMLソースを貼り付けてください...")

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

        # アクションボタン
        btn_box = ctk.CTkFrame(container, fg_color="transparent")
        btn_box.pack(fill="x", padx=16, pady=(0, 12))

        self.start_btn = ctk.CTkButton(
            btn_box,
            text="📥 取り込みを開始する",
            height=36,
            corner_radius=18,
            fg_color="#3a86ff",
            hover_color="#2b68cb",
            text_color="#ffffff",
            font=get_mac_font(size=12, weight="bold"),
            command=self._start_import
        )
        self.start_btn.pack(side="right", padx=(8, 0))

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

    def _open_dlsite_mypage(self):
        webbrowser.open("https://www.dlsite.com/maniax/mypage/userbuy")

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
            messagebox.showwarning("入力不足", "有効なRJ番号が見つかりませんでした。HTMLまたはRJコードを貼り付けてください。")
            return

        self.start_btn.configure(state="disabled")
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
            f"・対象RJコード: {total} 件\n"
            f"・PC内ゲームと照合済み: {matched} 件\n"
            f"・新規登録（未ダウンロード作品）: {added} 件"
        )
        if self.on_complete:
            self.on_complete()
        self.destroy()
