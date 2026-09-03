# -*- coding: utf-8 -*-
"""
MasterToolHub Update Client (Core Updater)
Kiểm tra bản phát hành mới từ GitHub (Manifest/API) và kích hoạt Bootstrap Updater độc lập.
"""
import os
import sys
import json
import urllib.request
import urllib.error
import ssl
import subprocess
import tempfile
import shutil

APP_VERSION = "2.7.1"
GITHUB_REPO = "khoathoiloi/Tool_Tong_Hop_GUI"
MANIFEST_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/update.json"
API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

def get_app_root_dir() -> str:
    """Lấy đúng đường dẫn thư mục gốc của app dù đang chạy EXE đóng gói hay chạy Python code"""
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        if os.path.basename(exe_dir).lower() == '_internal':
            return os.path.dirname(exe_dir)
        return exe_dir
    else:
        core_dir = os.path.dirname(os.path.abspath(__file__))
        if os.path.basename(core_dir).lower() == 'core':
            parent = os.path.dirname(core_dir)
            if os.path.basename(parent).lower() == '_internal':
                return os.path.dirname(parent)
            return parent
        return os.path.dirname(core_dir)

def compare_versions(current_v: str, latest_v: str) -> bool:
    """
    So sánh phiên bản theo Semantic Versioning dạng số nguyên (Major.Minor.Patch).
    Ví dụ: 2.10.0 > 2.9.0 (Trả về True nếu latest_v > current_v)
    """
    def _parse(v):
        v = str(v).lstrip('vV').strip()
        parts = []
        for p in v.split('.'):
            try:
                parts.append(int(p))
            except ValueError:
                parts.append(0)
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts)

    return _parse(latest_v) > _parse(current_v)

def _compare_versions(current_v: str, latest_v: str) -> bool:
    """Alias tương thích ngược"""
    return compare_versions(current_v, latest_v)

