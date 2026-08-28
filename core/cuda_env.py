# -*- coding: utf-8 -*-
"""
Module nạp DLLs CUDA và phát hiện GPU NVIDIA cho Faster-Whisper và AI Subtitle
"""
import os
import sys
import subprocess

os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

def setup_cuda_dlls():
    search_dirs = []
    if hasattr(sys, '_MEIPASS'):
        search_dirs.append(sys._MEIPASS)
        search_dirs.append(os.path.join(sys._MEIPASS, 'nvidia', 'cublas', 'bin'))
        search_dirs.append(os.path.join(sys._MEIPASS, 'nvidia', 'cudnn', 'bin'))
        search_dirs.append(os.path.join(sys._MEIPASS, 'nvidia', 'cuda_runtime', 'bin'))

    try:
        import site
        sp_list = site.getsitepackages() if hasattr(site, 'getsitepackages') else []
        if hasattr(site, 'getusersitepackages'):
            sp_list.append(site.getusersitepackages())
        for sp in sp_list:
            nvidia_base = os.path.join(sp, "nvidia")
            if os.path.isdir(nvidia_base):
                for sub in os.listdir(nvidia_base):
                    bin_dir = os.path.join(nvidia_base, sub, "bin")
                    if os.path.isdir(bin_dir):
                        search_dirs.append(bin_dir)
    except Exception:
        pass

    custom_paths = [
        r"C:\Users\TP\AppData\Local\Programs\Python\Python312\Lib\site-packages\nvidia\cublas\bin",
        r"C:\Users\TP\AppData\Local\Programs\Python\Python312\Lib\site-packages\nvidia\cudnn\bin",
        r"C:\Users\TP\AppData\Local\Programs\Python\Python312\Lib\site-packages\nvidia\cuda_runtime\bin",
        r"C:\Users\TP\AppData\Local\Programs\Python\Python312\Lib\site-packages\nvidia\cuda_nvrtc\bin",
    ]
    search_dirs.extend(custom_paths)

    for d in search_dirs:
        if os.path.isdir(d):
            try:
                os.add_dll_directory(d)
            except Exception:
                pass
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")

def get_gpu_info():
    setup_cuda_dlls()
    info = {
        "has_cuda": False,
        "device_name": "Không nhận diện GPU CUDA",
        "vram_gb": 0.0,
        "detail": "Đang chạy bằng CPU"
    }

    # 1. Kiểm tra qua CTranslate2 (Faster-Whisper engine)
    has_ct2_cuda = False
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            has_ct2_cuda = True
    except Exception:
        pass

    # 2. Lấy tên GPU và VRAM chính xác qua nvidia-smi
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        res = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader,nounits'],
            capture_output=True,
            text=True,
            creationflags=creationflags
        )
        if res.returncode == 0 and res.stdout.strip():
            first_line = res.stdout.strip().splitlines()[0]
            parts = first_line.split(',')
            name = parts[0].strip()
            vram_mb = float(parts[1].strip())
            vram_gb = round(vram_mb / 1024, 1)

            info["has_cuda"] = True
            info["device_name"] = name
            info["vram_gb"] = vram_gb
            info["detail"] = f"{name} ({vram_gb} GB VRAM)"
            return info
    except Exception:
        pass

    # 3. Fallback qua torch nếu có
    try:
        import torch
        if torch.cuda.is_available():
            info["has_cuda"] = True
            info["device_name"] = torch.cuda.get_device_name(0)
            total_mem = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
            info["vram_gb"] = round(total_mem, 1)
            info["detail"] = f"{info['device_name']} ({info['vram_gb']} GB VRAM)"
            return info
    except Exception:
        pass

    if has_ct2_cuda:
        info["has_cuda"] = True
        info["device_name"] = "NVIDIA CUDA GPU"
        info["detail"] = "NVIDIA CUDA GPU (Faster-Whisper Sẵn Sàng)"

    return info

setup_cuda_dlls()