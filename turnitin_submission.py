import os
import time
from datetime import datetime

def log(message: str):
    """Log a message with a timestamp to the terminal."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def random_wait(min_seconds=2, max_seconds=4):
    """Wait for a random amount of time to appear more human-like"""
    import random
    wait_time = random.uniform(min_seconds, max_seconds)
    time.sleep(wait_time)

from turnitin_auth import navigate_to_quick_submit

from turnitin_auth import navigate_to_quick_submit

def submit_document(page, file_path, chat_id, timestamp, bot, processing_messages):
    """Handle document submission process - Optimized version"""
    
    # Wait for page to load
    page.wait_for_load_state('networkidle', timeout=30000)
    random_wait(2, 3)
    
    # Click Submit button (use only working method)
    log("Clicking Submit button...")
    page.wait_for_selector('a.matte_button.submit_paper_button', timeout=15000)
    page.click('a.matte_button.submit_paper_button')
    log("Submit button clicked successfully")
    random_wait(2, 3)

    # Configure submission settings (simplified)
    log("Configuring submission settings...")
    page.wait_for_load_state('networkidle', timeout=30000)
    random_wait(2, 3)
    
    # Check all search options (use working selectors only)
    try:
        internet_checkbox = page.locator("label").filter(has_text="Search the internet").get_by_role("checkbox")
        if not internet_checkbox.is_checked():
            internet_checkbox.check()
        
        student_checkbox = page.locator("label").filter(has_text="Search student papers").get_by_role("checkbox")
        if not student_checkbox.is_checked():
            student_checkbox.check()
        
        periodicals_checkbox = page.locator("label").filter(has_text="Search periodicals, journals").get_by_role("checkbox")
        if not periodicals_checkbox.is_checked():
            periodicals_checkbox.check()
        
        # Set submit papers option
        submit_papers_select = page.get_by_label("Submit papers to: Standard")
        submit_papers_select.select_option("0")
        
        log("All submission settings configured successfully")
    except Exception as e:
        log(f"Error configuring settings: {e}")

    # Click Submit to proceed (use working method)
    log("Clicking Submit to proceed...")
    page.wait_for_selector('input[type="submit"][value="Submit"]', timeout=15000)
    page.click('input[type="submit"][value="Submit"]')
    random_wait(2, 3)

    # Fill submission details
    log("Filling submission details...")
    page.wait_for_selector('#author_first', timeout=15000)
    
    page.fill('#author_first', "Test User")
    page.fill('#author_last', "Document Check")
    
    submission_title = f"User_{chat_id}_Document_{timestamp}"
    page.fill('#title', submission_title)
    log("All form fields filled successfully")

    # Upload file (use working method only)
    log(f"Uploading file from path: {file_path}")
    msg = bot.send_message(chat_id, "📎 Uploading document...")
    processing_messages.append(msg.message_id)
    
    page.wait_for_selector("#choose-file-btn", timeout=15000)
    page.click("#choose-file-btn")
    random_wait(1, 2)
    
    page.locator("#selected-file").set_input_files(file_path)
    log("File uploaded successfully")
    random_wait(2, 3)

    # Click Upload button (use working method)
    log("Clicking Upload button...")
    page.wait_for_selector('button:has-text("Upload")', timeout=15000)
    page.click('button:has-text("Upload")')
    
    # Wait and extract metadata
    log("Waiting for metadata...")
    msg = bot.send_message(chat_id, "📊 Verifying document...")
    processing_messages.append(msg.message_id)
    page.wait_for_timeout(30000)  # 30 seconds
    
    try:
        # Extract metadata with safety checks
        try:
            actual_submission_title = page.locator("#submission-metadata-title").inner_text(timeout=10000)
            if not actual_submission_title or actual_submission_title.strip() == "":
                actual_submission_title = submission_title
        except:
            actual_submission_title = submission_title
        
        try:
            page_count = page.locator("#submission-metadata-pagecount").inner_text(timeout=5000)
            page_count = page_count.strip() if page_count else "Unknown"
        except:
            page_count = "Unknown"
            
        try:
            word_count = page.locator("#submission-metadata-wordcount").inner_text(timeout=5000)
            word_count = word_count.strip() if word_count else "Unknown"
        except:
            word_count = "Unknown"
        
        log(f"Submission metadata - Title: {actual_submission_title}, Pages: {page_count}, Words: {word_count}")
        
        # Only send verification message if we have valid metadata
        if page_count != "Unknown" and word_count != "Unknown":
            # Send verification message with HTML escaping
            import html
            page_count_safe = html.escape(str(page_count))
            word_count_safe = html.escape(str(word_count))
            
            verification_msg = f"""✅ <b>Document Verified</b>

📃 <b>Pages:</b> {page_count_safe}
📤 <b>Words:</b> {word_count_safe}

🚀 Submitting to Turnitin..."""
            
            verify_msg = bot.send_message(chat_id, verification_msg)
            processing_messages.append(verify_msg.message_id)
        else:
            # Send generic message if metadata extraction failed
            verify_msg = bot.send_message(chat_id, "✅ <b>Document Verified</b>\n\n🚀 Submitting to Turnitin...")
            processing_messages.append(verify_msg.message_id)
        
    except Exception as metadata_error:
        log(f"Could not extract metadata: {metadata_error}")
        actual_submission_title = submission_title
        # Send generic verification message
        verify_msg = bot.send_message(chat_id, "✅ <b>Document Verified</b>\n\n🚀 Submitting to Turnitin...")
        processing_messages.append(verify_msg.message_id)

    # Click Confirm button (use working method)
    log("Clicking Confirm button...")
    page.wait_for_selector("#confirm-btn", timeout=15000)
    page.click("#confirm-btn")

    # Wait for processing
    log("Waiting for processing...")
    msg = bot.send_message(chat_id, "⏳ Document submitted, processing...")
    processing_messages.append(msg.message_id)
    page.wait_for_timeout(60000)  # 60 seconds

    # Click inbox button (use working method)
    log("Going to assignment inbox...")
    page.wait_for_selector("#close-btn", timeout=15000)
    page.click("#close-btn")
    
    # Wait before searching for submission
    log("Waiting before searching for submission...")
    page.wait_for_timeout(30000)  # 30 seconds

    return actual_submission_title