# -*- coding: utf-8 -*-
"""
modules/article_rewriter/history_manager.py
Quản lý lịch sử và chống đăng trùng bài viết qua mã băm SHA256.
"""
import os
import json
import time
import hashlib
from typing import Dict, Any, List

class HistoryManager:
    def __init__(self, app_dir: str):
        self.history_file = os.path.join(app_dir, "user_data", "article_history.json")
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
        self.history = self._load()

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save(self):
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    @staticmethod
    def hash_content(content: str) -> str:
        clean = "".join(content.split()).lower()
        return hashlib.sha256(clean.encode("utf-8")).hexdigest()

    def is_posted(self, content: str) -> bool:
        h = self.hash_content(content)
        return h in self.history

    def mark_posted(self, content: str, title: str, article_id: str = ""):
        h = self.hash_content(content)
        self.history[h] = {
            "title": title,
            "id": article_id,
            "timestamp": int(time.time()),
            "date": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        self._save()

    def get_all(self) -> List[Dict[str, Any]]:
        return list(self.history.values())
