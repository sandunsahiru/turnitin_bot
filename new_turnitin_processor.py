import os
import re
import time
import json
import random
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# Load environment variables
load_dotenv()

# Turnitin service configuration
TURNITIN_USERNAME = os.getenv("TURNITIN_USERNAME")
TURNITIN_PASSWORD = os.getenv("TURNITIN_PASSWORD")
TURNITIN_BASE_URL = os.getenv("TURNITIN_BASE_URL", "https://www.turnitright.com")

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
    """Log with timestamp"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] NEW-PROCESSOR: {message}")

def random_wait(min_seconds=1, max_seconds=3):
    """Random wait to appear human-like"""
    time.sleep(random.uniform(min_seconds, max_seconds))

def create_unique_title(chat_id, timestamp, original_title="document"):
    """Create unique title for multi-user environment"""
    sanitized_title = re.sub(r'[^a-zA-Z0-9\s]', '_', original_title or "document")
    sanitized_title = re.sub(r'\s+', '_', sanitized_title)
    return f"user_{chat_id}_{timestamp}_{sanitized_title}"

def save_cookies():
    """Save current session cookies"""
    try:
        if browser_session['context']:
            storage_state = browser_session['context'].storage_state()
            with open("turnitin_session_cookies.json", "w") as f:
                json.dump(storage_state, f, indent=2)
            log("Session cookies saved successfully")
    except Exception as e:
        log(f"Error saving cookies: {e}")

def load_cookies():
    """Load saved cookies if available"""
    try:
        if os.path.exists("turnitin_session_cookies.json"):
            with open("turnitin_session_cookies.json", "r") as f:
                storage_state = json.load(f)
            log("Session cookies loaded successfully")
            return storage_state
        return None
    except Exception as e:
        log(f"Error loading cookies: {e}")
        return None

def test_cookie_session(page):
    """Test if cookie-based session is still valid"""
    try:
        log("Testing cookie session validity...")
        
        page.goto(f"{TURNITIN_BASE_URL}/my-files/", timeout=30000)
        page.wait_for_load_state('networkidle', timeout=15000)
        
        try:
            page.wait_for_selector('[href*="logout"], .user-menu, [href*="my-files"], .username', timeout=10000)
            log("Cookie session is valid - user is authenticated")
            return True
        except:
            current_url = page.url
            if "login" in current_url.lower():
                log("Cookie session expired - redirected to login")
                return False
            else:
                log("Cookie session status unclear, assuming valid")
                return True
                
    except Exception as e:
        log(f"Cookie session test failed: {e}")
        return False

def get_browser_session():
    """Get or create browser session with cookie support"""
    global browser_session
    
    # Check if session is valid
    if (browser_session['browser'] and 
        browser_session['context'] and 
        browser_session['page'] and
        browser_session['logged_in']):
        try:
            # Test session
            current_url = browser_session['page'].url
            browser_session['last_activity'] = datetime.now()
            log(f"Reusing existing browser session - Current URL: {current_url}")
            return browser_session['page']
        except:
            log("Existing session invalid, creating new one")
            cleanup_browser()
    
    # Create new session
    log("Creating new browser session...")
    try:
        # Set environment variables for Playwright to use custom temp directories
        temp_dir = '/root/turnitin_bot/playwright_temp'
        browser_data_dir = '/root/turnitin_bot/browser_data'
        
        # Create directories if they don't exist
        os.makedirs(temp_dir, exist_ok=True)
        os.makedirs(browser_data_dir, exist_ok=True)
        
        # Set environment variables
        os.environ['TMPDIR'] = temp_dir
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/root/.cache/ms-playwright'
        os.environ['PLAYWRIGHT_DOWNLOAD_PATH'] = browser_data_dir
        
        log(f"Set custom temp directory: {temp_dir}")
        log(f"Set custom browser data directory: {browser_data_dir}")
        
        browser_session['playwright'] = sync_playwright().start()
        
        browser_session['browser'] = browser_session['playwright'].chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--window-size=1920,1080',
                '--disable-dev-shm-usage',
                f'--data-path={browser_data_dir}',
                f'--disk-cache-dir={browser_data_dir}/cache',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding'
            ]
        )
        
        # Try to load saved cookies first
        storage_state = load_cookies()
        context_options = {
            'viewport': {'width': 1920, 'height': 1080},
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        if storage_state:
            log("Loading saved cookies into new session")
            context_options['storage_state'] = storage_state
        
        browser_session['context'] = browser_session['browser'].new_context(**context_options)
        browser_session['page'] = browser_session['context'].new_page()
        
        # Test cookie-based authentication first
        if storage_state and test_cookie_session(browser_session['page']):
            log("Successfully authenticated using saved cookies")
            browser_session['logged_in'] = True
            browser_session['last_activity'] = datetime.now()
            return browser_session['page']
        else:
            log("Cookie authentication failed, performing fresh login")
            # Clear invalid cookies
            try:
                os.remove("turnitin_session_cookies.json")
                log("Removed invalid cookies")
            except:
                pass
            
            # Perform fresh login
            if login():
                browser_session['logged_in'] = True
                browser_session['last_activity'] = datetime.now()
                save_cookies()  # Save new session cookies
                log("Fresh login successful, cookies saved")
                return browser_session['page']
            else:
                raise Exception("Login failed")
            
    except Exception as e:
        log(f"Browser session creation failed: {e}")
        cleanup_browser()
        raise

def login():
    """Login to Turnitin service with enhanced verification"""
    page = browser_session['page']
    
    try:
        log("Performing fresh login to Turnitin...")
        
        # Clear any existing session data
        page.context.clear_cookies()
        
        page.goto(f"{TURNITIN_BASE_URL}/login/", timeout=60000)
        page.wait_for_load_state('networkidle', timeout=30000)
        
        # Check if already logged in
        try:
            page.wait_for_selector('[href*="dashboard"], [href*="my-files"], .user-menu', timeout=5000)
            log("Already logged in")
            return True
        except:
            pass
        
        # Fill login form
        username_selectors = [
            'input[name="username"]', 'input[type="email"]', '#username', '#email'
        ]
        
        username_filled = False
        for selector in username_selectors:
            try:
                page.wait_for_selector(selector, timeout=8000)
                page.fill(selector, TURNITIN_USERNAME)
                log(f"Username filled using selector: {selector}")
                username_filled = True
                break
            except Exception as e:
                log(f"Username selector {selector} failed: {e}")
                continue
        
        if not username_filled:
            raise Exception("Username field not found")
        
        random_wait(1, 2)
        
        password_selectors = [
            'input[type="password"]', 'input[name="password"]', '#password'
        ]
        
        password_filled = False
        for selector in password_selectors:
            try:
                page.fill(selector, TURNITIN_PASSWORD)
                log(f"Password filled using selector: {selector}")
                password_filled = True
                break
            except Exception as e:
                log(f"Password selector {selector} failed: {e}")
                continue
        
        if not password_filled:
            raise Exception("Password field not found")
        
        random_wait(1, 2)
        
        # Submit form
        submit_selectors = [
            'input[type="submit"]', 'button[type="submit"]', 
            'button:has-text("Log in")', 'button:has-text("Login")',
            'button:has-text("Sign in")', '.login-btn', '.btn-primary'
        ]
        
        login_submitted = False
        for selector in submit_selectors:
            try:
                page.click(selector)
                log(f"Login submitted using selector: {selector}")
                login_submitted = True
                break
            except Exception as e:
                log(f"Submit selector {selector} failed: {e}")
                continue
        
        if not login_submitted:
            raise Exception("Submit button not found")
        
        # Wait for login to complete
        log("Waiting for login to complete...")
        page.wait_for_timeout(12000)
        
        # Enhanced login verification
        current_url = page.url
        page_title = page.title()
        
        log(f"After login - URL: {current_url}, Title: {page_title}")
        
        # Multiple verification approaches
        login_success = False
        
        # Method 1: Check URL
        if ("dashboard" in current_url.lower() or 
            "my-files" in current_url.lower() or 
            "profile" in current_url.lower() or
            "upload" in current_url.lower()):
            login_success = True
            log("Login verified by URL redirect")
        
        # Method 2: Check for authenticated elements
        if not login_success:
            try:
                page.wait_for_selector(
                    '[href*="logout"], .user-menu, [href*="my-files"], .username, [href*="upload"]', 
                    timeout=10000
                )
                login_success = True
                log("Login verified by authenticated elements")
            except:
                pass
        
        # Method 3: Check if NOT on login page
        if not login_success:
            if "login" not in current_url.lower():
                login_success = True
                log("Login verified by absence of login page")
        
        if login_success:
            log("Fresh login successful")
            return True
        else:
            log("Login verification failed")
            return False
            
    except Exception as e:
        log(f"Login error: {e}")
        return False

def upload_document(page, file_path, unique_title):
    """Upload document to Turnitin"""
    try:
        log("Navigating to upload page...")
        page.goto(f"{TURNITIN_BASE_URL}/upload/", timeout=60000)
        page.wait_for_selector('input[type="file"], #file', timeout=20000)
        
        # Upload file
        file_input_selectors = [
            'input[type="file"]', '#file', 'input[name="file"]'
        ]
        
        for selector in file_input_selectors:
            try:
                page.set_input_files(selector, file_path)
                log("File uploaded successfully")
                break
            except:
                continue
        else:
            raise Exception("File input not found")
        
        random_wait(2, 3)
        
        # Fill title
        title_selectors = ['#title', 'input[name="title"]']
        for selector in title_selectors:
            try:
                page.fill(selector, unique_title)
                log(f"Title set: {unique_title}")
                break
            except:
                continue
        
        # Fill author fields
        author_fields = [
            ('#author_first', 'Test'),
            ('#author_last', 'User'),
            ('input[name="author_first"]', 'Test'),
            ('input[name="author_last"]', 'User')
        ]
        
        for selector, value in author_fields:
            try:
                page.fill(selector, value)
            except:
                continue
        
        # Configure filters
        try:
            filter_checkboxes = [
                'input[name="exclude_bibliography"]',
                'input[name="exclude_quoted_text"]',
                'input[name="exclude_cited_text"]'
            ]
            
            for checkbox in filter_checkboxes:
                try:
                    if not page.is_checked(checkbox):
                        page.check(checkbox)
                except:
                    continue
        except:
            pass
        
        # Submit
        submit_selectors = [
            'button[type="submit"]', 'input[type="submit"]',
            'button:has-text("Submit")', 'button:has-text("Upload")'
        ]
        
        for selector in submit_selectors:
            try:
                page.click(selector)
                log("Upload submitted successfully")
                break
            except:
                continue
        else:
            raise Exception("Submit button not found")
        
        page.wait_for_timeout(30000)
        
        # Extract file ID if available
        current_url = page.url
        file_id_match = re.search(r'/file/(\d+)', current_url)
        file_id = file_id_match.group(1) if file_id_match else None
        
        log(f"Upload complete - File ID: {file_id}")
        return file_id
        
    except Exception as e:
        log(f"Upload failed: {e}")
        raise

def monitor_processing(page, unique_title, max_wait_minutes=30):
    """Monitor file processing with improved score extraction"""
    start_time = time.time()
    max_wait_seconds = max_wait_minutes * 60
    
    log(f"Monitoring processing for: {unique_title}")
    
    time.sleep(15)  # Initial wait
    
    while time.time() - start_time < max_wait_seconds:
        try:
            page.goto(f"{TURNITIN_BASE_URL}/my-files/", timeout=30000)
            page.wait_for_load_state('networkidle', timeout=10000)
            
            # Wait for table to load
            page.wait_for_selector('table tbody tr', timeout=15000)
            
            rows = page.locator('tbody tr').all()
            
            for row in rows:
                try:
                    # Get the title cell (first column)
                    title_cell = row.locator('td').first
                    title_text = title_cell.text_content()
                    
                    if unique_title in title_text:
                        log(f"Found file: {unique_title}")
                        
                        # Get all cells in the row
                        cells = row.locator('td').all()
                        
                        if len(cells) >= 6:  # Title, Author, Similarity, AI, Date, Actions
                            similarity_cell = cells[2]  # 3rd column
                            ai_cell = cells[3]  # 4th column
                            
                            similarity_text = similarity_cell.text_content()
                            ai_text = ai_cell.text_content()
                            
                            log(f"Similarity cell: {similarity_text}")
                            log(f"AI cell: {ai_text}")
                            
                            # Check if still processing
                            if ('Processing' in similarity_text or 'processing' in similarity_text.lower() or
                                'Processing' in ai_text or 'processing' in ai_text.lower()):
                                log("Still processing...")
                                break
                            
                            # Extract plagiarism score
                            plagiarism_score = None
                            plagiarism_match = re.search(r'(\d+)%', similarity_text)
                            if plagiarism_match:
                                plagiarism_score = int(plagiarism_match.group(1))
                            
                            # Extract AI score (handle asterisk for warnings)
                            ai_score = None
                            ai_error = None
                            
                            if '--' in ai_text or 'not available' in ai_text.lower():
                                ai_error = "AI analysis not available"
                            else:
                                # Look for patterns like "10*%" or "45%"
                                ai_match = re.search(r'(\d+)\*?%', ai_text)
                                if ai_match:
                                    ai_score = int(ai_match.group(1))
                                    if '*' in ai_text:
                                        ai_error = "AI analysis completed with warnings"
                            
                            # Check if we have enough data to consider processing complete
                            if plagiarism_score is not None:
                                log(f"Processing complete - Plagiarism: {plagiarism_score}%, AI: {ai_score}%")
                                return {
                                    'completed': True,
                                    'plagiarism_score': plagiarism_score,
                                    'ai_score': ai_score,
                                    'ai_error': ai_error
                                }
                            else:
                                log("Scores not ready yet...")
                                break
                        else:
                            log(f"Row has {len(cells)} cells, expected at least 6")
                            break
                            
                except Exception as row_error:
                    log(f"Error processing row: {row_error}")
                    continue
            
            time.sleep(10)
            
        except Exception as check_error:
            log(f"Monitoring error: {check_error}")
            time.sleep(10)
    
    log("Monitoring timeout reached")
    return {'completed': False}

def download_reports(page, unique_title, chat_id, timestamp):
    """Download similarity and AI reports with comprehensive button detection"""
    try:
        log("Starting report download process...")
        
        downloads_dir = "downloads"
        os.makedirs(downloads_dir, exist_ok=True)
        
        # Fresh page load with extra wait
        log("Loading my-files page for downloads...")
        page.goto(f"{TURNITIN_BASE_URL}/my-files/", timeout=30000)
        page.wait_for_load_state('domcontentloaded', timeout=15000)
        page.wait_for_load_state('networkidle', timeout=15000)
        
        # Extra wait for JavaScript and dynamic content
        log("Waiting for page content to fully load...")
        time.sleep(5)
        
        # Wait for table
        page.wait_for_selector('table tbody tr', timeout=20000)
        
        rows = page.locator('tbody tr').all()
        log(f"Found {len(rows)} rows in files table")
        
        sim_filename = None
        ai_filename = None
        target_row = None
        
        # Find our file row
        for i, row in enumerate(rows):
            try:
                title_cell = row.locator('td').first
                title_text = title_cell.text_content()
                
                if unique_title in title_text:
                    log(f"Found target file row {i}: {unique_title}")
                    target_row = row
                    break
                    
            except Exception as row_error:
                log(f"Error checking row {i}: {row_error}")
                continue
        
        if not target_row:
            log("Target file row not found")
            return None, None
        
        # Get all cells from target row
        cells = target_row.locator('td').all()
        log(f"Target row has {len(cells)} cells")
        
        if len(cells) >= 4:
            similarity_cell = cells[2]  # 3rd column - Similarity
            ai_cell = cells[3]         # 4th column - AI
            
            log("Analyzing similarity cell for download buttons...")
            
            # Method 1: Look for specific download button classes
            sim_buttons = similarity_cell.locator('button.download-similarity').all()
            log(f"Method 1 - Found {len(sim_buttons)} .download-similarity buttons")
            
            # Method 2: Look for buttons with download icons
            if not sim_buttons:
                sim_buttons = similarity_cell.locator('button').filter(has_text=re.compile(r'fa-download', re.I)).all()
                log(f"Method 2 - Found {len(sim_buttons)} buttons with fa-download")
            
            # Method 3: Look for any buttons in similarity cell
            if not sim_buttons:
                sim_buttons = similarity_cell.locator('button').all()
                log(f"Method 3 - Found {len(sim_buttons)} total buttons in similarity cell")
            
            # Method 4: Look for buttons with data-file-oid
            if not sim_buttons:
                sim_buttons = similarity_cell.locator('button[data-file-oid]').all()
                log(f"Method 4 - Found {len(sim_buttons)} buttons with data-file-oid")
            
            # Try to download similarity report
            if sim_buttons and len(sim_buttons) > 0:
                try:
                    log("Attempting similarity report download...")
                    
                    # Scroll into view and wait
                    sim_buttons[0].scroll_into_view_if_needed()
                    time.sleep(2)
                    
                    # Ensure button is visible and enabled
                    sim_buttons[0].wait_for(state='visible', timeout=10000)
                    
                    with page.expect_download(timeout=60000) as download_info:
                        sim_buttons[0].click()
                        log("Similarity download button clicked")
                    
                    download = download_info.value
                    sim_filename = os.path.join(downloads_dir, f"{chat_id}_{timestamp}_similarity.pdf")
                    download.save_as(sim_filename)
                    log(f"Similarity report saved: {sim_filename}")
                    
                    time.sleep(3)  # Wait between downloads
                    
                except Exception as sim_error:
                    log(f"Similarity download failed: {sim_error}")
            else:
                log("No similarity download buttons found")
            
            log("Analyzing AI cell for download buttons...")
            
            # Same methods for AI cell
            ai_buttons = ai_cell.locator('button.download-ai').all()
            log(f"Method 1 - Found {len(ai_buttons)} .download-ai buttons")
            
            if not ai_buttons:
                ai_buttons = ai_cell.locator('button').filter(has_text=re.compile(r'fa-download', re.I)).all()
                log(f"Method 2 - Found {len(ai_buttons)} AI buttons with fa-download")
            
            if not ai_buttons:
                ai_buttons = ai_cell.locator('button').all()
                log(f"Method 3 - Found {len(ai_buttons)} total buttons in AI cell")
            
            if not ai_buttons:
                ai_buttons = ai_cell.locator('button[data-file-oid]').all()
                log(f"Method 4 - Found {len(ai_buttons)} AI buttons with data-file-oid")
            
            # Try to download AI report
            if ai_buttons and len(ai_buttons) > 0:
                try:
                    log("Attempting AI report download...")
                    
                    # Scroll into view and wait
                    ai_buttons[0].scroll_into_view_if_needed()
                    time.sleep(2)
                    
                    # Ensure button is visible and enabled
                    ai_buttons[0].wait_for(state='visible', timeout=10000)
                    
                    with page.expect_download(timeout=60000) as download_info:
                        ai_buttons[0].click()
                        log("AI download button clicked")
                    
                    download = download_info.value
                    ai_filename = os.path.join(downloads_dir, f"{chat_id}_{timestamp}_ai.pdf")
                    download.save_as(ai_filename)
                    log(f"AI report saved: {ai_filename}")
                    
                except Exception as ai_error:
                    log(f"AI download failed: {ai_error}")
            else:
                log("No AI download buttons found")
            
            # If no buttons found, debug the HTML structure
            if not sim_buttons and not ai_buttons:
                log("DEBUGGING: No download buttons detected, examining HTML structure")
                
                try:
                    sim_html = similarity_cell.inner_html()
                    ai_html = ai_cell.inner_html()
                    log(f"Similarity cell HTML (first 200 chars): {sim_html[:200]}...")
                    log(f"AI cell HTML (first 200 chars): {ai_html[:200]}...")
                    
                    # Check for any download-related elements on entire page
                    all_download_elements = page.locator('button, a').filter(has_text=re.compile(r'download|report', re.I)).all()
                    log(f"Total download-related elements on page: {len(all_download_elements)}")
                    
                    # Check for buttons with specific classes
                    sim_class_buttons = page.locator('button.download-similarity').all()
                    ai_class_buttons = page.locator('button.download-ai').all()
                    log(f"Page-wide .download-similarity buttons: {len(sim_class_buttons)}")
                    log(f"Page-wide .download-ai buttons: {len(ai_class_buttons)}")
                    
                except Exception as debug_error:
                    log(f"Debug error: {debug_error}")
        
        return sim_filename, ai_filename
        
    except Exception as e:
        log(f"Download process failed: {e}")
        return None, None

def cleanup_files(*file_paths):
    """Clean up temporary files"""
    for file_path in file_paths:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                log(f"Cleaned up: {file_path}")
        except Exception as e:
            log(f"Cleanup error for {file_path}: {e}")

def cleanup_browser():
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

def process_turnitin(file_path: str, chat_id: int, bot):
    """Main Turnitin processing function with enhanced download capabilities"""
    timestamp = int(time.time())
    processing_messages = []
    
    try:
        # Initial message
        msg = bot.send_message(chat_id, "🚀 Starting Turnitin analysis...")
        processing_messages.append(msg.message_id)
        
        # Verify file
        if not os.path.exists(file_path):
            raise Exception(f"File not found: {file_path}")
        
        log(f"Processing file for user {chat_id}: {file_path} ({os.path.getsize(file_path)} bytes)")
        
        # Get browser session (will try cookies first, then fresh login)
        page = get_browser_session()
        
        # Create unique title
        original_filename = os.path.basename(file_path).split('.')[0]
        unique_title = create_unique_title(chat_id, timestamp, original_filename)
        
        # Upload document
        msg = bot.send_message(chat_id, "📤 Uploading document...")
        processing_messages.append(msg.message_id)
        
        file_id = upload_document(page, file_path, unique_title)
        
        # Save cookies after successful upload
        save_cookies()
        
        # Monitor processing
        msg = bot.send_message(chat_id, "⏳ Document uploaded, analyzing...")
        processing_messages.append(msg.message_id)
        
        result = monitor_processing(page, unique_title)
        
        if not result['completed']:
            # Clean up all messages
            for msg_id in processing_messages:
                try:
                    bot.delete_message(chat_id, msg_id)
                except:
                    pass
            
            bot.send_message(chat_id, 
                "⚠️ Processing is taking longer than expected.\n\n"
                "Your document was submitted successfully. "
                "Please wait a few minutes and submit another document to check if results are ready."
            )
            return
        
        # Update processing message - analysis complete, downloading reports
        try:
            # Delete previous messages except the last one
            for msg_id in processing_messages[:-1]:
                try:
                    bot.delete_message(chat_id, msg_id)
                except:
                    pass
            
            # Update the last message
            bot.edit_message_text(
                "📊 Analysis complete! Downloading reports...",
                chat_id,
                processing_messages[-1]
            )
        except:
            # If editing fails, send new message
            msg = bot.send_message(chat_id, "📊 Analysis complete! Downloading reports...")
            processing_messages = [msg.message_id]
        
        # Download reports with multiple attempts
        max_download_attempts = 3
        download_attempt = 0
        sim_filename = None
        ai_filename = None
        
        while download_attempt < max_download_attempts and not (sim_filename and ai_filename):
            download_attempt += 1
            log(f"Download attempt {download_attempt}/{max_download_attempts}")
            
            if download_attempt > 1:
                # Wait longer before retry and refresh page
                log("Waiting before retry...")
                time.sleep(15)
                
                page.reload()
                page.wait_for_load_state('networkidle', timeout=15000)
            else:
                # Even on first attempt, wait for buttons to be ready
                log("Waiting for download buttons to be ready...")
                time.sleep(8)
            
            sim_filename, ai_filename = download_reports(page, unique_title, chat_id, timestamp)
            
            if sim_filename or ai_filename:
                break
        
        # Save cookies after successful operation
        save_cookies()
        
        # Clean up all processing messages
        for msg_id in processing_messages:
            try:
                bot.delete_message(chat_id, msg_id)
            except:
                pass
        
        # Send final completion message
        scores_text = ""
        if result.get('plagiarism_score') is not None:
            scores_text += f"📊 Similarity: {result['plagiarism_score']}%\n"
        if result.get('ai_score') is not None:
            ai_score_text = str(result['ai_score'])
            if result.get('ai_error') and 'warnings' in str(result.get('ai_error')):
                ai_score_text += "*"
            scores_text += f"🤖 AI Detection: {ai_score_text}%\n"
        if result.get('ai_error'):
            scores_text += f"ℹ️ Note: {result['ai_error']}\n"
        
        completion_msg = bot.send_message(chat_id, f"✅ Analysis complete!\n\n{scores_text}")
        
        # Send reports if available
        reports_sent = 0
        if sim_filename and os.path.exists(sim_filename):
            try:
                with open(sim_filename, "rb") as f:
                    bot.send_document(chat_id, f, caption="📄 Similarity Report")
                reports_sent += 1
                log("Similarity report sent successfully")
            except Exception as e:
                log(f"Error sending similarity report: {e}")
        
        if ai_filename and os.path.exists(ai_filename):
            try:
                with open(ai_filename, "rb") as f:
                    bot.send_document(chat_id, f, caption="🤖 AI Detection Report")
                reports_sent += 1
                log("AI report sent successfully")
            except Exception as e:
                log(f"Error sending AI report: {e}")
        
        # If no reports were sent, update the completion message
        if reports_sent == 0:
            try:
                bot.edit_message_text(
                    f"⚠️ Analysis complete but reports not available for download yet!\n\n{scores_text}\n"
                    "Reports may take a few more minutes to generate. Please try submitting again in 5-10 minutes.",
                    chat_id,
                    completion_msg.message_id
                )
            except:
                bot.send_message(chat_id, 
                    "⚠️ Reports not available for download yet. Please try again in 5-10 minutes.")
        elif reports_sent == 1:
            # Update message to indicate partial success
            try:
                bot.edit_message_text(
                    f"✅ Analysis complete! (1 of 2 reports available)\n\n{scores_text}",
                    chat_id,
                    completion_msg.message_id
                )
            except:
                pass
        
        # Cleanup files
        cleanup_files(file_path, sim_filename, ai_filename)
        log(f"Processing completed successfully for user {chat_id}")
        
    except Exception as e:
        # Clean up all processing messages
        for msg_id in processing_messages:
            try:
                bot.delete_message(chat_id, msg_id)
            except:
                pass
        
        error_msg = f"Processing failed: {str(e)}"
        bot.send_message(chat_id, f"❌ {error_msg}\n\nPlease try again or contact support.")
        log(f"ERROR for user {chat_id}: {error_msg}")
        
        # Cleanup files
        cleanup_files(file_path)
        
        # Reset browser on critical errors
        if "browser" in str(e).lower() or "page" in str(e).lower():
            log("Critical browser error detected, resetting session")
            cleanup_browser()

def shutdown_browser_session():
    """Shutdown browser session"""
    log("Shutting down browser session...")
    cleanup_browser()
    log("Browser session closed")