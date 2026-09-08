import os
import sys
import hashlib
import urllib.request
import urllib.parse
import re
import ctypes
from ctypes import wintypes, c_void_p, c_int, c_uint, byref, sizeof
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from PIL import Image, ImageDraw, ImageFont

CACHE_DIR = Path("cache/icons")

class IconHelper:
    """元画像の優先利用、DLsiteからの公式サムネイル取得、exeアイコン抽出、キャッシュ管理"""

    def __init__(self, cache_dir: Path = CACHE_DIR):
        self.cache_dir = Path(cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Cookie": "adultchecked=1" # DLsite年齢確認用
        }

    def _get_cache_path(self, key: str) -> Path:
        hash_val = hashlib.md5(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{hash_val}.png"

    # --- DLsite サムネイル取得 ---
    def fetch_dlsite_thumbnail_by_rj(self, rj_code: str) -> Optional[str]:
        """RJ番号/VJ番号をもとにDLsite作品ページから公式ジャケット画像URLを取得"""
        rj = rj_code.upper().strip()
        pages = [
            f"https://www.dlsite.com/maniax/work/=/product_id/{rj}.html",
            f"https://www.dlsite.com/books/work/=/product_id/{rj}.html",
            f"https://www.dlsite.com/pro/work/=/product_id/{rj}.html",
            f"https://www.dlsite.com/home/work/=/product_id/{rj}.html",
        ]
        for page_url in pages:
            try:
                req = urllib.request.Request(page_url, headers=self.headers)
                with urllib.request.urlopen(req, timeout=5) as res:
                    html = res.read().decode("utf-8", errors="ignore")
                    # og:image タグ
                    m = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html)
                    if m:
                        return m.group(1)
                    # _img_main.jpg
                    m2 = re.search(r'//img\.dlsite\.jp/[^"\']+_img_main\.(?:jpg|png)', html)
                    if m2:
                        return "https:" + m2.group(0)
            except Exception:
                pass
        return None

    def search_dlsite_thumbnail_by_title(self, title: str) -> Optional[str]:
        """作品名でDLsite内検索を行い、一致した作品のジャケット画像URLを取得"""
        # バージョンや記号、かっこを除去して作品名本体を抽出
        clean = re.sub(r'[-_ ]*(v|ver|version)?[._ ]*\d+(\.\d+)+.*', '', title, flags=re.IGNORECASE)
        clean = re.sub(r'【[^】]*】|\[[^\]]*\]|\([^)]*\)', '', clean).strip()
        if not clean:
            clean = title.strip()

        search_url = f"https://www.dlsite.com/maniax/fsr/=/keyword/{urllib.parse.quote(clean)}"
        try:
            req = urllib.request.Request(search_url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=6) as res:
                html = res.read().decode("utf-8", errors="ignore")
                # 検索結果一覧のメイン画像
                matches = re.findall(r'//img\.dlsite\.jp/[^"\']+_img_main\.(?:jpg|png)', html)
                if matches:
                    return "https:" + matches[0]
                matches2 = re.findall(r'//img\.dlsite\.jp/[^"\']+\.(?:jpg|png)', html)
                for m in matches2:
                    if "work" in m:
                        return "https:" + m
        except Exception as e:
            print(f"[IconHelper] DLsite検索エラー ({clean}): {e}")
        return None

    def search_web_icons(self, query: str, max_results: int = 8) -> List[str]:
        """Bing画像検索を用いて、ゲーム/アプリのカバー・ロゴ候補URLを取得"""
        clean_query = query.strip()
        if re.search(r'(RJ|VJ)\d+', clean_query, re.IGNORECASE):
            search_term = f"{clean_query} DLsite"
        else:
            search_term = f"{clean_query} game logo icon"

        bing_url = f"https://www.bing.com/images/search?q={urllib.parse.quote(search_term)}&form=HDRSC2&first=1"
        req = urllib.request.Request(bing_url, headers=self.headers)
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

    def download_image(self, url: str, target_size: Tuple[int, int] = (140, 140)) -> Optional[Image.Image]:
        """指定したURLから画像をダウンロードして正方形のPIL Imageとして整形"""
        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=6) as res:
                img_data = res.read()
            import io
            img = Image.open(io.BytesIO(img_data)).convert("RGBA")
            img.thumbnail(target_size, Image.Resampling.LANCZOS)
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

    def process_local_image(self, local_path: str, target_size: Tuple[int, int] = (140, 140)) -> Optional[str]:
        """ローカルの元画像（イラスト）を正方形サムネイルに整形してキャッシュに保存"""
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
        except Exception as e:
            print(f"[IconHelper] ローカル画像整形エラー: {e}")
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

        draw.rounded_rectangle([4, 4, size[0] - 4, size[1] - 4], radius=20, fill=color)

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

    def get_or_create_icon(
        self,
        exe_path: str,
        app_name: str,
        preferred_icon_path: Optional[str] = None,
        local_illustration: Optional[str] = None,
        rj_code: Optional[str] = None,
        allow_web_search: bool = True
    ) -> str:
        """
        アイコン・サムネイルを解決する。
        【優先度ルール】:
        1. ユーザーが手動指定したアイコン (preferred_icon_path)
        2. ゲームフォルダ内に元からあるイラスト・ジャケット画像 (local_illustration)
        3. キャッシュ画像 (既存)
        4. DLsiteから作品名/RJ番号で確認して公式サムネイルを取得
        5. Bing画像検索
        6. exe内蔵アイコン
        7. フォールバックアイコン
        """
        # 1. ユーザー手動指定
        if preferred_icon_path and os.path.exists(preferred_icon_path):
            return preferred_icon_path

        # 2. 元からあるイラスト画像（ユーザーの最重要指示：ちゃんとイラストがある場合はDLsite検索せず元の画像を使う）
        if local_illustration and os.path.exists(local_illustration):
            cached_local = self.process_local_image(local_illustration)
            if cached_local:
                return cached_local

        # 3. キャッシュ確認
        cache_path = self._get_cache_path(f"{app_name}_{exe_path}")
        if cache_path.exists():
            return str(cache_path)

        # 4. DLsiteから公式サムネイルを取得
        if allow_web_search:
            dlsite_img_url = None
            if rj_code:
                dlsite_img_url = self.fetch_dlsite_thumbnail_by_rj(rj_code)
            if not dlsite_img_url:
                dlsite_img_url = self.search_dlsite_thumbnail_by_title(app_name)

            if dlsite_img_url:
                img = self.download_image(dlsite_img_url)
                if img:
                    return self.cache_image(f"{app_name}_{exe_path}", img)

            # 5. DLsiteになければBing画像検索
            try:
                urls = self.search_web_icons(app_name, max_results=1)
                if urls:
                    img = self.download_image(urls[0])
                    if img:
                        return self.cache_image(f"{app_name}_{exe_path}", img)
            except Exception:
                pass

        # 6. exeからアイコン抽出
        exe_icon = self.extract_icon_from_exe(exe_path)
        if exe_icon:
            return self.cache_image(f"{app_name}_{exe_path}", exe_icon)

        # 7. フォールバック
        fallback = self.create_fallback_icon(app_name)
        return self.cache_image(f"{app_name}_{exe_path}", fallback)
