# -*- coding: utf-8 -*-
import os
import sys
import shutil

def get_base_dirs():
    dirs = []
    cur_file = os.path.abspath(__file__)
    dirs.append(os.path.dirname(os.path.dirname(cur_file)))
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        dirs.append(exe_dir)
        dirs.append(os.path.join(exe_dir, '_internal'))
        if hasattr(sys, '_MEIPASS'):
            dirs.append(sys._MEIPASS)
    return dirs

def find_ffmpeg():
    for bdir in get_base_dirs():
        candidate = os.path.join(bdir, 'bin', 'ffmpeg.exe')
        if os.path.exists(candidate):
            return candidate

    in_path = shutil.which('ffmpeg')
    if in_path and os.path.exists(in_path):
        return in_path
    
    candidates = [
        r'C:\ffmpeg\bin\ffmpeg.exe',
        r'D:\Tool_Tong_Hop_GUI\bin\ffmpeg.exe',
        r'D:\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe',
        r'D:\VideoScriptThumbnailTool_Fresh_Project_With_Update_Backup\VideoScriptThumbnailTool_Fresh_Project\ffmpeg\ffmpeg.exe',
        r'E:\ffmpeg\bin\ffmpeg.exe',
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return 'ffmpeg'

def find_ffprobe():
    for bdir in get_base_dirs():
        candidate = os.path.join(bdir, 'bin', 'ffprobe.exe')
        if os.path.exists(candidate):
            return candidate

    in_path = shutil.which('ffprobe')
    if in_path and os.path.exists(in_path):
        return in_path
    
    candidates = [
        r'C:\ffmpeg\bin\ffprobe.exe',
        r'D:\Tool_Tong_Hop_GUI\bin\ffprobe.exe',
        r'D:\ffmpeg-8.1.1-full_build\bin\ffprobe.exe',
        r'D:\VideoScriptThumbnailTool_Fresh_Project_With_Update_Backup\VideoScriptThumbnailTool_Fresh_Project\ffmpeg\ffprobe.exe',
        r'E:\ffmpeg\bin\ffprobe.exe',
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return 'ffprobe'
