import os
import json
import threading
from datetime import datetime
from dotenv import load_dotenv

# Import our modular components
from turnitin_auth import (
    log, 
    create_browser, 
    create_browser_context, 
    create_page, 
    check_session_validity, 
    perform_login, 
    navigate_to_quick_submit,
    save_cookies
)
from turnitin_submission import submit_document
from turnitin_reports import (
    find_submission_with_retry, 
    download_reports_with_retry, 
    send_reports_to_user, 
    cleanup_files
)

# Load environment variables
load_dotenv()
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))

# Global storage for browser sessions awaiting retry
pending_retries = {}
retry_lock = threading.Lock()

def save_retry_session(chat_id, browser_data):
    """Save browser session for retry"""
    with retry_lock:
        pending_retries[str(chat_id)] = browser_data
        save_pending_retries()

def load_retry_session(chat_id):
    """Load browser session for retry"""
    with retry_lock:
        return pending_retries.get(str(chat_id))

def remove_retry_session(chat_id):
    """Remove browser session after successful retry"""
    with retry_lock:
        if str(chat_id) in pending_retries:
            del pending_retries[str(chat_id)]
            save_pending_retries()

def save_pending_retries():
    """Save pending retries to file"""
    try:
        # Don't save browser objects, just metadata
        retry_metadata = {}
        for chat_id, data in pending_retries.items():
            retry_metadata[chat_id] = {
                'timestamp': data.get('timestamp'),
                'submission_title': data.get('submission_title'),
                'file_path': data.get('file_path'),
                'status': data.get('status', 'pending_retry')
            }
        
        with open("pending_retries_queue.json", "w") as f:
            json.dump(retry_metadata, f, indent=2)
        log("Saved retry metadata to file")
    except Exception as e:
        log(f"Error saving retry metadata: {e}")

def load_pending_retries():
    """Load pending retries from file"""
    global pending_retries
    try:
        if os.path.exists("pending_retries_queue.json"):
            with open("pending_retries_queue.json", "r") as f:
                retry_metadata = json.load(f)
            log(f"Loaded {len(retry_metadata)} pending retry sessions")
            # Note: Browser objects won't be restored, will need fresh login for retries
        else:
            log("No pending retry file found")
    except Exception as e:
        log(f"Error loading retry metadata: {e}")

