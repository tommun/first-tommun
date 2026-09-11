import os
import sys
import subprocess
from typing import Optional

class StoreBrowserManager:
    """
    アプリケーション内包型WebView2ストアブラウザの起動・管理クラス
    外部ブラウザを立ち上げることなく、アプリ内でDLsite/FANZA/作品ページを直接閲覧可能。
    ログインセッションやCookieも自動永続化。
    """

    @classmethod
    def open_url(cls, url: str, title: str = "内蔵ストアブラウザ - DLsite & FANZA"):
        if not url:
            return

        # 実行パス解決
        current_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(current_dir, "store_browser_process.py")

        python_exe = sys.executable
        # PyInstaller (frozen) の場合
        if getattr(sys, 'frozen', False):
            # EXE自身に --webview-mode を渡して起動するか、同梱スクリプトを実行
            cmd = [sys.executable, "--store-browser", url, title]
            try:
                subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                return
            except Exception:
                pass

        cmd = [python_exe, script_path, "--url", url, "--title", title]
        try:
            subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except Exception as e:
            # フォールバックとして標準ブラウザで開く
            import webbrowser
            webbrowser.open(url)

    @classmethod
    def open_dlsite(cls, rj_code: str = ""):
        if rj_code:
            url = f"https://www.dlsite.com/maniax/work/=/product_id/{rj_code}.html"
            title = f"DLsite - {rj_code}"
        else:
            url = "https://www.dlsite.com/maniax/"
            title = "DLsite マニアックス (内蔵ストア)"
        cls.open_url(url, title)

    @classmethod
    def open_dlsite_mypage(cls):
        url = "https://www.dlsite.com/maniax/mypage/userbuy"
        cls.open_url(url, "DLsite - 購入履歴 / マイページ")

    @classmethod
    def open_fanza(cls, cid: str = ""):
        if cid:
            url = f"https://www.dmm.co.jp/dc/doujin/-/detail/=/cid={cid}/"
            title = f"FANZA 同人 - {cid}"
        else:
            url = "https://www.dmm.co.jp/dc/doujin/"
            title = "FANZA 同人 (内蔵ストア)"
        cls.open_url(url, title)

    @classmethod
    def open_fanza_purchased(cls):
        url = "https://www.dmm.co.jp/digital/-/member/bought/=/type=doujin/"
        cls.open_url(url, "FANZA - 購入済み作品一覧")
