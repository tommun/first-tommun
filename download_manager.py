import os
import sys
import json
import time
import re
from typing import Dict, Any, Optional

DOWNLOAD_STATUS_FILE = os.path.join(os.path.expanduser('~'), '.game_launcher', 'download_status.json')

class DownloadManager:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = DownloadManager()
        return cls._instance

    def __init__(self):
        self._last_modified = 0
        os.makedirs(os.path.dirname(DOWNLOAD_STATUS_FILE), exist_ok=True)

    @classmethod
    def update_download_status(cls, data: Dict[str, Any]):
        try:
            os.makedirs(os.path.dirname(DOWNLOAD_STATUS_FILE), exist_ok=True)
            temp_file = DOWNLOAD_STATUS_FILE + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(temp_file, DOWNLOAD_STATUS_FILE)
        except Exception:
            pass

    @classmethod
    def clear_status(cls):
        try:
            if os.path.exists(DOWNLOAD_STATUS_FILE):
                os.remove(DOWNLOAD_STATUS_FILE)
        except Exception:
            pass

    def check_status_file(self) -> Optional[Dict[str, Any]]:
        if not os.path.exists(DOWNLOAD_STATUS_FILE):
            return None
        try:
            mtime = os.path.getmtime(DOWNLOAD_STATUS_FILE)
            if mtime != self._last_modified:
                self._last_modified = mtime
                with open(DOWNLOAD_STATUS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return None
