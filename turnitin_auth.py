import os
import time
import random
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# Load environment variables
load_dotenv()
TURNITIN_EMAIL = os.getenv("TURNITIN_EMAIL")
TURNITIN_PASSWORD = os.getenv("TURNITIN_PASSWORD")

# Global browser session
browser_session = {
    'playwright': None,
    'browser': None,
    'context': None,
    'page': None,
    'logged_in': False,
    'last_activity': None
}

def log(message: str):
    """Log a message with a timestamp to the terminal."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def random_wait(min_seconds=2, max_seconds=4):
    """Wait for a random amount of time to appear more human-like"""
    wait_time = random.uniform(min_seconds, max_seconds)
    time.sleep(wait_time)

def get_or_create_browser_session():
    """Get existing browser session or create new one"""
    global browser_session
    
    # Check if session exists and is valid
    if (browser_session['browser'] and 
        browser_session['context'] and 
        browser_session['page'] and
        browser_session['logged_in']):
        
        try:
            # Test if session is still alive
            current_url = browser_session['page'].url
            browser_session['last_activity'] = datetime.now()
            log(f"Reusing existing browser session - Current URL: {current_url}")
            return browser_session['page']
        except Exception as e:
            log(f"Existing session invalid: {e}, creating new session")
            cleanup_browser_session()
    
    # Create new session
    log("Creating new browser session...")
    
    try:
        # Start Playwright
        browser_session['playwright'] = sync_playwright().start()
        
        # Launch browser with minimal args (only what works)
        browser_session['browser'] = browser_session['playwright'].chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        
        # Create context with cookies if available
        context_options = {
            'viewport': {'width': 1920, 'height': 1080},
            'user_agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        cookies_path = "cookies.json"
        if os.path.exists(cookies_path):
            try:
                context_options['storage_state'] = cookies_path
                log("Loading saved cookies")
            except:
                log("Could not load cookies, creating fresh session")
        
        browser_session['context'] = browser_session['browser'].new_context(**context_options)
        browser_session['page'] = browser_session['context'].new_page()
        
        # Check if we need to login
        if check_and_perform_login():
            browser_session['logged_in'] = True
            browser_session['last_activity'] = datetime.now()
            log("Browser session created and logged in successfully")
            return browser_session['page']
        else:
            raise Exception("Login failed")
            
    except Exception as e:
        log(f"Error creating browser session: {e}")
        cleanup_browser_session()
        raise

def check_and_perform_login():
    """Check if login is needed and perform if necessary"""
    page = browser_session['page']
    
    try:
        # Go to Turnitin login page
        page.goto("https://www.turnitin.com/login_page.asp?lang=en_us", timeout=60000)
        random_wait(2, 3)
        
        # Check if we're already logged in by looking for Quick Submit
        try:
            page.wait_for_selector('a.sn_quick_submit', timeout=5000)
            log("Already logged in - Quick Submit found")
            save_cookies()
            return True
        except:
            log("Need to perform login")
            
        # Fill email (use only working selector)
        page.wait_for_selector('input[name="email"]', timeout=15000)
        page.fill('input[name="email"]', TURNITIN_EMAIL)
        random_wait(1, 2)
        
        # Fill password (use only working selector)
        page.fill('input[type="password"]', TURNITIN_PASSWORD)
        random_wait(1, 2)
        
        # Click login button (use only working selector)
        page.click('input[type="submit"]')
        log("Login button clicked")
        
        # Wait for login to complete
        page.wait_for_timeout(10000)
        
        # Verify login success
        try:
            page.wait_for_selector('a.sn_quick_submit', timeout=20000)
            log("Login successful - Quick Submit found")
            save_cookies()
            return True
        except:
            log("Login verification failed")
            return False
            
    except Exception as e:
        log(f"Login process failed: {e}")
        return False

def navigate_to_quick_submit():
    """Navigate to Quick Submit page using persistent session"""
    page = browser_session['page']
    
    try:
        # Use only the working selector from logs
        page.wait_for_selector('a.sn_quick_submit', timeout=15000)
        page.click('a.sn_quick_submit')
        log("Successfully navigated to Quick Submit")
        random_wait(2, 3)
        return page
    except Exception as e:
        log(f"Error navigating to Quick Submit: {e}")
        raise

def save_cookies():
    """Save cookies for future sessions"""
    try:
        if browser_session['context']:
            browser_session['context'].storage_state(path="cookies.json")
            log("Cookies saved successfully")
    except Exception as e:
        log(f"Error saving cookies: {e}")

def cleanup_browser_session():
    """Clean up browser session"""
    global browser_session
    
    try:
        if browser_session['page']:
            browser_session['page'].close()
        if browser_session['context']:
            browser_session['context'].close()
        if browser_session['browser']:
            browser_session['browser'].close()
        if browser_session['playwright']:
            browser_session['playwright'].stop()
    except Exception as e:
        log(f"Error during cleanup: {e}")
    
    # Reset session
    browser_session = {
        'playwright': None,
        'browser': None,
        'context': None,
        'page': None,
        'logged_in': False,
        'last_activity': None
    }

def get_session_page():
    """Get the current session page, creating if necessary"""
    return get_or_create_browser_session()

def navigate_to_quick_submit():
    """Navigate to Quick Submit page using persistent session"""
    page = browser_session['page']
    
    try:
        # Use only the working selector from logs
        page.wait_for_selector('a.sn_quick_submit', timeout=15000)
        page.click('a.sn_quick_submit')
        log("Successfully navigated to Quick Submit")
        random_wait(2, 3)
        return page
    except Exception as e:
        log(f"Error navigating to Quick Submit: {e}")
        raise