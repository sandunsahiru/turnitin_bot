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

def log(message: str):
    """Log a message with a timestamp to the terminal."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def random_wait(min_seconds=2, max_seconds=5):
    """Wait for a random amount of time to appear more human-like"""
    wait_time = random.uniform(min_seconds, max_seconds)
    time.sleep(wait_time)

def check_network_connectivity():
    """Check if the server can reach Turnitin"""
    try:
        log("Testing network connectivity to Turnitin...")
        response = requests.get("https://www.turnitin.com", timeout=30)
        log(f"Network test response code: {response.status_code}")
        log(f"Response headers: {dict(list(response.headers.items())[:5])}")  # First 5 headers
        return True
    except Exception as network_error:
        log(f"Network connectivity test failed: {network_error}")
        return False

def test_server_environment():
    """Test if server environment can run Playwright"""
    try:
        log("Testing server environment for Playwright compatibility...")
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
        context = browser.new_context()
        page = context.new_page()
        
        # Test basic navigation
        page.goto("https://httpbin.org/user-agent", timeout=30000)
        content = page.content()
        log(f"Test page content length: {len(content)} characters")
        
        page.close()
        context.close()
        browser.close()
        p.stop()
        
        log("Server environment test passed")
        return True
    except Exception as test_error:
        log(f"Server environment test failed: {test_error}")
        return False

def create_browser():
    """Create and return a browser instance - Enhanced for server deployment"""
    # First test network and environment
    if not check_network_connectivity():
        raise Exception("Network connectivity test failed - cannot reach external sites")
    
    if not test_server_environment():
        raise Exception("Server environment test failed - Playwright may not be properly installed")
    
    p = sync_playwright().start()
    browser = None
    
    for attempt in range(3):
        try:
            log(f"Browser launch attempt {attempt + 1}/3...")
            
            if attempt == 0:
                # First attempt: Server-optimized headless mode
                browser = p.chromium.launch(
                    headless=True,
                    slow_mo=300,  # Slower for server
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--disable-software-rasterizer',
                        '--disable-background-timer-throttling',
                        '--disable-backgrounding-occluded-windows',
                        '--disable-renderer-backgrounding',
                        '--disable-features=TranslateUI',
                        '--disable-features=BlinkGenPropertyTrees',
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
                        '--disable-extensions',
                        '--disable-plugins',
                        '--metrics-recording-only',
                        '--no-report-upload',
                        '--disable-blink-features=AutomationControlled',
                        '--disable-web-security',
                        '--allow-running-insecure-content',
                        '--ignore-certificate-errors',
                        '--ignore-ssl-errors',
                        '--ignore-certificate-errors-spki-list',
                        '--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    ]
                )
            elif attempt == 1:
                # Second attempt: Even more conservative
                browser = p.chromium.launch(
                    headless=True,
                    slow_mo=500,  # Much slower
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--single-process',
                        '--disable-features=VizDisplayCompositor',
                        '--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    ]
                )
            else:
                # Third attempt: Minimal args - for debugging you might want to set headless=False temporarily
                browser = p.chromium.launch(
                    headless=True,  # Change to False temporarily to see what's happening
                    slow_mo=1000,
                    args=['--no-sandbox', '--disable-dev-shm-usage']
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
    """Create browser context with server-optimized settings"""
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
        
        # Server-optimized context options
        context_options = {
            'viewport': {'width': 1920, 'height': 1080},
            'user_agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'java_script_enabled': True,
            'accept_downloads': True,
            'bypass_csp': True,
            'ignore_https_errors': True,
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
                'user_agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
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
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Cache-Control': 'max-age=0'
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
    """Check if current session is valid with enhanced server debugging"""
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
        
        # Try navigation with enhanced server handling
        try:
            # Take screenshot before navigation
            try:
                page.screenshot(path="debug_before_turnitin_nav.png")
                log("Screenshot saved: debug_before_turnitin_nav.png")
            except Exception as screenshot_error:
                log(f"Could not take screenshot: {screenshot_error}")
            
            page.goto("https://www.turnitin.com/login_page.asp?lang=en_us", 
                     timeout=90000,  # Increased timeout for server
                     wait_until="domcontentloaded")
            log("Successfully navigated to login page")
            
            # Take screenshot after navigation
            try:
                page.screenshot(path="debug_after_turnitin_nav.png")
                log("Screenshot saved: debug_after_turnitin_nav.png")
            except Exception as screenshot_error:
                log(f"Could not take screenshot: {screenshot_error}")
                
        except Exception as nav_error:
            log(f"Navigation error: {nav_error}")
            
            # Take screenshot of failed state
            try:
                page.screenshot(path="debug_navigation_failed.png")
                log("Screenshot saved: debug_navigation_failed.png")
            except:
                pass
            
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
                page.goto("https://www.turnitin.com/", timeout=60000, wait_until="domcontentloaded")
                log("Successfully navigated to Turnitin homepage")
                time.sleep(3)
                page.goto("https://www.turnitin.com/login_page.asp?lang=en_us", 
                         timeout=60000, 
                         wait_until="domcontentloaded")
                log("Successfully navigated to login page on retry")
            except Exception as retry_nav_error:
                log(f"Retry navigation failed: {retry_nav_error}")
                raise Exception(f"Cannot access Turnitin website: {retry_nav_error}")
        
        log("Navigated to login page successfully")
        random_wait(5, 8)  # Longer wait for server
        
        # Check if login form is visible (means session expired)
        log("Checking if login form is visible...")
        try:
            # Use a more robust way to check for login form
            email_selectors = [
                'input[name="email"]',
                'input[type="email"]', 
                'input[placeholder*="email" i]',
                'input[id*="email" i]',
                '#email',
                '#user_email'
            ]
            
            email_found = False
            for selector in email_selectors:
                try:
                    log(f"Checking for email selector: {selector}")
                    page.wait_for_selector(selector, timeout=5000)
                    email_visible = page.locator(selector).is_visible()
                    log(f"Email field with selector {selector} visible: {email_visible}")
                    if email_visible:
                        email_found = True
                        break
                except Exception as selector_error:
                    log(f"Email selector {selector} failed: {selector_error}")
                    continue
            
            if email_found:
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
    """Perform login to Turnitin with enhanced server debugging"""
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
            # Take screenshot before login navigation
            page.screenshot(path="debug_before_login.png")
            log("Screenshot saved: debug_before_login.png")
            
            page.goto("https://www.turnitin.com/login_page.asp?lang=en_us", 
                     timeout=90000,  # Increased timeout for server
                     wait_until="domcontentloaded")
            log("Successfully navigated to login page for fresh login")
            
            # Take screenshot after login navigation
            page.screenshot(path="debug_login_page.png")
            log("Screenshot saved: debug_login_page.png")
            
        except Exception as login_nav_error:
            log(f"Failed to navigate to login page: {login_nav_error}")
            # Take screenshot of failed login navigation
            try:
                page.screenshot(path="debug_login_nav_failed.png")
                log("Screenshot saved: debug_login_nav_failed.png")
            except:
                pass
            raise Exception(f"Cannot reach Turnitin login page: {login_nav_error}")
        
        random_wait(5, 8)  # Longer wait for server
        
        # Debug: Check what's actually on the page
        try:
            page_title = page.title()
            page_url = page.url
            page_content = page.content()
            log(f"Login page title: {page_title}")
            log(f"Login page URL: {page_url}")
            log(f"Page content length: {len(page_content)} characters")
            log(f"Page content preview: {page_content[:500]}")  # First 500 chars
        except Exception as debug_error:
            log(f"Debug info collection failed: {debug_error}")
        
        log("Filling in email...")
        try:
            # Enhanced email field detection with more selectors
            email_selectors = [
                'input[name="email"]',
                'input[type="email"]', 
                'input[placeholder*="email" i]',
                'input[id*="email" i]',
                '#email',
                '#user_email',
                '.email-input',
                'input[autocomplete="email"]'
            ]
            
            email_field = None
            for selector in email_selectors:
                try:
                    log(f"Trying email selector: {selector}")
                    page.wait_for_selector(selector, timeout=10000)
                    email_field = page.locator(selector).first
                    if email_field.is_visible():
                        log(f"Found visible email field with selector: {selector}")
                        break
                except Exception as selector_error:
                    log(f"Email selector {selector} failed: {selector_error}")
                    continue
            
            if not email_field:
                # Take screenshot of current state
                page.screenshot(path="debug_no_email_field.png")
                log("Screenshot saved: debug_no_email_field.png")
                raise Exception("No email field found with any selector")
            
            email_field.click()
            email_field.fill(TURNITIN_EMAIL)
            log("Email filled successfully")
            
            # Take screenshot after email filled
            page.screenshot(path="debug_email_filled.png")
            log("Screenshot saved: debug_email_filled.png")
            
        except Exception as email_error:
            log(f"Error filling email: {email_error}")
            # Take screenshot of email error state
            try:
                page.screenshot(path="debug_email_error.png")
                log("Screenshot saved: debug_email_error.png")
            except:
                pass
            raise Exception(f"Cannot fill email field: {email_error}")
        
        random_wait(3, 5)
        
        log("Filling in password...")
        try:
            password_selectors = [
                'input[name="password"]',
                'input[type="password"]',
                'input[placeholder*="password" i]',
                'input[id*="password" i]',
                '#password',
                '#user_password'
            ]
            
            password_field = None
            for selector in password_selectors:
                try:
                    log(f"Trying password selector: {selector}")
                    password_field = page.locator(selector).first
                    if password_field.is_visible():
                        log(f"Found visible password field with selector: {selector}")
                        break
                except Exception as selector_error:
                    log(f"Password selector {selector} failed: {selector_error}")
                    continue
            
            if not password_field:
                raise Exception("No password field found")
            
            password_field.click()
            password_field.fill(TURNITIN_PASSWORD)
            log("Password filled successfully")
        except Exception as password_error:
            log(f"Error filling password: {password_error}")
            raise Exception(f"Cannot fill password field: {password_error}")
        
        random_wait(3, 5)
        
        log("Clicking 'Log in' button...")
        try:
            login_button_selectors = [
                'button:has-text("Log in")',
                'input[type="submit"]',
                'button[type="submit"]',
                'input[value*="Log in"]',
                'button:has-text("Login")',
                '.login-button'
            ]
            
            login_clicked = False
            for selector in login_button_selectors:
                try:
                    log(f"Trying login button selector: {selector}")
                    login_button = page.locator(selector).first
                    if login_button.is_visible():
                        login_button.click()
                        log(f"Login button clicked successfully with selector: {selector}")
                        login_clicked = True
                        break
                except Exception as login_selector_error:
                    log(f"Login selector {selector} failed: {login_selector_error}")
                    continue
            
            if not login_clicked:
                raise Exception("No login button found or clicked")
                
        except Exception as login_click_error:
            log(f"Error clicking login button: {login_click_error}")
            raise Exception(f"Cannot click login button: {login_click_error}")
        
        log("Waiting for login to complete...")
        page.wait_for_timeout(15000)  # Longer wait for server
        
        # Take screenshot after login attempt
        try:
            page.screenshot(path="debug_after_login.png")
            log("Screenshot saved: debug_after_login.png")
        except Exception as screenshot_error:
            log(f"Could not take post-login screenshot: {screenshot_error}")
        
        # Check if login was successful
        try:
            log("Checking for login success...")
            # Try to wait for a successful login indicator
            try:
                page.wait_for_selector('a.sn_quick_submit', timeout=30000)  # Increased timeout
                log("Login successful - Quick Submit link found")
            except:
                # Alternative check - see if we're no longer on login page
                current_url = page.url
                if "login" not in current_url:
                    log("Login appears successful - no longer on login page")
                else:
                    log("Still on login page, checking for errors...")
                    # Check for error messages
                    try:
                        error_elements = page.locator('.error, .alert, [class*="error"], [class*="alert"]').all()
                        for element in error_elements:
                            try:
                                error_text = element.inner_text()
                                if error_text:
                                    log(f"Found error message: {error_text}")
                            except:
                                pass
                    except:
                        pass
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
                page.goto(url, timeout=90000, wait_until="domcontentloaded")  # Increased timeout
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

# Add debugging command to test components
def debug_login_components():
    """Debug function to test login components separately"""
    log("=== DEBUGGING LOGIN COMPONENTS ===")
    
    # Test 1: Network connectivity
    log("1. Testing network connectivity...")
    if not check_network_connectivity():
        return False
    
    # Test 2: Server environment
    log("2. Testing server environment...")
    if not test_server_environment():
        return False
    
    # Test 3: Browser creation
    log("3. Testing browser creation...")
    try:
        p, browser = create_browser()
        log("Browser created successfully")
        
        # Test 4: Context creation
        log("4. Testing context creation...")
        context = create_browser_context(browser)
        log("Context created successfully")
        
        # Test 5: Page creation
        log("5. Testing page creation...")
        page = create_page(context)
        log("Page created successfully")
        
        # Test 6: Basic navigation
        log("6. Testing basic navigation...")
        page.goto("https://httpbin.org/html", timeout=60000)
        log("Basic navigation successful")
        
        # Test 7: Turnitin homepage access
        log("7. Testing Turnitin homepage access...")
        page.goto("https://www.turnitin.com/", timeout=90000)
        page.screenshot(path="debug_turnitin_homepage.png")
        log("Turnitin homepage access successful, screenshot saved")
        
        # Clean up
        page.close()
        context.close()
        browser.close()
        p.stop()
        
        log("=== ALL TESTS PASSED ===")
        return True
        
    except Exception as debug_error:
        log(f"Debug test failed: {debug_error}")
        return False