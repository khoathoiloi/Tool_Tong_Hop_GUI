# -*- coding: utf-8 -*-
from datetime import datetime
from pathlib import Path
import openpyxl

DEFAULT_COMMENT_1 = "watch full here 👉:"

def export_excel_file(valid_items, pages, pages_per_video, kho_path_str, output_dir_str, progress_cb=None, excel_type="token", comment1_text=DEFAULT_COMMENT_1, include_comment=True):
    kho_path = Path(kho_path_str)
    output_dir = Path(output_dir_str)
    total_valid_videos = len(valid_items)
    
    excel_rows = []
    used_folders = []
    stt = 1
    page_idx = 0
    video_idx = 0

    while page_idx < len(pages) and video_idx < total_valid_videos:
        current_video = valid_items[video_idx]
        group_pages = pages[page_idx : page_idx + pages_per_video]
        used_folders.append(current_video['folder_path'])
        
        # Xử lý gán bình luận: chỉ gán khi include_comment=True
        if include_comment:
            raw_or_short_url = current_video.get('raw_link', '')
            fc = current_video.get('first_comment', '')
            if fc:
                import re
                m = re.search(r'https?://[^\s]+', fc)
                if m:
                    raw_or_short_url = m.group(0)
                elif not raw_or_short_url:
                    raw_or_short_url = fc
            final_c1 = comment1_text.strip() if comment1_text else ""
            final_c2 = raw_or_short_url
            final_fc = current_video.get('first_comment', '')
        else:
            final_c1 = None
            final_c2 = None
            final_fc = None

        for p in group_pages:
            if excel_type == "token":
                if isinstance(p, dict):
                    p_name = p.get('page_name', '')
                    uid_val = p.get('uid', '')
                else:
                    p_str = str(p).strip()
                    if '|' in p_str:
                        parts = p_str.split('|', 1)
                        p_name = parts[0].strip()
                        uid_val = parts[1].strip()
                    else:
                        p_name = p_str
                        uid_val = p_str

                excel_rows.append({
                    'stt': stt,
                    'page_name': p_name,
                    'uid': uid_val,
                    'platform': 'Facebook',
                    'post_type': 'Reel',
                    'caption': current_video['caption'],
                    'video_path': current_video['video_path'],
                    'comment_1': final_c1,
                    'comment_2': final_c2,
                    'post_date': None,
                    'post_time': None,
                    'timezone': None,
                    'action': 'post_now'
                })
            else:
                p_name = p.get('page_name', '') if isinstance(p, dict) else str(p).strip()
                excel_rows.append({
                    'stt': stt,
                    'page_name': p_name,
                    'platform': 'Facebook',
                    'post_type': 'Reel',
                    'caption': current_video['caption'],
                    'video_path': current_video['video_path'],
                    'first_comment': final_fc,
                    'post_date': None,
                    'post_time': None,
                    'timezone': None,
                    'action': 'post_now'
                })

        page_idx += len(group_pages)
        video_idx += 1
        stt += 1
        if progress_cb:
            progress_cb(page_idx, len(pages), f"Đã ghép {page_idx}/{len(pages)} Page...")

    wb = openpyxl.Workbook()
    ws = wb.active

    if excel_type == "token":
        ws.title = "DanhSachDangBai"
        headers = [
            "STT", "Trang", "UID", "Nền tảng", "Loại bài", "Nội dung",
            "URL video/ảnh", "Bình luận 1", "Bình luận 2 (Trả lời)", "Ngày đăng (YYYY-MM-DD)",
            "Giờ đăng (HH:mm)", "Múi giờ", "Hành động"
        ]
        ws.append(headers)
        for row_data in excel_rows:
            ws.append([
                row_data['stt'],
                row_data['page_name'],
                row_data['uid'],
                row_data['platform'],
                row_data['post_type'],
                row_data['caption'],
                row_data['video_path'],
                row_data['comment_1'],
                row_data['comment_2'],
                row_data['post_date'],
                row_data['post_time'],
                row_data['timezone'],
                row_data['action']
            ])
    else:
        ws.title = "BaiDang"
        headers = [
            "STT", "Trang", "Nền tảng", "Loại bài", "Nội dung",
            "URL video/ảnh", "Bình luận đầu tiên", "Ngày đăng (YYYY-MM-DD)",
            "Giờ đăng (HH:mm)", "Múi giờ", "Hành động"
        ]
        ws.append(headers)
        for row_data in excel_rows:
            ws.append([
                row_data['stt'],
                row_data['page_name'],
                row_data['platform'],
                row_data['post_type'],
                row_data['caption'],
                row_data['video_path'],
                row_data['first_comment'],
                row_data['post_date'],
                row_data['post_time'],
                row_data['timezone'],
                row_data['action']
            ])

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp_str = datetime.now().strftime("%Y%m%d-%H%M%S")
    prefix = "blogbio-token" if excel_type == "token" else "blogbio"
    excel_filename = output_dir / f"{prefix}-{timestamp_str}.xlsx"
    counter = 1
    while excel_filename.exists():
        excel_filename = output_dir / f"{prefix}-{timestamp_str}_{counter}.xlsx"
        counter += 1

    wb.save(str(excel_filename))

    unused_pages = pages[page_idx:]
    unused_file = None
    if unused_pages:
        unused_file = output_dir / "page-chua-dang.txt"
        lines_to_write = []
        for u in unused_pages:
            if isinstance(u, dict):
                lines_to_write.append(u.get('raw', str(u)))
            else:
                lines_to_write.append(str(u))
        unused_file.write_text("\n".join(lines_to_write), encoding="utf-8")

    return {
        'excel_path': str(excel_filename),
        'total_pages_done': page_idx,
        'total_pages_left': len(unused_pages),
        'unused_file': str(unused_file) if unused_file else None,
        'total_videos_used': video_idx,
        'used_folders': used_folders,
        'last_folder_used': used_folders[-1] if used_folders else None,
        'excel_type': excel_type
    }