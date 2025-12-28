import os
import time
import random
import json
import requests
import threading
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# Global browser session lock for thread safety
browser_lock = threading.Lock()

# Load environment variables
load_dotenv()
TURNITIN_EMAIL = os.getenv("TURNITIN_EMAIL")
TURNITIN_PASSWORD = os.getenv("TURNITIN_PASSWORD")

# Removed proxy configuration - direct connection for better stealth

# Global browser session
browser_session = {
    'playwright': None,
    'browser': None,
    'context': None,
    'page': None,
    'logged_in': False,
    'last_activity': None,
    'stealth_enabled': True,
    'thread_id': None  # Track which thread owns this session
}

# Enhanced user agents with latest versions and realistic variations
USER_AGENTS = [
    # Chrome on Windows (most common)
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',

    # Chrome on macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',

    # Edge on Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0',

    # Firefox on Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',

    # Safari on macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15'
]

# Realistic screen resolutions
SCREEN_RESOLUTIONS = [
    {'width': 1920, 'height': 1080},  # Full HD (most common)
    {'width': 1366, 'height': 768},   # Laptop standard
    {'width': 1536, 'height': 864},   # Laptop scaled
    {'width': 1440, 'height': 900},   # MacBook
    {'width': 2560, 'height': 1440},  # QHD
    {'width': 1600, 'height': 900},   # Wide laptop
]

