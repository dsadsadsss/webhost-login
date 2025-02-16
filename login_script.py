from playwright.sync_api import sync_playwright, TimeoutError
import os
import requests
import time
from typing import Tuple, Optional, Dict, List
from urllib.parse import urlparse
import concurrent.futures
import random

class Proxy:
    def __init__(self, url: str):
        self.url = url
        self.parsed = urlparse(url)
        self.username = None
        self.password = None
        
        # 解析认证信息
        if '@' in url:
            auth_part = url.split('@')[0].split('://')[1]
            self.username, self.password = auth_part.split(':')
            # 重构没有认证信息的URL
            self.clean_url = url.replace(f"{self.username}:{self.password}@", "")
        else:
            self.clean_url = url
            
    def to_playwright_format(self) -> Dict[str, str]:
        """转换为Playwright代理格式"""
        proxy_settings = {
            "server": self.clean_url
        }
        if self.username and self.password:
            proxy_settings.update({
                "username": self.username,
                "password": self.password
            })
        return proxy_settings
    
    def to_requests_format(self) -> Dict[str, str]:
        """转换为requests代理格式"""
        return {
            'http': self.url,
            'https': self.url
        }

def test_proxy(proxy: Proxy) -> Tuple[bool, float]:
    """
    测试代理的可用性和速度
    
    参数:
        proxy: Proxy对象
    返回:
        Tuple[bool, float]: (是否可用, 响应时间)
    """
    test_url = "https://api.telegram.org"
    try:
        start_time = time.time()
        response = requests.get(
            test_url, 
            proxies=proxy.to_requests_format(),
            timeout=10
        )
        response_time = time.time() - start_time
        
        if response.status_code == 200:
            return True, response_time
    except:
        pass
    return False, float('inf')

def get_working_proxies(proxy_list: List[Proxy], max_workers: int = 10) -> List[Proxy]:
    """
    并发测试代理列表，返回可用代理
    
    参数:
        proxy_list: 代理列表
        max_workers: 最大并发测试数
    返回:
        List[Proxy]: 可用代理列表
    """
    working_proxies = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_proxy = {
            executor.submit(test_proxy, proxy): proxy 
            for proxy in proxy_list
        }
        
        for future in concurrent.futures.as_completed(future_to_proxy):
            proxy = future_to_proxy[future]
            is_working, response_time = future.result()
            if is_working:
                print(f"代理可用: {proxy.clean_url} (响应时间: {response_time:.2f}s)")
                working_proxies.append(proxy)
            else:
                print(f"代理不可用: {proxy.clean_url}")
                
    return sorted(working_proxies, key=lambda p: test_proxy(p)[1])  # 按响应时间排序

def get_proxy_list() -> List[Proxy]:
    """
    从环境变量获取代理列表
    
    返回:
        List[Proxy]: 代理对象列表
    """
    proxy_urls = os.environ.get('PROXY_URLS', '').split(';')
    return [Proxy(url.strip()) for url in proxy_urls if url.strip()]

def send_telegram_message(message: str, working_proxies: List[Proxy]) -> dict:
    """
    使用可用代理发送Telegram消息
    
    参数:
        message: 要发送的消息
        working_proxies: 可用代理列表
    返回:
        dict: Telegram API响应
    """
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    proxy = random.choice(working_proxies) if working_proxies else None
    
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    response = requests.post(
        url, 
        json=payload,
        proxies=proxy.to_requests_format() if proxy else None
    )
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
        page.goto("https://webhostmost.com/login")
        
        # 填写登录表单
        page.get_by_placeholder("Enter email").click()
        page.get_by_placeholder("Enter email").fill(email)
        page.get_by_placeholder("Password").click()
        page.get_by_placeholder("Password").fill(password)
        
        # 提交登录表单
        page.get_by_role("button", name="Login").click()
        
        # 检查错误消息
        try:
            error_message = page.wait_for_selector('.MuiAlert-message', timeout=5000)
            if error_message:
                error_text = error_message.inner_text()
                return False, f"登录失败：{error_text}"
        except TimeoutError:
            # 检查是否成功重定向到仪表板
            try:
                page.wait_for_url("https://webhostmost.com/clientarea.php", timeout=5000)
                return True, "登录成功！"
            except TimeoutError:
                return False, "登录失败：无法重定向到仪表板"
    except Exception as e:
        return False, f"登录尝试失败：{str(e)}"

