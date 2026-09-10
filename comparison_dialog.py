import os
import subprocess
from pathlib import Path
import tkinter as tk
import customtkinter as ctk
from typing import List, Dict, Any, Optional, Callable
from game_analyzer import GameAnalyzer
from font_manager import get_mac_font

class ComparisonDialog(ctk.CTkToplevel):
    """同一ゲームのバージョン・ファイル差分・セーブ進行度の比較と移行を行うモーダルダイアログ"""

    def __init__(self, master, game_group: List[Dict[str, Any]], on_refresh: Optional[Callable] = None):
        super().__init__(master)
        self.game_group = game_group
        self.on_refresh = on_refresh

        self.title("🔄 同一ゲームの検出・進行度比較")
        self.geometry("820x560")
        self.minsize(700, 480)
        self.configure(fg_color="#080617")

        # モーダル化
        self.grab_set()
        self.focus_set()

        self._build_ui()

    def _build_ui(self):
        # メインコンテナ
        main_frame = ctk.CTkFrame(
            self,
            corner_radius=16,
            fg_color="#121028",
            border_width=1,
            border_color="#221e4a"
        )
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # ヘッダー
        title_text = self.game_group[0].get("name", "ゲーム詳細比較")
        header_lbl = ctk.CTkLabel(
            main_frame,
            text=f"🎮 {title_text}",
            font=get_mac_font(size=20, weight="bold"),
            text_color="#ffffff"
        )
        header_lbl.pack(anchor="w", padx=20, pady=(15, 5))

        desc_lbl = ctk.CTkLabel(
            main_frame,
            text=f"同じゲームが {len(self.game_group)} 箇所で検出されました。バージョンの違いやセーブデータの進行状況を確認できます。",
            font=get_mac_font(size=13),
            text_color="#8d89b0"
        )
        desc_lbl.pack(anchor="w", padx=20, pady=(0, 15))

        # スクロール可能カード比較エリア
        scroll_frame = ctk.CTkScrollableFrame(main_frame, corner_radius=8)
        scroll_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        # 2つ以上あるアイテムの解析情報を収集
        analyzed_items = []
        for g in self.game_group:
            folder_p = g.get("folder_path", os.path.dirname(g.get("path", "")))
            exe_p = g.get("path", "")
            is_standalone = g.get("is_standalone", False)

            save_info = GameAnalyzer.analyze_save_progress(folder_p, exe_p, is_standalone)
            stat = os.stat(exe_p) if os.path.exists(exe_p) else None
            mtime = stat.st_mtime if stat else 0
            size_mb = round(stat.st_size / (1024 * 1024), 2) if stat else 0

            analyzed_items.append({
                "game": g,
                "folder": folder_p,
                "path": exe_p,
                "mtime": mtime,
                "size_mb": size_mb,
                "save": save_info
            })

        # 最新更新日順にソート（先頭が一番新しいexe）
        analyzed_items.sort(key=lambda x: x["mtime"], reverse=True)

        for idx, item in enumerate(analyzed_items):
            self._create_game_card(scroll_frame, item, is_newest=(idx == 0))

        # 下部ボタンエリア
        footer_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        footer_frame.pack(fill="x", padx=15, pady=(0, 10))

        # セーブ移行可能か判定（2つ以上ある場合）
        if len(analyzed_items) >= 2:
            migrate_btn = ctk.CTkButton(
                footer_frame,
                text="📦 古い版から最新版へセーブデータを引き継ぐ",
                fg_color="#2b7a4b",
                hover_color="#1e5835",
                font=get_mac_font(size=13, weight="bold"),
                command=lambda: self._migrate_save_data(analyzed_items)
            )
            migrate_btn.pack(side="left", padx=5)

        close_btn = ctk.CTkButton(
            footer_frame,
            text="閉じる",
            fg_color="gray30",
            hover_color="gray40",
            font=get_mac_font(size=12),
            command=self.destroy
        )
        close_btn.pack(side="right", padx=5)

    def _create_game_card(self, parent, item: Dict[str, Any], is_newest: bool):
        card = ctk.CTkFrame(parent, corner_radius=8, fg_color=("gray85", "gray20"))
        card.pack(fill="x", pady=8, padx=5)

        top_row = ctk.CTkFrame(card, fg_color="transparent")
        top_row.pack(fill="x", padx=12, pady=(10, 5))

        # タイトル & バッジ
        name_lbl = ctk.CTkLabel(
            top_row,
            text=item["game"].get("name", ""),
            font=get_mac_font(size=15, weight="bold")
        )
        name_lbl.pack(side="left")

        if is_newest:
            new_badge = ctk.CTkLabel(
                top_row,
                text=" 最新バージョン ",
                fg_color="#1f538d",
                corner_radius=6,
                font=get_mac_font(size=11, weight="bold")
            )
            new_badge.pack(side="left", padx=10)

        # 進行度バッジ
        save = item["save"]
        if save["has_save"]:
            save_badge = ctk.CTkLabel(
                top_row,
                text=" ⭐ プレイ中 ",
                fg_color="#b8860b",
                corner_radius=6,
                font=get_mac_font(size=11, weight="bold")
            )
            save_badge.pack(side="left", padx=5)

        # 詳細情報行
        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.pack(fill="x", padx=12, pady=5)

        from datetime import datetime
        dt_str = datetime.fromtimestamp(item["mtime"]).strftime("%Y/%m/%d %H:%M") if item["mtime"] else "不明"
        
        info_text = (
            f"📁 実行ファイル: {item['path']}\n"
            f"📅 更新日時: {dt_str}  |  💾 ファイルサイズ: {item['size_mb']} MB\n"
            f"📊 進行度: {save['latest_save_str']} (セーブファイル数: {save['save_count']})"
        )
        if save.get("details"):
            info_text += f" - {save['details']}"

        info_lbl = ctk.CTkLabel(
            info_frame,
            text=info_text,
            justify="left",
            font=get_mac_font(size=12),
            text_color="gray80"
        )
        info_lbl.pack(anchor="w")

        # ボタン行
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(5, 10))

        launch_btn = ctk.CTkButton(
            btn_row,
            text="▶ このバージョンを起動",
            width=160,
            height=30,
            font=get_mac_font(size=12, weight="bold"),
            command=lambda p=item["path"], w=item["folder"]: self._launch_exe(p, w)
        )
        launch_btn.pack(side="left", padx=(0, 10))

        folder_btn = ctk.CTkButton(
            btn_row,
            text="📂 フォルダを開く",
            width=130,
            height=30,
            fg_color="gray35",
            hover_color="gray45",
            font=get_mac_font(size=12),
            command=lambda f=item["folder"]: self._open_folder(f)
        )
        folder_btn.pack(side="left")

    def _launch_exe(self, exe_path: str, work_dir: str):
        if not os.path.exists(exe_path):
            tk.messagebox.showerror("エラー", f"実行ファイルが見つかりません:\n{exe_path}")
            return
        try:
            cwd = work_dir if os.path.exists(work_dir) else os.path.dirname(exe_path)
            subprocess.Popen([exe_path], cwd=cwd)
            self.destroy()
        except Exception as e:
            tk.messagebox.showerror("起動エラー", f"起動に失敗しました:\n{e}")

    def _open_folder(self, folder_path: str):
        if os.path.exists(folder_path):
            os.startfile(folder_path)

    def _migrate_save_data(self, analyzed_items: List[Dict[str, Any]]):
        """セーブデータのあるアイテムから最新のアイテムへセーブをコピー"""
        # 最新版
        target = analyzed_items[0]
        # 最も新しいセーブデータを持つ古い版を探す
        source = None
        for item in analyzed_items[1:]:
            if item["save"]["has_save"]:
                if source is None or (item["save"]["latest_save_time"] or 0) > (source["save"]["latest_save_time"] or 0):
                    source = item

        if not source:
            tk.messagebox.showinfo("情報", "コピー元のセーブデータが見つかりませんでした。")
            return

        confirm = tk.messagebox.askyesno(
            "セーブデータ移行確認",
            f"以下の移行を行います。よろしいですか？\n\n"
            f"【コピー元 (旧)】:\n{source['folder']}\n"
            f"進行度: {source['save']['latest_save_str']}\n\n"
            f"【コピー先 (最新)】:\n{target['folder']}\n\n"
            f"※コピー先の既存セーブデータは安全のため自動バックアップされます。"
        )

        if confirm:
            ok, msg = GameAnalyzer.migrate_saves(source["folder"], target["folder"])
            if ok:
                tk.messagebox.showinfo("成功", msg)
                self.destroy()
                if self.on_refresh:
                    self.on_refresh()
            else:
                tk.messagebox.showerror("失敗", msg)
