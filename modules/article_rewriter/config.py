# -*- coding: utf-8 -*-
"""
modules/article_rewriter/config.py
Quản lý cấu hình Module Xào Bài Báo và tự động Migration từ config_xao_bai.json cũ.
"""
import os
import json
import shutil
from typing import Dict, Any

DEFAULT_CONFIG: Dict[str, Any] = {
    "ai": {
        "provider": "gemini",  # "gemini" hoặc "openai_9router"
        "gemini_api_key": "",
        "gemini_model": "gemini-3.7-flash",
        "openai_base_url": "https://api.9router.com/v1",
        "openai_api_key": "",
        "openai_model": "gpt-4o-mini",
        "language": "English",
        "custom_prompt": ""
    },
    "gemini": {
        "api_key": "",
        "model": "gemini-3.7-flash",
        "language": "English",
        "custom_prompt": ""
    },
    "website": {
        "base_url": "https://jesusvibe.danhngon.pro",
        "login_url": "https://jesusvibe.danhngon.pro/login",
        "username": "",
        "password": "",
        "token": "",
        "cookie": "",
        "create_url": ""
    },
    "article": {
        "embed_pos": "Sau đoạn đầu",
        "embed_code": "",
        "keep_old_embed": True,
        "art_display": True,
        "art_home": True,
        "art_top": True
    },
    "performance": {
        "n_threads": 3,
        "delay": 5
    },
    "browser": {
        "chrome_path": ""
    }
}

class ArticleRewriterConfig:
    def __init__(self, app_dir: str):
        self.app_dir = app_dir
        self.config_dir = os.path.join(app_dir, "user_data")
        self.config_path = os.path.join(self.config_dir, "article_rewriter_config.json")
        os.makedirs(self.config_dir, exist_ok=True)
        self.data = self._load_or_migrate()

    def _load_or_migrate(self) -> Dict[str, Any]:
        """Tải cấu hình hiện tại hoặc tự động migrate từ config_xao_bai.json cũ nếu có"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    return self._merge_defaults(cfg)
            except Exception:
                pass

        # Kiểm tra nguồn config cũ để migrate
        legacy_candidates = [
            os.path.join(os.path.expanduser("~"), "Desktop", "xào báo", "config_xao_bai.json"),
            os.path.join(self.app_dir, "config_xao_bai.json"),
            os.path.join(os.path.expanduser("~"), ".kilo_token_tool", "token_state.json")
        ]

        migrated_cfg = dict(DEFAULT_CONFIG)
        found_legacy = False

        for legacy_file in legacy_candidates:
            if os.path.exists(legacy_file):
                try:
                    with open(legacy_file, "r", encoding="utf-8") as f:
                        old_data = json.load(f)
                        found_legacy = True
                        
                        # Map fields from legacy config_xao_bai.json
                        if "art_base" in old_data:
                            migrated_cfg["website"]["base_url"] = old_data.get("art_base", "https://jesusvibe.danhngon.pro")
                            migrated_cfg["website"]["token"] = old_data.get("art_token", "")
                            migrated_cfg["website"]["cookie"] = old_data.get("art_cookie", "")
                            migrated_cfg["gemini"]["language"] = old_data.get("art_lang", "English")
                            legacy_m = old_data.get("art_kilo_model", "gemini-3.7-flash")
                            if "3.5" in legacy_m or legacy_m == "gemini-1.5-flash":
                                legacy_m = "gemini-3.7-flash"
                            migrated_cfg["gemini"]["model"] = legacy_m
                            migrated_cfg["gemini"]["api_key"] = old_data.get("art_kilo_key", "")
                            migrated_cfg["ai"]["gemini_model"] = legacy_m
                            migrated_cfg["ai"]["gemini_api_key"] = old_data.get("art_kilo_key", "")
                            migrated_cfg["article"]["embed_pos"] = old_data.get("art_embed_pos", "Sau đoạn đầu")
                            migrated_cfg["article"]["keep_old_embed"] = bool(old_data.get("keep_old_embed", True))
                            migrated_cfg["article"]["art_display"] = bool(old_data.get("art_display", True))
                            migrated_cfg["article"]["art_home"] = bool(old_data.get("art_home", True))
                            migrated_cfg["article"]["art_top"] = bool(old_data.get("art_top", True))
                            migrated_cfg["performance"]["delay"] = int(old_data.get("delay", 5))
                            migrated_cfg["performance"]["n_threads"] = int(old_data.get("n_threads", 3))
                            
                        # Map token_state.json if available
                        if "access_token" in old_data or "art_token" in old_data:
                            if old_data.get("art_token"):
                                migrated_cfg["website"]["token"] = old_data["art_token"]
                            if old_data.get("art_cookie"):
                                migrated_cfg["website"]["cookie"] = old_data["art_cookie"]
                            if old_data.get("art_base"):
                                migrated_cfg["website"]["base_url"] = old_data["art_base"]
                        break
                except Exception:
                    pass

        if found_legacy:
            self.save(migrated_cfg)
            return migrated_cfg

        return DEFAULT_CONFIG

    def _merge_defaults(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        merged = {}
        for section, sec_data in DEFAULT_CONFIG.items():
            if isinstance(sec_data, dict):
                merged[section] = {**sec_data, **cfg.get(section, {})}
            elif section in cfg:
                merged[section] = cfg[section]
            else:
                merged[section] = sec_data

        # Migrate legacy model nếu phát hiện model cũ
        if "ai" in merged and isinstance(merged["ai"], dict):
            cur_m = merged["ai"].get("gemini_model", "")
            if "3.5" in cur_m or cur_m in ("gemini-1.5-flash", ""):
                merged["ai"]["gemini_model"] = "gemini-3.7-flash"
        if "gemini" in merged and isinstance(merged["gemini"], dict):
            cur_m = merged["gemini"].get("model", "")
            if "3.5" in cur_m or cur_m in ("gemini-1.5-flash", ""):
                merged["gemini"]["model"] = "gemini-3.7-flash"

        return merged

    def get(self, section: str, key_or_default=None, default=None):
        if default is None and not isinstance(key_or_default, str):
            return self.data.get(section, key_or_default)
        if isinstance(key_or_default, str):
            sec_dict = self.data.get(section, {})
            if isinstance(sec_dict, dict):
                return sec_dict.get(key_or_default, default)
            return default
        return self.data.get(section, default)

    def set(self, section: str, key: str, value: Any):
        if section not in self.data:
            self.data[section] = {}
        self.data[section][key] = value

    def save(self, data: Dict[str, Any] = None):
        if data:
            self.data = data
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
