from playwright.sync_api import sync_playwright, TimeoutError
import os
import requests
import time
from typing import Tuple

def send_telegram_message(message: str) -> dict:
    """
    使用bot API发送Telegram消息
    
    参数:
        message: 要发送的消息
    返回:
        dict: Telegram API响应
    """
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    response = requests.post(url, json=payload)
    return response.json()

def attempt_login(page, email: str, password: str) -> Tuple[bool, str]:
    """
    尝试登录WebHost账户
    
    参数:
        page: Playwright页面对象
        email: 用户邮箱
        password: 用户密码
    返回:
        Tuple[bool, str]: (成功状态, 消息)
    """
    try:
        # 导航到登录页面
        page.goto("https://client.webhostmost.com/login")
        time.sleep(5)
        # 填写登录表单
        page.get_by_placeholder("Enter email").click()
        page.get_by_placeholder("Enter email").fill(email)
        page.get_by_placeholder("Password").click()
        page.get_by_placeholder("Password").fill(password)
        
        # 提交登录表单
        page.get_by_role("button", name="Login").click()
        time.sleep(10)
        # 检查错误消息
        try:
            error_message = page.wait_for_selector('.MuiAlert-message', timeout=5000)
            if error_message:
                error_text = error_message.inner_text()
                return False, f"登录失败：{error_text}"
        except TimeoutError:
            # 检查是否成功重定向到仪表板
            try:
                page.wait_for_url("https://client.webhostmost.com/clientarea.php", timeout=5000)
                return True, "登录成功！"
            except TimeoutError:
                return False, "登录失败：无法重定向到仪表板"
    except Exception as e:
        return False, f"登录尝试失败：{str(e)}"

def login_webhost(email: str, password: str, max_retries: int = 5) -> str:
    """
    尝试使用重试机制登录WebHost账户
    
    参数:
        email: 用户邮箱
        password: 用户密码
        max_retries: 最大重试次数
    返回:
        str: 状态消息
    """
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()
        
        attempt = 1
        while attempt <= max_retries:
            try:
                success, message = attempt_login(page, email, password)
                if success:
                    return f"账户 {email} - {message}（第 {attempt}/{max_retries} 次尝试）"
                
                # 如果不成功且还有重试机会
                if attempt < max_retries:
                    print(f"账户 {email} 的第 {attempt}/{max_retries} 次重试：{message}")
                    time.sleep(2 * attempt)  # 指数退避
                else:
                    return f"账户 {email} - 所有 {max_retries} 次尝试均失败。最后错误：{message}"
                
            except Exception as e:
                if attempt == max_retries:
                    return f"账户 {email} - {max_retries} 次尝试后发生致命错误：{str(e)}"
            
            attempt += 1
        
        browser.close()

if __name__ == "__main__":
    # 从环境变量获取账户信息
    accounts = os.environ.get('WEBHOST', '').split()
    login_statuses = []
    
    # 处理每个账户
    for account in accounts:
        email, password = account.split(':')
        status = login_webhost(email, password)
        login_statuses.append(status)
        print(status)
    
    # 发送结果到Telegram
    if login_statuses:
        message = "WEBHOST 登录状态：\n\n" + "\n".join(login_statuses)
        result = send_telegram_message(message)
        print("消息已发送到Telegram：", result)
    else:
        error_message = "未配置任何账户"
        send_telegram_message(error_message)
        print(error_message)
