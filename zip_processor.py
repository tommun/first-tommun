import os
import re
import shutil
import zipfile
import threading
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Callable, List

from game_analyzer import GameAnalyzer
from folder_scanner import FolderScanner
from gemini_icon_finder import GeminiIconFinder

def sanitize_filename(name: str) -> str:
    """Windowsで使用不可能な記号を除去・置換して安全なファイル名を生成"""
    return re.sub(r'[\\/*?:"<>|]', '_', name).strip()

class ZipProcessor:
    """
    ZIPファイルの自動展開、要求PCスペック判定によるC(SSD)/D(HDD)振り分け、
    Gemini AI によるタイトル・メタデータ自動補正、
    および元ZIPアーカイブの自動リネーム整理・保管庫への退避を司るマネージャークラス
    """

    DEFAULT_ARCHIVE_DIR = r"D:\Games\ZipArchives" if os.path.exists("D:\\") else r"C:\Games\ZipArchives"

    @classmethod
    def get_archive_dir(cls, config_mgr=None) -> str:
        if config_mgr and hasattr(config_mgr, "config"):
            adir = config_mgr.config.get("settings", {}).get("zip_archive_dir")
            if adir and os.path.isabs(adir):
                return adir
        return cls.DEFAULT_ARCHIVE_DIR

    @classmethod
    def is_auto_organize_enabled(cls, config_mgr=None) -> bool:
        if config_mgr and hasattr(config_mgr, "config"):
            return config_mgr.config.get("settings", {}).get("auto_organize_zip", True)
        return True

    @classmethod
    def is_rename_zip_enabled(cls, config_mgr=None) -> bool:
        if config_mgr and hasattr(config_mgr, "config"):
            return config_mgr.config.get("settings", {}).get("rename_zip_with_title", True)
        return True

    @classmethod
    def find_downloaded_zips(cls, config_mgr=None) -> List[Path]:
        """ダウンロードフォルダ等に存在するゲームアーカイブとおぼしきZIPを探索"""
        search_dirs = [
            Path.home() / "Downloads",
            Path("D:\\download"),
            Path("D:\\ダウンロード"),
            Path("C:\\Games\\Downloads")
        ]
        found_zips = []
        for sdir in search_dirs:
            if sdir.exists():
                try:
                    for f in sdir.glob("*.zip"):
                        if f.is_file() and f.stat().st_size > 10 * 1024 * 1024: # 10MB以上
                            found_zips.append(f)
                except Exception:
                    pass
        # 更新日時の新しい順にソート
        found_zips.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return found_zips

    @classmethod
    def process_zip_async(
        cls,
        zip_path: Path,
        config_mgr,
        icon_helper,
        status_callback: Optional[Callable[[str, str], None]] = None,
        done_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        error_callback: Optional[Callable[[str], None]] = None
    ):
        """バックグラウンドスレッドでZIPの自動展開・登録・整理を実行"""
        def worker():
            try:
                res = cls.process_zip(
                    zip_path=zip_path,
                    config_mgr=config_mgr,
                    icon_helper=icon_helper,
                    status_callback=status_callback
                )
                if done_callback:
                    done_callback(res)
            except Exception as e:
                if error_callback:
                    error_callback(str(e))
                elif status_callback:
                    status_callback(f"❌ ZIP展開エラー: {e}", "#f87171")

        threading.Thread(target=worker, daemon=True).start()

    @classmethod
    def process_zip(
        cls,
        zip_path: Path,
        config_mgr,
        icon_helper,
        status_callback: Optional[Callable[[str, str], None]] = None
    ) -> Dict[str, Any]:
        """
        ZIPアーカイブを自動展開・登録・整理する同期処理
        """
        if not zip_path.exists():
            raise FileNotFoundError(f"ZIPファイルが見つかりません: {zip_path}")

        if status_callback:
            status_callback(f"📦 ZIPアーカイブを解析中: {zip_path.name}...", "#00f0ff")

        # 1. 展開後の推定サイズ計算 & スペック判定
        total_uncompressed = 0
        namelist = []
        with zipfile.ZipFile(str(zip_path), 'r') as z_scan:
            for info in z_scan.infolist():
                total_uncompressed += info.file_size
                namelist.append(info.filename)

        spec_info = GameAnalyzer.detect_spec_from_namelist(
            namelist=namelist,
            name=zip_path.stem,
            total_size_bytes=total_uncompressed
        )

        is_heavy = (spec_info["spec_level"] == "Heavy")
        target_root = r"C:\Games\HeavyLibrary" if is_heavy else r"D:\Games\LightLibrary"
        drive_name = f"Cドライブ (高速SSD / {spec_info['spec_label']})" if is_heavy else f"Dドライブ (大容量HDD / {spec_info['spec_label']})"
        size_mb = total_uncompressed / (1024 * 1024)

        # 2. 保存先フォルダ名の決定 (RJコードがあればRJコード、なければZIPファイル名)
        m_rj = re.search(r'(RJ\d{6,8}|VJ\d{6,8}|BJ\d{6,8})', zip_path.name, re.IGNORECASE)
        rj_code = m_rj.group(1).upper() if m_rj else None
        sub_folder_name = rj_code if rj_code else zip_path.stem
        extract_dest = os.path.join(target_root, sub_folder_name)

        if status_callback:
            status_callback(f"📦 {drive_name} へ展開中 ({size_mb:.1f} MB)...", "#00ff9d")

        os.makedirs(extract_dest, exist_ok=True)

        # 3. 解凍実行 (CP437 -> CP932 / UTF-8 文字化け対策)
        with zipfile.ZipFile(str(zip_path), 'r') as z:
            for member in z.infolist():
                fn = member.filename
                try:
                    fn = fn.encode('cp437').decode('cp932')
                except Exception:
                    try:
                        fn = fn.encode('cp437').decode('utf-8')
                    except Exception:
                        pass
                target_file_path = os.path.join(extract_dest, fn)
                if member.is_dir():
                    os.makedirs(target_file_path, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(target_file_path), exist_ok=True)
                    with z.open(member) as src, open(target_file_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)

        # 4. 展開先フォルダからゲーム・EXEをスキャン
        detected = FolderScanner.scan_library_folder(extract_dest, default_category="その他")
        if not detected:
            # 簡易検出 (直下またはサブディレクトリのEXE)
            for eroot, edirs, efiles in os.walk(extract_dest):
                for ef in efiles:
                    if ef.lower().endswith(".exe") and not any(x in ef.lower() for x in ["crash", "setup", "uninstall", "unitycrash", "update"]):
                        exe_full = os.path.join(eroot, ef)
                        detected.append({
                            "name": zip_path.stem,
                            "path": exe_full,
                            "work_dir": eroot,
                            "folder_path": extract_dest,
                            "category": "その他",
                            "genre": "その他",
                            "platform": "DLsite" if rj_code else "その他",
                            "rj_code": rj_code,
                            "is_installed": True
                        })
                        break
                if detected:
                    break

        # 5. Gemini AI によるメタデータ補正（タイトル・作者・サークル名・RJコード）
        formal_title = zip_path.stem
        circle_author = "不明"

        if GeminiIconFinder.is_available():
            if status_callback:
                status_callback("🤖 Gemini AI が作品情報を同定中...", "#00f0ff")

            ai_res = GeminiIconFinder.analyze_game_info(
                title=zip_path.stem,
                folder_path=extract_dest,
                exe_path=detected[0]["path"] if detected else "",
                config_mgr=config_mgr
            )
            if ai_res:
                if ai_res.get("formal_title"):
                    formal_title = ai_res["formal_title"]
                if ai_res.get("author"):
                    circle_author = ai_res["author"]
                if ai_res.get("rj_code") and not rj_code:
                    rj_code = ai_res["rj_code"]

        # 登録アイテムの強化
        registered_items = []
        for item in detected:
            item["is_installed"] = True
            if formal_title and formal_title != zip_path.stem and not item.get("name_locked"):
                item["name"] = formal_title
            if circle_author and circle_author != "不明":
                item["author"] = circle_author
            if rj_code and not item.get("rj_code"):
                item["rj_code"] = rj_code
                item["platform"] = "DLsite"

            item.setdefault("spec_level", spec_info["spec_level"])
            item.setdefault("spec_label", spec_info["spec_label"])
            item.setdefault("engine", spec_info["engine"])
            item.setdefault("gpu_required", spec_info["gpu_required"])
            item.setdefault("recommended_spec", spec_info["recommended_spec"])

            # サムネイルの自動取得
            resolved_icon, q = icon_helper.resolve_best_thumbnail(item, allow_web_search=True)
            if resolved_icon:
                item["icon_path"] = resolved_icon
                item["icon_quality"] = q

            config_mgr.add_or_update_game(item)
            registered_items.append(item)

        # 6. 元ZIPファイルの整理・アーカイブ保管庫への移動
        archived_path = None
        if cls.is_auto_organize_enabled(config_mgr):
            try:
                archive_dir = cls.get_archive_dir(config_mgr)
                os.makedirs(archive_dir, exist_ok=True)

                # 新しいファイル名の決定
                if cls.is_rename_zip_enabled(config_mgr) and formal_title:
                    clean_title = sanitize_filename(formal_title)
                    if rj_code:
                        new_zip_name = f"[{rj_code}] {clean_title}.zip"
                    else:
                        new_zip_name = f"{clean_title}.zip"
                else:
                    new_zip_name = zip_path.name

                dest_zip_file = os.path.join(archive_dir, new_zip_name)

                # 同名ファイル衝突回避（連番付与）
                if os.path.exists(dest_zip_file) and os.path.abspath(dest_zip_file) != os.path.abspath(str(zip_path)):
                    base_stem = Path(dest_zip_file).stem
                    counter = 1
                    while os.path.exists(dest_zip_file):
                        dest_zip_file = os.path.join(archive_dir, f"{base_stem} ({counter}).zip")
                        counter += 1

                # 移動の実行（ダウンロード中ロック等の場合はコピー後に削除を試みる）
                if os.path.abspath(dest_zip_file) != os.path.abspath(str(zip_path)):
                    if status_callback:
                        status_callback(f"📂 元ZIPを保管庫へ整理中: {Path(dest_zip_file).name}...", "#38bdf8")
                    try:
                        shutil.move(str(zip_path), dest_zip_file)
                        archived_path = dest_zip_file
                    except Exception:
                        shutil.copy2(str(zip_path), dest_zip_file)
                        try:
                            os.remove(str(zip_path))
                        except Exception:
                            pass
                        archived_path = dest_zip_file
                else:
                    archived_path = str(zip_path)

            except Exception as e:
                print(f"[ZipProcessor] ZIP整理エラー (スキップ): {e}")

        return {
            "zip_name": zip_path.name,
            "dest_dir": extract_dest,
            "drive_name": drive_name,
            "spec_info": spec_info,
            "game_items": registered_items,
            "archived_zip_path": archived_path,
            "formal_title": formal_title
        }
