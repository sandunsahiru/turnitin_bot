import os
import time
import random
import json
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# Load environment variables
load_dotenv()
TURNITIN_EMAIL = os.getenv("TURNITIN_EMAIL")
TURNITIN_PASSWORD = os.getenv("TURNITIN_PASSWORD")

def log(message: str):
    """Log a message with a timestamp to the terminal."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def random_wait(min_seconds=2, max_seconds=5):
    """Wait for a random amount of time to appear more human-like"""
    wait_time = random.uniform(min_seconds, max_seconds)
    time.sleep(wait_time)

def create_browser():
    """Create and return a browser instance - Fixed for stability"""
    p = sync_playwright().start()
    browser = None
    
    for attempt in range(3):
        try:
            log(f"Browser launch attempt {attempt + 1}/3...")
            
            if attempt == 0:
                # First attempt: Conservative headless mode for stability
                browser = p.chromium.launch(
                    headless=True,
                    slow_mo=100,  # Add small delay between actions
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--disable-features=VizDisplayCompositor',
                        '--disable-extensions',
                        '--disable-plugins',
                        '--disable-background-timer-throttling',
                        '--disable-backgrounding-occluded-windows',
                        '--disable-renderer-backgrounding',
                        '--disable-field-trial-config',
                        '--disable-back-forward-cache',
                        '--disable-ipc-flooding-protection',
                        '--memory-pressure-off',
                        '--max_old_space_size=4096',
                        '--no-first-run',
                        '--no-default-browser-check',
                        '--disable-default-apps',
                        '--disable-popup-blocking',
                        '--disable-translate',
                        '--disable-background-networking',
                        '--disable-sync',
                        '--metrics-recording-only',
                        '--no-report-upload',
                        '--disable-blink-features=AutomationControlled',  # Hide automation
                        '--disable-web-security',
                        '--allow-running-insecure-content',
                        '--ignore-certificate-errors',
                        '--ignore-ssl-errors',
                        '--ignore-certificate-errors-spki-list'
                    ]
                )
            elif attempt == 1:
                # Second attempt: Minimal arguments
                browser = p.chromium.launch(
                    headless=True,
                    slow_mo=200,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--single-process'
                    ]
                )
            else:
                # Third attempt: Try with visible mode for debugging
                log("Trying visible mode for debugging...")
                browser = p.chromium.launch(
                    headless=False,  # Visible for debugging
                    slow_mo=500,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage'
                    ]
                )
            
            log(f"Browser launched successfully on attempt {attempt + 1}")
            
            # Test if browser is actually working
            try:
                version = browser.version
                log(f"Browser version: {version}")
                
                # Additional stability test
                test_context = browser.new_context()
                test_page = test_context.new_page()
                test_page.goto("about:blank", timeout=10000)
                test_page.close()
                test_context.close()
                log("Browser stability test passed")
                
                return p, browser
            except Exception as version_error:
                log(f"Browser stability test failed: {version_error}")
                if browser:
                    browser.close()
                browser = None
                continue
                
        except Exception as browser_error:
            log(f"Browser launch attempt {attempt + 1} failed: {browser_error}")
            if browser:
                try:
                    browser.close()
                except:
                    pass
            browser = None
            if attempt == 2:  # Last attempt
                raise Exception(f"All browser launch attempts failed: {browser_error}")
            continue
    
    if not browser:
        raise Exception("Could not launch any browser")

def create_browser_context(browser):
    """Create browser context with enhanced stability"""
    cookies_path = "cookies.json"
    context = None
    
    try:
        log("Creating browser context...")
        
        # Test browser before creating context
        try:
            contexts = browser.contexts
            log(f"Browser has {len(contexts)} existing contexts")
        except Exception as browser_test_error:
            log(f"Browser context test failed: {browser_test_error}")
            raise Exception(f"Browser is not accessible: {browser_test_error}")
        
        # Enhanced context options for stability
        context_options = {
            'viewport': {'width': 1920, 'height': 1080},
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'java_script_enabled': True,
            'accept_downloads': True,
            'bypass_csp': True,
            'ignore_https_errors': True,
            'extra_http_headers': {
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-User': '?1',
                'Sec-Fetch-Dest': 'document'
            }
        }
        
        if os.path.exists(cookies_path):
            log("Found saved cookies. Attempting to load them...")
            try:
                with open(cookies_path, 'r') as f:
                    cookies_content = f.read().strip()
                
                if cookies_content and cookies_content != "":
                    json.loads(cookies_content)  # Validate JSON
                    try:
                        context_options['storage_state'] = cookies_path
                        context = browser.new_context(**context_options)
                        log("Successfully loaded saved cookies.")
                    except Exception as cookie_context_error:
                        log(f"Error creating context with cookies: {cookie_context_error}")
                        log("Creating context without cookies...")
                        del context_options['storage_state']
                        context = browser.new_context(**context_options)
                else:
                    log("Cookies file is empty. Creating new session.")
                    context = browser.new_context(**context_options)
            except Exception as cookie_error:
                log(f"Cookie loading error: {cookie_error}")
                context = browser.new_context(**context_options)
        else:
            log("No saved cookies found. Creating a new session.")
            context = browser.new_context(**context_options)
        
        # Test the context immediately
        try:
            test_page = context.new_page()
            test_page.goto("about:blank", timeout=10000)
            test_page.close()
            log("Context stability test passed")
        except Exception as context_test_error:
            log(f"Context stability test failed: {context_test_error}")
            raise Exception(f"Context is not stable: {context_test_error}")
            
        log("Browser context created successfully")
        return context
        
    except Exception as e:
        log(f"Error creating context: {e}. Creating fresh context...")
        if context:
            try:
                context.close()
            except:
                pass
        
        try:
            # Create minimal fresh context
            minimal_options = {
                'viewport': {'width': 1920, 'height': 1080},
                'java_script_enabled': True,
                'ignore_https_errors': True
            }
            context = browser.new_context(**minimal_options)
            log("Fresh minimal context created after error")
            return context
        except Exception as fresh_context_error:
            log(f"Cannot create fresh context: {fresh_context_error}")
            raise Exception(f"Browser context creation failed: {fresh_context_error}")

def create_page(context):
    """Create and test a new page with enhanced error handling"""
    page = None
    try:
        log("Attempting to create new page...")
        page = context.new_page()
        log("Created new page for Turnitin process")
        
        # Set additional headers and configurations
        try:
            page.set_extra_http_headers({
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            })
            
            # Test the page immediately
            log("Testing page immediately after creation...")
            page_url = page.url
            log(f"Page created with URL: {page_url}")
            
        except Exception as immediate_test_error:
            log(f"Immediate page test failed: {immediate_test_error}")
            raise Exception(f"Page immediate test failed: {immediate_test_error}")
                
    except Exception as page_error:
        log(f"Page creation failed: {page_error}")
        raise Exception(f"Could not create page: {page_error}")
    
    # Verify page is working with test navigation
    try:
        log("Testing page object with about:blank...")
        page.goto("about:blank", timeout=15000)
        log("Page object is working correctly")
        
        # Additional test - check if page is still responsive
        try:
            page_title = page.title()
            log(f"Page title test successful: '{page_title}'")
        except Exception as title_error:
            log(f"Page title test failed: {title_error}")
            raise Exception("Page is not responsive")
            
    except Exception as e:
        log(f"Page navigation test failed: {e}")
        raise Exception(f"Page is not functional: {e}")

    # Final validation
    try:
        current_url = page.url
        log(f"Final page validation successful. Current URL: {current_url}")
        return page
    except Exception as final_error:
        log(f"Final page validation failed: {final_error}")
        raise Exception("Page is not stable enough to proceed")

def check_session_validity(page):
    """Check if current session is valid with better error handling"""
    try:
        log("Checking session validity...")
        
        # First, verify the page is still accessible
        try:
            current_url = page.url
            log(f"Page is accessible, current URL: {current_url}")
        except Exception as page_access_error:
            log(f"Page access error: {page_access_error}")
            raise Exception("Page is no longer accessible")
        
        log("About to navigate to Turnitin login page...")
        
        # Try navigation with robust error handling
        try:
            page.goto("https://www.turnitin.com/login_page.asp?lang=en_us", 
                     timeout=60000, 
                     wait_until="domcontentloaded")  # Changed from "load" to "domcontentloaded"
            log("Successfully navigated to login page")
        except Exception as nav_error:
            log(f"Navigation error: {nav_error}")
            
            # Check if the page/context is still valid
            try:
                test_url = page.url
                log(f"Page still accessible after nav error: {test_url}")
            except Exception as page_check_error:
                log(f"Page no longer accessible: {page_check_error}")
                raise Exception(f"Page/context closed during navigation: {nav_error}")
            
            # Try a simpler approach
            try:
                log("Trying simpler navigation approach...")
                page.goto("https://www.turnitin.com/", timeout=45000, wait_until="domcontentloaded")
                log("Successfully navigated to Turnitin homepage")
                time.sleep(2)
                page.goto("https://www.turnitin.com/login_page.asp?lang=en_us", 
                         timeout=45000, 
                         wait_until="domcontentloaded")
                log("Successfully navigated to login page on retry")
            except Exception as retry_nav_error:
                log(f"Retry navigation failed: {retry_nav_error}")
                raise Exception(f"Cannot access Turnitin website: {retry_nav_error}")
        
        log("Navigated to login page successfully")
        random_wait(3, 5)
        
        # Check if login form is visible (means session expired)
        log("Checking if login form is visible...")
        try:
            # Use a more robust way to check for login form
            email_selector = 'input[name="email"], input[type="email"], input[placeholder*="email" i]'
            page.wait_for_selector(email_selector, timeout=10000)
            email_visible = page.locator(email_selector).is_visible()
            log(f"Email textbox visible: {email_visible}")
            
            if email_visible:
                log("Session expired - login form detected")
                return False
            else:
                log("Session appears to be valid")
                return True
                
        except Exception as form_check_error:
            log(f"Error checking login form: {form_check_error}")
            log("Assuming session is invalid and needs login")
            return False
            
    except Exception as e:
        log(f"Error checking session: {e}. Will perform fresh login...")
        log(f"Error type: {type(e).__name__}")
        log(f"Error details: {str(e)}")
        return False

def perform_login(page, context):
    """Perform login to Turnitin with enhanced stability"""
    log("Need to perform fresh login...")
    
    # First, check if the current page is still accessible
    try:
        current_url = page.url
        log(f"Current page before login: {current_url}")
    except Exception as page_check_error:
        log(f"Current page is not accessible: {page_check_error}")
        # Try to create a new page
        try:
            log("Creating fresh page for login...")
            page = context.new_page()
            log("Created fresh page for login")
        except Exception as new_page_error:
            log(f"Cannot create new page: {new_page_error}")
            raise Exception(f"Cannot create new page for login: {new_page_error}")
    
    try:
        # Test the page first
        try:
            log("Testing page with about:blank...")
            page.goto("about:blank", timeout=15000)
            log("Page is working")
        except Exception as test_error:
            log(f"Page test failed: {test_error}")
            raise Exception(f"Page is not working: {test_error}")
        
        log("Navigating to login page for fresh login...")
        try:
            page.goto("https://www.turnitin.com/login_page.asp?lang=en_us", 
                     timeout=60000, 
                     wait_until="domcontentloaded")
            log("Successfully navigated to login page for fresh login")
        except Exception as login_nav_error:
            log(f"Failed to navigate to login page: {login_nav_error}")
            raise Exception(f"Cannot reach Turnitin login page: {login_nav_error}")
        
        random_wait(3, 5)
        
        log("Filling in email...")
        try:
            email_selector = 'input[name="email"], input[type="email"], input[placeholder*="email" i]'
            page.wait_for_selector(email_selector, timeout=15000)
            email_field = page.locator(email_selector).first
            email_field.click()
            email_field.fill(TURNITIN_EMAIL)
            log("Email filled successfully")
        except Exception as email_error:
            log(f"Error filling email: {email_error}")
            raise Exception(f"Cannot fill email field: {email_error}")
        
        random_wait(2, 4)
        
        log("Filling in password...")
        try:
            password_selector = 'input[name="password"], input[type="password"], input[placeholder*="password" i]'
            password_field = page.locator(password_selector).first
            password_field.click()
            password_field.fill(TURNITIN_PASSWORD)
            log("Password filled successfully")
        except Exception as password_error:
            log(f"Error filling password: {password_error}")
            raise Exception(f"Cannot fill password field: {password_error}")
        
        random_wait(2, 4)
        
        log("Clicking 'Log in' button...")
        try:
            login_button_selector = 'button:has-text("Log in"), input[type="submit"], button[type="submit"]'
            login_button = page.locator(login_button_selector).first
            login_button.click()
            log("Login button clicked successfully")
        except Exception as login_click_error:
            log(f"Error clicking login button: {login_click_error}")
            raise Exception(f"Cannot click login button: {login_click_error}")
        
        log("Waiting for login to complete...")
        page.wait_for_timeout(10000)
        
        # Check if login was successful
        try:
            log("Checking for login success...")
            # Try to wait for a successful login indicator
            try:
                page.wait_for_selector('a.sn_quick_submit', timeout=20000)
                log("Login successful - Quick Submit link found")
            except:
                # Alternative check - see if we're no longer on login page
                current_url = page.url
                if "login" not in current_url:
                    log("Login appears successful - no longer on login page")
                else:
                    log("Still on login page, checking for errors...")
                    raise Exception("Login may have failed")
                    
        except Exception as success_check_error:
            log(f"Login success check failed: {success_check_error}")
            # Continue anyway, might still work
        
        # Update cookies after login
        try:
            context.storage_state(path="cookies.json")
            log("Cookies saved successfully after login.")
        except Exception as cookie_save_error:
            log(f"Error saving cookies after login: {cookie_save_error}")
        
        return page
            
    except Exception as e:
        log(f"Error during login process: {e}")
        log(f"Login error type: {type(e).__name__}")
        raise Exception(f"Failed to login: {e}")

def navigate_to_quick_submit(page):
    """Navigate to Quick Submit page with enhanced stability"""
    log("Navigating to Quick Submit...")
    try:
        # Verify page is still accessible
        try:
            current_url = page.url
            log(f"Current URL before Quick Submit: {current_url}")
        except Exception as url_error:
            log(f"Cannot get current URL: {url_error}")
            raise Exception("Page is no longer accessible")
        
        # Wait for page to be fully loaded
        try:
            page.wait_for_load_state('networkidle', timeout=30000)
        except Exception as load_error:
            log(f"Page load state error: {load_error}")
            # Continue anyway
        
        # Take a screenshot for debugging
        try:
            page.screenshot(path="debug_before_quicksubmit.png")
            log("Screenshot saved: debug_before_quicksubmit.png")
        except Exception as screenshot_error:
            log(f"Could not take screenshot: {screenshot_error}")
        
        # Try multiple approaches to find Quick Submit
        quick_submit_selectors = [
            "a.sn_quick_submit",
            'a:has-text("Quick Submit")',
            'a[href*="quicksubmit"]',
            'a[href*="quick_submit"]',
            '.sn_quick_submit'
        ]
        
        log("Trying different Quick Submit selectors...")
        for i, selector in enumerate(quick_submit_selectors):
            try:
                log(f"Trying selector {i+1}: {selector}")
                page.wait_for_selector(selector, timeout=10000)
                elements = page.locator(selector).all()
                if elements:
                    log(f"Found {len(elements)} elements with selector: {selector}")
                    for j, element in enumerate(elements):
                        try:
                            text = element.inner_text()
                            href = element.get_attribute('href')
                            visible = element.is_visible()
                            log(f"  Element {j+1}: '{text}' -> {href}, visible: {visible}")
                            
                            if visible:
                                log(f"Clicking visible element with selector: {selector}")
                                element.click()
                                log("Successfully clicked Quick Submit!")
                                random_wait(3, 5)
                                return page
                        except Exception as element_error:
                            log(f"Error with element {j+1}: {element_error}")
                            continue
                else:
                    log(f"No elements found with selector: {selector}")
            except Exception as selector_error:
                log(f"Selector {selector} failed: {selector_error}")
                continue
        
        # If selectors failed, try direct navigation
        log("All selectors failed, trying direct navigation...")
        direct_urls = [
            "https://www.turnitin.com/t_inbox.asp?aid=quicksubmit",
            "https://www.turnitin.com/t_inbox.asp?r=0&aid=quicksubmit"
        ]
        
        for url in direct_urls:
            try:
                log(f"Trying direct URL: {url}")
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
                log(f"Successfully navigated to: {url}")
                random_wait(3, 5)
                return page
            except Exception as url_error:
                log(f"Direct URL {url} failed: {url_error}")
                continue
        
        raise Exception("Could not navigate to Quick Submit with any method")
        
    except Exception as e:
        log(f"Error in navigate_to_quick_submit: {e}")
        raise Exception(f"Could not navigate to Quick Submit: {e}")

def save_cookies(context):
    """Save cookies for future sessions"""
    try:
        context.storage_state(path="cookies.json")
        log("Cookies updated successfully.")
    except Exception as e:
        log(f"Error updating cookies: {e}")