def process_turnitin(file_path: str, chat_id: int, bot):
    """
    Main Turnitin processing function that coordinates all the steps:
      - Log in using new system
      - Navigate to Quick Submit  
      - Configure submission settings
      - Upload the document
      - Wait for processing, then download reports
      - Send downloaded files to the Telegram user
      - Clean up files afterwards
      - Delete processing messages to keep chat clean
      - Handle retries with 5-minute countdown if files are missing
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    processing_messages = []  # Track messages to delete later
    p = None
    browser = None
    context = None
    page = None
    page1 = None
    
    try:
        # Send initial message and track it
        msg = bot.send_message(chat_id, "🚀 Starting Turnitin process...")
        processing_messages.append(msg.message_id)
        log("Starting Turnitin process...")

        # Verify file exists before proceeding
        if not os.path.exists(file_path):
            raise Exception(f"File not found: {file_path}")
        
        log(f"File verified: {file_path} (Size: {os.path.getsize(file_path)} bytes)")

        # Create browser instance
        log("Creating browser instance...")
        p, browser = create_browser()
        
        # Create browser context with cookies
        log("Creating browser context...")
        context = create_browser_context(browser)
        
        # Create and test page
        log("Creating page...")
        page = create_page(context)
        
        # Check if session is valid
        log("Checking session validity...")
        session_valid = check_session_validity(page)
        
        # Perform login if session is not valid
        if not session_valid:
            log("Performing fresh login...")
            page = perform_login(page, context)
        else:
            # Session is valid, ensure we're on the right page
            try:
                current_url = page.url
                log(f"Session valid, current URL: {current_url}")
                if "login" in current_url:
                    log("Valid session but on login page, navigating to home...")
                    page.goto("https://www.turnitin.com/home/", timeout=60000)
                    page.wait_for_timeout(2000)
            except Exception as e:
                log(f"Error navigating from valid session: {e}")

        # Always try to update cookies
        save_cookies(context)

        # Navigate to Quick Submit using the corrected function
        log("Navigating to Quick Submit...")
        page = navigate_to_quick_submit(page)

        # Submit the document
        log("Starting document submission process...")
        actual_submission_title = submit_document(page, file_path, chat_id, timestamp, bot, processing_messages)

        # Save browser session for potential retry
        browser_data = {
            'p': p,
            'browser': browser,
            'context': context,
            'page': page,
            'timestamp': timestamp,
            'submission_title': actual_submission_title,
            'file_path': file_path,
            'processing_messages': processing_messages,
            'status': 'finding_submission'
        }
        save_retry_session(chat_id, browser_data)

        # Find the submitted document with retry mechanism
        log("Finding submitted document...")
        page1 = find_submission_with_retry(page, actual_submission_title, chat_id, bot, processing_messages)
        
        # If page1 is None, it means retry option was shown, don't close browser
        if page1 is None:
            log("Retry option shown, keeping browser open for user retry")
            return  # Exit without closing browser
        
        # Update browser data with page1
        browser_data['page1'] = page1
        browser_data['status'] = 'downloading_reports'
        save_retry_session(chat_id, browser_data)

        # Download reports with retry mechanism
        log("Downloading reports...")
        sim_filename, ai_filename = download_reports_with_retry(page1, chat_id, timestamp, bot, processing_messages)
        
        # If both filenames are None, it means retry option was shown
        if sim_filename is None and ai_filename is None:
            log("Download retry option shown, keeping browser open for user retry")
            return  # Exit without closing browser

        # Send reports to user
        log("Sending reports to user...")
        send_reports_to_user(chat_id, sim_filename, ai_filename, bot, processing_messages)

        log("Turnitin process complete and reports sent.")

        # Clean up files
        cleanup_files(sim_filename, ai_filename, file_path)
        
        # Remove from retry queue since successful
        remove_retry_session(chat_id)

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
        
        # Remove from retry queue on error
        remove_retry_session(chat_id)
    
    finally:
        # Only clean up browser resources if not waiting for retry
        if str(chat_id) not in pending_retries:
            cleanup_browser_resources(p, browser, context, page, page1)

def cleanup_browser_resources(p, browser, context, page, page1):
    """Clean up browser resources"""
    try:
        if page1:
            page1.close()
            log("Closed submission page")
    except Exception as page1_close_error:
        log(f"Error closing submission page: {page1_close_error}")
    
    try:
        if page:
            page.close()
            log("Closed main page")
    except Exception as page_close_error:
        log(f"Error closing main page: {page_close_error}")
    
    try:
        if context:
            context.close()
            log("Closed browser context")
    except Exception as context_close_error:
        log(f"Error closing browser context: {context_close_error}")
    
    try:
        if browser:
            browser.close()
            log("Closed browser")
    except Exception as browser_close_error:
        log(f"Error closing browser: {browser_close_error}")
    
    try:
        if p:
            p.stop()
            log("Stopped Playwright")
    except Exception as p_close_error:
        log(f"Error stopping Playwright: {p_close_error}")

def handle_retry_submission(chat_id, submission_title, bot):
    """Handle retry for finding submission"""
    log(f"Handling retry for submission: {submission_title}")
    
    # Get stored browser session
    browser_data = load_retry_session(chat_id)
    if not browser_data:
        bot.send_message(chat_id, "❌ Session expired. Please submit your document again.")
        return
    
    processing_messages = []
    
    try:
        # Extract browser objects
        page = browser_data.get('page')
        timestamp = browser_data.get('timestamp')
        
        if not page:
            bot.send_message(chat_id, "❌ Browser session lost. Please submit your document again.")
            remove_retry_session(chat_id)
            return
        
        msg = bot.send_message(chat_id, "🔄 Retrying to find your submission...")
        processing_messages.append(msg.message_id)
        
        # Try to find submission again
        from turnitin_reports import find_submission
        
        # Navigate to Quick Submit again
        page = navigate_to_quick_submit(page)
        
        # Try to find the submission
        page1 = find_submission(page, submission_title, chat_id, bot, processing_messages)
        
        if page1:
            log("Retry successful - found submission")
            
            # Update browser data
            browser_data['page1'] = page1
            browser_data['status'] = 'downloading_reports'
            save_retry_session(chat_id, browser_data)
            
            # Download reports
            sim_filename, ai_filename = download_reports_with_retry(page1, chat_id, timestamp, bot, processing_messages)
            
            # If download successful, send reports
            if sim_filename or ai_filename:
                send_reports_to_user(chat_id, sim_filename, ai_filename, bot, processing_messages)
                
                # Clean up files
                file_path = browser_data.get('file_path')
                cleanup_files(sim_filename, ai_filename, file_path)
                
                # Clean up browser and remove from retry queue
                p = browser_data.get('p')
                browser = browser_data.get('browser')
                context = browser_data.get('context')
                cleanup_browser_resources(p, browser, context, page, page1)
                remove_retry_session(chat_id)
                
                log("Retry process completed successfully")
            else:
                log("Download retry needed again")
        else:
            # Still couldn't find, show another retry option
            log("Retry failed again, showing another retry option")
            bot.send_message(chat_id, "❌ Still couldn't find your submission. Please wait longer and try again, or submit a new document.")
            
    except Exception as e:
        log(f"Error during retry: {e}")
        bot.send_message(chat_id, f"❌ Retry failed: {e}")
        
        # Clean up on retry failure
        if browser_data:
            p = browser_data.get('p')
            browser = browser_data.get('browser')
            context = browser_data.get('context')
            page = browser_data.get('page')
            page1 = browser_data.get('page1')
            cleanup_browser_resources(p, browser, context, page, page1)
        
        remove_retry_session(chat_id)
    
    finally:
        # Clean up processing messages
        for message_id in processing_messages:
            try:
                bot.delete_message(chat_id, message_id)
            except:
                pass

def handle_retry_download(chat_id, timestamp, bot):
    """Handle retry for downloading reports"""
    log(f"Handling download retry for user: {chat_id}")
    
    # Get stored browser session
    browser_data = load_retry_session(chat_id)
    if not browser_data:
        bot.send_message(chat_id, "❌ Session expired. Please submit your document again.")
        return
    
    processing_messages = []
    
    try:
        # Extract browser objects
        page1 = browser_data.get('page1')
        
        if not page1:
            bot.send_message(chat_id, "❌ Browser session lost. Please submit your document again.")
            remove_retry_session(chat_id)
            return
        
        msg = bot.send_message(chat_id, "🔄 Retrying to download reports...")
        processing_messages.append(msg.message_id)
        
        # Try to download reports again
        from turnitin_reports import download_similarity_report, download_ai_report
        
        downloads_dir = "downloads"
        os.makedirs(downloads_dir, exist_ok=True)
        
        sim_filename = download_similarity_report(page1, chat_id, timestamp, downloads_dir)
        ai_filename = download_ai_report(page1, chat_id, timestamp, downloads_dir)
        
        # Check if download was successful
        if sim_filename and os.path.exists(sim_filename):
            log("Download retry successful")
            
            # Send reports to user
            send_reports_to_user(chat_id, sim_filename, ai_filename, bot, processing_messages)
            
            # Clean up files
            file_path = browser_data.get('file_path')
            cleanup_files(sim_filename, ai_filename, file_path)
            
            # Clean up browser and remove from retry queue
            p = browser_data.get('p')
            browser = browser_data.get('browser')
            context = browser_data.get('context')
            page = browser_data.get('page')
            cleanup_browser_resources(p, browser, context, page, page1)
            remove_retry_session(chat_id)
            
            log("Download retry process completed successfully")
        else:
            # Still couldn't download
            bot.send_message(chat_id, "❌ Still couldn't download reports. The document might not be ready yet. Please try submitting again later.")
            
            # Clean up browser and remove from retry queue
            p = browser_data.get('p')
            browser = browser_data.get('browser')
            context = browser_data.get('context')
            page = browser_data.get('page')
            cleanup_browser_resources(p, browser, context, page, page1)
            remove_retry_session(chat_id)
            
    except Exception as e:
        log(f"Error during download retry: {e}")
        bot.send_message(chat_id, f"❌ Download retry failed: {e}")
        
        # Clean up on retry failure
        if browser_data:
            p = browser_data.get('p')
            browser = browser_data.get('browser')
            context = browser_data.get('context')
            page = browser_data.get('page')
            page1 = browser_data.get('page1')
            cleanup_browser_resources(p, browser, context, page, page1)
        
        remove_retry_session(chat_id)
    
    finally:
        # Clean up processing messages
        for message_id in processing_messages:
            try:
                bot.delete_message(chat_id, message_id)
            except:
                pass

# Initialize on module import
load_pending_retries()