def check_for_updates(current_version=APP_VERSION, repo_name=GITHUB_REPO) -> dict:
    """
    Kiểm tra phiên bản mới từ GitHub:
    1. Ưu tiên đọc update.json manifest.
    2. Fallback sang GitHub Releases API nếu manifest chưa có hoặc lỗi.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    # 1. Thử đọc từ update.json Manifest
    manifest_url = f"https://raw.githubusercontent.com/{repo_name}/main/update.json"
    try:
        req = urllib.request.Request(manifest_url, headers={
            'User-Agent': 'MasterToolHub-UpdaterClient',
            'Accept': 'application/json'
        })
        with urllib.request.urlopen(req, context=ctx, timeout=8) as response:
            if response.status == 200:
                m_data = json.loads(response.read().decode('utf-8'))
                latest_v = m_data.get('latest_version', '').lstrip('vV').strip()
                if latest_v:
                    has_update = compare_versions(current_version, latest_v)
                    return {
                        'has_update': has_update,
                        'current_version': current_version,
                        'latest_version': latest_v,
                        'tag_name': f"v{latest_v}",
                        'html_url': f"https://github.com/{repo_name}/releases/tag/v{latest_v}",
                        'body': m_data.get('release_notes', 'Có phiên bản cập nhật mới trên GitHub!'),
                        'package_url': m_data.get('package_url', ''),
                        'package_sha256': m_data.get('package_sha256', ''),
                        'updater_url': m_data.get('updater_url', ''),
                        'updater_sha256': m_data.get('updater_sha256', ''),
                        'download_url': m_data.get('package_url', '') # Tương thích code cũ
                    }
    except Exception:
        pass # Fallback sang GitHub API bên dưới

    # 2. Fallback sang GitHub Releases API chuẩn
    url = f"https://api.github.com/repos/{repo_name}/releases/latest"
    req = urllib.request.Request(url, headers={
        'User-Agent': 'MasterToolHub-UpdaterClient',
        'Accept': 'application/vnd.github.v3+json'
    })

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                tag_name = data.get('tag_name', '')
                latest_v = tag_name.lstrip('vV').strip()
                body = data.get('body', '')
                html_url = data.get('html_url', '')

                assets = data.get('assets', [])
                package_url = ''
                updater_url = ''
                asset_name = ''
                
                for a in assets:
                    name = a.get('name', '')
                    name_lower = name.lower()
                    if name_lower.endswith('.zip') or (name_lower.startswith('mastertoolhub') and name_lower.endswith('.exe')):
                        package_url = a.get('browser_download_url', '')
                        asset_name = name
                    elif name_lower == 'updater.exe' or name_lower.startswith('updater'):
                        updater_url = a.get('browser_download_url', '')

                has_update = compare_versions(current_version, latest_v)

                return {
                    'has_update': has_update,
                    'current_version': current_version,
                    'latest_version': latest_v,
                    'tag_name': tag_name,
                    'html_url': html_url,
                    'body': body,
                    'package_url': package_url,
                    'package_sha256': '',
                    'updater_url': updater_url,
                    'download_url': package_url, # Tương thích code cũ
                    'asset_name': asset_name
                }
    except Exception as e:
        return {
            'has_update': False,
            'error': str(e),
            'current_version': current_version
        }

    return {'has_update': False, 'current_version': current_version}

def bootstrap_and_launch_updater(update_info: dict, progress_cb=None, log_cb=None) -> bool:
    """
    Tải Bootstrap Updater mới nhất (nếu cần) và khởi chạy tiến trình Updater.exe độc lập.
    Ứng dụng chính sau đó có thể đóng an toàn để nhường quyền cập nhật.
    """
    app_root = get_app_root_dir()
    package_url = update_info.get('package_url') or update_info.get('download_url')
    package_sha256 = update_info.get('package_sha256', '')
    to_version = update_info.get('latest_version', '')
    from_version = update_info.get('current_version', APP_VERSION)
    updater_url = update_info.get('updater_url', '')

    if not package_url:
        if log_cb: log_cb("Không tìm thấy link tải gói cài đặt cập nhật!", "ERROR")
        return False

    # 1. Tìm hoặc tải Updater.exe độc lập
    updater_exe_path = os.path.join(app_root, "Updater.exe")
    temp_updater_dir = os.path.join(tempfile.gettempdir(), "MasterToolUpdater")
    os.makedirs(temp_updater_dir, exist_ok=True)
    temp_updater_exe = os.path.join(temp_updater_dir, "Updater.exe")

    # Nếu có Updater.exe sẵn trong app_root -> copy sang temp để chạy (tránh lock chính file updater trong app_root)
    if os.path.exists(updater_exe_path) and os.path.getsize(updater_exe_path) > 1024:
        try:
            shutil.copy2(updater_exe_path, temp_updater_exe)
        except Exception:
            temp_updater_exe = updater_exe_path
    elif updater_url:
        # Nếu chưa có Updater.exe cục bộ, tải Bootstrap Updater trực tiếp từ GitHub Release
        if log_cb: log_cb("Đang tải Bootstrap Updater từ GitHub...", "INFO")
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            req = urllib.request.Request(updater_url, headers={'User-Agent': 'MasterToolHub-Bootstrap'})
            with urllib.request.urlopen(req, context=ctx, timeout=30) as resp, open(temp_updater_exe, 'wb') as out_f:
                shutil.copyfileobj(resp, out_f)
        except Exception as e:
            if log_cb: log_cb(f"Không thể tải Bootstrap Updater: {e}", "WARNING")

    # Kiểm tra lại xem file Updater.exe đã sẵn sàng chưa
    chosen_updater = temp_updater_exe if (os.path.exists(temp_updater_exe) and os.path.getsize(temp_updater_exe) > 1024) else updater_exe_path
    if not os.path.exists(chosen_updater):
        if log_cb: log_cb("Không tìm thấy Updater.exe! Vui lòng tải bản mới thủ công từ GitHub.", "ERROR")
        return False

    # 2. Khởi chạy Updater.exe với các tham số hoàn chỉnh
    current_pid = os.getpid()
    relaunch_exe = "MasterToolHub.exe" if getattr(sys, 'frozen', False) else "run_app.bat"
    
    cmd_args = [
        chosen_updater,
        "--target-dir", app_root,
        "--package-url", package_url,
        "--package-sha256", package_sha256,
        "--to-version", to_version,
        "--from-version", from_version,
        "--pid", str(current_pid),
        "--relaunch-exe", relaunch_exe
    ]

    if log_cb: log_cb("🚀 Đang khởi chạy MasterToolHub Updater...", "SUCCESS")

    try:
        if os.name == 'nt':
            creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(cmd_args, cwd=app_root, creationflags=creationflags, close_fds=True)
        else:
            subprocess.Popen(cmd_args, cwd=app_root, start_new_session=True)
        return True
    except Exception as e:
        if log_cb: log_cb(f"Lỗi khởi chạy Updater: {e}", "ERROR")
        return False

def download_and_apply_update(download_url, progress_cb=None, log_cb=None) -> bool:
    """Tương thích ngược với code cũ của Tab Settings"""
    info = {
        'package_url': download_url,
        'latest_version': 'New',
        'current_version': APP_VERSION
    }
    return bootstrap_and_launch_updater(info, progress_cb=progress_cb, log_cb=log_cb)