# -*- coding: utf-8 -*-
"""
Module Quản Lý & Tải Trọn Gói AI Model cho Faster-Whisper
Hỗ trợ lưu trữ Offline vào thư mục models/ của Tool
"""
import os
import sys
import time
import shutil
import threading
from pathlib import Path
from typing import Callable, Optional, Dict, List

SUPPORTED_MODELS = {
    "large-v3-turbo": {
        "name": "large-v3-turbo",
        "label": "large-v3-turbo (Khuyên dùng cho RTX 3060 - Siêu Tốc & Chính Xác Nhất)",
        "repo_id": "Systran/faster-whisper-large-v3-turbo",
        "size_mb": 1600,
        "vram_rec": "4GB - 12GB VRAM",
        "accuracy": "⭐⭐⭐⭐⭐ (Xuất sắc)",
        "speed": "⚡⚡⚡⚡⚡ (Nhanh nhất)"
    },
    "large-v3": {
        "name": "large-v3",
        "label": "large-v3 (Mô hình lớn đầy đủ - Cực Kỳ Chi Tiết)",
        "repo_id": "Systran/faster-whisper-large-v3",
        "size_mb": 3100,
        "vram_rec": "6GB - 12GB VRAM",
        "accuracy": "⭐⭐⭐⭐⭐ (Xuất sắc)",
        "speed": "⚡⚡⚡ (Chuẩn)"
    },
    "medium": {
        "name": "medium",
        "label": "medium (Mô hình tiêu chuẩn tầm trung)",
        "repo_id": "Systran/faster-whisper-medium",
        "size_mb": 1500,
        "vram_rec": "4GB VRAM",
        "accuracy": "⭐⭐⭐⭐ (Rất tốt)",
        "speed": "⚡⚡⚡⚡ (Nhanh)"
    },
    "small": {
        "name": "small",
        "label": "small (Mô hình nhẹ)",
        "repo_id": "Systran/faster-whisper-small",
        "size_mb": 480,
        "vram_rec": "2GB VRAM",
        "accuracy": "⭐⭐⭐ (Tốt)",
        "speed": "⚡⚡⚡⚡⚡ (Rất nhanh)"
    },
    "base": {
        "name": "base",
        "label": "base (Mô hình siêu nhẹ)",
        "repo_id": "Systran/faster-whisper-base",
        "size_mb": 145,
        "vram_rec": "1GB VRAM",
        "accuracy": "⭐⭐ (Cơ bản)",
        "speed": "⚡⚡⚡⚡⚡ (Cực nhanh)"
    }
}

def get_models_base_dir() -> Path:
    """Trả về đường dẫn thư mục models/ nằm ngay trong thư mục app"""
    from core.updater import get_app_root_dir
    app_root = get_app_root_dir()
    p = Path(app_root) / "models"
    p.mkdir(parents=True, exist_ok=True)
    return p

def get_model_local_path(model_name: str) -> Optional[Path]:
    """Kiểm tra xem model đã được tải hoàn chỉnh trong thư mục models/ chưa"""
    base_dir = get_models_base_dir()
    
    # 1. Kiểm tra thư mục trực tiếp models/<model_name>
    direct_p = base_dir / model_name
    if direct_p.is_dir():
        if (direct_p / "model.bin").exists() or (direct_p / "model.safetensors").exists():
            return direct_p

    # 2. Kiểm tra theo cấu trúc snapshot huggingface hub
    hub_prefix = f"models--Systran--faster-whisper-{model_name}"
    hub_p = base_dir / hub_prefix
    if hub_p.is_dir():
        snapshots_dir = hub_p / "snapshots"
        if snapshots_dir.is_dir():
            for snap in snapshots_dir.iterdir():
                if snap.is_dir() and ((snap / "model.bin").exists() or (snap / "model.safetensors").exists()):
                    return snap

    return None

def is_model_downloaded(model_name: str) -> bool:
    return get_model_local_path(model_name) is not None

def get_all_models_status() -> List[Dict]:
    """Trả về trạng thái của tất cả các model"""
    status_list = []
    for m_name, meta in SUPPORTED_MODELS.items():
        is_dl = is_model_downloaded(m_name)
        status_list.append({
            "name": m_name,
            "label": meta["label"],
            "size_mb": meta["size_mb"],
            "downloaded": is_dl,
            "vram_rec": meta["vram_rec"],
            "accuracy": meta["accuracy"],
            "speed": meta["speed"]
        })
    return status_list

def download_model_to_local(
    model_name: str, 
    progress_cb: Optional[Callable[[str, int, int], None]] = None,
    log_cb: Optional[Callable[[str, str], None]] = None,
    stop_check_cb: Optional[Callable[[], bool]] = None
) -> bool:
    """Tải model về thư mục models/ của Tool"""
    import faster_whisper
    
    base_dir = get_models_base_dir()
    if log_cb:
        log_cb(f"🚀 Bắt đầu tải Model [{model_name}] vào: {base_dir}...", "INFO")

    try:
        dest_dir = str(base_dir / model_name)
        download_path = faster_whisper.download_model(
            model_name,
            output_dir=dest_dir
        )
        if log_cb:
            log_cb(f"✅ Tải thành công Model [{model_name}]! Đã sẵn sàng chạy 100% Offline.", "SUCCESS")
        return True
    except Exception as e:
        try:
            from huggingface_hub import snapshot_download
            repo_id = SUPPORTED_MODELS.get(model_name, {}).get("repo_id", f"Systran/faster-whisper-{model_name}")
            dest_dir = str(base_dir / model_name)
            snapshot_download(
                repo_id=repo_id,
                local_dir=dest_dir,
                local_dir_use_symlinks=False
            )
            if log_cb:
                log_cb(f"✅ Tải thành công Model [{model_name}] qua HuggingFace Hub!", "SUCCESS")
            return True
        except Exception as e2:
            if log_cb:
                log_cb(f"❌ Lỗi tải Model [{model_name}]: {e2}", "ERROR")
            return False