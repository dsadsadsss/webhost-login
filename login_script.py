from playwright.sync_api import sync_playwright, TimeoutError
import os
import requests
import time
from typing import Tuple

def send_telegram_message(message: str) -> dict:
    """
    Send a message to Telegram using bot API
    
    Args:
        message: The message to send
    Returns:
        dict: Telegram API response
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
    Single attempt to login to WebHost account
    
    Args:
        page: Playwright page object
        email: User email
        password: User password
    Returns:
        Tuple[bool, str]: (success status, message)
    """
    try:
        # Navigate to login page
        page.goto("https://webhostmost.com/login")
        
        # Fill login form
        page.get_by_placeholder("Enter email").click()
        page.get_by_placeholder("Enter email").fill(email)
        page.get_by_placeholder("Password").click()
        page.get_by_placeholder("Password").fill(password)
        
        # Submit login form
        page.get_by_role("button", name="Login").click()
        
        # Check for error message
        try:
            error_message = page.wait_for_selector('.MuiAlert-message', timeout=5000)
            if error_message:
                error_text = error_message.inner_text()
                return False, f"Login failed: {error_text}"
        except TimeoutError:
            # Check for successful redirect to dashboard
            try:
                page.wait_for_url("https://webhostmost.com/clientarea.php", timeout=5000)
                return True, "Login successful!"
            except TimeoutError:
                return False, "Login failed: Could not redirect to dashboard"
    except Exception as e:
        return False, f"Login attempt failed: {str(e)}"

def login_webhost(email: str, password: str, max_retries: int = 5) -> str:
    """
    Attempt to login to WebHost account with retry mechanism
    
    Args:
        email: User email
        password: User password
        max_retries: Maximum number of retry attempts
    Returns:
        str: Status message
    """
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()
        
        attempt = 1
        while attempt <= max_retries:
            try:
                success, message = attempt_login(page, email, password)
                if success:
                    return f"Account {email} - {message} (attempt {attempt}/{max_retries})"
                
                # If not successful and we have more retries
                if attempt < max_retries:
                    print(f"Retry {attempt}/{max_retries} for {email}: {message}")
                    time.sleep(2 * attempt)  # Exponential backoff
                else:
                    return f"Account {email} - All {max_retries} attempts failed. Last error: {message}"
                
            except Exception as e:
                if attempt == max_retries:
                    return f"Account {email} - Fatal error after {max_retries} attempts: {str(e)}"
            
            attempt += 1
        
        browser.close()

if __name__ == "__main__":
    # Get accounts from environment variable
    accounts = os.environ.get('WEBHOST', '').split()
    login_statuses = []
    
    # Process each account
    for account in accounts:
        email, password = account.split(':')
        status = login_webhost(email, password)
        login_statuses.append(status)
        print(status)
    
    # Send results to Telegram
    if login_statuses:
        message = "WEBHOST Login Status:\n\n" + "\n".join(login_statuses)
        result = send_telegram_message(message)
        print("Message sent to Telegram:", result)
    else:
        error_message = "No accounts configured"
        send_telegram_message(error_message)
        print(error_message)
