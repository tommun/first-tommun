import tkinter as tk
from tkinter import font as tkfont
from typing import Optional
import customtkinter as ctk

# ==============================================================================
# Google Fonts 日本語おすすめ24選（サンゼンデザイン Labo 厳選）に基づくフォント階層
# 
# 1. Noto Sans JP:
#    GoogleとAdobeが共同開発した、現代Web/UIデザインの最高峰フォント。
#    漢字・仮名・英数字のバランスが極めて高く、ダークテーマ/サイバーUIでも鮮明。
# 2. BIZ UDPGothic (BIZ UDPゴシック):
#    モリサワ製ユニバーサルデザインフォント。誤読防止・高視認性。Windows標準搭載。
# 3. Zen Kaku Gothic New:
#    モダンで洗練された角ゴシック。
# 4. M PLUS 1p:
#    親しみやすくクッキリとした太さを持つモダンゴシック。
# ==============================================================================

RECOMMENDED_UI_FONTS = [
    "Noto Sans JP",              # Google Fonts 筆頭・最高可読性ゴシック
    "BIZ UDPGothic",             # モリサワ UDゴシック (プロポーショナル)
    "BIZ UDPゴシック",
    "Zen Kaku Gothic New",       # Google Fonts モダン角ゴシック
    "M PLUS 1p",                 # Google Fonts クッキリゴシック
    "Segoe UI Variable Text",    # Windows 11 Fluent UI
    "Segoe UI Variable Display",
    "Segoe UI",
    "Yu Gothic UI",              # Windows 標準
    "Meiryo UI",
]

# 見出し・タイトル用（力強い重厚デザイン書体）
RECOMMENDED_DISPLAY_FONTS = [
    "Dela Gothic One",           # Google Fonts おすすめデザイン書体 (超極太・重厚サイバー)
    "Noto Sans JP Black",
    "Noto Sans JP Medium",
    "Noto Sans JP",
    "Segoe UI Variable Display",
    "Bahnschrift",
]

_detected_main_font: Optional[str] = None
_detected_display_font: Optional[str] = None

def get_font_family() -> str:
    """システム上で利用可能な推奨日本語UIフォントファミリー名を判定して返す"""
    global _detected_main_font
    if _detected_main_font is not None:
        return _detected_main_font

    try:
        root = tk._default_root
        if not root:
            dummy = tk.Tk()
            dummy.withdraw()
            avail = tkfont.families()
            dummy.destroy()
        else:
            avail = tkfont.families()

        for cand in RECOMMENDED_UI_FONTS:
            if cand in avail:
                _detected_main_font = cand
                return _detected_main_font
    except Exception:
        pass

    _detected_main_font = "Yu Gothic UI"
    return _detected_main_font

def get_display_font_family() -> str:
    """見出し・タイトル用の力強いフォントファミリー名を判定して返す"""
    global _detected_display_font
    if _detected_display_font is not None:
        return _detected_display_font

    try:
        root = tk._default_root
        if not root:
            dummy = tk.Tk()
            dummy.withdraw()
            avail = tkfont.families()
            dummy.destroy()
        else:
            avail = tkfont.families()

        for cand in RECOMMENDED_DISPLAY_FONTS:
            if cand in avail:
                _detected_display_font = cand
                return _detected_display_font
    except Exception:
        pass

    _detected_display_font = get_font_family()
    return _detected_display_font

# 既存コードとの後方互換性エイリアス
get_mac_font_family = get_font_family

def get_main_font(size: int = 12, weight: str = "normal") -> ctk.CTkFont:
    """メインUI用（Noto Sans JP / BIZ UDPGothic等）のCTkFontを生成"""
    family = get_font_family()
    return ctk.CTkFont(family=family, size=size, weight=weight)

# 既存コードとの後方互換性エイリアス
get_mac_font = get_main_font

def get_display_font(size: int = 14, weight: str = "bold") -> ctk.CTkFont:
    """見出し・タイトル用（Dela Gothic One / Noto Sans JP Bold等）のCTkFontを生成"""
    family = get_display_font_family()
    return ctk.CTkFont(family=family, size=size, weight=weight)
