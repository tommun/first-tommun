import os
import sys
import time
import hashlib
import urllib.request
import urllib.parse
import re
import ctypes
import threading
from ctypes import wintypes, c_void_p, c_int, c_uint, byref, sizeof
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any, Callable
from PIL import Image, ImageDraw, ImageFont

CACHE_DIR = Path("cache/icons")

# サムネイルの品質レベル定義
QUALITY_NONE = 0
QUALITY_FALLBACK = 1       # 頭文字アイコン
QUALITY_EXE_ICON = 2       # exeから抽出したアイコン
QUALITY_BING_GENERIC = 3   # 一般Web検索
QUALITY_DLSITE_OFFICIAL = 4 # DLsite公式ジャケット
QUALITY_LOCAL_ORIGINAL = 5  # ローカルの元イラスト・ジャケット画像

def generate_query_candidates(name: str, path: str = "", folder_path: str = "", author: str = "") -> List[str]:
    """作品名、パス、フォルダ名、作者情報から高精度な検索クエリのバリエーションを生成"""
    candidates = []
    
    # 1. RJ/VJ/BJ番号（最高精度・固有ID）
    combined = f"{name} {path} {folder_path}"
    m_rj = re.findall(r'\b(RJ|VJ|BJ)\d{6,8}\b', combined, re.IGNORECASE)
    for rj in m_rj:
        if rj.upper() not in candidates:
            candidates.append(rj.upper())

    clean_author = author.strip() if author and author != "不明" else ""

    # 2. サークル名や角括弧・丸括弧を除去したクリーンタイトル
    clean1 = re.sub(r'\[[^\]]*\]|【[^】]*】|\([^)]*\)|（[^）]*）', '', name)
    clean1 = re.sub(r'[-_ ]*(v|ver|version)?[._ ]*\d+(\.\d+)+.*', '', clean1, flags=re.IGNORECASE).strip()

    # 作品名 + 作者名の組み合わせ（作品名が被る場合の一致精度を大幅向上）
    if clean1 and clean_author:
        q_author_title = f"{clean1} {clean_author}"
        if q_author_title not in candidates:
            candidates.append(q_author_title)

    if clean1 and clean1 not in candidates:
        candidates.append(clean1)

    # 3. サブタイトル（〜、～、-）の分離
    for sep in ['〜', '～', ' - ', '-']:
        if sep in clean1:
            part = clean1.split(sep)[0].strip()
            if part and len(part) >= 2 and part not in candidates:
                if clean_author:
                    candidates.append(f"{part} {clean_author}")
                candidates.append(part)

    # 4. 元の名前そのまま
    if name not in candidates:
        candidates.append(name)

    # 5. フォルダ名（親フォルダ名）
    if folder_path:
        f_name = Path(folder_path).name
        clean_f = re.sub(r'\[[^\]]*\]|【[^】]*】|\([^)]*\)|（[^）]*）', '', f_name)
        clean_f = re.sub(r'[-_ ]*(v|ver|version)?[._ ]*\d+(\.\d+)+.*', '', clean_f, flags=re.IGNORECASE).strip()
        if clean_f and clean_f not in candidates:
            candidates.append(clean_f)

    # 6. exeのファイル名本体（汎用名を除く）
    if path:
        stem = Path(path).stem
        if stem.lower() not in ["game", "start", "main", "play", "app", "launch", "rpg_rt", "nw"]:
            if stem not in candidates:
                candidates.append(stem)

    return candidates