def log(message: str):
    """Log a message with a timestamp to the terminal."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def is_session_logged_in(page):
    """Check if the current session is still logged in"""
    try:
        current_url = page.url

        # If we're on a login page, we're not logged in
        if "login" in current_url.lower():
            return False

        # Check for common logged-in indicators
        login_indicators = [
            'table',  # Common element on Turnitin dashboard
            '.class_name',  # Class listing elements
            'td.class_name',  # Class name table cells
            '[class*="instructor"]',  # Instructor dashboard elements
            '.dashboard'  # Dashboard elements
        ]

        for indicator in login_indicators:
            try:
                page.wait_for_selector(indicator, timeout=3000)
                return True
            except:
                continue

        # If no indicators found, we might be logged out
        return False

    except Exception:
        return False

def random_wait(min_seconds=2, max_seconds=4):
    """Human-like wait with realistic patterns"""
    # Add slight variation to make it more human
    base_wait = random.uniform(min_seconds, max_seconds)

    # Occasionally add longer pauses (like a human would)
    if random.random() < 0.1:  # 10% chance
        base_wait += random.uniform(1, 3)

    # Sometimes add micro-pauses (typing/thinking patterns)
    if random.random() < 0.3:  # 30% chance
        micro_pause = random.uniform(0.1, 0.5)
        time.sleep(micro_pause)
        base_wait -= micro_pause

    time.sleep(max(0.1, base_wait))

def human_like_typing(page, selector, text, delay_range=(0.05, 0.2)):
    """Type text with human-like delays between characters"""
    element = page.locator(selector)
    element.click()  # Focus first
    element.fill("")  # Clear existing

    for char in text:
        element.type(char)
        if random.random() < 0.8:  # 80% chance of delay
            time.sleep(random.uniform(*delay_range))

def human_mouse_movement(page):
    """Simulate human-like mouse movements"""
    try:
        # Random mouse movements to appear more human
        width = page.viewport_size['width']
        height = page.viewport_size['height']

        # Move mouse to random positions
        for _ in range(random.randint(1, 3)):
            x = random.randint(100, width - 100)
            y = random.randint(100, height - 100)
            page.mouse.move(x, y)
            time.sleep(random.uniform(0.1, 0.3))
    except Exception:
        pass

def generate_realistic_headers(user_agent):
    """Generate realistic browser headers to match the user agent"""
    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': random.choice([
            'en-US,en;q=0.9',
            'en-US,en;q=0.8,es;q=0.7',
            'en-GB,en;q=0.9',
            'en-US,en;q=0.9,fr;q=0.8'
        ]),
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-User': '?1',
        'Sec-Fetch-Dest': 'document',
        'Cache-Control': 'max-age=0'
    }

    # Add browser-specific headers
    if 'Chrome' in user_agent and 'Edg' not in user_agent:
        headers.update({
            'sec-ch-ua': '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"' if 'Windows' in user_agent else '"macOS"'
        })
    elif 'Edg' in user_agent:
        headers.update({
            'sec-ch-ua': '"Not A(Brand";v="99", "Microsoft Edge";v="121", "Chromium";v="121"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"'
        })
    elif 'Firefox' in user_agent:
        headers.update({
            'DNT': '1',
            'Sec-GPC': '1'
        })

    return headers

def add_browser_stealth_features(page):
    """Add advanced stealth features to avoid detection"""
    try:
        # Override navigator properties to appear more human
        stealth_script = """
        // Override WebDriver property
        Object.defineProperty(navigator, 'webdriver', {
            get: () => false,
        });

        // Override plugins to appear more realistic
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                {
                    name: 'Chrome PDF Plugin',
                    description: 'Portable Document Format',
                    filename: 'internal-pdf-viewer'
                },
                {
                    name: 'Chrome PDF Viewer',
                    description: '',
                    filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'
                }
            ],
        });

        // Override languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
        });

        // Override permissions
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );

        // Remove automation indicators
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;

        // Override Chrome runtime
        if (window.chrome) {
            window.chrome.runtime = {
                onConnect: undefined,
                onMessage: undefined,
                sendMessage: undefined,
            };
        }
        """

        page.add_init_script(stealth_script)
        log("Added stealth features to browser")

    except Exception as e:
        log(f"Error adding stealth features: {e}")

def simulate_human_activity(page):
    """Simulate human browsing behavior"""
    try:
        # Random scroll behavior
        if random.random() < 0.7:  # 70% chance
            scroll_distance = random.randint(100, 500)
            page.mouse.wheel(0, scroll_distance)
            time.sleep(random.uniform(0.5, 1.5))

        # Random mouse movements
        human_mouse_movement(page)

        # Occasionally hover over elements
        if random.random() < 0.3:  # 30% chance
            try:
                visible_elements = page.locator('button, a, input').all()
                if visible_elements:
                    random_element = random.choice(visible_elements)
                    random_element.hover()
                    time.sleep(random.uniform(0.2, 0.8))
            except Exception:
                pass

    except Exception as e:
        log(f"Error simulating human activity: {e}")

# Removed proxy testing - using direct connection for better stealth

def get_or_create_browser_session():
    """Get existing browser session or create new one with thread safety"""
    global browser_session
    current_thread_id = threading.get_ident()

    with browser_lock:  # Thread-safe access to browser session
        # Check if session exists and belongs to current thread
        if (browser_session['browser'] and
            browser_session['context'] and
            browser_session['page'] and
            browser_session['logged_in'] and
            browser_session['thread_id'] == current_thread_id):

            try:
                # Test if session is still alive and logged in
                current_url = browser_session['page'].url

                # Check if we're still logged in (not redirected to login page)
                if is_session_logged_in(browser_session['page']):
                    # Check if session needs refresh (every 10 uses or 2 hours)
                    session_age_hours = 0
                    if browser_session.get('last_restart'):
                        session_start = datetime.fromisoformat(browser_session['last_restart'])
                        session_age_hours = (datetime.now() - session_start).total_seconds() / 3600

                    session_count = browser_session.get('session_count', 0)

                    if session_count >= 10 or session_age_hours >= 2:
                        log(f"Session refresh needed (uses: {session_count}, age: {session_age_hours:.1f}h)")
                        log("Refreshing browser session to clear cache...")
                        cleanup_browser_session()
                        # Will create new session below
                    else:
                        browser_session['last_activity'] = datetime.now()
                        log(f"Reusing existing browser session - Current URL: {current_url}")
                        return browser_session['page']
                else:
                    log("Session expired or logged out, need to re-login")
                    # Don't cleanup, just re-login with existing session
                    if check_and_perform_login():
                        browser_session['logged_in'] = True
                        browser_session['last_activity'] = datetime.now()
                        log("Successfully re-logged in with existing session")
                        return browser_session['page']
                    else:
                        log("Re-login failed, creating new session")
                        cleanup_browser_session()
            except Exception as e:
                error_msg = str(e)
                # Check if this is a thread switching error
                if "thread" in error_msg.lower() or "greenlet" in error_msg.lower():
                    log(f"Thread switching detected: {e}")
                    log("Forcing complete session reset without cleanup (cross-thread operation not allowed)")
                    # Force reset without trying to close (which would fail cross-thread)
                    force_reset_browser_session()
                else:
                    log(f"Existing session invalid: {e}, creating new session")
                    cleanup_browser_session()

        # CRITICAL: If session belongs to a different thread, check if it's still active
        # Don't immediately reset - try to preserve the session
        elif browser_session['thread_id'] and browser_session['thread_id'] != current_thread_id:
            log(f"⚠️ Browser session is owned by thread {browser_session['thread_id']}, current thread is {current_thread_id}")
            
            # Check if the session is still active and recent
            if browser_session.get('last_activity'):
                last_activity = browser_session['last_activity']
                if isinstance(last_activity, datetime):
                    time_since_activity = (datetime.now() - last_activity).total_seconds()
                else:
                    time_since_activity = 999  # Force reset if can't determine
                
                # If session was used recently (within 30 seconds), it's likely still in use
                if time_since_activity < 30:
                    log(f"Session was active {time_since_activity:.1f}s ago - likely still in use by other thread")
                    log("⚠️ PREVENTING THREAD SWITCH: Keeping existing session intact")
                    log("Raising error to prevent thread switching - session will remain logged in")
                    
                    # Raise error to prevent thread switch - keeps session alive
                    raise Exception(f"Browser session is currently owned by another thread (active {time_since_activity:.1f}s ago). Retry will use same session.")
                else:
                    log(f"Session was last active {time_since_activity:.1f}s ago - appears abandoned")
                    log("Forcing session reset as fallback (session appears abandoned)")
                    force_reset_browser_session()
            else:
                log("No last activity timestamp - forcing reset as fallback")
                force_reset_browser_session()
    
        # Create new session (still within browser_lock)
        log("Creating enhanced stealth browser session...")

        try:
            # Start Playwright
            browser_session['playwright'] = sync_playwright().start()

            # Enhanced browser launch options for maximum stealth
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
                    '--disable-features=VizDisplayCompositor',

                    # Additional stealth arguments
                    '--disable-blink-features=AutomationControlled',
                    '--disable-plugins-discovery',
                    '--disable-component-extensions-with-background-pages',
                    '--disable-background-timer-throttling',
                    '--disable-renderer-backgrounding',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-features=TranslateUI',
                    '--no-default-browser-check',
                    '--no-service-autorun',
                    '--password-store=basic',
                    '--use-mock-keychain',
                    '--disable-sync',
                    '--metrics-recording-only',
                    '--disable-default-apps',
                    '--mute-audio',
                    '--disable-background-networking',
                    '--disable-notifications',
                    '--disable-permissions-api'
                ]
            }

            log("Using direct connection for maximum stealth (no proxy)")

            # Launch browser with stealth configuration
            browser_session['browser'] = browser_session['playwright'].chromium.launch(**launch_options)

            # Create context with maximum stealth anti-detection
            selected_user_agent = random.choice(USER_AGENTS)
            selected_resolution = random.choice(SCREEN_RESOLUTIONS)

            context_options = {
                'viewport': selected_resolution,
                'user_agent': selected_user_agent,
                'extra_http_headers': generate_realistic_headers(selected_user_agent),
                'java_script_enabled': True,
                'accept_downloads': True,
                'ignore_https_errors': True,

                # Enhanced privacy and stealth settings
                'permissions': ['geolocation', 'notifications'],
                'geolocation': {'latitude': 40.7128, 'longitude': -74.0060},  # New York
                'locale': 'en-US',
                'timezone_id': 'America/New_York',
                'color_scheme': 'light',
                'reduced_motion': 'no-preference',
                'forced_colors': 'none',

                # Device scale factor for more realistic fingerprint
                'device_scale_factor': random.choice([1, 1.25, 1.5, 2])
            }

            log(f"Browser configured with User-Agent: {selected_user_agent[:50]}...")
            log(f"Viewport: {selected_resolution['width']}x{selected_resolution['height']}")
            log(f"Scale factor: {context_options['device_scale_factor']}")

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

            # Apply advanced stealth features
            add_browser_stealth_features(browser_session['page'])

            # Simulate some initial human-like behavior
            log("Simulating initial human browsing behavior...")
            time.sleep(random.uniform(1, 3))  # Initial pause like a human opening browser

            # Check if we need to login
            if check_and_perform_login():
                browser_session['logged_in'] = True
                browser_session['last_activity'] = datetime.now()
                browser_session['thread_id'] = threading.get_ident()  # Track thread ownership
                browser_session['session_count'] = browser_session.get('session_count', 0) + 1
                browser_session['last_restart'] = datetime.now().isoformat()
                log("Stealth browser session created and logged in successfully")
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
        # Go to Turnitin login page with human-like behavior
        log("Navigating to Turnitin login page with human-like behavior...")
        page.goto("https://www.turnitin.com/login_page.asp?lang=en_us", timeout=90000)

        # Simulate human browsing behavior
        simulate_human_activity(page)
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

        # Validate credentials are available
        if not TURNITIN_EMAIL or not TURNITIN_PASSWORD:
            log("ERROR: Turnitin credentials not found in environment variables")
            log("Please set TURNITIN_EMAIL and TURNITIN_PASSWORD in your .env file")
            return False

        log(f"Using email: {TURNITIN_EMAIL[:3]}***{TURNITIN_EMAIL[-3:] if len(TURNITIN_EMAIL) > 6 else '***'}")

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

                # Use human-like typing instead of instant fill
                human_like_typing(page, selector, TURNITIN_EMAIL)
                log(f"Email typed like human with selector: {selector}")

                # Human-like pause before moving to password
                random_wait(1, 2)

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

                # Use human-like typing for password too
                human_like_typing(page, selector, TURNITIN_PASSWORD, delay_range=(0.03, 0.1))
                log(f"Password typed like human with selector: {selector}")

                # Brief pause like a human would do before clicking login
                random_wait(0.5, 1.5)

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
        
        # Verify login success by checking for class table or instructor dashboard
        try:
            # Look for multiple indicators of successful login
            login_indicators = [
                'table',  # Class table on homepage
                'a.sn_quick_submit',  # Legacy Quick Submit (if present)
                '.class_name',  # Class name elements
                'td.class_name',  # Class name table cells
                '[class*="instructor"]',  # Instructor dashboard elements
                '.dashboard'  # Dashboard elements
            ]

            for indicator in login_indicators:
                try:
                    page.wait_for_selector(indicator, timeout=10000)
                    log(f"Login successful - Found indicator: {indicator}")
                    save_cookies()
                    return True
                except:
                    continue

            # If no indicators found, check URL to confirm we're not on login page
            current_url = page.url
            if "login" not in current_url.lower() and "error" not in current_url.lower():
                log(f"Login successful - Redirected from login page to: {current_url}")
                save_cookies()
                return True

            log("Login verification failed - No success indicators found")
            log(f"Current URL: {current_url}")
            return False

        except Exception as verify_error:
            log(f"Login verification error: {verify_error}")
            current_url = page.url
            if "error" in current_url.lower() or "login" in current_url.lower():
                log("Still on login/error page after login attempt")
            return False
            
    except Exception as e:
        log(f"Login process failed: {e}")
        return False

def navigate_to_class_homepage():
    """Navigate to Business Administration class instead of Quick Submit"""
    from turnitin_helpers import navigate_to_class

    try:
        log("Navigating to Business Administration class...")
        navigate_to_class("Business Administration")
        log("Successfully navigated to class homepage")
        return browser_session['page']
    except Exception as e:
        log(f"Error navigating to class: {e}")
        raise

def save_cookies():
    """Save cookies for future sessions"""
    try:
        if browser_session['context']:
            browser_session['context'].storage_state(path="cookies.json")
            log("Cookies saved successfully")
    except Exception as e:
        log(f"Error saving cookies: {e}")

def force_reset_browser_session():
    """Force reset browser session without cleanup (for thread switching scenarios)"""
    global browser_session
    
    log("Forcing browser session reset (no cleanup - avoiding cross-thread operations)")
    
    # Don't try to close anything - just reset the dict
    # Python's garbage collector will handle the old Playwright objects
    browser_session = {
        'playwright': None,
        'browser': None,
        'context': None,
        'page': None,
        'logged_in': False,
        'last_activity': None,
        'stealth_enabled': True,
        'thread_id': None,
        'session_count': 0,
        'last_restart': None
    }
    
    log("Browser session forcefully reset - ready for new session creation")

def cleanup_browser_session(force_close=False):
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
        'stealth_enabled': True,
        'thread_id': None,
        'session_count': 0,  # Track how many times this session has been used
        'last_restart': None
    }

    if force_close:
        log("Browser session forcefully closed and reset")

def get_session_page():
    """Get the current session page, creating if necessary"""
    return get_or_create_browser_session()

