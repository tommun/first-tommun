import os
import re
import json
import urllib.request
import urllib.parse
from typing import Optional, Dict, Any, Tuple, List
from pathlib import Path

class GeminiIconFinder:
    """
    Google Gemini API を活用し、ノイズの多いゲームタイトル・フォルダ名・パスから
    正式タイトル、サークル名、RJコードを同定し、最高品質のサムネイル・ジャケット画像を高精度に引き当てるクラス
    """

    _cache: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def get_api_key(cls, config_mgr=None) -> Optional[str]:
        """設定ファイルまたは環境変数から Gemini API キーを取得"""
        # 1. 環境変数
        env_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if env_key:
            return env_key

        # 2. config_manager または launcher_config.json
        if config_mgr and hasattr(config_mgr, "config"):
            cfg_key = config_mgr.config.get("settings", {}).get("gemini_api_key", "").strip()
            if cfg_key:
                return cfg_key

        # 3. 直接ファイルを読み取り
        master_path = Path(r"C:\Games\Launcher\launcher_config.json")
        if master_path.exists():
            try:
                with open(master_path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    cfg_key = d.get("settings", {}).get("gemini_api_key", "").strip()
                    if cfg_key:
                        return cfg_key
            except Exception:
                pass

        return None

    @classmethod
    def is_available(cls, config_mgr=None) -> bool:
        """Gemini API が利用可能か判定"""
        return bool(cls.get_api_key(config_mgr))

    @classmethod
    def analyze_game_info(
        cls,
        title: str,
        folder_path: str = "",
        exe_path: str = "",
        author: str = "",
        config_mgr=None
    ) -> Optional[Dict[str, Any]]:
        """
        Gemini 3.8 Flash を使用してゲームタイトルとメタデータを解析
        戻り値: {
            "formal_title": "正式タイトル",
            "author": "サークル名",
            "rj_code": "RJxxxxxx" or None,
            "search_keywords": ["キーワード1", "キーワード2"],
            "genre": "ジャンル",
            "confidence": "high"
        }
        """
        api_key = cls.get_api_key(config_mgr)
        if not api_key:
            return None

        cache_key = f"{title}_{folder_path}_{exe_path}_{author}"
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)

            prompt = f"""あなたは日本国内のPCゲーム、同人ゲーム（DLsite, FANZA, Steam, フリーゲーム等）のメタデータ同定の専門家です。
以下のゲーム情報から、ファイル名やバージョン等のノイズを除去し、正式なタイトル、サークル/メーカー名、および対応するDLsite作品ID（RJ/VJ/BJ番号）を特定してください。

【ゲーム情報】
・現在の登録名: {title}
・親フォルダ名: {Path(folder_path).name if folder_path else 'なし'}
・実行ファイル名: {Path(exe_path).name if exe_path else 'なし'}
・現在の作者/サークル情報: {author if author else '不明'}

【指示】
1. formal_title: 不要なバージョン表記 (ver1.0, +修正パッチ等)、角括弧や配布プレフィックス (【DL版】, [サークル名]等) をすべて除去した正式な作品名を特定してください。
2. author: 正式なサークル名・ブランド名・作者名。
3. rj_code: もしこの作品がDLsiteやFANZA等で配信されている場合、対応するRJ番号 (例: RJ123456, RJ01180465) またはVJ/BJ番号を特定してください。確証がなければ null にしてください。
4. search_keywords: Google画像検索やWebで公式のジャケット・パッケージ・キービジュアル画像を1発でヒットさせるための最適な検索キーワード（2〜4個）。
5. genre: 推定されるゲームジャンル（例: アクション, ロールプレイング, アドベンチャー, シミュレーション）。

必ず以下のJSONフォーマットのみを出力してください:
{{
  "formal_title": "正式作品名",
  "author": "サークル名",
  "rj_code": "RJxxxxxxまたはnull",
  "search_keywords": ["検索語1", "検索語2"],
  "genre": "ジャンル",
  "confidence": "highまたはmediumまたはlow"
}}"""

            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            )

            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt,
                config=config
            )

            text = response.text.strip()
            data = json.loads(text)

            # RJコードの正規化
            rj = data.get("rj_code")
            if rj:
                m = re.search(r'(RJ|VJ|BJ)\d{6,8}', str(rj), re.IGNORECASE)
                data["rj_code"] = m.group(0).upper() if m else None
            else:
                data["rj_code"] = None

            cls._cache[cache_key] = data
            return data

        except Exception as e:
            print(f"[GeminiIconFinder] 解析エラー: {e}")
            return None

    @classmethod
    def test_connection(cls, api_key: str) -> Tuple[bool, str]:
        """APIキーの疎通確認テスト"""
        if not api_key or not api_key.strip():
            return False, "APIキーが入力されていません。"

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key.strip())
            resp = client.models.generate_content(
                model="gemini-3.8-flash",
                contents="ping",
                config=types.GenerateContentConfig(max_output_tokens=5)
            )
            if resp and resp.text:
                return True, "接続テスト成功！Gemini 3.8 Flash と正常に通信できました。"
            return False, "レスポンスが空でした。"
        except Exception as e:
            return False, f"接続エラー: {e}"
