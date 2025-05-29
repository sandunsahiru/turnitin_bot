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
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))  # For debug screenshots

def log(message: str):
    """Log a message with a timestamp to the terminal."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def random_wait(min_seconds=2, max_seconds=5):
    """Wait for a random amount of time to appear more human-like"""
    wait_time = random.uniform(min_seconds, max_seconds)
    time.sleep(wait_time)

def process_turnitin(file_path: str, chat_id: int, bot):
    """
    Automate Turnitin processing with new workflow:
      - Log in using new system
      - Navigate to Quick Submit
      - Configure submission settings
      - Upload the document
      - Wait for processing, then download reports
      - Send downloaded files to the Telegram user
      - Clean up files afterwards
      - Delete processing messages to keep chat clean
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    processing_messages = []  # Track messages to delete later
    
    try:
        # Send initial message and track it
        msg = bot.send_message(chat_id, "🚀 Starting Turnitin process...")
        processing_messages.append(msg.message_id)
        log("Starting Turnitin process...")

        # Verify file exists before proceeding
        if not os.path.exists(file_path):
            raise Exception(f"File not found: {file_path}")
        
        log(f"File verified: {file_path} (Size: {os.path.getsize(file_path)} bytes)")

        with sync_playwright() as p:
            # Launch browser in headless mode for production
            browser = None
            for attempt in range(3):
                try:
                    log(f"Browser launch attempt {attempt + 1}/3...")
                    
                    if attempt == 0:
                        # First attempt: headless with minimal arguments for production
                        browser = p.chromium.launch(
                            headless=True,
                            args=[
                                '--no-sandbox',
                                '--disable-dev-shm-usage',
                                '--disable-gpu',
                                '--disable-web-security',
                                '--disable-features=VizDisplayCompositor'
                            ]
                        )
                    elif attempt == 1:
                        # Second attempt: headless with fewer arguments
                        browser = p.chromium.launch(
                            headless=True,
                            args=['--no-sandbox', '--disable-dev-shm-usage']
                        )
                    else:
                        # Third attempt: try Firefox headless
                        log("Trying Firefox browser as fallback...")
                        browser = p.firefox.launch(headless=True)
                    
                    log(f"Browser launched successfully on attempt {attempt + 1}")
                    
                    # Test if browser is actually working
                    try:
                        version = browser.version
                        log(f"Browser version: {version}")
                        break  # Success, exit the loop
                    except Exception as version_error:
                        log(f"Browser version check failed: {version_error}")
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
                
            cookies_path = "cookies.json"

            # Create browser context with cookies if available
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
                
                if os.path.exists(cookies_path):
                    log("Found saved cookies. Attempting to load them...")
                    # Try to read and validate cookies file
                    with open(cookies_path, 'r') as f:
                        cookies_content = f.read().strip()
                    
                    if cookies_content and cookies_content != "":
                        json.loads(cookies_content)  # Validate JSON
                        try:
                            context = browser.new_context(storage_state=cookies_path)
                            log("Successfully loaded saved cookies.")
                        except Exception as cookie_context_error:
                            log(f"Error creating context with cookies: {cookie_context_error}")
                            log("Creating context without cookies...")
                            context = browser.new_context()
                    else:
                        log("Cookies file is empty. Creating new session.")
                        context = browser.new_context()
                else:
                    log("No saved cookies found. Creating a new session.")
                    context = browser.new_context()
                    
                log("Browser context created successfully")
            except (json.JSONDecodeError, FileNotFoundError, Exception) as e:
                log(f"Error loading cookies: {e}. Creating new session and removing bad cookies file.")
                if os.path.exists(cookies_path):
                    os.remove(cookies_path)
                try:
                    context = browser.new_context()
                    log("Fresh browser context created after error")
                except Exception as fresh_context_error:
                    log(f"Cannot create fresh context: {fresh_context_error}")
                    raise Exception(f"Browser context creation failed: {fresh_context_error}")

            # Create page with error handling
            try:
                log("Attempting to create new page...")
                page = context.new_page()
                log("Created new page for Turnitin process")
                
                # Immediately test the page
                try:
                    log("Testing page immediately after creation...")
                    page_url = page.url
                    log(f"Page created with URL: {page_url}")
                except Exception as immediate_test_error:
                    log(f"Immediate page test failed: {immediate_test_error}")
                    # Try to create another page
                    try:
                        log("Attempting to create replacement page...")
                        page.close()
                        page = context.new_page()
                        log("Replacement page created successfully")
                    except Exception as replacement_error:
                        log(f"Replacement page creation failed: {replacement_error}")
                        raise Exception(f"Cannot create working page: {replacement_error}")
                        
            except Exception as page_error:
                log(f"Page creation failed: {page_error}")
                log(f"Page error type: {type(page_error).__name__}")
                raise Exception(f"Could not create page: {page_error}")
            
            # Verify page is working with multiple tests
            try:
                log("Testing page object with about:blank...")
                page.goto("about:blank", timeout=10000)
                log("Page object is working correctly")
                
                # Additional test - check if page is still responsive
                try:
                    page_title = page.title()
                    log(f"Page title test successful: '{page_title}'")
                except Exception as title_error:
                    log(f"Page title test failed: {title_error}")
                    raise Exception("Page is not responsive")
                    
            except Exception as e:
                log(f"Page object issue detected: {e}")
                log("Attempting to create a new page...")
                try:
                    page.close()
                    page = context.new_page()
                    page.goto("about:blank", timeout=10000)
                    log("Successfully created new working page")
                except Exception as e2:
                    log(f"Cannot create working page: {e2}")
                    
                    # Try to create a new context entirely
                    try:
                        log("Attempting to create new context...")
                        context.close()
                        context = browser.new_context()
                        page = context.new_page()
                        page.goto("about:blank", timeout=10000)
                        log("Successfully created new context and page")
                    except Exception as e3:
                        log(f"Cannot create new context: {e3}")
                        raise Exception(f"Browser page creation failed: {e3}")

            # Add a final validation before proceeding
            try:
                current_url = page.url
                log(f"Final page validation successful. Current URL: {current_url}")
            except Exception as final_error:
                log(f"Final page validation failed: {final_error}")
                raise Exception("Page is not stable enough to proceed")

            # Try to check if session is valid by going to login page
            session_valid = False
            
            try:
                log("Checking session validity...")
                log("About to navigate to Turnitin login page...")
                
                # Try navigation with more detailed error handling
                try:
                    page.goto("https://www.turnitin.com/login_page.asp?lang=en_us", timeout=60000)
                    log("Successfully navigated to login page")
                except Exception as nav_error:
                    log(f"Navigation error: {nav_error}")
                    log("Attempting to check if page/context is still valid...")
                    
                    # Check if the page is still accessible
                    try:
                        current_url = page.url
                        log(f"Current page URL: {current_url}")
                    except Exception as url_error:
                        log(f"Cannot get page URL: {url_error}")
                        raise Exception(f"Page/context became invalid during navigation: {nav_error}")
                    
                    # Try navigation again with a simpler URL first
                    try:
                        log("Trying to navigate to Google first as a test...")
                        page.goto("https://www.google.com", timeout=30000)
                        log("Google navigation successful, now trying Turnitin...")
                        page.goto("https://www.turnitin.com/login_page.asp?lang=en_us", timeout=60000)
                        log("Turnitin navigation successful on second attempt")
                    except Exception as second_nav_error:
                        log(f"Second navigation attempt failed: {second_nav_error}")
                        raise Exception(f"Cannot access Turnitin website: {second_nav_error}")
                
                log("Navigated to login page successfully")
                random_wait(3, 5)
                
                # Check if login form is visible (means session expired)
                log("Checking if login form is visible...")
                try:
                    email_visible = page.get_by_role("textbox", name="Email address").is_visible(timeout=5000)
                    log(f"Email textbox visible: {email_visible}")
                    
                    if email_visible:
                        log("Session expired - login form detected")
                        session_valid = False
                    else:
                        log("Session appears to be valid")
                        session_valid = True
                        # Try to navigate to home to double-check
                        log("Attempting to navigate to home page...")
                        page.goto("https://www.turnitin.com/home/", timeout=60000)
                        log("Navigated to home page successfully")
                        random_wait(2, 4)
                except Exception as form_check_error:
                    log(f"Error checking login form: {form_check_error}")
                    log("Assuming session is invalid and needs login")
                    session_valid = False
                    
            except Exception as e:
                log(f"Error checking session: {e}. Will perform fresh login...")
                log(f"Error type: {type(e).__name__}")
                log(f"Error details: {str(e)}")
                session_valid = False

            # Perform login if session is not valid
            if not session_valid:
                log("Need to perform fresh login...")
                try:
                    # Create a fresh page for login to avoid any context issues
                    log("Creating fresh page for login...")
                    if page:
                        try:
                            page.close()
                            log("Closed previous page")
                        except Exception as close_error:
                            log(f"Error closing previous page: {close_error}")
                    
                    try:
                        page = context.new_page()
                        log("Created fresh page for login")
                    except Exception as new_page_error:
                        log(f"Error creating new page: {new_page_error}")
                        raise Exception(f"Cannot create new page for login: {new_page_error}")
                    
                    # Test the new page
                    try:
                        log("Testing new page with about:blank...")
                        page.goto("about:blank", timeout=10000)
                        log("New page is working")
                    except Exception as test_error:
                        log(f"New page test failed: {test_error}")
                        raise Exception(f"New page is not working: {test_error}")
                    
                    log("Navigating to login page for fresh login...")
                    try:
                        page.goto("https://www.turnitin.com/login_page.asp?lang=en_us", timeout=60000)
                        log("Successfully navigated to login page for fresh login")
                    except Exception as login_nav_error:
                        log(f"Failed to navigate to login page: {login_nav_error}")
                        # Try a simple connectivity test first
                        try:
                            log("Testing connectivity with Google...")
                            page.goto("https://www.google.com", timeout=30000)
                            log("Google connectivity successful")
                            log("Retrying Turnitin login page...")
                            page.goto("https://www.turnitin.com/login_page.asp?lang=en_us", timeout=60000)
                            log("Turnitin login page navigation successful on retry")
                        except Exception as retry_error:
                            log(f"Connectivity test or retry failed: {retry_error}")
                            raise Exception(f"Cannot reach Turnitin login page: {retry_error}")
                    
                    random_wait(3, 5)
                    
                    log("Filling in email...")
                    try:
                        page.get_by_role("textbox", name="Email address").click()
                        page.get_by_role("textbox", name="Email address").fill(TURNITIN_EMAIL)
                        log("Email filled successfully")
                    except Exception as email_error:
                        log(f"Error filling email: {email_error}")
                        raise Exception(f"Cannot fill email field: {email_error}")
                    
                    random_wait(2, 4)
                    
                    log("Filling in password...")
                    try:
                        page.get_by_role("textbox", name="Password").click()
                        page.get_by_role("textbox", name="Password").fill(TURNITIN_PASSWORD)
                        log("Password filled successfully")
                    except Exception as password_error:
                        log(f"Error filling password: {password_error}")
                        raise Exception(f"Cannot fill password field: {password_error}")
                    
                    random_wait(2, 4)
                    
                    log("Clicking 'Log in' button...")
                    try:
                        page.get_by_role("button", name="Log in").click()
                        log("Login button clicked successfully")
                    except Exception as login_click_error:
                        log(f"Error clicking login button: {login_click_error}")
                        raise Exception(f"Cannot click login button: {login_click_error}")
                    
                    log("Waiting for login to complete...")
                    page.wait_for_timeout(8000)  # Increased wait time
                    
                    # Check if login was successful
                    try:
                        log("Checking for Quick Submit to verify login...")
                        page.wait_for_selector('text="Quick Submit"', timeout=20000)  # Increased timeout
                        log("Login successful - dashboard loaded")
                    except PlaywrightTimeout:
                        log("Quick Submit not found, checking current URL...")
                        try:
                            current_url = page.url
                            log(f"Current URL after login: {current_url}")
                            if "login" in current_url:
                                raise Exception("Login failed - still on login page")
                            log("Not on login page, continuing despite Quick Submit not found...")
                        except Exception as url_check_error:
                            log(f"Cannot check URL after login: {url_check_error}")
                            raise Exception("Cannot verify login status")
                    
                    # Update cookies after successful login
                    try:
                        context.storage_state(path="cookies.json")
                        log("Cookies saved successfully after login.")
                    except Exception as e:
                        log(f"Error saving cookies after login: {e}")
                        
                except Exception as e:
                    log(f"Error during login process: {e}")
                    log(f"Login error type: {type(e).__name__}")
                    # Try to create a completely fresh page
                    try:
                        if page:
                            page.close()
                        page = context.new_page()
                        log("Created emergency fresh page after login error")
                    except Exception as emergency_error:
                        log(f"Cannot create emergency page: {emergency_error}")
                    raise Exception(f"Failed to login: {e}")
            else:
                # Session is valid, ensure we're on the right page
                try:
                    current_url = page.url
                    log(f"Session valid, current URL: {current_url}")
                    if "login" in current_url:
                        log("Valid session but on login page, navigating to home...")
                        page.goto("https://www.turnitin.com/home/", timeout=60000)
                        random_wait(2, 4)
                except Exception as e:
                    log(f"Error navigating from valid session: {e}")

            # Always try to update cookies
            try:
                context.storage_state(path="cookies.json")
                log("Cookies updated successfully.")
            except Exception as e:
                log(f"Error updating cookies: {e}")

            # Navigate to Quick Submit
            log("Navigating to Quick Submit...")
            try:
                # Ensure we have a valid page
                if not page:
                    log("Page is None, creating new page...")
                    page = context.new_page()
                
                # Check current URL and navigate to home if needed
                try:
                    current_url = page.url
                    log(f"Current URL before Quick Submit: {current_url}")
                except:
                    log("Could not get current URL, navigating to home...")
                    page.goto("https://www.turnitin.com/home/", timeout=60000)
                    random_wait(2, 4)
                
                # Make sure we're on the right page by checking if Quick Submit is visible
                log("Checking if Quick Submit is visible...")
                quick_submit_visible = False
                try:
                    quick_submit_visible = page.get_by_role("link", name="Quick Submit").is_visible(timeout=5000)
                    log(f"Quick Submit visible: {quick_submit_visible}")
                except Exception as e:
                    log(f"Error checking Quick Submit visibility: {e}")
                
                if not quick_submit_visible:
                    log("Quick Submit not visible, navigating to home page...")
                    page.goto("https://www.turnitin.com/home/", timeout=60000)
                    log("Navigated to home page")
                    random_wait(2, 4)
                    
                    # Check again after navigating to home
                    try:
                        quick_submit_visible = page.get_by_role("link", name="Quick Submit").is_visible(timeout=5000)
                        log(f"Quick Submit visible after home navigation: {quick_submit_visible}")
                    except Exception as e:
                        log(f"Error checking Quick Submit visibility after home: {e}")
                
                log("Clicking Quick Submit...")
                page.get_by_role("link", name="Quick Submit").click()
                log("Clicked Quick Submit successfully")
                random_wait(2, 4)
                
            except Exception as e:
                log(f"Error finding Quick Submit: {e}")
                # Try direct navigation as fallback
                log("Trying direct navigation to home page as fallback...")
                try:
                    if not page:
                        page = context.new_page()
                    page.goto("https://www.turnitin.com/home/", timeout=60000)
                    log("Direct navigation successful")
                    random_wait(3, 5)
                    log("Attempting to click Quick Submit again...")
                    page.get_by_role("link", name="Quick Submit").click()
                    log("Second attempt to click Quick Submit successful")
                    random_wait(2, 4)
                except Exception as e2:
                    log(f"Fallback navigation also failed: {e2}")
                    raise Exception(f"Could not navigate to Quick Submit: {e2}")

            log("Clicking Submit button...")
            try:
                page.get_by_role("link", name="Submit", exact=True).click()
                log("Submit button clicked successfully")
                random_wait(3, 5)
            except Exception as e:
                log(f"Error clicking Submit button: {e}")
                raise Exception(f"Failed to click Submit button: {e}")

            # Configure submission settings
            log("Configuring submission settings...")
            
            try:
                # Check all search options
                log("Checking 'Search the internet' option...")
                page.locator("label").filter(has_text="Search the internet").get_by_role("checkbox").check()
                random_wait(1, 2)
                
                log("Checking 'Search student papers' option...")
                page.locator("label").filter(has_text="Search student papers").get_by_role("checkbox").check()
                random_wait(1, 2)
                
                log("Checking 'Search periodicals, journals' option...")
                page.locator("label").filter(has_text="Search periodicals, journals").get_by_role("checkbox").check()
                random_wait(1, 2)
                
                log("Checking 'Search the Army Institute' option...")
                page.locator("label").filter(has_text="Search the Army Institute of").get_by_role("checkbox").check()
                random_wait(1, 2)

                # Set submit papers option
                log("Setting submit papers option...")
                page.get_by_label("Submit papers to: Standard").select_option("0")
                random_wait(2, 3)
                log("All submission settings configured successfully")
            except Exception as e:
                log(f"Error configuring submission settings: {e}")
                raise Exception(f"Failed to configure settings: {e}")

            log("Clicking Submit to proceed...")
            try:
                page.get_by_role("button", name="Submit").click()
                log("Submit button (to proceed) clicked successfully")
                random_wait(3, 5)
            except Exception as e:
                log(f"Error clicking Submit to proceed: {e}")
                raise Exception(f"Failed to click Submit to proceed: {e}")

            # Fill submission details - UPDATED TO INCLUDE USER ID FIRST
            log("Filling submission details...")
            
            page.get_by_role("textbox", name="First name").click()
            page.get_by_role("textbox", name="First name").fill("Test User")
            random_wait(1, 2)
            
            page.get_by_role("textbox", name="Last name").click()
            page.get_by_role("textbox", name="Last name").fill("Document Check")
            random_wait(1, 2)
            
            # NEW: Include user ID first in submission title for easy identification
            submission_title = f"User_{chat_id}_Document_{timestamp}"
            page.get_by_role("textbox", name="Submission title").click()
            page.get_by_role("textbox", name="Submission title").fill(submission_title)
            random_wait(2, 3)

            # Upload file - FIXED SECTION
            log(f"Uploading file from path: {file_path}")
            
            # Wait before file upload
            log("Waiting 5 seconds before file upload...")
            msg = bot.send_message(chat_id, "📎 Preparing document upload...")
            processing_messages.append(msg.message_id)
            page.wait_for_timeout(5000)
            
            try:
                # Method 1: Try to find the hidden file input directly
                log("Looking for file input element...")
                
                # Wait for the page to be fully loaded
                page.wait_for_load_state('domcontentloaded')
                random_wait(2, 3)
                
                # Try to find file input by different selectors
                file_input = None
                input_selectors = [
                    'input[type="file"]',
                    'input[name*="file"]', 
                    'input[accept*=".doc"]',
                    '#fileInput',
                    '.file-input',
                    'input[style*="display: none"]'
                ]
                
                for selector in input_selectors:
                    try:
                        file_inputs = page.locator(selector).all()
                        if file_inputs:
                            log(f"Found {len(file_inputs)} file input(s) with selector: {selector}")
                            file_input = file_inputs[0]
                            break
                    except Exception as selector_error:
                        log(f"Selector {selector} failed: {selector_error}")
                        continue
                
                if file_input:
                    log("Found file input element, attempting to set files...")
                    # Make the file input visible if it's hidden
                    try:
                        page.evaluate("""
                            const fileInputs = document.querySelectorAll('input[type="file"]');
                            fileInputs.forEach(input => {
                                input.style.display = 'block';
                                input.style.visibility = 'visible';
                                input.style.opacity = '1';
                                input.style.position = 'static';
                                input.style.width = 'auto';
                                input.style.height = 'auto';
                            });
                        """)
                        log("Made file input visible")
                        random_wait(1, 2)
                    except Exception as visibility_error:
                        log(f"Could not make file input visible: {visibility_error}")
                    
                    # Set the file
                    try:
                        file_input.set_input_files(file_path)
                        log("File uploaded using direct input method")
                        upload_success = True
                    except Exception as upload_error:
                        log(f"Direct file input upload failed: {upload_error}")
                        upload_success = False
                else:
                    log("No file input found with standard selectors")
                    upload_success = False
                
                # Method 2: If direct method failed, try clicking the browse button first
                if not upload_success:
                    log("Trying alternative upload method...")
                    try:
                        # Click the "Choose from this computer" link/button
                        log("Clicking 'Choose from this computer' button...")
                        choose_button = page.get_by_role("link", name="Choose from this computer")
                        choose_button.click()
                        log("Clicked choose button successfully")
                        random_wait(2, 3)
                        
                        # Now try to find and use the file input that should be activated
                        log("Looking for activated file input...")
                        page.wait_for_load_state('domcontentloaded')
                        
                        # Look for any file input that might have been activated
                        file_inputs = page.locator('input[type="file"]').all()
                        log(f"Found {len(file_inputs)} file input elements after clicking")
                        
                        if file_inputs:
                            # Try each file input until one works
                            for i, input_elem in enumerate(file_inputs):
                                try:
                                    log(f"Trying file input {i+1}...")
                                    input_elem.set_input_files(file_path)
                                    log(f"Successfully uploaded file using input {i+1}")
                                    upload_success = True
                                    break
                                except Exception as input_error:
                                    log(f"File input {i+1} failed: {input_error}")
                                    continue
                        
                    except Exception as alternative_error:
                        log(f"Alternative upload method failed: {alternative_error}")
                
                # Method 3: Use JavaScript to trigger file selection
                if not upload_success:
                    log("Trying JavaScript file upload method...")
                    try:
                        # Read the file content and convert to base64
                        with open(file_path, 'rb') as f:
                            file_content = f.read()
                        
                        import base64
                        file_base64 = base64.b64encode(file_content).decode('utf-8')
                        file_name = os.path.basename(file_path)
                        
                        # Use JavaScript to create and trigger file selection
                        js_code = f"""
                        const fileInput = document.querySelector('input[type="file"]');
                        if (fileInput) {{
                            // Create a DataTransfer object to simulate file selection
                            const dt = new DataTransfer();
                            
                            // Convert base64 to blob
                            const byteCharacters = atob('{file_base64}');
                            const byteNumbers = new Array(byteCharacters.length);
                            for (let i = 0; i < byteCharacters.length; i++) {{
                                byteNumbers[i] = byteCharacters.charCodeAt(i);
                            }}
                            const byteArray = new Uint8Array(byteNumbers);
                            const blob = new Blob([byteArray], {{type: 'application/octet-stream'}});
                            
                            // Create file object
                            const file = new File([blob], '{file_name}', {{type: 'application/octet-stream'}});
                            
                            // Add file to DataTransfer
                            dt.items.add(file);
                            
                            // Set files on input
                            fileInput.files = dt.files;
                            
                            // Trigger change event
                            const event = new Event('change', {{bubbles: true}});
                            fileInput.dispatchEvent(event);
                            
                            return true;
                        }}
                        return false;
                        """
                        
                        result = page.evaluate(js_code)
                        if result:
                            log("JavaScript file upload method successful")
                            upload_success = True
                        else:
                            log("JavaScript method failed - no file input found")
                            
                    except Exception as js_error:
                        log(f"JavaScript upload method failed: {js_error}")
                
                if not upload_success:
                    raise Exception("All file upload methods failed")
                    
            except Exception as upload_error:
                log(f"File upload error: {upload_error}")
                raise Exception(f"Failed to upload file: {upload_error}")

            random_wait(3, 5)

            # Wait for file selection confirmation
            try:
                log("Waiting for file selection confirmation...")
                page.wait_for_selector("#selected-file-name", timeout=10000)
                page.locator("#selected-file-name").click()
                log("File selection confirmed")
                random_wait(1, 2)
            except Exception as confirm_error:
                log(f"File selection confirmation failed: {confirm_error}")
                # Continue anyway, might still work

            log("Clicking Upload button...")
            try:
                page.get_by_role("button", name="Upload").click()
                log("Upload button clicked successfully")
                random_wait(2, 4)
            except Exception as upload_btn_error:
                log(f"Error clicking Upload button: {upload_btn_error}")
                raise Exception(f"Failed to click Upload button: {upload_btn_error}")

            # Handle privacy notice if it appears
            try:
                if page.get_by_text("We take your privacy very").is_visible(timeout=3000):
                    page.get_by_text("We take your privacy very").click()
                    random_wait(1, 2)
            except:
                log("Privacy notice not found, continuing...")

            # Wait before confirming and verify upload details
            log("Waiting 10 seconds before confirming document...")
            msg = bot.send_message(chat_id, "📤 Document uploaded, verifying details...")
            processing_messages.append(msg.message_id)
            page.wait_for_timeout(10000)

            # Extract and verify submission metadata before confirming
            try:
                log("Extracting submission metadata...")
                
                # Get submission details
                author = page.locator("#submission-metadata-author").inner_text()
                assignment_title = page.locator("#submission-metadata-assignment").inner_text()
                actual_submission_title = page.locator("#submission-metadata-title").inner_text()
                filename = page.locator("#submission-metadata-filename").inner_text()
                filesize = page.locator("#submission-metadata-filesize").inner_text()
                page_count = page.locator("#submission-metadata-pagecount").inner_text()
                word_count = page.locator("#submission-metadata-wordcount").inner_text()
                character_count = page.locator("#submission-metadata-charactercount").inner_text()
                
                log(f"Submission metadata extracted:")
                log(f"  Author: {author}")
                log(f"  Assignment: {assignment_title}")
                log(f"  Title: {actual_submission_title}")
                log(f"  Filename: {filename}")
                log(f"  Size: {filesize}")
                log(f"  Pages: {page_count}")
                log(f"  Words: {word_count}")
                log(f"  Characters: {character_count}")
                
                # Send simplified metadata to user (only essential info)
                metadata_msg = f"""✅ <b>Document Verified</b>

📃 <b>Pages:</b> {page_count}
🔤 <b>Words:</b> {word_count}
🔢 <b>Characters:</b> {character_count}

🚀 Submitting to Turnitin..."""
                
                verification_msg = bot.send_message(chat_id, metadata_msg)
                processing_messages.append(verification_msg.message_id)
                
                # Update our submission title to match what Turnitin assigned
                submission_title = actual_submission_title
                log(f"Updated submission title to: {submission_title}")
                
            except Exception as metadata_error:
                log(f"Error extracting metadata: {metadata_error}")
                # Continue anyway, but warn user
                warning_msg = bot.send_message(chat_id, "⚠️ Could not verify upload details, but proceeding with submission...")
                processing_messages.append(warning_msg.message_id)

            log("Clicking Confirm button...")
            try:
                page.get_by_role("button", name="Confirm").click()
                log("Confirm button clicked successfully")
            except Exception as confirm_error:
                log(f"Error clicking Confirm button: {confirm_error}")
                raise Exception(f"Failed to click Confirm button: {confirm_error}")

            # Wait up to 60 seconds before clicking "Go to assignment inbox" as requested
            log("Waiting up to 60 seconds for processing...")
            msg = bot.send_message(chat_id, "⏳ Document submitted, waiting for processing to complete...")
            processing_messages.append(msg.message_id)
            page.wait_for_timeout(60000)

            log("Clicking 'Go to assignment inbox'...")
            try:
                page.get_by_role("button", name="Go to assignment inbox").click()
                log("Go to assignment inbox clicked successfully")
                random_wait(3, 5)
            except Exception as inbox_error:
                log(f"Error clicking Go to assignment inbox: {inbox_error}")
                # Try alternative text
                try:
                    page.get_by_text("Go to assignment inbox").click()
                    log("Go to assignment inbox clicked using alternative selector")
                    random_wait(3, 5)
                except Exception as alt_inbox_error:
                    log(f"Alternative inbox button also failed: {alt_inbox_error}")
                    # Continue anyway, we might be able to find the submission

            # Wait 60 seconds before navigating to Quick Submit as requested
            log("Waiting 60 seconds before navigating to Quick Submit...")
            msg = bot.send_message(chat_id, "⏰ Waiting for document to appear in submissions list...")
            processing_messages.append(msg.message_id)
            page.wait_for_timeout(60000)

            # Navigate back to Quick Submit to find our submission
            log("Navigating to Quick Submit to find our submission...")
            try:
                page.get_by_role("link", name="Quick Submit").click()
                log("Navigated to Quick Submit successfully")
                random_wait(3, 5)
            except Exception as quick_submit_error:
                log(f"Error navigating to Quick Submit: {quick_submit_error}")
                # Try direct navigation
                try:
                    page.goto("https://www.turnitin.com/quicksubmit/", timeout=30000)
                    log("Direct navigation to Quick Submit successful")
                    random_wait(3, 5)
                except Exception as direct_nav_error:
                    log(f"Direct navigation also failed: {direct_nav_error}")
                    raise Exception("Cannot navigate to Quick Submit to find submission")

            # Look for our submission - UPDATED TO USE ACTUAL SUBMISSION TITLE
            log(f"Looking for submission with title: {submission_title}")
            submission_found = False
            page1 = None

            # Method 1: Try to find by the actual submission title from Turnitin
            try:
                log("Method 1: Looking for Test User cell...")
                page.get_by_role("cell", name="Test User Test User").click()
                random_wait(2, 3)
                
                log(f"Method 1: Looking for submission title link: {submission_title}")
                with page.expect_popup() as page1_info:
                    page.get_by_role("link", name=submission_title).click()
                page1 = page1_info.value
                random_wait(3, 5)
                submission_found = True
                log("Found submission using Method 1 with actual title")
                
            except Exception as e1:
                log(f"Method 1 failed: {e1}")

            # Method 2: Try finding by partial title match
            if not submission_found:
                try:
                    log("Method 2: Looking for any cell containing 'Test User'...")
                    cells = page.locator('td:has-text("Test User")').all()
                    if cells:
                        log(f"Found {len(cells)} cells with Test User")
                        cells[0].click()
                        random_wait(2, 3)
                        
                        # Look for our submission title (try partial matches)
                        title_parts = submission_title.split()
                        for part in title_parts:
                            if len(part) > 3:  # Only try meaningful parts
                                try:
                                    log(f"Trying to find link with text part: {part}")
                                    links = page.locator(f'a:has-text("{part}")').all()
                                    if links:
                                        log(f"Found {len(links)} links with title part: {part}")
                                        with page.expect_popup() as page1_info:
                                            links[0].click()
                                        page1 = page1_info.value
                                        random_wait(3, 5)
                                        submission_found = True
                                        log(f"Found submission using Method 2 with title part: {part}")
                                        break
                                except Exception as part_error:
                                    log(f"Title part {part} search failed: {part_error}")
                                    continue
                        
                        # If partial match didn't work, try full title
                        if not submission_found:
                            try:
                                links = page.locator(f'a:has-text("{submission_title}")').all()
                                if links:
                                    log(f"Found {len(links)} links with full submission title")
                                    with page.expect_popup() as page1_info:
                                        links[0].click()
                                    page1 = page1_info.value
                                    random_wait(3, 5)
                                    submission_found = True
                                    log("Found submission using Method 2 with full title")
                            except Exception as full_title_error:
                                log(f"Full title search failed: {full_title_error}")
                        
                except Exception as e2:
                    log(f"Method 2 failed: {e2}")

            # Method 3: Look for the most recent submission by timestamp
            if not submission_found:
                try:
                    log("Method 3: Looking for most recent submission by timestamp...")
                    # Get all submission links
                    submission_links = page.locator('a[href*="submissions"]').all()
                    if submission_links:
                        log(f"Found {len(submission_links)} submission links")
                        # Try to find the most recent one (should be first in list)
                        with page.expect_popup() as page1_info:
                            submission_links[0].click()
                        page1 = page1_info.value
                        random_wait(3, 5)
                        submission_found = True
                        log("Found submission using Method 3 (most recent)")
                except Exception as e3:
                    log(f"Method 3 failed: {e3}")

            # Method 4: Try searching by uploaded filename
            if not submission_found:
                try:
                    log("Method 4: Looking by uploaded filename...")
                    original_name = os.path.basename(file_path)
                    base_name = os.path.splitext(original_name)[0]  # Remove extension
                    
                    # Try finding by filename parts
                    filename_links = page.locator(f'a:has-text("{base_name}")').all()
                    if filename_links:
                        log(f"Found {len(filename_links)} links with filename pattern")
                        with page.expect_popup() as page1_info:
                            filename_links[0].click()
                        page1 = page1_info.value
                        random_wait(3, 5)
                        submission_found = True
                        log("Found submission using Method 4 with filename")
                except Exception as e4:
                    log(f"Method 4 failed: {e4}")

            # Method 5: Try by table row approach - click on any row with "Test User"
            if not submission_found:
                try:
                    log("Method 5: Looking for table rows with Test User...")
                    # Find table rows that contain "Test User"
                    rows = page.locator('tr:has-text("Test User")').all()
                    if rows:
                        log(f"Found {len(rows)} rows with Test User")
                        for i, row in enumerate(rows):
                            try:
                                log(f"Trying row {i+1}...")
                                # Look for a link in this row
                                row_links = row.locator('a[href*="submissions"]').all()
                                if row_links:
                                    log(f"Found {len(row_links)} submission links in row {i+1}")
                                    with page.expect_popup() as page1_info:
                                        row_links[0].click()
                                    page1 = page1_info.value
                                    random_wait(3, 5)
                                    submission_found = True
                                    log(f"Found submission using Method 5, row {i+1}")
                                    break
                            except Exception as row_error:
                                log(f"Row {i+1} failed: {row_error}")
                                continue
                except Exception as e5:
                    log(f"Method 5 failed: {e5}")

            if not submission_found:
                # Enhanced debugging with more detailed information
                try:
                    log("Debugging: Comprehensive link and content analysis...")
                    
                    # Check if we're on the right page
                    current_url = page.url
                    page_title = page.title()
                    log(f"Current page URL: {current_url}")
                    log(f"Current page title: {page_title}")
                    
                    # Look for all table elements that might contain submissions
                    tables = page.locator('table').all()
                    log(f"Found {len(tables)} tables on page")
                    
                    # Look for all cells containing "Test User"
                    test_user_cells = page.locator('td:has-text("Test User")').all()
                    log(f"Found {len(test_user_cells)} cells with 'Test User'")
                    
                    # Get more detailed link information
                    all_links = page.locator('a').all()
                    log(f"Found {len(all_links)} total links on page")
                    
                    submission_links = []
                    for i, link in enumerate(all_links[:20]):  # Check first 20 links
                        try:
                            link_text = link.inner_text()[:100]  # First 100 chars
                            link_href = link.get_attribute('href') or 'No href'
                            
                            # Check if this might be a submission link
                            if any(keyword in link_href.lower() for keyword in ['submission', 'view', 'paper']):
                                submission_links.append((i+1, link_text, link_href))
                                log(f"Potential submission link {i+1}: '{link_text}' -> {link_href}")
                            elif 'Test User' in link_text or any(word in link_text.lower() for word in ['project', 'document', 'paper', submission_title.lower()]):
                                log(f"Relevant link {i+1}: '{link_text}' -> {link_href}")
                        except Exception as link_debug_error:
                            log(f"Error analyzing link {i+1}: {link_debug_error}")
                            continue
                    
                    log(f"Found {len(submission_links)} potential submission links")
                    
                    # Try clicking the first potential submission link if any found
                    if submission_links:
                        try:
                            log(f"Attempting to click first potential submission link...")
                            link_index = submission_links[0][0] - 1  # Convert back to 0-based index
                            with page.expect_popup() as page1_info:
                                all_links[link_index].click()
                            page1 = page1_info.value
                            random_wait(3, 5)
                            submission_found = True
                            log("Found submission using debugging method with potential link")
                        except Exception as debug_click_error:
                            log(f"Debug click failed: {debug_click_error}")
                    
                except Exception as debug_error:
                    log(f"Enhanced debugging failed: {debug_error}")
                
                if not submission_found:
                    # Last resort: take a screenshot for manual debugging
                    try:
                        screenshot_path = f"debug_screenshot_{chat_id}_{timestamp}.png"
                        page.screenshot(path=screenshot_path)
                        log(f"Screenshot saved for debugging: {screenshot_path}")
                        
                        # Send screenshot to admin for debugging
                        try:
                            with open(screenshot_path, "rb") as screenshot_file:
                                bot.send_photo(
                                    ADMIN_TELEGRAM_ID, 
                                    screenshot_file, 
                                    caption=f"Debug Screenshot - User {chat_id} - Could not find submission"
                                )
                            os.remove(screenshot_path)  # Clean up screenshot
                        except Exception as screenshot_send_error:
                            log(f"Could not send debug screenshot: {screenshot_send_error}")
                    except Exception as screenshot_error:
                        log(f"Could not take debug screenshot: {screenshot_error}")
                    
                    raise Exception(f"Could not find the submitted document using any method. Title was: {submission_title}")

            # Ensure downloads folder exists
            downloads_dir = "downloads"
            os.makedirs(downloads_dir, exist_ok=True)

            # Wait for the submission page to fully load
            log("Waiting for submission page to load...")
            try:
                page1.wait_for_load_state('networkidle', timeout=30000)
                msg = bot.send_message(chat_id, "📊 Processing complete. Downloading reports...")
                processing_messages.append(msg.message_id)
                log("Submission page loaded successfully")
            except Exception as load_error:
                log(f"Page load timeout: {load_error}")
                msg = bot.send_message(chat_id, "📊 Processing complete. Attempting to download reports...")
                processing_messages.append(msg.message_id)

            # Download Similarity Report
            log("Downloading Similarity Report...")
            sim_filename = None
            try:
                # Wait for page to be ready
                log("Waiting for download buttons to be ready...")
                page1.wait_for_load_state('domcontentloaded')
                random_wait(3, 5)
                
                # Click the download icon (this opens the popover menu)
                log("Clicking download icon to open menu...")
                try:
                    # Try clicking the download button by different selectors
                    download_selectors = [
                        'tii-sws-download-btn-mfe',
                        '[id="sws-download-btn-mfe"]',
                        'button[aria-label="Download"]',
                        'button[data-px="DownloadMenuClicked"]'
                    ]
                    
                    download_clicked = False
                    for selector in download_selectors:
                        try:
                            log(f"Trying download selector: {selector}")
                            download_btn = page1.locator(selector)
                            if download_btn.count() > 0:
                                download_btn.click()
                                log(f"Successfully clicked download button with selector: {selector}")
                                download_clicked = True
                                break
                        except Exception as sel_error:
                            log(f"Selector {selector} failed: {sel_error}")
                            continue
                    
                    if not download_clicked:
                        # Try using JavaScript to click the download button
                        log("Trying JavaScript click method...")
                        js_click_result = page1.evaluate("""
                            const downloadBtn = document.querySelector('tii-sws-download-btn-mfe') || 
                                               document.querySelector('[data-px="DownloadMenuClicked"]') ||
                                               document.querySelector('button[aria-label="Download"]');
                            if (downloadBtn) {
                                downloadBtn.click();
                                return true;
                            }
                            return false;
                        """)
                        
                        if js_click_result:
                            log("JavaScript click successful")
                            download_clicked = True
                        else:
                            log("JavaScript click failed - button not found")
                    
                    if not download_clicked:
                        raise Exception("Could not click download button with any method")
                        
                except Exception as download_click_error:
                    log(f"Error clicking download button: {download_click_error}")
                    raise Exception(f"Failed to open download menu: {download_click_error}")
                
                random_wait(2, 3)
                
                # Click on Similarity Report option in the popover menu
                log("Clicking Similarity Report option in menu...")
                try:
                    # Try different selectors for the similarity report button
                    sim_selectors = [
                        'button[data-px="SimReportDownloadClicked"]',
                        'button:has-text("Similarity Report")',
                        'li.download-menu-item:has-text("Similarity Report") button',
                        '.download-menu button:has-text("Similarity Report")'
                    ]
                    
                    sim_clicked = False
                    for selector in sim_selectors:
                        try:
                            log(f"Trying similarity report selector: {selector}")
                            sim_btn = page1.locator(selector)
                            if sim_btn.count() > 0 and sim_btn.is_visible():
                                with page1.expect_download(timeout=30000) as download_info:
                                    sim_btn.click()
                                download_sim = download_info.value
                                sim_filename = os.path.join(downloads_dir, f"{chat_id}_{timestamp}_similarity.pdf")
                                download_sim.save_as(sim_filename)
                                log(f"Saved Similarity Report as {sim_filename}")
                                sim_clicked = True
                                break
                        except Exception as sim_error:
                            log(f"Similarity selector {selector} failed: {sim_error}")
                            continue
                    
                    if not sim_clicked:
                        # Try JavaScript approach for similarity report
                        log("Trying JavaScript method for similarity report...")
                        js_sim_result = page1.evaluate("""
                            const simBtn = document.querySelector('button[data-px="SimReportDownloadClicked"]') ||
                                          document.querySelector('button:contains("Similarity Report")') ||
                                          Array.from(document.querySelectorAll('button')).find(btn => btn.textContent.includes('Similarity Report'));
                            if (simBtn) {
                                simBtn.click();
                                return true;
                            }
                            return false;
                        """)
                        
                        if js_sim_result:
                            log("JavaScript similarity report click successful, waiting for download...")
                            try:
                                with page1.expect_download(timeout=30000) as download_info:
                                    pass  # Download should already be triggered
                                download_sim = download_info.value
                                sim_filename = os.path.join(downloads_dir, f"{chat_id}_{timestamp}_similarity.pdf")
                                download_sim.save_as(sim_filename)
                                log(f"Saved Similarity Report as {sim_filename}")
                                sim_clicked = True
                            except Exception as js_download_error:
                                log(f"JavaScript download failed: {js_download_error}")
                        
                    if not sim_clicked:
                        raise Exception("Could not click similarity report button")
                        
                except Exception as sim_click_error:
                    log(f"Error clicking similarity report: {sim_click_error}")
                    raise Exception(f"Failed to download similarity report: {sim_click_error}")
                
            except Exception as e:
                log(f"Error downloading Similarity Report: {e}")
                # Don't raise exception, continue to try AI report
                sim_filename = None

            # Try to download AI Writing Report  
            ai_filename = None
            try:
                log("Attempting to download AI Writing Report...")
                
                # Wait a bit before trying AI report
                random_wait(2, 3)
                
                # Click the download icon again to open the popover menu
                log("Clicking download icon for AI report...")
                try:
                    # Try the same download selectors
                    download_clicked = False
                    for selector in download_selectors:
                        try:
                            log(f"Trying download selector for AI: {selector}")
                            download_btn = page1.locator(selector)
                            if download_btn.count() > 0:
                                download_btn.click()
                                log(f"Successfully clicked download button for AI with selector: {selector}")
                                download_clicked = True
                                break
                        except Exception as sel_error:
                            log(f"AI download selector {selector} failed: {sel_error}")
                            continue
                    
                    if not download_clicked:
                        # Try JavaScript method
                        js_click_result = page1.evaluate("""
                            const downloadBtn = document.querySelector('tii-sws-download-btn-mfe') || 
                                               document.querySelector('[data-px="DownloadMenuClicked"]') ||
                                               document.querySelector('button[aria-label="Download"]');
                            if (downloadBtn) {
                                downloadBtn.click();
                                return true;
                            }
                            return false;
                        """)
                        
                        if js_click_result:
                            log("JavaScript click for AI successful")
                            download_clicked = True
                        else:
                            raise Exception("Could not click download button for AI report")
                            
                except Exception as ai_download_click_error:
                    log(f"Error clicking download button for AI: {ai_download_click_error}")
                    raise Exception(f"Failed to open download menu for AI: {ai_download_click_error}")
                
                random_wait(2, 3)
                
                # Click on AI Writing Report option in the popover menu
                log("Clicking AI Writing Report option in menu...")
                try:
                    # Try different selectors for the AI report button
                    ai_selectors = [
                        'button[data-px="AIWritingReportDownload"]',
                        'button:has-text("AI Writing Report")',
                        'li.download-menu-item:has-text("AI Writing Report") button',
                        '.download-menu button:has-text("AI Writing Report")'
                    ]
                    
                    ai_clicked = False
                    for selector in ai_selectors:
                        try:
                            log(f"Trying AI report selector: {selector}")
                            ai_btn = page1.locator(selector)
                            if ai_btn.count() > 0 and ai_btn.is_visible():
                                with page1.expect_download(timeout=30000) as download_info:
                                    ai_btn.click()
                                download_ai = download_info.value
                                ai_filename = os.path.join(downloads_dir, f"{chat_id}_{timestamp}_ai.pdf")
                                download_ai.save_as(ai_filename)
                                log(f"Saved AI Writing Report as {ai_filename}")
                                ai_clicked = True
                                break
                        except Exception as ai_error:
                            log(f"AI selector {selector} failed: {ai_error}")
                            continue
                    
                    if not ai_clicked:
                        # Try JavaScript approach for AI report
                        log("Trying JavaScript method for AI report...")
                        js_ai_result = page1.evaluate("""
                            const aiBtn = document.querySelector('button[data-px="AIWritingReportDownload"]') ||
                                         document.querySelector('button:contains("AI Writing Report")') ||
                                         Array.from(document.querySelectorAll('button')).find(btn => btn.textContent.includes('AI Writing Report'));
                            if (aiBtn) {
                                aiBtn.click();
                                return true;
                            }
                            return false;
                        """)
                        
                        if js_ai_result:
                            log("JavaScript AI report click successful, waiting for download...")
                            try:
                                with page1.expect_download(timeout=30000) as download_info:
                                    pass  # Download should already be triggered
                                download_ai = download_info.value
                                ai_filename = os.path.join(downloads_dir, f"{chat_id}_{timestamp}_ai.pdf")
                                download_ai.save_as(ai_filename)
                                log(f"Saved AI Writing Report as {ai_filename}")
                                ai_clicked = True
                            except Exception as js_ai_download_error:
                                log(f"JavaScript AI download failed: {js_ai_download_error}")
                        
                    if not ai_clicked:
                        log("Could not click AI Writing Report button - might not be available")
                        
                except Exception as ai_click_error:
                    log(f"Error clicking AI report: {ai_click_error}")
                    # AI report might not be available for this document
                
            except Exception as e:
                log(f"Could not download AI Writing Report: {e}")
                # AI report might not be available for this document

            # Close browser
            try:
                context.close()
                browser.close()
                log("Browser closed successfully")
            except Exception as close_error:
                log(f"Error closing browser: {close_error}")

            # Delete all processing messages before sending final results
            try:
                log(f"Deleting {len(processing_messages)} processing messages...")
                for message_id in processing_messages:
                    try:
                        bot.delete_message(chat_id, message_id)
                    except Exception as delete_error:
                        log(f"Could not delete message {message_id}: {delete_error}")
                        pass  # Continue even if some messages can't be deleted
                log("Processing messages cleaned up")
            except Exception as cleanup_msg_error:
                log(f"Error during message cleanup: {cleanup_msg_error}")

            # Send the downloaded files to Telegram user
            if sim_filename and os.path.exists(sim_filename):
                log("Sending Similarity Report to Telegram user...")
                try:
                    with open(sim_filename, "rb") as sim_file:
                        bot.send_document(chat_id, sim_file, caption="📄 Turnitin Similarity Report")
                    log("Similarity Report sent successfully")
                except Exception as send_error:
                    log(f"Error sending Similarity Report: {send_error}")
                    bot.send_message(chat_id, f"❌ Error sending Similarity Report: {send_error}")
            else:
                bot.send_message(chat_id, "❌ Similarity Report could not be downloaded")

            if ai_filename and os.path.exists(ai_filename):
                log("Sending AI Writing Report to Telegram user...")
                try:
                    with open(ai_filename, "rb") as ai_file:
                        bot.send_document(chat_id, ai_file, caption="🤖 Turnitin AI Writing Report")
                    bot.send_message(chat_id, "✅ Process complete. Both reports have been sent.")
                    log("AI Writing Report sent successfully")
                except Exception as send_ai_error:
                    log(f"Error sending AI Writing Report: {send_ai_error}")
                    bot.send_message(chat_id, "✅ Similarity report sent. AI report send failed.")
            else:
                message = ("✅ Similarity report sent successfully!\n\n"
                          "⚠️ AI Writing Report could not be generated.\n\n"
                          "Please check that your document:\n"
                          "• Contains between 500-10,000 words\n"
                          "• Has sufficient original content\n"
                          "• Is in a supported format (PDF, DOC, DOCX)\n\n"
                          "💡 Try submitting a longer document with more text content.")
                bot.send_message(chat_id, message)

            log("Turnitin process complete and reports sent.")

            # Delete downloaded files and the uploaded file after sending
            try:
                if sim_filename and os.path.exists(sim_filename):
                    os.remove(sim_filename)
                    log(f"Deleted downloaded file {sim_filename}")
                
                if ai_filename and os.path.exists(ai_filename):
                    os.remove(ai_filename)
                    log(f"Deleted downloaded file {ai_filename}")
                
                if os.path.exists(file_path):
                    os.remove(file_path)
                    log(f"Deleted uploaded file {file_path}")
            except Exception as cleanup_error:
                log(f"Error during cleanup: {cleanup_error}")

    except Exception as e:
        error_msg = f"An error occurred during Turnitin processing: {str(e)}"
        
        # Delete processing messages even if there was an error
        try:
            log(f"Deleting {len(processing_messages)} processing messages due to error...")
            for message_id in processing_messages:
                try:
                    bot.delete_message(chat_id, message_id)
                except:
                    pass  # Continue even if some messages can't be deleted
        except Exception as cleanup_msg_error:
            log(f"Error during error message cleanup: {cleanup_msg_error}")
        
        bot.send_message(chat_id, f"❌ {error_msg}")
        log(f"ERROR: {error_msg}")
        
        # Clean up files even if process failed
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                log(f"Cleaned up uploaded file {file_path}")
        except Exception as cleanup_error:
            log(f"Error during error cleanup: {cleanup_error}")