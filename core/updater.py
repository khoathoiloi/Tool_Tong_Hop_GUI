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

APP_VERSION = "2.5.1"
GITHUB_REPO = "khoathoiloi/Tool_Tong_Hop_GUI"
API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

def _compare_versions(current_v: str, latest_v: str) -> bool:
    """Trả về True nếu latest_v mới hơn current_v"""
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
    """
    Kiểm tra phiên bản mới từ GitHub Release API
    Trả về dict: {
        'has_update': bool,
        'latest_version': str,
        'tag_name': str,
        'html_url': str,
        'body': str,
        'download_url': str,
        'asset_name': str
    }
    """
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

                # Tìm asset file zip hoặc exe
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

def download_and_extract_update(download_url, target_dir, progress_cb=None, log_cb=None):
    """
    Tải file update ZIP và giải nén đè vào target_dir
    """
    if not download_url:
        if log_cb: log_cb("Không tìm thấy link tải bản cập nhật!", "ERROR")
        return False

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    temp_zip = os.path.join(tempfile.gettempdir(), "mastertool_update.zip")
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

    if log_cb: log_cb("📦 Đang giải nén và cập nhật tệp tin...", "INFO")

    try:
        with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
            zip_ref.extractall(target_dir)
        if log_cb: log_cb("🎉 CẬP NHẬT HOÀN TẤT THÀNH CÔNG!", "SUCCESS")
        return True
    except Exception as e:
        if log_cb: log_cb(f"❌ Lỗi giải nén: {e}", "ERROR")
        return False
    finally:
        if os.path.exists(temp_zip):
            try:
                os.remove(temp_zip)
            except Exception:
                pass