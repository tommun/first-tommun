import os
import re
import subprocess
import threading
import urllib.request
from PIL import Image, ImageTk
import customtkinter as ctk
from typing import Dict, Any, Callable, Optional, List

from save_script_detector import SaveScriptDetector
from dlsite_metadata import DLsiteMetadataFetcher
from fanza_metadata import FANZAMetadataFetcher

class GameDetailView(ctk.CTkFrame):
    """
    Steamスタイルのゲーム固有詳細ビュー
    - ヒーローバナー＆タイトル
    - 巨大な「▶ プレイ」ボタン
    - プレイ時間、最終プレイ日
    - セーブデータ進捗＆スロット数表示
    - スクリプト/MOD直接アクセススイッチ
    - ストアからスクレイピングしたスクリーンショットギャラリー
    - 作品詳細・あらすじ・タグ
    """

    def __init__(
        self,
        parent,
        game: Dict[str, Any],
        icon_helper,
        on_back: Callable[[], None],
        on_launch: Callable[[Dict[str, Any]], None],
        on_open_store: Optional[Callable[[str], None]] = None,
        on_open_settings: Optional[Callable[[Dict[str, Any]], None]] = None,
        **kwargs
    ):
        super().__init__(parent, fg_color="#0b0f19", **kwargs)
        self.game = game
        self.icon_helper = icon_helper
        self.on_back = on_back
        self.on_launch = on_launch
        self.on_open_store = on_open_store
        self.on_open_settings = on_open_settings

        self.sample_photos = []  # GC防止

        self._build_ui()
        self._load_async_metadata()

    def _build_ui(self):
        # 1. ナビゲーションバー（戻るボタン）
        nav_frame = ctk.CTkFrame(self, fg_color="#101726", height=45, corner_radius=0)
        nav_frame.pack(fill="x", side="top")
        nav_frame.pack_propagate(False)

        back_btn = ctk.CTkButton(
            nav_frame,
            text="◀ ライブラリに戻る",
            command=self.on_back,
            fg_color="#1e293b",
            hover_color="#334155",
            text_color="#38bdf8",
            font=("Segoe UI", 12, "bold"),
            width=140,
            height=32
        )
        back_btn.pack(side="left", padx=16, pady=6)

        title_short = self.game.get("name", "ゲーム詳細")
        if len(title_short) > 40:
            title_short = title_short[:40] + "..."
        ctk.CTkLabel(
            nav_frame,
            text=f"ライブラリ > {title_short}",
            font=("Segoe UI", 11),
            text_color="#64748b"
        ).pack(side="left", padx=8)

        # 2. メインスクロールエリア
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=20, pady=10)

        # --- ヒーローバナーエリア ---
        self.hero_frame = ctk.CTkFrame(self.scroll, fg_color="#131c2e", corner_radius=12, border_width=1, border_color="#1e293b")
        self.hero_frame.pack(fill="x", pady=(0, 16))

        # ヒーローコンテンツ（内包）
        hero_inner = ctk.CTkFrame(self.hero_frame, fg_color="transparent")
        hero_inner.pack(fill="x", padx=24, pady=20)

        # 左側: アイコン/ジャケット（アスペクト比保持コンテナ）
        self.cover_box = ctk.CTkFrame(hero_inner, fg_color="#0f172a", corner_radius=8, width=240, height=180)
        self.cover_box.pack(side="left", padx=(0, 24))
        self.cover_box.pack_propagate(False)

        self.cover_label = ctk.CTkLabel(self.cover_box, text="")
        self.cover_label.place(relx=0.5, rely=0.5, anchor="center")
        self._set_cover_image()

        # 右側: タイトル、サークル、バッジ、メタ情報
        info_col = ctk.CTkFrame(hero_inner, fg_color="transparent")
        info_col.pack(side="left", fill="both", expand=True)

        # プラットフォーム＆ジャンルバッジ
        badge_frame = ctk.CTkFrame(info_col, fg_color="transparent")
        badge_frame.pack(fill="x", anchor="w", pady=(0, 4))

        plat = self.game.get("platform", "PC")
        plat_color = "#38bdf8" if plat == "DLsite" else ("#ec4899" if plat == "FANZA" else "#a855f7")
        ctk.CTkLabel(
            badge_frame,
            text=f"  {plat}  ",
            fg_color=plat_color,
            text_color="#0f172a",
            font=("Segoe UI", 10, "bold"),
            corner_radius=4
        ).pack(side="left", padx=(0, 8))

        genre = self.game.get("genre") or self.game.get("category") or "ゲーム"
        ctk.CTkLabel(
            badge_frame,
            text=f"  {genre}  ",
            fg_color="#1e293b",
            text_color="#94a3b8",
            font=("Segoe UI", 10),
            corner_radius=4
        ).pack(side="left", padx=(0, 8))

        rj = self.game.get("rj_code")
        if rj:
            ctk.CTkLabel(
                badge_frame,
                text=f" {rj} ",
                fg_color="#0284c7",
                text_color="#ffffff",
                font=("Segoe UI", 10, "bold"),
                corner_radius=4
            ).pack(side="left")

        # ゲームタイトル
        title_label = ctk.CTkLabel(
            info_col,
            text=self.game.get("name", "名称未設定"),
            font=("Segoe UI", 20, "bold"),
            text_color="#f8fafc",
            anchor="w",
            justify="left",
            wraplength=620
        )
        title_label.pack(fill="x", anchor="w", pady=(4, 6))

        # サークル/作者
        author = self.game.get("author", "不明")
        ctk.CTkLabel(
            info_col,
            text=f"メーカー / サークル: {author}",
            font=("Segoe UI", 12),
            text_color="#94a3b8",
            anchor="w"
        ).pack(fill="x", anchor="w", pady=(0, 12))

        # --- アクションバー (Steam風: プレイボタン & プレイ統計) ---
        action_bar = ctk.CTkFrame(info_col, fg_color="#0f172a", corner_radius=8, border_width=1, border_color="#1e293b")
        action_bar.pack(fill="x", pady=(4, 0))

        # プレイボタン
        is_installed = self.game.get("is_installed", True)
        if is_installed:
            play_btn = ctk.CTkButton(
                action_bar,
                text="▶  プレイ",
                command=lambda: self.on_launch(self.game),
                fg_color="#06b6d4",
                hover_color="#0891b2",
                text_color="#0b0f19",
                font=("Segoe UI", 15, "bold"),
                width=160,
                height=44,
                corner_radius=6
            )
        else:
            play_btn = ctk.CTkButton(
                action_bar,
                text="⬇️  ストア / ダウンロード",
                command=self._open_store_action,
                fg_color="#10b981",
                hover_color="#059669",
                text_color="#ffffff",
                font=("Segoe UI", 13, "bold"),
                width=190,
                height=44,
                corner_radius=6
            )
        play_btn.pack(side="left", padx=14, pady=10)

        # プレイ時間 & 最終プレイ日
        stats_frame = ctk.CTkFrame(action_bar, fg_color="transparent")
        stats_frame.pack(side="left", padx=16, pady=10)

        last_play = self.game.get("last_played") or "未プレイ"
        ctk.CTkLabel(
            stats_frame,
            text=f"最終プレイ日: {last_play}",
            font=("Segoe UI", 11),
            text_color="#94a3b8",
            anchor="w"
        ).pack(anchor="w")

        play_seconds = self.game.get("play_time_seconds", 0)
        play_time_str = self._format_play_time(play_seconds)
        ctk.CTkLabel(
            stats_frame,
            text=f"総プレイ時間: {play_time_str}",
            font=("Segoe UI", 12, "bold"),
            text_color="#38bdf8",
            anchor="w"
        ).pack(anchor="w")

        # クイックツールバー（フォルダ、ストア、設定）
        tools_frame = ctk.CTkFrame(action_bar, fg_color="transparent")
        tools_frame.pack(side="right", padx=14, pady=10)

        ctk.CTkButton(
            tools_frame,
            text="📂 フォルダ",
            command=self._open_game_folder,
            fg_color="#1e293b",
            hover_color="#334155",
            text_color="#e2e8f0",
            font=("Segoe UI", 11),
            width=85,
            height=32
        ).pack(side="left", padx=4)

        if self.game.get("url") or self.game.get("fanza_url") or self.game.get("rj_code"):
            ctk.CTkButton(
                tools_frame,
                text="🌐 ストア",
                command=self._open_store_action,
                fg_color="#1e293b",
                hover_color="#334155",
                text_color="#38bdf8",
                font=("Segoe UI", 11),
                width=75,
                height=32
            ).pack(side="left", padx=4)

        if self.on_open_settings:
            ctk.CTkButton(
                tools_frame,
                text="⚙️",
                command=lambda: self.on_open_settings(self.game),
                fg_color="#1e293b",
                hover_color="#334155",
                text_color="#94a3b8",
                font=("Segoe UI", 12),
                width=36,
                height=32
            ).pack(side="left", padx=4)

        # --- 2カラム構成（左: セーブ・改造スイッチ・詳細、右: スクリーンショット） ---
        body_grid = ctk.CTkFrame(self.scroll, fg_color="transparent")
        body_grid.pack(fill="both", expand=True)
        body_grid.columnconfigure(0, weight=4)
        body_grid.columnconfigure(1, weight=6)

        # 左カラム: セーブデータ進捗 ＆ スクリプト/MOD スイッチ
        left_panel = ctk.CTkFrame(body_grid, fg_color="transparent")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        self._build_save_and_script_cards(left_panel)
        self._build_info_card(left_panel)

        # 右カラム: スクリーンショット ギャラリー
        right_panel = ctk.CTkFrame(body_grid, fg_color="transparent")
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        self._build_screenshot_gallery(right_panel)

    def _build_save_and_script_cards(self, parent):
        # 1. セーブデータ進捗カード
        save_card = ctk.CTkFrame(parent, fg_color="#131c2e", corner_radius=10, border_width=1, border_color="#1e293b")
        save_card.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            save_card,
            text="💾  セーブデータ＆進捗状況",
            font=("Segoe UI", 13, "bold"),
            text_color="#38bdf8"
        ).pack(anchor="w", padx=16, pady=(12, 6))

        game_path = self.game.get("path", "")
        folder_path = self.game.get("folder_path", "")
        saves_info = SaveScriptDetector.detect_saves(game_path, folder_path)

        count = saves_info["count"]
        latest = saves_info["latest_date"] or "なし"
        save_dir = saves_info["save_dir"]

        info_text = f"・検出セーブスロット: {count} 件\n・最新セーブ更新日時: {latest}"
        ctk.CTkLabel(
            save_card,
            text=info_text,
            font=("Segoe UI", 11),
            text_color="#cbd5e1",
            justify="left",
            anchor="w"
        ).pack(anchor="w", padx=16, pady=(0, 8))

        btn_row = ctk.CTkFrame(save_card, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 12))

        if save_dir and os.path.exists(save_dir):
            ctk.CTkButton(
                btn_row,
                text="📂 セーブフォルダを開く",
                command=lambda: os.startfile(save_dir),
                fg_color="#1e293b",
                hover_color="#334155",
                text_color="#f8fafc",
                font=("Segoe UI", 11),
                height=30
            ).pack(side="left")

        # 2. スクリプト・MOD 直接アクセススイッチ
        script_card = ctk.CTkFrame(parent, fg_color="#131c2e", corner_radius=10, border_width=1, border_color="#1e293b")
        script_card.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            script_card,
            text="🛠️  スクリプト / MOD / 改造スイッチ",
            font=("Segoe UI", 13, "bold"),
            text_color="#a855f7"
        ).pack(anchor="w", padx=16, pady=(12, 6))

        engine_info = SaveScriptDetector.detect_scripts_and_engine(game_path, folder_path)
        engine_name = engine_info["engine"]
        s_desc = engine_info["description"]
        s_dir = engine_info["script_dir"]

        eng_text = f"・検出エンジン: {engine_name}\n・対象データ: {s_desc}"
        ctk.CTkLabel(
            script_card,
            text=eng_text,
            font=("Segoe UI", 11),
            text_color="#cbd5e1",
            justify="left",
            anchor="w"
        ).pack(anchor="w", padx=16, pady=(0, 8))

        s_btn_row = ctk.CTkFrame(script_card, fg_color="transparent")
        s_btn_row.pack(fill="x", padx=16, pady=(0, 12))

        if s_dir and os.path.exists(s_dir):
            ctk.CTkButton(
                s_btn_row,
                text="📂 スクリプトフォルダを開く",
                command=lambda: os.startfile(s_dir),
                fg_color="#1e293b",
                hover_color="#334155",
                text_color="#e2e8f0",
                font=("Segoe UI", 11),
                height=30
            ).pack(side="left", padx=(0, 8))

            # VS Code で開くスイッチ（入っていれば）
            ctk.CTkButton(
                s_btn_row,
                text="💻 VS Code で開く",
                command=lambda: self._open_vscode(s_dir),
                fg_color="#4338ca",
                hover_color="#4f46e5",
                text_color="#ffffff",
                font=("Segoe UI", 11),
                height=30
            ).pack(side="left")

    def _build_info_card(self, parent):
        info_card = ctk.CTkFrame(parent, fg_color="#131c2e", corner_radius=10, border_width=1, border_color="#1e293b")
        info_card.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            info_card,
            text="📋  作品概要＆タグ",
            font=("Segoe UI", 13, "bold"),
            text_color="#f8fafc"
        ).pack(anchor="w", padx=16, pady=(12, 6))

        # タグ
        tags = self.game.get("tags", [])
        if tags:
            tag_box = ctk.CTkFrame(info_card, fg_color="transparent")
            tag_box.pack(fill="x", padx=16, pady=(0, 8))
            # 最大10個
            for t in tags[:10]:
                ctk.CTkLabel(
                    tag_box,
                    text=f" #{t} ",
                    fg_color="#1e293b",
                    text_color="#94a3b8",
                    font=("Segoe UI", 10),
                    corner_radius=4
                ).pack(side="left", padx=(0, 4), pady=2)

        # あらすじ・説明文
        desc = self.game.get("description", "")
        if not desc:
            desc = "作品情報取得中またはローカル登録ゲームです。"
        self.desc_label = ctk.CTkLabel(
            info_card,
            text=desc,
            font=("Segoe UI", 11),
            text_color="#94a3b8",
            wraplength=380,
            justify="left",
            anchor="w"
        )
        self.desc_label.pack(fill="x", anchor="w", padx=16, pady=(0, 12))

    def _build_screenshot_gallery(self, parent):
        self.gallery_card = ctk.CTkFrame(parent, fg_color="#131c2e", corner_radius=10, border_width=1, border_color="#1e293b")
        self.gallery_card.pack(fill="both", expand=True, pady=(0, 12))

        header_row = ctk.CTkFrame(self.gallery_card, fg_color="transparent")
        header_row.pack(fill="x", padx=16, pady=(12, 6))

        ctk.CTkLabel(
            header_row,
            text="🖼️  スクリーンショット・メディア",
            font=("Segoe UI", 13, "bold"),
            text_color="#38bdf8"
        ).pack(side="left")

        self.status_label = ctk.CTkLabel(
            header_row,
            text="",
            font=("Segoe UI", 10),
            text_color="#64748b"
        )
        self.status_label.pack(side="right")

        # メインプレビュー画像
        self.main_preview = ctk.CTkLabel(self.gallery_card, text="", height=280, fg_color="#0a0f1d", corner_radius=8)
        self.main_preview.pack(fill="x", padx=16, pady=(0, 10))

        # サムネイルスクロール
        self.thumbs_scroll = ctk.CTkScrollableFrame(self.gallery_card, fg_color="transparent", orientation="horizontal", height=85)
        self.thumbs_scroll.pack(fill="x", padx=16, pady=(0, 12))

    def _set_cover_image(self):
        icon_path = self.game.get("icon_path")
        if icon_path and os.path.exists(icon_path):
            try:
                pil_img = Image.open(icon_path)
                orig_w, orig_h = pil_img.size
                if orig_w > 0 and orig_h > 0:
                    max_w, max_h = 240, 180
                    ratio = min(max_w / orig_w, max_h / orig_h)
                    new_w = max(1, int(orig_w * ratio))
                    new_h = max(1, int(orig_h * ratio))

                    resized = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    ctk_img = ctk.CTkImage(light_image=resized, dark_image=resized, size=(new_w, new_h))
                    self.sample_photos.append(ctk_img)
                    self.cover_label.configure(image=ctk_img, text="", width=new_w, height=new_h)
                    return
            except Exception:
                pass
        self.cover_label.configure(text="NO IMAGE\n(公式画像未取得)", font=("Segoe UI", 11), text_color="#64748b")

    def _format_play_time(self, seconds: int) -> str:
        if seconds <= 0:
            return "0分"
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        if hours > 0:
            return f"{hours}時間 {mins}分"
        return f"{mins}分"

    def _open_game_folder(self):
        folder = self.game.get("folder_path")
        if not folder or not os.path.exists(folder):
            path = self.game.get("path")
            if path and os.path.exists(path):
                folder = os.path.dirname(path)
        if folder and os.path.exists(folder):
            os.startfile(folder)

    def _open_vscode(self, path: str):
        try:
            subprocess.Popen(["code", path], shell=True)
        except Exception:
            os.startfile(path)

    def _open_store_action(self):
        url = self.game.get("url") or self.game.get("fanza_url")
        if not url:
            rj = self.game.get("rj_code")
            if rj:
                url = f"https://www.dlsite.com/maniax/work/=/product_id/{rj}.html"
            cid = self.game.get("fanza_cid")
            if cid:
                url = f"https://www.dmm.co.jp/dc/doujin/-/detail/=/cid={cid}/"

        if url:
            if self.on_open_store:
                self.on_open_store(url)
            else:
                import webbrowser
                webbrowser.open(url)

    def _load_async_metadata(self):
        """スクリーンショットや作品説明文を非同期でダウンロード・表示"""
        def worker():
            sample_urls = self.game.get("sample_images", [])
            desc = self.game.get("description", "")

            # サンプルURLがまだない場合はスクレイピング試行
            if not sample_urls or not desc:
                rj = self.game.get("rj_code")
                if rj:
                    meta = DLsiteMetadataFetcher.fetch_by_rj(rj)
                    if meta:
                        sample_urls = meta.get("sample_images", [])
                        desc = meta.get("description", desc)
                        self.game["sample_images"] = sample_urls
                        self.game["description"] = desc
                elif self.game.get("fanza_cid"):
                    meta = FANZAMetadataFetcher.fetch_by_cid(self.game["fanza_cid"])
                    if meta:
                        sample_urls = meta.get("sample_images", [])
                        self.game["sample_images"] = sample_urls

            if desc and hasattr(self, "desc_label"):
                self.after(0, lambda: self.desc_label.configure(text=desc))

            if not sample_urls:
                self.after(0, lambda: self.status_label.configure(text="スクリーンショットなし"))
                return

            self.after(0, lambda: self.status_label.configure(text=f"{len(sample_urls)}枚取得中..."))

            # 画像をDLしてサムネイル表示
            images_pil = []
            for idx, u in enumerate(sample_urls[:8]):
                try:
                    headers = {"User-Agent": "Mozilla/5.0"}
                    req = urllib.request.Request(u, headers=headers)
                    with urllib.request.urlopen(req, timeout=6) as res:
                        img_data = res.read()
                    import io
                    pil_img = Image.open(io.BytesIO(img_data))
                    images_pil.append(pil_img)
                    self.after(0, lambda i=pil_img, count=idx+1: self._add_gallery_item(i, count))
                except Exception:
                    continue

            self.after(0, lambda: self.status_label.configure(text=f"{len(images_pil)}枚のスクリーンショット"))

        threading.Thread(target=worker, daemon=True).start()

    def _add_gallery_item(self, pil_img: Image.Image, count: int):
        # 最初の1枚をメインプレビューに設定
        if count == 1:
            self._set_main_preview(pil_img)

        # サムネイル
        thumb = pil_img.copy()
        thumb.thumbnail((110, 75), Image.Resampling.LANCZOS)
        ctk_thumb = ctk.CTkImage(light_image=thumb, dark_image=thumb, size=thumb.size)
        self.sample_photos.append(ctk_thumb)

        btn = ctk.CTkButton(
            self.thumbs_scroll,
            image=ctk_thumb,
            text="",
            width=thumb.size[0] + 4,
            height=thumb.size[1] + 4,
            fg_color="#0f172a",
            hover_color="#38bdf8",
            corner_radius=4,
            command=lambda img=pil_img: self._set_main_preview(img)
        )
        btn.pack(side="left", padx=4, pady=2)

    def _set_main_preview(self, pil_img: Image.Image):
        # メインプレビューをアスペクト比保持でリサイズ
        w, h = pil_img.size
        if w <= 0 or h <= 0:
            return
        max_w, max_h = 540, 320
        ratio = min(max_w / w, max_h / h)
        target_w = max(1, int(w * ratio))
        target_h = max(1, int(h * ratio))

        resized = pil_img.copy().resize((target_w, target_h), Image.Resampling.LANCZOS)
        ctk_main = ctk.CTkImage(light_image=resized, dark_image=resized, size=(target_w, target_h))
        self.sample_photos.append(ctk_main)
        self.main_preview.configure(image=ctk_main, text="", width=target_w, height=target_h)
