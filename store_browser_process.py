import sys
import os
import argparse
import webview

def main():
    parser = argparse.ArgumentParser(description="Launcher Embedded Store Browser")
    parser.add_argument("--url", default="https://www.dlsite.com/maniax/", help="Target URL")
    parser.add_argument("--title", default="内蔵ストアブラウザ - DLsite & FANZA", help="Window Title")
    args = parser.parse_args()

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
