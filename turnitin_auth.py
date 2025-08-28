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

# Webshare API configuration
WEBSHARE_API_TOKEN = os.getenv("WEBSHARE_API_TOKEN", "")

# Global browser session
browser_session = {
    'playwright': None,
    'browser': None,
    'context': None,
    'page': None,
    'logged_in': False,
    'last_activity': None,
    'current_proxy': None
}

# Rotating user agents for better success rate
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0'
]

def log(message: str):
    """Log a message with a timestamp to the terminal."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def random_wait(min_seconds=2, max_seconds=4):
    """Wait for a random amount of time to appear more human-like"""
    wait_time = random.uniform(min_seconds, max_seconds)
    time.sleep(wait_time)

def get_webshare_proxies():
    """Get a list of working proxies from Webshare API"""
    if not WEBSHARE_API_TOKEN:
        log("No Webshare API token configured, using direct connection")
        return []
    
    try:
        headers = {"Authorization": f"Token {WEBSHARE_API_TOKEN}"}
        
        response = requests.get(
            "https://proxy.webshare.io/api/v2/proxy/list/?mode=direct&page=1&page_size=20",
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            proxy_data = response.json()
            proxies = proxy_data.get('results', [])
            
            if proxies:
                # Filter for valid proxies, prioritize US proxies
                us_proxies = [p for p in proxies if p.get('valid') and p.get('country_code') == 'US']
                other_proxies = [p for p in proxies if p.get('valid') and p.get('country_code') != 'US']
                
                # Return US proxies first, then others
                valid_proxies = us_proxies + other_proxies
                log(f"Retrieved {len(valid_proxies)} valid proxies from Webshare ({len(us_proxies)} US, {len(other_proxies)} others)")
                return valid_proxies
            else:
                log("No proxies returned from Webshare API")
        else:
            log(f"Webshare API error: {response.status_code} - {response.text}")
    
    except Exception as e:
        log(f"Error fetching Webshare proxies: {e}")
    
    return []

def test_proxy_connection(proxy_info, session=None):
    """Test if a proxy is working properly with multiple test methods"""
    if session is None:
        session = requests.Session()
    
    proxy_config = {
        'http': f"http://{proxy_info['username']}:{proxy_info['password']}@{proxy_info['proxy_address']}:{proxy_info['port']}",
        'https': f"http://{proxy_info['username']}:{proxy_info['password']}@{proxy_info['proxy_address']}:{proxy_info['port']}"
    }
    
    # Test URLs in order of preference
    test_urls = [
        'http://icanhazip.com',
        'https://api.ipify.org',
        'http://checkip.amazonaws.com'
    ]
    
    for test_url in test_urls:
        try:
            response = session.get(
                test_url, 
                proxies=proxy_config, 
                timeout=15,
                headers={'User-Agent': random.choice(USER_AGENTS)}
            )
            
            if response.status_code == 200:
                ip_response = response.text.strip()
                if ip_response and len(ip_response) < 50:  # Basic IP validation
                    log(f"Proxy test successful via {test_url}: External IP = {ip_response}")
                    return True
        except Exception as e:
            log(f"Proxy test failed for {test_url}: {e}")
            continue
    
    return False

def get_working_proxy():
    """Get a working proxy with rotation and testing"""
    proxies = get_webshare_proxies()
    
    if not proxies:
        log("No proxies available, using direct connection")
        return None
    
    # Shuffle proxies for rotation
    random.shuffle(proxies)
    
    # Test up to 5 proxies to find a working one
    for i, proxy in enumerate(proxies[:5]):
        log(f"Testing proxy {i+1}/5: {proxy['proxy_address']}:{proxy['port']} ({proxy.get('country_code', 'Unknown')})")
        
        if test_proxy_connection(proxy):
            log(f"Selected working proxy: {proxy['proxy_address']}:{proxy['port']} ({proxy.get('country_code', 'Unknown')})")
            return proxy
        else:
            log(f"Proxy failed test: {proxy['proxy_address']}:{proxy['port']}")
    
    log("No working proxies found after testing 5 proxies, using direct connection")
    return None

def test_browser_proxy(page, proxy_info):
    """Test proxy functionality within the browser context"""
    test_urls = [
        'https://httpbin.org/ip',
        'https://api64.ipify.org?format=json',
        'https://icanhazip.com'
    ]
    
    for test_url in test_urls:
        try:
            log(f"Testing browser proxy with {test_url}")
            response = page.goto(test_url, timeout=20000, wait_until='networkidle')
            
            if response and response.ok:
                try:
                    content = page.content()
                    # Check if we got a reasonable response
                    if len(content) > 50 and len(content) < 5000:
                        log(f"Browser proxy test successful via {test_url}")
                        return True
                except Exception as content_error:
                    log(f"Could not read content from {test_url}: {content_error}")
                    
        except Exception as e:
            log(f"Browser proxy test failed for {test_url}: {e}")
            continue
    
    return False

def get_or_create_browser_session():
    """Get existing browser session or create new one with improved proxy handling"""
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
        
        # Get a working proxy with testing and rotation
        proxy_info = get_working_proxy()
        
        # Prepare browser launch options
        launch_options = {
            'headless': True,
            'args': [
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-extensions',
                '--no-first-run',
                '--disable-default-apps',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor'
            ]
        }
        
        # Add Webshare proxy configuration if available
        if proxy_info:
            proxy_config = {
                "server": f"http://{proxy_info['proxy_address']}:{proxy_info['port']}",
                "username": proxy_info['username'],
                "password": proxy_info['password']
            }
            launch_options['proxy'] = proxy_config
            browser_session['current_proxy'] = proxy_info
            log(f"Using tested proxy: {proxy_info['proxy_address']}:{proxy_info['port']}")
        else:
            log("No proxy configured, using direct connection")
        
        # Launch browser with proxy support
        browser_session['browser'] = browser_session['playwright'].chromium.launch(**launch_options)
        
        # Create context with enhanced anti-detection
        context_options = {
            'viewport': {'width': 1920, 'height': 1080},
            'user_agent': random.choice(USER_AGENTS),
            'extra_http_headers': {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-User': '?1',
                'Sec-Fetch-Dest': 'document',
                'Cache-Control': 'max-age=0'
            },
            'java_script_enabled': True,
            'accept_downloads': True,
            'ignore_https_errors': True
        }
        
        # Load cookies if available
        cookies_path = "cookies.json"
        if os.path.exists(cookies_path):
            try:
                context_options['storage_state'] = cookies_path
                log("Loading saved cookies")
            except:
                log("Could not load cookies, creating fresh session")
        
        browser_session['context'] = browser_session['browser'].new_context(**context_options)
        browser_session['page'] = browser_session['context'].new_page()
        
        # Test proxy connection in browser if configured
        if proxy_info:
            if test_browser_proxy(browser_session['page'], proxy_info):
                log("Browser proxy verification successful")
            else:
                log("Browser proxy verification failed, but continuing...")
        
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
        # Go to Turnitin login page with longer timeout
        log("Navigating to Turnitin login page...")
        page.goto("https://www.turnitin.com/login_page.asp?lang=en_us", timeout=90000)
        random_wait(3, 5)
        
        # Wait for page to fully load
        page.wait_for_load_state('networkidle', timeout=30000)
        
        # Check current URL and page title for debugging
        current_url = page.url
        page_title = page.title()
        log(f"Login page loaded - URL: {current_url}, Title: {page_title}")
        
        # Check if we're already logged in
        try:
            page.wait_for_selector('a.sn_quick_submit', timeout=10000)
            log("Already logged in - Quick Submit found")
            save_cookies()
            return True
        except:
            log("Need to perform login")
            
        # Check if we got blocked (403 error page)
        if "403" in page_title or "blocked" in page.content().lower():
            log("Detected blocking page - may need different proxy")
            return False
            
        # Try multiple email selectors with increased timeout
        email_selectors = [
            'input[name="email"]',
            'input[type="email"]',
            'input[id="email"]',
            '#email',
            '[placeholder*="email" i]'
        ]
        
        email_filled = False
        for selector in email_selectors:
            try:
                log(f"Trying email selector: {selector}")
                page.wait_for_selector(selector, timeout=20000)
                page.fill(selector, TURNITIN_EMAIL)
                log(f"Email filled successfully with selector: {selector}")
                email_filled = True
                break
            except Exception as selector_error:
                log(f"Email selector {selector} failed: {selector_error}")
                continue
        
        if not email_filled:
            log("Could not find email field with any selector")
            # Take screenshot for debugging
            try:
                page.screenshot(path="debug_login_no_email.png")
                log("Debug screenshot saved: debug_login_no_email.png")
            except:
                pass
            return False
        
        random_wait(2, 3)
        
        # Fill password with multiple selectors
        password_selectors = [
            'input[type="password"]',
            'input[name="password"]',
            '#password',
            '[placeholder*="password" i]'
        ]
        
        password_filled = False
        for selector in password_selectors:
            try:
                log(f"Trying password selector: {selector}")
                page.fill(selector, TURNITIN_PASSWORD)
                log(f"Password filled successfully with selector: {selector}")
                password_filled = True
                break
            except Exception as selector_error:
                log(f"Password selector {selector} failed: {selector_error}")
                continue
        
        if not password_filled:
            log("Could not find password field")
            return False
        
        random_wait(2, 3)
        
        # Click login button with multiple selectors
        login_selectors = [
            'input[type="submit"]',
            'button[type="submit"]',
            'button:has-text("Log in")',
            'input[value*="Log" i]'
        ]
        
        login_clicked = False
        for selector in login_selectors:
            try:
                log(f"Trying login button selector: {selector}")
                page.click(selector)
                log(f"Login button clicked successfully with selector: {selector}")
                login_clicked = True
                break
            except Exception as selector_error:
                log(f"Login selector {selector} failed: {selector_error}")
                continue
        
        if not login_clicked:
            log("Could not find or click login button")
            return False
        
        # Wait for login to complete with longer timeout
        log("Waiting for login to complete...")
        page.wait_for_timeout(15000)
        
        # Verify login success
        try:
            page.wait_for_selector('a.sn_quick_submit', timeout=30000)
            log("Login successful - Quick Submit found")
            save_cookies()
            return True
        except:
            log("Login verification failed - Quick Submit not found")
            # Check if we're on an error page
            current_url = page.url
            if "error" in current_url.lower() or "login" in current_url.lower():
                log("Still on login/error page after login attempt")
            return False
            
    except Exception as e:
        log(f"Login process failed: {e}")
        return False

def navigate_to_quick_submit():
    """Navigate to Quick Submit page using persistent session"""
    page = browser_session['page']
    
    try:
        # Use only the working selector from logs
        page.wait_for_selector('a.sn_quick_submit', timeout=20000)
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
        'last_activity': None,
        'current_proxy': None
    }

def get_session_page():
    """Get the current session page, creating if necessary"""
    return get_or_create_browser_session()