class IconHelper:
    """元画像の優先利用、DLsite公式サムネイル取得、exeアイコン抽出、品質管理"""

    def __init__(self, cache_dir: Path = CACHE_DIR):
        self.cache_dir = Path(cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Cookie": "adultchecked=1" # DLsite年齢確認
        }

    def _get_cache_path(self, key: str) -> Path:
        hash_val = hashlib.md5(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{hash_val}.png"

    def fetch_dlsite_thumbnail_by_rj(self, rj_code: str) -> Optional[str]:
        """RJ番号/VJ番号をもとにDLsite作品ページから公式ジャケット画像URLを取得"""
        rj = rj_code.upper().strip()
        pages = [
            f"https://www.dlsite.com/maniax/work/=/product_id/{rj}.html",
            f"https://www.dlsite.com/books/work/=/product_id/{rj}.html",
            f"https://www.dlsite.com/pro/work/=/product_id/{rj}.html",
            f"https://www.dlsite.com/home/work/=/product_id/{rj}.html",
            f"https://www.dlsite.com/girls/work/=/product_id/{rj}.html",
        ]
        for page_url in pages:
            try:
                req = urllib.request.Request(page_url, headers=self.headers)
                with urllib.request.urlopen(req, timeout=4) as res:
                    html = res.read().decode("utf-8", errors="ignore")
                    m = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html)
                    if m:
                        return m.group(1)
                    m2 = re.search(r'//img\.dlsite\.jp/[^"\']+_img_main\.(?:jpg|png)', html)
                    if m2:
                        return "https:" + m2.group(0)
            except Exception:
                pass
        return None

    def search_dlsite_thumbnail_by_query(self, query: str) -> Optional[str]:
        """作品名等のクエリでDLsite内検索を行い、公式ジャケット画像URLを取得"""
        if not query or len(query.strip()) < 2:
            return None
        search_url = f"https://www.dlsite.com/maniax/fsr/=/keyword/{urllib.parse.quote(query.strip())}"
        try:
            req = urllib.request.Request(search_url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=5) as res:
                html = res.read().decode("utf-8", errors="ignore")
                matches = re.findall(r'//img\.dlsite\.jp/[^"\']+_img_main\.(?:jpg|png)', html)
                if matches:
                    return "https:" + matches[0]
                matches2 = re.findall(r'//img\.dlsite\.jp/[^"\']+\.(?:jpg|png)', html)
                for m in matches2:
                    if "work" in m:
                        return "https:" + m
        except Exception:
            pass
        return None

    def search_web_icons(self, query: str, max_results: int = 6) -> List[str]:
        """Bing画像検索を用いて候補画像URLを取得"""
        clean_query = query.strip()
        search_term = f"{clean_query} game logo icon"
        bing_url = f"https://www.bing.com/images/search?q={urllib.parse.quote(search_term)}&form=HDRSC2&first=1"
        req = urllib.request.Request(bing_url, headers=self.headers)
        results = []
        try:
            with urllib.request.urlopen(req, timeout=5) as res:
                html = res.read().decode("utf-8", errors="ignore")
                matches = re.findall(r'murl&quot;:&quot;(http[^&]+)&quot;', html)
                if not matches:
                    matches = re.findall(r'"murl":"(http[^"]+)"', html)
                for m in matches:
                    if m not in results and not m.endswith(".svg"):
                        results.append(m)
                    if len(results) >= max_results:
                        break
        except Exception:
            pass
        return results

    def download_image(self, url: str, target_size: Tuple[int, int] = (260, 260)) -> Optional[Image.Image]:
        """URLから画像をダウンロードして正方形のPIL Imageとして整形"""
        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=5) as res:
                img_data = res.read()
            import io
            img = Image.open(io.BytesIO(img_data)).convert("RGBA")
            img.thumbnail(target_size, Image.Resampling.LANCZOS)
            final_img = Image.new("RGBA", target_size, (0, 0, 0, 0))
            offset_x = (target_size[0] - img.width) // 2
            offset_y = (target_size[1] - img.height) // 2
            final_img.paste(img, (offset_x, offset_y), img)
            return final_img
        except Exception:
            return None

    def cache_image(self, key: str, image: Image.Image) -> str:
        """画像をキャッシュディレクトリにPNG形式で保存し、パスを返す"""
        cache_path = self._get_cache_path(key)
        try:
            image.save(cache_path, "PNG")
            return str(cache_path)
        except Exception:
            return ""

    def process_local_image(self, local_path: str, target_size: Tuple[int, int] = (260, 260)) -> Optional[str]:
        """ローカル画像（イラスト）を正方形サムネイルに整形してキャッシュに保存"""
        if not local_path or not os.path.exists(local_path):
            return None
        try:
            img = Image.open(local_path).convert("RGBA")
            img.thumbnail(target_size, Image.Resampling.LANCZOS)
            final_img = Image.new("RGBA", target_size, (0, 0, 0, 0))
            offset_x = (target_size[0] - img.width) // 2
            offset_y = (target_size[1] - img.height) // 2
            final_img.paste(img, (offset_x, offset_y), img)
            return self.cache_image(f"local_{local_path}", final_img)
        except Exception:
            return local_path

    def extract_icon_from_exe(self, exe_path: str, target_size: Tuple[int, int] = (140, 140)) -> Optional[Image.Image]:
        """Windows API経由でexeからアイコンを抽出"""
        if not os.path.exists(exe_path):
            return None
        try:
            shell32 = ctypes.windll.shell32
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32

            HICON = c_void_p
            HBITMAP = c_void_p
            HDC = c_void_p
            HWND = c_void_p

            class ICONINFO(ctypes.Structure):
                _fields_ = [
                    ("fIcon", wintypes.BOOL),
                    ("xHotspot", wintypes.DWORD),
                    ("yHotspot", wintypes.DWORD),
                    ("hbmMask", HBITMAP),
                    ("hbmColor", HBITMAP),
                ]

            class BITMAP(ctypes.Structure):
                _fields_ = [
                    ("bmType", wintypes.LONG),
                    ("bmWidth", wintypes.LONG),
                    ("bmHeight", wintypes.LONG),
                    ("bmWidthBytes", wintypes.LONG),
                    ("bmPlanes", wintypes.WORD),
                    ("bmBitsPixel", wintypes.WORD),
                    ("bmBits", c_void_p),
                ]

            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ("biSize", wintypes.DWORD),
                    ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD),
                    ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG),
                    ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD),
                ]

            shell32.ExtractIconExW.argtypes = [wintypes.LPCWSTR, c_int, ctypes.POINTER(HICON), ctypes.POINTER(HICON), c_uint]
            shell32.ExtractIconExW.restype = c_uint
            user32.GetIconInfo.argtypes = [HICON, ctypes.POINTER(ICONINFO)]
            user32.GetIconInfo.restype = wintypes.BOOL
            user32.DestroyIcon.argtypes = [HICON]
            user32.DestroyIcon.restype = wintypes.BOOL
            user32.GetDC.argtypes = [HWND]
            user32.GetDC.restype = HDC
            user32.ReleaseDC.argtypes = [HWND, HDC]
            user32.ReleaseDC.restype = c_int
            gdi32.GetObjectW.argtypes = [HBITMAP, c_int, c_void_p]
            gdi32.GetObjectW.restype = c_int
            gdi32.GetDIBits.argtypes = [HDC, HBITMAP, c_uint, c_uint, c_void_p, c_void_p, c_uint]
            gdi32.GetDIBits.restype = c_int
            gdi32.DeleteObject.argtypes = [c_void_p]
            gdi32.DeleteObject.restype = wintypes.BOOL

            large_icon = HICON()
            small_icon = HICON()
            num = shell32.ExtractIconExW(exe_path, 0, byref(large_icon), byref(small_icon), 1)
            hicon = large_icon.value or small_icon.value
            if not hicon:
                return None

            icon_info = ICONINFO()
            if not user32.GetIconInfo(hicon, byref(icon_info)):
                user32.DestroyIcon(hicon)
                return None

            bmp = BITMAP()
            gdi32.GetObjectW(icon_info.hbmColor, sizeof(BITMAP), byref(bmp))
            width = bmp.bmWidth
            height = bmp.bmHeight
            if width <= 0 or height <= 0:
                user32.DestroyIcon(hicon)
                return None

            bi = BITMAPINFOHEADER()
            bi.biSize = sizeof(BITMAPINFOHEADER)
            bi.biWidth = width
            bi.biHeight = -height
            bi.biPlanes = 1
            bi.biBitCount = 32
            bi.biCompression = 0

            hdc = user32.GetDC(None)
            buf = ctypes.create_string_buffer(width * height * 4)
            gdi32.GetDIBits(hdc, icon_info.hbmColor, 0, height, buf, byref(bi), 0)
            user32.ReleaseDC(None, hdc)

            gdi32.DeleteObject(icon_info.hbmColor)
            gdi32.DeleteObject(icon_info.hbmMask)
            user32.DestroyIcon(hicon)
            if small_icon.value and small_icon.value != hicon:
                user32.DestroyIcon(small_icon.value)

            raw_bytes = bytes(buf)
            img = Image.frombytes("RGBA", (width, height), raw_bytes, "raw", "BGRA")
            if target_size and (width, height) != target_size:
                img = img.resize(target_size, Image.Resampling.LANCZOS)
            return img
        except Exception:
            return None

    def create_fallback_icon(self, name: str, size: Tuple[int, int] = (140, 140)) -> Image.Image:
        """アプリ名の頭文字をもとに洗練された角丸アイコンを生成"""
        img = Image.new("RGBA", size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        hash_code = int(hashlib.md5(name.encode("utf-8")).hexdigest()[:6], 16)
        r = (hash_code & 0xFF0000) >> 16
        g = (hash_code & 0x00FF00) >> 8
        b = (hash_code & 0x0000FF)
        color = ((r % 160) + 50, (g % 160) + 50, (b % 160) + 50, 255)

        draw.rounded_rectangle([4, 4, size[0] - 4, size[1] - 4], radius=24, fill=color)

        char = (name[0] if name else "?").upper()
        try:
            font = ImageFont.truetype("meiryo.ttc", int(size[1] * 0.45))
        except Exception:
            try:
                font = ImageFont.truetype("arial.ttf", int(size[1] * 0.45))
            except Exception:
                font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), char, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        text_x = (size[0] - text_w) // 2 - bbox[0]
        text_y = (size[1] - text_h) // 2 - bbox[1]
        draw.text((text_x, text_y), char, font=font, fill=(255, 255, 255, 240))

        return img

    def resolve_best_thumbnail(
        self,
        game_data: Dict[str, Any],
        allow_web_search: bool = True
    ) -> Tuple[str, int]:
        """
        指定されたゲームの最も最適なサムネイルと、その品質スコアを返す。
        戻り値: (icon_path, quality_score)
        """
        exe_path = game_data.get("path", "")
        name = game_data.get("name", "")
        folder_path = game_data.get("folder_path", "")
        preferred_icon_path = game_data.get("icon_path")
        local_ill = game_data.get("local_illustration")
        rj_code = game_data.get("rj_code")

        author = game_data.get("author", "")

        # 1. ユーザー手動指定
        if preferred_icon_path and os.path.exists(preferred_icon_path) and "cache" not in preferred_icon_path:
            return preferred_icon_path, QUALITY_LOCAL_ORIGINAL

        # 2. ローカルの元イラスト・ジャケット画像（最優先）
        if local_ill and os.path.exists(local_ill):
            cached_local = self.process_local_image(local_ill)
            if cached_local:
                return cached_local, QUALITY_LOCAL_ORIGINAL

        # 3. キャッシュ確認（既存品質が記録されていればそれを使用）
        cache_path = self._get_cache_path(f"{name}_{exe_path}")
        existing_quality = game_data.get("icon_quality", QUALITY_NONE)
        if cache_path.exists() and existing_quality >= QUALITY_DLSITE_OFFICIAL:
            return str(cache_path), existing_quality

        # 4. DLsite公式サムネイル探索（クエリバリエーションを網羅）
        if allow_web_search:
            # RJコードが明示されている場合は最優先で直接取得
            if rj_code and re.match(r'^(RJ|VJ|BJ)\d+$', rj_code, re.IGNORECASE):
                dlsite_img_url = self.fetch_dlsite_thumbnail_by_rj(rj_code)
                if dlsite_img_url:
                    img = self.download_image(dlsite_img_url)
                    if img:
                        saved_path = self.cache_image(f"{name}_{exe_path}", img)
                        return saved_path, QUALITY_DLSITE_OFFICIAL

            queries = generate_query_candidates(name, exe_path, folder_path, author=author)
            for q in queries:
                dlsite_img_url = None
                if re.match(r'^(RJ|VJ|BJ)\d+$', q, re.IGNORECASE):
                    dlsite_img_url = self.fetch_dlsite_thumbnail_by_rj(q)
                else:
                    dlsite_img_url = self.search_dlsite_thumbnail_by_query(q)

                if dlsite_img_url:
                    img = self.download_image(dlsite_img_url)
                    if img:
                        saved_path = self.cache_image(f"{name}_{exe_path}", img)
                        return saved_path, QUALITY_DLSITE_OFFICIAL

            # 5. DLsiteになければBing画像検索
            try:
                clean_name = queries[1] if len(queries) > 1 else name
                urls = self.search_web_icons(clean_name, max_results=1)
                if urls:
                    img = self.download_image(urls[0])
                    if img:
                        saved_path = self.cache_image(f"{name}_{exe_path}", img)
                        return saved_path, QUALITY_BING_GENERIC
            except Exception:
                pass

        # 6. exe内蔵アイコン
        exe_icon = self.extract_icon_from_exe(exe_path)
        if exe_icon:
            saved_path = self.cache_image(f"{name}_{exe_path}", exe_icon)
            return saved_path, QUALITY_EXE_ICON

        # 7. フォールバック
        fallback = self.create_fallback_icon(name)
        saved_path = self.cache_image(f"{name}_{exe_path}", fallback)
        return saved_path, QUALITY_FALLBACK


