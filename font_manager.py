import tkinter as tk
from tkinter import font as tkfont
from typing import Optional
import customtkinter as ctk

# macOS準拠のフォント優先順位リスト
MAC_FONT_CANDIDATES = [
    "SF Pro Display",
    "SF Pro Text",
    "SF Pro",
    "Helvetica Neue",
    "Helvetica",
    "Hiragino Sans",
    "Hiragino Kaku Gothic ProN",
    "Hiragino Kaku Gothic Pro",
    "Apple SD Gothic Neo",
    "Yu Gothic UI",     # WindowsにおけるMacヒラギノに最も近いモダン角ゴシック
    "Segoe UI",
    "Meiryo UI",
]

_detected_mac_font: Optional[str] = None

def get_mac_font_family() -> str:
    """システム上で利用可能なMac準拠のフォントファミリー名を判定して返す"""
    global _detected_mac_font
    if _detected_mac_font is not None:
        return _detected_mac_font

    try:
        root = tk._default_root
        if not root:
            dummy = tk.Tk()
            dummy.withdraw()
            avail = tkfont.families()
            dummy.destroy()
        else:
            avail = tkfont.families()

        for cand in MAC_FONT_CANDIDATES:
            if cand in avail:
                _detected_mac_font = cand
                return _detected_mac_font
    except Exception:
        pass

    _detected_mac_font = "Yu Gothic UI"
    return _detected_mac_font

def get_mac_font(size: int = 12, weight: str = "normal") -> ctk.CTkFont:
    """Mac準拠のフォントファミリーを使用したCTkFontを生成"""
    family = get_mac_font_family()
    return ctk.CTkFont(family=family, size=size, weight=weight)
