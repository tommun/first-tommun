import sys
import os
import argparse
import time
import json
import webview
from download_manager import DownloadManager

def setup_download_hook():
    """WebView2のダウンロードイベントをフックし、進行状況を随時ファイルへ通知"""
    try:
        import webview.platforms.winforms as wf
        import System

        orig_on_download_starting = wf.Chromium.EdgeChrome.on_download_starting

        def patched_on_download_starting(self, sender, args):
            orig_on_download_starting(self, sender, args)

            if args.Cancel:
                DownloadManager.update_download_status({
                    "status": "cancelled",
                    "filename": "",
                    "bytes_received": 0,
                    "total_bytes": 0,
                    "progress": 0.0,
                    "updated_at": time.time()
                })
                return

            download_op = args.DownloadOperation
            file_path = str(args.ResultFilePath)
            filename = os.path.basename(file_path)

            DownloadManager.update_download_status({
                "status": "downloading",
                "filename": filename,
                "file_path": file_path,
                "bytes_received": 0,
                "total_bytes": download_op.TotalBytesToReceive if hasattr(download_op, "TotalBytesToReceive") else 0,
                "progress": 0.0,
                "updated_at": time.time()
            })

            def on_bytes_received_changed(s, e):
                try:
                    recv = download_op.BytesReceived
                    total = download_op.TotalBytesToReceive
                    prog = round((recv / total * 100.0), 1) if total > 0 else 0.0
                    DownloadManager.update_download_status({
                        "status": "downloading",
                        "filename": filename,
                        "file_path": file_path,
                        "bytes_received": recv,
                        "total_bytes": total,
                        "progress": prog,
                        "updated_at": time.time()
                    })
                except Exception:
                    pass

            def on_state_changed(s, e):
                try:
                    state_str = str(download_op.State)
                    recv = download_op.BytesReceived
                    total = download_op.TotalBytesToReceive
                    if "Completed" in state_str:
                        DownloadManager.update_download_status({
                            "status": "completed",
                            "filename": filename,
                            "file_path": file_path,
                            "bytes_received": recv,
                            "total_bytes": total,
                            "progress": 100.0,
                            "updated_at": time.time()
                        })
                    elif "Interrupted" in state_str:
                        DownloadManager.update_download_status({
                            "status": "interrupted",
                            "filename": filename,
                            "file_path": file_path,
                            "bytes_received": recv,
                            "total_bytes": total,
                            "progress": 0.0,
                            "updated_at": time.time()
                        })
                except Exception:
                    pass

            download_op.BytesReceivedChanged += System.EventHandler[System.Object](on_bytes_received_changed)
            download_op.StateChanged += System.EventHandler[System.Object](on_state_changed)

        wf.Chromium.EdgeChrome.on_download_starting = patched_on_download_starting
        print("[StoreBrowser] Download hook installed successfully")
    except Exception as e:
        print(f"[StoreBrowser] Failed to hook download: {e}")

def main():
    parser = argparse.ArgumentParser(description="Launcher Embedded Store Browser")
    parser.add_argument("--url", default="https://www.dlsite.com/maniax/", help="Target URL")
    parser.add_argument("--title", default="内蔵ストアブラウザ - DLsite & FANZA", help="Window Title")
    args = parser.parse_args()

    # ダウンロード許可
    webview.settings["ALLOW_DOWNLOADS"] = True

    # ダウンロードフック設定
    setup_download_hook()

    # WebView2 ユーザープロファイル保存先（Cookie/ログインセッションを永続化）
    profile_dir = os.path.join(os.path.expanduser("~"), ".game_launcher", "webview_cache")
    os.makedirs(profile_dir, exist_ok=True)

    # アプリ内WebView2ウィンドウ作成
    window = webview.create_window(
        title=args.title,
        url=args.url,
        width=1200,
        height=800,
        resizable=True,
        confirm_close=False,
        background_color="#0b0f19"
    )

    # WindowsのWebView2で起動
    webview.start(private_mode=False, storage_path=profile_dir)

if __name__ == "__main__":
    main()

