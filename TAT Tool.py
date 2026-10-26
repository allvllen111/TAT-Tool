# -*- coding: utf-8 -*-
"""TikTok Upload Tool - BAN 1 FILE DUY NHAT (GUI + engine upload Selenium + GPM).
VERSION: v3.9 - sua loi thread-safety: cac luong phu (quet info / upload)
khong cap nhat truc tiep Treeview nua ma dua vao hang doi UI de main thread
xu ly (khac phuc nguy co treo/crash GUI khi chay nhieu luong).
VERSION: v3.2 - accounts.txt chuan 8 truong (group luu rieng trong
tool_settings.json), chuot phai Copy thong tin account nhieu dinh dang,
double-click mo bang chi tiet account. (v3.1: bang account la chinh,
cot Mail backup, Add Account dan text, tu xoa cache TikTok sau upload.
v3.0: 3 tinh nang GUI (chuot phai xoa job o bang status,
chia luoi cua so trinh duyet theo so luong, bang account cot moi nhu anh mau).
Mo len ma tieu de cua so khong co "v3.1" thi do la BAN CU, tai lai file nay.

Gop tu 4 file cu: gui_upload.py (giao dien v2.1) + accounts.py (doc account)
+ upload_v2.py (engine upload Selenium) + 2 hang so cua common.py
(ROOT_DIR, GPM_API_URL). Phan Playwright (common/login/mailcode/antibot/
fingerprint) DA BO HAN - dung huong hien tai: login tay trong GPM Login,
upload bang Selenium qua remote_debugging_port nhu test1.py.

CACH DUNG:
  1. Dat file nay o D:\\tooltiktok\\ (acc.txt dang o do san) hoac trong
     D:\\tooltiktok\\app\\ deu duoc - no tu tim accounts.txt canh file
     truoc, khong thay moi tim o thu muc cha.
  2. Chay:  python "TAT Tool.py"
  3. Test nhanh khong can GUI:
     python "TAT Tool.py" --cli <idTiktok> "D:\\video.mp4" "caption"

Tinh nang engine (giu nguyen ban dang chay tot):
  - Start GPM profile kem remote_debugging_port rieng (goc 40444).
  - Chon gpmdriver KHOP phien ban trinh duyet (147/154...) tu /json/version.
  - Xac nhan session bang GIAO DIEN trang Studio (khong chi dua cookie).
  - Chon dung tab tiktokstudio, cho khoi upload san sang, gan file co thu
    lai, xac nhan da nhan qua o caption/input.files trong ca cua so cho.
  - Dat caption, cho nut Post toi da 300s, bam Post, xac nhan CHI bang URL.
  - Dang thanh cong -> XOA video goc (tat bang DELETE_AFTER_UPLOAD = False).
"""
import glob
import json
import math
import os
import queue
import random
import re
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
import webbrowser

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# ============================================================
# ==== ENGINE AUTO LOGIN TAT (gop tu tat_login_engine.py) ====
# ============================================================
"""
ENGINE AUTO LOGIN TAT (tach tu auto_login_tat.py) - da gop thang
vao file TAT Tool.py, khong con la file rieng nua.

Dung chung cho moi GUI: nhan 1 Selenium driver DA gan vao profile GPM
va 1 dict account cua accounts.txt, tu dang nhap TikTok (lay code 6 so
qua API get_code_oauth2, khong duoc thi khoi phuc qua Outlook web +
fviainboxes nhu ban TAT goc).

API chinh:
    ok, result = tat_login(driver, acc)
    acc = {"id", "password", "email", "passmail" (pass Outlook),
           "refresh_token", "client_id", "mailbackup" (mail khoi phuc)}
    ok=True va result="ĐÃ ĐĂNG NHẬP" khi login thanh cong.

Module nay KHONG tu mo/dong profile GPM - GUI tu lo (start profile,
gan driver, kill browser) nhu cach tool Upload dang lam voi upload.
"""
import time
import re
import json
import traceback

import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait


# ==== URL + LOCATOR cua trang TikTok (lay nguyen tu auto_login_tat.py) ====
SETTING_URL = "https://www.tiktok.com/setting?lang=en"
TAT_UPLOAD_URL = "https://www.tiktok.com/upload"
LOGIN_URL = "https://www.tiktok.com/login/"
PAGE_TIMEOUT = 60

SUCCESS_LOCATOR = (By.XPATH, "//button[@data-e2e='select_video_button']")
LOGIN_BUTTON_LOCATOR = (By.XPATH, "//*[@id='loginContainer']/div[1]/div/div/div[3]/div[2]")
EMAIL_OPTION_LOCATOR = (By.XPATH, "//a[@href='/login/phone-or-email/email' and contains(text(), 'email')]")
USERNAME_INPUT_LOCATOR = (By.XPATH, "//input[@name='username' or @placeholder='Email or Username' or @placeholder='Email hoặc Tên người dùng']")
PASSWORD_INPUT_LOCATOR = (By.XPATH, "//input[@type='password']")
SUBMIT_BUTTON_LOCATOR = (By.XPATH, "//button[@type='submit']")
CODE_INPUT_LOCATOR = (By.XPATH, "//input[@placeholder='Enter 6-digit code' or @placeholder='Nhập mã gồm 6 chữ số']")
CODE_CONFIRM_BUTTON_LOCATOR = (By.XPATH, "//div[contains(@class,'pc-email-otp-next-btn')]//button[@data-testid='tux-web-button']")
VERIFY_POPUP_LOCATOR = (By.XPATH, "//div[contains(., 'Xác minh đó là bạn') or contains(., 'Verify it')]")
EMAIL_VERIFY_OPTION_LOCATOR = (By.XPATH, "//button[contains(text(), 'Email')] | //div[contains(@class, 'verify')]//button | //label[contains(text(), 'Email')]")


def log(message):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [TAT] {message}", flush=True)


def log_exception(message):
    log(message)
    print(traceback.format_exc(), flush=True)


def focus_browser(driver):
    try:
        handle = driver.current_window_handle
        driver.switch_to.window(handle)
    except Exception:
        pass
    try:
        driver.execute_script("window.focus();")
    except Exception:
        pass


def wait_page_ready(driver, timeout=30):
    try:
        WebDriverWait(driver, timeout).until(lambda d: d.execute_script("return document.readyState") == "complete")
    except Exception:
        log("Trang chưa báo readyState=complete; tiếp tục kiểm tra.")


def open_new_tab(driver, url):
    log(f"Mở tab mới: {url}")
    driver.switch_to.new_window("tab")
    try:
        driver.get(url)
    except Exception as exc:
        log(f"Thông báo khi tải trang: {exc}")
    wait_page_ready(driver)
    log(f"URL hiện tại: {driver.current_url}")


def navigate_page(driver, url):
    log(f"Điều hướng đến: {url}")
    try:
        driver.get(url)
    except Exception as exc:
        log(f"Thông báo khi điều hướng: {exc}")
    wait_page_ready(driver)
    log(f"URL sau điều hướng: {driver.current_url}")


def type_text_with_delay(driver, locator, text, delay=150):
    element = driver.find_element(*locator)
    element.clear()
    for char in text:
        element.send_keys(char)
        time.sleep(delay / 1000)


def find_visible_element(driver, locator, timeout=15):
    """Tìm element ĐANG HIỂN THỊ + enabled trong số các element trùng locator.

    find_element() chỉ lấy element đầu tiên trong DOM - trên fviainboxes
    có nhiều input#username (bản ẩn cho mobile / form khác), lấy trúng
    bản ẩn là 'element not interactable' ngay.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        for element in driver.find_elements(*locator):
            try:
                if element.is_displayed() and element.is_enabled():
                    return element
            except Exception:
                continue
        time.sleep(0.5)
    return None


def fill_visible_input(driver, locator, text, delay=80):
    """Điền text vào input đang hiển thị. Selenium gõ không được thì
    dùng JS native setter (trang React: gán .value trực tiếp không ăn,
    phải dùng setter của HTMLInputElement + bắn event input/change)."""
    element = find_visible_element(driver, locator, timeout=15)
    if element is None:
        raise RuntimeError(f"Không tìm thấy input đang hiển thị: {locator}")

    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        time.sleep(0.3)
        element.click()
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", element)
        except Exception:
            pass

    try:
        element.clear()
        for char in text:
            element.send_keys(char)
            time.sleep(delay / 1000)
    except Exception as exc:
        log(f"  Gõ thường không được ({type(exc).__name__}), điền bằng JS...")
        driver.execute_script("""
            const el = arguments[0], value = arguments[1];
            el.focus();
            const setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
            setter.call(el, value);
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
        """, element, text)

    current = (element.get_attribute("value") or "").strip()
    if current != text.strip():
        raise RuntimeError(f"Điền xong nhưng value không khớp: '{current}' != '{text}'")
    return element


def extract_6digit_code(text):
    match = re.search(r'\b\d{6}\b', text)
    return match.group(0) if match else ""


# ============================================================
# FIX 1: Lấy mã bảo mật Microsoft 6 số - ĐA NGÔN NGỮ
# ============================================================
def normalize_digits(text):
    """Số Ả Rập / Ba Tư / full-width -> số Latin 0-9."""
    return text.translate(str.maketrans(
        "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹０１２３４５６７８９",
        "012345678901234567890123456789"
    ))


MS_SECURITY_KEYWORDS = [
    "security code", "single-use code", "verification code",        # Anh
    "mã bảo mật", "mã an toàn", "mã xác minh", "mã xác thực",       # Việt
    "sicherheitscode", "sicherheits-code", "bestätigungscode", "verifizierungscode",  # Đức
    "رمز الأمان", "رمز الحماية", "رمز التحقق",                        # Ả Rập / Saudi
    "安全代码", "安全码", "验证码", "验证代码", "安全代碼", "驗證碼", "驗證代碼",  # Trung
    "セキュリティコード", "セキュリティ コード", "確認コード", "認証コード",  # Nhật
    "보안 코드", "보안코드", "인증 코드", "인증코드", "확인 코드",      # Hàn
    "código de seguridad", "código de verificación",                # Tây Ban Nha
    "code de sécurité", "code de vérification",                     # Pháp
    "codice di sicurezza", "codice di verifica",                    # Ý
    "código de segurança", "código de verificação",                 # Bồ Đào Nha
    "код безопасности", "код подтверждения",                        # Nga
]


def extract_ms_security_code(text):
    """Trích mã 6 số của Microsoft bất kể mail là ngôn ngữ nào.

    Không phụ thuộc dấu ':' nữa (mỗi ngôn ngữ dùng ':', '：', '：' khác nhau,
    mail RTL tiếng Ả Rập code còn có thể đứng trước keyword).
    """
    if not text:
        return ""
    text = normalize_digits(text)

    # Ưu tiên 0 - QUAN TRỌNG NHẤT: dòng "Keyword: 863380" trong mail đang mở
    # Đúng format trong ảnh fviainboxes: một dòng riêng "Security code: 863380"
    # Tìm theo TỪNG DÒNG trước khi gộp text, để không bắt nhầm code của
    # mail cũ (8m ago) nằm trong danh sách / nội dung ẩn ở cùng trang.
    keyword_pattern = "|".join(re.escape(kw) for kw in MS_SECURITY_KEYWORDS)
    for line in text.splitlines():
        found = re.search(
            rf"(?:{keyword_pattern})\s*[:：]\s*(?<!\d)(\d{{6}})(?!\d)",
            line.strip(), re.IGNORECASE
        )
        if found:
            return found.group(1)

    clean = re.sub(r"\s+", " ", text)

    # Ưu tiên 1: code nằm SAU keyword (hầu hết các ngôn ngữ)
    for kw in MS_SECURITY_KEYWORDS:
        for m in re.finditer(re.escape(kw), clean, re.IGNORECASE):
            found = re.search(r"(?<!\d)(\d{6})(?!\d)", clean[m.end():m.end() + 100])
            if found:
                return found.group(1)

    # Ưu tiên 2: code nằm TRƯỚC keyword (mail RTL / một số mail Đức)
    for kw in MS_SECURITY_KEYWORDS:
        for m in re.finditer(re.escape(kw), clean, re.IGNORECASE):
            found = re.search(r"(?<!\d)(\d{6})(?!\d)", clean[max(0, m.start() - 60):m.start()])
            if found:
                return found.group(1)

    # Ưu tiên 3: một dòng chỉ chứa đúng 6 số
    for line in text.splitlines():
        stripped = line.strip()
        if re.fullmatch(r"\d{6}", stripped):
            return stripped

    # Cuối cùng: số 6 chữ số đầu tiên trong nội dung mail
    candidates = re.findall(r"(?<!\d)(\d{6})(?!\d)", clean)
    return candidates[0] if candidates else ""


def get_code_from_fviainboxes_js(driver):
    """(v7 - bản chốt) Bắt code bằng JS quét TOÀN BỘ nơi mail có thể nằm.

    Vì sao v5/v6 vẫn không bắt được dù code hiện rõ trên màn hình?
    Cả 2 bản trước đều chỉ đọc document.body.innerText của trang chính.
    Nhưng nội dung mail Microsoft trên fviainboxes KHÔNG nằm ở trang chính:
    nó được nhúng trong <iframe> (thường là srcdoc) để cách ly HTML mail.
    innerText / body.text của trang chính không hề chứa text trong iframe,
    nên click bao nhiêu lần, poll bao nhiêu lần cũng không thấy code.
    Đó cũng là lý do code gốc đọc page_source thì thấy code (srcdoc nằm
    trong HTML) nhưng lại bắt nhầm code của mail cũ.

    Bản này JS chạy trong trang và quét theo thứ tự ưu tiên:
      1) iframe đang hiển thị (innerText + textContent + srcdoc)
      2) trang chính: innerText, rồi textContent (kể cả pane đã bị ẩn)
    Click cũng sửa lại: không click li[0] toàn trang nữa (có thể là menu),
    mà click đúng mục inbox có chữ 'account-security-noreply' ở trên cùng.
    Trả về 'code|source' để log biết code được bắt từ đâu.
    """
    keywords_json = json.dumps(MS_SECURITY_KEYWORDS, ensure_ascii=False)
    script = r"""
        var callback = arguments[arguments.length - 1];
        var keywords = KEYWORDS_JSON;

        function normalizeDigits(s) {
            return (s || '').replace(/[\u0660-\u0669\u06F0-\u06F9\uFF10-\uFF19]/g, function(ch) {
                var c = ch.charCodeAt(0);
                if (c >= 0x0660 && c <= 0x0669) return String(c - 0x0660);
                if (c >= 0x06F0 && c <= 0x06F9) return String(c - 0x06F0);
                return String(c - 0xFF10);
            });
        }

        function extract(text) {
            if (!text) return '';
            text = normalizeDigits(text);
            var lines = text.split(/\n+/);
            for (var i = 0; i < lines.length; i++) {
                var low = lines[i].toLowerCase();
                for (var k = 0; k < keywords.length; k++) {
                    if (low.indexOf(keywords[k].toLowerCase()) !== -1) {
                        var m = lines[i].match(/[:\uFF1A]\s*(\d{6})(?!\d)/);
                        if (m) return m[1];
                    }
                }
            }
            var clean = text.replace(/\s+/g, ' ');
            var cleanLow = clean.toLowerCase();
            for (var k2 = 0; k2 < keywords.length; k2++) {
                var kw = keywords[k2].toLowerCase();
                var idx = cleanLow.indexOf(kw);
                while (idx !== -1) {
                    var m2 = clean.substring(idx, idx + 160).match(/(\d{6})(?!\d)/);
                    if (m2) return m2[1];
                    idx = cleanLow.indexOf(kw, idx + 1);
                }
            }
            return '';
        }

        function collectCandidates() {
            var out = [];
            // 1) Các iframe trước - nội dung mail nằm ở đây
            var frames = document.querySelectorAll('iframe');
            for (var i = 0; i < frames.length; i++) {
                var f = frames[i];
                var rect = f.getBoundingClientRect();
                var visible = rect.width > 100 && rect.height > 50;
                try {
                    var doc = f.contentDocument;
                    if (doc && doc.body) {
                        out.push({text: doc.body.innerText || '', source: 'iframe-innerText#' + i, prio: visible ? 0 : 3});
                        out.push({text: doc.body.textContent || '', source: 'iframe-textContent#' + i, prio: visible ? 1 : 4});
                    }
                } catch (e) { /* iframe cross-origin (quảng cáo): bỏ qua */ }
                try {
                    var sd = f.getAttribute('srcdoc');
                    if (sd) {
                        var div = document.createElement('div');
                        div.innerHTML = sd;
                        out.push({text: div.innerText || div.textContent || '', source: 'iframe-srcdoc#' + i, prio: visible ? 0 : 3});
                    }
                } catch (e) {}
            }
            // 2) Shadow DOM (nếu trang bọc nội dung mail trong web component)
            var allEls = document.querySelectorAll('*');
            for (var s = 0; s < allEls.length; s++) {
                if (allEls[s].shadowRoot) {
                    out.push({text: allEls[s].shadowRoot.textContent || '', source: 'shadowRoot#' + s, prio: 2});
                }
            }
            // 3) Trang chính
            if (document.body) {
                out.push({text: document.body.innerText || '', source: 'main-innerText', prio: 2});
                out.push({text: document.body.textContent || '', source: 'main-textContent', prio: 5});
            }
            out.sort(function(a, b) { return a.prio - b.prio; });
            return out;
        }

        function scanOnce() {
            var cands = collectCandidates();
            for (var i = 0; i < cands.length; i++) {
                var code = extract(cands[i].text);
                if (code) return code + '|' + cands[i].source;
            }
            return '';
        }

        function findEmailItem() {
            var all = document.querySelectorAll('li, a, button, [role="button"], div');
            var matches = [];
            for (var i = 0; i < all.length; i++) {
                var el = all[i];
                var t = (el.innerText || '').trim();
                if (!t || t.length > 200) continue;
                if (t.toLowerCase().indexOf('account-security-noreply') === -1) continue;
                var r = el.getBoundingClientRect();
                if (r.width <= 0 || r.height <= 0) continue;
                matches.push({el: el, top: r.top, len: t.length});
            }
            // Trên cùng trước (mail mới nhất), element nhỏ nhất trong nhóm đó
            matches.sort(function(a, b) { return (a.top - b.top) || (a.len - b.len); });
            if (matches.length) return matches[0].el;
            var lis = document.querySelectorAll('li');
            return lis.length ? lis[0] : null;
        }

        var attempts = 0;
        function tryOnce() {
            attempts++;
            var already = scanOnce();
            if (already) { callback(already); return; }
            var item = findEmailItem();
            if (item) { try { item.scrollIntoView({block: 'center'}); } catch (e) {} item.click(); }
            var started = Date.now();
            var timer = setInterval(function() {
                var found = scanOnce();
                if (found) { clearInterval(timer); callback(found); return; }
                if (Date.now() - started > 4000) {
                    clearInterval(timer);
                    if (attempts >= 8) { callback(''); } else { tryOnce(); }
                }
            }, 100);
        }
        tryOnce();
    """.replace("KEYWORDS_JSON", keywords_json)

    try:
        driver.set_script_timeout(90)
        result = driver.execute_async_script(script)
        result = str(result).strip() if result else ""
        if "|" in result:
            code, source = result.split("|", 1)
            code = code.strip()
            if re.fullmatch(r"\d{6}", code):
                log(f"  JS scan thấy code ở: {source}")
                return code
            return ""
        return result if re.fullmatch(r"\d{6}", result) else ""
    except Exception as exc:
        log(f"  Lỗi JS scan fviainboxes (v7): {exc}")
        return ""


def extract_code_from_page_and_frames(driver):
    """Fallback Python: đọc trang chính, rồi switch vào TỪNG iframe đọc tiếp.
    Nội dung mail nằm trong iframe nên chỉ đọc body trang chính là không thấy."""
    try:
        code = extract_ms_security_code(driver.find_element(By.TAG_NAME, "body").text)
        if code:
            return code
    except Exception:
        pass

    frame_count = len(driver.find_elements(By.TAG_NAME, "iframe"))
    for idx in range(frame_count):
        try:
            frames = driver.find_elements(By.TAG_NAME, "iframe")
            driver.switch_to.frame(frames[idx])
            try:
                code = extract_ms_security_code(driver.find_element(By.TAG_NAME, "body").text)
            except Exception:
                code = ""
            driver.switch_to.default_content()
            if code:
                log(f"  Fallback: thấy code trong iframe #{idx}")
                return code
        except Exception:
            try:
                driver.switch_to.default_content()
            except Exception:
                pass
    return ""


def dump_fvia_diagnostic(driver):
    """Khi vẫn không bắt được code: log cấu trúc trang để biết code nằm ở đâu
    (số iframe, iframe nào có chữ 'security', độ dài text từng nguồn)."""
    try:
        info = driver.execute_script(r"""
            var out = {iframes: [], lis: document.querySelectorAll('li').length,
                       mainInnerLen: 0, mainTextLen: 0, mainHasSecurity: false};
            if (document.body) {
                out.mainInnerLen = (document.body.innerText || '').length;
                out.mainTextLen = (document.body.textContent || '').length;
                out.mainHasSecurity = (document.body.textContent || '').toLowerCase().indexOf('security') !== -1;
            }
            var frames = document.querySelectorAll('iframe');
            for (var i = 0; i < frames.length; i++) {
                var f = {i: i, src: (frames[i].getAttribute('src') || '').substring(0, 80),
                         srcdocLen: (frames[i].getAttribute('srcdoc') || '').length,
                         bodyLen: -1, hasSecurity: false};
                try {
                    var d = frames[i].contentDocument;
                    if (d && d.body) {
                        f.bodyLen = (d.body.textContent || '').length;
                        f.hasSecurity = (d.body.textContent || '').toLowerCase().indexOf('security') !== -1;
                    }
                } catch (e) { f.bodyLen = -2; }
                out.iframes.push(f);
            }
            return JSON.stringify(out);
        """)
        log(f"  🔍 Diagnostic fviainboxes: {info}")
    except Exception as exc:
        log(f"  Không dump được diagnostic: {exc}")


def element_exists(driver, locator):
    try:
        return any(element.is_displayed() for element in driver.find_elements(*locator))
    except Exception:
        return False


def get_code_from_outlook(email, refresh_token, client_id, max_retries=1, wait_time=3):
    """Lấy code 6 chữ số từ TikTok email qua API."""
    try:
        log(f"🔍 Poll Outlook API (get_code_oauth2): {email}")

        for attempt in range(max_retries):
            log(f"  Lần {attempt + 1}/{max_retries}...")

            response = requests.post(
                "https://tools.dongvanfb.net/api/get_code_oauth2",
                json={
                    "email": email,
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "type": "tiktok"
                },
                timeout=60
            )

            response.raise_for_status()
            payload = response.json()

            if payload.get("status") is False:
                content = payload.get("content", "Error")
                log(f"    status=False: {content}")
                if attempt < max_retries - 1:
                    time.sleep(wait_time)
                continue

            code = payload.get("code", "").strip()
            if code and len(str(code)) == 6:
                log(f"✅ Lấy code thành công: {code}")
                return code

            log(f"    Chưa có code, retry...")
            if attempt < max_retries - 1:
                time.sleep(wait_time)

        log(f"❌ Timeout: API không trả code")
        log(f"⚠️  Refresh token có thể đã hết hạn. Cần khôi phục account Hotmail.")
        return ""

    except Exception as exc:
        log(f"❌ Lỗi API: {exc}")
        return ""


def get_mail_name(email):
    """Extract mail name (trước @) từ email."""
    return email.split("@")[0].strip() if "@" in email else email


# ============================================================
# (v8) Lấy TikTok code trong Outlook web
# ============================================================
def extract_tiktok_code(text):
    """Trích code TikTok 6 số. Mail TikTok để code ngay ở SUBJECT:
    '123456 is your verification code' - nhìn thấy ngay trong danh sách
    mail mà không cần mở mail. Code cũ không hề đọc subject/list item,
    chỉ cố tìm iframe[@title='Email content'] -> title khác là văng
    NoSuchElement (đúng đoạn stacktrace gpmdriver anh gửi)."""
    if not text:
        return ""
    text = normalize_digits(text)

    # 1) Code đứng đầu câu/subject: "123456 is your verification code ..."
    #    và đúng format trong ảnh Outlook: "415961 là mã gồm 6 chữ số của bạn"
    found = re.search(
        r"(?<!\d)(\d{6})(?!\d)\s*(?:is your|ist ihr|là|est votre|es tu)?\s*"
        r"(?:verification code|verify code|6[-\s]?digit code|mã gồm 6 chữ số|mã 6 chữ số|"
        r"mã xác minh|mã xác thực|mã|sicherheitscode|código)",
        text, re.IGNORECASE)
    if found:
        return found.group(1)

    # 2) Keyword đứng trước code: "verification code is: 123456", "Mã xác minh: 123456"
    #    và đúng format thân mail trong ảnh: "Mã gồm 6 chữ số của bạn là: 415961"
    found = re.search(
        r"(?:verification code|verify code|your code|6[-\s]?digit code|mã gồm 6 chữ số|"
        r"mã 6 chữ số|6 chữ số|mã xác minh|mã xác thực|mã bảo mật|"
        r"código de verificación|code de vérification|sicherheitscode|セキュリティ|보안 코드|验证码)"
        r"[^0-9]{0,40}(?<!\d)(\d{6})(?!\d)",
        text, re.IGNORECASE)
    if found:
        return found.group(1)

    # 3) Một dòng chỉ chứa đúng code (mail mở: code hiện 1 dòng riêng)
    for line in text.splitlines():
        if re.fullmatch(r"\s*\d{6}\s*", line):
            return line.strip()
    return ""


def scan_frames_for_tiktok_code(driver):
    """Quét TẤT CẢ iframe (không chỉ iframe title='Email content' như code cũ -
    title thay đổi theo ngôn ngữ/giao diện Outlook là tìm không ra)."""
    frame_count = len(driver.find_elements(By.TAG_NAME, "iframe"))
    for idx in range(frame_count):
        try:
            frames = driver.find_elements(By.TAG_NAME, "iframe")
            driver.switch_to.frame(frames[idx])
            try:
                code = extract_tiktok_code(driver.find_element(By.TAG_NAME, "body").text)
            except Exception:
                code = ""
            driver.switch_to.default_content()
            if code:
                log(f"  Fallback TikTok: thấy code trong iframe #{idx}")
                return code
        except Exception:
            try:
                driver.switch_to.default_content()
            except Exception:
                pass
    return ""


def get_tiktok_code_from_outlook(driver, attempts=10, delay=3):
    """Poll Outlook tìm TikTok code theo 3 nguồn, theo thứ tự:
    1) Text của mail ĐẦU TIÊN (mới nhất) trong danh sách - code nằm ở subject
    2) Mọi iframe sau khi click mở mail (nội dung mail thật)
    3) Reading pane bằng JS (bỏ qua các item trong danh sách để khỏi
       bắt nhầm code của mail cũ trong 9 mail kia)
    """
    for poll in range(attempts):
        try:
            tiktok_emails = driver.find_elements(By.XPATH,
                "//div[@role='option' and contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'tiktok')]")

            if tiktok_emails:
                log(f"  ✓ Tìm thấy {len(tiktok_emails)} TikTok emails")

                # Chọn mail MỚI NHẤT theo vị trí TRÊN MÀN HÌNH (top nhỏ nhất),
                # không lấy [0] theo thứ tự DOM: danh sách Outlook là list ảo,
                # phần tử đầu trong DOM chưa chắc là mail trên cùng (10:33 AM
                # trong ảnh), lấy sai là trúng mail cũ.
                newest_email = tiktok_emails[0]
                try:
                    best_top = None
                    for item in tiktok_emails:
                        try:
                            if not item.is_displayed():
                                continue
                            top = driver.execute_script(
                                "return arguments[0].getBoundingClientRect().top;", item)
                            if best_top is None or top < best_top:
                                best_top = top
                                newest_email = item
                        except Exception:
                            continue
                except Exception:
                    pass

                # Nguồn 1: subject/list item của mail mới nhất (trên cùng)
                try:
                    item_text = newest_email.text
                    log(f"  Mail mới nhất (trên cùng): {item_text[:120]!r}")
                    code = extract_tiktok_code(item_text)
                    if code:
                        log(f"  ✅ Lấy TikTok code từ subject/list: {code}")
                        return code
                except Exception as e:
                    log(f"  Lỗi đọc list item: {e}")

                # Mở mail mới nhất
                try:
                    newest_email.click()
                except Exception:
                    try:
                        driver.execute_script("arguments[0].click();", newest_email)
                    except Exception:
                        pass
                time.sleep(2)

                # Nguồn 2: mọi iframe
                code = scan_frames_for_tiktok_code(driver)
                if code:
                    log(f"  ✅ Lấy TikTok code từ iframe mail: {code}")
                    return code

                # Nguồn 3: reading pane (JS, loại trừ list item)
                try:
                    candidates = driver.execute_script(r"""
                        var out = [];
                        var all = document.querySelectorAll('div, section, article, td, span, p');
                        for (var i = 0; i < all.length; i++) {
                            var el = all[i];
                            if (el.closest && el.closest("[role='option']")) continue;
                            var t = (el.innerText || '').trim();
                            if (t && t.length <= 600 && /code/i.test(t) && /\d{6}/.test(t)) out.push(t);
                            if (out.length >= 20) break;
                        }
                        return out;
                    """) or []
                    for cand in candidates:
                        code = extract_tiktok_code(cand)
                        if code:
                            log(f"  ✅ Lấy TikTok code từ reading pane: {code}")
                            return code
                except Exception as e:
                    log(f"  Lỗi đọc reading pane: {e}")

            if poll < attempts - 1:
                log(f"  Chưa có TikTok mail, retry... ({poll + 1}/{attempts})")
                time.sleep(delay)

        except Exception as e:
            log(f"  Lỗi poll Outlook: {e}")
            time.sleep(delay)

    log("  ❌ Timeout: Không tìm được TikTok code email")
    return ""



def recover_outlook_code(driver, email, password, mail_kp):
    """Khôi phục + lấy code từ Outlook khi token die.

    FIX 2: Lưu handle của từng tab ngay từ đầu.
    - Selenium KHÔNG tự chuyển focus khi close() một tab (chỉ giao diện
      trình duyệt tự hiện tab trước đó). Phải switch_to.window() thủ công.
    - Không dùng window_handles[0]: đó là tab đầu tiên của profile GPM,
      không phải tab TikTok.
    """
    # Lưu handle TRƯỚC try để finally luôn dùng được
    tiktok_handle = driver.current_window_handle
    outlook_handle = None
    fvia_handle = None

    try:
        log(f"🔄 Khôi phục Outlook account: {email}")

        # Mở tab Outlook login
        driver.switch_to.new_window("tab")
        outlook_handle = driver.current_window_handle
        driver.get("https://login.live.com/")
        time.sleep(2)

        # Nhập email
        try:
            email_input = WebDriverWait(driver, 15).until(
                lambda d: d.find_element(By.XPATH, "//input[@type='email' or @id='i0116']")
            )
            email_input.clear()
            type_text_with_delay(driver, (By.XPATH, "//input[@type='email' or @id='i0116']"), email)
            driver.find_element(By.XPATH, "//button[@type='submit' or @id='idSIButton9']").click()
            time.sleep(2)
        except Exception as exc:
            log(f"  Lỗi nhập email Outlook: {exc}")
            return ""

        # Check nếu có nút "Sử dụng mật khẩu của bạn" (Use password instead)
        try:
            time.sleep(1)
            log("  Tìm nút 'Sử dụng mật khẩu của bạn'...")
            use_pwd_xpaths = [
                "//a[contains(text(), 'mật khẩu')]",
                "//button[contains(text(), 'mật khẩu')]",
                "//div[@role='button'][contains(., 'mật khẩu')]",
                "//span[contains(text(), 'mật khẩu')]//..",
                "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ', 'abcdefghijklmnopqrstuvwxyzaaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyyyd'), 'su dung mat khau')]",
            ]

            use_pwd_btn = None
            for xpath in use_pwd_xpaths:
                try:
                    elements = driver.find_elements(By.XPATH, xpath)
                    if elements:
                        use_pwd_btn = elements[0]
                        log(f"  ✓ Tìm thấy nút qua XPath: {xpath}")
                        break
                except Exception:
                    pass

            if use_pwd_btn:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", use_pwd_btn)
                time.sleep(0.5)
                use_pwd_btn.click()
                log("  ✓ Clicked 'Sử dụng mật khẩu của bạn'")
                time.sleep(2)
            else:
                log("  ⚠️  Không tìm được nút 'Sử dụng mật khẩu', tiếp tục...")
        except Exception as exc:
            log(f"  ⚠️  Lỗi click nút password: {exc}")
            pass

        # Nhập password
        try:
            log("  Chờ password input xuất hiện...")
            pwd_input = WebDriverWait(driver, 30).until(
                lambda d: d.find_element(By.XPATH, "//input[@type='password']")
            )
            pwd_input.clear()
            log(f"  Nhập password mail...")
            type_text_with_delay(driver, (By.XPATH, "//input[@type='password']"), password)
            time.sleep(1)

            try:
                submit_btn = driver.find_element(By.XPATH, "//button[@type='submit' or @id='idSIButton9']")
                log("  Click nút submit password...")
                submit_btn.click()
            except Exception:
                log("  Nhấn Enter để submit password...")
                pwd_input.send_keys(Keys.RETURN)
            time.sleep(3)
        except Exception as exc:
            log(f"  Lỗi nhập password: {exc}")
            return ""

        # Check nếu cần mail khôi phục (MFA / recovery flow)
        if mail_kp:
            try:
                log(f"  Tìm option mail khôi phục: {mail_kp}")
                mail_name = get_mail_name(mail_kp)

                recovery_inputs = driver.find_elements(By.XPATH, "//input[@id='iProof0']")
                if recovery_inputs:
                    recovery_inputs[0].click()
                    time.sleep(1)

                    recovery_box = WebDriverWait(driver, 10).until(
                        lambda d: d.find_element(By.XPATH, "//input[@id='iProofEmail']")
                    )
                    recovery_box.clear()
                    type_text_with_delay(driver, (By.XPATH, "//input[@id='iProofEmail']"), mail_name)
                    time.sleep(1)

                    driver.find_element(By.XPATH, "//input[@id='iSelectProofAction']").click()
                    time.sleep(2)
                    log(f"  ✓ Đã gửi code tới: {email} (recovery: {mail_kp})")

                    # ===== Mở fviainboxes để lấy code =====
                    log(f"  Mở fviainboxes để lấy code...")
                    outlook_handle = driver.current_window_handle  # lưu chắc chắn tab Hotmail
                    driver.execute_script("window.open('https://fviainboxes.com/', '_blank');")
                    time.sleep(2)

                    fvia_handle = driver.window_handles[-1]
                    driver.switch_to.window(fvia_handle)
                    time.sleep(3)

                    # Nhập mail KP vào username
                    # FIX (v6): không dùng find_element(#username) nữa - nó lấy
                    # trúng input ẨN đầu tiên trong DOM -> 'element not
                    # interactable' (log 17:23:32 -> 17:23:38). Phải chọn đúng
                    # input đang hiển thị, gõ không được thì điền bằng JS.
                    log(f"  Nhập username: {mail_name}")
                    try:
                        fill_visible_input(driver, (By.CSS_SELECTOR, "input#username"), mail_name)
                        log(f"  ✓ Đã nhập username: {mail_name}")
                        time.sleep(1)
                    except Exception as e:
                        log(f"  Lỗi nhập username fviainboxes: {e}")

                    # Click Get Email button
                    try:
                        get_email_btn = WebDriverWait(driver, 10).until(
                            lambda d: d.find_element(By.XPATH, "//button[@type='submit' and .//span[normalize-space()='Get Email']]")
                        )
                        log("  Click 'Get Email'...")
                        get_email_btn.click()
                        time.sleep(5)
                    except Exception as e:
                        log(f"  Lỗi click Get Email: {e}")

                    # ===== FIX (v4): Phải click mail 2-3 lần, và ĐỌC NGAY sau mỗi lần click =====
                    # fviainboxes: nhấn vào mail thì nội dung chỉ hiện vài giây
                    # rồi biến mất, phải click lại nó mới hiện lại.
                    # Code cũ sai ở chỗ click 3 lần xong MỚI đọc (đọc page_source).
                    # Bản v3 sai ở chỗ click 1 lần, sleep(3) rồi poll mỗi 2 giây -
                    # lúc bắt đầu đọc thì nội dung đã biến mất (log 16:41:11 click,
                    # 16:41:14 mới đọc, 16:41:34 báo không tìm được).
                    # Cách đúng: mỗi vòng = tìm lại mail -> click -> đọc ngay
                    # lập tức mỗi 0.5 giây trong ~3 giây. Chưa có thì click lại.
                    ms_code = None
                    # (v5) Thử bắt code bằng JS trong trình duyệt trước:
                    # JS click + poll 100ms ngay trong trang nên bắt kịp
                    # trước khi pane mail biến mất, Python/Selenium thì không.
                    try:
                        log("  Bắt code bằng JS ngay trong trình duyệt (poll 100ms)...")
                        js_code = get_code_from_fviainboxes_js(driver)
                        if js_code:
                            ms_code = js_code
                            log(f"  ✅ JS bắt được code: {ms_code}")
                    except Exception as e:
                        log(f"  JS bắt code lỗi, chuyển sang cách click+đọc Python: {e}")

                    try:
                        if not ms_code:
                            log("  Click mail mới nhất + đọc code ngay sau mỗi lần click...")
                        for attempt in range(0 if ms_code else 6):  # JS có code rồi thì bỏ qua vòng này
                            # Tìm LẠI element mỗi vòng (element cũ sẽ stale
                            # sau khi pane biến mất / trang render lại)
                            try:
                                first_email = WebDriverWait(driver, 10).until(
                                    lambda d: d.find_element(By.XPATH, "(//li)[1]")
                                )
                                log(f"  Click mail lần {attempt + 1}/6...")
                                try:
                                    first_email.click()
                                except Exception:
                                    driver.execute_script("arguments[0].click();", first_email)
                            except Exception as e:
                                log(f"  Lỗi click mail lần {attempt + 1}: {e}")
                                time.sleep(1)
                                continue

                            # Đọc NGAY, không sleep(3) trước. Chỉ lấy code từ
                            # dòng "Security code: XXXXXX" trong text nhìn thấy
                            # của mail đang mở - không đọc page_source (chứa
                            # cả code mail cũ 8m ago đã hết hạn).
                            for check in range(6):  # 6 x 0.5s = ~3 giây / lần click
                                time.sleep(0.5)
                                # Quét cả trang chính LẪN các iframe (mail nằm trong iframe)
                                ms_code = extract_code_from_page_and_frames(driver) or None
                                if ms_code:
                                    break
                            if ms_code:
                                break
                            log(f"  Chưa thấy code (mail đã ẩn?), click lại...")

                        if ms_code:
                            log(f"  ✅ Lấy code đúng từ mail đang mở: {ms_code}")
                        else:
                            log(f"  ❌ Không tìm được dòng code sau 6 lần click")
                            dump_fvia_diagnostic(driver)
                            return ""
                    except Exception as e:
                        log(f"  Lỗi lấy code: {e}")
                        return ""

                    # ===== FIX 2: Đóng tab fviainboxes -> TỰ switch về tab Hotmail =====
                    # Code cũ close() xong đọc driver.current_url ngay -> văng
                    # NoSuchWindowException -> except return "" (mất luôn code).
                    try:
                        log(f"  Đóng tab fviainboxes, quay về tab Hotmail...")
                        if fvia_handle in driver.window_handles:
                            driver.switch_to.window(fvia_handle)
                            driver.close()
                        driver.switch_to.window(outlook_handle)  # BẮT BUỘC
                        fvia_handle = None
                        time.sleep(1)
                        log(f"  ✓ Đã về tab Hotmail: {driver.current_url}")
                    except Exception as e:
                        log(f"  Lỗi đóng tab fviainboxes: {e}")
                        return ""

                    # Nhập code vào Hotmail
                    try:
                        code_input = WebDriverWait(driver, 10).until(
                            lambda d: d.find_element(By.XPATH, "//div[@data-testid='codeEntry']//input | //input[@id='iOttText']")
                        )
                        code_input.clear()
                        type_text_with_delay(driver, (By.XPATH, "//div[@data-testid='codeEntry']//input | //input[@id='iOttText']"), ms_code)
                        time.sleep(1)

                        try:
                            submit_btn = driver.find_element(By.XPATH, "//button[@type='submit' or @id='idSIButton9']")
                            submit_btn.click()
                        except Exception:
                            code_input.send_keys(Keys.RETURN)

                        log(f"  ✓ Đã nhập code: {ms_code}")
                        time.sleep(3)
                    except Exception as e:
                        log(f"  Lỗi nhập code: {e}")
                        return ""

                    # ===== Sau khi nhập code Microsoft, chờ redirect tới Outlook =====
                    log("  Chờ Outlook inbox load...")
                    time.sleep(5)

                    try:
                        driver.get("https://outlook.live.com/mail/")
                        time.sleep(3)

                        WebDriverWait(driver, 20).until(
                            lambda d: d.find_element(By.XPATH, "//div[@id='MailList' or @role='main']")
                        )
                        log("  ✓ Outlook inbox đã load")
                    except Exception as e:
                        log(f"  Lỗi load Outlook: {e}")
                        return ""

                    # Poll mailbox tìm TikTok code (v8: helper chung - subject/iframe/reading pane)
                    tiktok_code = get_tiktok_code_from_outlook(driver)
                    if tiktok_code:
                        return tiktok_code
                    return ""

            except Exception as exc:
                log(f"  ⚠️  Lỗi mail khôi phục: {exc}")

        # Có thể yêu cầu MFA — click "Ask later" hoặc "Skip for now"
        try:
            skip_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Skip') or contains(text(), 'Ask later')]")
            skip_btn.click()
            time.sleep(2)
        except Exception:
            pass

        # Đi tới Outlook mail
        driver.get("https://outlook.live.com/mail/")
        time.sleep(3)

        try:
            WebDriverWait(driver, 20).until(
                lambda d: d.find_element(By.XPATH, "//div[@id='MailList' or @role='main']")
            )
        except Exception:
            log("  Timeout chờ mailbox")
            return ""

        # Poll mailbox tìm TikTok code (v8: helper chung)
        return get_tiktok_code_from_outlook(driver)

    except Exception as exc:
        log(f"❌ Lỗi khôi phục Outlook: {exc}")
        return ""
    finally:
        # FIX 2: Chỉ đóng tab do hàm này mở (fvia + Outlook),
        # rồi quay về ĐÚNG tab TikTok đã lưu handle - tuyệt đối không dùng [0]
        for handle in (fvia_handle, outlook_handle):
            try:
                if handle and handle in driver.window_handles:
                    driver.switch_to.window(handle)
                    driver.close()
            except Exception:
                pass
        try:
            if tiktok_handle in driver.window_handles:
                driver.switch_to.window(tiktok_handle)
        except Exception:
            pass


def process_tiktok(driver, username, password, email, refresh_token, client_id, outlook_pass="", mail_kp=""):
    """Quy trình đăng nhập TikTok. Auto lấy code từ API Outlook."""

    focus_browser(driver)
    open_new_tab(driver, SETTING_URL)
    time.sleep(1.5)
    navigate_page(driver, TAT_UPLOAD_URL)
    time.sleep(2)

    if element_exists(driver, SUCCESS_LOCATOR):
        log(f"[{username}] Đã đăng nhập, không cần xác thực.")
        return "ĐÃ ĐĂNG NHẬP"

    log(f"[{username}] Chưa đăng nhập, khởi động quy trình xác thực.")

    if not element_exists(driver, LOGIN_BUTTON_LOCATOR):
        log("Không tìm nút login, điều hướng trực tiếp tới login page.")
        navigate_page(driver, LOGIN_URL)
    else:
        element = driver.find_element(*LOGIN_BUTTON_LOCATOR)
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        element.click()
        time.sleep(1.5)

    try:
        email_option = driver.find_element(*EMAIL_OPTION_LOCATOR)
        email_option.click()
        time.sleep(1)
    except Exception as exc:
        log(f"Email option không tìm được, refresh trang...")
        for refresh_try in range(2):
            time.sleep(1)
            driver.refresh()
            time.sleep(2)
            try:
                email_option = driver.find_element(*EMAIL_OPTION_LOCATOR)
                email_option.click()
                log(f"✓ Refresh lần {refresh_try + 1} thành công")
                time.sleep(1)
                break
            except Exception:
                if refresh_try == 1:
                    log(f"Lỗi click email option sau refresh: {exc}")
                    raise

    try:
        WebDriverWait(driver, 20).until(lambda d: d.find_element(*USERNAME_INPUT_LOCATOR).is_displayed())
        type_text_with_delay(driver, USERNAME_INPUT_LOCATOR, username)
        time.sleep(0.5)
    except Exception as exc:
        log(f"Lỗi nhập username: {exc}")
        return f"LỖI: Không nhập được username - {exc}"

    try:
        WebDriverWait(driver, 20).until(lambda d: d.find_element(*PASSWORD_INPUT_LOCATOR).is_displayed())
        type_text_with_delay(driver, PASSWORD_INPUT_LOCATOR, password)
        time.sleep(0.5)
    except Exception as exc:
        log(f"Lỗi nhập password: {exc}")
        return f"LỖI: Không nhập được password - {exc}"

    try:
        submit_btn = driver.find_element(*SUBMIT_BUTTON_LOCATOR)
        submit_btn.click()
        log("Đã click nút submit, chờ kết quả...")

        for retry in range(5):
            time.sleep(2)
            current_url = driver.current_url

            if "upload" in current_url or "tiktokstudio" in current_url:
                log(f"✓ URL redirect tới upload: {current_url}")
                time.sleep(2)
                if element_exists(driver, SUCCESS_LOCATOR):
                    log(f"[{username}] ✓✓ ĐĂNG NHẬP THÀNH CÔNG (không cần code)!")
                    return "ĐÃ ĐĂNG NHẬP"

            if element_exists(driver, CODE_INPUT_LOCATOR):
                log("Code input box xuất hiện")
                break
    except Exception as exc:
        log(f"Lỗi click submit: {exc}")

    # Chờ popup xác minh xuất hiện (có thể mất 10-15 giây)
    # v3.78: trang TikTok MOI (tieu de "Xac minh danh tinh") hien THANG o
    # nhap code, khong qua popup "Xac minh do la ban" nua. Ban cu chi doi
    # popup nen o code da hien san van chay du 60s moi di lay code - nhin
    # man hinh thi thay tool "khong get code", ma code TikTok thi gia di.
    # Thay o nhap code la thoat ngay, xuong lay code lien.
    log("⏳ Chờ popup xác minh xuất hiện (tối đa 60 giây)...")
    verify_found = False
    for attempt in range(30):
        try:
            if element_exists(driver, VERIFY_POPUP_LOCATOR):
                log(f"✓ Phát hiện popup xác minh (lần {attempt + 1})")
                verify_found = True
                break
            if element_exists(driver, CODE_INPUT_LOCATOR):
                log("✓ Ô nhập code đã hiện sẵn trên trang - bỏ qua chờ popup, đi lấy code ngay.")
                break
        except Exception:
            pass
        time.sleep(2)

    if verify_found:
        log("Tìm và click email option trong popup xác minh...")
        time.sleep(1)
        try:
            popup_div = driver.execute_script("""
                let popup = document.querySelector('[class*="modal"]') ||
                           document.querySelector('[role="dialog"]') ||
                           document.evaluate("//div[contains(text(), 'Xác minh') or contains(text(), 'Verify')]/..", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                return popup ? popup.outerHTML : 'POPUP NOT FOUND';
            """)
            log(f"🔍 POPUP HTML:\n{popup_div[:1000]}")

            all_buttons = driver.find_elements(By.XPATH, "//button")
            log(f"🔍 Tổng buttons: {len(all_buttons)}")
            for idx, btn in enumerate(all_buttons):
                text = btn.text[:50] if btn.text else "(no text)"
                onclick = btn.get_attribute("onclick") or ""
                aria_label = btn.get_attribute("aria-label") or ""
                log(f"  [{idx}] text='{text}' aria-label='{aria_label}' onclick='{onclick[:30]}'")

            email_text_elements = driver.find_elements(By.XPATH, "//*[contains(text(), '@') and (contains(text(), 'hotmail') or contains(text(), 'gmail') or contains(text(), 'outlook'))]")
            if email_text_elements:
                log(f"🔍 Tìm thấy {len(email_text_elements)} email elements")
                email_elem = email_text_elements[0]
                log(f"  Email text: {email_elem.text}")
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", email_elem)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", email_elem)
                log("✓ Đã click email address.")
            else:
                all_elements = driver.find_elements(By.XPATH, "//*[contains(text(), '@')]")
                log(f"🔍 Tìm thấy {len(all_elements)} elements chứa '@'")
                if all_elements:
                    for elem in all_elements:
                        text = elem.text
                        if text and '@' in text and len(text) < 50:
                            log(f"  → Clicking: {text}")
                            driver.execute_script("arguments[0].click();", elem)
                            log("✓ Đã click.")
                            break
        except Exception as exc:
            log(f"Lỗi click email option: {exc}")
            log(traceback.format_exc())
        time.sleep(2)
    else:
        log("⚠ Không phát hiện popup xác minh, tiếp tục...")

    if element_exists(driver, SUCCESS_LOCATOR):
        log(f"[{username}] ✓ Đăng nhập thành công (không cần code).")
        return "ĐÃ ĐĂNG NHẬP"

    try:
        WebDriverWait(driver, 60).until(lambda d: d.find_element(*CODE_INPUT_LOCATOR).is_displayed())
        log("Code input box xuất hiện.")
    except Exception as exc:
        log(f"Timeout chờ code box: {exc}")
        return "LỖI: Không thấy code input sau khi nhập password"

    log(f"🔍 Lấy code từ API: {email}")
    tiktok_code = get_code_from_outlook(email, refresh_token, client_id)

    if not tiktok_code:
        log("❌ API fail → Khôi phục bằng Outlook login")
        # outlook_pass (cột E) + mail_kp (cột H) đã được đọc sẵn ở luồng chính
        # và truyền vào - luồng phụ KHÔNG đọc/ghi Excel (openpyxl không thread-safe)
        tiktok_code = recover_outlook_code(driver, email, outlook_pass, mail_kp)

    if not tiktok_code:
        log("❌ Không lấy được code (API + Outlook)")
        return "LỖI: Không lấy được code (API + Outlook fail)"

    try:
        code_input = driver.find_element(*CODE_INPUT_LOCATOR)
        code_input.clear()
        type_text_with_delay(driver, CODE_INPUT_LOCATOR, tiktok_code, delay=150)
        log(f"✅ Đã nhập code: {tiktok_code}")
        time.sleep(1)

        confirm_btn = driver.find_element(*CODE_CONFIRM_BUTTON_LOCATOR)
        confirm_btn.click()
        log("Đã click nút confirm code, chờ redirect...")

        for retry in range(15):  # Tối đa 30 giây (15 × 2s)
            time.sleep(2)

            try:
                current_url = driver.current_url
                if "upload" in current_url or "tiktokstudio" in current_url:
                    log(f"✓ URL redirect: {current_url}")
                    time.sleep(2)

                    if element_exists(driver, SUCCESS_LOCATOR):
                        log(f"[{username}] ✓✓ ĐĂNG NHẬP THÀNH CÔNG!")
                        return "ĐÃ ĐĂNG NHẬP"
            except Exception:
                pass

            if retry % 5 == 4:
                log(f"  Chờ redirect... ({retry + 1}/15)")

        log(f"[{username}] ✗ Timeout: Không redirect được")
        return "CODE SAI - CHỜ RETRY"
    except Exception as exc:
        log(f"Lỗi nhập/confirm code: {exc}")
        return f"LỖI: Nhập code thất bại - {exc}"


# ============================================================
# ==== API CHO GUI ====
# ============================================================

# Ban chuan TAT chi goi API get_code_oauth2 DUNG 1 LAN roi chuyen khoi
# phuc mail ngay. Trong GUI chay nhanh + nhieu luong, mail code TikTok
# thuong ve tre 10-60s nen 1 lan goi do rat de "chua thay mail" du token
# con song. Ham poll duoi day KHONG sua ham chuan: no goi lai chinh ham
# chuan nhieu vong (moi vong 1 request nhu ban goc) cho den khi co code
# hoac het 5 vong (~40s cho + thoi gian request).
_SINGLE_GET_CODE = get_code_from_outlook

# ==== v3.81: THEO FILE CHUAN + DOI 15s TRUOC KHI NHAN CODE ====
# Duong lay code theo dung file chuan tat_login_engine.py anh Tu gui
# (poll 5 vong, code dau tien API tra la dung luon, tat_login nhu ban
# chuan). Them 1 sua theo y anh: _polling_get_code DOI 15s roi moi goi
# API lan dau - goi som qua thi mail moi chua ve, API tra code cu,
# nhap vao loi phai chay lai lan 2; doi 15s thi code lay duoc la code
# MOI NHAT. Ngoai cho doi 15s nay va doan thoat som vong cho popup
# trong process_tiktok (o code hien san thi khoi cho 60s vo ich), con
# lai giong het file chuan (kiem AST: process_tiktok chi khac 2 cho
# do + ten TAT_UPLOAD_URL bat buoc khi gop file).


def _polling_get_code(email, refresh_token, client_id, max_retries=1, wait_time=3):
    attempts = 5
    # v3.81 (y anh Tu): DOI 15s roi moi nhan code. Goi API ngay khi o
    # nhap code vua hien thi mail moi chua kip ve -> API tra CODE CU
    # cua lan truoc -> nhap vao la loi, phai chay lai lan 2 moi duoc.
    # Doi 15s cho mail moi ve han thi code API tra ve la CODE MOI NHAT
    # trong mail - lay luon nhu ban chuan (poll 5 vong, co code la
    # dung, rong thi cho 8s goi lai).
    log("  ⏳ Chờ 15s cho mail code mới về hẳn rồi mới lấy code mới nhất...")
    time.sleep(15)
    for i in range(attempts):
        code = _SINGLE_GET_CODE(email, refresh_token, client_id)
        if code:
            return code
        if i < attempts - 1:
            log(f"  OAuth2 chưa có code (vòng {i + 1}/{attempts}) - "
                f"chờ 8s rồi gọi lại (token vẫn đang được dùng, chưa bỏ cuộc)...")
            time.sleep(8)
    return ""



def tat_login(driver, acc):
    """Dang nhap TikTok cho 1 account bang driver GPM da gan san.
    Tra (ok, result): ok=True khi result la 'ĐÃ ĐĂNG NHẬP'."""
    username = str(acc.get("id") or "").strip().lstrip("@")
    global get_code_from_outlook
    _orig_get_code = get_code_from_outlook
    get_code_from_outlook = _polling_get_code
    try:
        result = process_tiktok(
        driver,
        username,
        str(acc.get("password") or ""),
        str(acc.get("email") or ""),
        str(acc.get("refresh_token") or ""),
        str(acc.get("client_id") or ""),
        outlook_pass=str(acc.get("passmail") or ""),
        mail_kp=str(acc.get("mailbackup") or ""),
        )
    finally:
        get_code_from_outlook = _orig_get_code
    return str(result).startswith("ĐÃ ĐĂNG NHẬP"), str(result)

# ============================================================
# ==== CONFIG (tu common.py cu) ====
# ============================================================
if getattr(sys, "frozen", False) or "__compiled__" in globals():
    # Ban dong goi EXE (PyInstaller sys.frozen / Nuitka __compiled__):
    # __file__ tro vao thu muc tam giai giai nen - phai lay thu muc chua
    # file EXE lam goc, de accounts.txt / tool_settings.json /
    # proxies.txt... (de canh EXE) duoc doc/ghi dung khi mang sang PC khac.
    APP_DIR = Path(sys.executable).resolve().parent
    # ffmpeg.exe dat canh EXE (neu co) cung phai duoc yt-dlp nhin thay
    # khi ghep hinh + tieng cho video tai ve.
    os.environ["PATH"] = (str(APP_DIR) + os.pathsep
                          + os.environ.get("PATH", ""))
else:
    APP_DIR = Path(__file__).resolve().parent   # thu muc chua file nay
ROOT_DIR = APP_DIR.parent                   # thu muc cha (cau truc app cu)
# Ban EXE khong console (--windows-console-mode=disable cua Nuitka):
# stdout/stderr co the la None - gan tam vao devnull de print() khong
# sap truoc khi GUI kip doi stdout sang LogStream.
if sys.stdout is None:
    try:
        sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="ignore")
    except Exception:  # noqa
        pass
if sys.stderr is None:
    try:
        sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="ignore")
    except Exception:  # noqa
        pass
GPM_API_URL = "http://localhost:9495/api/v1"
TOOL_VERSION = "v4.03"
# Link Raw GitHub chua file tool moi nhat cho nut "Update" tu
# tai ve (repo cong khai). De trong = tool se hoi link 1 lan
# roi luu vao settings (key "update_url") - moi PC chi can
# dan link 1 lan duy nhat.
TAT_UPDATE_URL = ""


def _ver_tuple(v):
    """'v4.02' -> (4, 2) de so sanh phien ban moi / cu."""
    return tuple(int(x) for x in re.findall(r"\d+", v or "")) or (0,)


def _find_accounts_file():
    """Tim accounts.txt: uu tien ngay canh file nay (dat o D:\\tooltiktok),
    khong thay thi o thu muc cha (dat o D:\\tooltiktok\\app nhu cu).
    Ca 2 cho deu khong co thi mac dinh canh file nay."""
    for cand in (APP_DIR / "accounts.txt", ROOT_DIR / "accounts.txt"):
        if cand.exists():
            return cand
    return APP_DIR / "accounts.txt"


ACC_FILE = _find_accounts_file()
VIDEO_EXTS = ('.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv')

# ============================================================
# ==== ACCOUNTS (tu accounts.py) ====
# Format: idTiktok|password|email|passmail|refreshToken|clientId|cookie|mailbackup|proxy|group
# ============================================================
FIELDS = ["id", "password", "email", "passmail",
          "refresh_token", "client_id", "cookie", "mailbackup", "proxy", "group", "folder"]


# Cac cot nguoi dung chon duoc khi Add Account: (key chuan -> nhan hien thi)
ADD_FIELD_LABELS = [("id", "ID TikTok"), ("password", "Password"),
                    ("email", "Email"), ("passmail", "Pass Mail"),
                    ("refresh_token", "Refresh Token"),
                    ("client_id", "Client ID"), ("cookie", "Cookie"),
                    ("mailbackup", "Mail Backup"), ("", "(bỏ qua)")]


def _parse_account_line(line, fmt_keys=None):
    """Parse 1 dong account theo THU TU COT tuy chon: fmt_keys la list
    key chuan theo dung thu tu cac cot trong dong dan ("" = bo qua cot).
    Khong truyen fmt_keys thi theo format chuan 8 truong nhu parse_line.
    Tra dict day du 8 key chuan + name."""
    parts = (line or "").rstrip("\n").split("|")
    keys = list(fmt_keys) if fmt_keys else list(ACCOUNT_FIELDS_8)
    acc = {f: "" for f in ACCOUNT_FIELDS_8}
    for i, k in enumerate(keys):
        if k and i < len(parts):
            acc[k] = parts[i].strip()
    acc["name"] = "".join(c for c in acc["id"]
                          if c.isalnum() or c in "._-") or "acc"
    return acc


def parse_line(line: str) -> dict:
    parts = line.rstrip("\n").split("|")
    acc = {f: (parts[i].strip() if i < len(parts) else "") for i, f in enumerate(FIELDS)}
    # Ten profile GPM: lay idTiktok, bo ky tu la - PHAI trung ten GPM profile!
    acc["name"] = "".join(c for c in acc["id"] if c.isalnum() or c in "._-") or "acc"
    return acc


def load_accounts(path) -> list:
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"[LỖI] Không thấy file account: {p}")
    out = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        out.append(parse_line(s))
    return out


# ============================================================
# ==== CAU HINH GUI (duong dan profile GPM, tu xoa cache) ====
# ============================================================
SETTINGS_FILE = APP_DIR / "tool_settings.json"
_SETTINGS_LOCK = threading.RLock()


def _load_settings():
    """Đọc tool_settings.json. File chính mà lỗi (vd bị ghi dở khi
    tool bị tắt ngang) thì tự đọc bản sao lưu .bak - tránh mất
    sạch dữ liệu (group / note / gán kênh...) vì 1 lần ghi hỏng."""
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa
        pass
    try:
        bak = SETTINGS_FILE.with_name(SETTINGS_FILE.name + ".bak")
        return json.loads(bak.read_text(encoding="utf-8"))
    except Exception:  # noqa
        return {}


def _save_settings(data):
    """Ghi settings AN TOÀN: ghi ra file tạm rồi thay thế (atomic)
    nên tool bị tắt/kill giữa chừng cũng không để lại file lỗi;
    bản cũ còn tốt được giữ lại thành .bak trước khi thay."""
    try:
        text = json.dumps(data, ensure_ascii=False, indent=1)
        tmp = SETTINGS_FILE.with_name(SETTINGS_FILE.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        try:
            cur = SETTINGS_FILE.read_text(encoding="utf-8")
            json.loads(cur)
            SETTINGS_FILE.with_name(
                SETTINGS_FILE.name + ".bak").write_text(
                    cur, encoding="utf-8")
        except Exception:  # noqa
            pass
        os.replace(tmp, SETTINGS_FILE)
    except Exception:  # noqa
        pass


def _update_settings(patch):
    """Gop them/doi 1 so key trong tool_settings.json, giu nguyen key khac.
    Có KHOÁ chống ghi chồng: nhiều luồng cùng lưu 1 lúc cũng
    không làm hỏng file hay mất key của nhau."""
    with _SETTINGS_LOCK:
        data = _load_settings()
        data.update(patch)
        _save_settings(data)


# 8 truong chuan cua 1 account (thu tu co dinh trong accounts.txt)
ACCOUNT_FIELDS_8 = ["id", "password", "email", "passmail",
                    "refresh_token", "client_id", "cookie", "mailbackup"]


def format_account_line(acc):
    """Dung 1 dong account chuan 8 truong: idTiktok|password|email|passmail|refreshToken|clientId|cookie|mailBackup."""
    return "|".join(str(acc.get(f, "")) for f in ACCOUNT_FIELDS_8)


def clean_tiktok_cache(root_dir):
    """Xoa moi thu muc 'https_www.tiktok.com_0.indexeddb.blob' nam sau trong
    thu muc profile GPM (cache IndexedDB cua TikTok, rat nang) - tuong duong
    lenh PowerShell user dua. Tra (so thu muc da xoa, so byte giai phong,
    so thu muc bo qua vi loi/dang bi khoa)."""
    root = Path(root_dir)
    if not root.exists():
        return 0, 0, 0
    targets = []
    for dirpath, dirnames, _files in os.walk(root):
        for d in dirnames:
            if d == "https_www.tiktok.com_0.indexeddb.blob":
                targets.append(Path(dirpath) / d)
    deleted = freed = skipped = 0
    for t in targets:
        size = 0
        for dp, _dn, fns in os.walk(t):
            for fn in fns:
                try:
                    size += os.path.getsize(os.path.join(dp, fn))
                except OSError:
                    pass
        try:
            shutil.rmtree(t)
            deleted += 1
            freed += size
        except Exception:  # noqa
            skipped += 1
    return deleted, freed, skipped


# ============================================================
# ==== QUET INFO ACCOUNT BANG COOKIE (chay an, da luong) ====
# ============================================================
STATS_FILE = APP_DIR / "stats_cache.json"
SCAN_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36")
_stats_lock = threading.Lock()


def _load_stats_cache():
    try:
        return json.loads(STATS_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa
        return {}


def _save_stats_cache(acc_id, stats):
    with _stats_lock:
        data = _load_stats_cache()
        data[acc_id] = {**data.get(acc_id, {}), **stats}
        try:
            STATS_FILE.write_text(json.dumps(data, ensure_ascii=False),
                                  encoding="utf-8")
        except Exception:  # noqa
            pass


def _proxy_url(line):
    """1 dong proxy -> URL. Ho tro: host:port | host:port:user:pass |
    user:pass@host:port | scheme://host:port[:user:pass]."""
    t = (line or "").strip()
    if not t or t.startswith("#"):
        return None
    if "://" not in t:
        if "@" in t:
            t = "http://" + t
        else:
            parts = t.split(":")
            if len(parts) == 2:
                t = f"http://{parts[0]}:{parts[1]}"
            elif len(parts) == 4:
                t = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
            else:
                return None
    return t


def _proxies_dict(url):
    return {"http": url, "https": url} if url else None


class ProxyPool:
    """Xoay vong proxy giua cac account va cac lan thu, an toan da luong."""
    def __init__(self, lines):
        self.urls = [u for u in (_proxy_url(l) for l in lines) if u]
        self._i = 0
        self._lock = threading.Lock()

    def __len__(self):
        return len(self.urls)

    def next(self):
        if not self.urls:
            return None
        with self._lock:
            u = self.urls[self._i % len(self.urls)]
            self._i += 1
            return u


def _cookie_header_from_line(line):
    """1 dong trong file cookie trung gian -> Cookie header.
    Dong day du 'k=v; k2=v2' thi giu nguyen; dong chi co gia tri sessionid
    thi tu boc thanh 'sessionid=<gia tri>'."""
    t = (line or "").strip()
    if not t or t.startswith("#"):
        return None
    if "=" not in t:
        return f"sessionid={t}"
    return t


class CookiePool:
    """Xoay vong cookie TRUNG GIAN (cua cac acc khac) de di quet info:
    acc trong bang la doi tuong do, cookie trung gian chi la phien dang
    nhap gui request - xoay nhieu cookie de loang tai, tranh bi gioi han."""
    def __init__(self, lines):
        self.headers = [h for h in (_cookie_header_from_line(l) for l in lines) if h]
        self._i = 0
        self._lock = threading.Lock()

    def __len__(self):
        return len(self.headers)

    def next(self):
        if not self.headers:
            return None
        with self._lock:
            h = self.headers[self._i % len(self.headers)]
            self._i += 1
            return h


def _extract_user_info(html):
    """Lay userInfo (user + stats) tu HTML trang profile TikTok:
    uu tien JSON __UNIVERSAL_DATA_FOR_REHYDRATION__, khong co thi regex."""
    m = re.search(r'id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
                  html, re.S)
    if m:
        try:
            data = json.loads(m.group(1))
            scope = data.get("__DEFAULT_SCOPE__", {})
            detail = scope.get("webapp.user-detail") or scope.get("webapp.userDetail") or {}
            ui = detail.get("userInfo") or {}
            if ui.get("stats"):
                return ui
        except Exception:  # noqa
            pass

    def num(key):
        mm = re.search(r'"%s":(\d+)' % key, html)
        return int(mm.group(1)) if mm else None

    sec = re.search(r'"secUid":"(.*?)"', html)
    reg = re.search(r'"region":"([A-Za-z]{2})"', html)
    stats = {"followerCount": num("followerCount"), "heartCount": num("heartCount"),
             "videoCount": num("videoCount"), "followingCount": num("followingCount")}
    if stats["followerCount"] is not None:
        return {"user": {"secUid": sec.group(1) if sec else "",
                         "region": reg.group(1) if reg else ""},
                "stats": stats}
    return None


def _fetch_video_items(sec_uid, cookie_header, proxy_url, referer,
                       want_pages=6, page_size=35, timeout=15, handle=""):
    """Lay cac video gan nhat (createTime + playCount) qua API item_list,
    lat trang bang cursor, toi da want_pages trang.
    Tra (items, diag): diag mo ta phan hoi cua API (HTTP/statusCode) de
    biet vi sao khong lay duoc view thay vi im lang tra rong."""
    items = []
    diag = "chưa gọi được API item_list"
    _mst = _cookie_value(cookie_header, "msToken")
    cursor = 0
    for _ in range(want_pages):
        params = {"aid": "1988", "app_language": "vi-VN", "app_name": "tiktok_web",
                  "browser_language": "vi-VN", "browser_name": "Mozilla",
                  "browser_online": "true", "browser_platform": "Win32",
                  "browser_version": "5.0 (Windows)", "channel": "tiktok_web",
                  "cookie_enabled": "true", "count": str(page_size),
                  "cursor": str(cursor), "device_platform": "web_pc",
                  "from_page": "user", "is_fullscreen": "false",
                  "is_page_visible": "true", "language": "vi-VN", "os": "windows",
                  "region": "VN", "screen_height": "1080", "screen_width": "1920",
                  "secUid": sec_uid, "tz_name": "Asia/Bangkok",
                  "webcast_language": "vi-VN"}
        if _mst:
            # msToken cua chinh cookie (nhu cach da giup API Check Tien
            # tra data) - thieu no API item_list hay tra danh sach rong.
            params["msToken"] = _mst
        try:
            r = requests.get("https://www.tiktok.com/api/post/item_list/",
                             params=params,
                             headers={"User-Agent": SCAN_UA, "Referer": referer,
                                      "Cookie": cookie_header,
                                      "Accept": "application/json"},
                             proxies=_proxies_dict(proxy_url), timeout=timeout)
        except Exception as e:  # noqa
            diag = f"lỗi gọi API: {_short(e)}"
            if _ == 0:
                _save_scan_raw(handle, {
                    "url": "https://www.tiktok.com/api/post/item_list/",
                    "error": f"{type(e).__name__}: {e}"[:500]})
            break
        try:
            js = r.json()
        except Exception:  # noqa
            js = None
        if js is None:
            diag = (f"item_list trả về không phải JSON "
                    f"(HTTP {r.status_code})")
            if _ == 0:
                _save_scan_raw(handle, {
                    "url": "https://www.tiktok.com/api/post/item_list/",
                    "http": r.status_code,
                    "body_head": (r.text or "")[:4000]})
            break
        batch = js.get("itemList") or []
        diag = (f"HTTP {r.status_code}, "
                f"statusCode={js.get('statusCode')}, "
                f"msg={str(js.get('status_msg') or js.get('statusMsg') or '')[:60]}, "
                f"items_trang={len(batch)}")
        if _ == 0:
            _save_scan_raw(handle, {
                "url": "https://www.tiktok.com/api/post/item_list/",
                "http": r.status_code, "json": js})
        if not batch:
            break
        for it in batch:
            st = it.get("stats") or {}
            items.append({"createTime": int(it.get("createTime") or 0),
                          "playCount": int(st.get("playCount") or 0)})
        if not js.get("hasMore"):
            break
        cursor = js.get("cursor") or (items[-1]["createTime"] * 1000 if items else 0)
    return items, diag


INCENTIVES_URLS = {
    "US": "https://api16-normal-useast5.tiktokv.us/tiktok/v1/creator/incentives/profile",
    "EU": "https://api16-normal-useastred.tiktokv.eu/tiktok/v1/creator/incentives/profile",
}
PAYOUT_SUMMARY_URL = ("https://webcast.us.tiktok.com/webcast/api/money/"
                      "creator_earnings/v1/payout_summary?locale=en&webcast_language=en")
MONTHLY_EARNING_URL = ("https://webcast.us.tiktok.com/webcast/api/money/"
                       "payout_onboarding/v2/onboarding_detail?wallet_type=MONTHLY_EARNING")
MONEY_RAW_DIR = APP_DIR / "money_raw"
SCAN_RAW_DIR = APP_DIR / "scan_raw"


def _save_scan_raw(handle, data):
    """Luu response tho cua API item_list vao scan_raw/<acc>.json de
    chan doan khi quet khong ra view (nhu money_raw cua Check Tien)."""
    try:
        SCAN_RAW_DIR.mkdir(parents=True, exist_ok=True)
        txt = json.dumps(data, ensure_ascii=False, indent=1)
        (SCAN_RAW_DIR / f"{handle or 'unknown'}.json").write_text(
            txt[:300000], encoding="utf-8")
    except Exception:  # noqa
        pass
_EU_CC = {"de", "fr", "it", "es", "nl", "pl", "se", "no", "dk", "fi", "ie",
          "pt", "at", "be", "cz", "sk", "hu", "ro", "bg", "hr", "gr", "lt",
          "lv", "ee", "si", "lu", "mt", "cy"}


def _deep_find(obj, keys, depth=0):
    """Tim de quy gia tri vo huong dau tien co ten khoa thuoc keys."""
    if depth > 6 or obj is None:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys and isinstance(v, (str, int, float, bool)) \
                    and v not in ("", None):
                return v
        for v in obj.values():
            r = _deep_find(v, keys, depth + 1)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _deep_find(v, keys, depth + 1)
            if r is not None:
                return r
    return None


def _fmt_money(v, currency=""):
    if isinstance(v, bool):
        return ""
    if isinstance(v, (int, float)):
        s = f"{v:,.0f}" if float(v) == int(v) else f"{v:,.2f}"
    else:
        s = str(v)
    return f"{s} {currency}".strip()


def _api_error(js):
    """JSON envelope loi cua TikTok (HTTP 200 nhung status_code=20003
    'session user not logged in') -> tra thong diep loi, khong thi None."""
    if not isinstance(js, dict):
        return None
    msg = js.get("status_message") or js.get("status_msg") or ""
    low = msg.lower() if isinstance(msg, str) else ""
    if "not logged in" in low or "doesn't login" in low or "not login" in low:
        return msg
    code = js.get("status_code")
    if code not in (None, 0, 200) and msg:
        return f"status_code={code}: {msg}"
    return None


def _cookie_value(cookie_header, name):
    m = re.search(rf"(?:^|;\s*){re.escape(name)}=([^;]+)",
                  cookie_header or "")
    return m.group(1) if m else ""


def _webcast_url(url, cookie_header):
    """Gan them tham so ngu canh web ma frontend TikTok luon gui kem
    khi goi webcast (aid/app_name/device_platform + msToken cua cookie)."""
    extra = "aid=1988&app_name=tiktok_web&device_platform=web_pc"
    mst = _cookie_value(cookie_header, "msToken")
    if mst:
        extra += f"&msToken={mst}"
    return url + ("&" if "?" in url else "?") + extra


PHONE_UA = ("com.ss.android.ugc.trill/350903 (Linux; U; Android 14; en_US; "
            "Pixel 8 Pro; Build/UP1A.231005.007; Cronet/TTNetVersion:2fdb62f1 "
            "2024-08-09 QuicVersion:acde0d3d 2024-05-23)")


def _webcast_url_phone(url, cookie_header):
    """URL webcast theo kieu APP dien thoai: tham so app (aid cua app,
    device_platform=android...) + msToken, di kem UA app (PHONE_UA)."""
    extra = ("aid=1233&app_name=musical_ly&device_platform=android"
             "&os_version=14&version_code=350903&version_name=35.9.3"
             "&channel=googleplay&language=en&region=US")
    mst = _cookie_value(cookie_header, "msToken")
    if mst:
        extra += f"&msToken={mst}"
    return url + ("&" if "?" in url else "?") + extra


def _region_order(cookie_header):
    """Thu tu host US/EU theo goi y trong cookie (idc / country-code)."""
    m = re.search(r"(?:tt-target-idc|store-idc)=([a-z0-9-]+)",
                  cookie_header or "")
    idc = m.group(1) if m else ""
    m2 = re.search(r"store-country-code=([a-z]{2})", cookie_header or "")
    cc = m2.group(1) if m2 else ""
    if "useastred" in idc or cc in _EU_CC:
        return ["EU", "US"]
    return ["US", "EU"]


def _parse_monthly(js):
    """Doc JSON onboarding_detail (wallet_type=MONTHLY_EARNING). Du lieu
    that (doi chieu acc US): API nay tra TRANG THAI KYC + lien ket rut
    tien, thuong khong co so tien thang. Uu tien so tien neu co; khong
    co thi tra trang thai rut tien de thay '—' vo nghia.
    Tra (chuoi hien thi, doc_duoc_khong)."""
    data = js.get("data") if isinstance(js, dict) else None
    scope = data if isinstance(data, dict) else (js or {})
    v = _deep_find(scope, ("amount", "total_amount", "monthly_earnings",
                           "earnings", "total_earnings", "totalAmount"))
    if v is not None:
        cur = _deep_find(scope, ("currency", "currency_code", "currencyCode"))
        return _fmt_money(v, cur if isinstance(cur, str) else ""), True
    if isinstance(data, dict) and data:
        if data.get("confirmed") and data.get("pi_bind_status") == 1:
            return "✅ Sẵn rút tiền", True
        if data.get("kyc_status") == 1:
            return "KYC✅ chưa LK rút", True
        if data.get("confirmed") or data.get("kyc_status"):
            return "Đang KYC", True
        return "Chưa KYC", True
    return "—", False


try:
    from curl_cffi import requests as _cffi_requests
except Exception:  # noqa
    _cffi_requests = None


def _http_get(url, headers, timeout):
    """GET bang curl_cffi (gia lap dau van tay TLS/HTTP2 cua Chrome -
    day la khac biet lon nhat giua requests tran va trinh duyet that
    khien webcast tra 'not logged in'); chua cai curl_cffi thi dung
    requests thuong."""
    if _cffi_requests is not None:
        return _cffi_requests.get(url, headers=headers, timeout=timeout,
                                  impersonate="chrome")
    return requests.get(url, headers=headers, timeout=timeout)


def check_session_alive(acc, timeout=15):
    """Kiem tra nhanh session cua 1 acc con song khong, bang cookie
    cua CHINH acc do vao API creator incentives (API nay can dang
    nhap moi tra du lieu). Tra (state, msg):
      'alive'   - API tra du lieu that (khong loi) o 1 vung nao do.
      'dead'    - moi vung deu bao chua dang nhap (het session chac).
      'unknown' - khong ket luan duoc (thieu cookie, loi mang, API
                  tra loi khac) - khong bao gio coi la chet."""
    cookie = (acc.get("cookie") or "").strip()
    if not cookie:
        return "unknown", "chưa có cookie trong accounts.txt"
    headers = {"User-Agent": SCAN_UA, "Cookie": cookie,
               "Accept": "application/json, text/plain, */*",
               "Referer": "https://www.tiktok.com/",
               "Origin": "https://www.tiktok.com",
               "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8"}
    csrf = _cookie_value(cookie, "tt_csrf_token")
    if csrf:
        headers["x-secsdk-csrf-token"] = csrf
    auth_err = None
    last_err = ""
    for region in _region_order(cookie):
        try:
            r = _http_get(INCENTIVES_URLS[region], headers=headers,
                          timeout=timeout)
        except Exception as e:  # noqa
            last_err = _short(e)
            continue
        if r.status_code in (401, 403):
            auth_err = f"HTTP {r.status_code}"
            continue
        if r.status_code != 200:
            last_err = f"HTTP {r.status_code}"
            continue
        try:
            js = r.json()
        except Exception:  # noqa
            last_err = "phản hồi không phải JSON"
            continue
        err = _api_error(js)
        if not err:
            return "alive", f"vùng {region}"
        low = err.lower()
        if ("not logged in" in low or "login" in low
                or "session" in low or "20003" in err):
            auth_err = err
        else:
            last_err = err
    if auth_err:
        return "dead", auth_err
    return "unknown", last_err or "không rõ phản hồi"


def scan_account_info(acc, proxy_pool, recent_n=5, timeout=15, cookie_pool=None):
    """Quet info 1 account (khong mo trinh duyet): UU TIEN cookie cua
    chinh acc do; acc nao khong co cookie moi dung cookie TRUNG GIAN
    (cookie_pool) xoay vong.
    Tra dict gom: follows (T.Follows), likes (T.Likes - tong tim),
    videos (T.Video), views30d (tong view video dang trong 30 ngay),
    views (tong view cua recent_n video moi nhat), msg (trang thai)."""
    handle = (acc.get("id") or "").strip().lstrip("@")
    own_cookie = (acc.get("cookie") or "").strip()
    cookie_header = own_cookie
    own_cc = (_cookie_value(own_cookie, "store-country-code") or "").upper()
    res = {"ok": False, "follows": None, "likes": None, "videos": None,
           "views30d": None, "views": None, "recent_n": recent_n, "msg": "",
           "src": "cookie của acc" if own_cookie else "cookie trung gian",
           "country": ""}
    if not handle:
        res["msg"] = "thiếu ID"
        return res
    if not own_cookie and not (cookie_pool and len(cookie_pool)):
        res["msg"] = "thiếu cookie (acc không có, file trung gian trống)"
        return res
    attempts = 3 if ((proxy_pool and len(proxy_pool))
                     or (cookie_pool and len(cookie_pool))) else 1
    last_err = ""
    for _try in range(attempts):
        proxy_url = _proxy_url(acc.get("proxy")) or (proxy_pool.next() if proxy_pool else None)
        if not own_cookie and cookie_pool and len(cookie_pool):
            cookie_header = cookie_pool.next()
        try:
            r = requests.get(f"https://www.tiktok.com/@{handle}",
                             headers={"User-Agent": SCAN_UA, "Cookie": cookie_header,
                                      "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8"},
                             proxies=_proxies_dict(proxy_url), timeout=timeout)
            if r.status_code != 200 or len(r.text) < 5000:
                last_err = f"profile HTTP {r.status_code}"
                continue
            ui = _extract_user_info(r.text)
            if not ui:
                last_err = "không đọc được dữ liệu profile (cookie hết hạn?)"
                continue
            st = ui.get("stats") or {}
            res["follows"] = st.get("followerCount")
            res["likes"] = st.get("heartCount")
            res["videos"] = st.get("videoCount")
            sec_uid = (ui.get("user") or {}).get("secUid") or ""
            view_err = ""
            if sec_uid:
                items, diag = _fetch_video_items(
                    sec_uid, cookie_header, proxy_url,
                    f"https://www.tiktok.com/@{handle}",
                    timeout=timeout, handle=handle)
                if items:
                    cutoff = int(time.time()) - 30 * 86400
                    res["views30d"] = sum(i["playCount"] for i in items
                                          if i["createTime"] >= cutoff)
                    res["views"] = sum(i["playCount"] for i in items[:recent_n])
                elif _try < attempts - 1:
                    # API tra rong (thuong do bi chan theo cookie/proxy):
                    # giu lai so profile da doc duoc roi thu lai voi
                    # cookie/proxy xoay vong tiep theo, thay vi bo cuoc
                    # ngay nhu ban truoc.
                    res["country"] = ((ui.get("user") or {}).get("region")
                                      or "").strip().upper() or own_cc
                    last_err = f"item_list rỗng ({diag})"
                    continue
                else:
                    view_err = f"item_list rỗng ({diag})"
            res["country"] = ((ui.get("user") or {}).get("region")
                              or "").strip().upper() or own_cc
            res["ok"] = res["follows"] is not None
            res["msg"] = "OK" if res["views"] is not None else \
                ("có số profile, chưa lấy được view video - " + view_err
                 if view_err else
                 "có số profile, chưa lấy được view video")
            return res
        except Exception as e:  # noqa
            last_err = _short(e)
            continue
    if res["follows"] is not None:
        # It nhat 1 lan thu da doc duoc profile (chi thieu view video):
        # acc van song, khong duoc danh dau loi/chet oan.
        res["ok"] = True
        res["msg"] = ("có số profile, chưa lấy được view video - "
                      + (last_err or "item_list rỗng"))
        if not res["country"]:
            res["country"] = own_cc
        return res
    if not res["country"]:
        res["country"] = own_cc
    res["msg"] = last_err or "lỗi không rõ"
    return res


import glob
import os
import re
import threading
import time
import random
import requests
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload"
GPM_BASE_PORT = 40444  # giong test1.py

POST_WAIT_S = 300        # giong test1.py
POST_CONFIRM_WAIT_S = 60  # giong test1.py
ACCEPT_WAIT_S = 25       # cho TikTok nhan file sau moi lan gan


_ctx = threading.local()


def _log(msg):
    tag = getattr(_ctx, "tag", "")
    prefix = f"  [UP] @{tag}" if tag else "  [UP]"
    print(f"{prefix} {msg}", flush=True)


def _short(e):
    """Rut gon loi Selenium thanh 1 dong (mac dinh str(e) chua ca stacktrace)."""
    s = str(e) or ""
    first = s.splitlines()[0][:180] if s else ""
    return f"{type(e).__name__}: {first}"


# ============================================================
# ==== GPM DRIVER PATH (chon theo phien ban trinh duyet) ====
# ============================================================

TEST1_DRIVER_PATH = r"C:\Users\Tu-x79\AppData\Roaming\GPMLoginGlobal\Browsers\ChromiumCore_v147\gpmdriver.exe"


def _all_driver_candidates():
    """Liet ke moi gpmdriver.exe trong cac thu muc nhan trinh duyet cua GPM.
    Moi nhan (ChromiumCore_v147, v154...) co gpmdriver RIENG theo phien ban."""
    env = os.environ.get("GPM_DRIVER_PATH")
    if env and os.path.exists(env):
        return [env]
    appdata = os.environ.get("APPDATA", "")
    patterns = [
        os.path.join(appdata, "GPMLoginGlobal", "Browsers", "*", "gpmdriver.exe"),
        r"C:\Users\*\AppData\Roaming\GPMLoginGlobal\Browsers\*\gpmdriver.exe",
    ]
    cands = []
    for p in patterns:
        cands += glob.glob(p)
    return sorted(set(cands))


def _browser_major(port):
    """Doc phien ban trinh duyet dang chay tu /json/version. VD '147'."""
    try:
        r = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=5)
        browser = (r.json().get("Browser") or "") if r.ok else ""
        m = re.search(r"(\d+)\.", browser)
        if m:
            return m.group(1), browser
    except Exception:  # noqa
        pass
    return None, ""


def _driver_path_for_major(major):
    """Chon gpmdriver KHOP phien ban trinh duyet (thu muc ChromiumCore_v<major>).
    Khong thay thi fallback ve driver v147 cua test1.py, roi moi den ban moi nhat."""
    cands = _all_driver_candidates()
    if major:
        for c in cands:
            folder = os.path.basename(os.path.dirname(c))
            if folder.endswith(f"v{major}") or f"v{major}" in folder:
                return c
    if os.path.exists(TEST1_DRIVER_PATH):
        return TEST1_DRIVER_PATH
    for c in cands:
        folder = os.path.basename(os.path.dirname(c))
        if "v147" in folder:
            return c
    return cands[-1] if cands else TEST1_DRIVER_PATH


# ============================================================
# ==== PORT REGISTRY + KHOA THEO PROFILE (nhu test1.py) ====
# ============================================================

_port_lock = threading.Lock()
_port_registry = {}


def _port_for(name):
    with _port_lock:
        if name not in _port_registry:
            _port_registry[name] = GPM_BASE_PORT + len(_port_registry)
        return _port_registry[name]


_locks_guard = threading.Lock()
_profile_locks = {}


def _lock_for(name):
    """Moi profile chi chay 1 job tai 1 thoi diem (2 job cung acc se xep hang,
    khong mo 2 lan cung 1 profile roi stop cheo nhau)."""
    with _locks_guard:
        if name not in _profile_locks:
            _profile_locks[name] = threading.Lock()
        return _profile_locks[name]


# ============================================================
# ==== XEP LUOI CUA SO TRINH DUYET THEO SO LUONG ====
# ============================================================

GRID_TOTAL = 1  # GUI dat = min(so luong, so job) truoc moi dot chay
HIDE_BROWSER = False  # GUI dat theo o "An trinh duyet" truoc moi dot chay

# Gian cach mo profile: moi lan mo profile GPM phai cach lan mo truoc
# it nhat "delay" giay (GUI dat truoc moi dot chay qua _set_launch_delay).
_launch_lock = threading.Lock()
_launch_state = {"delay": 0, "next": 0.0}


def _set_launch_delay(seconds):
    """Dat do gian cach mo profile (giay) + reset moc thoi gian de
    profile dau tien cua dot chay mo ngay, khong phai cho."""
    try:
        _launch_state["delay"] = max(0, int(seconds))
    except Exception:  # noqa
        _launch_state["delay"] = 0
    _launch_state["next"] = 0.0


def _wait_launch_slot():
    """Dat cho mo profile theo gian cach: giu cho duoi khoa roi ngu
    ngoai khoa, tranh cac profile mo don cung mot luc."""
    d = _launch_state["delay"]
    if d <= 0:
        return
    with _launch_lock:
        now = time.time()
        start = max(now, _launch_state["next"])
        _launch_state["next"] = start + d
    wait = start - now
    if wait > 0:
        _log(f"delay mở trình duyệt: chờ {wait:.0f}s (giãn cách {d}s/profile)")
        time.sleep(wait)


class _StopRequested(Exception):
    """Ngoại lệ nội bộ: người dùng bấm STOP - job chưa chạy thì dừng êm."""
_slot_lock = threading.Lock()
_active_slots = set()


def _grid_layout(total, sw, sh):
    """(so cot, so hang, rong o, cao o) cho total cua so tren man sw x sh,
    chia deu can doi theo ti le man hinh. VD 30 cua so tren 1920x1080
    -> luoi 8 cot x 4 hang, moi o 240x270."""
    total = max(1, int(total))
    cols = math.ceil(math.sqrt(total * sw / max(1, sh)))
    rows = math.ceil(total / cols)
    return cols, rows, sw // cols, sh // rows


def _screen_size():
    try:
        import ctypes
        return (ctypes.windll.user32.GetSystemMetrics(0),
                ctypes.windll.user32.GetSystemMetrics(1))
    except Exception:  # noqa
        return 1920, 1080


def _claim_slot():
    with _slot_lock:
        for i in range(max(1, GRID_TOTAL)):
            if i not in _active_slots:
                _active_slots.add(i)
                return i
    return None


def _release_slot(slot):
    if slot is not None:
        with _slot_lock:
            _active_slots.discard(slot)


def _hide_window(driver):
    """Ẩn hẳn cửa sổ trình duyệt: THU NHỎ (minimize) bằng CDP - cách chắc
    ăn nhất trên Windows. Cách cũ (set_window_rect ra -32000) hay bị
    Chrome kéo cửa sổ lại / không ăn khi cửa sổ đang maximize nên trình
    duyệt vẫn nhảy ra màn hình dù đã tích Ẩn trình duyệt. Minimize xong
    vẫn giữ thêm lớp đẩy ra ngoài màn hình làm dự phòng."""
    try:
        win = driver.execute_cdp_cmd("Browser.getWindowForTarget", {})
        wid = win.get("windowId")
        if wid:
            driver.execute_cdp_cmd(
                "Browser.setWindowBounds",
                {"windowId": wid, "bounds": {"windowState": "minimized"}})
            _log("đã ẩn cửa sổ trình duyệt (minimize)")
            return True
    except Exception:  # noqa
        pass
    try:
        driver.minimize_window()
        _log("đã ẩn cửa sổ trình duyệt (minimize)")
        return True
    except Exception:  # noqa
        pass
    try:
        driver.set_window_rect(x=-32000, y=-32000, width=900, height=700)
        _log("đã ẩn cửa sổ trình duyệt (đẩy ra ngoài màn hình)")
        return True
    except Exception:  # noqa
        pass
    return False


def _tile_window(driver, slot):
    """Co nho + xep cua so trinh duyet vao o luoi cua no: chay bao nhieu
    luong thi man hinh chia deu bay nhieu o, nhin thay tat ca cung luc.
    Neu bat An trinh duyet: minimize cua so thay vi xep luoi."""
    if HIDE_BROWSER:
        _hide_window(driver)
        return
    total = max(1, GRID_TOTAL)
    if total <= 1 or slot is None:
        return
    sw, sh = _screen_size()
    cols, rows, cw, ch = _grid_layout(total, sw, sh)
    x = (slot % cols) * cw
    y = (slot // cols) * ch
    try:
        driver.set_window_rect(x=x, y=y, width=cw, height=ch)
        _log(f"cửa sổ ô {slot + 1}/{total} (lưới {cols}x{rows}, ô {cw}x{ch} tại {x},{y})")
    except Exception as e:  # noqa
        _log(f"không xếp được cửa sổ vào lưới: {_short(e)}")


# ============================================================
# ==== GPM API ====
# ============================================================

def _list_all_profiles():
    """Lay het profile GPM (co phan trang nhu test1.py, ban common.py cu
    chi doc trang dau nen de sot profile)."""
    all_profiles = []
    page = 1
    while True:
        try:
            res = requests.get(f"{GPM_API_URL}/profiles",
                               params={"page": page, "per_page": 30}, timeout=10)
        except Exception as e:  # noqa
            _log(f"list profiles lỗi: {_short(e)}")
            break
        if not res.ok:
            break
        try:
            js = res.json()
        except Exception:  # noqa
            break
        data = js.get("data", {})
        rows = data.get("data", []) if isinstance(data, dict) else []
        if not rows:
            break
        all_profiles.extend(rows)
        if data.get("current_page", page) >= data.get("last_page", page):
            break
        page += 1
    return all_profiles


_profiles_cache = {"ts": 0.0, "map": {}, "force_ts": 0.0}
_profiles_cache_lock = threading.Lock()
PROFILES_CACHE_TTL = 60  # giay


def _profiles_map(force=False):
    """Map {ten profile: id} tu GPM, co CACHE 60s + khoa chong nhieu
    luong cung liet ke mot luc. Ban truoc _get_profile_id liet ke lai
    TOAN BO profile (phan trang 30/trang - 500 profile la 18 request
    HTTP) cho MOI job upload: 5 luong cung liet ke luc khoi dong nen
    bam START phai doi 10s+ moi thay trinh duyet dau tien."""
    now = time.time()
    with _profiles_cache_lock:
        if (not force and _profiles_cache["map"]
                and now - _profiles_cache["ts"] < PROFILES_CACHE_TTL):
            return _profiles_cache["map"]
        m = {}
        for prof in _list_all_profiles():
            nm = str(prof.get("name", "")).strip()
            if nm:
                m[nm] = prof.get("id")
        _profiles_cache["map"] = m
        _profiles_cache["ts"] = now
        return m


def _get_profile_id(account_name):
    m = _profiles_map()
    pid = m.get(account_name)
    if pid:
        return pid
    # Khong thay: lam moi cache 1 lan (profile vua tao?) - toi da 1
    # lan/30s de account khong co profile khong gay liet ke lien tuc.
    now = time.time()
    if now - _profiles_cache.get("force_ts", 0.0) > 30:
        _profiles_cache["force_ts"] = now
        return _profiles_map(force=True).get(account_name)
    return None



# ---- Registry trinh duyet dang mo + STOP cung (kill ngay lap tuc) ----
# Moi profile tool start (upload / xuat cookie / mo thu cong) deu dang ky
# vao _active_profiles; _stop_profile tu go dang ky. Driver Selenium dang
# gan dang ky theo ten account. request_engine_stop() kill tat ca NGAY:
# goi GPM stop tat han tien trinh Chromium + dat co _KILL_EVENT de cac
# vong cho trong engine thoat ngay thay vi cho het timeout.
_active_lock = threading.Lock()
_active_profiles = set()
_active_drivers = {}
_KILL_EVENT = threading.Event()


def _register_active_profile(profile_id):
    if profile_id:
        with _active_lock:
            _active_profiles.add(profile_id)


def _register_active_driver(name, driver):
    if name and driver is not None:
        with _active_lock:
            _active_drivers[name] = driver


def _unregister_active_driver(name):
    with _active_lock:
        _active_drivers.pop(name, None)


def _engine_killed():
    return _KILL_EVENT.is_set()


def clear_engine_stop():
    """Run moi bat dau: xoa lenh STOP cu de engine chay binh thuong."""
    _KILL_EVENT.clear()


def request_engine_stop():
    """STOP CUNG: kill NGAY moi trinh duyet tool dang mo va dat co de
    engine dung ngay. Tra so profile da kill."""
    _KILL_EVENT.set()
    with _active_lock:
        profiles = list(_active_profiles)
        drivers = list(_active_drivers.values())

    def _kill_driver(drv):
        try:
            drv.quit()
        except Exception:  # noqa
            pass

    # Kill SONG SONG tat ca cung luc (GPM stop tat tien trinh Chromium,
    # driver.quit chay nen song song) - khong cho tuan tu tung trinh
    # duyet nen STOP phan hoi gan nhu tuc thi du dang mo nhieu cua so.
    with ThreadPoolExecutor(max_workers=16) as ex:
        futs = [ex.submit(_stop_profile, pid) for pid in profiles]
        futs += [ex.submit(_kill_driver, drv) for drv in drivers]
        for f in futs:
            try:
                f.result(timeout=15)
            except Exception:  # noqa
                pass
    return len(profiles)


def _stop_profile(profile_id):
    with _active_lock:
        _active_profiles.discard(profile_id)
    try:
        requests.get(f"{GPM_API_URL}/profiles/stop/{profile_id}", timeout=10)
    except Exception:  # noqa
        pass


def _start_profile(profile_id, port):
    """Start profile kem remote_debugging_port (nhu gpm_start_profile cua
    test1.py). Tra ve cong thuc te GPM mo, hoac None neu that bai."""
    _wait_launch_slot()
    _stop_profile(profile_id)
    time.sleep(1)
    try:
        res = requests.get(f"{GPM_API_URL}/profiles/start/{profile_id}",
                           params={"remote_debugging_port": port}, timeout=30)
    except Exception as e:  # noqa
        _log(f"start profile lỗi: {_short(e)}")
        return None
    if not res.ok:
        _log(f"start profile thất bại: HTTP {res.status_code} {res.text[:200]}")
        return None
    try:
        js = res.json()
    except Exception:  # noqa
        _log("start profile: response không phải JSON")
        return None
    if not js.get("success"):
        _log(f"start profile: GPM trả success=false: {js.get('message')}")
        return None
    actual = int((js.get("data") or {}).get("remote_debugging_port") or port)
    _log(f"profile đã start, remote_debugging_port={actual}")
    return actual


def open_profile_browser(account_id):
    """Mo profile GPM cua account de nguoi dung thao tac THU CONG: chi
    start profile roi DE NGUYEN cua so - khong stop truoc (profile dang
    chay san thi giu nguyen), khong attach driver, khong upload, tool
    khong tu dong lai. Tra (ok, thong_diep)."""
    name = (account_id or "").strip()
    if not name:
        return False, "thiếu ID account"
    pid = _get_profile_id(name)
    if not pid:
        return False, f"không tìm thấy profile GPM tên '{name}'"
    _wait_launch_slot()
    port = _port_for(name)
    try:
        res = requests.get(f"{GPM_API_URL}/profiles/start/{pid}",
                           params={"remote_debugging_port": port},
                           timeout=30)
    except Exception as e:  # noqa
        return False, f"không gọi được GPM: {_short(e)}"
    try:
        js = res.json()
    except Exception:  # noqa
        js = {}
    if res.ok and js.get("success"):
        actual = int((js.get("data") or {}).get("remote_debugging_port")
                     or port)
        _register_active_profile(pid)
        return True, f"đã mở trình duyệt (port {actual})"
    msg = str(js.get("message") or res.text[:150]
              or f"HTTP {res.status_code}")
    low = msg.lower()
    if "already" in low or "running" in low or "đang" in low:
        return True, "profile đang mở sẵn rồi"
    return False, f"GPM không mở được profile: {msg}"


def _wait_devtools(port, timeout=30):
    """Cho cong DevTools tra loi /json/version roi moi gan driver."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=3)
            if r.ok:
                return True
        except Exception:  # noqa
            pass
        time.sleep(0.5)
    return False


# ============================================================
# ==== UPLOAD (port tu GPMTikTokSession cua test1.py) ====
# ============================================================

FILE_SELECTORS = ["input[type='file']", "input[accept*='video']", "input[name='file']"]
CAPTION_SELECTORS = ["div[data-e2e='caption-input']", "div[contenteditable='true']",
                     "div.public-DraftEditor-content", "div[class*='caption']",
                     "textarea[placeholder]"]
POST_SELECTOR = "button[data-e2e='post_video_button']"
SELECT_BTN_XPATHS = [
    "//button[contains(.,'Chọn video')]",
    "//button[contains(.,'Select video')]",
    "//*[contains(text(),'Chọn video để tải lên')]",
    "//*[contains(text(),'Select video to upload')]",
]
DIALOG_BUTTON_SELECTORS = [
    "button[class*='primary'][class*='button']",
    "button.ant-btn-primary",
    "div[role='dialog'] button[type='button']",
    "button[color='primary']",
    "div[role='modal'] button",
]
DIALOG_UPLOAD_KEYWORDS = [
    "tai len", "tải lên", "upload",
    "đăng ngay", "post now",
    "上传", "上傳",
    "アップロード", "アップ", "投稿",
    "업로드", "업로",
]



_BAD_TAB_PREFIXES = ("chrome-extension://", "devtools://",
                     "chrome-devtools://")


def _ensure_page_tab(driver):
    """Dam bao tab hien tai la TAB TRANG THAT, khong phai trang nen
    extension (chrome-extension://<id>/background.html).

    Khi ChromeDriver gan qua debuggerAddress luc profile vua start (mo
    nhieu luong cung luc, may dang tai nang), tab 'hien tai' co the la
    trang nen cua 1 extension GPM: trang do khong co cua so (xep luoi
    bao 'Browser window not found'), driver.get() khong dieu huong di
    dau duoc, doc cookie = 0 -> cho login 20s oan roi quit - trinh duyet
    'mo len roi tat luon' du profile da login san. Ham nay ra moi
    handle: uu tien tab tiktok.com, roi tab trang thuong; khong co tab
    trang nao thi mo tab moi. Tra True neu dang o 1 tab trang that."""
    try:
        cur = (driver.current_url or "")
    except Exception:  # noqa
        cur = ""
    if cur and not cur.startswith(_BAD_TAB_PREFIXES):
        return True
    try:
        handles = list(driver.window_handles)
    except Exception:  # noqa
        handles = []
    fallback = None
    for h in handles:
        try:
            driver.switch_to.window(h)
            u = (driver.current_url or "")
        except Exception:  # noqa
            continue
        if "tiktok.com" in u:
            _log(f"đã chọn lại tab trang thật: {u[:80]}")
            return True
        if u and not u.startswith(_BAD_TAB_PREFIXES) and fallback is None:
            fallback = h
    if fallback is not None:
        try:
            driver.switch_to.window(fallback)
            _log("đã chọn lại tab trang thật (không phải trang nền extension)")
            return True
        except Exception:  # noqa
            pass
    try:
        driver.switch_to.new_window("tab")
        _log("không có tab trang nào - đã mở tab mới")
        return True
    except Exception:  # noqa
        pass
    try:
        driver.execute_script("window.open('about:blank','_blank');")
        hs = list(driver.window_handles)
        if hs:
            driver.switch_to.window(hs[-1])
            return True
    except Exception:  # noqa
        pass
    return False


def _focus_tiktok_tab(driver):
    """Chon dung tab de lam viec khi profile mo nhieu tab:
    uu tien 1: tab TikTok Studio (upload/content) — ban truoc chi tim tab
    nao co 'tiktok.com' la dung lai, de nham sang tab trang chu TikTok
    (o do lam gi co input file nen bao 'khong co input trong DOM');
    uu tien 2: tab tiktok.com bat ky; khong co thi giu nguyen tab goc."""
    try:
        original = driver.current_window_handle
    except Exception:  # noqa
        original = None
    chosen = None
    try:
        handles = list(driver.window_handles)
        for want in ("tiktokstudio", "tiktok.com"):
            for handle in handles:
                try:
                    driver.switch_to.window(handle)
                    if want in (driver.current_url or ""):
                        chosen = handle
                        break
                except Exception:  # noqa
                    continue
            if chosen:
                break
        if chosen:
            try:
                driver.switch_to.window(chosen)
            except Exception:  # noqa
                pass
        elif original:
            try:
                driver.switch_to.window(original)
            except Exception:  # noqa
                pass
            try:
                if (driver.current_url or "").startswith(_BAD_TAB_PREFIXES):
                    _ensure_page_tab(driver)
            except Exception:  # noqa
                pass
    except Exception:  # noqa
        pass
    try:
        driver.execute_script("window.focus();")
    except Exception:  # noqa
        pass


def _page_diag(driver):
    """Tom tat trang hien tai (URL + tieu de + 200 ky tu noi dung dau)
    de thay ngay trinh duyet dang dung o trang gi khi co loi."""
    try:
        url = (driver.current_url or "")[:110]
    except Exception:  # noqa
        url = "?"
    try:
        title = (driver.title or "")[:60]
    except Exception:  # noqa
        title = ""
    body = ""
    try:
        txt = driver.find_element(By.TAG_NAME, "body").text or ""
        body = " ".join(txt.split())[:200]
    except Exception:  # noqa
        pass
    return f"URL={url} | title={title!r} | nội dung đầu trang: {body!r}"


def _wait_upload_ready(driver, timeout=25):
    """Cho khoi upload khoi tao xong: nut/khung 'Chon video' xuat hien.
    Trang Studio vua mo, khoi upload chua san sang ma gan file ngay la
    file bi trang nuot mat (send_keys xong input.files van rong)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _engine_killed():
            return False
        for xp in SELECT_BTN_XPATHS:
            try:
                els = driver.find_elements(By.XPATH, xp)
                if any(e.is_displayed() for e in els):
                    _log("khối upload đã sẵn sàng (thấy nút Chọn video)")
                    time.sleep(2)  # on dinh them truoc khi gan file
                    return True
            except Exception:  # noqa
                continue
        time.sleep(0.5)
    _log("không thấy nút Chọn video sau thời gian chờ, vẫn thử gắn file")
    return False


def _make_input_visible(driver, el):
    try:
        driver.execute_script("""
            var el=arguments[0];
            el.style.cssText='display:block !important;visibility:visible !important;\
                opacity:1 !important;position:fixed;top:0;left:0;\
                width:100px;height:100px;z-index:99999;pointer-events:auto;';
            el.removeAttribute('disabled');el.removeAttribute('readonly');
        """, el)
        time.sleep(0.4)
    except Exception:  # noqa
        pass


def _caption_present(driver):
    for sel in CAPTION_SELECTORS:
        try:
            if driver.find_elements(By.CSS_SELECTOR, sel):
                return True
        except Exception:  # noqa
            continue
    return False


def _fresh_files_count(driver, selector):
    """Hoi lai element MOI trong DOM xem co giu file khong (element cu sau
    khi trang re-render se khong con dang tin nua)."""
    try:
        els = driver.find_elements(By.CSS_SELECTOR, selector)
        for el in els:
            try:
                n = int(driver.execute_script(
                    "return arguments[0].files ? arguments[0].files.length : 0", el) or 0)
                if n > 0:
                    return n
            except Exception:  # noqa
                continue
    except Exception:  # noqa
        pass
    return 0


def _wait_accepted(driver, selector, timeout_s=ACCEPT_WAIT_S):
    """Trong ca cua so cho: o caption xuat hien HOAC input (hoi lai moi)
    co files > 0 thi coi nhu TikTok da nhan file."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if _caption_present(driver):
            return "caption"
        if _fresh_files_count(driver, selector) > 0:
            # Co file roi, cho them ti de o caption mo ra
            t0 = time.time()
            while time.time() - t0 < 8:
                if _caption_present(driver):
                    return "caption"
                time.sleep(0.5)
            return "files"
        time.sleep(1)
    return None


def _try_one_input(driver, selector, idx, abs_path, attempt):
    """1 lan thu gan file vao input[idx] cua selector. Tra True neu duoc nhan."""
    inputs = driver.find_elements(By.CSS_SELECTOR, selector)
    if idx >= len(inputs):
        return False
    inp = inputs[idx]
    if attempt >= 2:
        # Lan 1 gan tran (khong dong vao style), tu lan 2 moi ep hien nhu test1
        _make_input_visible(driver, inp)
        inputs = driver.find_elements(By.CSS_SELECTOR, selector)
        if idx < len(inputs):
            inp = inputs[idx]
    inp.send_keys(abs_path)
    how = _wait_accepted(driver, selector)
    if how:
        _log(f"input[{idx}] '{selector}' (lần {attempt}): TikTok ĐÃ nhận video ({how})")
        return True
    _log(f"input[{idx}] '{selector}' (lần {attempt}): quá {ACCEPT_WAIT_S}s chưa được nhận")
    return False


def _set_video_file(driver, abs_path):
    """Gan file: duyet tung selector x tung input, moi input thu toi da
    2 lan; khong duoc nua thi thu trong iframe nhu test1.py."""
    if _engine_killed():
        return False
    for selector in FILE_SELECTORS:
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
        except Exception:  # noqa
            _log(f"selector '{selector}': không có input nào trong DOM")
            continue
        try:
            n = len(driver.find_elements(By.CSS_SELECTOR, selector))
        except Exception:  # noqa
            n = 0
        _log(f"selector '{selector}': {n} input")
        for idx in range(n):
            for attempt in (1, 2):
                try:
                    if _try_one_input(driver, selector, idx, abs_path, attempt):
                        return True
                except Exception as e:  # noqa
                    _log(f"input[{idx}] '{selector}' lần {attempt} lỗi: {_short(e)}")
                    time.sleep(1)

    # Thu trong iframe nhu test1.py
    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        if iframes:
            _log(f"thử {len(iframes)} iframe...")
        for i, iframe in enumerate(iframes):
            try:
                driver.switch_to.default_content()
                driver.switch_to.frame(iframe)
                for selector in FILE_SELECTORS:
                    try:
                        inp = WebDriverWait(driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                        _make_input_visible(driver, inp)
                        inp = driver.find_element(By.CSS_SELECTOR, selector)
                        inp.send_keys(abs_path)
                        if _wait_accepted(driver, selector, timeout_s=10):
                            _log(f"gắn file OK trong iframe[{i}]")
                            driver.switch_to.default_content()
                            return True
                    except Exception:  # noqa
                        pass
            except Exception:  # noqa
                pass
            finally:
                try:
                    driver.switch_to.default_content()
                except Exception:  # noqa
                    pass
    except Exception as e:  # noqa
        _log(f"tìm iframe lỗi: {_short(e)}")
    return False


def _set_caption(driver, caption_text):
    time.sleep(1)
    for sel in CAPTION_SELECTORS:
        try:
            el = WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
            driver.execute_script("arguments[0].click();", el)
            time.sleep(0.3)
            el.send_keys(Keys.CONTROL + "a")
            el.send_keys(Keys.DELETE)
            time.sleep(0.2)
            el.send_keys(caption_text)
            _log(f"đã đặt caption (selector '{sel}')")
            return True
        except Exception:  # noqa
            continue
    _log("không đặt được caption")
    return False


def _wait_post_button(driver, timeout_s=POST_WAIT_S):
    _log("đang chờ nút Post...")
    deadline = time.time() + timeout_s
    last_log = 0.0
    while time.time() < deadline:
        if _engine_killed():
            return False
        try:
            btn = driver.find_element(By.CSS_SELECTOR, POST_SELECTOR)
            if btn and btn.is_enabled():
                aria = btn.get_attribute("aria-disabled") or ""
                cls = btn.get_attribute("class") or ""
                if aria != "true" and "disabled" not in cls:
                    _log("nút Post đã sẵn sàng")
                    return True
        except Exception:  # noqa
            pass
        now = time.time()
        if now - last_log >= 15:
            _log(f"vẫn đang chờ video tải lên / nút Post... (còn tối đa {int(deadline - now)}s)")
            last_log = now
        time.sleep(0.5)
    return False


def _click_post(driver):
    try:
        btn = driver.find_element(By.CSS_SELECTOR, POST_SELECTOR)
        driver.execute_script("arguments[0].scrollIntoView({block:'center'})", btn)
        time.sleep(0.3)
        try:
            btn.click()
        except Exception:  # noqa
            driver.execute_script("arguments[0].click()", btn)
        _log("đã bấm Post")
        return True
    except Exception as e:  # noqa
        _log(f"không bấm được Post: {_short(e)}")
        return False



CONTINUE_POST_XPATHS = [
    "//button[contains(.,'Đăng ngay')]",
    "//button[contains(.,'Post now')]",
    "//button[contains(.,'Post Now')]",
]


def _click_continue_posting(driver):
    """Hop thoai 'Tiep tuc dang?' cua TikTok: hien voi mot so account
    ngay sau khi bam Post, khi TikTok chua kiem tra xong video ('van
    dang kiem tra video cua ban de phat hien xem co van de tiem an hay
    khong... tiep tuc dang truoc khi quy trinh kiem tra hoan tat?').
    Phai bam nut 'Dang ngay' / 'Post now' thi video moi duoc dang that;
    khong bam la _confirm_posted cho doi URL den het gio roi bao loi
    oan. Tra True neu vua bam duoc nut."""
    for xp in CONTINUE_POST_XPATHS:
        try:
            for btn in driver.find_elements(By.XPATH, xp):
                try:
                    if not btn.is_displayed():
                        continue
                    if btn.get_attribute("data-e2e") == "post_video_button":
                        continue
                    _log("thấy hộp thoại 'Tiếp tục đăng?' -> bấm 'Đăng ngay'")
                    try:
                        btn.click()
                    except Exception:  # noqa
                        driver.execute_script("arguments[0].click()", btn)
                    return True
                except Exception:  # noqa
                    continue
        except Exception:  # noqa
            continue
    return False


def _confirm_posted(driver, timeout_s=POST_CONFIRM_WAIT_S):
    """Xac nhan CHI bang URL + hop thoai sau Post, nhu test1.py."""
    deadline = time.time() + timeout_s
    dialog_clicked = False
    last_continue_click = 0.0
    while time.time() < deadline:
        if _engine_killed():
            return False
        # Hop thoai 'Tiep tuc dang?' co the hien bat ky luc nao trong
        # luc cho xac nhan: thay la bam 'Dang ngay' ngay (toi da 1 lan
        # moi 5 giay, tranh bam lap neu hop thoai chua kip dong).
        if time.time() - last_continue_click >= 5:
            try:
                if _click_continue_posting(driver):
                    last_continue_click = time.time()
                    time.sleep(1)
            except Exception:  # noqa
                pass
        try:
            if not dialog_clicked:
                clicked = False
                for sel in DIALOG_BUTTON_SELECTORS:
                    try:
                        for btn in driver.find_elements(By.CSS_SELECTOR, sel):
                            try:
                                if not btn.is_displayed():
                                    continue
                                if btn.get_attribute("data-e2e") == "post_video_button":
                                    continue
                                text = (btn.text or "").strip()
                                low = text.lower()
                                if any(k in low or k in text for k in DIALOG_UPLOAD_KEYWORDS):
                                    _log(f"thấy nút hộp thoại '{text}' -> bấm")
                                    driver.execute_script(
                                        "arguments[0].scrollIntoView({block:'center'})", btn)
                                    time.sleep(0.5)
                                    try:
                                        btn.click()
                                    except Exception:  # noqa
                                        driver.execute_script("arguments[0].click()", btn)
                                    dialog_clicked = True
                                    clicked = True
                                    break
                            except Exception:  # noqa
                                continue
                    except Exception:  # noqa
                        continue
                    if clicked:
                        break
                if dialog_clicked:
                    t0 = time.time()
                    while time.time() - t0 < 25:
                        cur = (driver.current_url or "").lower()
                        if "tiktokstudio/upload" in cur or "tiktokstudio/content" in cur:
                            _log("SUCCESS: đã về trang đích sau hộp thoại")
                            return True
                        time.sleep(1)
                    _log("bấm nút hộp thoại xong nhưng 25s chưa chuyển trang")
                    continue
            cur = (driver.current_url or "").lower()
            if "tiktokstudio/content" in cur or "tiktokstudio/video" in cur:
                _log("xác nhận thành công (trang content/video)")
                return True
            if "upload" not in cur and cur not in ("", "about:blank"):
                _log("xác nhận thành công (đã rời trang upload)")
                return True
        except Exception:  # noqa
            pass
        time.sleep(0.3)
    return False


def _is_logged_in(driver):
    try:
        for c in driver.get_cookies():
            if c.get("name") == "sessionid" and c.get("value"):
                return True
    except Exception:  # noqa
        pass
    return False


def _cookie_names(driver):
    """Chi lay TEN cookie (khong lay gia tri) de chan doan khi can."""
    try:
        return sorted({c.get("name", "") for c in driver.get_cookies() if c.get("name")})
    except Exception:  # noqa
        return []


def _looks_logged_in(driver):
    """Da login chua - danh gia bang GIAO DIEN (tin cay hon doc cookie nhieu):
    trang TikTok Studio upload chi hien khung 'Chon video' khi da login,
    chua login la TikTok da ve trang login. get_cookies() cua Selenium chi
    doc cookie cua dung tab dang active nen rat de bao thieu gia."""
    cur = (driver.current_url or "").lower()
    if "login" in cur:
        return False
    for xp in SELECT_BTN_XPATHS:
        try:
            if any(e.is_displayed() for e in driver.find_elements(By.XPATH, xp)):
                return True
        except Exception:  # noqa
            continue
    return False


def _do_upload(driver, abs_path, caption):
    if _engine_killed():
        _log("⏹ đã bấm STOP - huỷ trước khi upload")
        return False
    _ensure_page_tab(driver)
    driver.get(UPLOAD_URL)
    try:
        WebDriverWait(driver, 15).until(
            lambda d: d.execute_script("return document.readyState") == "complete")
    except Exception:  # noqa
        time.sleep(1)
    _focus_tiktok_tab(driver)

    # Xac nhan login bang GIAO DIEN + cookie, cho toi da 20s de trang on dinh.
    # (Ban truoc chi dua vao cookie nen bao "chua login" oan cho profile
    # da login tay san trong GPM.)
    logged_in = False
    deadline = time.time() + 20
    while time.time() < deadline:
        if _engine_killed():
            _log("⏹ đã bấm STOP - huỷ upload ngay")
            return False
        try:
            _cu = (driver.current_url or "")
        except Exception:  # noqa
            _cu = ""
        if _cu.startswith(_BAD_TAB_PREFIXES):
            # Ket o trang nen extension: chon lai tab trang that roi vao
            # lai trang upload (tab TikTok co the vua moi xuat hien).
            if _ensure_page_tab(driver):
                try:
                    driver.get(UPLOAD_URL)
                except Exception:  # noqa
                    pass
        if _looks_logged_in(driver) or _is_logged_in(driver):
            logged_in = True
            break
        time.sleep(1)
    if not logged_in:
        cur = driver.current_url or ""
        names = _cookie_names(driver)
        _log(f"KHÔNG thấy dấu hiệu đã login sau 20s. URL hiện tại: {cur[:100]}")
        _log(f"cookie đọc được ({len(names)}): {', '.join(names[:25]) or 'không có'}")
        _log(f"trang lúc này: {_page_diag(driver)}")
        _log("Nếu cửa sổ đang hiện trang login thật -> profile chưa có session. "
             "Nếu đang hiện khung chọn video -> gửi tôi 2 dòng log trên.")
        return False
    _log("đã xác nhận có session (qua giao diện/cookie)")

    if not _wait_upload_ready(driver):
        _log(f"trang lúc này: {_page_diag(driver)}")

    if not _set_video_file(driver, abs_path):
        _log("KHÔNG gắn được file vào trang upload (đã thử mọi input x2 lần + iframe)")
        return False
    _log("đang tải video lên...")

    if caption:
        _set_caption(driver, caption)

    if not _wait_post_button(driver):
        _log("nút Post không bật sau thời gian chờ, vẫn thử bấm như test1.py...")
    if not _click_post(driver):
        return False

    ok = _confirm_posted(driver)
    _log("ĐÃ ĐĂNG (xác nhận bằng URL)" if ok else
         "upload KHÔNG được xác nhận -> coi như THẤT BẠI")
    return ok


# ============================================================
# ==== HAM GUI GOI: upload_one_selenium ====
# ============================================================

# ---- Xoa video goc sau khi DANG THANH CONG (da xac nhan bang URL) ----
DELETE_AFTER_UPLOAD = True  # doi thanh False neu muon giu lai file goc

_inuse_lock = threading.Lock()
_inuse_paths = {}  # duong dan -> so job dang dung file do


def _inuse_add(path):
    with _inuse_lock:
        _inuse_paths[path] = _inuse_paths.get(path, 0) + 1


def _inuse_release(path):
    """Giam so job dang dung file; tra ve so con lai."""
    with _inuse_lock:
        n = _inuse_paths.get(path, 1) - 1
        if n <= 0:
            _inuse_paths.pop(path, None)
            return 0
        _inuse_paths[path] = n
        return n


def _delete_source_file(abs_path):
    """Xoa file video goc. Thu lai vai lan: trinh duyet vua dong xong co
    the con giu handle file them vai giay (Windows khoa file)."""
    for i in range(6):
        try:
            os.remove(abs_path)
            _log(f"đã XOÁ video gốc: {abs_path}")
            return True
        except FileNotFoundError:
            _log("video gốc đã không còn trên đĩa (đã bị xoá trước đó)")
            return True
        except Exception as e:  # noqa
            if i == 5:
                _log(f"KHÔNG xoá được video gốc: {_short(e)}")
                return False
            time.sleep(1)
    return False


def _upload_one_run(name, abs_path, caption):
    """Phan chay that cua 1 job (da khoa theo profile). Tra True/False."""
    with _lock_for(name):
        profile_id = _get_profile_id(name)
        if not profile_id:
            _log(f"không tìm thấy GPM profile tên '{name}'")
            return False

        port = _start_profile(profile_id, _port_for(name))
        if port is None:
            return False
        _register_active_profile(profile_id)
        if not _wait_devtools(port):
            _log(f"cổng DevTools {port} không trả lời sau 30s")
            _stop_profile(profile_id)
            return False

        # Chon gpmdriver KHOP phien ban trinh duyet vua mo (147 != 154!)
        major, browser_str = _browser_major(port)
        driver_path = _driver_path_for_major(major)
        _log(f"trình duyệt: {browser_str or '?'} -> gpmdriver: {driver_path}")
        if not os.path.exists(driver_path):
            _log(f"không thấy gpmdriver.exe tại: {driver_path}")
            _stop_profile(profile_id)
            return False

        slot = _claim_slot()  # o luoi de xep cua so can doi man hinh
        driver = None
        try:
            svc = Service(executable_path=driver_path)
            opts = Options()
            opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
            driver = webdriver.Chrome(service=svc, options=opts)
            _log(f"Selenium đã gắn vào profile qua cổng {port}")
            _register_active_driver(name, driver)
            _ensure_page_tab(driver)
            _tile_window(driver, slot)
            return _do_upload(driver, abs_path, caption or "")
        except Exception as e:  # noqa
            _log(f"lỗi upload: {_short(e)}")
            return False
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:  # noqa
                    pass
                _log("đã đóng trình duyệt (driver.quit)")
            _unregister_active_driver(name)
            _stop_profile(profile_id)
            _release_slot(slot)


# Cookie phiên đăng nhập của TikTok: tuỳ profile/vùng mà trình duyệt chỉ
# có 1 trong 3 tên này (cùng 1 giá trị phiên) - có bất kỳ cái nào là đã login.
SESSION_COOKIE_KEYS = ("sessionid", "sessionid_ss", "sid_tt")


def _cookies_to_header(cookies):
    """Ghép list cookie dict của Selenium thành chuỗi dạng
    'name=value; name=value; ...'. Tên trùng ở nhiều domain thì ưu tiên
    bản thuộc '.tiktok.com'. Có cookie phiên (sessionid / sessionid_ss /
    sid_tt) mới coi là đã login; nếu thiếu 'sessionid' trần mà có bản
    _ss/sid_tt thì tự bổ sung 'sessionid=' cùng giá trị cho đồng nhất
    định dạng. Trả '' nếu không có cookie phiên nào (chưa login)."""
    best = {}
    for c in cookies or []:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        domain = c.get("domain") or ""
        if "tiktok" not in domain:
            continue
        if name not in best or domain == ".tiktok.com":
            best[name] = c.get("value") or ""
    sid = ""
    for k in SESSION_COOKIE_KEYS:
        if best.get(k):
            sid = best[k]
            break
    if not sid:
        return ""
    if not best.get("sessionid"):
        best["sessionid"] = sid
    return "; ".join(f"{k}={v}" for k, v in best.items())


def export_cookie_selenium(account_id):
    """Mở profile GPM của account (đã login tay sẵn), đọc toàn bộ cookie
    tiktok.com và ghép thành chuỗi header. Trả chuỗi cookie (có
    sessionid) nếu thành công, '' nếu thất bại. Đi đúng quy trình mở
    profile như upload: start kèm remote_debugging_port, gpmdriver khớp
    phiên bản, xếp lưới/ẩn cửa sổ theo GRID_TOTAL + HIDE_BROWSER."""
    name = parse_line(str(account_id))["name"]
    _ctx.tag = name
    print(f"\n=== Xuất cookie cho {account_id} (profile {name}) ===", flush=True)
    with _lock_for(name):
        profile_id = _get_profile_id(name)
        if not profile_id:
            _log(f"không tìm thấy GPM profile tên '{name}'")
            return ""
        port = _start_profile(profile_id, _port_for(name))
        if port is None:
            return ""
        _register_active_profile(profile_id)
        if not _wait_devtools(port):
            _log(f"cổng DevTools {port} không trả lời sau 30s")
            _stop_profile(profile_id)
            return ""
        major, browser_str = _browser_major(port)
        driver_path = _driver_path_for_major(major)
        _log(f"trình duyệt: {browser_str or '?'} -> gpmdriver: {driver_path}")
        if not os.path.exists(driver_path):
            _log(f"không thấy gpmdriver.exe tại: {driver_path}")
            _stop_profile(profile_id)
            return ""
        slot = _claim_slot()
        driver = None
        try:
            svc = Service(executable_path=driver_path)
            opts = Options()
            opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
            driver = webdriver.Chrome(service=svc, options=opts)
            _log(f"Selenium đã gắn vào profile qua cổng {port}")
            _register_active_driver(name, driver)
            _ensure_page_tab(driver)
            _tile_window(driver, slot)
            try:
                driver.get("https://www.tiktok.com/")
            except Exception:  # noqa
                pass
            time.sleep(3)
            header = _cookies_to_header(driver.get_cookies())
            if header:
                _log(f"đã lấy {header.count(';') + 1} cookie, có cookie phiên đăng nhập")
            else:
                _log("không thấy cookie phiên (sessionid/sessionid_ss/sid_tt) - profile chưa login TikTok?")
            return header
        except Exception as e:  # noqa
            _log(f"lỗi xuất cookie: {_short(e)}")
            return ""
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:  # noqa
                    pass
            _unregister_active_driver(name)
            _stop_profile(profile_id)
            _release_slot(slot)


_VIEW_HOOK_JS = """
window.__capItems = [];
(function () {
  function grab(j) {
    try {
      if (j && j.itemList) {
        for (var k = 0; k < j.itemList.length; k++) {
          window.__capItems.push(j.itemList[k]);
        }
      }
    } catch (e) {}
  }
  var of = window.fetch;
  if (of) {
    window.fetch = function () {
      var u = '';
      try { u = (arguments[0] && arguments[0].url) || String(arguments[0] || ''); } catch (e) {}
      return of.apply(this, arguments).then(function (r) {
        try {
          if (u.indexOf('/api/post/item_list/') >= 0) {
            r.clone().json().then(grab).catch(function () {});
          }
        } catch (e) {}
        return r;
      });
    };
  }
  var oo = XMLHttpRequest.prototype.open;
  var os = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) {
    this.__capU = u;
    return oo.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function () {
    var self = this;
    this.addEventListener('load', function () {
      try {
        if (self.__capU && String(self.__capU).indexOf('/api/post/item_list/') >= 0) {
          grab(JSON.parse(self.responseText));
        }
      } catch (e) {}
    });
    return os.apply(this, arguments);
  };
})();
"""

_VIEW_EXTRACT_JS = """
var m = {};
var arr = window.__capItems || [];
for (var k = 0; k < arr.length; k++) {
  var it = arr[k];
  if (it && it.id) { m[it.id] = it; }
}
var out = [];
for (var id in m) {
  var v = m[id];
  var p = 0;
  try { p = (v.stats && v.stats.playCount) || 0; } catch (e) {}
  out.push([v.createTime || 0, p]);
}
return out;
"""


def scan_views_via_browser(account_id, recent_n=5, max_scrolls=12,
                           wait_s=60):
    """Quet VIEW du phong qua trinh duyet GPM cua chinh account: mo
    profile (da login tay san), gan hook bat cac phan hoi item_list ma
    TRANG TU TAI bang phien dang nhap that, cuon trang de tai them,
    roi tinh view30d + view cua recent_n video moi nhat (giong het
    cong thuc cua quet an). Tra (views30d, views, so_video, msg);
    that bai thi views30d/views = None."""
    name = parse_line(str(account_id))["name"]
    _ctx.tag = name
    with _lock_for(name):
        profile_id = _get_profile_id(name)
        if not profile_id:
            return None, None, 0, f"không tìm thấy GPM profile tên '{name}'"
        port = _start_profile(profile_id, _port_for(name))
        if port is None:
            return None, None, 0, "không start được profile GPM"
        _register_active_profile(profile_id)
        driver = None
        slot = None
        try:
            if not _wait_devtools(port):
                return None, None, 0, (f"cổng DevTools {port} không trả "
                                       "lời sau 30s")
            major, browser_str = _browser_major(port)
            driver_path = _driver_path_for_major(major)
            _log(f"trình duyệt: {browser_str or '?'} -> gpmdriver: {driver_path}")
            if not os.path.exists(driver_path):
                return None, None, 0, f"không thấy gpmdriver.exe tại: {driver_path}"
            slot = _claim_slot()
            svc = Service(executable_path=driver_path)
            opts = Options()
            opts.add_experimental_option("debuggerAddress",
                                         f"127.0.0.1:{port}")
            driver = webdriver.Chrome(service=svc, options=opts)
            _log(f"Selenium đã gắn vào profile qua cổng {port}")
            _register_active_driver(name, driver)
            _ensure_page_tab(driver)
            _tile_window(driver, slot)
            try:
                driver.execute_cdp_cmd(
                    "Page.addScriptToEvaluateOnNewDocument",
                    {"source": _VIEW_HOOK_JS})
            except Exception as e:  # noqa
                _log(f"không gắn được hook bắt item_list: {_short(e)}")
            _log(f"mở trang profile @{name} để quét view qua trình duyệt...")
            try:
                driver.get(f"https://www.tiktok.com/@{name}")
            except Exception:  # noqa
                pass
            # TOI UU TOC DO: ban cu ngu 2.5s/vong + cuon lien tuc nen rat
            # cham. Ban nay doc du lieu moi 0.6s, chi cuon khi con thieu
            # video (cach nhau >= 1.2s), va dung theo THOI GIAN on dinh:
            # du recent_n video + 3s khong tang them la xong (khong phai
            # cho het vong nhu truoc).
            cutoff = int(time.time()) - 30 * 86400
            deadline = time.time() + wait_s
            pairs = []
            last_n = 0
            last_growth = time.time()
            scrolls = 0
            last_scroll = 0.0
            while time.time() < deadline:
                if _engine_killed():
                    return None, None, 0, "đã dừng (STOP)"
                try:
                    pairs = driver.execute_script(_VIEW_EXTRACT_JS) or []
                except Exception:  # noqa
                    pairs = []
                if pairs:
                    pairs = sorted(pairs,
                                   key=lambda p: -int(p[0] or 0))
                    if len(pairs) != last_n:
                        last_n = len(pairs)
                        last_growth = time.time()
                    oldest = int(pairs[-1][0] or 0)
                    idle = time.time() - last_growth
                    if len(pairs) >= recent_n and idle >= 3.0:
                        break
                    if oldest and oldest < cutoff and idle >= 1.5 \
                            and len(pairs) >= recent_n:
                        break
                need_more = (not pairs or len(pairs) < recent_n
                             or (pairs and int(pairs[-1][0] or 0) >= cutoff))
                if need_more and scrolls < max_scrolls \
                        and time.time() - last_scroll >= 1.2:
                    try:
                        driver.execute_script(
                            "window.scrollTo(0, document.body.scrollHeight);")
                    except Exception:  # noqa
                        pass
                    scrolls += 1
                    last_scroll = time.time()
                time.sleep(0.6)
            if not pairs:
                return None, None, 0, ("trang profile không tải được danh "
                                       "sách video (profile chưa login? "
                                       "bị chặn?)")
            views30d = sum(int(p[1] or 0) for p in pairs
                           if int(p[0] or 0) >= cutoff)
            views = sum(int(p[1] or 0) for p in pairs[:recent_n])
            _log(f"quét view qua trình duyệt: {len(pairs)} video, "
                 f"view30d={views30d}, view{recent_n}={views}")
            return views30d, views, len(pairs), "OK"
        except Exception as e:  # noqa
            return None, None, 0, (f"lỗi quét view qua trình duyệt: "
                                   f"{_short(e)}")
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:  # noqa
                    pass
            _unregister_active_driver(name)
            _stop_profile(profile_id)
            if slot is not None:
                _release_slot(slot)


def scan_account_full(acc, proxy_pool, recent_n=5, timeout=15,
                      cookie_pool=None, view_browser=False):
    """scan_account_info + du phong: acc nao quet an doc duoc profile
    ma khong ra view, neu view_browser=True thi mo profile GPM cua acc
    do de lay view tu trang profile that."""
    r = scan_account_info(acc, proxy_pool, recent_n, timeout, cookie_pool)
    if view_browser and r.get("ok") and r.get("views") is None:
        handle = (acc.get("id") or "").strip().lstrip("@")
        print(f"  [SCAN] @{handle}: quét ẩn không ra view -> thử quét "
              "qua trình duyệt GPM...", flush=True)
        v30, vn, _n_items, bmsg = scan_views_via_browser(handle, recent_n)
        if vn is not None:
            r["views30d"] = v30
            r["views"] = vn
            r["msg"] = "OK (view qua trình duyệt GPM)"
        else:
            r["msg"] = (r.get("msg") or "") + f" | trình duyệt: {bmsg}"
    return r


def upload_one_selenium(account_id, video_path, caption="", delete_after=None):
    """Upload 1 video cho 1 account bang Selenium + GPM.

    account_id: id TikTok (chuoi) nhu gui_upload.py truyen acc["id"].
    Tra ve True neu dang xong (da xac nhan bang URL), False neu khong.
    Dang THANH CONG thi tu dong XOA video goc trong thu muc (tru khi
    delete_after=False hoac DELETE_AFTER_UPLOAD=False), va chi xoa khi
    khong con job nao khac dang dung chung file do.
    """
    video = Path(str(video_path))
    if not video.exists():
        print(f"  [UP] không thấy file video: {video}", flush=True)
        return False
    abs_path = os.path.abspath(str(video))

    name = parse_line(str(account_id))["name"]
    _ctx.tag = name
    print(f"\n=== Upload (Selenium) cho {account_id} (profile {name}) ===\n"
          f"  Video: {video.name}", flush=True)

    if delete_after is None:
        delete_after = DELETE_AFTER_UPLOAD

    _inuse_add(abs_path)
    try:
        result = _upload_one_run(name, abs_path, caption or "")
        if not result:
            # User yêu cầu: upload lỗi thì (trình duyệt/profile đã tự tắt
            # sạch ở cuối _upload_one_run) TỰ CHẠY LẠI LẦN 2; lần 2 vẫn
            # lỗi thì trả False -> job bị đánh dấu lỗi và bỏ qua.
            print("  [UP] ❌ Upload lỗi lần 1 - tự chạy lại lần 2...", flush=True)
            result = _upload_one_run(name, abs_path, caption or "")
            if not result:
                print("  [UP] ❌ Upload vẫn lỗi ở lần 2 - đánh dấu lỗi, bỏ qua video này.", flush=True)
    finally:
        remaining = _inuse_release(abs_path)

    if result and delete_after:
        if remaining == 0:
            _delete_source_file(abs_path)
        else:
            _log(f"chưa xoá video gốc: còn {remaining} job khác đang dùng file này")
    return result


def upload_one(account_id, video_path, caption="", **kwargs):
    """Alias de tuong thich neu noi nao do goi upload_one: di duong Selenium."""
    return upload_one_selenium(account_id, video_path, caption)


def _cli_main():
    import sys
    if len(sys.argv) < 3:
        print("Dùng: python tiktok_upload_tool.py --cli <idTiktok> <video> [caption]")
        sys.exit(1)
    ok = upload_one_selenium(sys.argv[1], sys.argv[2],
                             sys.argv[3] if len(sys.argv) > 3 else "")
    print("Kết quả:", "OK" if ok else "THẤT BẠI")
    sys.exit(0 if ok else 1)


# ============================================================
# ==== GUI (tu gui_upload.py v2.1) ====
# ============================================================



# ============================================================
# ==== CONFIG ====
# ============================================================


def _sort_key_for_cell(s):
    """Khoa sap xep 1 o bang: thoi luong 'mm:ss'/'hh:mm:ss' tinh ra
    giay; so (ke ca co dau phay ngan nghin, $, %, hau to K/M/B) xep
    theo gia tri; chu xep theo bang chu cai; o trong/'—' nho nhat."""
    t = (s or "").strip()
    if t in ("", "—", "-", "–"):
        return (0, 0.0, "")
    m = re.fullmatch(r"(\d+):(\d{2})(?::(\d{2}))?", t)
    if m:
        secs = 0
        for g in m.groups():
            if g is not None:
                secs = secs * 60 + int(g)
        return (0, float(secs), "")
    num = t.replace(",", "").replace("$", "").replace("%", "").strip()
    mult = 1.0
    if num and num[-1] in "KkMmBb":
        mult = {"k": 1e3, "m": 1e6, "b": 1e9}[num[-1].lower()]
        num = num[:-1]
    try:
        return (0, float(num) * mult, "")
    except ValueError:
        return (1, 0.0, t.casefold())


def sort_treeview(tree, col, reverse=False, renumber=None):
    """Sap xep cac dong cua 1 Treeview theo cot `col` - chi xep tren
    man hinh, khong doi thu tu du lieu goc. renumber='text': danh lai
    STT o cot #0; renumber='first': danh lai STT o values[0]."""
    items = list(tree.get_children(""))
    items.sort(key=lambda iid: _sort_key_for_cell(tree.set(iid, col)),
               reverse=reverse)
    for idx, iid in enumerate(items):
        tree.move(iid, "", idx)
    if renumber == "text":
        for idx, iid in enumerate(items):
            tree.item(iid, text=str(idx + 1))
    elif renumber == "first":
        for idx, iid in enumerate(items):
            vals = list(tree.item(iid, "values") or ())
            if vals:
                vals[0] = idx + 1
                tree.item(iid, values=vals)
    return items


class LogStream:
    """Hứng print() để hiển thị log."""
    def __init__(self, q): self.q = q
    def write(self, s):
        if s:
            self.q.put(s)
    def flush(self): pass


class UploadJob:
    """1 job upload: account + video + caption."""
    def __init__(self, acc_id, video_path, caption=""):
        self.acc_id = acc_id
        self.video_path = Path(video_path)
        self.caption = caption or self.video_path.stem
        self.status = "⏳ Chờ"
        self.progress = 0
        self.start_time = None
        self.end_time = None
        self.error = ""

    @property
    def duration(self):
        if not self.start_time:
            return None
        end = self.end_time or time.time()
        return end - self.start_time

    def __repr__(self):
        return f"<Job {self.acc_id}|{self.video_path.name}>"


# ============================================================
# ==== TAI VIDEO YOUTUBE SHORTS (API v3 loc + yt-dlp tai) ====
# ============================================================
# Vai tro tach bach de tiet kiem quota + tranh bi chan nhip:
# - YouTube Data API v3 CHI de lay metadata (title, thoi luong): videos.list
#   ton 1 quota/lan goi, 1 lan check duoc 50 video. Loc Shorts that (<=61s),
#   bo video rieng tu/da xoa TRUOC khi tai.
# - Tai file that bang yt-dlp (nhu test1.py): it luong, nghi ngau nhien
#   giua cac video, tu thu lai khi loi -> tranh HTTP 429 / spam flag.
# - yt_downloaded.json ghi lai ID da tai -> chay lai khong tai trung.
YT_CACHE_FILE = APP_DIR / "yt_downloaded.json"
YT_SHORTS_MAX_SEC = 61
_yt_lock = threading.Lock()


def _strip_hashtags(name):
    """Bo toan bo hashtag (#...) khoi ten, don khoang trang thua."""
    s = re.sub(r"#\S+", "", name or "")
    s = re.sub(r"\s+", " ", s)
    return s.strip(" -_|")


def _transform_name(name, find="", repl="", prefix="", suffix="",
                    strip_tags=False, number=None, fixed=""):
    """Doi ten hang loat: neu co `fixed` thi thay TOAN BO ten bang
    chu co dinh do (bo qua moi muc khac, khong danh so). Khong thi:
    xoa hashtag -> tim/thay the -> them dau/cuoi -> danh so o cuoi
    (khi number khac None)."""
    fx = re.sub(r"\s+", " ", (fixed or "")).strip()
    if fx:
        return fx
    s = name or ""
    if strip_tags:
        s = _strip_hashtags(s)
    if find:
        s = s.replace(find, repl)
    s = f"{prefix or ''}{s}{suffix or ''}"
    if number is not None:
        s = f"{s} {number}"
    return re.sub(r"\s+", " ", s).strip()


def _safe_file_stem(stem):
    """Bo ky tu cam trong ten file Windows, khong de rong."""
    s = re.sub(r'[\\/:*?"<>|]', "_", stem or "")
    return s.strip(" .") or "video"


def _set_yt_cache_titles(titles):
    """Ghi title moi cho nhieu video vao yt_downloaded.json (gop voi
    entry cu, ghi 1 lan duy nhat)."""
    if not titles:
        return
    with _yt_lock:
        data = _load_yt_cache()
        for vid, title in titles.items():
            entry = dict(data.get(vid) or {})
            entry["title"] = title
            data[vid] = entry
        try:
            YT_CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False),
                                     encoding="utf-8")
        except Exception:  # noqa
            pass


def _load_yt_cache():
    try:
        return json.loads(YT_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa
        return {}


def _save_yt_cache_entry(video_id, info):
    with _yt_lock:
        data = _load_yt_cache()
        data[video_id] = info
        try:
            YT_CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False),
                                     encoding="utf-8")
        except Exception:  # noqa
            pass


def parse_youtube_id(text):
    """Tach video ID (11 ky tu) tu link watch / shorts / youtu.be hoac ID tho."""
    t = (text or "").strip()
    if not t:
        return None
    m = re.search(r"(?:shorts/|youtu\.be/|[?&]v=)([A-Za-z0-9_-]{11})", t)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", t):
        return t
    return None


def parse_iso8601_duration(s):
    """'PT1H2M3S' -> so giay (1 gio = 3600 giay)."""
    m = re.match(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$", (s or "").strip())
    if not m:
        return 0
    h, mi, sec = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + sec


def fmt_duration(sec):
    """Số giây -> 'phút:giây' (75 -> '1:15', 45 -> '0:45')."""
    if sec is None:
        return "—"
    sec = int(sec)
    return f"{sec // 60}:{sec % 60:02d}"


def send_telegram_message(token, chat_id, text):
    """Gửi 1 tin nhắn qua Telegram Bot API.
    Trả None nếu thành công, chuỗi mô tả lỗi nếu hỏng."""
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text}, timeout=20)
        data = r.json()
        if data.get("ok"):
            return None
        return str(data.get("description") or f"HTTP {r.status_code}")
    except Exception as e:  # noqa
        return _short(e)


def fetch_telegram_chat_id(token):
    """Lấy Chat ID từ getUpdates của bot (người dùng cần mở bot và nhắn
    /start trước). Trả (chat_id, tên) hoặc (None, lý do)."""
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{token}/getUpdates", timeout=20)
        data = r.json()
        if not data.get("ok"):
            return None, str(data.get("description") or "Token không hợp lệ")
        for upd in reversed(data.get("result", [])):
            msg = upd.get("message") or upd.get("edited_message") or {}
            chat = msg.get("chat") or {}
            if chat.get("id") is not None:
                who = chat.get("username") or chat.get("first_name") or ""
                return str(chat["id"]), who
        return None, ("Chưa thấy tin nhắn nào - hãy mở Telegram, tìm bot "
                      "của bạn, nhắn /start rồi bấm lấy lại.")
    except Exception as e:  # noqa
        return None, _short(e)


# ==== NHIEU API key YouTube v3 (v3.95): pool key + tu xoay vong ====
# Nguoi dung co the nhap NHIEU key (moi key mac dinh 10.000 quota/ngay).
# Moi loi goi API di qua _yt_get: key dang dung het quota / key khong
# hop le thi tu dong danh dau "chet" va thu lai bang key ke tiep.
_YT_KEY_LOCK = threading.Lock()
_YT_KEYS = []
_YT_DEAD_KEYS = set()


def _parse_yt_keys(raw):
    """Tach DS key tu chuoi (moi dong / dau phay / dau cham phay /
    khoang trang = 1 key) hoac tu list san co. Bo trung, giu thu tu."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        out, seen = [], set()
        for it in raw:
            for p in _parse_yt_keys(it):
                if p not in seen:
                    seen.add(p)
                    out.append(p)
        return out
    out, seen = [], set()
    for p in re.split(r"[\s,;]+", str(raw)):
        p = p.strip()
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def yt_keys_set(keys):
    """Dat lai DS key cho pool (tu settings / GUI). Key 'chet' nao
    khong con trong DS thi quen di; key con trong DS van giu danh dau
    chet (chi reset khi khoi dong lai tool)."""
    global _YT_KEYS
    ks = _parse_yt_keys(keys)
    with _YT_KEY_LOCK:
        _YT_KEYS = ks
        _YT_DEAD_KEYS.intersection_update(set(ks))


def _yt_resp_is_dead_key(resp):
    """True neu response la loi HET QUOTA hoac KEY INVALID - key nay
    khong dung tiep duoc hom nay, nen doi sang key khac."""
    if resp is None:
        return False
    reason = ""
    try:
        errs = resp.json().get("error", {}).get("errors", [])
        reason = (errs[0].get("reason", "") if errs else "") or ""
    except Exception:  # noqa
        reason = ""
    if reason in ("quotaExceeded", "dailyLimitExceeded"):
        return True
    if reason == "keyInvalid":
        return True
    if resp.status_code == 403 and "quota" in (resp.text or "").lower():
        return True
    return False


def _yt_get(url, params, timeout=25):
    """GET YouTube API bang key trong POOL: tu dong doi sang key ke
    tiep khi key hien tai het quota / invalid, roi thu lai ngay.
    params['key'] (key caller truyen vao) chi dung de seed pool khi
    pool dang rong. Het sach key song -> tra response loi cuoi cung
    de caller xu ly nhu truoc."""
    params = dict(params or {})
    seed = params.get("key") or ""
    with _YT_KEY_LOCK:
        if not _YT_KEYS and seed:
            _YT_KEYS.extend(_parse_yt_keys(seed))
        have_pool = bool(_YT_KEYS)
    if not have_pool:
        return requests.get(url, params=params, timeout=timeout)
    tried = set()
    last = None
    while True:
        with _YT_KEY_LOCK:
            alive = [k for k in _YT_KEYS
                     if k not in _YT_DEAD_KEYS and k not in tried]
            key = alive[0] if alive else None
        if key is None:
            if last is not None:
                return last
            return requests.get(url, params=params, timeout=timeout)
        tried.add(key)
        p = dict(params)
        p["key"] = key
        r = requests.get(url, params=p, timeout=timeout)
        last = r
        if _yt_resp_is_dead_key(r):
            with _YT_KEY_LOCK:
                _YT_DEAD_KEYS.add(key)
                left = sum(1 for k in _YT_KEYS if k not in _YT_DEAD_KEYS)
            mask = (key[:6] + "..." + key[-4:]) if len(key) > 12 else key
            if left:
                print(f"[API KEY] Key {mask} het quota/khong hop le "
                      f"-> tu chuyen sang key tiep theo (con {left} key)")
            else:
                print(f"[API KEY] Key {mask} het quota/khong hop le "
                      f"-> DA HET SACH KEY trong danh sach!")
            continue
        return r



def fetch_yt_metadata(api_key, ids):
    """Lay title + thoi luong nhieu video bang YouTube Data API v3.
    Tra ({id: {title, duration}}, so_lan_goi_api). Het quota thi bao ro."""
    meta = {}
    calls = 0
    for i in range(0, len(ids), 50):
        batch = ids[i:i + 50]
        r = _yt_get("https://www.googleapis.com/youtube/v3/videos",
                         params={"part": "snippet,contentDetails",
                                 "id": ",".join(batch), "key": api_key},
                         timeout=25)
        calls += 1
        if r.status_code != 200:
            detail = ""
            try:
                detail = r.json().get("error", {}).get("message", "")
            except Exception:  # noqa
                pass
            if r.status_code == 403 and "quota" in (detail + r.text).lower():
                raise RuntimeError("API key đã hết quota hôm nay (mặc định "
                                   "10.000 units/ngày) - mai quay lại hoặc dùng key khác")
            raise RuntimeError(f"YouTube API lỗi HTTP {r.status_code}: {detail[:120]}")
        for item in r.json().get("items", []):
            meta[item["id"]] = {
                "title": (item.get("snippet") or {}).get("title", ""),
                "duration": parse_iso8601_duration(
                    (item.get("contentDetails") or {}).get("duration", "")),
            }
    return meta, calls


def check_yt_api_key(api_key):
    """Kiểm tra API key YouTube v3 còn dùng được không (tốn 1 quota).
    Tra (True/False, thông báo dễ hiểu)."""
    try:
        r = requests.get("https://www.googleapis.com/youtube/v3/videos",
                         params={"part": "id", "id": "dQw4w9WgXcQ",
                                 "key": api_key},
                         timeout=20)
    except Exception as e:  # noqa
        return False, f"Không gọi được YouTube API: {_short(e)}"
    if r.status_code == 200:
        return True, "✅ API key hợp lệ và quota còn dùng được."
    reason = ""
    try:
        errs = r.json().get("error", {}).get("errors", [])
        reason = errs[0].get("reason", "") if errs else ""
    except Exception:  # noqa
        pass
    if reason in ("quotaExceeded", "dailyLimitExceeded"):
        return False, "Key đúng nhưng đã HẾT quota hôm nay (reset vào ngày mai)."
    if reason == "keyInvalid":
        return False, "API key không hợp lệ - kiểm tra lại key đã dán."
    if reason == "accessNotConfigured":
        return False, "Project chưa bật 'YouTube Data API v3' - vào Google Cloud bật lên trước."
    return False, f"API trả lỗi HTTP {r.status_code} ({reason or 'không rõ'})"


def _title_file_stem(title, vid):
    """Ten file tai ve theo TIEU DE GOC cua video: bo hashtag, bo ky
    tu cam cua Windows va '%' (ky tu dac biet cua yt-dlp outtmpl),
    cat 80 ky tu; khong con gi thi lui ve video id."""
    s = _strip_hashtags(title or "")
    s = s.replace("%", "")
    s = re.sub(r'[\\/:*?"<>|]', "_", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    s = s[:80].rstrip(" .")
    return s or vid


_dl_name_lock = threading.Lock()
_dl_claimed = set()


def _dl_file_path(out_dir, vid, title):
    """Chon duong dan file se tai ve cho vid, tranh 2 video trung
    tieu de ghi de len nhau (ke ca khi tai song song nhieu luong):
    file muc tieu da co chu khac (theo cache) hoac dang bi tai boi
    video khac thi them hau to [<vid>]."""
    stem = _title_file_stem(title, vid)
    out = Path(out_dir)
    cache = _load_yt_cache()
    owner = None
    for k, v in cache.items():
        if isinstance(v, dict) and v.get("file") == f"{stem}.mp4":
            owner = k
            break
    cand = out / f"{stem}.mp4"
    with _dl_name_lock:
        taken = str(cand) in _dl_claimed
        if not taken and cand.exists() and owner != vid:
            taken = True
        if taken:
            cand = out / f"{stem} [{vid}].mp4"
        _dl_claimed.add(str(cand))
    return cand


def _release_dl_path(path):
    with _dl_name_lock:
        _dl_claimed.discard(str(path))


def _find_downloaded(out_dir, vid, cache=None):
    """Tim file da tai cua 1 video: theo ten file ghi trong cache
    (ten theo tieu de), khong co thi thu ten cu <vid>.mp4.
    Tra Path hoac None."""
    if cache is None:
        cache = _load_yt_cache()
    folder = Path(out_dir)
    entry = cache.get(vid)
    if isinstance(entry, dict) and entry.get("file"):
        p = folder / entry["file"]
        if p.exists():
            return p
    legacy = folder / f"{vid}.mp4"
    if legacy.exists():
        return legacy
    return None


def download_one_yt(video_id, out_dir, progress_cb=None, title=None):
    """Tai 1 video bang yt-dlp ve out_dir, ten file theo TIEU DE GOC
    cua video (da bo hashtag); chua biet title thi ten file =
    <video_id>.mp4. Tra (True, duong_dan_file) hoac (False, loi)."""
    try:
        import yt_dlp
    except ImportError:
        return False, "chưa cài yt-dlp - chạy lệnh: pip install yt-dlp"
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    final = _dl_file_path(out, video_id, title)
    stem = final.stem

    def hook(d):
        if progress_cb and d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            if total:
                progress_cb(int(done * 100 / total))

    opts = {"outtmpl": str(out / f"{stem}.%(ext)s"),
            "format": "bv*[ext=mp4][height<=1080]+ba[ext=m4a]/b[ext=mp4][height<=1080]/best",
            "merge_output_format": "mp4",
            "retries": 5, "fragment_retries": 5, "extractor_retries": 3,
            "socket_timeout": 30, "noplaylist": True,
            "quiet": True, "no_warnings": True,
            "progress_hooks": [hook]}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    except Exception as e:  # noqa
        return False, _short(e)
    finally:
        _release_dl_path(final)
    if final.exists() and final.stat().st_size > 0:
        return True, str(final)
    cands = [f for f in out.iterdir()
             if f.is_file() and f.name.startswith(stem + ".")]
    cands.sort(key=lambda f: -f.stat().st_size)
    if cands and cands[0].stat().st_size > 0:
        return True, str(cands[0])
    return False, "tải xong nhưng không thấy file"


def _mode_from_channel_url(text):
    """Nhận loại video từ đuôi tab trong link kênh: .../shorts -> 'shorts',
    .../videos -> 'long', không có đuôi tab -> None (dùng nút chọn tay)."""
    t = (text or "").lower()
    if "/shorts" in t:
        return "shorts"
    if "/videos" in t:
        return "long"
    return None


def _extract_yt_handle(text):
    """Lấy @handle từ link kênh / chuỗi '@handle...': handle
    YouTube có thể là chữ Ả-rập / Trung / Nga... (không chỉ
    ASCII) và có thể đang percent-encode khi copy từ thanh địa
    chỉ trình duyệt -> unquote trước. Trả handle (không kèm
    '@') hoặc None."""
    t = (text or "").strip()
    m = re.search(r"@([^/\s?#]+)", t)
    if not m:
        return None
    h = m.group(1)
    try:
        from urllib.parse import unquote
        h = unquote(h)
    except Exception:  # noqa
        pass
    return h or None


def _channel_url_key(text, mode):
    """Khoa chong trung cho 1 link kenh + loai video, chuan hoa tu URL:
    @handle (khong phan biet hoa thuong), /channel/UC..., /user/...,
    /c/... -> '<dinh danh>|<mode>'. UC id giu nguyen hoa thuong."""
    t = (text or "").strip()
    m = re.search(r"/channel/(UC[A-Za-z0-9_-]{22})", t)
    if m:
        ident = m.group(1)
    elif re.fullmatch(r"UC[A-Za-z0-9_-]{22}", t):
        ident = t
    else:
        _h = _extract_yt_handle(t)
        mu = re.search(r"/user/([A-Za-z0-9_-]+)", t)
        mc = re.search(r"/c/([A-Za-z0-9._-]+)", t)
        if _h:
            ident = "@" + _h.lower()
        elif mu:
            ident = "user:" + mu.group(1).lower()
        elif mc:
            ident = "c:" + mc.group(1).lower()
        elif t.startswith("@"):
            ident = t.lower()
        else:
            ident = re.sub(r"\s+", "", t.lower())
    return f"{ident}|{mode}"


def _query_from_search_input(text):
    """Lay tu khoa tu link search YouTube (results?search_query=...);
    nguoi dung go thang tu khoa thi tra nguyen van; link YouTube khong
    phai link search thi tra ''."""
    t = (text or "").strip()
    if not t:
        return ""
    m = re.search(r"[?&]search_query=([^&]+)", t)
    if m:
        from urllib.parse import unquote_plus
        return unquote_plus(m.group(1)).strip()
    if t.startswith("http") and "youtube" in t:
        return ""
    return t


def search_channels_from_videos(api_key, query, limit, max_pages=12):
    """Quet cac VIDEO cua trang ket qua tim kiem (search.list,
    type=video; 100 quota/trang) va gom cac KENH khac nhau dung sau
    cac video do. Dung khi du `limit` kenh, het trang ket qua, hoac
    het max_pages trang. Tra [(channel_id, channel_title)] theo thu
    tu xuat hien."""
    out = []
    seen = set()
    token = None
    pages = 0
    while len(out) < limit and pages < max_pages:
        params = {"part": "snippet", "type": "video", "q": query,
                  "maxResults": 50, "key": api_key}
        if token:
            params["pageToken"] = token
        r = _yt_get("https://www.googleapis.com/youtube/v3/search",
                         params=params, timeout=25)
        if r.status_code != 200:
            raise RuntimeError(f"Search API lỗi HTTP {r.status_code}")
        js = r.json()
        pages += 1
        for it in js.get("items", []):
            sn = it.get("snippet") or {}
            cid = sn.get("channelId") or ""
            if cid and cid not in seen:
                seen.add(cid)
                out.append((cid, sn.get("channelTitle", "")))
                if len(out) >= limit:
                    break
        token = js.get("nextPageToken")
        if not token:
            break
    return out


def fetch_channel_handles(api_key, channel_ids):
    """Tra {channel_id: (handle_hoac_None, title)} bang channels.list
    (1 quota / toi da 50 kenh)."""
    res = {}
    for i in range(0, len(channel_ids), 50):
        batch = channel_ids[i:i + 50]
        r = _yt_get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={"part": "snippet", "id": ",".join(batch),
                    "key": api_key}, timeout=25)
        if r.status_code != 200:
            raise RuntimeError(f"Channels API lỗi HTTP {r.status_code}")
        for it in r.json().get("items", []):
            sn = it.get("snippet") or {}
            res[it.get("id")] = (sn.get("customUrl") or None,
                                 sn.get("title", ""))
    return res


def resolve_channel_id(api_key, text):
    """URL/handle kênh -> channel ID (UC...). Nhận link @handle,
    /channel/UC..., /user/... hoặc ID UC thô. Tốn 1 quota khi phải tra."""
    t = (text or "").strip()
    m = re.search(r"/channel/(UC[A-Za-z0-9_-]{22})", t)
    if m:
        return m.group(1)
    if re.fullmatch(r"UC[A-Za-z0-9_-]{22}", t):
        return t
    params = None
    _h = _extract_yt_handle(t)
    mu = re.search(r"/user/([A-Za-z0-9_-]+)", t)
    if _h:
        params = {"part": "id", "forHandle": "@" + _h, "key": api_key}
    elif mu:
        params = {"part": "id", "forUsername": mu.group(1), "key": api_key}
    elif t.startswith("@"):
        params = {"part": "id", "forHandle": t, "key": api_key}
    if not params:
        raise RuntimeError("Không nhận dạng được link kênh - hãy dán link dạng "
                           "youtube.com/@tenkenh hoặc youtube.com/channel/UC...")
    r = _yt_get("https://www.googleapis.com/youtube/v3/channels",
                     params=params, timeout=25)
    if r.status_code != 200:
        raise RuntimeError(f"Tra kênh lỗi HTTP {r.status_code}")
    items = r.json().get("items", [])
    if not items:
        raise RuntimeError("Không tìm thấy kênh này (sai handle?)")
    return items[0]["id"]


def _yt_playlist_id(channel_id, mode):
    """Playlist ID suy ra từ channel ID: UU = tất cả, UUSH = Shorts,
    UULF = video dài. Lật các playlist này tốn 1 quota / 50 link."""
    suffix = channel_id[2:]
    if mode == "shorts":
        return "UUSH" + suffix
    if mode == "long":
        return "UULF" + suffix
    return "UU" + suffix


def _fetch_playlist_page(api_key, playlist_id, page_token):
    params = {"part": "contentDetails", "playlistId": playlist_id,
              "maxResults": "50", "key": api_key}
    if page_token:
        params["pageToken"] = page_token
    r = _yt_get("https://www.googleapis.com/youtube/v3/playlistItems",
                     params=params, timeout=25)
    if r.status_code != 200:
        return None, None, r.status_code
    js = r.json()
    ids = [(it.get("contentDetails") or {}).get("videoId")
           for it in js.get("items", [])]
    return [i for i in ids if i], js.get("nextPageToken"), 200


def fetch_channel_video_ids(api_key, channel_id, mode, limit, progress=None):
    """Lấy tối đa `limit` video ID của kênh theo đúng TAB của kênh:
    mode 'shorts' đọc playlist Shorts riêng (UUSH - chính là nội dung tab
    /shorts), mode 'long' đọc playlist video dài riêng (UULF - tab
    /videos). KHÔNG phân loại bằng thời lượng. Tốn 1 quota / 50 link."""
    limit = max(1, int(limit))
    playlist = _yt_playlist_id(channel_id, mode)
    ids, token, calls = [], None, 0
    label = "Shorts" if mode == "shorts" else "video dài"
    while len(ids) < limit:
        page, token, status = _fetch_playlist_page(api_key, playlist, token)
        calls += 1
        if page is None:
            if not ids:
                raise RuntimeError(
                    f"Không đọc được danh sách {label} của kênh (HTTP {status}) "
                    f"- kiểm tra lại link kênh / API key")
            break
        if not page:
            break  # kênh không có video loại này
        ids.extend(page)
        if progress:
            progress(len(ids))
        if not token:
            break
    return ids[:limit], calls


# ==== Tab UPLOAD Acc/Kenh (v3.84): kenh Shorts > 200 -> file tong,
# gan kenh 1-1 cho acc, moi acc 1 file Shorts rieng ====
AKC_MIN_SHORTS = 200  # chi lay kenh co so video Shorts > 200
AKC_MASTER_PATH = APP_DIR / "yt_channels_master.txt"  # file TONG cac kenh dat chuan
AKC_ACC_DIR = APP_DIR / "yt_acc_shorts"  # thu muc file Shorts theo tung acc TikTok
AKC_ASSIGNED_PATH = APP_DIR / "yt_channels_assigned.txt"  # kenh da gan cho acc (da tru khoi file tong)
AKC_POOL_PATH = APP_DIR / "yt_channels_pool.txt"  # kenh DU BI trong pool (tu acc xoa / acc doi kenh) cho ke nhiem


def count_playlist_videos(api_key, channel_id, mode):
    """Dem TONG so video trong playlist cua kenh (UUSH = Shorts,
    UULF = video dai) bang pageInfo.totalResults - ton dung 1 quota.
    Loi HTTP (kenh khong co playlist nay) -> None."""
    playlist = _yt_playlist_id(channel_id, mode)
    try:
        r = _yt_get(
            "https://www.googleapis.com/youtube/v3/playlistItems",
            params={"part": "id", "playlistId": playlist,
                    "maxResults": "1", "key": api_key}, timeout=25)
        if r.status_code != 200:
            return None
        return int((r.json().get("pageInfo") or {}).get("totalResults")
                   or 0)
    except Exception:  # noqa
        return None


class AppUpload:
    def __init__(self, root):
        self.root = root
        root.title(f"TikTok Upload Tool - Account Management {TOOL_VERSION}")
        root.geometry("1760x920")

        self.logq = queue.Queue()
        self._log_buffer = []        # toan bo log chay nen (cua so Log doc tu day)
        self._log_win = None         # cua so Log tien trinh dang mo (neu co)
        self._log_win_text = None
        self.uiq = queue.Queue()  # ham cap nhat UI tu luong phu -> main thread chay
        self.busy = False
        self.all_accounts = []
        self.selected_accounts = []
        self.videos = []
        self.jobs = []
        self.job_items = {}
        self.groups = set()  # Danh sách nhóm

        # Redirect stdout
        sys.stdout = LogStream(self.logq)
        print(f"[OK] Đang chạy TikTok Upload Tool {TOOL_VERSION} (bản đầy đủ tính năng)")

        # Variables
        self.folder_var = tk.StringVar()
        self.group_filter = tk.StringVar(value="All")
        self.threads_var = tk.IntVar(value=3)
        self.videos_per_acc_var = tk.IntVar(value=5)
        self.num_load_videos_var = tk.IntVar(value=10)  # NEW: số video load
        _st = _load_settings()
        self.gpm_dir_var = tk.StringVar(value=_st.get("gpm_profile_dir", r"C:\profileGPM"))
        self.clean_cache_var = tk.BooleanVar(value=_st.get("auto_clean_cache", True))
        self.proxy_file_var = tk.StringVar(value=_st.get("proxy_file", str(APP_DIR / "proxies.txt")))
        self.checker_file_var = tk.StringVar(value=_st.get("checker_cookie_file", str(APP_DIR / "cookies_check.txt")))
        self.scan_threads_var = tk.IntVar(value=5)
        self.recent_videos_var = tk.IntVar(value=5)
        self.scanning = False
        self.alogin_threads_var = tk.IntVar(value=int(_st.get("alogin_threads", 3) or 3))
        self.alogin_delay_var = tk.IntVar(value=int(_st.get("alogin_delay", 5) or 5))
        self.alogin_running = False
        self.yt_links_file_var = tk.StringVar(value=_st.get("yt_links_file", str(APP_DIR / "yt_links.txt")))
        self.yt_api_keys = _parse_yt_keys(
            _st.get("yt_api_keys") or _st.get("yt_api_key", ""))
        yt_keys_set(self.yt_api_keys)
        self.yt_api_key_var = tk.StringVar(
            value=self.yt_api_keys[0] if self.yt_api_keys else "")
        self.yt_key_info_var = tk.StringVar()
        self._yt_key_info_refresh()
        self.yt_threads_var = tk.IntVar(value=3)
        self.tele_token_var = tk.StringVar(value=_st.get("tele_token", ""))
        self.tele_chat_var = tk.StringVar(value=_st.get("tele_chat_id", ""))
        self.hide_browser_var = tk.BooleanVar(value=bool(_st.get("hide_browser", False)))
        self.scan_view_browser_var = tk.BooleanVar(value=bool(_st.get("scan_view_browser", False)))
        self.stop_requested = False
        self.cookie_exporting = False
        self.yt_downloading = False
        self.yt_channel_history = list(_st.get("yt_channel_history") or [])
        self.yt_search_var = tk.StringVar(value=_st.get("yt_search", ""))
        self.yt_search_count_var = tk.IntVar(value=int(_st.get("yt_search_count", 20) or 20))
        self.session_checking = False
        self.yt_searching = False
        self.yt_mode_var = tk.StringVar(value="shorts")
        self.yt_count_var = tk.IntVar(value=100)
        self.yt_per_acc_var = tk.IntVar(value=int(_st.get("yt_per_acc", 5)))
        self.yt_up_threads_var = tk.IntVar(value=int(_st.get("yt_up_threads", 2)))
        self.up_delay_var = tk.IntVar(value=int(_st.get("up_delay", 0)))
        self.yt_delay_var = tk.IntVar(value=int(_st.get("yt_delay", 0)))
        self.yt_list_info_var = tk.StringVar(value="Chưa lấy list")
        self.yt_fetched_ids = []
        # Phan gan link -> account duoc luu trong tool_settings.json,
        # mo lai tool la con nguyen (khoi phai gan lai)
        self.yt_assignments = {a: list(v) for a, v in
                               (_st.get("yt_assignments", {}) or {}).items() if v}
        # --- Tab UPLOAD Acc/Kênh (v3.84): gán kênh 1-1 cho từng acc ---
        self.yt_acc_channels = {a: dict(v) for a, v in
                                (_st.get("yt_acc_channels", {}) or {}).items()
                                if isinstance(v, dict)}
        # Pool kênh BẢO LƯU chờ kế nhiệm (v3.90): kênh của acc đã bị
        # xoá khỏi bảng (hoặc acc đổi kênh) - acc mới gán vào sẽ nhận
        # kênh này + file link còn lại (POOL_<channel_id>.txt) để up
        # tiếp, không trùng video acc cũ đã up, không quét lại.
        self.yt_channel_pool = [dict(p) for p in
                                (_st.get("yt_channel_pool", []) or [])
                                if isinstance(p, dict)]
        self.akc_search_var = tk.StringVar(value=_st.get("akc_search", ""))
        self.akc_search_count_var = tk.IntVar(
            value=int(_st.get("akc_search_count", 100) or 100))
        self.akc_per_acc_var = tk.IntVar(
            value=int(_st.get("akc_per_acc", 5) or 5))
        self.akc_threads_var = tk.IntVar(
            value=int(_st.get("akc_threads", 3) or 3))
        self.akc_delay_var = tk.IntVar(
            value=int(_st.get("akc_delay", 0) or 0))
        self.akc_scan_threads_var = tk.IntVar(
            value=int(_st.get("akc_scan_threads", 5) or 5))
        self.akc_master_info_var = tk.StringVar(value="")
        self.akc_info_var = tk.StringVar(value="")
        self.akc_searching = False
        self.akc_scanning = False
        self._akc_file_lock = threading.Lock()
        self._akc_state_lock = threading.Lock()
        self.yt_fetching = False
        self.pipeline_running = False
        self.yt_link_rows = []
        self.yt_link_status = {}  # vid -> "ok" (Upload thanh cong) / "fail" (Upload loi)
        self.yt_list_name_var = tk.StringVar(value="")
        self.yt_list_pick_var = tk.StringVar(value="")
        self.yt_link_info_var = tk.StringVar(value="0 link")
        self.yt_folder_var = tk.StringVar(value=_st.get("yt_folder", ""))

        self._build_ui()
        self._load_accounts()
        self._update_log()

    def _build_ui(self):
        """Xây dựng giao diện."""
        # ---- Style: theme Windows native + font Segoe UI cho de nhin ----
        try:
            style = ttk.Style(self.root)
            for _theme in ("vista", "xpnative", "clam"):
                if _theme in style.theme_names():
                    style.theme_use(_theme)
                    break
            style.configure("TLabel", font=("Segoe UI", 10))
            style.configure("TButton", font=("Segoe UI", 10), padding=4)
            style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=5)
            style.configure("Treeview", font=("Segoe UI", 10), rowheight=24)
            style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
            style.configure("TLabelframe.Label", font=("Segoe UI", 10, "bold"))
            style.configure("TNotebook.Tab", font=("Segoe UI", 11, "bold"),
                            padding=(16, 7))
            style.map("TNotebook.Tab",
                      background=[("selected", "#d9ead3")],
                      foreground=[("selected", "#14531d")])
        except Exception:  # noqa
            pass
        # (v3.7) Hang Folder Video + Profile GPM da duoc DOI xuong dau cot
        # phai, ngay tren Upload Manager - xem phan right_frame ben duoi.
        # Cot trai tu tren xuong chi con Account Manager.

        # ---- 2 COLUMNS: LEFT (Accounts) + RIGHT (Upload) ----
        main = ttk.PanedWindow(self.root, orient="horizontal")
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # ---- LEFT: Account Management ----
        left_frame = ttk.LabelFrame(main, text="Account Manager", width=1150)
        main.add(left_frame, weight=7)

        # Group filter + manage
        filter_frame = ttk.Frame(left_frame)
        filter_frame.pack(fill="x", padx=5, pady=5)
        ttk.Label(filter_frame, text="Group:").pack(side="left")
        self.group_combo = ttk.Combobox(filter_frame, textvariable=self.group_filter, width=15, state="readonly")
        self.group_combo.pack(side="left", padx=5)
        self.group_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_account_table())

        ttk.Button(filter_frame, text="+ Tạo Group", command=self._create_group).pack(side="left", padx=5)
        ttk.Button(filter_frame, text="✕ Xoá Group", command=self._delete_group).pack(side="left", padx=2)
        ttk.Button(filter_frame, text="✏️ Sửa tên Group", command=self._rename_group).pack(side="left", padx=2)
        self.acc_sel_label = ttk.Label(filter_frame,
                                       text="Đã chọn: 0 / 0 tài khoản",
                                       font=("Segoe UI", 10, "bold"))
        self.acc_sel_label.pack(side="right", padx=6)

        # Thanh quet info: chay an bang cookie, da luong, xoay proxy
        scan_frame = ttk.Frame(left_frame)
        scan_frame.pack(fill="x", padx=5, pady=(0, 5))
        ttk.Label(scan_frame, text="Luồng quét:").pack(side="left")
        ttk.Spinbox(scan_frame, from_=1, to=50, textvariable=self.scan_threads_var,
                    width=5).pack(side="left", padx=4)
        ttk.Label(scan_frame, text="Video mới nhất:").pack(side="left", padx=(10, 0))
        ttk.Spinbox(scan_frame, from_=1, to=100, textvariable=self.recent_videos_var,
                    width=5).pack(side="left", padx=4)
        ttk.Button(scan_frame, text="🔍 Quét Info", style="Accent.TButton",
                   command=self._start_scan).pack(side="left", padx=10)
        ttk.Label(scan_frame, text="(chọn account để quét riêng, không chọn = quét tất cả)").pack(side="left")

        # Tuy chon: acc nao quet an khong ra view thi mo profile GPM
        # cua chinh acc do de lay view tu trang profile that (cham hon)
        scan2_frame = ttk.Frame(left_frame)
        scan2_frame.pack(fill="x", padx=5, pady=(0, 5))
        ttk.Checkbutton(scan2_frame, text="Quét VIEW qua trình duyệt GPM",
                        variable=self.scan_view_browser_var).pack(side="left")

        # Hang tim account theo list ID dan vao (loc bang account)
        self.search_ids = None
        search_frame = ttk.Frame(left_frame)
        search_frame.pack(fill="x", padx=5, pady=(0, 5))
        ttk.Label(search_frame, text="🔎 Tìm account:").pack(side="left")
        self.search_text = tk.Text(search_frame, width=34, height=3,
                                   font=("Consolas", 9))
        self.search_text.pack(side="left", padx=4)
        ttk.Button(search_frame, text="🔎 Tìm",
                   command=self._search_accounts).pack(side="left", padx=2)
        ttk.Button(search_frame, text="✖ Bỏ tìm",
                   command=self._clear_search).pack(side="left", padx=2)
        ttk.Label(search_frame, text="(dán list ID, mỗi dòng 1 acc - bảng lọc ra đúng các acc đó)").pack(side="left")

        # Hang nhap file proxy + cookie trung gian (ngay duoi nut Quet Info)
        scan2_frame = ttk.Frame(left_frame)
        scan2_frame.pack(fill="x", padx=5, pady=(0, 5))
        ttk.Label(scan2_frame, text="File proxy:").pack(side="left")
        ttk.Entry(scan2_frame, textvariable=self.proxy_file_var, width=34).pack(side="left", padx=4)
        ttk.Button(scan2_frame, text="Browse", command=self._pick_proxy_file).pack(side="left", padx=2)
        ttk.Label(scan2_frame, text="Cookie trung gian:").pack(side="left", padx=(14, 0))
        ttk.Entry(scan2_frame, textvariable=self.checker_file_var, width=34).pack(side="left", padx=4)
        ttk.Button(scan2_frame, text="Browse", command=self._pick_checker_file).pack(side="left", padx=2)
        ttk.Label(scan2_frame, text="(mỗi file 1 dòng, tự xoay vòng)").pack(side="left", padx=(4, 0))

        # Account table - treeview với right-click
        acc_table_frame = ttk.Frame(left_frame)
        acc_table_frame.pack(fill="both", expand=True, padx=5, pady=5)

        acc_scroll = ttk.Scrollbar(acc_table_frame)
        acc_scroll.pack(side="right", fill="y")
        acc_xscroll = ttk.Scrollbar(acc_table_frame, orient="horizontal")
        acc_xscroll.pack(side="bottom", fill="x")

        acc_cols = ("ID", "View30d", "Follow", "Like", "TView", "TVideo",
                    "GanKenh", "Country", "Email", "MailBackup", "Status", "ALogin",
                    "Cookie", "Note")
        self.acc_tree = ttk.Treeview(
            acc_table_frame,
            columns=acc_cols,
            height=20,
            selectmode="extended",
            yscrollcommand=acc_scroll.set,
            xscrollcommand=acc_xscroll.set
        )
        acc_scroll.config(command=self.acc_tree.yview)
        acc_xscroll.config(command=self.acc_tree.xview)
        self.acc_tree.bind("<<TreeviewSelect>>",
                           lambda e: self._update_acc_sel_label())

        self.acc_tree.column("#0", width=42, anchor="center")
        self.acc_tree.heading("#0", text="STT")
        self.acc_tree.column("ID", anchor="w", width=120)
        self.acc_tree.column("View30d", anchor="center", width=72)
        self.acc_tree.column("Follow", anchor="center", width=66)
        self.acc_tree.column("Like", anchor="center", width=66)
        self.acc_tree.column("TView", anchor="center", width=72)
        self.acc_tree.column("TVideo", anchor="center", width=56)
        self.acc_tree.column("GanKenh", anchor="center", width=82)
        self.acc_tree.column("Country", anchor="center", width=42)
        self.acc_tree.column("Email", anchor="w", width=78)
        self.acc_tree.column("MailBackup", anchor="w", width=78)
        self.acc_tree.column("Status", anchor="center", width=62)
        self.acc_tree.column("ALogin", anchor="center", width=118)
        self.acc_tree.column("Cookie", anchor="w", width=112)
        self.acc_tree.column("Note", anchor="w", width=200, stretch=True)

        self.acc_tree.heading("ID", text="ID")
        self.acc_tree.heading("View30d", text="View 30d")
        self.acc_tree.heading("Follow", text="Follow")
        self.acc_tree.heading("Like", text="Like")
        self.acc_tree.heading("TView", text="T.view")
        self.acc_tree.heading("TVideo", text="T.Video")
        self.acc_tree.heading("GanKenh", text="Đã Gán Kênh")
        self.acc_tree.heading("Country", text="QG")
        self.acc_tree.heading("Email", text="Email")
        self.acc_tree.heading("MailBackup", text="Mail KP")
        self.acc_tree.heading("Status", text="Tình Trạng")
        self.acc_tree.heading("ALogin", text="Auto Login")
        self.acc_tree.heading("Cookie", text="Cookie")
        self.acc_tree.heading("Note", text="📝 Note")
        self._bind_sort(self.acc_tree, "text")

        # To hang xen ke xanh nhat nhu anh mau
        self.acc_tree.tag_configure("oddrow", background="#ffffff")
        self.acc_tree.tag_configure("evenrow", background="#ffffff")
        self.acc_tree.tag_configure("goldrow", background="#ffe97a")
        self.acc_tree.tag_configure("deadrow", background="#f6a6a6")

        self.acc_tree.pack(fill="both", expand=True)

        # Bind Ctrl+A, Ctrl+Click, Right-Click
        self.acc_tree.bind("<Control-a>", self._select_all_accounts)
        self.acc_tree.bind("<Control-Button-1>", self._ctrl_click_select)
        self.acc_tree.bind("<Button-3>", self._right_click_menu)
        self.acc_tree.bind("<Double-Button-1>", self._on_acc_double_click)

        # Buttons
        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(fill="x", padx=5, pady=5)
        ttk.Button(btn_frame, text="Add Account", command=self._add_account).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="🍪 Xuất Cookie", command=self._export_cookies).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="📤 Xuất thông tin", command=self._export_info_dialog).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="📝 Note", command=self._edit_note).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="🧮 Máy tính", command=self._open_calculator).pack(side="left", padx=2)
        ttk.Checkbutton(btn_frame, text="Ẩn trình duyệt",
                        variable=self.hide_browser_var).pack(side="left", padx=6)

        # ---- RIGHT: Upload Management ----
        right_frame = ttk.LabelFrame(main, text="Upload Manager")
        main.add(right_frame, weight=3)
        # Ti le Account Manager 70% / Upload Manager 30% de bang account
        # du rong thay het cac cot (dat sash sau khi cua so da ve xong)
        try:
            self.root.after(300, lambda: main.sashpos(
                0, int(main.winfo_width() * 0.7)))
        except Exception:  # noqa
            pass

        # Khung Auto Login: 1 nut chay autologin.gpmlaunch, 1 nut mo Login.xlsx
        login_frame = ttk.LabelFrame(right_frame, text="🔑 Auto Login TAT")
        login_frame.pack(fill="x", padx=5, pady=(5, 2))
        al_row1 = ttk.Frame(login_frame)
        al_row1.pack(fill="x", padx=5, pady=(5, 2))
        ttk.Button(al_row1, text="▶ Chạy Auto Login", style="Accent.TButton",
                   command=self._run_autologin).pack(side="left", padx=(0, 6))
        ttk.Label(al_row1, text="Luồng:").pack(side="left")
        ttk.Spinbox(al_row1, from_=1, to=20, width=4,
                    textvariable=self.alogin_threads_var).pack(side="left", padx=3)
        ttk.Label(al_row1, text="Delay mở (s):").pack(side="left", padx=(8, 0))
        ttk.Spinbox(al_row1, from_=0, to=300, width=4,
                    textvariable=self.alogin_delay_var).pack(side="left", padx=3)
        ttk.Button(al_row1, text="⏹ STOP", command=self._stop_all_runs).pack(side="left", padx=8)
        ttk.Button(al_row1, text="⬆ Update",
                   command=self._check_update).pack(side="right", padx=4)
        # Hang Profile GPM (v4.01: chuyen tu tab Upload Offline
        # len khung Auto Login - ngay duoi hang Chay Auto Login,
        # luon thay o ca 3 tab)
        gpm_frame = ttk.Frame(login_frame)
        gpm_frame.pack(fill="x", padx=5, pady=(2, 0))
        ttk.Label(gpm_frame, text="Profile GPM:").pack(side="left", padx=5)
        ttk.Entry(gpm_frame, textvariable=self.gpm_dir_var, width=30).pack(side="left", padx=5)
        ttk.Button(gpm_frame, text="Browse", command=self._pick_gpm_dir).pack(side="left", padx=2)
        ttk.Button(gpm_frame, text="📂", width=3,
                   command=lambda: self._open_folder_of(self.gpm_dir_var)).pack(side="left", padx=2)
        al_row2 = ttk.Frame(login_frame)
        al_row2.pack(fill="x", padx=5, pady=(0, 5))
        ttk.Label(al_row2, text="(chọn account ở bảng trái, Ctrl+A = tất cả; login xong tự xuất cookie vào bảng)").pack(side="left")
        tk.Button(al_row2, text="Buffsieutoc", fg="blue",
                  activeforeground="blue", font=("Segoe UI", 9, "bold"),
                  cursor="hand2",
                  command=lambda: webbrowser.open("https://buffsieutoc.shop/")).pack(side="left", padx=5, pady=5)
        tk.Button(al_row2, text="Clonetiktok", fg="blue",
                  activeforeground="blue", font=("Segoe UI", 9, "bold"),
                  cursor="hand2",
                  command=lambda: webbrowser.open("https://clonetiktok.shop/")).pack(side="left", padx=5, pady=5)

        # Khung tai video YouTube Shorts: file list link + API v3 + yt-dlp
        # Notebook 2 tab cho gon giao dien: ⬇ YouTube / 📤 Upload.
        # (Khung Auto Login o tren va Log o day cua so giu co dinh, luon thay.)
        # Khung Telegram: nhan bao cao account loi sau moi dot upload
        tele_frame = ttk.LabelFrame(right_frame, text="Telegram - báo account lỗi upload")
        tele_frame.pack(fill="x", padx=5, pady=(0, 5))
        tele_row1 = ttk.Frame(tele_frame)
        tele_row1.pack(fill="x", padx=5, pady=(4, 2))
        ttk.Label(tele_row1, text="🤖 Bot Token:").pack(side="left")
        ttk.Entry(tele_row1, textvariable=self.tele_token_var, width=30,
                  show="*").pack(side="left", padx=4)
        ttk.Button(tele_row1, text="✔ Test", command=self._test_telegram).pack(side="left", padx=2)
        ttk.Label(tele_row1, text="Chat ID:").pack(side="left", padx=(10, 0))
        ttk.Entry(tele_row1, textvariable=self.tele_chat_var, width=30).pack(side="left", padx=4)
        ttk.Button(tele_row1, text="Lấy Chat ID", command=self._fetch_chat_id).pack(side="left", padx=2)
        # Hang API Key YouTube v3 (v3.96: chuyen tu tab Chung File
        # xuong duoi hang Bot Token - luon thay, ca 3 tab dung chung 1 key)
        tele_row2 = ttk.Frame(tele_frame)
        tele_row2.pack(fill="x", padx=5, pady=(2, 4))
        ttk.Label(tele_row2, text="🔑 API Key v3:").pack(side="left")
        ttk.Entry(tele_row2, textvariable=self.yt_api_key_var, width=36).pack(side="left", padx=4)
        ttk.Button(tele_row2, text="💾 Lưu Key", command=self._save_api_key).pack(side="left", padx=2)
        ttk.Button(tele_row2, text="✔ Test Key", command=self._test_api_key).pack(side="left", padx=2)
        ttk.Button(tele_row2, text="🔑 DS Key", command=self._edit_api_keys).pack(side="left", padx=2)
        ttk.Label(tele_row2, textvariable=self.yt_key_info_var).pack(side="left", padx=4)

        self.notebook = ttk.Notebook(right_frame)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)
        up_tab = ttk.Frame(self.notebook)
        self.notebook.add(up_tab, text="🔵 Upload Offline")
        yt_tab = ttk.Frame(self.notebook)
        self.notebook.add(yt_tab, text="🟢 Upload Chung File")
        self.yt_tab = yt_tab
        self.up_tab = up_tab
        # Tab MOI (v3.84): UPLOAD Acc/Kênh - luồng gán kênh 1-1 cho acc,
        # chạy song song, KHÔNG thay thế các tab cũ.
        akc_tab = ttk.Frame(self.notebook)
        self.notebook.add(akc_tab, text="🟣 Upload Acc/Kênh")
        self.akc_tab = akc_tab
        self._build_akc_tab(akc_tab)

        yt_frame = ttk.Frame(yt_tab)
        yt_frame.pack(fill="both", expand=True)
        yt_row0 = ttk.Frame(yt_frame)
        yt_row0.pack(fill="x", padx=5, pady=(5, 2))
        ttk.Label(yt_row0, text="Folder lưu video:").pack(side="left")
        ttk.Entry(yt_row0, textvariable=self.yt_folder_var, width=28).pack(side="left", padx=4)
        ttk.Button(yt_row0, text="Browse", command=self._pick_yt_folder).pack(side="left", padx=2)
        ttk.Button(yt_row0, text="📂", width=3,
                   command=lambda: self._open_folder_of(self.yt_folder_var)).pack(side="left", padx=2)
        ttk.Separator(yt_frame, orient="horizontal").pack(fill="x", padx=5, pady=4)
        yt_row4 = ttk.Frame(yt_frame)
        yt_row4.pack(fill="x", padx=5, pady=2)
        ttk.Label(yt_row4, text="Link kênh:").pack(side="left", anchor="n")
        self.yt_channel_text = tk.Text(yt_row4, width=46, height=4)
        self.yt_channel_text.pack(side="left", padx=4)
        _old_ch = _load_settings().get("yt_channel", "")
        if _old_ch:
            self.yt_channel_text.insert("1.0", _old_ch)
        ttk.Radiobutton(yt_row4, text="Shorts", value="shorts",
                        variable=self.yt_mode_var).pack(side="left", padx=2)
        ttk.Radiobutton(yt_row4, text="Video dài", value="long",
                        variable=self.yt_mode_var).pack(side="left", padx=2)
        yt_row5 = ttk.Frame(yt_frame)
        yt_row5.pack(fill="x", padx=5, pady=2)
        ttk.Label(yt_row5, text="Số video/kênh:").pack(side="left")
        ttk.Spinbox(yt_row5, from_=1, to=5000, textvariable=self.yt_count_var,
                    width=7).pack(side="left", padx=4)
        ttk.Button(yt_row5, text="🔗 Lấy list link", style="Accent.TButton",
                   command=self._start_fetch_channel).pack(side="left", padx=6)
        ttk.Label(yt_row5, textvariable=self.yt_list_info_var).pack(side="left", padx=4)
        yt_row_search = ttk.Frame(yt_frame)
        yt_row_search.pack(fill="x", padx=5, pady=2)
        ttk.Label(yt_row_search, text="Link search:").pack(side="left")
        ttk.Entry(yt_row_search, textvariable=self.yt_search_var, width=40).pack(side="left", padx=4)
        ttk.Label(yt_row_search, text="Số kênh:").pack(side="left")
        ttk.Spinbox(yt_row_search, from_=1, to=500, textvariable=self.yt_search_count_var,
                    width=6).pack(side="left", padx=4)
        ttk.Button(yt_row_search, text="🔍 Quét kênh",
                   command=self._start_search_channels).pack(side="left", padx=6)
        yt_row_opt = ttk.Frame(yt_frame)
        yt_row_opt.pack(fill="x", padx=5, pady=2)
        ttk.Label(yt_row_opt, text="Video/Acc (gán):").pack(side="left")
        ttk.Spinbox(yt_row_opt, from_=1, to=50, width=4,
                    textvariable=self.yt_per_acc_var).pack(side="left", padx=4)
        ttk.Label(yt_row_opt, text="Luồng upload:").pack(side="left", padx=(14, 0))
        ttk.Spinbox(yt_row_opt, from_=1, to=10, width=4,
                    textvariable=self.yt_up_threads_var).pack(side="left", padx=4)
        ttk.Label(yt_row_opt, text="Delay mở trình duyệt (giây):").pack(side="left", padx=(14, 0))
        ttk.Spinbox(yt_row_opt, from_=0, to=300, width=4,
                    textvariable=self.yt_delay_var).pack(side="left", padx=4)
        yt_row6 = ttk.Frame(yt_frame)
        yt_row6.pack(fill="x", padx=5, pady=(2, 5))
        ttk.Button(yt_row6, text="📌 Gán link cho Account",
                   command=self._assign_links).pack(side="left", padx=6)
        ttk.Button(yt_row6, text="▶ START: Tải → Upload → Xoá", style="Accent.TButton",
                   command=self._start_pipeline).pack(side="left", padx=6)
        ttk.Button(yt_row6, text="⏹ STOP", command=self._stop_all_runs).pack(side="left", padx=2)
        ttk.Button(yt_row6, text="🍪 Check cookie",
                   command=self._start_session_check).pack(side="left", padx=2)
        ttk.Checkbutton(yt_row6, text="Tự xoá cache TikTok khi account upload xong",
                        variable=self.clean_cache_var,
                        command=self._persist_settings).pack(side="left", padx=10)

        # ---- Bang List Link (trong tab Upload Online, duoi cac hang cau hinh) ----
        lk_frame = ttk.Frame(yt_tab)
        lk_frame.pack(fill="both", expand=True, padx=5, pady=(2, 5))
        # ---- Tab List Link YouTube: bang quan ly list link da lay ----
        lk_bar1 = ttk.Frame(lk_frame)
        lk_bar1.pack(fill="x", padx=5, pady=(5, 2))
        ttk.Label(lk_bar1, text="Tên list:").pack(side="left")
        ttk.Entry(lk_bar1, textvariable=self.yt_list_name_var, width=20).pack(side="left", padx=4)
        ttk.Button(lk_bar1, text="💾 Lưu file", command=self._save_link_list).pack(side="left", padx=2)
        ttk.Label(lk_bar1, text="List đã lưu:").pack(side="left", padx=(12, 0))
        self.yt_lists_combo = ttk.Combobox(lk_bar1, textvariable=self.yt_list_pick_var,
                                           width=20, state="readonly")
        self.yt_lists_combo.pack(side="left", padx=4)
        ttk.Button(lk_bar1, text="📂 Mở", command=self._open_saved_list).pack(side="left", padx=2)
        ttk.Button(lk_bar1, text="🗑 Xoá list", command=self._delete_saved_list).pack(side="left", padx=2)
        lk_bar2 = ttk.Frame(lk_frame)
        lk_bar2.pack(fill="x", padx=5, pady=2)
        ttk.Label(lk_bar2, text="Luồng tải:").pack(side="left", padx=(2, 0))
        ttk.Spinbox(lk_bar2, from_=1, to=10, textvariable=self.yt_threads_var,
                    width=5).pack(side="left", padx=4)
        ttk.Button(lk_bar2, text="⬇ Tải link đã chọn",
                   command=self._download_selected_links).pack(side="left", padx=2)
        ttk.Button(lk_bar2, text="📌 Gán link đã chọn",
                   command=self._assign_links).pack(side="left", padx=6)
        ttk.Button(lk_bar2, text="🔄 Trạng thái",
                   command=self._refresh_link_table).pack(side="left", padx=2)
        ttk.Button(lk_bar2, text="✏️ Đổi tên",
                   command=lambda: self._open_rename_dialog("links")).pack(side="left", padx=2)
        ttk.Button(lk_bar2, text="🧹 Xoá hashtag",
                   command=self._strip_hashtags_links).pack(side="left", padx=2)
        ttk.Label(lk_bar2, textvariable=self.yt_link_info_var).pack(side="left", padx=8)
        lk_table_frame = ttk.Frame(lk_frame)
        lk_table_frame.pack(fill="both", expand=True, padx=5, pady=5)
        lk_scroll = ttk.Scrollbar(lk_table_frame)
        lk_scroll.pack(side="right", fill="y")
        lk_cols = ("STT", "VideoID", "Kind", "Title", "Duration", "Status", "Account", "Link")
        self.link_tree = ttk.Treeview(lk_table_frame, columns=lk_cols, show="headings",
                                      selectmode="extended",
                                      yscrollcommand=lk_scroll.set)
        lk_scroll.config(command=self.link_tree.yview)
        _lk_w = {"STT": 34, "VideoID": 88, "Kind": 56, "Title": 160, "Duration": 64,
                 "Status": 80, "Account": 140, "Link": 90}
        _lk_h = {"STT": "STT", "VideoID": "Video ID", "Kind": "Loại", "Title": "Tiêu đề",
                 "Duration": "Thời lượng", "Status": "Trạng thái",
                 "Account": "Account", "Link": "Link"}
        for _c in lk_cols:
            self.link_tree.column(_c, anchor="w" if _c in ("Title", "Link") else "center",
                                  width=_lk_w[_c])
            self.link_tree.heading(_c, text=_lk_h[_c])
        self._bind_sort(self.link_tree, "first", exclude=("STT",))
        self.link_tree.tag_configure("evenrow", background="white")
        self.link_tree.tag_configure("oddrow", background="white")
        self.link_tree.pack(fill="both", expand=True)
        self.link_tree.bind("<Button-3>", self._link_right_click)
        self.link_tree.bind("<Double-Button-1>", self._link_open_selected)
        self.link_tree.bind("<Control-a>", self._link_select_all)
        self.link_tree.bind("<Control-A>", self._link_select_all)
        self._refresh_lists_combo()

        # Hang Folder Video (doi tu thanh menu tren cung xuong)
        vid_frame = ttk.Frame(up_tab)
        vid_frame.pack(fill="x", padx=5, pady=(5, 0))
        ttk.Label(vid_frame, text="Folder Video:").pack(side="left", padx=5)
        ttk.Entry(vid_frame, textvariable=self.folder_var, width=30).pack(side="left", padx=5)
        ttk.Button(vid_frame, text="Browse", command=self._pick_folder).pack(side="left", padx=2)
        ttk.Button(vid_frame, text="📂", width=3,
                   command=lambda: self._open_folder_of(self.folder_var)).pack(side="left", padx=2)

        vid2_frame = ttk.Frame(up_tab)
        vid2_frame.pack(fill="x", padx=5, pady=(2, 0))
        ttk.Label(vid2_frame, text="Load N video:").pack(side="left", padx=5)
        ttk.Spinbox(vid2_frame, from_=1, to=1000, textvariable=self.num_load_videos_var,
                    width=6).pack(side="left", padx=5)
        ttk.Button(vid2_frame, text="Scan & Load", command=self._scan_videos).pack(side="left", padx=5)

        # Config bar
        cfg_frame = ttk.Frame(up_tab)
        cfg_frame.pack(fill="x", padx=5, pady=5)

        ttk.Label(cfg_frame, text="Threads:").pack(side="left", padx=5)
        ttk.Spinbox(cfg_frame, from_=1, to=20, textvariable=self.threads_var, width=5).pack(side="left", padx=5)

        ttk.Label(cfg_frame, text="Video/Acc:").pack(side="left", padx=15)
        ttk.Spinbox(cfg_frame, from_=1, to=100, textvariable=self.videos_per_acc_var, width=5).pack(side="left", padx=5)

        ttk.Label(cfg_frame, text="Delay mở trình duyệt (giây):").pack(side="left", padx=15)
        ttk.Spinbox(cfg_frame, from_=0, to=300, textvariable=self.up_delay_var, width=5).pack(side="left", padx=5)

        ttk.Button(cfg_frame, text="Create Jobs", command=self._create_jobs).pack(side="left", padx=15)
        ttk.Button(cfg_frame, text="▶ Start Upload", style="Accent.TButton",
                   command=self._start_upload).pack(side="left", padx=5)
        ttk.Button(cfg_frame, text="⏹ STOP", command=self._stop_all_runs).pack(side="left", padx=5)
        ttk.Checkbutton(cfg_frame, text="Tự xoá cache TikTok khi account upload xong",
                        variable=self.clean_cache_var,
                        command=self._persist_settings).pack(side="left", padx=10)

        job_name_frame = ttk.Frame(up_tab)
        job_name_frame.pack(fill="x", padx=5, pady=(0, 2))
        ttk.Label(job_name_frame, text="Tên video:").pack(side="left", padx=5)
        ttk.Button(job_name_frame, text="✏️ Đổi tên hàng loạt",
                   command=lambda: self._open_rename_dialog("jobs")).pack(side="left", padx=2)
        ttk.Button(job_name_frame, text="🧹 Xoá hashtag",
                   command=self._strip_hashtags_jobs).pack(side="left", padx=2)
        ttk.Label(job_name_frame, text="(job đang chọn, không chọn = tất cả job)").pack(side="left", padx=6)

        # Upload table
        up_table_frame = ttk.Frame(up_tab)
        up_table_frame.pack(fill="both", expand=True, padx=5, pady=5)

        up_scroll = ttk.Scrollbar(up_table_frame)
        up_scroll.pack(side="right", fill="y")

        up_cols = ("ID", "Video", "Status", "Progress", "Time")
        self.up_tree = ttk.Treeview(
            up_table_frame,
            columns=up_cols,
            height=20,
            selectmode="extended",
            yscrollcommand=up_scroll.set
        )
        self.up_tree.tag_configure("oddrow", background="#ffffff")
        self.up_tree.tag_configure("evenrow", background="#ffffff")
        up_scroll.config(command=self.up_tree.yview)

        self.up_tree.column("#0", width=0)
        self.up_tree.column("ID", anchor="w", width=100)
        self.up_tree.column("Video", anchor="w", width=260)
        self.up_tree.column("Status", anchor="center", width=120)
        self.up_tree.column("Progress", anchor="center", width=80)
        self.up_tree.column("Time", anchor="center", width=80)

        self.up_tree.heading("ID", text="ID")
        self.up_tree.heading("Video", text="Video")
        self.up_tree.heading("Status", text="Status")
        self.up_tree.heading("Progress", text="Progress")
        self.up_tree.heading("Time", text="Time")
        self._bind_sort(self.up_tree)

        self.up_tree.pack(fill="both", expand=True)

        # Chon nhieu dong o bang job: Ctrl+A, Ctrl+Click, chuot phai, phim Delete
        self.up_tree.bind("<Control-a>", self._jobs_select_all)
        self.up_tree.bind("<Button-3>", self._jobs_right_click)
        self.up_tree.bind("<Delete>", lambda e: self._delete_selected_jobs())

        # ---- BOTTOM: nut mo cua so Log tien trinh (khong con khung log
        # chiem cho duoi bang nua - log van chay nen va luu vao bo dem,
        # bam nut thi mo cua so rieng de xem + copy) ----
        log_bar = ttk.Frame(self.root)
        log_bar.pack(side="bottom", fill="x", padx=10, pady=(4, 10), before=main)
        ttk.Button(log_bar, text="📜 Log tiến trình",
                   command=self._open_log_window).pack(side="left")
        ttk.Label(log_bar, text="(log vẫn chạy nền - bấm nút để xem / copy log)").pack(side="left", padx=8)

    def _load_accounts(self):
        """Load account từ file."""
        try:
            self.all_accounts = load_accounts(ACC_FILE)
            # Ap group da luu trong tool_settings.json (accounts.txt chuan 8
            # truong khong chua group); file cu 10/11 truong co san group
            # trong dong thi van dung duoc neu settings chua co.
            _gmap = _load_settings().get("groups", {})
            for _acc in self.all_accounts:
                if _acc["id"] in _gmap:
                    _acc["group"] = _gmap[_acc["id"]]
            _pmap = _load_settings().get("proxies", {})
            for _acc in self.all_accounts:
                if _acc["id"] in _pmap:
                    _acc["proxy"] = _pmap[_acc["id"]]
            _nmap = _load_settings().get("notes", {})
            for _acc in self.all_accounts:
                if _acc["id"] in _nmap:
                    _acc["note"] = _nmap[_acc["id"]]
            # Gop so lieu quet info lan truoc (stats_cache.json)
            _stats = _load_stats_cache()
            for _acc in self.all_accounts:
                _sv = _stats.get(_acc["id"]) or {}
                for _k in ("views30d", "follows", "likes", "views", "videos",
                           "country", "alogin"):
                    if _sv.get(_k) is not None:
                        _acc[_k] = _sv[_k]
                if _sv.get("dead"):
                    _acc["scan_dead"] = True
            print(f"[OK] Load {len(self.all_accounts)} account")

            # Collect groups
            self.groups = set()
            for acc in self.all_accounts:
                group = acc.get("group", "Chưa phân loại")
                if group:
                    self.groups.add(group)

            groups = sorted(list(self.groups))
            self.group_combo['values'] = ["All"] + groups
            self.group_combo.set("All")

            self._refresh_account_table()
        except Exception as e:
            print(f"[LỖI] Load account: {e}")

    def _acc_row_tag(self, acc, idx):
        """Màu nền 1 dòng account: đỏ = quét info không ra (acc die),
        vàng = trên 10.000 follow, còn lại xen kẽ trắng/xanh nhạt."""
        if acc.get("scan_dead"):
            return "deadrow"
        f = acc.get("follows")
        num = 0
        if isinstance(f, (int, float)):
            num = f
        elif isinstance(f, str):
            try:
                num = int(f.replace(",", "").replace(".", ""))
            except Exception:  # noqa
                num = 0
        if num > 10000:
            return "goldrow"
        return "evenrow" if idx % 2 == 0 else "oddrow"

    # ---------- Tim account theo list ID dan vao ----------
    @staticmethod
    def _parse_id_list(text):
        """Tach list ID tu text dan vao: moi dong / dau phay / khoang trang
        la 1 ID; bo @ o dau, khong phan biet hoa thuong, bo trung lap."""
        out, seen = [], set()
        for tok in re.split(r"[\s,;]+", text or ""):
            t = tok.strip().lstrip("@")
            if t and t.lower() not in seen:
                seen.add(t.lower())
                out.append(t)
        return out

    def _search_accounts(self):
        ids = self._parse_id_list(self.search_text.get("1.0", "end"))
        if not ids:
            messagebox.showinfo("Tìm account",
                                "Chưa có ID nào - hãy dán list ID vào ô tìm.")
            return
        self.search_ids = {t.lower() for t in ids}
        self._refresh_account_table()
        kids = self.acc_tree.get_children()
        visible = set()
        for item in kids:
            self.acc_tree.selection_add(item)
            v = self.acc_tree.item(item, "values")
            if v:
                visible.add(str(v[0]).lower())
        missing = [t for t in ids if t.lower() not in visible]
        print(f"[SEARCH] Tìm {len(ids)} account: thấy {len(kids)} trong bảng, "
              f"thiếu {len(missing)}"
              + (f" - thiếu: {', '.join(missing)}" if missing else ""))
        self._update_acc_sel_label()

    def _clear_search(self):
        self.search_ids = None
        try:
            self.search_text.delete("1.0", "end")
        except Exception:  # noqa
            pass
        self._refresh_account_table()
        print("[SEARCH] Đã bỏ lọc tìm account - hiện toàn bộ bảng.")

    def _update_acc_sel_label(self):
        """Nhan 'Da chon: X / Y tai khoan' - X dong dang to chon,
        Y tong so dong dang hien trong bang account."""
        lbl = getattr(self, "acc_sel_label", None)
        if lbl is None:
            return
        try:
            total = len(self.acc_tree.get_children())
            sel = len(self.acc_tree.selection())
        except Exception:  # noqa
            return
        lbl.config(text=f"Đã chọn: {sel} / {total} tài khoản")

    def _bind_sort(self, tree, renumber=None, exclude=()):
        """Bam vao tieu de cot de sap xep bang (so theo gia tri, chu
        theo bang chu cai); bam lai chinh cot do thi dao chieu. Cot
        dang xep co them mui ten ▲ (tang dan) / ▼ (giam dan)."""
        state = {"col": None, "rev": False, "renumber": renumber}
        tree._sort_state = state
        base_text = {c: tree.heading(c, "text") for c in tree["columns"]}

        def make_cmd(col):
            def _cmd():
                if state["col"] == col:
                    state["rev"] = not state["rev"]
                else:
                    state["col"] = col
                    state["rev"] = False
                for c, t0 in base_text.items():
                    tree.heading(c, text=t0)
                tree.heading(col, text=base_text[col]
                             + (" ▼" if state["rev"] else " ▲"))
                sort_treeview(tree, col, state["rev"], renumber)
            return _cmd

        for c in tree["columns"]:
            if c in exclude:
                continue
            tree.heading(c, command=make_cmd(c))

    def _reapply_sort(self, tree):
        """Bang vua ve lai (refresh) thi ap lai thu tu sap xep dang
        chon cua bang do (neu co)."""
        st = getattr(tree, "_sort_state", None)
        if st and st.get("col"):
            sort_treeview(tree, st["col"], st["rev"], st.get("renumber"))

    def _refresh_account_table(self):
        """Cập nhật bảng account theo group filter + loc tim account."""
        for item in self.acc_tree.get_children():
            self.acc_tree.delete(item)

        filtered = self.all_accounts
        if self.group_filter.get() != "All":
            filtered = [a for a in filtered if a.get("group") == self.group_filter.get()]
        _sids = getattr(self, "search_ids", None)
        if _sids is not None:
            filtered = [a for a in filtered
                        if (a.get("id") or "").lower() in _sids]

        for idx, acc in enumerate(filtered):
            self.acc_tree.insert("", "end", text=str(idx + 1),
                                 values=self._acc_row_values(acc),
                                 tags=(self._acc_row_tag(acc, idx),))
        self._update_acc_sel_label()
        self._reapply_sort(self.acc_tree)

    def _acc_row_values(self, acc):
        """Gia tri 1 dong cua bang account theo dung thu tu cot."""
        cookie = acc.get("cookie", "")
        cookie_disp = (cookie[:26] + "…") if len(cookie) > 26 else cookie
        return (acc["id"], acc.get("views30d", "—"),
                acc.get("follows", "—"), acc.get("likes", "—"),
                acc.get("views", "—"), acc.get("videos", "—"),
                ("Có" if (self.yt_acc_channels.get(acc["id"]) or {}).get("url")
                 else "Chưa"),
                acc.get("country", "—"),
                acc.get("email", ""), acc.get("mailbackup", ""),
                ("Die" if acc.get("scan_dead") else "Live"),
                acc.get("alogin", "—"),
                cookie_disp,
                str(acc.get("note", "") or "").replace("\n", " "))

    def _refresh_acc_row(self, acc):
        """Cap nhat lai 1 dong account (sau khi quet info xong)."""
        for pos, item in enumerate(self.acc_tree.get_children()):
            vals = self.acc_tree.item(item, "values")
            if vals and vals[0] == acc["id"]:
                self.acc_tree.item(item, values=self._acc_row_values(acc),
                                   tags=(self._acc_row_tag(acc, pos),))
                break

    def _select_all_accounts(self, event=None):
        """Ctrl+A: select tất cả account hiện tại."""
        for item in self.acc_tree.get_children():
            self.acc_tree.selection_add(item)
        return "break"  # Prevent default Ctrl+A

    def _ctrl_click_select(self, event):
        """Ctrl+Click: toggle select."""
        item = self.acc_tree.identify('item', event.x, event.y)
        if item:
            if item in self.acc_tree.selection():
                self.acc_tree.selection_remove(item)
            else:
                self.acc_tree.selection_add(item)
        return "break"

    def _right_click_menu(self, event):
        """Right-click menu để chuyển nhóm."""
        item = self.acc_tree.identify('item', event.x, event.y)
        if not item:
            return

        selected = self.acc_tree.selection()
        if item not in selected:
            self.acc_tree.selection_set(item)

        # Popup menu
        menu = tk.Menu(self.root, tearoff=False)
        for group in sorted(self.groups):
            menu.add_command(label=f"→ {group}", command=lambda g=group: self._move_to_group(g))
        menu.add_separator()
        menu.add_command(label="Tạo Group mới...", command=self._create_group_for_accounts)
        menu.add_separator()
        copy_menu = tk.Menu(menu, tearoff=False)
        copy_menu.add_command(label="ID TikTok",
                              command=lambda: self._copy_accounts("id"))
        copy_menu.add_command(label="Link TikTok",
                              command=lambda: self._copy_accounts("link"))
        copy_menu.add_command(label="Password",
                              command=lambda: self._copy_accounts("password"))
        copy_menu.add_command(label="Email|Passmail|RefreshToken|ClientId",
                              command=lambda: self._copy_accounts("mail_bundle"))
        copy_menu.add_command(label="Cookie",
                              command=lambda: self._copy_accounts("cookie"))
        copy_menu.add_command(label="Mail backup",
                              command=lambda: self._copy_accounts("mailbackup"))
        copy_menu.add_separator()
        copy_menu.add_command(label="Dòng đầy đủ (8 trường)",
                              command=lambda: self._copy_accounts("full8"))
        menu.add_cascade(label="📋 Copy thông tin", menu=copy_menu)
        menu.add_command(label="🔍 Xem chi tiết", command=self._show_account_detail)
        menu.add_command(label="📤 Xuất thông tin acc đã chọn ra .txt...", command=self._export_info_dialog)
        menu.add_command(label="📝 Ghi chú (Note) cho acc đã chọn...", command=self._edit_note)
        menu.add_separator()
        menu.add_command(label="🌐 Mở trình duyệt GPM", command=self._open_selected_profiles)
        menu.add_command(label="🔑 Chạy Auto Login (acc đã chọn)", command=self._run_autologin_selected)
        menu.add_command(label="🔁 Chạy lại Auto Login - chỉ acc LỖI đã chọn", command=self._run_autologin_failed)
        menu.add_command(label="🗑 Xoá account đã chọn", command=self._delete_account)
        menu.post(event.x_root, event.y_root)

    def _move_to_group(self, target_group):
        """Chuyển selected accounts sang group khác."""
        selected = self.acc_tree.selection()
        if not selected:
            messagebox.showwarning("Cảnh báo", "Chọn account trước!")
            return

        # Update in memory
        updated_count = 0
        for item in selected:
            acc_id = self.acc_tree.item(item, "values")[0]
            for acc in self.all_accounts:
                if acc["id"] == acc_id:
                    acc["group"] = target_group
                    updated_count += 1
                    break

        # Save to file
        self._save_accounts()
        self._refresh_account_table()
        print(f"[OK] Chuyển {updated_count} account sang group '{target_group}'")

    def _create_group(self):
        """Tạo nhóm mới."""
        name = simpledialog.askstring("Tạo Group", "Tên group:")
        if not name:
            return

        name = name.strip()
        if name in self.groups:
            messagebox.showerror("Lỗi", "Group đã tồn tại!")
            return

        self.groups.add(name)
        self.group_combo['values'] = ["All"] + sorted(list(self.groups))
        print(f"[OK] Tạo group: {name}")

    def _rename_group(self):
        """Đổi tên group đang chọn ở bộ lọc: mọi account thuộc group cũ
        chuyển sang tên mới, lưu qua _save_accounts (groups nằm trong
        tool_settings.json)."""
        old = self.group_filter.get()
        if not old or old == "All":
            messagebox.showwarning("Chưa chọn group",
                                   "Hãy chọn group cần sửa tên ở bộ lọc trước!")
            return
        new = simpledialog.askstring("Sửa tên Group",
                                     f"Tên mới cho group '{old}':",
                                     initialvalue=old)
        if not new:
            return
        new = new.strip()
        if not new or new == old:
            return
        if new in self.groups:
            messagebox.showerror("Lỗi", "Đã có group mang tên này!")
            return
        n = 0
        for acc in self.all_accounts:
            if acc.get("group") == old:
                acc["group"] = new
                n += 1
        self.groups.discard(old)
        self.groups.add(new)
        self.group_combo['values'] = ["All"] + sorted(list(self.groups))
        self.group_filter.set(new)
        self._save_accounts()
        self._refresh_account_table()
        print(f"[OK] Đổi tên group '{old}' -> '{new}' ({n} account)")

    def _delete_group(self):
        """Xoá nhóm (chuyển account về 'Chưa phân loại')."""
        group = self.group_filter.get()
        if group == "All":
            messagebox.showwarning("Cảnh báo", "Không thể xoá 'All'!")
            return

        if messagebox.askyesno("Xác nhận", f"Xoá group '{group}'?\nAccount sẽ chuyển về 'Chưa phân loại'"):
            # Move accounts out
            for acc in self.all_accounts:
                if acc.get("group") == group:
                    acc["group"] = "Chưa phân loại"

            self.groups.discard(group)
            self.group_combo['values'] = ["All"] + sorted(list(self.groups))
            self.group_filter.set("All")

            self._save_accounts()
            self._refresh_account_table()
            print(f"[OK] Xoá group: {group}")

    def _save_accounts(self):
        """Lưu accounts.txt."""
        try:
            lines = []
            for acc in self.all_accounts:
                lines.append(format_account_line(acc))

            ACC_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
            # Group la du lieu rieng cua GUI -> luu trong tool_settings.json
            # theo ID account, de accounts.txt giu dung chuan 8 truong.
            # Note (ghi chu cua tung account) cung la du lieu rieng cua
            # GUI -> luu trong tool_settings.json theo ID nhu group/proxy.
            # CHỐNG MẤT DỮ LIỆU: file đang có dữ liệu mà trong bộ
            # nhớ đang rỗng (vd vừa load lỗi) thì GIỮ NGUYÊN dữ
            # liệu cũ, tuyệt đối không ghi đè rỗng lên.
            _stored = _load_settings()
            for _key, _field in (("groups", "group"),
                                 ("proxies", "proxy"),
                                 ("notes", "note")):
                _new = {a["id"]: a.get(_field, "")
                        for a in self.all_accounts if a.get(_field)}
                if not _new and _stored.get(_key):
                    print(f"[BẢO VỆ] Bỏ qua ghi '{_key}': file đang "
                          f"có {len(_stored[_key])} mục nhưng bộ "
                          f"nhớ đang rỗng - giữ nguyên dữ liệu cũ.")
                    continue
                _update_settings({_key: _new})
            print("[OK] Lưu accounts.txt")
        except Exception as e:
            print(f"[LỖI] Save accounts: {e}")

    def _pick_folder(self):
        """Chọn folder video."""
        folder = filedialog.askdirectory(title="Chọn folder video")
        if folder:
            self.folder_var.set(folder)

    def _scan_videos(self):
        """Quét N video từ folder."""
        folder = self.folder_var.get()
        if not folder or not Path(folder).exists():
            messagebox.showerror("Lỗi", "Folder không tồn tại!")
            return

        num_load = self.num_load_videos_var.get()
        all_videos = self._scan_folder(folder)

        self.videos = all_videos[:num_load]  # Lấy N video đầu tiên
        print(f"[OK] Load {len(self.videos)} / {len(all_videos)} video")

    def _scan_folder(self, folder):
        """Quét tất cả video trong 1 folder (không giới hạn số lượng)."""
        all_videos = []
        for ext in VIDEO_EXTS:
            all_videos.extend(sorted(Path(folder).glob(f"*{ext}")))
            all_videos.extend(sorted(Path(folder).glob(f"*{ext.upper()}")))
        all_videos = list(set(all_videos))
        all_videos.sort()
        return all_videos

    def _create_jobs(self):
        """Tạo job list từ selected accounts + videos."""
        selected_items = self.acc_tree.selection()
        if not selected_items:
            messagebox.showerror("Lỗi", "Chọn account trước!")
            return

        self.selected_accounts = []
        for item in selected_items:
            acc_id = self.acc_tree.item(item, "values")[0]
            acc = next((a for a in self.all_accounts if a["id"] == acc_id), None)
            if acc:
                self.selected_accounts.append(acc)

        if not self.videos:
            messagebox.showerror("Lỗi", "Chưa load video!")
            return

        # Tat ca account dung chung 1 folder video, phan bo vong tron
        videos_per_acc = self.videos_per_acc_var.get()
        self.jobs = []

        for i, video in enumerate(self.videos):
            acc_idx = (i // videos_per_acc) % len(self.selected_accounts)
            acc = self.selected_accounts[acc_idx]
            job = UploadJob(acc["id"], video)
            self.jobs.append(job)

        print(f"[OK] Tạo {len(self.jobs)} job từ {len(self.selected_accounts)} account")
        self._refresh_upload_table()

    def _refresh_upload_table(self):
        """Cập nhật bảng upload."""
        for item in self.up_tree.get_children():
            self.up_tree.delete(item)

        self.job_items = {}
        for idx, job in enumerate(self.jobs):
            item_id = self.up_tree.insert("", "end", values=(
                job.acc_id,
                job.video_path.name,
                job.status,
                f"{job.progress}%",
                ""
            ), tags=("evenrow" if idx % 2 == 0 else "oddrow",))
            self.job_items[item_id] = job

    # ------ Doi ten video hang loat / xoa hashtag ------
    def _rename_targets(self, kind):
        """Tra (targets, dang_chon): dang chon neu co dong dang duoc
        chon o bang tuong ung, khong thi lay tat ca."""
        if kind == "jobs":
            sel = [self.job_items[i] for i in self.up_tree.selection()
                   if i in getattr(self, "job_items", {})]
            return (sel, True) if sel else (list(self.jobs), False)
        sel_ids = set()
        for i in self.link_tree.selection():
            vals = self.link_tree.item(i, "values")
            if vals and len(vals) > 1:
                sel_ids.add(vals[1])
        if sel_ids:
            return [r for r in self.yt_link_rows
                    if r["id"] in sel_ids], True
        return list(self.yt_link_rows), False

    def _open_rename_dialog(self, kind):
        """Hop thoai doi ten hang loat: tim & thay the, them dau/cuoi,
        xoa hashtag, danh so thu tu - kem xem truoc. kind='jobs' doi
        TEN FILE video (Offline); kind='links' doi TITLE (List Link,
        pipeline dung lam caption)."""
        targets, scoped = self._rename_targets(kind)
        if not targets:
            messagebox.showwarning("Trống", "Chưa có video nào để đổi tên!")
            return
        if kind == "jobs":
            old_names = [Path(j.video_path).name for j in targets]
            title = "Đổi tên video hàng loạt (Offline — tên file)"
        else:
            old_names = [(r.get("title") or "") for r in targets]
            title = "Đổi tên video hàng loạt (List Link — tiêu đề)"
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.geometry("540x590")
        dlg.transient(self.root)
        dlg.grab_set()
        ttk.Label(dlg, text=f"Áp dụng cho {len(targets)} video "
                            f"({'đang chọn' if scoped else 'tất cả'})",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w",
                                                      padx=12, pady=(12, 6))
        find_var = tk.StringVar()
        repl_var = tk.StringVar()
        prefix_var = tk.StringVar()
        suffix_var = tk.StringVar()
        strip_var = tk.BooleanVar(value=False)
        num_var = tk.BooleanVar(value=False)
        start_var = tk.IntVar(value=1)
        fixed_on_var = tk.BooleanVar(value=False)
        fixed_var = tk.StringVar()
        fix_row = ttk.Frame(dlg)
        fix_row.pack(fill="x", padx=12, pady=(0, 2))
        ttk.Checkbutton(fix_row, text="Thay toàn bộ tên bằng 1 chữ cố định:",
                        variable=fixed_on_var).pack(side="left")
        ttk.Entry(fix_row, textvariable=fixed_var, width=24).pack(side="left", padx=4)
        ttk.Label(dlg, text="(Bật mục này thì các mục dưới bị bỏ qua. Riêng Offline: "
                            "các file cùng thư mục không thể trùng tên — "
                            "file trùng sẽ bị bỏ qua.)",
                  foreground="#888").pack(anchor="w", padx=12, pady=(0, 4))
        frm = ttk.Frame(dlg)
        frm.pack(fill="x", padx=12)
        ttk.Label(frm, text="Tìm:").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(frm, textvariable=find_var, width=24).grid(row=0, column=1, sticky="w")
        ttk.Label(frm, text="Thay bằng:").grid(row=0, column=2, sticky="w", padx=(14, 0))
        ttk.Entry(frm, textvariable=repl_var, width=24).grid(row=0, column=3, sticky="w")
        ttk.Label(frm, text="Thêm vào đầu:").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(frm, textvariable=prefix_var, width=24).grid(row=1, column=1, sticky="w")
        ttk.Label(frm, text="Thêm vào cuối:").grid(row=1, column=2, sticky="w", padx=(14, 0))
        ttk.Entry(frm, textvariable=suffix_var, width=24).grid(row=1, column=3, sticky="w")
        ttk.Checkbutton(dlg, text="🧹 Xoá toàn bộ hashtag (#...)",
                        variable=strip_var).pack(anchor="w", padx=12, pady=(8, 0))
        num_row = ttk.Frame(dlg)
        num_row.pack(fill="x", padx=12, pady=(2, 0))
        ttk.Checkbutton(num_row, text="Đánh số thứ tự ở cuối tên, bắt đầu từ:",
                        variable=num_var).pack(side="left")
        ttk.Spinbox(num_row, from_=1, to=9999, textvariable=start_var,
                    width=6).pack(side="left", padx=4)
        ttk.Label(dlg, text="Xem trước (8 video đầu):").pack(anchor="w",
                                                             padx=12, pady=(10, 2))
        prev = tk.Text(dlg, height=9, font=("Consolas", 9))
        prev.pack(fill="x", padx=12)

        def preview_name(i, old):
            try:
                number = (start_var.get() + i) if num_var.get() else None
            except Exception:  # noqa
                number = None
            ops = (find_var.get(), repl_var.get(), prefix_var.get(),
                   suffix_var.get(), strip_var.get(), number)
            fx = fixed_var.get() if fixed_on_var.get() else ""
            if kind == "jobs":
                p = Path(old)
                stem = _transform_name(p.stem, *ops, fixed=fx)
                return (_safe_file_stem(stem) + p.suffix) if stem else old
            if not old:
                return "(bỏ qua — chưa có title)"
            return _transform_name(old, *ops, fixed=fx) or old

        def refresh_preview(*_a):
            try:
                lines = [f"{o}  →  {preview_name(i, o)}"
                         for i, o in enumerate(old_names[:8])]
                prev.delete("1.0", "end")
                prev.insert("1.0", "\n".join(lines))
            except Exception:  # noqa
                pass

        for v in (find_var, repl_var, prefix_var, suffix_var,
                  strip_var, num_var, start_var,
                  fixed_on_var, fixed_var):
            v.trace_add("write", refresh_preview)
        refresh_preview()

        def do_apply():
            try:
                start = start_var.get()
            except Exception:  # noqa
                start = 1
            ops = dict(find=find_var.get(), repl=repl_var.get(),
                       prefix=prefix_var.get(), suffix=suffix_var.get(),
                       strip_tags=strip_var.get(), num=num_var.get(),
                       start=start,
                       fixed=(fixed_var.get() if fixed_on_var.get()
                              else ""))
            dlg.destroy()
            if kind == "jobs":
                self._apply_job_rename(targets, ops)
            else:
                self._apply_link_rename(targets, ops)

        btns = ttk.Frame(dlg)
        btns.pack(pady=12)
        ttk.Button(btns, text="✔ Áp dụng", command=do_apply).pack(side="left", padx=6)
        ttk.Button(btns, text="Huỷ", command=dlg.destroy).pack(side="left", padx=6)

    def _apply_job_rename(self, jobs, ops):
        """Doi ten FILE video cua cac job Offline + cap nhat
        job.video_path/caption. Bo qua: job dang chay, file khong con,
        ten moi trung file da co hoac khong doi."""
        ok = fail = skip = 0
        for i, job in enumerate(jobs):
            if str(job.status).startswith("🔄"):
                skip += 1
                continue
            old = Path(job.video_path)
            number = (ops["start"] + i) if ops["num"] else None
            stem = _transform_name(old.stem, ops["find"], ops["repl"],
                                   ops["prefix"], ops["suffix"],
                                   ops["strip_tags"], number,
                                   fixed=ops.get("fixed", ""))
            if not stem or stem == old.stem:
                skip += 1
                continue
            new_path = old.with_name(_safe_file_stem(stem) + old.suffix)
            if new_path == old or new_path.exists():
                if new_path != old:
                    print(f"[RENAME] ⚠️ Bỏ qua (đã có file tên này): "
                          f"{new_path.name}")
                skip += 1
                continue
            if not old.exists():
                skip += 1
                continue
            try:
                old.rename(new_path)
            except Exception as e:  # noqa
                print(f"[RENAME] ❌ {old.name}: {_short(e)}")
                fail += 1
                continue
            job.video_path = new_path
            job.caption = new_path.stem
            ok += 1
            print(f"[RENAME] {old.name} -> {new_path.name}")
        self._refresh_upload_table()
        print(f"[RENAME] Đổi tên file (Offline): xong {ok}, "
              f"bỏ qua {skip}, lỗi {fail}.")
        self._notify_done("Đổi tên video (Offline)",
                          f"✅ Đã đổi tên {ok} video.\n"
                          f"Bỏ qua: {skip} — Lỗi: {fail}")

    def _apply_link_rename(self, rows, ops):
        """Doi TITLE cua cac dong List Link + ghi title moi vao
        yt_downloaded.json (de pipeline dung lam caption)."""
        ok = skip = 0
        titles = {}
        for i, row in enumerate(rows):
            old = row.get("title") or ""
            if not old:
                skip += 1
                continue
            number = (ops["start"] + i) if ops["num"] else None
            new = _transform_name(old, ops["find"], ops["repl"],
                                  ops["prefix"], ops["suffix"],
                                  ops["strip_tags"], number,
                                  fixed=ops.get("fixed", ""))
            if not new or new == old:
                skip += 1
                continue
            row["title"] = new
            titles[row["id"]] = new
            ok += 1
            print(f"[RENAME] {row['id']}: {old} -> {new}")
        _set_yt_cache_titles(titles)
        self._refresh_link_table()
        print(f"[RENAME] Đổi title (List Link): xong {ok}, bỏ qua {skip}.")
        self._notify_done("Đổi tên video (List Link)",
                          f"✅ Đã đổi tên {ok} video.\nBỏ qua: {skip}")

    def _strip_hashtags_jobs(self):
        targets, _scoped = self._rename_targets("jobs")
        if not targets:
            messagebox.showwarning("Trống", "Chưa có job nào!")
            return
        ops = dict(find="", repl="", prefix="", suffix="",
                   strip_tags=True, num=False, start=1)
        self._apply_job_rename(targets, ops)

    def _strip_hashtags_links(self):
        targets, _scoped = self._rename_targets("links")
        if not targets:
            messagebox.showwarning("Trống", "List link đang trống!")
            return
        ops = dict(find="", repl="", prefix="", suffix="",
                   strip_tags=True, num=False, start=1)
        self._apply_link_rename(targets, ops)

    def _start_upload(self):
        """Bắt đầu upload song song - CHI chay job CHUA thanh cong
        (job da ✅ tu bo qua, tranh dang trung video len TikTok)."""
        global GRID_TOTAL, HIDE_BROWSER
        if self.busy:
            messagebox.showwarning("Cảnh báo", "Đang upload...")
            return

        if not self.jobs:
            messagebox.showerror("Lỗi", "Tạo job trước!")
            return

        pending = [j for j in self.jobs if not j.status.startswith("✅")]
        if not pending:
            messagebox.showinfo("Thông báo",
                                "Tất cả job đã ✅ thành công, không còn gì để chạy lại.")
            return

        for j in pending:
            j.status = "⏳ Chờ"
            j.progress = 0
            j.error = ""
            self._update_job_ui(j)

        threads = self.threads_var.get()
        # So o luoi cua so = so luong chay cung luc (toi da bang so job)
        GRID_TOTAL = max(1, min(threads, len(pending)))
        _set_launch_delay(self.up_delay_var.get())
        HIDE_BROWSER = bool(self.hide_browser_var.get())
        print(f"[OK] Chạy {len(pending)} job chưa thành công "
              f"(bỏ qua {len(self.jobs) - len(pending)} job đã ✅) - "
              f"{threads} luồng, chia lưới {GRID_TOTAL} cửa sổ"
              + (" - ẨN trình duyệt" if HIDE_BROWSER else ""))

        self.stop_requested = False
        clear_engine_stop()
        self.busy = True
        print("[START] ▶ Đã bắt đầu upload - đang mở các trình duyệt "
              "đầu tiên, vui lòng đợi vài giây...")
        threading.Thread(target=self._upload_worker, args=(threads, pending),
                         daemon=True).start()

    def _upload_worker(self, max_workers, jobs):
        """Worker: upload song song cac job duoc giao."""
        totals = {}
        for j in jobs:
            totals[j.acc_id] = totals.get(j.acc_id, 0) + 1
        done_counts = {}
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(self._upload_one, job): job for job in jobs}

                for future in as_completed(futures):
                    job = futures[future]
                    try:
                        result = future.result()
                        if not result and self.stop_requested:
                            job.status = "⏹ Đã dừng"
                        else:
                            job.status = "✅ OK" if result else "❌ Failed"
                        job.progress = 100 if result else 0
                    except _StopRequested:
                        job.status = "⏹ Đã dừng"
                        job.progress = 0
                    except Exception as e:
                        job.status = "❌ Error"
                        job.error = str(e)
                        print(f"[ERROR] {job}: {e}")

                    job.end_time = time.time()
                    self._ui(lambda j=job: self._update_job_ui(j))
                    self._ui(lambda jid=job.acc_id, st=job.status:
                             self._set_acc_status(jid, st))
                    done_counts[job.acc_id] = done_counts.get(job.acc_id, 0) + 1
                    if done_counts[job.acc_id] >= totals[job.acc_id]:
                        self._ui(lambda jid=job.acc_id: self._maybe_clean_cache(jid))
        finally:
            self.busy = False
            print("[DONE] Upload hoàn tất!")
            failed_accs = []
            ok_n = fail_n = 0
            for j in jobs:
                st = str(j.status)
                if st.startswith("❌"):
                    fail_n += 1
                    if j.acc_id not in failed_accs:
                        failed_accs.append(j.acc_id)
                elif st.startswith("✅"):
                    ok_n += 1
            if failed_accs:
                self._report_upload_result("Upload Offline", ok_n, fail_n,
                                           failed_accs)
            self._notify_done(
                "Upload Offline",
                ("⏹ Đã dừng upload theo yêu cầu.\n"
                 if self.stop_requested else "✅ Upload đã hoàn tất!\n")
                + f"Thành công: {ok_n} - Lỗi: {fail_n} "
                  f"(tổng {len(jobs)} job)")

    def _upload_one(self, job):
        """Upload 1 video."""
        if self.stop_requested:
            raise _StopRequested()
        job.status = "🔄 Đang mở trình duyệt..."
        job.start_time = time.time()
        self._ui(lambda: self._update_job_ui(job))
        self._ui(lambda jid=job.acc_id: self._set_acc_status(
            jid, "🔄 Đang mở trình duyệt..."))

        try:
            acc = next((a for a in self.all_accounts if a["id"] == job.acc_id), None)
            if not acc:
                print(f"[!] {job.acc_id} không tìm thấy")
                return False

            print(f"  [UP] Upload: {job.video_path.name}")
            # FIX: Dùng Selenium upload (real file chooser, không Playwright)
            result = upload_one_selenium(acc["id"], str(job.video_path), job.caption)
            job.progress = 100 if result else 50

            return result
        except Exception as e:
            print(f"  [!] {job}: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _ui(self, fn):
        """Dua 1 ham cap nhat giao dien vao hang doi; main thread se chay no
        trong vong lap _update_log (Tkinter khong an toan khi goi tu luong phu)."""
        self.uiq.put(fn)

    def _update_job_ui(self, job):
        """Cập nhật UI của 1 job."""
        for item_id, j in self.job_items.items():
            if j == job:
                duration_str = f"{job.duration:.1f}s" if job.duration else ""
                self.up_tree.item(item_id, values=(
                    job.acc_id,
                    job.video_path.name,
                    job.status,
                    f"{job.progress}%",
                    duration_str
                ))
                break

    def _add_account(self):
        """Thêm account: mở cửa sổ dán text (nhiều dòng) rồi bấm SAVE.

        Định dạng mỗi dòng:
        idTiktok|password|email|passmail|refreshToken|clientId|cookie|mailBackup
        (thiếu trường cuối thì để trống). ID đã có thì CẬP NHẬT thông tin
        (giữ nguyên group). ID MỚI: nếu dòng không ghi group thì tự vào
        group đang chọn ở bộ lọc (chọn All thì để không group), và bảng
        tự tô chọn + cuộn tới các account vừa thêm. Thứ tự cột khi dán
        chọn ở khung Định dạng trong cửa sổ (được nhớ vào settings)."""
        win = tk.Toplevel(self.root)
        win.title("Thêm Account - dán danh sách account")
        win.geometry("860x600")
        win.minsize(700, 420)
        win.transient(self.root)
        win.lift()
        ttk.Label(win, text="Mỗi dòng 1 account, các trường cách nhau bằng dấu | "
                            "- thứ tự cột chọn ở khung Định dạng bên dưới."
                  ).pack(anchor="w", padx=10, pady=(10, 4))
        _cur_group = self.group_filter.get()
        if _cur_group and _cur_group != "All":
            ttk.Label(win, text=f"📌 Group đang chọn: {_cur_group} - account MỚI "
                                f"sẽ tự được thêm vào group này.",
                      foreground="#0b5ed7").pack(anchor="w", padx=10, pady=(0, 2))

        # Thanh nut GHIM o day cua so (pack side="bottom" TRUOC o text)
        # -> nut SAVE khong bao gio bi o text day khuat khoi tam nhin
        btns = ttk.Frame(win)
        btns.pack(side="bottom", fill="x", padx=10, pady=10)
        # ---- Khung chon dinh dang cot khi dan (nho vao settings) ----
        fmt_frame = ttk.LabelFrame(
            win, text="Định dạng cột khi dán - chọn theo đúng thứ tự dòng của bạn")
        fmt_frame.pack(fill="x", padx=10, pady=(6, 2))
        slots_frame = ttk.Frame(fmt_frame)
        slots_frame.pack(fill="x", padx=6, pady=(4, 2))
        _label2key = {lbl: k for k, lbl in ADD_FIELD_LABELS}
        _key2label = {k: lbl for k, lbl in ADD_FIELD_LABELS}
        _all_labels = [lbl for _k, lbl in ADD_FIELD_LABELS]
        fmt_vars = []

        def _current_keys():
            return [_label2key.get(v.get(), "") for v in fmt_vars]

        def build_slots(keys):
            keys = list(keys)[:12] or ["id"]
            for w in slots_frame.winfo_children():
                w.destroy()
            fmt_vars.clear()
            for i, k in enumerate(keys):
                var = tk.StringVar(value=_key2label.get(k, "(bỏ qua)"))
                fmt_vars.append(var)
                cell = ttk.Frame(slots_frame)
                cell.grid(row=i // 4, column=i % 4, padx=4, pady=2, sticky="w")
                ttk.Label(cell, text=f"{i + 1}.").pack(side="left")
                ttk.Combobox(cell, values=_all_labels, textvariable=var,
                             width=13, state="readonly").pack(side="left", padx=2)

        _saved_fmt = _load_settings().get("add_acc_format")
        if not (isinstance(_saved_fmt, list) and _saved_fmt
                and all(k in _key2label for k in _saved_fmt)):
            _saved_fmt = list(ACCOUNT_FIELDS_8)
        build_slots(_saved_fmt)

        fmt_btns = ttk.Frame(fmt_frame)
        fmt_btns.pack(fill="x", padx=6, pady=(0, 4))
        ttk.Button(fmt_btns, text="+ Thêm cột",
                   command=lambda: build_slots(_current_keys() + [""])
                   ).pack(side="left", padx=2)
        ttk.Button(fmt_btns, text="− Bớt cột",
                   command=lambda: build_slots(_current_keys()[:-1])
                   ).pack(side="left", padx=2)
        ttk.Button(fmt_btns, text="↺ Về mặc định (8 cột chuẩn)",
                   command=lambda: build_slots(list(ACCOUNT_FIELDS_8))
                   ).pack(side="left", padx=2)

        txt = tk.Text(win, font=("Courier", 10))
        txt.pack(fill="both", expand=True, padx=10, pady=4)

        def do_save():
            raw = txt.get("1.0", "end").strip()
            if not raw:
                messagebox.showwarning(
                    "Chưa có dữ liệu",
                    "Hãy dán danh sách account vào ô trống trước khi bấm SAVE!",
                    parent=win)
                return
            fmt_keys = [_label2key.get(v.get(), "") for v in fmt_vars]
            if fmt_keys.count("id") != 1:
                messagebox.showwarning(
                    "Định dạng chưa đúng",
                    "Khung Định dạng phải có đúng 1 cột 'ID TikTok' - "
                    "kiểm tra lại các ô chọn cột trước khi SAVE!",
                    parent=win)
                return
            added = updated = skipped = 0
            new_ids = []
            target_group = self.group_filter.get()
            if target_group == "All":
                target_group = ""
            by_id = {a["id"]: a for a in self.all_accounts}
            for line in raw.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                acc = _parse_account_line(line, fmt_keys)
                if not acc["id"]:
                    skipped += 1
                    continue
                if acc["id"] in by_id:
                    old = by_id[acc["id"]]
                    keep_group = old.get("group", "")
                    old.update(acc)
                    old["group"] = keep_group
                    updated += 1
                else:
                    # Acc MOI: dong dan khong ghi group thi tu vao group
                    # dang chon o bo loc - khoi phai qua All keo xuong day tim
                    if not acc.get("group") and target_group:
                        acc["group"] = target_group
                    self.all_accounts.append(acc)
                    by_id[acc["id"]] = acc
                    new_ids.append(acc["id"])
                    if acc.get("group"):
                        self.groups.add(acc["group"])
                    added += 1
            self._save_accounts()
            _update_settings({"add_acc_format": fmt_keys})
            self.group_combo['values'] = ["All"] + sorted(list(self.groups))
            self._refresh_account_table()
            # To chon + cuon toi cac account vua them cho de thay
            if new_ids:
                wanted = set(new_ids)
                first = None
                for item in self.acc_tree.get_children():
                    vals = self.acc_tree.item(item, "values")
                    if vals and vals[0] in wanted:
                        self.acc_tree.selection_add(item)
                        if first is None:
                            first = item
                if first:
                    self.acc_tree.focus(first)
                    self.acc_tree.see(first)
            print(f"[OK] Thêm account: +{added} mới, cập nhật {updated}, "
                  f"bỏ qua {skipped} dòng lỗi"
                  + (f" - account mới vào group '{target_group}'"
                     if target_group and added else ""))
            messagebox.showinfo(
                "Đã lưu",
                f"Đã SAVE vào accounts.txt:\n+ {added} account mới\n"
                f"• Cập nhật {updated} account\n• Bỏ qua {skipped} dòng lỗi"
                + (f"\n📌 Account mới đã vào group: {target_group}"
                   if target_group and added else ""),
                parent=win)
            win.destroy()

        ttk.Button(btns, text="💾 SAVE - Lưu vào accounts.txt",
                   command=do_save).pack(side="right", padx=5)
        ttk.Button(btns, text="Huỷ", command=win.destroy).pack(side="right", padx=5)
        txt.focus_set()
        win.grab_set()


    def _edit_account(self):
        """Sửa account."""
        messagebox.showinfo("Info", "Tính năng coming soon...")

    def _open_selected_profiles(self):
        """Chuột phải: mở trình duyệt GPM của các account đang chọn để
        thao tác thủ công (chỉ mở rồi để nguyên cửa sổ, tool không
        upload và không tự đóng)."""
        accs = self._selected_accounts()
        if not accs:
            messagebox.showinfo("Mở trình duyệt",
                                "Hãy chọn ít nhất 1 account trong bảng!")
            return

        # Gian cach mo profile: lay theo o "Delay mo trinh duyet (giay)"
        # ma nguoi dung da dat (lay muc lon hon giua 2 tab) - neu khong
        # goi, _launch_state giu gia tri tu lan chay truoc (thuong la 0 o
        # phien moi) nen mo tay se don 1 luc, khong cach nhau nhu da hua.
        try:
            _manual_delay = max(int(self.up_delay_var.get() or 0),
                                int(self.yt_delay_var.get() or 0))
        except Exception:  # noqa
            _manual_delay = 0
        _set_launch_delay(_manual_delay)

        def run():
            for acc in accs:
                ok, msg = open_profile_browser(acc["id"])
                print(f"[OPEN] @{acc['id']}: {'✅' if ok else '❌'} {msg}")

        threading.Thread(target=run, daemon=True).start()
        print(f"[OPEN] Đang mở trình duyệt cho {len(accs)} account...")

    def _delete_account(self):
        """Xoá account."""
        selected = self.acc_tree.selection()
        if not selected:
            messagebox.showwarning("Cảnh báo", "Chọn account!")
            return

        if messagebox.askyesno("Xác nhận", f"Xoá {len(selected)} account?"):
            _del_ids = []
            for item in selected:
                acc_id = self.acc_tree.item(item, "values")[0]
                _del_ids.append(acc_id)
                self.all_accounts = [a for a in self.all_accounts if a["id"] != acc_id]

            self._save_accounts()
            if any(a in self.yt_assignments for a in _del_ids):
                for a in _del_ids:
                    self.yt_assignments.pop(a, None)
                self._save_assignments()
                self._refresh_link_table()
            self._refresh_account_table()
            print(f"[OK] Xoá {len(selected)} account")

    def _create_group_for_accounts(self):
        """Tạo group mới và chuyển selected accounts vào."""
        name = simpledialog.askstring("Tạo Group", "Tên group mới:")
        if not name:
            return

        name = name.strip()
        if name in self.groups:
            messagebox.showerror("Lỗi", "Group đã tồn tại!")
            return

        self._create_group()
        self._move_to_group(name)

    # ---------- Bang job: chon nhieu dong + xoa job ----------
    def _jobs_select_all(self, event=None):
        """Ctrl+A o bang job: chon tat ca dong."""
        for item in self.up_tree.get_children():
            self.up_tree.selection_add(item)
        return "break"

    def _jobs_right_click(self, event):
        """Menu chuot phai tren bang job (status video)."""
        item = self.up_tree.identify('item', event.x, event.y)
        if item and item not in self.up_tree.selection():
            self.up_tree.selection_set(item)

        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(label="🗑 Xoá dòng đã chọn", command=self._delete_selected_jobs)
        menu.add_command(label="🗑 Xoá tất cả job ✅ thành công",
                         command=self._delete_successful_jobs)
        menu.add_command(label="🗑 Xoá dòng + xoá luôn file video",
                         command=self._delete_selected_jobs_with_files)
        menu.add_separator()
        menu.add_command(label="Chọn tất cả (Ctrl+A)", command=self._jobs_select_all)
        menu.post(event.x_root, event.y_root)

    def _remove_job_rows(self, item_ids):
        """Xoa cac dong job khoi bang + khoi danh sach job, to lai mau xen ke."""
        removed = 0
        for iid in item_ids:
            job = self.job_items.pop(iid, None)
            if job is not None and job in self.jobs:
                self.jobs.remove(job)
            try:
                self.up_tree.delete(iid)
            except Exception:
                pass
            removed += 1
        for idx, iid in enumerate(self.up_tree.get_children()):
            self.up_tree.item(iid, tags=("evenrow" if idx % 2 == 0 else "oddrow",))
        return removed

    def _delete_selected_jobs(self):
        if self.busy:
            messagebox.showwarning("Cảnh báo", "Đang upload, không xoá được!")
            return
        sel = list(self.up_tree.selection())
        if not sel:
            messagebox.showwarning("Cảnh báo", "Chọn dòng trước (Ctrl+Click / Ctrl+A)!")
            return
        n = self._remove_job_rows(sel)
        print(f"[OK] Đã xoá {n} job khỏi bảng")

    def _delete_successful_jobs(self):
        if self.busy:
            messagebox.showwarning("Cảnh báo", "Đang upload, không xoá được!")
            return
        ids = [iid for iid, j in self.job_items.items() if j.status.startswith("✅")]
        if not ids:
            print("[!] Chưa có job ✅ thành công nào để xoá")
            return
        n = self._remove_job_rows(ids)
        print(f"[OK] Đã xoá {n} job ✅ - còn {len(self.jobs)} job chưa thành công để chạy lại")

    def _delete_selected_jobs_with_files(self):
        """Xoá các dòng job đã chọn VÀ xoá luôn file video trên ổ đĩa.
        File nào còn job khác dùng chung thì giữ lại (chỉ xoá dòng)."""
        if self.busy:
            messagebox.showwarning("Cảnh báo", "Đang upload, không xoá được!")
            return
        sel = list(self.up_tree.selection())
        if not sel:
            messagebox.showwarning("Cảnh báo", "Chọn dòng trước (Ctrl+Click / Ctrl+A)!")
            return
        sel_set = set(sel)
        paths, still_used = [], set()
        for iid, job in self.job_items.items():
            pth = str(job.video_path)
            if iid in sel_set:
                if pth not in paths:
                    paths.append(pth)
            else:
                still_used.add(pth)
        deletable = [x for x in paths if x not in still_used]
        kept = [x for x in paths if x in still_used]
        msg = (f"Xoá {len(sel)} dòng job và xoá luôn {len(deletable)} file video "
               f"khỏi ổ đĩa?")
        if kept:
            msg += (f"\n({len(kept)} file còn job khác dùng chung nên chỉ xoá "
                    f"dòng, giữ nguyên file.)")
        if not messagebox.askyesno("Xoá job + file video", msg):
            return
        self._remove_job_rows(sel)
        ok = 0
        for pth in deletable:
            if _delete_source_file(pth):
                ok += 1
        print(f"[OK] Đã xoá {len(sel)} dòng job + {ok}/{len(deletable)} file video")

    # ---------- Cot Tinh trang + Thu muc rieng cua account ----------
    def _set_acc_status(self, acc_id, text):
        """Ghi trang thai moi nhat cua account (bang khong con cot Tinh
        trang - trang thai xem o muc Xem chi tiet cua account)."""
        target = None
        for acc in self.all_accounts:
            if acc["id"] == acc_id:
                acc["last_status"] = text
                target = acc
                break
        if target is not None:
            self._refresh_acc_row(target)

    # ---------- Cau hinh duong dan GPM + xoa cache ----------
    def _persist_settings(self):
        _update_settings({"gpm_profile_dir": self.gpm_dir_var.get(),
                          "auto_clean_cache": bool(self.clean_cache_var.get()),
                          "proxy_file": self.proxy_file_var.get(),
                          "checker_cookie_file": self.checker_file_var.get(),
                          "yt_links_file": self.yt_links_file_var.get(),
                          "yt_api_key": self.yt_api_key_var.get(),
                          "yt_api_keys": list(getattr(self, "yt_api_keys", []) or []),
                          "yt_folder": self.yt_folder_var.get(),
                          "yt_per_acc": self.yt_per_acc_var.get(),
                          "yt_up_threads": self.yt_up_threads_var.get(),
                          "up_delay": self.up_delay_var.get(),
                          "yt_delay": self.yt_delay_var.get(),
                          "tele_token": self.tele_token_var.get(),
                          "tele_chat_id": self.tele_chat_var.get(),
                          "hide_browser": bool(self.hide_browser_var.get()),
                          "scan_view_browser": bool(self.scan_view_browser_var.get()),
                          "yt_search": self.yt_search_var.get(),
                          "yt_search_count": self.yt_search_count_var.get()})

    def _open_folder_of(self, var):
        """Mở nhanh thư mục trong ô đường dẫn bằng Windows Explorer."""
        path = (var.get() or "").strip()
        if path and Path(path).exists():
            try:
                os.startfile(path)  # noqa: chi co tren Windows
            except Exception as e:  # noqa
                print(f"[!] Không mở được thư mục: {_short(e)}")
        else:
            messagebox.showwarning("Cảnh báo", f"Thư mục chưa tồn tại:\n{path}")

    def _pick_gpm_dir(self):
        """Chọn thư mục chứa profile GPM (mỗi máy mỗi khác)."""
        folder = filedialog.askdirectory(title="Chọn thư mục profile GPM")
        if folder:
            self.gpm_dir_var.set(folder)
            self._persist_settings()
            print(f"[OK] Đường dẫn profile GPM: {folder}")

    def _maybe_clean_cache(self, acc_id):
        """Account vua chay xong het job cua no -> xoa cache TikTok cho nhe may."""
        if not self.clean_cache_var.get():
            return
        root = (self.gpm_dir_var.get() or "").strip()
        if not root:
            print("[CLEAN] Chưa đặt đường dẫn profile GPM, bỏ qua xoá cache")
            return
        self._persist_settings()
        threading.Thread(target=self._clean_cache_worker, args=(acc_id, root),
                         daemon=True).start()

    def _clean_cache_worker(self, acc_id, root):
        n, freed, skipped = clean_tiktok_cache(root)
        if n:
            print(f"[CLEAN] @{acc_id} đã xoá {n} thư mục cache TikTok, "
                  f"giải phóng ~{freed / 1048576:.1f} MB"
                  + (f" (bỏ qua {skipped} thư mục đang khoá)" if skipped else ""))
        else:
            print(f"[CLEAN] @{acc_id} không thấy cache TikTok cần xoá trong {root}"
                  + (f" (bỏ qua {skipped} thư mục đang khoá)" if skipped else ""))

    # ---------- Copy thong tin + xem chi tiet account ----------
    def _selected_accounts(self):
        """Danh sach dict account tuong ung cac dong dang chon o bang account."""
        out = []
        for item in self.acc_tree.selection():
            vals = self.acc_tree.item(item, "values")
            if vals:
                acc = next((a for a in self.all_accounts if a["id"] == vals[0]), None)
                if acc:
                    out.append(acc)
        return out

    def _copy_text(self, text, label=""):
        self.root.clipboard_clear()
        self.root.clipboard_append(text or "")
        print(f"[OK] Đã copy {label}".rstrip())

    def _copy_accounts(self, fmt):
        """Copy thong tin cac account dang chon theo 1 dinh dang.
        Chon nhieu account thi moi account 1 dong."""
        accs = self._selected_accounts()
        if not accs:
            messagebox.showwarning("Cảnh báo", "Chọn account trước!")
            return
        labels = {"id": "ID TikTok", "link": "Link TikTok",
                  "password": "Password",
                  "mail_bundle": "Email|Passmail|RefreshToken|ClientId",
                  "cookie": "Cookie", "mailbackup": "Mail backup",
                  "full8": "Dòng đầy đủ (8 trường)"}

        def one(a):
            if fmt == "id":
                return a["id"]
            if fmt == "link":
                return ("http://tiktok.com/@"
                        + (a["id"] or "").lstrip("@"))
            if fmt == "password":
                return a.get("password", "")
            if fmt == "mail_bundle":
                return "|".join([a.get("email", ""), a.get("passmail", ""),
                                 a.get("refresh_token", ""), a.get("client_id", "")])
            if fmt == "cookie":
                return a.get("cookie", "")
            if fmt == "mailbackup":
                return a.get("mailbackup", "")
            return format_account_line(a)

        self._copy_text("\n".join(one(a) for a in accs),
                        f"{len(accs)} account - {labels.get(fmt, fmt)}")

    def _edit_note(self):
        """Sửa ghi chú (Note) cho các account đang chọn: chọn 1 acc thì
        sửa ghi chú riêng của acc đó; chọn nhiều acc thì ghi CÙNG 1 ghi
        chú cho tất cả. Note lưu riêng trong tool_settings.json (key
        "notes", theo ID account) giống group/proxy - accounts.txt giữ
        nguyên chuẩn 8 trường."""
        accs = self._selected_accounts()
        if not accs:
            messagebox.showinfo("Ghi chú",
                                "Hãy chọn ít nhất 1 account trong bảng trước!")
            return
        _notes = {str(a.get("note", "") or "") for a in accs}
        win = tk.Toplevel(self.root)
        win.title(f"Ghi chú (Note) - {len(accs)} account đã chọn")
        win.geometry("560x330")
        win.transient(self.root)
        win.lift()
        ids_txt = ", ".join("@" + a["id"] for a in accs[:6])
        if len(accs) > 6:
            ids_txt += f", ... (+{len(accs) - 6} acc nữa)"
        ttk.Label(win, text=f"Account: {ids_txt}").pack(anchor="w", padx=10,
                                                        pady=(10, 2))
        ttk.Label(win, text="Ghi chú (áp dụng cho mọi account đang chọn):"
                  ).pack(anchor="w", padx=10, pady=(0, 2))
        if len(_notes) > 1:
            ttk.Label(win, text="(Các account đang có ghi chú khác nhau - "
                                "gõ mới sẽ ghi đè cho tất cả)",
                      foreground="#888").pack(anchor="w", padx=10)
        # Thanh nút GHIM ĐÁY cửa sổ (pack side="bottom" TRƯỚC ô text) -
        # bài học từ cửa sổ Add Account: nút SAVE không bị đẩy khuất.
        btns = ttk.Frame(win)
        btns.pack(side="bottom", fill="x", padx=10, pady=10)
        txt = tk.Text(win, height=7, wrap="word", font=("Segoe UI", 10))
        txt.pack(fill="both", expand=True, padx=10, pady=4)
        if len(_notes) == 1:
            txt.insert("1.0", _notes.pop())

        def do_save():
            note = txt.get("1.0", "end").strip()
            for a in accs:
                a["note"] = note
            self._save_accounts()
            for a in accs:
                self._refresh_acc_row(a)
            print(f"[NOTE] Đã lưu ghi chú cho {len(accs)} account"
                  + (f": {note[:60]!r}" if note else " (ghi chú trống)"))
            win.destroy()

        def do_clear():
            for a in accs:
                a["note"] = ""
            self._save_accounts()
            for a in accs:
                self._refresh_acc_row(a)
            print(f"[NOTE] Đã xoá ghi chú của {len(accs)} account")
            win.destroy()

        ttk.Button(btns, text="🗑 Xoá ghi chú", command=do_clear).pack(side="left", padx=5)
        ttk.Button(btns, text="Huỷ", command=win.destroy).pack(side="right", padx=5)
        ttk.Button(btns, text="💾 SAVE Note", style="Accent.TButton",
                   command=do_save).pack(side="right", padx=5)
        txt.focus_set()
        win.grab_set()

    def _on_acc_double_click(self, event):
        item = self.acc_tree.identify('item', event.x, event.y)
        if item:
            self.acc_tree.selection_set(item)
            # Double-click đúng ô cột Note (cột cuối) thì mở sửa ghi chú,
            # các ô khác vẫn mở bảng chi tiết như cũ.
            try:
                _note_col = f"#{len(self.acc_tree['columns'])}"
                if self.acc_tree.identify_column(event.x) == _note_col:
                    self._edit_note()
                    return
            except Exception:  # noqa
                pass
            self._show_account_detail()

    def _show_account_detail(self):
        """Bang chi tiet day du thong tin 1 account (như bang du lieu):
        moi truong 1 dong kem nut Copy rieng."""
        accs = self._selected_accounts()
        if not accs:
            return
        acc = accs[0]
        win = tk.Toplevel(self.root)
        win.title(f"Thông tin account - {acc['id']}")
        win.geometry("780x480")
        fields = [("ID TikTok", acc.get("id", "")),
                  ("Password", acc.get("password", "")),
                  ("Email", acc.get("email", "")),
                  ("Passmail", acc.get("passmail", "")),
                  ("Refresh Token", acc.get("refresh_token", "")),
                  ("Client Id", acc.get("client_id", "")),
                  ("Cookie", acc.get("cookie", "")),
                  ("Mail backup", acc.get("mailbackup", "")),
                  ("Proxy", acc.get("proxy", "")),
                  ("Group", acc.get("group", "")),
                  ("Note", str(acc.get("note", "") or "").replace("\n", " ")),
                  ("Tình trạng", acc.get("last_status", "—")),
                  ("Views (30d)", str(acc.get("views30d", "—"))),
                  ("T.Follows", str(acc.get("follows", "—"))),
                  ("T.Likes", str(acc.get("likes", "—"))),
                  ("T.Views (video mới nhất)", str(acc.get("views", "—"))),
                  ("T.Video", str(acc.get("videos", "—")))]
        body = ttk.Frame(win)
        body.pack(fill="both", expand=True, padx=12, pady=10)
        for r, (label, value) in enumerate(fields):
            ttk.Label(body, text=label + ":", width=16).grid(
                row=r, column=0, sticky="w", pady=2)
            ent = ttk.Entry(body, width=80)
            ent.insert(0, value)
            ent.configure(state="readonly")
            ent.grid(row=r, column=1, sticky="ew", pady=2)
            ttk.Button(body, text="Copy", width=7,
                       command=lambda v=value, lb=label: self._copy_text(v, lb)
                       ).grid(row=r, column=2, padx=(6, 0), pady=2)
        btns = ttk.Frame(win)
        btns.pack(fill="x", padx=12, pady=(0, 10))
        ttk.Button(btns, text="📋 Copy dòng đầy đủ (8 trường)",
                   command=lambda: self._copy_text(format_account_line(acc),
                                                   "dòng đầy đủ")
                   ).pack(side="right", padx=5)
        ttk.Button(btns, text="Đóng", command=win.destroy).pack(side="right", padx=5)

    # ---------- Quet info account ----------
    def _pick_proxy_file(self):
        f = filedialog.askopenfilename(title="Chọn file proxy (mỗi dòng 1 proxy)",
                                       filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if f:
            self.proxy_file_var.set(f)
            self._persist_settings()
            print(f"[OK] File proxy: {f}")

    def _notify_done(self, title, msg):
        """Nhảy hộp thông báo khi 1 tác vụ nền chạy xong (đi qua hàng
        đợi UI nên an toàn khi gọi từ worker thread)."""
        self._ui(lambda: messagebox.showinfo(title, msg))

    def _start_scan(self):
        """Quét info các account đang chọn (không chọn = tất cả) - chạy ẩn
        bằng cookie, đa luồng, xoay vòng proxy trong file proxy."""
        global GRID_TOTAL, HIDE_BROWSER
        if self.scanning:
            messagebox.showwarning("Cảnh báo", "Đang quét info...")
            return
        targets = self._selected_accounts() or list(self.all_accounts)
        if not targets:
            messagebox.showerror("Lỗi", "Chưa có account nào!")
            return
        lines = []
        pf = (self.proxy_file_var.get() or "").strip()
        if pf and Path(pf).exists():
            lines = Path(pf).read_text(encoding="utf-8", errors="ignore").splitlines()
        pool = ProxyPool(lines)
        ck_lines = []
        cf = (self.checker_file_var.get() or "").strip()
        if cf and Path(cf).exists():
            ck_lines = Path(cf).read_text(encoding="utf-8", errors="ignore").splitlines()
        cpool = CookiePool(ck_lines)
        threads = max(1, self.scan_threads_var.get())
        recent_n = max(1, self.recent_videos_var.get())
        self._persist_settings()
        use_browser = bool(self.scan_view_browser_var.get())
        if use_browser:
            GRID_TOTAL = max(1, min(threads, len(targets)))
            HIDE_BROWSER = bool(self.hide_browser_var.get())
            clear_engine_stop()
        print(f"[SCAN] Quét info {len(targets)} account - {threads} luồng - "
              f"{len(pool)} proxy - {len(cpool)} cookie trung gian - "
              f"view của {recent_n} video mới nhất + 30 ngày"
              + ("" if pf and Path(pf).exists() else " (không có file proxy, chạy trực tiếp)")
              + " (ưu tiên cookie của chính acc; acc thiếu cookie mới dùng trung gian)"
              + (" + acc thiếu view sẽ mở trình duyệt GPM quét tiếp" if use_browser else ""))
        self.scanning = True
        threading.Thread(target=self._scan_worker,
                         args=(targets, pool, threads, recent_n, cpool, use_browser),
                         daemon=True).start()

    def _scan_worker(self, targets, pool, threads, recent_n, cpool=None, view_browser=False):
        done = 0
        try:
            with ThreadPoolExecutor(max_workers=threads) as executor:
                futures = {executor.submit(scan_account_full, acc, pool, recent_n, 15, cpool, view_browser): acc
                           for acc in targets}
                for future in as_completed(futures):
                    acc = futures[future]
                    try:
                        r = future.result()
                    except Exception as e:  # noqa
                        r = {"ok": False, "msg": str(e)[:80]}
                    for k in ("follows", "likes", "videos", "views30d", "views"):
                        if r.get(k) is not None:
                            acc[k] = r[k]
                    if r.get("country"):
                        acc["country"] = r["country"]
                    if r.get("ok") and r.get("views") is not None:
                        acc["last_status"] = "✅ Info"
                    elif r.get("ok"):
                        acc["last_status"] = "⚠️ Thiếu view"
                    else:
                        acc["last_status"] = "❌ Quét lỗi"
                    # Quét không ra chút info nào -> coi như acc die (tô
                    # đỏ); lần quét sau ra info thì tự hết đỏ.
                    acc["scan_dead"] = not r.get("ok")
                    _entry = {k: acc.get(k) for k in
                              ("views30d", "follows", "likes", "views", "videos")}
                    if acc.get("country"):
                        _entry["country"] = acc["country"]
                    _entry["dead"] = bool(acc.get("scan_dead"))
                    _save_stats_cache(acc["id"], _entry)
                    self._ui(lambda a=acc: self._refresh_acc_row(a))
                    done += 1
                    print(f"[SCAN] ({done}/{len(targets)}) @{acc['id']}: "
                          f"follow={acc.get('follows', '—')} like={acc.get('likes', '—')} "
                          f"video={acc.get('videos', '—')} view30d={acc.get('views30d', '—')} "
                          f"view{recent_n}={acc.get('views', '—')} nước={acc.get('country', '—')} - {r.get('msg', '')} [{r.get('src', '')}]")
        finally:
            self.scanning = False
            print("[SCAN] Quét info hoàn tất!")
            self._notify_done(
                "Quét Info",
                f"✅ Đã quét info xong {len(targets)} account!")

    def _pick_checker_file(self):
        f = filedialog.askopenfilename(
            title="Chọn file cookie TRUNG GIAN (mỗi dòng 1 cookie của acc khác)",
            filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if f:
            self.checker_file_var.set(f)
            self._persist_settings()
            print(f"[OK] File cookie trung gian: {f}")

    # ---------- Auto Login (mo file ngoai bang 1 nut bam) ----------
    def _launch_file(self, path, label):
        """Mở 1 file bằng ứng dụng mặc định của Windows (như double-click)."""
        if not path or not Path(path).exists():
            messagebox.showwarning("Không thấy file",
                                   f"Không tìm thấy {label}:\n{path}")
            print(f"[!] Không thấy {label}: {path}")
            return
        try:
            os.startfile(path)  # noqa: chi co tren Windows
            print(f"[OK] Đã mở {label}: {path}")
        except Exception as e:  # noqa
            messagebox.showerror("Lỗi", f"Không mở được {label}:\n{_short(e)}")

    # ---------- Auto Login TAT (engine da gop trong file nay) ----------
    def _run_autologin(self):
        """Nut Chay Auto Login: chay cho account DANG CHON o bang trai
        (Ctrl+A = chon tat ca); khong chon account nao thi chay TAT CA."""
        targets = self._selected_accounts() or list(self.all_accounts)
        self._start_autologin(targets)

    def _run_autologin_selected(self):
        """Chuot phai: chi chay account dang chon."""
        targets = self._selected_accounts()
        if not targets:
            messagebox.showinfo("Auto Login", "Hãy chọn ít nhất 1 account trong bảng!")
            return
        self._start_autologin(targets)

    def _run_autologin_failed(self):
        """Chuot phai: chay lai Auto Login chi cho cac account da chon
        dang o trang thai LOI (cot Auto Login bat dau bang ❌)."""
        targets = [a for a in self._selected_accounts()
                   if str(a.get("alogin", "")).startswith("❌")]
        if not targets:
            messagebox.showinfo(
                "Auto Login",
                "Trong các account đã chọn không có account nào đang LỖI để chạy lại!")
            return
        self._start_autologin(targets)

    def _start_autologin(self, targets):
        global GRID_TOTAL, HIDE_BROWSER
        if self.alogin_running:
            messagebox.showwarning("Cảnh báo", "Auto Login đang chạy...")
            return
        targets = [a for a in (targets or []) if a.get("id")]
        if not targets:
            messagebox.showerror("Lỗi", "Chưa có account nào để login!")
            return
        threads = max(1, min(int(self.alogin_threads_var.get() or 1), len(targets)))
        delay = max(0, int(self.alogin_delay_var.get() or 0))
        GRID_TOTAL = max(1, threads)
        HIDE_BROWSER = bool(self.hide_browser_var.get())
        _set_launch_delay(delay)
        _update_settings({"alogin_threads": threads, "alogin_delay": delay})
        self.stop_requested = False
        clear_engine_stop()
        self.alogin_running = True
        print(f"[TAT] ▶ Auto Login {len(targets)} account - {threads} luồng - "
              f"delay mở {delay}s/profile"
              + (" - ẨN trình duyệt" if HIDE_BROWSER else "")
              + ". Login thành công sẽ tự xuất cookie vào bảng.")
        threading.Thread(target=self._alogin_worker, args=(targets, threads),
                         daemon=True).start()

    def _alogin_set_status(self, acc, text):
        acc["alogin"] = text
        _save_stats_cache(acc["id"], {"alogin": text})
        self._ui(lambda a=acc: self._refresh_acc_row(a))

    def _alogin_worker(self, targets, threads):
        done = {"n": 0, "ok": 0, "cookie": False}
        try:
            with ThreadPoolExecutor(max_workers=threads) as ex:
                futs = {ex.submit(self._alogin_one, acc): acc for acc in targets}
                for fut in as_completed(futs):
                    acc = futs[fut]
                    try:
                        ok, has_cookie = fut.result()
                    except Exception as e:  # noqa
                        ok, has_cookie = False, False
                        print(f"[TAT] ❌ @{acc['id']}: lỗi luồng - {_short(e)}")
                    done["n"] += 1
                    if ok:
                        done["ok"] += 1
                    if has_cookie:
                        done["cookie"] = True
                    print(f"[TAT] ({done['n']}/{len(targets)}) @{acc['id']}: "
                          f"{acc.get('alogin', '')}")
            if done["cookie"]:
                self._save_accounts()
                print("[TAT] Đã ghi cookie mới vào accounts.txt")
        finally:
            self.alogin_running = False
            print(f"[TAT] Hoàn tất Auto Login: {done['ok']}/{len(targets)} thành công.")
            self._notify_done(
                "Auto Login TAT",
                ("⏹ Đã dừng Auto Login theo yêu cầu.\n"
                 if self.stop_requested else "✅ Auto Login đã xong!\n")
                + f"Thành công: {done['ok']}/{len(targets)} account"
                + ("\nCookie mới đã lưu vào accounts.txt." if done["cookie"] else ""))

    def _alogin_one(self, acc):
        """Login 1 account (có tự chạy lại): lần 1 lỗi thì trình duyệt đã
        đóng sạch trong _alogin_attempt -> TỰ CHẠY LẠI LẦN 2; lần 2 vẫn
        lỗi thì giữ trạng thái lỗi và bỏ qua account (user yêu cầu). Lỗi
        thiếu dữ liệu trong bảng thì không chạy lại (chạy lại cũng lỗi)."""
        ok, has_cookie = self._alogin_attempt(acc)
        if ok or self.stop_requested:
            return ok, has_cookie
        _st = str(acc.get("alogin", ""))
        if _st.startswith("\u23f9") or "bảng thiếu" in _st:
            return ok, has_cookie
        print(f"[TAT] @{acc.get('id')}: ❌ login lỗi lần 1 - tự chạy lại lần 2...")
        self._alogin_set_status(acc, "🔁 Đang login lại (lần 2)...")
        ok, has_cookie = self._alogin_attempt(acc)
        if not ok and not self.stop_requested:
            print(f"[TAT] @{acc.get('id')}: vẫn lỗi ở lần 2 - giữ lỗi, bỏ qua account này.")
        return ok, has_cookie

    def _alogin_attempt(self, acc):
        """1 lần login: mở profile GPM (như xuất cookie) -> chạy engine
        TAT -> thành công thì xuất cookie thẳng vào bảng + accounts.txt.
        Trả (ok, có_cookie_mới)."""
        if self.stop_requested:
            self._alogin_set_status(acc, "⏹ Đã dừng")
            return False, False
        self._alogin_set_status(acc, "🔄 Đang login...")
        # Du lieu login lay TRUC TIEP tu cac cot cua bang (khong qua Excel):
        # Email / Refresh Token / Client ID thieu thi bao loi ngay o cot
        # Auto Login, thay vi im lang roi nhay sang khoi phuc mail.
        _missing = [lbl for lbl, v in (("Email", acc.get("email")),
                                       ("Refresh Token", acc.get("refresh_token")),
                                       ("Client ID", acc.get("client_id")))
                    if not str(v or "").strip()]
        if _missing:
            self._alogin_set_status(acc, f"❌ Lỗi: bảng thiếu {', '.join(_missing)}")
            print(f"[TAT] @{acc.get('id')}: THIẾU {', '.join(_missing)} trong bảng - "
                  f"bổ sung rồi chạy lại, đừng để nó đi khôi phục mail oan")
            return False, False
        _tok = str(acc.get("refresh_token") or "")
        print(f"[TAT] @{acc.get('id')}: lấy từ bảng -> email={acc.get('email')} | "
              f"client_id={acc.get('client_id')} | refresh_token={_tok[:8]}...({len(_tok)} ký tự)")
        name = parse_line(str(acc.get("id") or ""))["name"]
        _ctx.tag = name
        with _lock_for(name):
            profile_id = _get_profile_id(name)
            if not profile_id:
                self._alogin_set_status(acc, "❌ Lỗi: không thấy profile GPM")
                return False, False
            port = _start_profile(profile_id, _port_for(name))
            if port is None:
                self._alogin_set_status(acc, "❌ Lỗi: không start được profile")
                return False, False
            _register_active_profile(profile_id)
            if not _wait_devtools(port):
                self._alogin_set_status(acc, "❌ Lỗi: DevTools không trả lời")
                _stop_profile(profile_id)
                return False, False
            major, browser_str = _browser_major(port)
            driver_path = _driver_path_for_major(major)
            if not os.path.exists(driver_path):
                self._alogin_set_status(acc, "❌ Lỗi: thiếu gpmdriver")
                _stop_profile(profile_id)
                return False, False
            slot = _claim_slot()
            driver = None
            try:
                svc = Service(executable_path=driver_path)
                opts = Options()
                opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
                driver = webdriver.Chrome(service=svc, options=opts)
                _register_active_driver(name, driver)
                _ensure_page_tab(driver)
                _tile_window(driver, slot)
                ok, result = tat_login(driver, acc)
                has_cookie = False
                if ok:
                    header = _cookies_to_header(driver.get_cookies())
                    if header:
                        acc["cookie"] = header
                        has_cookie = True
                        print(f"[TAT] @{acc['id']}: đã xuất cookie "
                              f"({len(header)} ký tự) vào bảng")
                if self.stop_requested:
                    self._alogin_set_status(acc, "⏹ Đã dừng")
                    return False, has_cookie
                self._alogin_set_status(
                    acc, "✅ Hoàn thành" if ok else f"❌ Lỗi: {str(result)[:60]}")
                return ok, has_cookie
            except Exception as e:  # noqa
                if self.stop_requested:
                    self._alogin_set_status(acc, "⏹ Đã dừng")
                    return False, False
                self._alogin_set_status(acc, f"❌ Lỗi: {_short(e)[:60]}")
                return False, False
            finally:
                if driver is not None:
                    try:
                        driver.quit()
                    except Exception:  # noqa
                        pass
                _unregister_active_driver(name)
                _stop_profile(profile_id)
                _release_slot(slot)

    # ---------- Folder luu video cua Upload Online ----------
    # ---------- May tinh Windows (tinh toan nhanh khi dang lam) ----------
    def _open_calculator(self):
        """Mo Windows Calculator (calc.exe) bang nut 🧮 May tinh ben canh
        nut Xoa list: phuong an 1 goi thang calc.exe, du phong chay qua
        lenh shell 'start'. Mo app ngoai doc lap, khong chan giao dien."""
        try:
            import subprocess
            subprocess.Popen(["calc.exe"])
            print("[OK] \u0110\u00e3 m\u1edf M\u00e1y t\u00ednh (calc.exe)")
            return
        except Exception as e:  # noqa
            print(f"[CALC] G\u1ecdi tr\u1ef1c ti\u1ebfp calc.exe l\u1ed7i: {_short(e)} - th\u1eed qua start...")
        try:
            import subprocess
            subprocess.Popen("start calc.exe", shell=True)
            print("[OK] \u0110\u00e3 m\u1edf M\u00e1y t\u00ednh qua l\u1ec7nh start")
        except Exception as e:  # noqa
            messagebox.showerror("L\u1ed7i", f"Kh\u00f4ng m\u1edf \u0111\u01b0\u1ee3c M\u00e1y t\u00ednh:\n{_short(e)}")

    def _yt_out_dir(self):
        """Thư mục lưu video tải về của Upload Online: ưu tiên ô riêng
        của tab Online; để trống thì dùng Folder Video của Upload Offline."""
        d = (self.yt_folder_var.get() or "").strip()
        return d or (self.folder_var.get() or "").strip()

    def _pick_yt_folder(self):
        f = filedialog.askdirectory(
            title="Chọn folder lưu video tải về (Upload Online)")
        if f:
            self.yt_folder_var.set(f)
            self._persist_settings()
            print(f"[OK] Folder lưu video (Online): {f}")

    # ---------- Tai video YouTube Shorts ----------
    def _yt_download_ids(self, ids, out_dir, api_key, threads):
        """Tải danh sách video ID về out_dir: bỏ video đã có, kiểm tra
        video chết/riêng tư bằng API v3 (nếu có key), yt-dlp tải đa
        luồng có nghỉ ngẫu nhiên."""
        cache = _load_yt_cache()
        row_titles = {r["id"]: (r.get("title") or "")
                      for r in getattr(self, "yt_link_rows", [])}
        todo = []
        for vid in ids:
            if vid in cache:
                continue
            found = _find_downloaded(out_dir, vid, cache)
            if found is not None:
                _save_yt_cache_entry(vid, {
                    "file": found.name,
                    "title": row_titles.get(vid, ""),
                    "ts": int(time.time())})
                continue
            todo.append(vid)
        print(f"[YT] {len(ids)} link hợp lệ - đã có {len(ids) - len(todo)}, "
              f"cần tải {len(todo)}")
        if not todo:
            print("[YT] Tất cả đã tải xong từ trước, không cần tải lại.")
            return
        meta = {}
        if api_key:
            try:
                meta, calls = fetch_yt_metadata(api_key, todo)
                print(f"[YT] API v3: lấy info {len(meta)}/{len(todo)} video, "
                      f"tốn {calls} quota (1 quota check được 50 video)")
            except Exception as e:  # noqa
                print(f"[YT] Lỗi API v3: {_short(e)} - vẫn tải tiếp, không lọc.")
                meta = {}
        queue_ids = []
        for vid in todo:
            if meta and meta.get(vid) is None:
                print(f"[YT] Bỏ qua {vid}: không lấy được info "
                      f"(video riêng tư/đã xoá?)")
                continue
            queue_ids.append(vid)
        if not queue_ids:
            print("[YT] Không còn video nào cần tải sau khi lọc.")
            return
        print(f"[YT] Bắt đầu tải {len(queue_ids)} video - {threads} luồng, "
              f"nghỉ ngẫu nhiên 1-4s giữa mỗi video để tránh bị chặn nhịp")
        total = len(queue_ids)
        state = {"n": 0, "ok": 0, "fail": 0}

        def job(vid):
            time.sleep(random.uniform(1, 4))
            last = {"pct": -25}

            def cb(pct):
                if pct - last["pct"] >= 25:
                    last["pct"] = pct
                    print(f"[YT] {vid} ... {pct}%")

            dl_title = (row_titles.get(vid)
                        or (meta.get(vid) or {}).get("title", ""))
            ok, res = download_one_yt(vid, out_dir, cb, title=dl_title)
            state["n"] += 1
            if ok:
                state["ok"] += 1
                _save_yt_cache_entry(vid, {
                    "file": Path(res).name,
                    "title": (meta.get(vid) or {}).get("title", ""),
                    "ts": int(time.time())})
                print(f"[YT] ({state['n']}/{total}) ✅ {vid} - "
                      f"{(meta.get(vid) or {}).get('title', '')[:60]}")
            else:
                state["fail"] += 1
                print(f"[YT] ({state['n']}/{total}) ❌ {vid}: {res}")

        with ThreadPoolExecutor(max_workers=threads) as ex:
            list(ex.map(job, queue_ids))
        print(f"[YT] Xong! Đã tải {state['ok']} video vào {out_dir} - "
              f"lỗi {state['fail']}. Bấm 'Scan & Load' ở Folder Video "
              f"để đưa vào danh sách upload.")
    # ---------- Lay list link tu kenh YouTube ----------
    def _start_search_channels(self):
        """Quét list KÊNH từ link search YouTube: giải mã từ khoá trong
        link, quét các video của trang kết quả và gom các kênh khác
        nhau đứng sau chúng, xuất file txt rồi tự mở file lên."""
        if getattr(self, "yt_searching", False):
            messagebox.showwarning("Cảnh báo", "Đang quét kênh từ search...")
            return
        api_key = self._yt_active_key()
        if not api_key:
            messagebox.showerror(
                "Thiếu API key",
                "Quét kênh từ search bắt buộc có YT API Key.")
            return
        query = _query_from_search_input(self.yt_search_var.get())
        if not query:
            messagebox.showerror(
                "Lỗi", "Chưa nhập link search YouTube (hoặc gõ thẳng "
                       "từ khoá)!")
            return
        self._persist_settings()
        limit = max(1, self.yt_search_count_var.get())
        mode = self.yt_mode_var.get()
        self.yt_searching = True
        print(f"[YT] Quét kênh từ search: từ khoá '{query}' - lấy tối đa "
              f"{limit} kênh ({'Shorts' if mode == 'shorts' else 'video dài'})...")
        threading.Thread(target=self._search_channels_worker,
                         args=(api_key, query, limit, mode),
                         daemon=True).start()

    def _search_channels_worker(self, api_key, query, limit, mode):
        try:
            found = search_channels_from_videos(api_key, query, limit)
            ids = [cid for cid, _t in found]
            handles = fetch_channel_handles(api_key, ids) if ids else {}
            tab = "shorts" if mode == "shorts" else "videos"
            lines = []
            for cid in ids:
                handle = (handles.get(cid) or (None, ""))[0]
                if handle:
                    h = handle if handle.startswith("@") else "@" + handle
                    lines.append(f"https://www.youtube.com/{h}/{tab}")
                else:
                    lines.append(
                        f"https://www.youtube.com/channel/{cid}/{tab}")
            safe = re.sub(r'[\\/:*?"<>|]', "_", query).strip()[:40] \
                or "channels"
            path = APP_DIR / f"yt_search_{safe}.txt"
            path.write_text("\n".join(lines), encoding="utf-8")
            dup_n = 0
            for ln in lines:
                if self._find_channel_history(_channel_url_key(ln, mode)):
                    dup_n += 1
            print(f"[YT] Quét search xong: gom được {len(lines)} kênh "
                  f"từ các video kết quả -> {path.name}"
                  + (f" (trong đó {dup_n} kênh đã lấy list trước đây)"
                     if dup_n else ""))
            if lines:
                self._ui(lambda p=str(path):
                         self._launch_file(p, "file danh sách kênh"))
                self._notify_done(
                    "Quét kênh từ Search",
                    f"✅ Đã quét được {len(lines)} kênh cho từ khoá "
                    f"'{query}'.\nĐã lưu và mở file: {path.name}"
                    + (f"\nTrong đó {dup_n} kênh đã lấy list trước đây "
                       f"(khi lấy list sẽ tự bỏ qua)." if dup_n else ""))
            else:
                self._notify_done(
                    "Quét kênh từ Search",
                    f"Không tìm thấy kênh nào cho từ khoá '{query}'.")
        except Exception as e:  # noqa
            print(f"[YT] Lỗi quét kênh từ search: {_short(e)}")
            self._ui(lambda m=_short(e):
                     messagebox.showerror("Lỗi quét kênh", m))
        finally:
            self.yt_searching = False

    def _find_channel_history(self, key):
        """Tim 1 khoa kenh trong lich su da lay list (khong phan biet
        khoa la link hay UC id - entry luu ca 2)."""
        for e in self.yt_channel_history or []:
            if key in (e.get("keys") or []):
                return e
        return None

    def _record_channel_history(self, url_text, channel_id, mode, count,
                                name, tag=None):
        """Luu 1 kenh vua lay list thanh cong vao lich su (settings
        yt_channel_history) de lan sau dan trung la bo qua.
        tag="master": kenh moi duoc danh cho trong FILE TONG (tab
        Upload Acc/Kenh quet kenh) - chua lay list, chi giu cho."""
        keys = []
        for k in (_channel_url_key(url_text, mode),
                  f"{channel_id}|{mode}"):
            if k and k not in keys:
                keys.append(k)
        self.yt_channel_history = [
            e for e in (self.yt_channel_history or [])
            if not (set(e.get("keys") or []) & set(keys))]
        entry = {"keys": keys, "url": url_text, "channel_id": channel_id,
                 "mode": mode, "ts": int(time.time()), "count": count,
                 "name": name}
        if tag:
            entry["tag"] = tag
        self.yt_channel_history.append(entry)
        _update_settings({"yt_channel_history": self.yt_channel_history})

    def _start_fetch_channel(self):
        if self.yt_fetching:
            messagebox.showwarning("Cảnh báo", "Đang lấy list link...")
            return
        api_key = self._yt_active_key()
        if not api_key:
            messagebox.showerror(
                "Thiếu API key",
                "Lấy list từ kênh bắt buộc có YT API Key (để trống không lấy được).")
            return
        raw = (self.yt_channel_text.get("1.0", "end")
               if hasattr(self, "yt_channel_text") else "")
        lines, seen_line = [], set()
        for ln in raw.splitlines():
            ln = ln.strip()
            if ln and ln.lower() not in seen_line:
                seen_line.add(ln.lower())
                lines.append(ln)
        if not lines:
            messagebox.showerror("Lỗi", "Chưa nhập link kênh YouTube!")
            return
        self._persist_settings()
        todo, dups = [], []
        for ln in lines:
            mode = _mode_from_channel_url(ln) or self.yt_mode_var.get()
            dup = self._find_channel_history(_channel_url_key(ln, mode))
            if dup:
                dups.append((ln, mode, dup))
            else:
                todo.append((ln, mode))
        for ln, mode, dup in dups:
            when = time.strftime("%d/%m %H:%M",
                                 time.localtime(dup.get("ts") or 0))
            print(f"[YT] TRÙNG KÊNH - bỏ qua: {ln} "
                  f"({'Shorts' if mode == 'shorts' else 'video dài'}) "
                  f"đã lấy lúc {when} ({dup.get('count', 0)} link)")
        if not todo:
            messagebox.showwarning(
                "Trùng kênh - đã lấy list rồi",
                "Tất cả kênh bạn dán đều ĐÃ LẤY LIST RỒI nên tool không "
                "lấy lại để tránh trùng link.\n\n"
                + "\n".join(f"- {ln}" for ln, _, _ in dups[:8])
                + ("\n..." if len(dups) > 8 else ""))
            return
        if dups:
            print(f"[YT] Bỏ qua {len(dups)} kênh trùng, lấy "
                  f"{len(todo)} kênh còn lại.")
        self.yt_fetching = True
        self.yt_list_info_var.set("Đang lấy list...")
        threading.Thread(
            target=self._fetch_channel_worker,
            args=(api_key, todo, max(1, self.yt_count_var.get())),
            daemon=True).start()

    def _fetch_channel_worker(self, api_key, channels, limit):
        """Worker lấy list NHIỀU kênh: mỗi kênh lấy tối đa `limit` video,
        link của mọi kênh DỒN VÀO 1 BẢNG (khử trùng theo video id).
        Kênh nào trùng lịch sử (theo UC id) hoặc lỗi thì bỏ qua, các
        kênh còn lại vẫn lấy tiếp."""
        all_rows = []
        seen_ids = set()
        total_quota = 0
        fetched_names = []
        try:
            for idx, (channel_text, mode) in enumerate(channels, 1):
                try:
                    channel_id = resolve_channel_id(api_key, channel_text)
                except Exception as e:  # noqa
                    print(f"[YT] ({idx}/{len(channels)}) Lỗi tra kênh "
                          f"{channel_text}: {_short(e)} - bỏ qua kênh này")
                    continue
                dup = self._find_channel_history(f"{channel_id}|{mode}")
                if dup:
                    when = time.strftime(
                        "%d/%m %H:%M",
                        time.localtime(dup.get("ts") or 0))
                    print(f"[YT] ({idx}/{len(channels)}) TRÙNG KÊNH - "
                          f"bỏ qua: {channel_text} (đã lấy lúc {when}, "
                          f"{dup.get('count', 0)} link)")
                    continue
                handle = re.search(r"@([A-Za-z0-9._-]+)", channel_text)
                name = handle.group(1) if handle else channel_id
                print(f"[YT] ({idx}/{len(channels)}) Kênh {name} "
                      f"({channel_id}) - lấy tối đa {limit} video "
                      f"{'Shorts' if mode == 'shorts' else 'dài'}...")
                try:
                    ids, calls = fetch_channel_video_ids(
                        api_key, channel_id, mode, limit)
                except Exception as e:  # noqa
                    print(f"[YT] ({idx}/{len(channels)}) Lỗi lấy list "
                          f"kênh {name}: {_short(e)} - bỏ qua kênh này")
                    continue
                total_quota += calls
                new_ids = [v for v in ids if v not in seen_ids]
                for v in new_ids:
                    seen_ids.add(v)
                ch_file = APP_DIR / f"yt_links_{name}.txt"
                try:
                    ch_file.write_text(
                        "\n".join(f"https://www.youtube.com/watch?v={v}"
                                   for v in ids), encoding="utf-8")
                except Exception:  # noqa
                    pass
                meta = {}
                if ids:
                    try:
                        meta, used = fetch_yt_metadata(api_key, ids)
                        total_quota += used
                    except Exception as e:  # noqa
                        print(f"[YT] Không lấy được tiêu đề/thời lượng "
                              f"kênh {name}: {_short(e)}")
                for v in new_ids:
                    all_rows.append(
                        {"id": v, "kind": mode,
                         "title": (meta.get(v) or {}).get("title", ""),
                         "duration": (meta.get(v) or {}).get("duration")})
                print(f"[YT] ({idx}/{len(channels)}) {name}: lấy "
                      f"{len(ids)} link ({len(new_ids)} link mới) - "
                      f"tổng dồn {len(all_rows)} link")
                self._ui(lambda i=idx, t=len(channels), n=len(all_rows):
                         self.yt_list_info_var.set(
                             f"Kênh {i}/{t} - tổng {n} link"))
                if ids:
                    fetched_names.append(name)
                    self._ui(lambda u=channel_text, cid=channel_id,
                             md=mode, n=len(ids), nm=name:
                             self._record_channel_history(u, cid, md,
                                                          n, nm))
            self.yt_fetched_ids = [r["id"] for r in all_rows]
            if not all_rows:
                print("[YT] Không lấy được link nào (kênh trùng/lỗi hết).")
                self._ui(lambda: self.yt_list_info_var.set(
                    "Không lấy được link nào"))
                return
            if len(fetched_names) == 1:
                list_name = fetched_names[0]
                list_file = APP_DIR / f"yt_links_{fetched_names[0]}.txt"
            else:
                list_name = (f"{fetched_names[0]} "
                             f"(+{len(fetched_names) - 1} kênh)")
                list_file = (APP_DIR /
                             f"yt_links_{fetched_names[0]}_multi.txt")
                try:
                    list_file.write_text(
                        "\n".join(
                            f"https://www.youtube.com/watch?v={r['id']}"
                            for r in all_rows), encoding="utf-8")
                except Exception:  # noqa
                    pass
            self._ui(lambda f=str(list_file):
                     self.yt_links_file_var.set(f))
            print(f"[YT] Xong: dồn {len(all_rows)} link từ "
                  f"{len(fetched_names)} kênh vào 1 bảng "
                  f"(tốn {total_quota} quota) - list '{list_name}'.")
            self._ui(lambda n=len(all_rows): self.yt_list_info_var.set(
                f"Đã lấy {n} link"))
            part_files = ([str(APP_DIR / f"yt_links_{n}.txt")
                           for n in fetched_names]
                          if len(fetched_names) > 1 else None)
            self._ui(lambda r=all_rows, nm=list_name, lf=str(list_file),
                     pf=part_files:
                     self._apply_link_rows(r, nm, lf, parts=pf))
        except Exception as e:  # noqa
            print(f"[YT] Lỗi lấy list kênh: {_short(e)}")
            self._ui(lambda: self.yt_list_info_var.set("Lấy list lỗi"))
        finally:
            self.yt_fetching = False

    # ================= TAB UPLOAD Acc/Kênh (v3.84) =================
    # Luồng MỚI chạy song song tab Upload Online cũ (không thay thế):
    # (1) quét kênh Shorts > 200 video -> dồn vào 1 file tổng;
    # (2) gán kênh 1-1 cho từng acc TikTok, mỗi acc quét FULL Shorts
    # của kênh mình -> file yt_acc_shorts/<username>.txt, dòng 1 của
    # file là LINK KÊNH (tool tự bỏ qua khi chạy, không up nhầm);
    # (3) upload thành công link nào thì xoá link đó khỏi file của acc.

    def _build_akc_tab(self, tab):
        f = ttk.Frame(tab)
        f.pack(fill="both", expand=True)
        g1 = ttk.LabelFrame(
            f, text="1) Quét kênh Shorts (chỉ lấy kênh có trên 200 "
                    "video Shorts) -> File tổng")
        g1.pack(fill="x", padx=5, pady=(5, 2))
        r1 = ttk.Frame(g1)
        r1.pack(fill="x", padx=5, pady=3)
        ttk.Label(r1, text="Link search / từ khoá:").pack(side="left")
        ttk.Entry(r1, textvariable=self.akc_search_var,
                  width=38).pack(side="left", padx=4)
        ttk.Label(r1, text="Số kênh quét:").pack(side="left")
        ttk.Spinbox(r1, from_=1, to=500, width=6,
                    textvariable=self.akc_search_count_var).pack(
                        side="left", padx=4)
        ttk.Label(r1, text="Luồng quét:").pack(side="left")
        ttk.Spinbox(r1, from_=1, to=20, width=4,
                    textvariable=self.akc_scan_threads_var).pack(
                        side="left", padx=4)
        ttk.Button(r1, text="🔍 Quét kênh -> File tổng",
                   command=self._akc_start_search).pack(side="left", padx=6)
        ttk.Button(r1, text="⏹ Dừng quét",
                   command=self._akc_stop_scans).pack(side="left", padx=2)
        r1b = ttk.Frame(g1)
        r1b.pack(fill="x", padx=5, pady=(0, 4))
        ttk.Label(r1b, textvariable=self.akc_master_info_var).pack(
            side="left")
        ttk.Button(r1b, text="📂 Mở file tổng",
                   command=lambda: self._launch_file(
                       str(AKC_MASTER_PATH), "file tổng kênh")).pack(
                           side="left", padx=6)
        ttk.Button(r1b, text="Nạp kênh từ file tổng",
                   command=self._akc_load_master_to_box).pack(
                       side="left", padx=2)
        g2 = ttk.LabelFrame(
            f, text="2) Gán kênh 1-1 cho Account + quét FULL Shorts "
                    "-> file theo Acc")
        g2.pack(fill="both", expand=True, padx=5, pady=2)
        r2 = ttk.Frame(g2)
        r2.pack(fill="x", padx=5, pady=(3, 0))
        ttk.Label(r2, text="Danh sách kênh (mỗi dòng 1 link kênh):"
                  ).pack(side="left")
        self.akc_channel_text = tk.Text(g2, width=72, height=5)
        self.akc_channel_text.pack(fill="x", padx=5, pady=3)
        if AKC_MASTER_PATH.exists():
            try:
                self.akc_channel_text.insert(
                    "1.0", AKC_MASTER_PATH.read_text(
                        encoding="utf-8", errors="ignore"))
            except Exception:  # noqa
                pass
        r4 = ttk.Frame(g2)
        r4.pack(fill="x", padx=5, pady=(2, 4))
        ttk.Button(r4, text="🎯 Gán kênh + Quét FULL Shorts theo Acc",
                   style="Accent.TButton",
                   command=self._akc_start_assign_scan).pack(
                       side="left", padx=4)
        ttk.Button(r4, text="⏹ Dừng quét",
                   command=self._akc_stop_scans).pack(
                       side="left", padx=2)
        ttk.Button(r4, text="🔁 Đổi kênh cho acc đã chọn",
                   command=self._akc_swap_channels_clicked).pack(
                       side="left", padx=2)
        ttk.Button(r4, text="📂 Mở thư mục file Acc",
                   command=self._akc_open_acc_dir).pack(
                       side="left", padx=4)
        ttk.Label(r4, text="Luồng quét:").pack(side="left", padx=(10, 0))
        ttk.Spinbox(r4, from_=1, to=20, width=4,
                    textvariable=self.akc_scan_threads_var).pack(
                        side="left", padx=2)
        r4b = ttk.Frame(g2)
        r4b.pack(fill="x", padx=5, pady=(0, 4))
        ttk.Button(r4b, text="🔍 Check acc chưa có file Shorts",
                   command=self._akc_check_missing_files).pack(
                       side="left", padx=4)
        ttk.Button(r4b, text="🗂 Pool kênh dự bị",
                   command=self._akc_show_pool_file).pack(
                       side="left", padx=4)
        ttk.Label(r4b, text="(tô đen sẵn trong bảng Account bên trái "
                            "các acc chưa có file / đã hết link - để "
                            "chạy Gán kênh + Quét tiếp)").pack(
                                side="left", padx=2)
        g3 = ttk.LabelFrame(f, text="3) Chạy upload theo phần gán Acc/Kênh")
        g3.pack(fill="x", padx=5, pady=2)
        # Hàng thông số chạy đặt NGAY ở mục 3, cạnh nút START (v3.85)
        r3 = ttk.Frame(g3)
        r3.pack(fill="x", padx=5, pady=(3, 0))
        ttk.Label(r3, text="Video/Acc mỗi lần chạy:").pack(side="left")
        ttk.Spinbox(r3, from_=1, to=50, width=4,
                    textvariable=self.akc_per_acc_var).pack(
                        side="left", padx=4)
        ttk.Label(r3, text="Luồng upload:").pack(side="left",
                                                 padx=(12, 0))
        ttk.Spinbox(r3, from_=1, to=10, width=4,
                    textvariable=self.akc_threads_var).pack(
                        side="left", padx=4)
        ttk.Label(r3, text="Delay mở trình duyệt (giây):").pack(
            side="left", padx=(12, 0))
        ttk.Spinbox(r3, from_=0, to=300, width=4,
                    textvariable=self.akc_delay_var).pack(
                        side="left", padx=4)
        r5 = ttk.Frame(g3)
        r5.pack(fill="x", padx=5, pady=3)
        ttk.Button(r5, text="▶ START Upload", style="Accent.TButton",
                   command=self._akc_start_upload).pack(
                       side="left", padx=4)
        ttk.Button(r5, text="⏹ STOP",
                   command=self._stop_all_runs).pack(side="left", padx=2)
        ttk.Checkbutton(r5, text="Tự xoá cache TikTok khi account upload xong",
                        variable=self.clean_cache_var,
                        command=self._persist_settings).pack(
                            side="left", padx=10)
        ttk.Label(r5, textvariable=self.akc_info_var).pack(
            side="left", padx=8)
        ttk.Label(g3, text="Cách chạy: Tô đen các account trong "
                           "bảng account bên trái rồi bấm START - "
                           "Tool sẽ tự lấy link của file shorts đã "
                           "gán. Upload xong sẽ tự xóa link đó ra "
                           "khỏi file txt.",
                  wraplength=900, justify="left").pack(
                      fill="x", padx=5, pady=(0, 4))
        self._akc_refresh_master_info()

    def _akc_open_acc_dir(self):
        AKC_ACC_DIR.mkdir(parents=True, exist_ok=True)
        self._launch_file(str(AKC_ACC_DIR), "thư mục file Acc")

    def _akc_refresh_master_info(self):
        n = 0
        if AKC_MASTER_PATH.exists():
            try:
                n = sum(1 for ln in AKC_MASTER_PATH.read_text(
                    encoding="utf-8", errors="ignore").splitlines()
                    if ln.strip())
            except Exception:  # noqa
                n = 0
        self.akc_master_info_var.set(
            f"File tổng: {AKC_MASTER_PATH.name} - hiện có {n} kênh "
            f"(chỉ kênh > {AKC_MIN_SHORTS} Shorts)")

    def _akc_load_master_to_box(self):
        if not AKC_MASTER_PATH.exists():
            messagebox.showinfo("File tổng",
                                "Chưa có file tổng - hãy Quét kênh trước!")
            return
        txt = AKC_MASTER_PATH.read_text(encoding="utf-8",
                                        errors="ignore")
        self.akc_channel_text.delete("1.0", "end")
        self.akc_channel_text.insert("1.0", txt)
        n = sum(1 for ln in txt.splitlines() if ln.strip())
        print(f"[AKC] Đã nạp {n} kênh từ file tổng xuống ô danh sách kênh.")

    # --- 1) Quét kênh theo search -> lọc > 200 Shorts -> file tổng ---
    def _akc_show_scan_notice(self, what):
        """Vừa bấm quét -> mở luôn cửa sổ Log tiến trình để người
        dùng thấy ngay là tool đang quét và theo dõi được tiến
        trình (log mới vẫn chảy tiếp vào cửa sổ khi đang mở; cửa
        sổ đã mở rồi thì chỉ đưa lên trước)."""
        print(f"[AKC] {what} - theo dõi tiến trình trong cửa sổ "
              f"Log này (hoặc nút 📜 Log tiến trình ở thanh dưới).")
        try:
            self._open_log_window()
        except Exception:  # noqa
            pass

    def _akc_start_search(self):
        if self.akc_searching:
            messagebox.showwarning("Cảnh báo",
                                   "Đang quét kênh (tab Acc/Kênh)...")
            return
        api_key = self._yt_active_key()
        if not api_key:
            messagebox.showerror(
                "Thiếu API key",
                "Quét kênh bắt buộc có YT API Key (nhập ở tab "
                "Upload Chung File).")
            return
        query = _query_from_search_input(self.akc_search_var.get())
        if not query:
            messagebox.showerror(
                "Lỗi", "Chưa nhập link search YouTube (hoặc gõ thẳng "
                       "từ khoá)!")
            return
        _update_settings({"akc_search": self.akc_search_var.get(),
                          "akc_search_count":
                              self.akc_search_count_var.get(),
                          "akc_scan_threads":
                              self.akc_scan_threads_var.get()})
        limit = max(1, self.akc_search_count_var.get())
        threads = max(1, self.akc_scan_threads_var.get())
        self.stop_requested = False
        self.akc_searching = True
        print(f"[AKC] Quét kênh từ search: '{query}' - tối đa {limit} "
              f"kênh, chỉ giữ kênh có > {AKC_MIN_SHORTS} Shorts "
              f"-> file tổng...")
        threading.Thread(target=self._akc_search_worker,
                         args=(api_key, query, limit, threads),
                         daemon=True).start()
        self._akc_show_scan_notice("🔍 ĐANG QUÉT KÊNH -> file tổng")

    def _akc_search_worker(self, api_key, query, limit, threads=5):
        try:
            found = search_channels_from_videos(api_key, query, limit)
            ids = [cid for cid, _t in found]
            handles = fetch_channel_handles(api_key, ids) if ids else {}
            # Khoá các kênh đã có trong file tổng (chống trùng kênh)
            master_keys = set()
            if AKC_MASTER_PATH.exists():
                for ln in AKC_MASTER_PATH.read_text(
                        encoding="utf-8", errors="ignore").splitlines():
                    k = _channel_url_key(ln, "shorts")
                    if k:
                        master_keys.add(k)
            # Tách kênh trùng trước (không tốn API); phần ĐẾM số
            # Shorts của từng kênh chạy SONG SONG nhiều luồng cho
            # nhanh (đây là chỗ chậm nhất khi quét nhiều kênh).
            cand = []
            cand_keys = set()
            skip_dup = 0
            for cid in ids:
                handle = (handles.get(cid) or (None, ""))[0]
                if handle:
                    h = handle if handle.startswith("@") \
                        else "@" + handle
                    link = f"https://www.youtube.com/{h}/shorts"
                else:
                    link = (f"https://www.youtube.com/channel/{cid}"
                            f"/shorts")
                key = _channel_url_key(link, "shorts")
                if key in master_keys or key in cand_keys or \
                        self._find_channel_history(f"{cid}|shorts"):
                    skip_dup += 1
                    print(f"[AKC] TRÙNG KÊNH - bỏ qua: {link} "
                          f"(đã có trong file tổng / lịch sử quét)")
                    continue
                cand_keys.add(key)
                cand.append((cid, link, key, handle))
            counts = {}
            if cand:
                print(f"[AKC] Đếm Shorts của {len(cand)} kênh bằng "
                      f"{threads} luồng song song...")
                with ThreadPoolExecutor(max_workers=threads) as ex:
                    futs = {ex.submit(count_playlist_videos,
                                       api_key, cid, "shorts"): cid
                            for cid, _l, _k, _h in cand}
                    for fut in as_completed(futs):
                        if getattr(self, "stop_requested", False):
                            print("[AKC] ⏹ STOP - dừng quét kênh.")
                            for f in futs:
                                f.cancel()
                            break
                        _cid = futs[fut]
                        try:
                            counts[_cid] = fut.result()
                        except Exception:  # noqa
                            counts[_cid] = None
            new_lines, kept_info, kept, skip_low = [], [], 0, 0
            for cid, link, key, handle in cand:
                if cid not in counts:
                    continue  # đã bấm STOP giữa chừng - bỏ phần còn lại
                cnt = counts[cid]
                if cnt is None or cnt <= AKC_MIN_SHORTS:
                    skip_low += 1
                    print(f"[AKC] Bỏ kênh {link}: "
                          f"{cnt if cnt is not None else '?'} Shorts "
                          f"(phải > {AKC_MIN_SHORTS})")
                    continue
                master_keys.add(key)
                new_lines.append(link)
                kept_info.append((link, cid, cnt, handle or cid))
                kept += 1
                print(f"[AKC] + Kênh đạt: {link} ({cnt} Shorts)")
            if new_lines:
                old = ""
                if AKC_MASTER_PATH.exists():
                    old = AKC_MASTER_PATH.read_text(
                        encoding="utf-8", errors="ignore")
                with open(AKC_MASTER_PATH, "a",
                          encoding="utf-8") as fh:
                    if old and not old.endswith("\n"):
                        fh.write("\n")
                    fh.write("\n".join(new_lines) + "\n")
                # Lưu LỊCH SỬ các kênh vừa vào file tổng (thẻ "master")
                # để lần quét sau trùng là báo + bỏ qua, và các luồng
                # khác cũng không lấy trùng kênh này.
                for _link, _cid, _cnt, _nm in kept_info:
                    self._ui(lambda u=_link, c=_cid, n=_cnt, nm=_nm:
                             self._record_channel_history(
                                 u, c, "shorts", n, nm, tag="master"))
            total = len(master_keys)
            print(f"[AKC] Quét xong: {len(ids)} kênh từ search -> "
                  f"{kept} kênh mới đạt (> {AKC_MIN_SHORTS} Shorts), "
                  f"bỏ {skip_low} kênh ít Shorts, bỏ {skip_dup} kênh "
                  f"trùng/đã dùng. File tổng hiện có {total} kênh.")
            self._ui(self._akc_refresh_master_info)
            if new_lines:
                self._ui(lambda p=str(AKC_MASTER_PATH):
                         self._launch_file(p, "file tổng kênh"))
            self._notify_done(
                "Quét kênh (Acc/Kênh)",
                f"✅ Thêm {kept} kênh mới (> {AKC_MIN_SHORTS} Shorts) "
                f"vào file tổng.\n"
                f"Bỏ: {skip_low} kênh ít Shorts, {skip_dup} kênh "
                f"trùng/đã dùng.\n"
                f"File tổng hiện có {total} kênh: "
                f"{AKC_MASTER_PATH.name}")
        except Exception as e:  # noqa
            print(f"[AKC] Lỗi quét kênh: {_short(e)}")
            self._ui(lambda m=_short(e):
                     messagebox.showerror("Lỗi quét kênh", m))
        finally:
            self.akc_searching = False

    # --- 2) Gán kênh 1-1 cho acc + quét FULL Shorts -> file theo acc ---
    # ---------- Tu cap nhat tu GitHub (v4.03) ----------
    def _check_update(self):
        """Nút ⬆ Update: lấy link cập nhật (settings 'update_url'
        hoặc hằng TAT_UPDATE_URL); chưa có link thì mở hộp hỏi
        link 1 lần. Có link rồi thì tải file mới về so version."""
        url = ""
        try:
            url = (_load_settings().get("update_url", "")
                   or "").strip()
        except Exception:  # noqa
            url = ""
        if not url:
            url = (TAT_UPDATE_URL or "").strip()
        if not url:
            self._ask_update_url()
            return
        print("[UPDATE] Đang kiểm tra bản mới trên GitHub...")
        threading.Thread(target=self._update_fetch, args=(url,),
                         daemon=True).start()

    def _ask_update_url(self):
        """Hộp dán link Raw GitHub (chỉ hỏi 1 lần, lưu settings).
        Cách lấy link: tạo repo Public trên github.com, upload
        file 'TAT Tool.py' lên, mở file đó rồi bấm nút Raw, copy
        link trên thanh địa chỉ dán vào đây."""
        win = tk.Toplevel(self.root)
        win.title("⬆ Update - dán link cập nhật (1 lần duy nhất)")
        win.geometry("620x300")
        win.grab_set()
        ttk.Label(
            win, wraplength=590,
            text="Chưa có link cập nhật. Cách lấy link (làm 1 lần "
                 "duy nhất):\n"
                 "1) Vào github.com, tạo 1 Repository mới, chọn "
                 "Public.\n"
                 "2) Upload file TAT Tool.py lên repo đó.\n"
                 "3) Mở file vừa upload trên GitHub, bấm nút "
                 "'Raw' ở góc phải, copy link trên thanh địa chỉ "
                 "rồi dán vào ô dưới.\n"
                 "Từ nay mỗi khi có bản mới: chỉ cần upload đè "
                 "file lên GitHub, các PC mở tool bấm nút "
                 "⬆ Update là tự cập nhật.").pack(
                     fill="x", padx=10, pady=8)
        var = tk.StringVar()
        ttk.Entry(win, textvariable=var, width=86).pack(
            fill="x", padx=10, pady=4)

        def do_save():
            u = var.get().strip()
            if not u:
                messagebox.showwarning(
                    "Thiếu link", "Hãy dán link Raw GitHub vào ô "
                    "trước!", parent=win)
                return
            _update_settings({"update_url": u})
            print(f"[UPDATE] Đã lưu link cập nhật: {u}")
            win.destroy()
            self._check_update()

        brow = ttk.Frame(win)
        brow.pack(fill="x", padx=10, pady=10)
        ttk.Button(brow, text="Lưu link + Kiểm tra ngay",
                   padding=(14, 6),
                   command=do_save).pack(side="left", padx=4)
        ttk.Button(brow, text="Huỷ", padding=(14, 6),
                   command=win.destroy).pack(side="right", padx=4)

    def _update_fetch(self, url):
        """(Luồng phụ) Tải file tool từ link Raw, đọc version,
        biên dịch thử để chắc file không hỏng, rồi chuyển sang
        bước xác nhận trên luồng giao diện."""
        try:
            r = requests.get(url, timeout=30)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            new_src = r.content.decode("utf-8")
        except Exception as e:  # noqa
            self._ui(lambda: messagebox.showerror(
                "Update", f"Không tải được file cập nhật:\n"
                          f"{_short(e)}"))
            return
        m = re.search(r'TOOL_VERSION\s*=\s*"([^"]+)"', new_src)
        if not m:
            self._ui(lambda: messagebox.showerror(
                "Update", "File tải về không phải TAT Tool "
                          "(không thấy TOOL_VERSION). Kiểm tra "
                          "lại link Raw GitHub."))
            return
        new_ver = m.group(1)
        try:
            compile(new_src, "TAT Tool.py", "exec")
        except SyntaxError as e:
            self._ui(lambda: messagebox.showerror(
                "Update", f"File bản mới bị lỗi cú pháp, không "
                          f"cập nhật được:\n{_short(e)}"))
            return
        self._ui(lambda: self._update_confirm(new_ver, new_src))

    def _update_confirm(self, new_ver, new_src):
        """(Luồng giao diện) So version: mới hơn thì hỏi xác
        nhận rồi mới thay file."""
        if _ver_tuple(new_ver) <= _ver_tuple(TOOL_VERSION):
            messagebox.showinfo(
                "Update", f"Bạn đang dùng bản mới nhất "
                          f"({TOOL_VERSION}) rồi ✅")
            return
        ok = messagebox.askyesno(
            "Update", f"Có bản mới {new_ver} (đang dùng "
                      f"{TOOL_VERSION}).\n\nCập nhật ngay "
                      f"không? Tool sẽ tự đóng, thay file và mở "
                      f"lại.\nSettings / accounts / dữ liệu "
                      f"trên máy này giữ nguyên, bản cũ được "
                      f"sao lưu lại.")
        if ok:
            self._update_apply(new_ver, new_src)

    def _update_apply(self, new_ver, new_src):
        """Ghi file mới ra <tool>.new.py, tạo script updater
        chờ tiến trình tool thoát hẳn rồi: sao lưu file cũ ->
        thay file mới -> mở lại tool. Chạy updater tách rời
        (detached) nên tool đóng ngay được."""
        if getattr(sys, "frozen", False) or "__compiled__" in globals():
            messagebox.showwarning(
                "Update", "Bản EXE đóng gói không tự cập nhật "
                          "được - hãy thay file EXE thủ công.")
            return
        import subprocess
        script = Path(__file__).resolve()
        new_path = script.with_name(script.stem + ".new.py")
        backup = script.with_name(
            f"{script.stem}_backup_{TOOL_VERSION}.py")
        try:
            new_path.write_text(new_src, encoding="utf-8")
        except Exception as e:  # noqa
            messagebox.showerror(
                "Update", f"Không ghi được file mới:\n{_short(e)}")
            return
        upd_lines = [
            "import shutil, subprocess, sys, time",
            "from pathlib import Path",
            "pid = int(sys.argv[4])",
            "if sys.platform.startswith('win'):",
            "    import ctypes",
            "    h = ctypes.windll.kernel32.OpenProcess(",
            "        0x00100000, False, pid)",
            "    if h:",
            "        ctypes.windll.kernel32.WaitForSingleObject(",
            "            h, 120000)",
            "        ctypes.windll.kernel32.CloseHandle(h)",
            "time.sleep(1)",
            "script, newp, backup = (Path(a) for a in sys.argv[1:4])",
            "try:",
            "    shutil.copyfile(script, backup)",
            "except Exception:",
            "    pass",
            "shutil.copyfile(newp, script)",
            "try:",
            "    newp.unlink()",
            "except Exception:",
            "    pass",
            "subprocess.Popen([sys.executable, str(script)])",
            "try:",
            "    Path(__file__).unlink()",
            "except Exception:",
            "    pass",
        ]
        updater = APP_DIR / "tat_updater.py"
        try:
            updater.write_text("\n".join(upd_lines) + "\n",
                               encoding="utf-8")
            subprocess.Popen(
                [sys.executable, str(updater), str(script),
                 str(new_path), str(backup), str(os.getpid())],
                creationflags=0x00000008 | 0x00000200,
                close_fds=True)
        except Exception as e:  # noqa
            messagebox.showerror(
                "Update", f"Không chạy được updater:\n{_short(e)}")
            return
        print(f"[UPDATE] Đã tải bản {new_ver} - đóng tool để "
              f"thay file và mở lại...")
        messagebox.showinfo(
            "Update", f"Đã tải bản mới {new_ver}. Bấm OK là "
                      f"tool tự đóng, thay file rồi mở lại ngay."
                      f"\n(Bản cũ sao lưu thành {backup.name})")
        self.root.destroy()

    def _akc_check_missing_files(self):
        """Check acc nao CHUA CO file Shorts rieng
        (yt_acc_shorts/<acc>.txt) hoac co file nhung da HET link
        chua up -> TO DEN cac acc do trong bang Account ben trai,
        de chay 'Gan kenh + Quet FULL Shorts' tiep ngay. Logic doc
        file giong het START upload (bo qua link da up theo cache)."""
        accs = list(self.all_accounts)
        if not accs:
            messagebox.showinfo("Check file Shorts",
                                "Chưa có account nào trong bảng!")
            return
        done = {v for v, st in self.yt_link_status.items()
                if st == "ok"}
        done |= {v for v, e in _load_yt_cache().items()
                 if isinstance(e, dict) and e.get("uploaded")}
        no_file, empty, ok_acc, remain = [], [], 0, 0
        for acc in accs:
            fp = AKC_ACC_DIR / f"{acc['id']}.txt"
            if not fp.exists():
                no_file.append(acc["id"])
                continue
            ids, seen = [], set()
            try:
                lines = fp.read_text(encoding="utf-8",
                                     errors="ignore").splitlines()
            except Exception:  # noqa
                lines = []
            for ln in lines:
                vid = parse_youtube_id(ln)
                if vid and vid not in seen and vid not in done:
                    seen.add(vid)
                    ids.append(vid)
            if ids:
                ok_acc += 1
                remain += len(ids)
            else:
                empty.append(acc["id"])
        targets = set(no_file) | set(empty)
        id2item = {}
        for item in self.acc_tree.get_children():
            vals = self.acc_tree.item(item, "values")
            if vals:
                id2item[vals[0]] = item
        sel = [id2item[a] for a in targets if a in id2item]
        hidden = len(targets) - len(sel)
        self.acc_tree.selection_set(sel)
        if sel:
            self.acc_tree.see(sel[0])
        print(f"[AKC] CHECK file Shorts: tổng {len(accs)} acc | "
              f"chưa có file: {len(no_file)} | có file nhưng hết "
              f"link: {len(empty)} | còn link: {ok_acc} acc "
              f"({remain} link chưa up)")
        for aid in no_file:
            print(f"[AKC]   - @{aid}: CHƯA CÓ FILE Shorts")
        for aid in empty:
            print(f"[AKC]   - @{aid}: có file nhưng HẾT LINK chưa up")
        if hidden:
            print(f"[AKC]   ! {hidden} acc cần chạy đang bị ẩn bởi "
                  f"bộ lọc Nhóm/Tìm kiếm - đặt lọc về 'All' rồi bấm "
                  f"Check lại để tô đen đủ")
        if not targets:
            messagebox.showinfo(
                "Check file Shorts theo Acc",
                f"Tất cả {len(accs)} acc đều đã có file Shorts và "
                f"còn link chưa up ✅")
            return
        msg = (f"Đã tô đen {len(sel)} acc cần chạy trong bảng "
               f"Account bên trái:\n"
               f"- Chưa có file Shorts: {len(no_file)} acc\n"
               f"- Có file nhưng hết link chưa up: {len(empty)} acc\n"
               f"(Đã sẵn sàng: {ok_acc} acc, {remain} link chưa up)")
        if hidden:
            msg += (f"\n\n⚠ {hidden} acc cần chạy đang bị ẩn bởi bộ "
                    f"lọc Nhóm/Tìm kiếm - đặt bộ lọc về 'All' rồi "
                    f"bấm Check lại để tô đen đủ.")
        messagebox.showinfo("Check file Shorts theo Acc", msg)

    def _akc_show_pool_file(self):
        """Nút Pool kênh dự bị: gom kênh của acc ĐÃ XOÁ khỏi bảng
        vào pool trước (nếu chưa), ghi link các kênh đang bảo lưu
        (từ acc xoá / acc đổi kênh) ra file txt
        yt_channels_pool.txt, rồi mở hộp SỬA pool: xoá bớt link /
        thêm link kênh mới / đổi thứ tự (acc mới kế nhiệm theo
        thứ tự từ trên xuống). Lưu xong đồng bộ cả settings
        (yt_channel_pool) lẫn file txt; kênh bỏ khỏi pool thì
        file link POOL_<id>.txt của nó cũng bị xoá theo."""
        swept = self._akc_release_dead_channels()
        if swept:
            print(f"[AKC] ♻️ Vừa bảo lưu thêm {swept} kênh của acc "
                  f"đã xoá vào pool")
        pool = list(self.yt_channel_pool or [])

        def _link_of(p):
            u = (p or {}).get("url", "") or ""
            if not u:
                return ""
            return re.sub(r"/(shorts|videos|streams)/?$", "",
                          u.rstrip("/")) + "/shorts"

        def _left_of(p):
            cid = (p or {}).get("channel_id", "") or ""
            if not cid:
                return -1
            fp = AKC_ACC_DIR / f"POOL_{cid}.txt"
            if not fp.exists():
                return -1
            try:
                return max(0, len(fp.read_text(
                    encoding="utf-8",
                    errors="ignore").splitlines()) - 1)
            except Exception:  # noqa
                return -1

        lines0 = []
        for p in pool:
            lk = _link_of(p)
            if not lk:
                continue
            lines0.append(lk)
            n_left = _left_of(p)
            print(f"[AKC] POOL: {lk} | từ acc "
                  f"@{(p or {}).get('from_acc', '') or '?'} | "
                  + (f"còn {n_left} link chưa up" if n_left >= 0
                     else "chưa có file link (kế nhiệm sẽ quét mới)"))
        AKC_POOL_PATH.write_text(
            "\n".join(lines0) + ("\n" if lines0 else ""),
            encoding="utf-8")
        print(f"[AKC] 🗂 Pool kênh dự bị: {len(lines0)} kênh -> "
              f"{AKC_POOL_PATH}")

        win = tk.Toplevel(self.root)
        win.title("🗂 Pool kênh dự bị - sửa / xoá / thêm link kênh")
        win.geometry("640x500")
        win.grab_set()
        ttk.Label(win, text=f"Pool hiện có {len(lines0)} kênh dự "
                            f"bị (từ acc đã xoá / acc đổi kênh). "
                            f"Sửa trực tiếp trong khung: xoá dòng "
                            f"= bỏ kênh khỏi pool, thêm dòng mới "
                            f"= thêm kênh dự bị (1 link kênh / "
                            f"dòng, dạng youtube.com/@tenkenh). "
                            f"Acc mới chạy Gán kênh sẽ KẾ NHIỆM "
                            f"theo thứ tự từ trên xuống.",
                  wraplength=610).pack(fill="x", padx=8, pady=6)
        txt = tk.Text(win, font=("Consolas", 10), wrap="none")
        txt.pack(fill="both", expand=True, padx=8, pady=4)
        txt.insert("1.0", "\n".join(lines0))

        def do_open_txt():
            try:
                os.startfile(AKC_POOL_PATH)  # noqa: chi co tren Windows
            except Exception as e:  # noqa
                print(f"[!] Không mở được file pool: {_short(e)}")

        def do_save():
            raw = [ln.strip() for ln in
                   txt.get("1.0", "end").splitlines() if ln.strip()]
            bad, links, seen = [], [], set()
            for ln in raw:
                ok = ("youtube.com/@" in ln
                      or "youtube.com/channel/" in ln
                      or "youtube.com/c/" in ln
                      or "youtube.com/user/" in ln
                      or ln.startswith("@"))
                if not ok:
                    bad.append(ln)
                    continue
                if "youtube.com" in ln:
                    link = re.sub(r"/(shorts|videos|streams)/?$",
                                  "", ln.rstrip("/")) + "/shorts"
                else:  # go thang "@handle"
                    link = ("https://www.youtube.com/" + ln
                            + "/shorts")
                k = _channel_url_key(link, "shorts")
                if k in seen:
                    continue
                seen.add(k)
                links.append(link)
            if bad:
                messagebox.showwarning(
                    "Dòng không phải link kênh",
                    "Các dòng sau không giống link kênh YouTube "
                    "nên CHƯA lưu được:\n" + "\n".join(bad[:8])
                    + "\nHãy sửa thành dạng "
                      "youtube.com/@tenkenh rồi bấm Lưu lại.",
                    parent=win)
                return
            old_by_key = {}
            for p in pool:
                lk = _link_of(p)
                if lk:
                    old_by_key[_channel_url_key(lk, "shorts")] = p
            new_pool, added, kept = [], 0, 0
            for link in links:
                k = _channel_url_key(link, "shorts")
                if k in old_by_key:
                    new_pool.append(old_by_key[k])
                    kept += 1
                else:
                    new_pool.append({"channel_id": "", "url": link,
                                     "from_acc": "them_tay"})
                    added += 1
            kept_cids = {(p or {}).get("channel_id", "")
                         for p in new_pool}
            removed = 0
            for k, p in old_by_key.items():
                if k not in seen:
                    removed += 1
                    cid = (p or {}).get("channel_id", "") or ""
                    if cid and cid not in kept_cids:
                        fp = AKC_ACC_DIR / f"POOL_{cid}.txt"
                        try:
                            if fp.exists():
                                fp.unlink()
                                print(f"[AKC] POOL: đã xoá file "
                                      f"link của kênh bỏ khỏi "
                                      f"pool: {fp.name}")
                        except Exception:  # noqa
                            pass
            self.yt_channel_pool = new_pool
            _update_settings({"yt_channel_pool":
                              self.yt_channel_pool})
            AKC_POOL_PATH.write_text(
                "\n".join(links) + ("\n" if links else ""),
                encoding="utf-8")
            print(f"[AKC] 🗂 Đã lưu Pool kênh dự bị: giữ {kept}, "
                  f"thêm {added}, bỏ {removed} -> tổng "
                  f"{len(new_pool)} kênh (đã đồng bộ file "
                  f"yt_channels_pool.txt)")
            win.destroy()
            messagebox.showinfo(
                "Pool kênh dự bị",
                f"Đã lưu pool: {len(new_pool)} kênh dự bị (giữ "
                f"{kept}, thêm mới {added}, bỏ {removed}).\n"
                f"Acc mới chạy '🎯 Gán kênh + Quét' sẽ kế nhiệm "
                f"các kênh này theo thứ tự trong danh sách.")

        brow = ttk.Frame(win)
        brow.pack(fill="x", padx=8, pady=8)
        ttk.Button(brow, text="Lưu Pool", padding=(16, 7),
                   command=do_save).pack(side="left", padx=4)
        ttk.Button(brow, text="Mở file txt", padding=(16, 7),
                   command=do_open_txt).pack(side="left", padx=4)
        ttk.Button(brow, text="Huỷ", padding=(16, 7),
                   command=win.destroy).pack(side="right", padx=4)

    def _akc_target_accounts(self):
        """Acc đích của luồng Acc/Kênh: acc đang chọn trong bảng
        account; không chọn acc nào thì lấy TẤT CẢ acc (đúng thứ tự
        trong bảng)."""
        sel = self._selected_accounts()
        if sel:
            ids = {a["id"] for a in sel}
            return [a for a in self.all_accounts if a["id"] in ids]
        return list(self.all_accounts)

    # ---------- Pool kênh BẢO LƯU chờ kế nhiệm (v3.90) ----------
    def _akc_pool_release(self, acc_id):
        """Thả kênh của 1 acc về POOL BẢO LƯU: bỏ mapping của acc,
        đăng ký kênh vào yt_channel_pool và đổi file Shorts còn lại
        của acc thành file pool theo kênh (POOL_<channel_id>.txt).
        Acc mới kế nhiệm kênh này sẽ nhận file pool đó để up tiếp
        phần link còn lại. Trả về info kênh đã thả (hoặc None)."""
        info = self.yt_acc_channels.pop(acc_id, None)
        if not info:
            return None
        url = info.get("url", "") or ""
        cid = info.get("channel_id", "") or ""
        if url:
            key = _channel_url_key(url, "shorts")
            pool = list(self.yt_channel_pool or [])
            if not any(_channel_url_key((p or {}).get("url", ""),
                                         "shorts") == key
                       for p in pool):
                pool.append({"channel_id": cid, "url": url,
                             "from_acc": acc_id})
                self.yt_channel_pool = pool
        src = AKC_ACC_DIR / f"{acc_id}.txt"
        if cid and src.exists():
            dst = AKC_ACC_DIR / f"POOL_{cid}.txt"
            try:
                if dst.exists():
                    old = [ln for ln in dst.read_text(
                        encoding="utf-8",
                        errors="ignore").splitlines() if ln.strip()]
                    seen = set(old)
                    merged = list(old)
                    for ln in src.read_text(
                            encoding="utf-8",
                            errors="ignore").splitlines()[1:]:
                        if ln.strip() and ln not in seen:
                            seen.add(ln)
                            merged.append(ln)
                    dst.write_text("\n".join(merged) + "\n",
                                   encoding="utf-8")
                    src.unlink()
                else:
                    src.rename(dst)
            except Exception:  # noqa
                pass
        print(f"[AKC] ♻️ Bảo lưu kênh {url} của @{acc_id} vào pool "
              f"- chờ acc mới kế nhiệm up tiếp")
        return info

    def _akc_release_dead_channels(self):
        """Tự bảo lưu kênh của các acc ĐÃ BỊ XOÁ khỏi bảng (mapping
        còn mà acc không còn): kênh + file link còn lại vào pool để
        acc mới gán vào thì kế nhiệm, up tiếp, không trùng video
        acc cũ đã up. Trả về số kênh đã bảo lưu."""
        live = {a["id"] for a in self.all_accounts}
        dead = [a for a in list(self.yt_acc_channels.keys())
                if a not in live]
        for acc_id in dead:
            self._akc_pool_release(acc_id)
        if dead:
            _update_settings(
                {"yt_acc_channels": self.yt_acc_channels,
                 "yt_channel_pool": self.yt_channel_pool})
        return len(dead)

    def _akc_pool_take_file(self, cid, acc_id):
        """Acc kế nhiệm 1 kênh trong pool: đổi file pool của kênh
        (POOL_<channel_id>.txt) thành file Shorts của acc. Trả về
        True nếu có file pool (acc khỏi quét lại, up tiếp luôn)."""
        if not cid:
            return False
        src = AKC_ACC_DIR / f"POOL_{cid}.txt"
        if not src.exists():
            return False
        dst = AKC_ACC_DIR / f"{acc_id}.txt"
        try:
            if dst.exists():
                old = [ln for ln in dst.read_text(
                    encoding="utf-8",
                    errors="ignore").splitlines() if ln.strip()]
                seen = set(old)
                merged = list(old)
                for ln in src.read_text(
                        encoding="utf-8",
                        errors="ignore").splitlines()[1:]:
                    if ln.strip() and ln not in seen:
                        seen.add(ln)
                        merged.append(ln)
                dst.write_text("\n".join(merged) + "\n",
                               encoding="utf-8")
                src.unlink()
            else:
                src.rename(dst)
            return True
        except Exception:  # noqa
            return False

    def _akc_stop_scans(self):
        """Nút ⏹ Dừng quét (mục 1 + mục 2): dừng lượt quét đang
        chạy của tab Acc/Kênh (quét kênh / quét FULL Shorts) -
        worker tự thoát ở vòng lặp kế tiếp."""
        self.stop_requested = True
        print("[AKC] ⏹ Đã bấm Dừng quét - lượt quét đang chạy sẽ "
              "dừng lại.")

    def _akc_start_assign_scan(self):
        if self.akc_scanning:
            messagebox.showwarning("Cảnh báo",
                                   "Đang quét Shorts theo Acc...")
            return
        api_key = self._yt_active_key()
        if not api_key:
            messagebox.showerror(
                "Thiếu API key",
                "Quét Shorts bắt buộc có YT API Key (nhập ở tab "
                "Upload Chung File).")
            return
        raw = (self.akc_channel_text.get("1.0", "end")
               if hasattr(self, "akc_channel_text") else "")
        lines, seen_line = [], set()
        for ln in raw.splitlines():
            ln = ln.strip()
            if ln and ln.lower() not in seen_line:
                seen_line.add(ln.lower())
                lines.append(ln)
        if not lines and AKC_MASTER_PATH.exists():
            for ln in AKC_MASTER_PATH.read_text(
                    encoding="utf-8", errors="ignore").splitlines():
                ln = ln.strip()
                if ln and ln.lower() not in seen_line:
                    seen_line.add(ln.lower())
                    lines.append(ln)
            if lines:
                print(f"[AKC] Ô kênh trống -> tự nạp {len(lines)} kênh "
                      f"từ file tổng.")
        if not lines:
            messagebox.showerror(
                "Lỗi", "Chưa có kênh nào - hãy Quét kênh vào file tổng "
                       "hoặc dán link kênh vào ô danh sách!")
            return
        accs = self._akc_target_accounts()
        if not accs:
            messagebox.showerror("Lỗi",
                                 "Chưa có account nào trong bảng!")
            return
        # Tự bảo lưu kênh của acc đã bị xoá khỏi bảng vào pool, để
        # acc mới trong chính đợt gán này kế nhiệm luôn (up tiếp
        # phần link còn lại, không trùng video acc cũ đã up).
        self._akc_release_dead_channels()
        # Gán 1-1 theo thứ tự bảng acc. Chống trùng kênh: 1 kênh chỉ
        # thuộc 1 acc. Acc ĐÃ có kênh (từ lần trước) thì giữ đúng kênh
        # đó - không rút kênh mới nữa; chỉ acc CHƯA có kênh mới rút
        # kênh chưa dùng trong danh sách.
        used_by = {}
        for a_id, info in (self.yt_acc_channels or {}).items():
            k = _channel_url_key((info or {}).get("url", ""), "shorts")
            if k:
                used_by[k] = a_id
        line_keys = [_channel_url_key(u, "shorts") for u in lines]
        used_idx = set()
        pairs, rest = [], []
        for acc in accs:
            own_url = (self.yt_acc_channels.get(acc["id"])
                       or {}).get("url", "")
            if own_url:
                k_old = _channel_url_key(own_url, "shorts")
                for i, k in enumerate(line_keys):
                    if i not in used_idx and k == k_old:
                        used_idx.add(i)
                        break
                pairs.append((acc["id"], own_url))
            else:
                rest.append(acc)
        # Acc chưa có kênh: ưu tiên KẾ NHIỆM kênh trong pool bảo
        # lưu (kênh của acc cũ đã xoá / đã đổi kênh) - nhận luôn
        # file link còn lại để up tiếp, KHÔNG quét lại. Hết pool
        # mới rút kênh chưa dùng trong danh sách.
        ready_ids = set()
        still_rest = []
        for acc in rest:
            ent = None
            while self.yt_channel_pool:
                cand = self.yt_channel_pool.pop(0)
                if (cand or {}).get("url"):
                    ent = cand
                    break
            if not ent:
                still_rest.append(acc)
                continue
            url = ent.get("url", "")
            cid = ent.get("channel_id", "") or ""
            self.yt_acc_channels[acc["id"]] = {"url": url,
                                               "channel_id": cid}
            used_by[_channel_url_key(url, "shorts")] = acc["id"]
            if self._akc_pool_take_file(cid, acc["id"]):
                ready_ids.add(acc["id"])
                try:
                    n_left = max(0, len(
                        (AKC_ACC_DIR / f"{acc['id']}.txt").read_text(
                            encoding="utf-8",
                            errors="ignore").splitlines()) - 1)
                except Exception:  # noqa
                    n_left = 0
                print(f"[AKC] ♻️ @{acc['id']} KẾ NHIỆM kênh {url} "
                      f"(bảo lưu từ acc cũ) - còn {n_left} link chưa "
                      f"up trong file, không quét lại")
            else:
                print(f"[AKC] ♻️ @{acc['id']} KẾ NHIỆM kênh {url} "
                      f"(bảo lưu từ acc cũ, chưa có file link -> "
                      f"quét mới)")
            pairs.append((acc["id"], url))
        rest = still_rest
        skipped = []
        li = 0
        for acc in rest:
            placed = False
            while li < len(lines):
                i = li
                li += 1
                if i in used_idx:
                    continue
                owner = used_by.get(line_keys[i])
                if owner:
                    why = ("trùng kênh trong danh sách"
                           if owner == acc["id"]
                           else f"đã gán cho @{owner}")
                    skipped.append((lines[i], why))
                    continue
                used_by[line_keys[i]] = acc["id"]
                used_idx.add(i)
                pairs.append((acc["id"], lines[i]))
                placed = True
                break
            if not placed:
                break
        for url, why in skipped:
            print(f"[AKC] TRÙNG KÊNH - bỏ qua: {url} ({why})")
        if not pairs:
            messagebox.showwarning(
                "Không gán được kênh nào",
                "Mọi kênh đều đã gán cho account khác (chống trùng "
                "kênh). Hãy quét thêm kênh mới vào file tổng.")
            return
        if len(pairs) < len(accs):
            print(f"[AKC] Chỉ gán được {len(pairs)}/{len(accs)} "
                  f"account (hết kênh chưa dùng).")
        # Lưu ngay phần gán kênh -> acc: cột 'Đã Gán Kênh' hiện "Có"
        # ngay, và lần mở tool sau acc vẫn giữ đúng kênh của nó.
        for a_id, url in pairs:
            cur = self.yt_acc_channels.get(a_id) or {}
            if cur.get("url") != url:
                self.yt_acc_channels[a_id] = {
                    "url": url,
                    "channel_id": cur.get("channel_id", "")}
        _update_settings({"yt_acc_channels": self.yt_acc_channels,
                          "yt_channel_pool": self.yt_channel_pool})
        self._refresh_account_table()
        _update_settings({"akc_per_acc": self.akc_per_acc_var.get(),
                          "akc_threads": self.akc_threads_var.get(),
                          "akc_delay": self.akc_delay_var.get(),
                          "akc_scan_threads":
                              self.akc_scan_threads_var.get()})
        threads = max(1, self.akc_scan_threads_var.get())
        self.stop_requested = False
        self.akc_scanning = True
        self.akc_info_var.set("Đang quét FULL Shorts theo Acc...")
        print(f"[AKC] Gán kênh 1-1: {len(pairs)} account - bắt đầu "
              f"quét FULL Shorts từng kênh -> thư mục "
              f"{AKC_ACC_DIR.name}/")
        threading.Thread(target=self._akc_scan_worker,
                         args=(api_key, pairs, ready_ids, threads),
                         daemon=True).start()
        self._akc_show_scan_notice("🔍 ĐANG QUÉT FULL Shorts theo Acc")

    def _akc_swap_channels_clicked(self):
        """🔁 ĐỔI KÊNH cho các acc đang TÔ ĐEN: kênh cũ của acc
        được BẢO LƯU vào pool (để acc khác kế nhiệm up tiếp phần
        còn lại), acc nhận kênh MỚI chưa dùng trong ô danh sách
        kênh (theo thứ tự trong ô) rồi quét FULL Shorts của kênh
        mới (tự trừ video đã up)."""
        if self.akc_scanning:
            messagebox.showwarning("Cảnh báo",
                                   "Đang quét Shorts theo Acc...")
            return
        api_key = self._yt_active_key()
        if not api_key:
            messagebox.showerror(
                "Thiếu API key",
                "Đổi kênh (quét Shorts kênh mới) bắt buộc có YT API "
                "Key (nhập ở tab Upload Chung File).")
            return
        sel = self._selected_accounts()
        if not sel:
            messagebox.showwarning(
                "Chưa chọn account",
                "Hãy tô đen các account muốn ĐỔI kênh trong bảng "
                "Account trước!")
            return
        ids = {a["id"] for a in sel}
        accs = [a for a in self.all_accounts if a["id"] in ids]
        raw = (self.akc_channel_text.get("1.0", "end")
               if hasattr(self, "akc_channel_text") else "")
        lines, seen_line = [], set()
        for ln in raw.splitlines():
            ln = ln.strip()
            if ln and ln.lower() not in seen_line:
                seen_line.add(ln.lower())
                lines.append(ln)
        if not lines:
            messagebox.showwarning(
                "Chưa có kênh mới",
                "Hãy dán link kênh MỚI vào ô danh sách kênh (mục 2) "
                "trước khi đổi!")
            return
        used_by = {}
        for a_id, info in (self.yt_acc_channels or {}).items():
            k = _channel_url_key((info or {}).get("url", ""), "shorts")
            if k:
                used_by[k] = a_id
        pool_keys = {_channel_url_key((p or {}).get("url", ""),
                                       "shorts")
                     for p in (self.yt_channel_pool or [])}
        pairs = []
        for acc in accs:
            cur_url = (self.yt_acc_channels.get(acc["id"])
                       or {}).get("url", "")
            if not cur_url:
                print(f"[AKC] @{acc['id']}: chưa có kênh - bỏ qua "
                      f"đổi kênh (dùng nút Gán kênh cho acc này)")
                continue
            cur_key = _channel_url_key(cur_url, "shorts")
            repl = None
            for u in lines:
                k = _channel_url_key(u, "shorts")
                if not k or k == cur_key or k in pool_keys:
                    continue
                owner = used_by.get(k)
                if owner and owner != acc["id"]:
                    continue
                repl = u
                break
            if repl is None:
                print(f"[AKC] Hết kênh mới chưa dùng trong ô - "
                      f"@{acc['id']} giữ nguyên kênh cũ {cur_url}")
                break
            self._akc_pool_release(acc["id"])
            self.yt_acc_channels[acc["id"]] = {"url": repl,
                                               "channel_id": ""}
            used_by[_channel_url_key(repl, "shorts")] = acc["id"]
            pairs.append((acc["id"], repl))
            print(f"[AKC] 🔁 @{acc['id']}: đổi kênh {cur_url} "
                  f"-> {repl}")
        if not pairs:
            messagebox.showinfo(
                "Không đổi được kênh nào",
                "Không có kênh mới khả dụng trong ô (kênh trong ô "
                "đã có chủ / đang bảo lưu, hoặc các acc đã chọn "
                "chưa có kênh).")
            return
        _update_settings({"yt_acc_channels": self.yt_acc_channels,
                          "yt_channel_pool": self.yt_channel_pool})
        self._refresh_account_table()
        self.stop_requested = False
        self.akc_scanning = True
        self.akc_info_var.set("Đang quét FULL Shorts (đổi kênh)...")
        threads = max(1, self.akc_scan_threads_var.get())
        threading.Thread(target=self._akc_scan_worker,
                         args=(api_key, pairs, None, threads),
                         daemon=True).start()
        self._akc_show_scan_notice(
            "🔍 ĐANG QUÉT FULL Shorts (đổi kênh)")

    def _akc_scan_worker(self, api_key, pairs, ready_ids=None,
                         threads=5):
        AKC_ACC_DIR.mkdir(parents=True, exist_ok=True)
        uploaded = {v for v, e in _load_yt_cache().items()
                    if isinstance(e, dict) and e.get("uploaded")}
        uploaded |= {v for v, st in self.yt_link_status.items()
                     if st == "ok"}
        done_accs = []
        total_links = 0
        ready_ids = set(ready_ids or ())

        def scan_one(idx, acc_id, ch_url):
            """Quét FULL Shorts cho 1 acc (chạy trong luồng phụ).
            Trả về số link chưa up, hoặc None nếu bỏ qua / lỗi."""
            _info = self.yt_acc_channels.get(acc_id) or {}
            cid = ""
            if (_info.get("url") or "") == ch_url:
                cid = _info.get("channel_id") or ""
            if not cid:
                try:
                    cid = resolve_channel_id(api_key, ch_url)
                except Exception as e:  # noqa
                    print(f"[AKC] ({idx}/{len(pairs)}) @{acc_id}: "
                          f"lỗi tra kênh {ch_url}: {_short(e)} "
                          f"- bỏ qua")
                    return None
            # Chống trùng kênh theo UC id: kênh acc KHÁC đã quét
            # rồi thì không quét lại cho acc này (acc tự quét lại
            # kênh của chính nó thì được - để nạp thêm video mới).
            own = (self.yt_acc_channels.get(acc_id)
                   or {}).get("channel_id")
            dup = self._find_channel_history(f"{cid}|shorts")
            # Kênh gắn thẻ "master" = mới dành chỗ trong file
            # tổng (chưa lấy list) -> acc được gán vẫn quét bình
            # thường. Kênh đã LẤY LIST ở luồng khác (không thẻ)
            # -> trùng thật, báo + bỏ qua.
            if dup and own != cid and dup.get("tag") != "master":
                print(f"[AKC] ({idx}/{len(pairs)}) TRÙNG KÊNH - "
                      f"bỏ qua: {ch_url} (đã quét list trước đây)")
                return None
            try:
                ids, _calls = fetch_channel_video_ids(
                    api_key, cid, "shorts", 10 ** 9)
            except Exception as e:  # noqa
                print(f"[AKC] ({idx}/{len(pairs)}) @{acc_id}: "
                      f"lỗi lấy Shorts của {ch_url}: {_short(e)} "
                      f"- bỏ qua")
                return None
            keep = [v for v in ids if v not in uploaded]
            base = re.sub(r"/(shorts|videos|streams)/?$", "",
                          ch_url.rstrip("/"))
            header = base + "/shorts"
            fp = AKC_ACC_DIR / f"{acc_id}.txt"
            body = [header] + [
                f"https://www.youtube.com/watch?v={v}" for v in keep]
            fp.write_text("\n".join(body) + "\n", encoding="utf-8")
            with self._akc_state_lock:
                self.yt_acc_channels[acc_id] = {"url": ch_url,
                                                "channel_id": cid}
                _update_settings(
                    {"yt_acc_channels": self.yt_acc_channels})
            # Kênh đã có chủ -> TRỪ khỏi file tổng (file tổng chỉ
            # còn kênh CHƯA dùng) + ghi sổ kênh đã gán.
            self._akc_consume_master(ch_url, acc_id)
            print(f"[AKC] ({idx}/{len(pairs)}) @{acc_id} <- "
                  f"{ch_url}: quét FULL {len(ids)} Shorts, còn "
                  f"{len(keep)} link chưa up (đã trừ "
                  f"{len(ids) - len(keep)} link up rồi) "
                  f"-> {fp.name}")
            self._ui(lambda u=ch_url, c=cid, n=len(ids), a=acc_id:
                     self._record_channel_history(u, c, "shorts",
                                                  n, a))
            return len(keep)

        try:
            todo = []
            for idx, (acc_id, ch_url) in enumerate(pairs, 1):
                fp = AKC_ACC_DIR / f"{acc_id}.txt"
                n_left = -1
                if fp.exists():
                    n_left = max(0, len(fp.read_text(
                        encoding="utf-8",
                        errors="ignore").splitlines()) - 1)
                inherited = acc_id in ready_ids
                info = self.yt_acc_channels.get(acc_id) or {}
                # Acc ĐÃ gán đúng kênh này + ĐÃ quét rồi (có
                # channel_id) + file vẫn còn link chưa up -> bỏ
                # qua, KHÔNG quét lại (khỏi tốn quota). File hết
                # link thì vẫn quét lại để nạp video MỚI của kênh.
                already = (not inherited
                           and bool(info.get("channel_id"))
                           and _channel_url_key(
                               info.get("url", ""), "shorts")
                           == _channel_url_key(ch_url, "shorts"))
                if (inherited or already) and n_left > 0:
                    done_accs.append(acc_id)
                    total_links += n_left
                    if inherited:
                        print(f"[AKC] ({idx}/{len(pairs)}) "
                              f"@{acc_id} <- {ch_url}: KẾ NHIỆM - "
                              f"còn {n_left} link chưa up trong "
                              f"file (không quét lại)")
                    else:
                        print(f"[AKC] ({idx}/{len(pairs)}) "
                              f"@{acc_id} <- {ch_url}: ĐÃ QUÉT "
                              f"RỒI - còn {n_left} link chưa up "
                              f"trong file, bỏ qua (không tốn "
                              f"quota)")
                    self._ui(lambda i=idx, t=len(pairs),
                             n=total_links:
                             self.akc_info_var.set(
                                 f"Đã quét {i}/{t} acc - "
                                 f"tổng {n} link"))
                else:
                    todo.append((idx, acc_id, ch_url))
            if todo:
                print(f"[AKC] Quét FULL Shorts cho {len(todo)} acc "
                      f"bằng {threads} luồng song song...")
                with ThreadPoolExecutor(max_workers=threads) as ex:
                    futs = {ex.submit(scan_one, i, a, u): a
                            for i, a, u in todo}
                    done_n = 0
                    for fut in as_completed(futs):
                        if getattr(self, "stop_requested", False):
                            print("[AKC] ⏹ STOP - dừng quét Shorts "
                                  "theo Acc.")
                            for f in futs:
                                f.cancel()
                            break
                        n_keep = fut.result()
                        if n_keep is not None:
                            done_accs.append(futs[fut])
                            total_links += n_keep
                        done_n += 1
                        self._ui(lambda d=done_n, t=len(todo),
                                 n=total_links:
                                 self.akc_info_var.set(
                                     f"Đã quét {d}/{t} acc - "
                                     f"tổng {n} link"))
            print(f"[AKC] Quét xong: {len(done_accs)} acc, "
                  f"{total_links} link chưa up -> thư mục {AKC_ACC_DIR}")
            if done_accs:
                self._notify_done(
                    "Quét Shorts theo Acc",
                    f"✅ Đã quét FULL Shorts cho {len(done_accs)} "
                    f"account ({total_links} link chưa upload).\n"
                    f"Giờ chỉ cần: tô đen các account trong bảng "
                    f"Account -> qua mục 3 của tab này bấm "
                    f"▶ START Upload.")
        except Exception as e:  # noqa
            print(f"[AKC] Lỗi quét Shorts theo Acc: {_short(e)}")
        finally:
            self.akc_scanning = False
            self._ui(lambda: self.akc_info_var.set(""))

    def _akc_consume_master(self, ch_url, acc_id):
        """Kênh đã gán + quét xong cho 1 acc -> TRỪ kênh đó khỏi file
        tổng (file tổng chỉ còn kênh CHƯA dùng: quét 1000 kênh, gán
        900 acc thì file tổng còn đúng 100) và ghi vào file sổ kênh
        đã gán (yt_channels_assigned.txt) để tra cứu / tránh trùng."""
        try:
            key = _channel_url_key(ch_url, "shorts")
            with self._akc_file_lock:
                if AKC_MASTER_PATH.exists():
                    lines = AKC_MASTER_PATH.read_text(
                        encoding="utf-8", errors="ignore").splitlines()
                    kept = [ln for ln in lines
                            if _channel_url_key(ln, "shorts") != key]
                    if len(kept) != len(lines):
                        AKC_MASTER_PATH.write_text(
                            "\n".join(kept) + ("\n" if kept else ""),
                            encoding="utf-8")
                        print(f"[AKC] Đã trừ kênh {ch_url} khỏi file "
                              f"tổng (đã gán cho @{acc_id}) - file "
                              f"tổng còn {len(kept)} kênh chưa dùng")
                with open(AKC_ASSIGNED_PATH, "a",
                          encoding="utf-8") as fh:
                    fh.write(f"{ch_url}\t{acc_id}\n")
            self._ui(self._akc_refresh_master_info)
        except Exception:  # noqa
            pass



    # --- 3) Chạy upload + xoá link khỏi file acc khi thành công ---
    def _akc_start_upload(self):
        """START của tab Acc/Kênh: lấy các acc đang TÔ ĐEN trong bảng
        Account; mỗi acc tự mở file Shorts riêng của nó
        (yt_acc_shorts/<acc>.txt), lấy 'Video/Acc mỗi lần chạy' link
        đầu (tự bỏ dòng LINK KÊNH ở đầu file + link đã up) -> chạy
        pipeline luôn, KHÔNG qua bước gán link và KHÔNG đổ link ra
        bảng List Link. Up thành công link nào, link đó tự xoá khỏi
        file của acc (hook trong pipeline) rồi file tự lưu lại."""
        accs = self._selected_accounts()
        if not accs:
            messagebox.showwarning(
                "Chưa chọn account",
                "Hãy tô đen (chọn) các account cần chạy trong bảng "
                "Account bên trái trước!")
            return
        per = max(1, self.akc_per_acc_var.get())
        done = {v for v, st in self.yt_link_status.items()
                if st == "ok"}
        done |= {v for v, e in _load_yt_cache().items()
                 if isinstance(e, dict) and e.get("uploaded")}
        run_assign, no_file, empty = {}, 0, 0
        for acc in accs:
            fp = AKC_ACC_DIR / f"{acc['id']}.txt"
            if not fp.exists():
                no_file += 1
                print(f"[AKC] @{acc['id']}: chưa có file Shorts riêng "
                      f"- bỏ qua (hãy Gán kênh + Quét FULL Shorts "
                      f"trước)")
                continue
            ids, seen = [], set()
            for ln in fp.read_text(encoding="utf-8",
                                   errors="ignore").splitlines():
                vid = parse_youtube_id(ln)
                if vid and vid not in seen and vid not in done:
                    seen.add(vid)
                    ids.append(vid)
            if not ids:
                empty += 1
                print(f"[AKC] @{acc['id']}: file Shorts không còn "
                      f"link chưa up - bỏ qua")
                continue
            run_assign[acc["id"]] = ids[:per]
        if not run_assign:
            messagebox.showinfo(
                "Không có link để chạy",
                "Các account đã chọn chưa có file Shorts hoặc đã up "
                "hết link.\nHãy bấm '🎯 Gán kênh + Quét FULL Shorts "
                "theo Acc' trước!")
            return
        self.yt_assignments = run_assign
        self._save_assignments()
        # Luồng này không dùng bảng List Link: dọn bảng để pipeline
        # không bị lọc theo lựa chọn cũ trong bảng.
        self.yt_link_rows = []
        self.yt_fetched_ids = []
        self._refresh_link_table()
        total = sum(len(v) for v in run_assign.values())
        print(f"[AKC] START: {len(run_assign)} acc x tối đa {per} "
              f"video = {total} link (lấy trực tiếp từ file của "
              f"từng acc)"
              + (f"; bỏ qua {no_file} acc chưa có file, {empty} acc "
                 f"hết link" if (no_file or empty) else ""))
        # Đồng bộ số luồng + delay của tab này sang biến dùng chung
        # của pipeline (engine upload dùng chung với tab Chung File).
        self.yt_up_threads_var.set(max(1, self.akc_threads_var.get()))
        self.yt_delay_var.set(max(0, self.akc_delay_var.get()))
        _update_settings({"akc_threads": self.akc_threads_var.get(),
                          "akc_delay": self.akc_delay_var.get()})
        self._start_pipeline()

    def _akc_remove_uploaded_link(self, acc_id, vid):
        """Upload thành công 1 link -> xoá link đó khỏi file Shorts
        của acc (yt_acc_shorts/<acc>.txt) để hôm sau không up lại
        nữa. Dòng đầu (link kênh) và các link còn lại giữ nguyên."""
        try:
            fp = AKC_ACC_DIR / f"{acc_id}.txt"
            if not fp.exists():
                return
            with self._akc_file_lock:
                lines = fp.read_text(encoding="utf-8",
                                     errors="ignore").splitlines()
                kept = [ln for ln in lines
                        if parse_youtube_id(ln) != vid]
                if len(kept) != len(lines):
                    fp.write_text("\n".join(kept) + "\n",
                                  encoding="utf-8")
                    left = sum(1 for ln in kept
                               if parse_youtube_id(ln))
                    print(f"[AKC] @{acc_id}: đã xoá link {vid} khỏi "
                          f"file acc (còn {left} link chưa up)")
        except Exception:  # noqa
            pass

    # ---------- Gan link cho account + pipeline Tai -> Upload -> Xoa ----------
    def _assign_links(self):
        """Chia list link cho các account theo thứ tự nối tiếp: mỗi acc
        nhận đúng số ở ô 'Video/Acc', acc sau nhận các link tiếp theo."""
        ids, seen = [], set()
        for vid in self._selected_link_ids():
            if vid not in seen:
                seen.add(vid)
                ids.append(vid)
        if not ids:
            for row in self.yt_link_rows:
                if row["id"] not in seen:
                    seen.add(row["id"])
                    ids.append(row["id"])
        if not ids:
            for vid in self.yt_fetched_ids:
                if vid not in seen:
                    seen.add(vid)
                    ids.append(vid)
        if not ids:
            lf = (self.yt_links_file_var.get() or "").strip()
            if lf and Path(lf).exists():
                for line in Path(lf).read_text(encoding="utf-8",
                                               errors="ignore").splitlines():
                    vid = parse_youtube_id(line)
                    if vid and vid not in seen:
                        seen.add(vid)
                        ids.append(vid)
        _done = {v for v, st in self.yt_link_status.items() if st == "ok"}
        _done |= {v for v, e in _load_yt_cache().items()
                  if isinstance(e, dict) and e.get("uploaded")}
        if _done:
            _kept = [v for v in ids if v not in _done]
            if len(_kept) != len(ids):
                print(f"[GÁN] Bỏ qua {len(ids) - len(_kept)} link đã "
                      f"'Upload thành công' (không gán lại).")
                ids = _kept
            if not ids:
                messagebox.showinfo(
                    "Gán link", "Toàn bộ link trong list đều đã upload "
                                "thành công - không còn link nào để gán.")
                return
        if not ids:
            messagebox.showerror(
                "Lỗi", "Chưa có list link nào - hãy 'Lấy list link' từ kênh "
                       "hoặc mở 1 list đã lưu trong bảng List Link trước!")
            return
        accs = self._selected_accounts() or list(self.all_accounts)
        if not accs:
            messagebox.showerror("Lỗi", "Chưa có account nào trong bảng!")
            return
        per = max(1, self.yt_per_acc_var.get())
        assignments = {}
        pos = 0
        for acc in accs:
            take = ids[pos:pos + per]
            if not take:
                break
            assignments[acc["id"]] = take
            pos += len(take)
        self.yt_assignments = assignments
        self._save_assignments()
        self._refresh_link_table()
        total = sum(len(v) for v in assignments.values())
        print(f"[GÁN] Đã gán {total} link cho {len(assignments)} account "
              f"(mỗi acc tối đa {per} video) - còn dư {len(ids) - total} link.")
        for acc_id, vids in assignments.items():
            print(f"[GÁN] @{acc_id}: {len(vids)} video")
        if len(assignments) < len(accs):
            messagebox.showwarning(
                "Thiếu link",
                f"Chỉ đủ link cho {len(assignments)}/{len(accs)} account "
                f"(mỗi acc {per} video). Hãy lấy thêm link hoặc giảm Video/Acc.")
        else:
            messagebox.showinfo(
                "Đã gán link",
                f"Đã gán {total} link cho {len(assignments)} account.\n"
                f"Bấm '▶ START: Tải → Upload → Xoá' để chạy.")

    # ---------- Kiem tra session truoc khi chay ----------
    def _check_sessions_parallel(self, acc_ids, threads=5):
        """Kiem tra session song song cho nhieu acc.
        Tra {acc_id: (state, msg)}."""
        by_id = {a["id"]: a for a in self.all_accounts}
        out = {}

        def job(aid):
            acc = by_id.get(aid)
            if acc is None:
                return aid, ("unknown", "không thấy account")
            return aid, check_session_alive(acc)

        with ThreadPoolExecutor(max_workers=max(1, threads)) as ex:
            for aid, res in ex.map(job, list(acc_ids)):
                out[aid] = res
        return out

    def _apply_session_results(self, results):
        """Ghi ket qua kiem tra session len cot trang thai cua tung
        account + dong log tong ket. Tra danh sach account chet."""
        alive = unknown = 0
        dead = []
        for aid, (state, _msg) in results.items():
            if state == "alive":
                alive += 1
                self._ui(lambda a=aid: self._set_acc_status(
                    a, "🍪 Cookie ✅ còn sống"))
            elif state == "dead":
                dead.append(aid)
                self._ui(lambda a=aid: self._set_acc_status(
                    a, "🍪 Cookie ❌ đã chết — đăng nhập lại trong GPM"))
            else:
                unknown += 1
                self._ui(lambda a=aid: self._set_acc_status(
                    a, "🍪 Cookie ⚠️ không rõ"))
        print(f"[COOKIE] Kết quả: {alive} sống, {len(dead)} chết, "
              f"{unknown} không rõ"
              + (f". Account chết: {', '.join(dead)}" if dead else ""))
        return dead

    def _start_session_check(self):
        """Nut kiem tra session doc lap: uu tien account da gan link,
        khong co thi account dang chon o bang Account, khong nua thi
        toan bo account."""
        if getattr(self, "session_checking", False):
            messagebox.showwarning("Cảnh báo", "Đang kiểm tra cookie...")
            return
        targets = list(self.yt_assignments.keys())
        scope = "account đã gán link"
        if not targets:
            targets = [self.acc_tree.item(i, "values")[0]
                       for i in self.acc_tree.selection()]
            scope = "account đang chọn"
        if not targets:
            targets = [a["id"] for a in self.all_accounts]
            scope = "toàn bộ account"
        if not targets:
            messagebox.showwarning("Trống", "Chưa có account nào!")
            return
        self.session_checking = True
        print(f"[COOKIE] Đang kiểm tra cookie {len(targets)} "
              f"account ({scope})...")
        threading.Thread(target=self._session_check_worker,
                         args=(targets,), daemon=True).start()

    def _session_check_worker(self, targets):
        try:
            results = self._check_sessions_parallel(targets)
            dead = self._apply_session_results(results)
            n_alive = sum(1 for s, _m in results.values()
                          if s == "alive")
            n_unk = sum(1 for s, _m in results.values()
                        if s == "unknown")
            self._notify_done(
                "Check cookie",
                f"✅ Còn sống: {n_alive} — ❌ Đã chết: {len(dead)}"
                f" — ⚠️ Không rõ: {n_unk}"
                + (f"\nAccount chết: {', '.join(dead)}\n"
                   f"(mở GPM đăng nhập lại các account này)"
                   if dead else ""))
        finally:
            self.session_checking = False

    def _start_pipeline(self):
        global GRID_TOTAL, HIDE_BROWSER
        if self.pipeline_running:
            messagebox.showwarning("Cảnh báo", "Pipeline đang chạy...")
            return
        if not self.yt_assignments:
            messagebox.showerror(
                "Lỗi", "Chưa gán link cho account - bấm '📌 Gán link cho Account' trước!")
            return
        run_assign = {a: list(v) for a, v in self.yt_assignments.items()}
        _done = {v for v, st in self.yt_link_status.items() if st == "ok"}
        _done |= {v for v, e in _load_yt_cache().items()
                  if isinstance(e, dict) and e.get("uploaded")}
        if _done:
            run_assign = {a: [v for v in vids if v not in _done]
                          for a, vids in run_assign.items()}
            run_assign = {a: v for a, v in run_assign.items() if v}
        _sel = set(self._selected_link_ids())
        if _sel:
            run_assign = {a: [v for v in vids if v in _sel]
                          for a, vids in run_assign.items()}
            run_assign = {a: v for a, v in run_assign.items() if v}
            print(f"[PIPE] Chỉ chạy {sum(len(v) for v in run_assign.values())} "
                  f"link đang chọn trong bảng List Link.")
        if not run_assign:
            messagebox.showinfo(
                "START", "Không còn link nào cần chạy (các link đã gán đều "
                         "đã upload thành công, hoặc lựa chọn hiện tại trống).")
            return
        out_dir = self._yt_out_dir()
        if not out_dir:
            messagebox.showerror(
                "Lỗi", "Chưa chọn Folder Video (nơi tải video về trước khi upload)!")
            return
        threads = max(1, self.yt_up_threads_var.get())
        GRID_TOTAL = max(1, min(threads, len(run_assign)))
        _set_launch_delay(self.yt_delay_var.get())
        HIDE_BROWSER = bool(self.hide_browser_var.get())
        self._persist_settings()
        self.stop_requested = False
        clear_engine_stop()
        self.pipeline_running = True
        print("[START] ▶ Pipeline đang khởi động - tải video & mở trình "
              "duyệt, vui lòng đợi vài giây..."
              + (" (đang bật ẨN trình duyệt)" if HIDE_BROWSER else ""))
        threading.Thread(
            target=self._pipeline_worker,
            args=(run_assign, out_dir, threads,
                  self._yt_active_key()),
            daemon=True).start()

    def _pipeline_worker(self, assignments, out_dir, threads, api_key):
        """Pipeline từng account: tải video (yt-dlp) -> upload
        (upload_one_selenium - tự xoá file gốc khi đăng thành công) ->
        xong acc này sang acc khác; các acc chạy song song theo số luồng."""
        total_vids = sum(len(v) for v in assignments.values())
        print(f"[PIPE] Bắt đầu pipeline: {len(assignments)} account, "
              f"{total_vids} video - {threads} luồng. Mỗi video: "
              f"tải → upload → xoá file gốc.")
        state = {"ok": 0, "fail": 0, "done": [], "failed": []}
        titles = {}
        cache_titles = {k: (v or {}).get("title", "")
                        for k, v in _load_yt_cache().items()}
        row_titles = {r.get("id"): (r.get("title") or "")
                      for r in getattr(self, "yt_link_rows", [])}
        all_ids = [v for vids in assignments.values() for v in vids]
        if api_key:
            try:
                meta, _calls = fetch_yt_metadata(api_key, all_ids)
                titles = {k: (v or {}).get("title", "")
                          for k, v in meta.items()}
                print(f"[PIPE] Đã lấy title của {len(titles)} video làm caption "
                      f"(tốn {_calls} quota)")
            except Exception as e:  # noqa
                print(f"[PIPE] Không lấy được title làm caption: {_short(e)}")

        def run_account(acc_id, vids):
            self._ui(lambda a=acc_id: self._set_acc_status(
                a, "🔄 Đang chạy pipeline..."))
            for n_vid, vid in enumerate(vids):
                if self.stop_requested:
                    print(f"[PIPE] ⏹ STOP - @{acc_id}: bỏ qua "
                          f"{len(vids) - n_vid} video còn lại")
                    break
                found = _find_downloaded(out_dir, vid)
                path = (found if found is not None
                        else Path(out_dir) / f"{vid}.mp4")
                if found is None:
                    dl_title = (row_titles.get(vid) or titles.get(vid)
                                or cache_titles.get(vid, ""))
                    ok_dl, res = download_one_yt(vid, out_dir,
                                                 title=dl_title)
                    if not ok_dl:
                        state["fail"] += 1
                        if acc_id not in state["failed"]:
                            state["failed"].append(acc_id)
                        print(f"[PIPE] ❌ @{acc_id} {vid}: tải lỗi - {res}")
                        continue
                    path = Path(res)
                    _save_yt_cache_entry(vid, {
                        "file": path.name, "title": titles.get(vid, ""),
                        "ts": int(time.time())})
                if self.stop_requested:
                    print(f"[PIPE] ⏹ STOP - @{acc_id}: dừng, không upload {vid}")
                    break
                caption = (row_titles.get(vid) or titles.get(vid)
                           or cache_titles.get(vid, ""))
                ok = upload_one_selenium(acc_id, str(path), caption)
                if not ok and self.stop_requested:
                    print(f"[PIPE] ⏹ STOP - @{acc_id}: trình duyệt đã bị "
                          f"kill giữa chừng, link {vid} KHÔNG tính lỗi "
                          f"(chạy lại sau)")
                    break
                if ok:
                    state["ok"] += 1
                    state["done"].append(vid)
                    # Tab UPLOAD Acc/Kênh: xoá link vừa up khỏi file
                    # Shorts của acc để hôm sau không up lại (acc
                    # không có file riêng thì hàm tự bỏ qua).
                    self._akc_remove_uploaded_link(acc_id, vid)
                    self._ui(lambda a=acc_id: self._set_acc_status(
                        a, "✅ Đã đăng (link YT)"))
                    self._ui(lambda v=vid: self._mark_link_uploaded(v))
                    if path.exists():  # engine thường đã xoá; dọn nốt nếu còn
                        try:
                            path.unlink()
                            print(f"[PIPE] Đã xoá file gốc: {path.name}")
                        except Exception:  # noqa
                            pass
                else:
                    state["fail"] += 1
                    if acc_id not in state["failed"]:
                        state["failed"].append(acc_id)
                    print(f"[PIPE] ❌ @{acc_id} {vid}: upload lỗi")
                    self._ui(lambda v=vid: self._mark_link_failed(v))
                    self._ui(lambda a=acc_id: self._set_acc_status(
                        a, "❌ Upload lỗi (link YT)"))
            # Acc vừa chạy xong -> tự xoá cache TikTok nếu đang tick
            # ô 'Tự xoá cache...' cạnh nút START (giống tab Offline).
            self._ui(lambda a=acc_id: self._maybe_clean_cache(a))
            print(f"[PIPE] Xong account @{acc_id}")

        try:
            with ThreadPoolExecutor(max_workers=threads) as ex:
                futures = [ex.submit(run_account, a, v)
                           for a, v in assignments.items()]
                for f in futures:
                    f.result()
        except Exception as e:  # noqa
            print(f"[PIPE] Lỗi pipeline: {_short(e)}")
        finally:
            self.pipeline_running = False
            if state["done"]:
                self._ui(lambda d=list(state["done"]): self._prune_assignments(d))
            if state["failed"]:
                self._report_upload_result("Upload (YouTube)", state["ok"],
                                           state["fail"], state["failed"])
            print(f"[PIPE] Hoàn tất: đăng thành công {state['ok']}, "
                  f"lỗi {state['fail']}.")
            self._notify_done(
                "Upload (YouTube)",
                ("⏹ Pipeline đã dừng theo yêu cầu.\n"
                 if self.stop_requested else "✅ Pipeline đã hoàn tất!\n")
                + f"Đăng thành công: {state['ok']} - Lỗi: {state['fail']}")

    # ---------- API key YouTube v3 (NHIEU key, tu xoay vong) ----------
    def _yt_key_info_refresh(self):
        """Cap nhat nhan so key canh o API Key + dong bo pool key."""
        keys = list(getattr(self, "yt_api_keys", []) or [])
        yt_keys_set(keys)
        if len(keys) > 1:
            txt = f"🔑 {len(keys)} key - tự chuyển key khi hết quota"
        elif len(keys) == 1:
            txt = "🔑 1 key"
        else:
            txt = "🔑 chưa có key"
        try:
            self.yt_key_info_var.set(txt)
        except Exception:  # noqa
            pass

    def _yt_active_key(self):
        """Tra key chinh (key dau trong DS) + dong bo DS key tu o nhap:
        dan NHIEU key vao o Key (cach nhau bang dau phay / xuong dong /
        khoang trang) thi nhan ca list; go 1 key moi la thi thay list
        bang key do; o dang chua key dau cua DS thi giu nguyen DS."""
        parsed = _parse_yt_keys(self.yt_api_key_var.get())
        cur = list(getattr(self, "yt_api_keys", []) or [])
        if len(parsed) > 1:
            cur = parsed
        elif len(parsed) == 1 and parsed[0] not in cur:
            cur = parsed
        self.yt_api_keys = cur
        yt_keys_set(cur)
        return cur[0] if cur else ""

    def _save_api_key(self):
        """Lưu (các) API key vào tool_settings.json để lần sau khỏi dán lại."""
        key = self._yt_active_key()
        if not key:
            messagebox.showwarning(
                "Trống", "Chưa có API key nào - dán key vào ô hoặc bấm 🔑 DS Key!")
            return
        self.yt_api_key_var.set(key)
        self._persist_settings()
        self._yt_key_info_refresh()
        n = len(self.yt_api_keys)
        print(f"[YT] Đã lưu {n} API key vào tool_settings.json")
        messagebox.showinfo(
            "Đã lưu",
            f"Đã lưu {n} API key. Tool sẽ tự nhớ cho các lần sau.\n"
            "Khi 1 key hết quota, tool tự chuyển sang key kế tiếp.")

    def _test_api_key(self):
        """Test TỪNG key trong DS bằng 1 lần gọi API thật (1 quota / key)."""
        first = self._yt_active_key()
        keys = list(self.yt_api_keys)
        if not first or not keys:
            messagebox.showwarning("Trống", "Hãy dán API key vào ô trước!")
            return
        self.yt_api_key_var.set(first)
        self._persist_settings()
        self._yt_key_info_refresh()
        print(f"[YT] Đang test {len(keys)} API key (tốn 1 quota / key)...")

        def run():
            lines = []
            ok_all = True
            for i, k in enumerate(keys, 1):
                ok, msg = check_yt_api_key(k)
                ok_all = ok_all and ok
                mask = (k[:6] + "..." + k[-4:]) if len(k) > 12 else k
                lines.append(f"Key {i} ({mask}): {msg}")
                print(f"[YT] Test key {i}/{len(keys)}: {msg}")
            report = "\n".join(lines)
            if ok_all:
                self._ui(lambda: messagebox.showinfo("Test API Key", report))
            else:
                self._ui(lambda: messagebox.showerror("Test API Key", report))

        threading.Thread(target=run, daemon=True).start()

    def _edit_api_keys(self):
        """Dialog sửa DANH SÁCH API key: mỗi dòng 1 key. Tool dùng key
        theo thứ tự, key nào hết quota thì tự chuyển sang key kế tiếp."""
        win = tk.Toplevel(self.root)
        win.title("🔑 Danh sách API Key YouTube v3")
        win.geometry("560x420")
        ttk.Label(
            win,
            text="Mỗi dòng 1 API key. Tool dùng theo thứ tự từ trên xuống,\n"
                 "key nào hết quota sẽ tự chuyển sang key kế tiếp:").pack(
            anchor="w", padx=10, pady=(10, 4))
        txt = tk.Text(win, height=14, width=64)
        txt.pack(fill="both", expand=True, padx=10, pady=4)
        txt.insert("1.0", "\n".join(self.yt_api_keys))
        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=10, pady=8)

        def do_save():
            keys = _parse_yt_keys(txt.get("1.0", "end"))
            self.yt_api_keys = keys
            yt_keys_set(keys)
            self.yt_api_key_var.set(keys[0] if keys else "")
            self._persist_settings()
            self._yt_key_info_refresh()
            print(f"[YT] Đã lưu danh sách {len(keys)} API key")
            messagebox.showinfo(
                "Đã lưu",
                f"Đã lưu {len(keys)} API key.\n"
                "Khi 1 key hết quota, tool tự chuyển sang key kế tiếp.",
                parent=win)
            win.destroy()

        ttk.Button(bar, text="💾 Lưu DS Key", command=do_save).pack(
            side="left", padx=2)
        ttk.Button(bar, text="Huỷ", command=win.destroy).pack(
            side="left", padx=2)
        txt.focus_set()

    # ---------- Bang List Link YouTube ----------
    def _reg_entry(self, path, rows, parts=None):
        """Mục đăng ký 1 list đã lưu: kèm Loại nếu mọi link cùng 1 loại
        (để mở lại list vẫn biết link nào là Shorts, link nào Video dài).
        parts = cac file tung kenh cua 1 list gop nhieu kenh - de khi
        xoa list thi xoa sach ca chung khoi thu muc."""
        kinds = {r.get("kind") for r in rows}
        kind = (next(iter(kinds))
                if len(kinds) == 1 and None not in kinds else None)
        if parts:
            entry = {"path": path, "parts": list(parts)}
            if kind:
                entry["kind"] = kind
            return entry
        if kind:
            return {"path": path, "kind": kind}
        return path

    def _reg_parts(self, entry):
        """Danh sach file con (file tung kenh) cua 1 muc dang ky list."""
        if isinstance(entry, dict):
            return list(entry.get("parts") or [])
        return []

    def _reg_path_kind(self, entry):
        """Đọc 1 mục đăng ký list -> (đường dẫn file, loại hoặc None)."""
        if isinstance(entry, dict):
            return entry.get("path"), entry.get("kind")
        return entry, None

    def _yt_lists_registry(self):
        """Danh sách list đã lưu: {tên list: đường dẫn file} trong settings."""
        try:
            return dict(_load_settings().get("yt_lists", {}))
        except Exception:  # noqa
            return {}

    def _refresh_lists_combo(self):
        self.yt_lists_combo['values'] = sorted(self._yt_lists_registry().keys())

    def _refresh_link_table(self):
        """Vẽ lại bảng List Link từ self.yt_link_rows + trạng thái đã tải."""
        for item in self.link_tree.get_children():
            self.link_tree.delete(item)
        cache = _load_yt_cache()
        folder = self._yt_out_dir()
        assign_of = {}
        for _acc_id, _vids in (self.yt_assignments or {}).items():
            for _v in _vids:
                assign_of[_v] = _acc_id
        for i, row in enumerate(self.yt_link_rows):
            vid = row["id"]
            _up = self.yt_link_status.get(vid)
            _centry = cache.get(vid)
            if _up == "ok" or (isinstance(_centry, dict)
                               and _centry.get("uploaded")):
                status = "✅ Upload thành công"
            elif _up == "fail":
                status = "❌ Upload lỗi"
            elif vid in cache or (folder and _find_downloaded(folder, vid, cache)):
                status = "✅ Đã tải"
            else:
                status = "Chưa tải"
            kind_txt = {"shorts": "Shorts", "video": "Video dài"}.get(
                row.get("kind"), "—")
            self.link_tree.insert("", "end", values=(
                i + 1, vid, kind_txt, row.get("title", ""),
                fmt_duration(row.get("duration")),
                status, assign_of.get(vid, "—"),
                f"https://www.youtube.com/watch?v={vid}"),
                tags=("evenrow" if i % 2 == 0 else "oddrow",))
        self.yt_link_info_var.set(f"{len(self.yt_link_rows)} link")
        self._reapply_sort(self.link_tree)

    def _apply_link_rows(self, rows, name=None, file_path=None,
                         parts=None):
        """Đổ list link vào bảng, đăng ký vào list đã lưu (nếu có tên)
        và chuyển sang tab List Link cho người dùng thấy ngay."""
        self.yt_link_rows = list(rows)
        if name:
            self.yt_list_name_var.set(name)
            if file_path:
                reg = self._yt_lists_registry()
                reg[name] = self._reg_entry(file_path, rows,
                                            parts=parts)
                _update_settings({"yt_lists": reg})
                self._refresh_lists_combo()
                self.yt_list_pick_var.set(name)
        self._refresh_link_table()
        try:
            self.notebook.select(self.yt_tab)
        except Exception:  # noqa
            pass

    def _save_link_list(self):
        """Lưu bảng list hiện tại ra file .txt với tên list đã đặt."""
        if not self.yt_link_rows:
            messagebox.showwarning(
                "Trống", "Bảng list đang trống - hãy lấy list từ kênh hoặc mở 1 file list trước!")
            return
        name = (self.yt_list_name_var.get() or "").strip() or "list_link"
        safe = re.sub(r"[^\w\- ]", "_", name)
        path = filedialog.asksaveasfilename(
            title="Lưu list link", defaultextension=".txt",
            initialdir=str(APP_DIR), initialfile=f"yt_links_{safe}.txt",
            filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if not path:
            return
        Path(path).write_text(
            "\n".join(f"https://www.youtube.com/watch?v={r['id']}"
                       for r in self.yt_link_rows), encoding="utf-8")
        reg = self._yt_lists_registry()
        reg[name] = self._reg_entry(path, self.yt_link_rows)
        _update_settings({"yt_lists": reg})
        self._refresh_lists_combo()
        self.yt_list_pick_var.set(name)
        self.yt_links_file_var.set(path)
        print(f"[YT] Đã lưu list '{name}': {len(self.yt_link_rows)} link -> {path}")
        messagebox.showinfo("Đã lưu",
                            f"Đã lưu list '{name}' ({len(self.yt_link_rows)} link).\n{path}")

    def _open_saved_list(self):
        name = (self.yt_list_pick_var.get() or "").strip()
        path, kind = self._reg_path_kind(self._yt_lists_registry().get(name))
        if not path:
            messagebox.showwarning("Chưa chọn", "Hãy chọn 1 list đã lưu trong ô danh sách!")
            return
        if not Path(path).exists():
            messagebox.showerror("Lỗi", f"File của list '{name}' không còn tồn tại:\n{path}")
            return
        self._load_link_file_into_table(path, name, kind)

    def _delete_saved_list(self):
        name = (self.yt_list_pick_var.get() or "").strip()
        reg = self._yt_lists_registry()
        if name not in reg:
            messagebox.showwarning("Chưa chọn", "Hãy chọn 1 list đã lưu để xoá!")
            return
        entry = reg[name]
        path, _k = self._reg_path_kind(entry)
        targets = [path] + self._reg_parts(entry)
        if not messagebox.askyesno(
                "Xoá list",
                f"Xoá list '{name}' khỏi danh sách quản lý?\n"
                f"(Sẽ xoá luôn {len(targets)} file của list này "
                f"trong thư mục cạnh tool.)"):
            return
        reg.pop(name)
        _update_settings({"yt_lists": reg})
        self._refresh_lists_combo()
        self.yt_list_pick_var.set("")
        deleted, failed = self._delete_list_files(targets,
                                                  only_app_dir=False)
        cur = (self.yt_links_file_var.get() or "").strip()
        if path and cur and str(Path(cur)) == str(Path(path)):
            self.yt_links_file_var.set("")
        print(f"[YT] Đã xoá list '{name}': xoá {deleted} file khỏi "
              f"thư mục"
              + (f", {len(failed)} file xoá không được" if failed
                 else ""))
        if failed:
            messagebox.showwarning(
                "Chưa xoá hết file",
                "Các file sau chưa xoá được (có thể đang mở ở Notepad/"
                "chương trình khác - đóng lại rồi bấm Xoá list lại):\n"
                + "\n".join(failed))

    def _delete_list_files(self, paths, only_app_dir=True):
        """Xoá các file list; only_app_dir=True thi chi xoa file nam
        trong APP_DIR (an toan cho quet hang loat). Tra
        (so file da xoa, [ten file xoa khong duoc])."""
        deleted = 0
        failed = []
        seen = set()
        for p in paths:
            if not p:
                continue
            pp = Path(p)
            try:
                key = str(pp.resolve())
            except Exception:  # noqa
                key = str(pp)
            if key in seen:
                continue
            seen.add(key)
            if not pp.exists():
                continue
            if only_app_dir:
                try:
                    if pp.resolve().parent != APP_DIR.resolve():
                        continue
                except Exception:  # noqa
                    continue
            try:
                pp.unlink()
                deleted += 1
            except Exception:  # noqa
                failed.append(pp.name)
        return deleted, failed

    def _load_link_file_into_table(self, path, name, kind=None):
        """Đọc 1 file list link -> đổ vào bảng; lấy tiêu đề + thời lượng
        ở nền nếu có API key."""
        ids, seen = [], set()
        for line in Path(path).read_text(encoding="utf-8",
                                         errors="ignore").splitlines():
            vid = parse_youtube_id(line)
            if vid and vid not in seen:
                seen.add(vid)
                ids.append(vid)
        self.yt_fetched_ids = ids
        self.yt_links_file_var.set(str(path))
        self._apply_link_rows(
            [{"id": v, "title": "", "duration": None, "kind": kind}
             for v in ids], name, str(path))
        print(f"[YT] Đã mở list '{name}': {len(ids)} link")
        key = self._yt_active_key()
        if key and ids:
            def fill():
                try:
                    meta, _u = fetch_yt_metadata(key, ids)
                    rows = [{"id": v, "kind": kind,
                             "title": (meta.get(v) or {}).get("title", ""),
                             "duration": (meta.get(v) or {}).get("duration")}
                            for v in ids]
                    self._ui(lambda r=rows: self._apply_link_rows(r, name, str(path)))
                except Exception:  # noqa
                    pass
            threading.Thread(target=fill, daemon=True).start()

    def _selected_link_ids(self):
        out = []
        for item in self.link_tree.selection():
            vals = self.link_tree.item(item, "values")
            if vals and len(vals) > 1:
                out.append(vals[1])
        return out

    def _download_selected_links(self):
        """Tải các link đang chọn trong bảng (không chọn = tải cả bảng)."""
        if self.yt_downloading:
            messagebox.showwarning("Cảnh báo", "Đang tải video YouTube...")
            return
        ids = self._selected_link_ids() or [r["id"] for r in self.yt_link_rows]
        if not ids:
            messagebox.showerror("Lỗi", "Bảng list đang trống!")
            return
        out_dir = self._yt_out_dir()
        if not out_dir:
            messagebox.showerror(
                "Lỗi", "Chưa chọn Folder Video - video tải về sẽ vào thư mục đó!")
            return
        self.yt_downloading = True
        threading.Thread(
            target=self._download_links_thread,
            args=(ids, out_dir, self._yt_active_key(),
                  max(1, self.yt_threads_var.get())),
            daemon=True).start()

    def _download_links_thread(self, ids, out_dir, api_key, threads):
        try:
            self._yt_download_ids(ids, out_dir, api_key, threads)
        except Exception as e:  # noqa
            print(f"[YT] Lỗi tải: {_short(e)}")
        finally:
            self.yt_downloading = False
            self._ui(self._refresh_link_table)

    def _link_open_selected(self, event=None):
        ids = self._selected_link_ids()
        if ids:
            webbrowser.open(f"https://www.youtube.com/watch?v={ids[0]}")

    def _link_right_click(self, event):
        item = self.link_tree.identify_row(event.y)
        if item and item not in self.link_tree.selection():
            self.link_tree.selection_set(item)
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(label="📋 Copy link",
                         command=lambda: self._copy_text(
                             "\n".join(f"https://www.youtube.com/watch?v={v}"
                                        for v in self._selected_link_ids()), "link"))
        menu.add_command(label="📋 Copy Video ID",
                         command=lambda: self._copy_text(
                             "\n".join(self._selected_link_ids()), "Video ID"))
        menu.add_command(label="🌐 Mở trong trình duyệt",
                         command=self._link_open_selected)
        menu.add_command(label="Chọn tất cả (Ctrl+A)", command=self._link_select_all)
        menu.add_separator()
        menu.add_command(label="🔀 Random link (tráo vị trí ngẫu nhiên)",
                         command=self._shuffle_link_rows)
        menu.add_command(label="⏱ Xoá link theo thời lượng video...",
                         command=self._delete_links_by_duration_dialog)
        menu.add_separator()
        menu.add_command(label="🔁 Chọn các link Upload lỗi (để chạy lại)",
                         command=self._select_failed_links)
        menu.add_command(label="🗑 Xoá các link Upload thành công",
                         command=self._delete_uploaded_links)
        menu.add_command(label="📤 Chuyển các dòng đã chọn sang list khác...",
                         command=self._move_selected_links_dialog)
        menu.add_separator()
        menu.add_command(label="🗑 Xoá dòng đã chọn khỏi bảng",
                         command=self._remove_selected_link_rows)
        menu.post(event.x_root, event.y_root)

    def _shuffle_link_rows(self):
        """Chuột phải List Link: tráo vị trí các link ngẫu nhiên (Random),
        ghi lại luôn vào file list hiện tại."""
        if len(self.yt_link_rows) < 2:
            messagebox.showinfo("Random link",
                                "Cần ít nhất 2 link trong bảng để tráo vị trí!")
            return
        random.shuffle(self.yt_link_rows)
        self.yt_fetched_ids = [r["id"] for r in self.yt_link_rows]
        self._refresh_link_table()
        self._persist_link_file()
        print(f"[YT] 🔀 Đã tráo ngẫu nhiên vị trí {len(self.yt_link_rows)} link trong bảng")

    def _delete_links_by_duration_dialog(self):
        """Chuột phải List Link: xoá các link có thời lượng video NHỎ HƠN
        hoặc LỚN HƠN số giây tự chọn (vd < 5s, > 180s). Link chưa rõ thời
        lượng (chưa lấy được metadata) thì giữ lại."""
        if not self.yt_link_rows:
            messagebox.showinfo("Xoá theo thời lượng", "Bảng list đang trống!")
            return
        win = tk.Toplevel(self.root)
        win.title("Xoá link theo thời lượng video")
        win.geometry("400x220")
        win.transient(self.root)
        win.lift()
        mode_var = tk.StringVar(value="lt")
        sec_var = tk.IntVar(value=5)
        btn_row = ttk.Frame(win)
        btn_row.pack(side="bottom", fill="x", padx=12, pady=10)

        def do_delete():
            try:
                sec = int(sec_var.get())
            except Exception:  # noqa
                sec = 0
            if sec <= 0:
                messagebox.showwarning("Chưa hợp lệ", "Hãy nhập số giây > 0!", parent=win)
                return
            lt = mode_var.get() == "lt"
            drop, unknown = [], 0
            for r in self.yt_link_rows:
                d = r.get("duration")
                if d is None:
                    unknown += 1
                    continue
                if (lt and d < sec) or (not lt and d > sec):
                    drop.append(r["id"])
            if not drop:
                messagebox.showinfo(
                    "Không có link nào khớp",
                    f"Không có link nào {'nhỏ hơn' if lt else 'lớn hơn'} {sec}s trong bảng.",
                    parent=win)
                return
            if not messagebox.askyesno(
                    "Xoá link theo thời lượng",
                    f"Xoá {len(drop)} link có thời lượng {'<' if lt else '>'} {sec}s khỏi bảng?",
                    parent=win):
                return
            drop_set = set(drop)
            self.yt_link_rows = [r for r in self.yt_link_rows if r["id"] not in drop_set]
            self.yt_fetched_ids = [v for v in self.yt_fetched_ids if v not in drop_set]
            changed_assign = False
            for _acc_id in list((self.yt_assignments or {}).keys()):
                _vids = self.yt_assignments[_acc_id]
                _kept = [v for v in _vids if v not in drop_set]
                if len(_kept) != len(_vids):
                    self.yt_assignments[_acc_id] = _kept
                    changed_assign = True
            if changed_assign:
                self._save_assignments()
            self._refresh_link_table()
            self._persist_link_file()
            print(f"[YT] ⏱ Đã xoá {len(drop)} link theo thời lượng ({'<' if lt else '>'} {sec}s)"
                  + (f"; giữ lại {unknown} link chưa rõ thời lượng" if unknown else ""))
            win.destroy()

        ttk.Button(btn_row, text="🗑 Xoá các link khớp", style="Accent.TButton",
                   command=do_delete).pack(side="right")
        ttk.Button(btn_row, text="Huỷ", command=win.destroy).pack(side="right", padx=6)
        ttk.Label(win, text="Xoá các link có thời lượng video:").pack(anchor="w", padx=12, pady=(12, 4))
        r1 = ttk.Frame(win)
        r1.pack(fill="x", padx=12, pady=2)
        ttk.Radiobutton(r1, text="Nhỏ hơn", value="lt", variable=mode_var).pack(side="left")
        ttk.Radiobutton(r1, text="Lớn hơn", value="gt", variable=mode_var).pack(side="left", padx=10)
        r2 = ttk.Frame(win)
        r2.pack(fill="x", padx=12, pady=4)
        ttk.Label(r2, text="Số giây:").pack(side="left")
        ttk.Spinbox(r2, from_=1, to=86400, width=8, textvariable=sec_var).pack(side="left", padx=6)
        ttk.Label(win, text="Ví dụ: Nhỏ hơn 5 = xoá video < 5s; Lớn hơn 180 = xoá video > 180s.\n"
                            "Link chưa rõ thời lượng sẽ được giữ lại.").pack(anchor="w", padx=12, pady=4)

    def _persist_link_file(self):
        """Ghi lại file list link hiện tại theo đúng các dòng còn trong bảng
        (gọi ngay sau khi xoá link - file text tự lưu lại luôn)."""
        lf = (self.yt_links_file_var.get() or "").strip()
        if not lf:
            return
        try:
            Path(lf).write_text(
                "\n".join(f"https://www.youtube.com/watch?v={r['id']}"
                           for r in self.yt_link_rows), encoding="utf-8")
        except Exception:  # noqa
            pass

    def _remove_selected_link_rows(self):
        drop = set(self._selected_link_ids())
        if not drop:
            return
        self.yt_link_rows = [r for r in self.yt_link_rows if r["id"] not in drop]
        self.yt_fetched_ids = [v for v in self.yt_fetched_ids if v not in drop]
        self._refresh_link_table()
        self._persist_link_file()
        print(f"[YT] Đã xoá {len(drop)} dòng khỏi bảng list (file list đã lưu lại)")

    # ---------- Chon tat ca + loc theo Loai ----------
    def _link_select_all(self, event=None):
        """Ctrl+A trong bảng List Link: chọn tất cả dòng."""
        kids = self.link_tree.get_children()
        if kids:
            self.link_tree.selection_set(kids)
        return "break"

    # ---------- Link da dung: xoa khoi list sau khi upload thanh cong ----------
    def _consume_link(self, vid):
        """Xoá 1 link khỏi bảng List Link + file list hiện tại. Gọi khi link
        đó đã được gán cho account và upload thành công - tránh dùng lại."""
        before = len(self.yt_link_rows)
        self.yt_link_rows = [r for r in self.yt_link_rows if r["id"] != vid]
        if vid in self.yt_fetched_ids:
            self.yt_fetched_ids.remove(vid)
        if len(self.yt_link_rows) != before:
            self._refresh_link_table()
        self._persist_link_file()
        print(f"[PIPE] Đã xoá link {vid} khỏi list (đã dùng xong)")

    def _save_assignments(self):
        """Luu phan gan link -> account vao tool_settings.json de tat
        mo lai tool van con nguyen, khoi phai gan lai."""
        _update_settings({"yt_assignments": self.yt_assignments})

    def _prune_assignments(self, done_ids):
        """Bỏ các link đã upload thành công khỏi phần gán còn lưu trong bộ
        nhớ, để bấm START lần nữa không chạy lại link cũ."""
        done = set(done_ids)
        if not done:
            return
        new_assign = {}
        for acc_id, vids in self.yt_assignments.items():
            rest = [v for v in vids if v not in done]
            if rest:
                new_assign[acc_id] = rest
        self.yt_assignments = new_assign
        self._save_assignments()

    # ---------- Trang thai upload cua tung link (bang List Link) ----------
    def _mark_link_uploaded(self, vid):
        """Danh dau 1 link la 'Upload thanh cong': hien trong cot Trang
        thai cua bang List Link, ghi co vao yt_downloaded.json de tat
        mo tool van nho, va cat khoi phan gan de START khong chay lai.
        Link KHONG con tu xoa khoi bang - nguoi dung tu xoa bang chuot
        phai 'Xoa cac link Upload thanh cong'."""
        self.yt_link_status[vid] = "ok"
        try:
            entry = dict(_load_yt_cache().get(vid) or {})
            entry["uploaded"] = True
            entry["uploaded_ts"] = int(time.time())
            _save_yt_cache_entry(vid, entry)
        except Exception:  # noqa
            pass
        self._prune_assignments([vid])
        self._refresh_link_table()
        print(f"[PIPE] ✅ Link {vid}: Upload thành công (đã đánh dấu trong bảng)")

    def _mark_link_failed(self, vid):
        """Danh dau 1 link la 'Upload loi' trong bang List Link. Link van
        o lai trong phan gan de bam START chay lai."""
        if self.yt_link_status.get(vid) != "ok":
            self.yt_link_status[vid] = "fail"
        self._refresh_link_table()

    def _select_failed_links(self):
        """Chuot phai: chon (to sang) dung cac dong dang 'Upload loi'
        trong bang List Link - de nhin lai hoac bam START chay lai."""
        fails = {v for v, st in self.yt_link_status.items() if st == "fail"}
        if not fails:
            messagebox.showinfo("Upload lỗi",
                                "Chưa có link nào ở trạng thái Upload lỗi.")
            return
        picked = 0
        for item in self.link_tree.get_children():
            vals = self.link_tree.item(item, "values")
            if vals and str(vals[1]) in fails:
                self.link_tree.selection_add(item)
                picked += 1
            else:
                self.link_tree.selection_remove(item)
        print(f"[YT] Đã chọn {picked} link Upload lỗi trong bảng - bấm "
              f"'▶ START' (Upload Online) để chạy lại đúng các link này.")

    def _delete_uploaded_links(self):
        """Chuot phai: xoa khoi bang + file list tat ca link da 'Upload
        thanh cong' (don list sau khi dang xong)."""
        oks = {v for v, st in self.yt_link_status.items() if st == "ok"}
        cache = _load_yt_cache()
        oks |= {v for v, e in cache.items()
                if isinstance(e, dict) and e.get("uploaded")}
        oks &= {r["id"] for r in self.yt_link_rows}
        if not oks:
            messagebox.showinfo("Upload thành công",
                                "Chưa có link nào ở trạng thái Upload thành công.")
            return
        self.yt_link_rows = [r for r in self.yt_link_rows
                             if r["id"] not in oks]
        self.yt_fetched_ids = [v for v in self.yt_fetched_ids
                               if v not in oks]
        for v in oks:
            self.yt_link_status.pop(v, None)
        self._prune_assignments(list(oks))
        self._refresh_link_table()
        self._persist_link_file()
        print(f"[YT] Đã xoá {len(oks)} link Upload thành công khỏi "
              f"bảng + file list.")

    def _move_selected_links_dialog(self):
        """Chuot phai: chuyen cac dong link dang chon trong bang List Link
        sang 1 file list khac - chon list da luu hoac tao list moi."""
        ids = self._selected_link_ids()
        if not ids:
            messagebox.showinfo(
                "Chuyển list",
                "Hãy tô chọn ít nhất 1 dòng link trong bảng trước!")
            return
        reg = self._yt_lists_registry()
        cur_file = (self.yt_links_file_var.get() or "").strip()
        dlg = tk.Toplevel(self.root)
        dlg.title("Chuyển link sang list khác")
        dlg.geometry("460x370")
        dlg.transient(self.root)
        dlg.grab_set()
        ttk.Label(dlg, text=f"Chuyển {len(ids)} link đã chọn sang:",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12,
                                                      pady=(12, 4))
        ttk.Label(dlg, text="Chọn 1 list đã lưu:").pack(anchor="w", padx=12)
        lb = tk.Listbox(dlg, height=8, font=("Segoe UI", 10))
        lb.pack(fill="x", padx=12, pady=4)
        names = []
        for nm in reg:
            pth, _k = self._reg_path_kind(reg.get(nm))
            if pth and cur_file and str(Path(pth)) == str(Path(cur_file)):
                continue  # bo qua chinh list dang mo
            names.append(nm)
            lb.insert("end", nm)
        ttk.Label(dlg, text="...hoặc tạo list mới với tên:").pack(
            anchor="w", padx=12, pady=(8, 0))
        name_var = tk.StringVar()
        ttk.Entry(dlg, textvariable=name_var).pack(fill="x", padx=12, pady=4)

        def do_move():
            new_name = (name_var.get() or "").strip()
            if new_name:
                safe = re.sub(r"[^\w\- ]", "_", new_name)
                path = str(APP_DIR / f"yt_links_{safe}.txt")
                if cur_file and str(Path(path)) == str(Path(cur_file)):
                    messagebox.showwarning(
                        "Trùng list",
                        "Tên list mới trùng với list đang mở - "
                        "hãy đặt tên khác!", parent=dlg)
                    return
                self._move_links_to_file(ids, path, new_name, is_new=True)
                dlg.destroy()
                return
            sel = lb.curselection()
            if not sel:
                messagebox.showwarning(
                    "Chưa chọn",
                    "Hãy chọn 1 list đã lưu hoặc nhập tên list mới!",
                    parent=dlg)
                return
            nm = names[sel[0]]
            pth, _k = self._reg_path_kind(reg.get(nm))
            self._move_links_to_file(ids, pth, nm, is_new=False)
            dlg.destroy()

        btns = ttk.Frame(dlg)
        btns.pack(fill="x", padx=12, pady=10)
        ttk.Button(btns, text="📤 Chuyển", style="Accent.TButton",
                   command=do_move).pack(side="left")
        ttk.Button(btns, text="Huỷ", command=dlg.destroy).pack(side="left",
                                                               padx=8)

    def _move_links_to_file(self, ids, target_path, target_name,
                            is_new=False):
        """Ghi cac link (theo id) vao file list dich (tranh trung lap),
        dang ky list moi neu can, roi go khoi bang + file list hien tai
        + phan gan."""
        idset = set(ids)
        rows_move = [r for r in self.yt_link_rows if r["id"] in idset]
        existing = set()
        tp = Path(target_path)
        if tp.exists():
            for line in tp.read_text(encoding="utf-8",
                                     errors="ignore").splitlines():
                v = parse_youtube_id(line)
                if v:
                    existing.add(v)
        to_add = [r for r in rows_move if r["id"] not in existing]
        try:
            with tp.open("a", encoding="utf-8") as f:
                for r in to_add:
                    f.write(f"https://www.youtube.com/watch?v={r['id']}\n")
        except Exception as e:  # noqa
            messagebox.showerror(
                "Lỗi", f"Không ghi được vào file list đích:\n"
                       f"{target_path}\n{_short(e)}")
            return
        if is_new:
            reg = self._yt_lists_registry()
            reg[target_name] = self._reg_entry(target_path, rows_move)
            _update_settings({"yt_lists": reg})
            self._refresh_lists_combo()
        self.yt_link_rows = [r for r in self.yt_link_rows
                             if r["id"] not in idset]
        self.yt_fetched_ids = [v for v in self.yt_fetched_ids
                               if v not in idset]
        self._prune_assignments(list(idset))
        self._refresh_link_table()
        self._persist_link_file()
        dup = len(rows_move) - len(to_add)
        print(f"[YT] Đã chuyển {len(to_add)} link sang list "
              f"'{target_name}' ({target_path}) - gỡ {len(rows_move)} link "
              f"khỏi list hiện tại"
              + (f" ({dup} link đã có sẵn ở list đích)" if dup else ""))

    # ---------- Xuat cookie TikTok tu profile GPM ----------
    def _export_info_dialog(self):
        """Xuất thông tin các account ĐÃ TÔ ĐEN (đang chọn) ra file .txt:
        đúng 8 CỘT TUỲ CHỌN (mặc định 8 trường chuẩn của accounts.txt),
        mỗi account 1 dòng, các cột cách nhau bằng dấu |. Bộ cột đã chọn
        được nhớ vào tool_settings.json (export_cols)."""
        targets = self._selected_accounts()
        if not targets:
            messagebox.showwarning(
                "Chưa chọn account",
                "Hãy tô đen (chọn) các account cần xuất thông tin trước!")
            return
        fields = [("id", "ID TikTok"), ("password", "Password"),
                  ("email", "Email"), ("passmail", "Pass Email"),
                  ("refresh_token", "Refresh Token"), ("client_id", "Client ID"),
                  ("cookie", "Cookie"), ("mailbackup", "Mail Backup"),
                  ("group", "Group"), ("proxy", "Proxy"),
                  ("follows", "Follow"), ("likes", "Like"),
                  ("views30d", "View 30d"), ("views", "Tổng View"),
                  ("videos", "Tổng Video"), ("country", "Quốc gia"),
                  ("status_live", "Tình trạng"), ("alogin", "Auto Login"),
                  ("note", "Note")]
        labels = [lb for _k, lb in fields]
        key_of = {lb: k for k, lb in fields}
        label_of = dict(fields)
        defaults = ["id", "password", "email", "passmail",
                    "refresh_token", "client_id", "cookie", "mailbackup"]
        saved = _load_settings().get("export_cols") or defaults
        saved = [k for k in saved if k in label_of][:8]
        while len(saved) < 8:
            saved.append(defaults[len(saved)])
        win = tk.Toplevel(self.root)
        win.title("Xuất thông tin account ra .txt")
        win.geometry("520x300")
        win.transient(self.root)
        win.lift()
        btn_row = ttk.Frame(win)
        btn_row.pack(side="bottom", fill="x", padx=12, pady=10)
        ttk.Label(win, text=f"Xuất {len(targets)} account đã chọn - chọn 8 cột theo thứ tự dòng xuất:"
                  ).pack(anchor="w", padx=12, pady=(12, 6))
        grid = ttk.Frame(win)
        grid.pack(fill="x", padx=12)
        vars8 = []
        for i in range(8):
            r, c = divmod(i, 2)
            ttk.Label(grid, text=f"Cột {i + 1}:").grid(row=r, column=c * 2, sticky="w", pady=3)
            v = tk.StringVar(value=label_of[saved[i]])
            cb = ttk.Combobox(grid, textvariable=v, values=labels,
                              state="readonly", width=20)
            cb.grid(row=r, column=c * 2 + 1, padx=(4, 14), pady=3)
            vars8.append(v)
        ttk.Label(win, text="Mỗi account 1 dòng, các cột cách nhau bằng dấu | như accounts.txt."
                  ).pack(anchor="w", padx=12, pady=(8, 0))

        def do_export():
            keys = []
            for v in vars8:
                k = key_of.get(v.get())
                if not k:
                    messagebox.showwarning("Thiếu cột", "Hãy chọn đủ 8 cột!", parent=win)
                    return
                keys.append(k)
            path = filedialog.asksaveasfilename(
                title="Lưu file xuất thông tin", defaultextension=".txt",
                initialfile="accounts_export.txt",
                filetypes=[("Text", "*.txt"), ("All", "*.*")], parent=win)
            if not path:
                return
            _update_settings({"export_cols": keys})
            lines = []
            for acc in targets:
                vals = []
                for k in keys:
                    if k == "status_live":
                        vals.append("Die" if acc.get("scan_dead") else "Live")
                    else:
                        vals.append(str(acc.get(k, "") or "").replace("\n", " "))
                lines.append("|".join(vals))
            Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
            print(f"[OK] Đã xuất thông tin {len(lines)} account ra {path} "
                  f"(cột: {', '.join(keys)})")
            messagebox.showinfo("Đã xuất",
                                f"Đã ghi {len(lines)} account vào file:\n{path}",
                                parent=win)
            win.destroy()

        ttk.Button(btn_row, text="📤 Xuất ra file .txt", style="Accent.TButton",
                   command=do_export).pack(side="right")
        ttk.Button(btn_row, text="Huỷ", command=win.destroy).pack(side="right", padx=6)

    def _export_cookies(self):
        """Xuất cookie TikTok từ các profile GPM đã login sẵn và lưu
        thẳng vào cột Cookie của từng account trong bảng (accounts.txt).
        Account đang chọn thì chỉ xuất cho account đó; không chọn thì
        xuất cho tất cả. Tôn trọng ô Ẩn trình duyệt và nút STOP."""
        global GRID_TOTAL, HIDE_BROWSER
        if self.cookie_exporting:
            messagebox.showwarning("Cảnh báo", "Đang xuất cookie...")
            return
        targets = self._selected_accounts() or list(self.all_accounts)
        if not targets:
            messagebox.showerror("Lỗi", "Chưa có account nào trong bảng!")
            return
        threads = max(1, min(self.threads_var.get(), len(targets)))
        GRID_TOTAL = max(1, threads)
        _set_launch_delay(self.up_delay_var.get())
        HIDE_BROWSER = bool(self.hide_browser_var.get())
        self.stop_requested = False
        clear_engine_stop()
        self.cookie_exporting = True
        print(f"[COOKIE] Bắt đầu xuất cookie cho {len(targets)} account "
              f"({threads} luồng, ẩn trình duyệt: "
              f"{'BẬT' if HIDE_BROWSER else 'tắt'})...")
        threading.Thread(target=self._export_cookies_worker,
                         args=(targets, threads), daemon=True).start()

    def _export_cookies_worker(self, targets, threads):
        done = {"n": 0, "ok": 0}
        def task(a):
            if self.stop_requested:
                return None
            return export_cookie_selenium(a["id"])
        try:
            with ThreadPoolExecutor(max_workers=threads) as ex:
                futs = {ex.submit(task, acc): acc for acc in targets}
                for fut in as_completed(futs):
                    acc = futs[fut]
                    try:
                        cookie_str = fut.result()
                    except Exception:  # noqa
                        cookie_str = ""
                    if cookie_str is None:
                        acc["last_status"] = "⏹ Đã dừng"
                        self._ui(lambda a=acc: self._refresh_acc_row(a))
                        continue
                    if not cookie_str and self.stop_requested:
                        acc["last_status"] = "⏹ Đã dừng"
                        self._ui(lambda a=acc: self._refresh_acc_row(a))
                        continue
                    done["n"] += 1
                    if cookie_str:
                        acc["cookie"] = cookie_str
                        acc["last_status"] = "🍪 Đã xuất cookie"
                        done["ok"] += 1
                        print(f"[COOKIE] ({done['n']}/{len(targets)}) ✅ "
                              f"@{acc['id']}: đã lưu cookie "
                              f"({len(cookie_str)} ký tự, có cookie phiên)")
                    else:
                        acc["last_status"] = "❌ Xuất cookie lỗi"
                        print(f"[COOKIE] ({done['n']}/{len(targets)}) ❌ "
                              f"@{acc['id']}: không lấy được cookie "
                              f"(chưa login? profile lỗi?) - giữ cookie cũ")
                    self._ui(lambda a=acc: self._refresh_acc_row(a))
            if done["ok"]:
                self._save_accounts()
                print(f"[COOKIE] Đã ghi cookie mới của {done['ok']} account "
                      f"vào accounts.txt")
        finally:
            self.cookie_exporting = False
            print(f"[COOKIE] Hoàn tất: {done['ok']}/{len(targets)} account "
                  f"xuất cookie thành công.")
            self._notify_done(
                "Xuất Cookie",
                ("⏹ Đã dừng xuất cookie theo yêu cầu.\n"
                 if self.stop_requested else "✅ Xuất cookie đã xong!\n")
                + f"Thành công: {done['ok']}/{len(targets)} account")

    # ---------- STOP: kill trinh duyet + dung ngay lap tuc ----------
    def _stop_all_runs(self):
        """Bấm STOP: KILL NGAY mọi trình duyệt tool đang mở (kể cả video
        đang upload dở) và dừng toàn bộ hàng chờ (Offline + Online +
        Xuất Cookie) - không chờ chạy xong nốt."""
        if (self.busy or self.pipeline_running
                or getattr(self, "cookie_exporting", False)
                or getattr(self, "alogin_running", False)):
            self.stop_requested = True
            threading.Thread(target=self._kill_browsers_now,
                             daemon=True).start()
            print("[STOP] ⏹ Đã bấm STOP - kill toàn bộ trình duyệt ngay "
                  "lập tức, dừng mọi hàng chờ.")
        else:
            print("[STOP] Hiện không có tiến trình nào đang chạy.")

    def _kill_browsers_now(self):
        n = request_engine_stop()
        if n:
            print(f"[STOP] Đã kill {n} trình duyệt đang mở.")

    # ---------- Bao cao sau upload: file txt + Telegram ----------
    def _report_upload_result(self, source, ok_count, fail_count, failed_accs):
        """Sau 1 đợt upload: nếu có account lỗi thì gửi danh sách
        account lỗi về Telegram (khi đã nhập Token + Chat ID).
        KHÔNG xuất file txt nữa (tránh rác thư mục)."""
        failed_accs = list(dict.fromkeys(failed_accs))
        if not failed_accs:
            return
        token = (self.tele_token_var.get() or "").strip()
        chat_id = (self.tele_chat_var.get() or "").strip()
        if not token or not chat_id:
            print("[REPORT] Chưa nhập đủ Token + Chat ID Telegram "
                  "- không gửi báo cáo lỗi.")
            return
        shown = failed_accs[:100]
        extra = (f"\n... và {len(failed_accs) - 100} account nữa"
                 if len(failed_accs) > 100 else "")
        text = (f"❌ TikTok Upload - {source}\n"
                f"⏰ {time.strftime('%d/%m/%Y %H:%M:%S')}\n"
                f"✅ Thành công: {ok_count} | ❌ Lỗi: {fail_count}\n"
                f"Account lỗi ({len(failed_accs)}):\n"
                + "\n".join(shown) + extra)
        err = send_telegram_message(token, chat_id, text)
        if err:
            print(f"[REPORT] Gửi Telegram lỗi: {err}")
        else:
            print("[REPORT] Đã gửi danh sách account lỗi lên Telegram.")

    def _test_telegram(self):
        token = (self.tele_token_var.get() or "").strip()
        chat_id = (self.tele_chat_var.get() or "").strip()
        if not token or not chat_id:
            messagebox.showwarning(
                "Thiếu thông tin",
                "Hãy nhập Bot Token và Chat ID trước (Chat ID lấy bằng nút "
                "'Lấy Chat ID' sau khi nhắn /start cho bot).")
            return
        self._persist_settings()
        print("[TELE] Đang gửi tin nhắn test...")
        def run():
            err = send_telegram_message(
                token, chat_id,
                "✅ Test từ TikTok Upload Tool - kết nối Telegram OK!")
            if err:
                print(f"[TELE] Gửi test lỗi: {err}")
            else:
                print("[TELE] Đã gửi tin test - hãy kiểm tra Telegram của bạn.")
        threading.Thread(target=run, daemon=True).start()

    def _fetch_chat_id(self):
        token = (self.tele_token_var.get() or "").strip()
        if not token:
            messagebox.showwarning("Thiếu Token", "Hãy dán Bot Token trước!")
            return
        print("[TELE] Đang lấy Chat ID từ bot...")
        def run():
            chat_id, info = fetch_telegram_chat_id(token)
            if chat_id:
                def apply():
                    self.tele_chat_var.set(chat_id)
                    self._persist_settings()
                    print(f"[TELE] Đã lấy Chat ID: {chat_id} ({info})")
                self._ui(apply)
            else:
                print(f"[TELE] Không lấy được Chat ID: {info}")
        threading.Thread(target=run, daemon=True).start()

    def _open_log_window(self):
        """Mở cửa sổ Log tiến trình riêng: hiện toàn bộ log đã chạy (lưu
        trong bộ đệm _log_buffer), log mới vẫn chảy tiếp vào cửa sổ khi
        đang mở. Có nút Copy log để chép toàn bộ log."""
        existing = getattr(self, "_log_win", None)
        if existing is not None:
            try:
                existing.lift()
                existing.focus_force()
                return
            except Exception:  # noqa
                self._log_win = None
                self._log_win_text = None
        win = tk.Toplevel(self.root)
        win.title("Log tiến trình")
        win.geometry("920x560")
        self._log_win = win
        btn_row = ttk.Frame(win)
        btn_row.pack(side="bottom", fill="x", padx=8, pady=8)
        txt_frame = ttk.Frame(win)
        txt_frame.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        sc = ttk.Scrollbar(txt_frame)
        sc.pack(side="right", fill="y")
        tw = tk.Text(txt_frame, yscrollcommand=sc.set,
                     font=("Consolas", 9), wrap="none")
        sc.config(command=tw.yview)
        tw.pack(fill="both", expand=True)
        tw.insert("end", "".join(self._log_buffer))
        tw.see("end")
        self._log_win_text = tw

        def _copy_log():
            self.root.clipboard_clear()
            self.root.clipboard_append("".join(self._log_buffer))
            print("[OK] Đã copy toàn bộ log tiến trình vào clipboard")

        def _clear_log():
            self._log_buffer.clear()
            try:
                tw.delete("1.0", "end")
            except Exception:  # noqa
                pass

        def _on_close():
            self._log_win = None
            self._log_win_text = None
            win.destroy()

        ttk.Button(btn_row, text="📋 Copy log", style="Accent.TButton",
                   command=_copy_log).pack(side="left")
        ttk.Button(btn_row, text="🗑 Xoá log", command=_clear_log).pack(side="left", padx=6)
        ttk.Button(btn_row, text="Đóng", command=_on_close).pack(side="right")
        win.protocol("WM_DELETE_WINDOW", _on_close)

    def _update_log(self):
        """Cập nhật log + chay cac ham cap nhat UI duoc dua tu luong phu."""
        try:
            while True:
                msg = self.logq.get_nowait()
                self._log_buffer.append(msg)
                if len(self._log_buffer) > 12000:
                    del self._log_buffer[:2000]
                _lw = getattr(self, "_log_win_text", None)
                if _lw is not None:
                    try:
                        _lw.insert("end", msg)
                        _lw.see("end")
                    except Exception:  # noqa
                        self._log_win_text = None
        except queue.Empty:
            pass
        try:
            while True:
                fn = self.uiq.get_nowait()
                try:
                    fn()
                except Exception as e:  # noqa
                    print(f"[LỖI UI] {e}")
        except queue.Empty:
            pass

        self.root.after(500, self._update_log)


def main():
    root = tk.Tk()
    app = AppUpload(root)
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--cli":
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        _cli_main()
    else:
        main()