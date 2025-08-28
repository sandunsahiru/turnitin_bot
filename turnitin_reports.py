import os
import time
import threading
from datetime import datetime, timedelta

def log(message: str):
    """Log a message with a timestamp to the terminal."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def random_wait(min_seconds=2, max_seconds=4):
    """Wait for a random amount of time to appear more human-like"""
    import random
    wait_time = random.uniform(min_seconds, max_seconds)
    time.sleep(wait_time)

from turnitin_auth import navigate_to_quick_submit

def find_submission_with_retry(page, submission_title, chat_id, bot, processing_messages):
    """Find the submitted document - Optimized version"""
    
    # Navigate to Quick Submit using global session
    navigate_to_quick_submit()  # No arguments needed
    
    # Get the session page 
    from turnitin_auth import browser_session
    page = browser_session['page']
    
    page.wait_for_load_state('networkidle', timeout=20000)
    random_wait(2, 3)

    log(f"Looking for submission: {submission_title}")
    
    # Use only the working method from logs (Method 1)
    try:
        page.wait_for_selector('span.or_full_version a', timeout=15000)
        percentage_links = page.locator('span.or_full_version a').all()
        
        if percentage_links:
            log(f"Found {len(percentage_links)} percentage links")
            with page.expect_popup() as page1_info:
                percentage_links[0].click()  # Click the first percentage link
            page1 = page1_info.value
            random_wait(2, 3)
            log("Found submission using percentage link")
            return page1
        else:
            raise Exception("No percentage links found")
            
    except Exception as e:
        log(f"Could not find submission: {e}")
        show_retry_option(chat_id, submission_title, bot, processing_messages)
        return None

def download_reports_with_retry(page1, chat_id, timestamp, bot, processing_messages):
    """Download reports - Optimized version"""
    
    # Ensure downloads folder exists
    downloads_dir = "downloads"
    os.makedirs(downloads_dir, exist_ok=True)

    # Wait for page to load with longer timeout
    try:
        page1.wait_for_load_state('networkidle', timeout=60000)  # Increased from 30 to 60 seconds
        msg = bot.send_message(chat_id, "📊 Processing complete. Downloading reports...")
        processing_messages.append(msg.message_id)
    except Exception as load_error:
        log(f"Page load timeout, continuing anyway: {load_error}")
        msg = bot.send_message(chat_id, "📊 Attempting to download reports...")
        processing_messages.append(msg.message_id)

    # Wait for reports to be ready
    log("Waiting 60 seconds for reports...")
    page1.wait_for_timeout(60000)

    # Check if reports are available
    if not check_reports_availability(page1):
        log("Reports not ready")
        show_retry_option(chat_id, "download_retry", bot, processing_messages)
        return None, None

    # Download reports using only working methods
    sim_filename = download_similarity_report(page1, chat_id, timestamp, downloads_dir)
    ai_filename = download_ai_report(page1, chat_id, timestamp, downloads_dir)
    
    if sim_filename or ai_filename:
        log(f"Reports downloaded - Similarity: {bool(sim_filename)}, AI: {bool(ai_filename)}")
        return sim_filename, ai_filename
    else:
        show_retry_option(chat_id, "download_retry", bot, processing_messages)
        return None, None

def check_reports_availability(page1):
    """Check if reports are available - Simplified"""
    try:
        current_url = page1.url
        log(f"Checking reports on: {current_url}")
        
        # Use only working selector from logs
        page1.wait_for_selector('tii-sws-download-btn-mfe', timeout=10000)
        button = page1.locator('tii-sws-download-btn-mfe')
        
        if button.count() > 0 and button.first.is_visible():
            log("Download button found - reports available")
            return True
        else:
            log("Download button not visible")
            return False
            
    except Exception as e:
        log(f"Reports not available: {e}")
        return False

def download_similarity_report(page1, chat_id, timestamp, downloads_dir):
    """Download similarity report - Optimized version"""
    log("Downloading Similarity Report...")
    
    try:
        # Click download button (use working method)
        page1.click('tii-sws-download-btn-mfe')
        random_wait(1, 2)
        
        # Click Similarity Report option
        page1.wait_for_selector('button:has-text("Similarity Report")', timeout=10000)
        with page1.expect_download(timeout=60000) as download_info:
            page1.get_by_role("button", name="Similarity Report").click()
        
        download_sim = download_info.value
        sim_filename = os.path.join(downloads_dir, f"{chat_id}_{timestamp}_similarity.pdf")
        download_sim.save_as(sim_filename)
        log(f"Saved Similarity Report as {sim_filename}")
        return sim_filename
        
    except Exception as e:
        log(f"Error downloading Similarity Report: {e}")
        return None

def download_ai_report(page1, chat_id, timestamp, downloads_dir):
    """Download AI report - Optimized version"""
    
    try:
        random_wait(1, 2)
        
        # Click download button again
        page1.click('tii-sws-download-btn-mfe')
        random_wait(1, 2)
        
        # Click AI Writing Report option
        page1.wait_for_selector('button:has-text("AI Writing Report")', timeout=10000)
        with page1.expect_download(timeout=60000) as download_info:
            page1.get_by_role("button", name="AI Writing Report").click()
        
        download_ai = download_info.value
        ai_filename = os.path.join(downloads_dir, f"{chat_id}_{timestamp}_ai.pdf")
        download_ai.save_as(ai_filename)
        log(f"Saved AI Writing Report as {ai_filename}")
        return ai_filename
        
    except Exception as e:
        log(f"Could not download AI Writing Report: {e}")
        return None

def show_retry_option(chat_id, retry_type, bot, processing_messages):
    """Show simple retry option without complex countdown"""
    
    # Clean up processing messages
    for message_id in processing_messages:
        try:
            bot.delete_message(chat_id, message_id)
        except:
            pass
    
    if retry_type == "download_retry":
        message = ("⚠️ <b>Reports Not Ready Yet</b>\n\n"
                  "Your document was submitted but reports are still being generated. "
                  "Please wait a few minutes and try submitting again.\n\n"
                  "💡 <b>Tip:</b> Larger documents take longer to process.")
    else:
        message = ("⚠️ <b>Document Not Found</b>\n\n"
                  "Your document was submitted but hasn't appeared in the list yet. "
                  "Please wait a few minutes and try submitting again.\n\n"
                  "💡 <b>Tip:</b> Processing can take 2-5 minutes.")
    
    bot.send_message(chat_id, message)

def send_reports_to_user(chat_id, sim_filename, ai_filename, bot, processing_messages):
    """Send downloaded reports to Telegram user"""
    
    # Clean up processing messages
    for message_id in processing_messages:
        try:
            bot.delete_message(chat_id, message_id)
        except:
            pass

    # Send available reports
    if sim_filename and os.path.exists(sim_filename):
        log("Sending Similarity Report...")
        with open(sim_filename, "rb") as sim_file:
            bot.send_document(chat_id, sim_file, caption="📄 Turnitin Similarity Report")

    if ai_filename and os.path.exists(ai_filename):
        log("Sending AI Writing Report...")
        with open(ai_filename, "rb") as ai_file:
            bot.send_document(chat_id, ai_file, caption="🤖 Turnitin AI Writing Report")

    # Send completion message
    if sim_filename and ai_filename and os.path.exists(sim_filename) and os.path.exists(ai_filename):
        bot.send_message(chat_id, "✅ Process complete. Both reports sent successfully!")
    elif sim_filename and os.path.exists(sim_filename):
        bot.send_message(chat_id, "✅ Similarity report sent! (AI report may not be available for this document)")
    else:
        bot.send_message(chat_id, "❌ Could not download reports. Please try again.")

def cleanup_files(sim_filename, ai_filename, file_path):
    """Clean up downloaded and uploaded files"""
    try:
        if sim_filename and os.path.exists(sim_filename):
            os.remove(sim_filename)
            log(f"Deleted {sim_filename}")
        
        if ai_filename and os.path.exists(ai_filename):
            os.remove(ai_filename)
            log(f"Deleted {ai_filename}")
        
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            log(f"Deleted {file_path}")
    except Exception as e:
        log(f"Cleanup error: {e}")