class ContinuousIconOptimizer:
    """
    バックグラウンドで常駐し、サムネイルが最高品質（DLsite公式またはローカル元イラスト）
    に達していないゲームを常に最適解を探し続けて自動アップグレードするワーカー
    """

    def __init__(self, icon_helper: IconHelper, get_games_fn: Callable[[], List[Dict[str, Any]]], on_updated_callback: Callable[[Dict[str, Any]], None]):
        self.icon_helper = icon_helper
        self.get_games_fn = get_games_fn
        self.on_updated_callback = on_updated_callback
        self.running = False
        self.thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False

    def _worker_loop(self):
        """バックグラウンドでサムネイル最適化を行う低負荷ループ"""
        time.sleep(5.0) # 起動完了まで待機してUI描画を最優先
        while self.running:
            try:
                games = self.get_games_fn()
                candidates = [
                    g for g in games
                    if g.get("icon_quality", QUALITY_NONE) < QUALITY_DLSITE_OFFICIAL
                    and not g.get("icon_locked", False)
                ]

                if not candidates:
                    time.sleep(120)
                    continue

                for game in candidates[:3]: # 1回あたり最大3件に絞って負荷分散
                    if not self.running:
                        break

                    cur_quality = game.get("icon_quality", QUALITY_NONE)
                    new_path, new_quality = self.icon_helper.resolve_best_thumbnail(game, allow_web_search=True)

                    if new_quality > cur_quality and new_path:
                        game["icon_path"] = new_path
                        game["icon_quality"] = new_quality
                        self.on_updated_callback(game)

                    time.sleep(3.0)

            except Exception as e:
                time.sleep(30)

            # バッチ間に十分なインターバルを設けてUIを常に軽快に保つ
            time.sleep(60)