def login_webhost(email: str, password: str, working_proxies: List[Proxy], max_retries: int = 5) -> str:
    """
    使用可用代理尝试登录WebHost账户
    
    参数:
        email: 用户邮箱
        password: 用户密码
        working_proxies: 可用代理列表
        max_retries: 最大重试次数
    返回:
        str: 状态消息
    """
    with sync_playwright() as p:
        proxy = random.choice(working_proxies) if working_proxies else None
        
        browser = p.firefox.launch(
            headless=True,
            proxy=proxy.to_playwright_format() if proxy else None
        )
        
        page = browser.new_page()
        
        attempt = 1
        while attempt <= max_retries:
            try:
                success, message = attempt_login(page, email, password)
                if success:
                    return f"账户 {email} - {message}（第 {attempt}/{max_retries} 次尝试）[代理: {proxy.clean_url if proxy else 'direct'}]"
                
                if attempt < max_retries:
                    print(f"账户 {email} 的第 {attempt}/{max_retries} 次重试：{message}")
                    # 切换到其他代理
                    if proxy and len(working_proxies) > 1:
                        new_proxy = random.choice([p for p in working_proxies if p != proxy])
                        browser.close()
                        proxy = new_proxy
                        browser = p.firefox.launch(
                            headless=True,
                            proxy=proxy.to_playwright_format()
                        )
                        page = browser.new_page()
                    time.sleep(2 * attempt)
                else:
                    return f"账户 {email} - 所有 {max_retries} 次尝试均失败。最后错误：{message}"
                
            except Exception as e:
                if attempt == max_retries:
                    return f"账户 {email} - {max_retries} 次尝试后发生致命错误：{str(e)}"
            
            attempt += 1
        
        browser.close()

def parse_accounts(accounts_str: str) -> List[Tuple[str, str]]:
    """
    解析账户信息字符串
    
    参数:
        accounts_str: 格式为 "email1:pass1 email2:pass2" 的字符串
    返回:
        List[Tuple[str, str]]: 账户列表，每个元素为 (email, password)
    """
    accounts = []
    if not accounts_str:
        return accounts
        
    for account in accounts_str.strip().split():
        try:
            if ':' not in account:
                print(f"跳过格式错误的账户配置: {account}")
                continue
                
            email, password = account.split(':', 1)  # 只在第一个:处分割
            if not email or not password:
                print(f"跳过空邮箱或密码的账户配置: {account}")
                continue
                
            accounts.append((email.strip(), password.strip()))
        except Exception as e:
            print(f"解析账户配置时出错: {account}, 错误: {str(e)}")
            continue
            
    return accounts

if __name__ == "__main__":
    # 获取并测试代理
    proxy_list = get_proxy_list()
    if proxy_list:
        print(f"正在测试 {len(proxy_list)} 个代理...")
        working_proxies = get_working_proxies(proxy_list)
        print(f"找到 {len(working_proxies)} 个可用代理")
    else:
        working_proxies = []
        print("未配置代理，将使用直接连接")
    
    # 从环境变量获取并解析账户信息
    accounts_str = os.environ.get('WEBHOST', '')
    accounts = parse_accounts(accounts_str)
    
    if not accounts:
        error_message = "未配置有效账户"
        send_telegram_message(error_message, working_proxies)
        print(error_message)
        exit(1)
        
    login_statuses = []
    
    # 处理每个账户
    for email, password in accounts:
        try:
            status = login_webhost(email, password, working_proxies)
            login_statuses.append(status)
            print(status)
        except Exception as e:
            error_status = f"账户 {email} - 处理时发生错误: {str(e)}"
            login_statuses.append(error_status)
            print(error_status)
    
    # 发送结果到Telegram
    message = "WEBHOST 登录状态：\n\n" + "\n".join(login_statuses)
    result = send_telegram_message(message, working_proxies)
    print("消息已发送到Telegram：", result)
