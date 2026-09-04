# -*- coding: utf-8 -*-
"""
modules/article_rewriter/text_utils.py
Xử lý làm sạch và chuẩn hóa font chữ, khắc phục triệt để lỗi mã hóa kép Mojibake
(ví dụ: UTF-8 bị giải mã sai thành Latin-1 / Windows-1252 làm xuất hiện 'Valentineâs'),
và đưa các ký tự đặc biệt/dấu nháy cong về dạng ASCII chuẩn tương thích 100% với CMS và MySQL.
"""
import re

def clean_mojibake_and_typography(text: str) -> str:
    """
    Chuẩn hóa font chữ, khắc phục triệt để lỗi mã hóa kép Mojibake (UTF-8 bị giải mã Latin-1)
    và đưa các ký tự đặc biệt/dấu nháy cong về dạng ký tự chuẩn ASCII tương thích 100% với CMS/MySQL.
    """
    if not text:
        return ""
    t = str(text)

    # 1. Thử phục hồi chuỗi bị mã hóa kép Latin1/CP1252 -> UTF-8 nếu an toàn
    try:
        if any(c in t for c in ("â\x80", "â€™", "â€", "Ã", "\x80", "\x99")):
            fixed = t.encode("latin1").decode("utf-8")
            t = fixed
    except Exception:
        pass

    # 2. Thay thế các mẫu Mojibake phổ biến từ Windows-1252 / ISO-8859-1
    replacements = {
        "â\x80\x99": "'",
        "â€™": "'",
        "â\x80\x98": "'",
        "â€˜": "'",
        "â\x80\x9c": '"',
        "â€œ": '"',
        "â\x80\x9d": '"',
        "â€\x9d": '"',
        "â\x80\x94": "—",
        "â€”": "—",
        "â\x80\x93": "–",
        "â€“": "–",
        "â\x80\xa6": "...",
        "â€¦": "...",
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "`": "'",
        "´": "'",
    }
    for bad, good in replacements.items():
        t = t.replace(bad, good)

    # 3. Khắc phục triệt để trường hợp các byte điều khiển đã bị nuốt chửng, chỉ còn lại 'âs' hoặc 'â'
    # Ví dụ: Valentineâs -> Valentine's
    t = re.sub(r'([A-Za-z0-9])âs\b', r"\1's", t)
    t = re.sub(r'([A-Za-z0-9])â\b', r"\1'", t)
    t = re.sub(r'\bâ([A-Za-z0-9])', r"'\1", t)
    
    # Loại bỏ các ký tự điều khiển unprintable không hợp lệ (\x80-\x9f)
    t = re.sub(r'[\x80-\x9f]', '', t)

    return t.strip()
