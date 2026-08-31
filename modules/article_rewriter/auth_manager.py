# -*- coding: utf-8 -*-
"""
modules/article_rewriter/auth_manager.py
Quản lý phiên xác thực, tự động trích xuất CSRF Token và Cookie của website CMS qua Chrome CDP.
"""
import time
from typing import Tuple, Dict, Any, Callable
from .cdp_browser import CDPBrowser, host_of

class AuthManager:
    def __init__(self, log_cb: Callable = None):
        self.log = log_cb or (lambda m, lv="INFO": None)

    def fetch_session_via_cdp(
        self,
        login_url: str,
        user: str,
        password: str,
        base_url: str,
        chrome_path: str = ""
    ) -> Tuple[bool, Dict[str, Any], str]:
        """
        Khởi chạy Chrome riêng, thực hiện đăng nhập và trích xuất CSRF Token + Cookie.
        Trả về: (success, session_dict, error_message)
        """
        browser = None
        target_url = login_url or (base_url.rstrip("/") + "/login")
        self.log(f"Bắt đầu quá trình lấy Token/Cookie từ: {target_url}", "INFO")

        try:
            browser = CDPBrowser(chrome_path=chrome_path, log_cb=self.log)
            browser.open(target_url)
            time.sleep(1.5)

            if user and password:
                self.log(f"Đang tự động điền tài khoản: {user}...", "INFO")
                browser.autofill_and_login(user, password)
                time.sleep(3.0) # Đợi điều hướng sau login

            # Đọc CSRF Token và Cookie
            csrf_token = browser.get_csrf_token()
            cookie_str = browser.get_cookie_header_str(base_url or target_url)

            # Nếu chưa có cookie trên domain base_url, thử đọc trên target_url
            if not cookie_str:
                cookie_str = browser.get_cookie_header_str(target_url)

            if cookie_str:
                self.log(f"✅ Trích xuất Cookie thành công! (Dài: {len(cookie_str)} ký tự)", "SUCCESS")
            else:
                self.log("⚠️ Cảnh báo: Chưa bắt được Cookie phiên từ trình duyệt!", "WARNING")

            if csrf_token:
                self.log(f"✅ Trích xuất CSRF Token thành công: {csrf_token[:15]}...", "SUCCESS")

            session_data = {
                "base_url": base_url,
                "token": csrf_token,
                "cookie": cookie_str,
                "updated_at": int(time.time())
            }

            return True, session_data, "Lấy Session/Cookie thành công!"

        except Exception as e:
            err_msg = f"Lỗi trong quá trình lấy Token qua CDP: {e}"
            self.log(err_msg, "ERROR")
            return False, {}, err_msg
        finally:
            if browser:
                try: browser.close()
                except Exception: pass
