# -*- coding: utf-8 -*-
import os
import sys
import json
import urllib.request
import urllib.error
import ssl
import threading
import subprocess
import zipfile
import tempfile
import shutil

APP_VERSION = "2.5.2"
GITHUB_REPO = "khoathoiloi/Tool_Tong_Hop_GUI"
API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

def get_app_root_dir():
    """Lấy đúng đường dẫn thư mục gốc của app dù đang chạy EXE đóng gói hay chạy Python code"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        # File này nằm trong core/updater.py -> thư mục gốc là thư mục cha của core
        core_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.dirname(core_dir)

def _compare_versions(current_v: str, latest_v: str) -> bool:
    def _parse(v):
        v = v.lstrip('vV').strip()
        parts = []
        for p in v.split('.'):
            try:
                parts.append(int(p))
            except ValueError:
                parts.append(0)
        while len(parts) < 3:
            parts.append(0)
        return parts

    return _parse(latest_v) > _parse(current_v)

def check_for_updates(current_version=APP_VERSION, repo_name=GITHUB_REPO):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    url = f"https://api.github.com/repos/{repo_name}/releases/latest"
    req = urllib.request.Request(url, headers={
        'User-Agent': 'MasterToolHub-Updater',
        'Accept': 'application/vnd.github.v3+json'
    })

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=8) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                tag_name = data.get('tag_name', '')
                body = data.get('body', '')
                html_url = data.get('html_url', '')

                assets = data.get('assets', [])
                download_url = ''
                asset_name = ''
                for a in assets:
                    name = a.get('name', '').lower()
                    if name.endswith('.zip') or name.endswith('.exe'):
                        download_url = a.get('browser_download_url', '')
                        asset_name = a.get('name', '')
                        break

                has_update = _compare_versions(current_version, tag_name)

                return {
                    'has_update': has_update,
                    'current_version': current_version,
                    'latest_version': tag_name.lstrip('vV'),
                    'tag_name': tag_name,
                    'html_url': html_url,
                    'body': body,
                    'download_url': download_url,
                    'asset_name': asset_name
                }
    except Exception as e:
        return {
            'has_update': False,
            'error': str(e),
            'current_version': current_version
        }

    return {'has_update': False, 'current_version': current_version}

def download_and_apply_update(download_url, progress_cb=None, log_cb=None):
    """
    Tải bản cập nhật ZIP, giải nén vào thư mục tạm, tạo script ghi đè file khi đóng app
    và tự động khởi động lại ứng dụng với phiên bản mới nhất!
    """
    if not download_url:
        if log_cb: log_cb("Không tìm thấy link tải bản cập nhật!", "ERROR")
        return False

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    app_root = get_app_root_dir()
    temp_dir = tempfile.gettempdir()
    temp_zip = os.path.join(temp_dir, "mastertool_update.zip")
    staging_dir = os.path.join(temp_dir, "mastertool_staging")

    if os.path.exists(staging_dir):
        shutil.rmtree(staging_dir, ignore_errors=True)
    os.makedirs(staging_dir, exist_ok=True)

    if log_cb: log_cb(f"⏳ Đang tải bản cập nhật từ: {download_url}...", "INFO")

    req = urllib.request.Request(download_url, headers={'User-Agent': 'MasterToolHub-Updater'})
    with urllib.request.urlopen(req, context=ctx) as resp, open(temp_zip, 'wb') as out_f:
        total_size = int(resp.headers.get('content-length', 0))
        downloaded = 0
        block_size = 65536

        while True:
            buffer = resp.read(block_size)
            if not buffer:
                break
            downloaded += len(buffer)
            out_f.write(buffer)
            if total_size > 0 and progress_cb:
                pct = int(downloaded / total_size * 100)
                progress_cb(pct, downloaded, total_size)

    if log_cb: log_cb("📦 Đang giải nén dữ liệu cập nhật...", "INFO")

    try:
        with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
            zip_ref.extractall(staging_dir)
    except Exception as e:
        if log_cb: log_cb(f"❌ Lỗi giải nén ZIP: {e}", "ERROR")
        return False
    finally:
        if os.path.exists(temp_zip):
            try: os.remove(temp_zip)
            except Exception: pass

    # Kiểm tra xem zip có chứa folder con lồng nhau không
    source_copy_dir = staging_dir
    entries = os.listdir(staging_dir)
    if len(entries) == 1 and os.path.isdir(os.path.join(staging_dir, entries[0])):
        source_copy_dir = os.path.join(staging_dir, entries[0])

    if log_cb: log_cb("🔄 Đang khởi tạo tiến trình ghi đè và tự khởi động lại...", "SUCCESS")

    # Xác định file khởi chạy lại
    is_frozen = getattr(sys, 'frozen', False)
    exe_name = "MasterToolHub.exe"
    exe_target = os.path.join(app_root, exe_name)
    run_bat_target = os.path.join(app_root, "run_app.bat")

    relaunch_cmd = f'start "" "{exe_target}"' if (is_frozen or os.path.exists(exe_target)) else f'start "" "{run_bat_target}"'

    # Tạo batch script độc lập để ghi đè file sau khi app đóng
    bat_path = os.path.join(temp_dir, "apply_mastertool_update.bat")
    bat_content = f"""@echo off
title DANG CAP NHAT PHAN MEM...
timeout /t 2 /nobreak > nul

:: Copy đè toàn bộ tệp mới vào thư mục ứng dụng
xcopy "{source_copy_dir}\\*" "{app_root}\\" /E /Y /I /Q > nul

:: Xóa thư mục tạm staging
rmdir /s /q "{staging_dir}" > nul

:: Khởi động lại ứng dụng
{relaunch_cmd}

:: Tự xóa file bat cập nhật
del "%~f0" > nul
exit
"""
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)

    # Chạy script cập nhật trong tiến trình độc lập
    if os.name == 'nt':
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(["cmd.exe", "/c", bat_path], creationflags=creationflags, close_fds=True)
    else:
        subprocess.Popen(["sh", bat_path], start_new_session=True)

    return True