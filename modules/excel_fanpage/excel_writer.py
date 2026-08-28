# -*- coding: utf-8 -*-
from datetime import datetime
from pathlib import Path
import openpyxl

def export_excel_file(valid_items, pages, pages_per_video, kho_path_str, output_dir_str, progress_cb=None):
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
        
        for p in group_pages:
            excel_rows.append({
                'stt': stt,
                'page_name': p,
                'platform': 'Facebook',
                'post_type': 'Reel',
                'caption': current_video['caption'],
                'video_path': current_video['video_path'],
                'first_comment': current_video['first_comment'],
                'post_date': None,
                'post_time': None,
                'timezone': None,
                'action': 'post_now'
            })

        page_idx += len(group_pages)
        video_idx += 1
        stt += 1
        if progress_cb:
            progress_cb(page_idx, len(pages), 'Đã ghép ' + str(page_idx) + '/' + str(len(pages)) + ' Page...')

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'BaiDang'

    headers = [
        'STT', 'Trang', 'Nền tảng', 'Loại bài', 'Nội dung',
        'URL video/ảnh', 'Bình luận đầu tiên', 'Ngày đăng (YYYY-MM-DD)',
        'Giờ đăng (HH:mm)', 'Múi giờ', 'Hành động'
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
    timestamp_str = datetime.now().strftime('%Y%m%d-%H%M%S')
    excel_filename = output_dir / ('blogbio-' + timestamp_str + '.xlsx')
    counter = 1
    while excel_filename.exists():
        excel_filename = output_dir / ('blogbio-' + timestamp_str + '_' + str(counter) + '.xlsx')
        counter += 1

    wb.save(str(excel_filename))

    unused_pages = pages[page_idx:]
    unused_file = None
    if unused_pages:
        unused_file = output_dir / 'page-chua-dang.txt'
        unused_file.write_text('\n'.join(unused_pages), encoding='utf-8')

    return {
        'excel_path': str(excel_filename),
        'total_pages_done': page_idx,
        'total_pages_left': len(unused_pages),
        'unused_file': str(unused_file) if unused_file else None,
        'total_videos_used': video_idx,
        'used_folders': used_folders,
        'last_folder_used': used_folders[-1] if used_folders else None
    }
