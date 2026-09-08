import os
import sys
import hashlib
import urllib.request
import urllib.parse
import re
import ctypes
from ctypes import wintypes, c_void_p, c_int, c_uint, byref, sizeof
from pathlib import Path
from typing import List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

CACHE_DIR = Path("cache/icons")

class IconHelper:
    """exeからのアイコン抽出、Web画像検索、アイコンキャッシュを担うヘルパークラス"""

    def __init__(self, cache_dir: Path = CACHE_DIR):
        self.cache_dir = Path(cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, key: str) -> Path:
        hash_val = hashlib.md5(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{hash_val}.png"

    def search_web_icons(self, query: str, max_results: int = 8) -> List[str]:
        """Bing画像検索を用いて、ゲーム/アプリのアイコン・カバー画像候補URLを取得"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        # クエリの調整
        clean_query = query.strip()
        # RJコードの場合はRJコードとゲームで検索
        if re.search(r'(RJ|VJ)\d+', clean_query, re.IGNORECASE):
            search_term = f"{clean_query} ゲーム"
        else:
            search_term = f"{clean_query} game logo icon"

        bing_url = f"https://www.bing.com/images/search?q={urllib.parse.quote(search_term)}&form=HDRSC2&first=1"
        req = urllib.request.Request(bing_url, headers=headers)
        results = []
        try:
            with urllib.request.urlopen(req, timeout=6) as res:
                html = res.read().decode("utf-8", errors="ignore")
                matches = re.findall(r'murl&quot;:&quot;(http[^&]+)&quot;', html)
                if not matches:
                    matches = re.findall(r'"murl":"(http[^"]+)"', html)
                for m in matches:
                    if m not in results and not m.endswith(".svg"):
                        results.append(m)
                    if len(results) >= max_results:
                        break
        except Exception as e:
            print(f"[IconHelper] Web画像検索エラー ({query}): {e}")
        return results

    def download_image(self, url: str, target_size: Tuple[int, int] = (128, 128)) -> Optional[Image.Image]:
        """指定したURLから画像をダウンロードしてPIL Imageとして整形"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=6) as res:
                img_data = res.read()
            import io
            img = Image.open(io.BytesIO(img_data)).convert("RGBA")
            # アスペクト比を維持しつつ正方形に収める
            img.thumbnail(target_size, Image.Resampling.LANCZOS)
            # 正方形の透過背景キャンバスに中央配置
            final_img = Image.new("RGBA", target_size, (0, 0, 0, 0))
            offset_x = (target_size[0] - img.width) // 2
            offset_y = (target_size[1] - img.height) // 2
            final_img.paste(img, (offset_x, offset_y), img)
            return final_img
        except Exception as e:
            print(f"[IconHelper] 画像ダウンロード失敗 ({url}): {e}")
            return None

    def cache_image(self, key: str, image: Image.Image) -> str:
        """画像をキャッシュディレクトリにPNG形式で保存し、絶対パスを返す"""
        cache_path = self._get_cache_path(key)
        try:
            image.save(cache_path, "PNG")
            return str(cache_path)
        except Exception as e:
            print(f"[IconHelper] キャッシュ保存失敗: {e}")
            return ""

    def extract_icon_from_exe(self, exe_path: str, target_size: Tuple[int, int] = (128, 128)) -> Optional[Image.Image]:
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
        except Exception as e:
            return None

    def create_fallback_icon(self, name: str, size: Tuple[int, int] = (128, 128)) -> Image.Image:
        """アプリ名の頭文字をもとに洗練されたグラデーション風アイコンを生成"""
        img = Image.new("RGBA", size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 背景グラデーション風の角丸四角形
        hash_code = int(hashlib.md5(name.encode("utf-8")).hexdigest()[:6], 16)
        r = (hash_code & 0xFF0000) >> 16
        g = (hash_code & 0x00FF00) >> 8
        b = (hash_code & 0x0000FF)
        # 彩度を高めて暗すぎず明るすぎない色に補正
        color = ((r % 160) + 50, (g % 160) + 50, (b % 160) + 50, 255)

        draw.rounded_rectangle([4, 4, size[0] - 4, size[1] - 4], radius=24, fill=color)

        # 文字
        char = (name[0] if name else "?").upper()
        # フォント設定
        try:
            font = ImageFont.truetype("meiryo.ttc", int(size[1] * 0.5))
        except Exception:
            try:
                font = ImageFont.truetype("arial.ttf", int(size[1] * 0.5))
            except Exception:
                font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), char, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        text_x = (size[0] - text_w) // 2 - bbox[0]
        text_y = (size[1] - text_h) // 2 - bbox[1]
        draw.text((text_x, text_y), char, font=font, fill=(255, 255, 255, 240))

        return img

    def get_or_create_icon(self, exe_path: str, app_name: str, preferred_icon_path: Optional[str] = None, allow_web_search: bool = True) -> str:
        """
        アイコンパスを解決して返す。
        1. preferred_icon_path が有効な画像ファイルならそれを返す
        2. キャッシュが存在すればそれを返す
        3. Web検索で画像取得を試行（allow_web_search=True時）
        4. exeからアイコン抽出
        5. フォールバックアイコンを生成
        """
        if preferred_icon_path and os.path.exists(preferred_icon_path):
            return preferred_icon_path

        cache_path = self._get_cache_path(f"{app_name}_{exe_path}")
        if cache_path.exists():
            return str(cache_path)

        # 3. Web画像検索
        if allow_web_search:
            try:
                urls = self.search_web_icons(app_name, max_results=1)
                if urls:
                    img = self.download_image(urls[0])
                    if img:
                        return self.cache_image(f"{app_name}_{exe_path}", img)
            except Exception as e:
                print(f"[IconHelper] Webアイコン自動取得失敗: {e}")

        # 4. exeからアイコン抽出
        exe_icon = self.extract_icon_from_exe(exe_path)
        if exe_icon:
            return self.cache_image(f"{app_name}_{exe_path}", exe_icon)

        # 5. フォールバック
        fallback = self.create_fallback_icon(app_name)
        return self.cache_image(f"{app_name}_{exe_path}", fallback)
