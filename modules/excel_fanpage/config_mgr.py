# -*- coding: utf-8 -*-
import json
from pathlib import Path

class ConfigMgr:
    def __init__(self):
        self.cfg_dir = Path.home() / '.config_tool_excel'
        self.cfg_dir.mkdir(exist_ok=True)
        self.cfg_file = self.cfg_dir / 'config_v2.json'
        self.history_file = self.cfg_dir / 'processed_folders.json'

    def save(self, data):
        try:
            self.cfg_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception:
            pass

    def load(self):
        if self.cfg_file.exists():
            try:
                return json.loads(self.cfg_file.read_text(encoding='utf-8'))
            except Exception:
                return {}
        return {}

    def get_processed_folders(self):
        if self.history_file.exists():
            try:
                return set(json.loads(self.history_file.read_text(encoding='utf-8')))
            except Exception:
                return set()
        return set()

    def add_processed_folders(self, folder_paths):
        try:
            processed = self.get_processed_folders()
            for p in folder_paths:
                processed.add(str(Path(p).resolve()))
            self.history_file.write_text(json.dumps(list(processed), ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception:
            pass

    def reset_history(self):
        try:
            if self.history_file.exists():
                self.history_file.unlink()
            return True
        except Exception:
            return False
