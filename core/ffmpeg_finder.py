# -*- coding: utf-8 -*-
import os
import shutil

def find_ffmpeg():
    in_path = shutil.which('ffmpeg')
    if in_path and os.path.exists(in_path):
        return in_path
    
    candidates = [
        r'D:\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe',
        r'D:\VideoScriptThumbnailTool_Fresh_Project_With_Update_Backup\VideoScriptThumbnailTool_Fresh_Project\ffmpeg\ffmpeg.exe',
        r'C:\ffmpeg\bin\ffmpeg.exe',
        r'E:\ffmpeg\bin\ffmpeg.exe',
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return 'ffmpeg'

def find_ffprobe():
    in_path = shutil.which('ffprobe')
    if in_path and os.path.exists(in_path):
        return in_path
    
    candidates = [
        r'D:\ffmpeg-8.1.1-full_build\bin\ffprobe.exe',
        r'D:\VideoScriptThumbnailTool_Fresh_Project_With_Update_Backup\VideoScriptThumbnailTool_Fresh_Project\ffmpeg\ffprobe.exe',
        r'C:\ffmpeg\bin\ffprobe.exe',
        r'E:\ffmpeg\bin\ffprobe.exe',
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return 'ffprobe'
