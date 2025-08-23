import os
import time
import threading
from datetime import datetime, timedelta
from turnitin_auth import log, random_wait, navigate_to_quick_submit

def find_submission_with_retry(page, submission_title, chat_id, bot, processing_messages, max_retries=1):
    """Find the submitted document in Quick Submit with retry mechanism - Enhanced for headless"""
    
    for attempt in range(max_retries + 1):
        try:
            log(f"Attempt {attempt + 1} to find submission: {submission_title}")
            
            # Navigate back to Quick Submit to find our submission
            log("Navigating to Quick Submit to find our submission...")
            try:
                # Use the corrected navigation function
                page = navigate_to_quick_submit(page)
                # Wait for page to load completely
                page.wait_for_load_state('networkidle', timeout=30000)
                random_wait(3, 5)
            except Exception as quick_submit_error:
                log(f"Error navigating to Quick Submit: {quick_submit_error}")
                if attempt < max_retries:
                    continue
                raise Exception("Cannot navigate to Quick Submit to find submission")

            # Try to find the submission
            page1 = find_submission(page, submission_title, chat_id, bot, processing_messages)
            if page1:
                return page1
                
        except Exception as e:
            log(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries:
                log(f"Will retry in next attempt...")
                continue
            else:
                # Show retry option to user if this is the final attempt
                log("All attempts failed, showing retry option to user")
                return show_retry_option(page, submission_title, chat_id, bot, processing_messages)
    
    return None

def show_retry_option(page, submission_title, chat_id, bot, processing_messages):
    """Show retry button with 5-minute countdown"""
    
    # Delete processing messages
    try:
        for message_id in processing_messages:
            try:
                bot.delete_message(chat_id, message_id)
            except:
                pass
        processing_messages.clear()
    except:
        pass
    
    # Create retry keyboard with shorter callback data
    from telebot import types
    
    retry_markup = types.InlineKeyboardMarkup()
    retry_button = types.InlineKeyboardButton(
        "🔒 Retry in 5:00", 
        callback_data=f"retry_locked_{chat_id}"  # Shortened callback data
    )
    retry_markup.add(retry_button)
    
    retry_msg = bot.send_message(
        chat_id,
        "⚠️ <b>Document Processing Issue</b>\n\n"
        "Your document was submitted but we couldn't find it in the submissions list yet. "
        "This sometimes happens when Turnitin is still processing.\n\n"
        "⏰ Please wait 5 minutes for processing to complete, then click retry.",
        reply_markup=retry_markup
    )
    
    # Start countdown timer
    start_countdown_timer(chat_id, retry_msg.message_id, bot, page, submission_title)
    
    return None  # Return None to indicate retry is needed

def start_countdown_timer(chat_id, message_id, bot, page, submission_title):
    """Start a 5-minute countdown timer"""
    
    def countdown_worker():
        from telebot import types
        
        total_seconds = 300  # 5 minutes
        
        while total_seconds > 0:
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            
            # Update button text
            retry_markup = types.InlineKeyboardMarkup()
            retry_button = types.InlineKeyboardButton(
                f"🔒 Retry in {minutes}:{seconds:02d}", 
                callback_data=f"retry_locked_{chat_id}"
            )
            retry_markup.add(retry_button)
            
            try:
                bot.edit_message_reply_markup(
                    chat_id, 
                    message_id, 
                    reply_markup=retry_markup
                )
            except Exception as edit_error:
                log(f"Error updating countdown: {edit_error}")
                break
            
            time.sleep(1)
            total_seconds -= 1
        
        # Enable retry button after countdown - use hash to shorten data
        retry_markup = types.InlineKeyboardMarkup()
        title_hash = str(hash(submission_title))[:8]  # Short hash of title
        retry_button = types.InlineKeyboardButton(
            "🔓 Retry Now", 
            callback_data=f"retry_ready_{chat_id}_{title_hash}"
        )
        retry_markup.add(retry_button)
        
        try:
            bot.edit_message_text(
                "✅ <b>Ready to Retry</b>\n\n"
                "5 minutes have passed. Click the button below to retry finding your document.",
                chat_id,
                message_id,
                reply_markup=retry_markup
            )
        except Exception as final_edit_error:
            log(f"Error enabling retry button: {final_edit_error}")
    
    # Start countdown in separate thread
    countdown_thread = threading.Thread(target=countdown_worker, daemon=True)
    countdown_thread.start()

def find_submission(page, submission_title, chat_id, bot, processing_messages):
    """Find the submitted document in Quick Submit - Enhanced for headless mode"""
    
    # Look for our submission - Use actual submission title
    log(f"Looking for submission with title: {submission_title}")
    submission_found = False
    page1 = None

    # Wait for page to be fully loaded
    page.wait_for_load_state('networkidle', timeout=30000)
    random_wait(3, 5)

    # Method 1: Try to find by the percentage link (updated based on HTML)
    try:
        log("Method 1: Looking for percentage link...")
        # Wait for percentage links to be available
        page.wait_for_selector('span.or_full_version a', timeout=15000)
        percentage_links = page.locator('span.or_full_version a').all()
        if percentage_links:
            log(f"Found {len(percentage_links)} percentage links")
            with page.expect_popup() as page1_info:
                percentage_links[0].click()  # Click the first percentage link
            page1 = page1_info.value
            random_wait(4, 6)  # Increased wait for headless
            submission_found = True
            log("Found submission using Method 1 with percentage link")
        
    except Exception as e1:
        log(f"Method 1 failed: {e1}")

    # Method 2: Try to find by submission title in table rows
    if not submission_found:
        try:
            log("Method 2: Looking for submission title in table...")
            # Look for links containing parts of our submission title
            title_parts = submission_title.split('_')
            for part in title_parts:
                if len(part) > 3:  # Only try meaningful parts
                    try:
                        log(f"Trying to find link with text part: {part}")
                        page.wait_for_selector(f'a:has-text("{part}")', timeout=10000)
                        links = page.locator(f'a:has-text("{part}")').all()
                        if links:
                            log(f"Found {len(links)} links with title part: {part}")
                            with page.expect_popup() as page1_info:
                                links[0].click()
                            page1 = page1_info.value
                            random_wait(4, 6)
                            submission_found = True
                            log(f"Found submission using Method 2 with title part: {part}")
                            break
                    except Exception as part_error:
                        log(f"Title part {part} search failed: {part_error}")
                        continue
                
        except Exception as e2:
            log(f"Method 2 failed: {e2}")

    # Method 3: Look for Test User submissions
    if not submission_found:
        try:
            log("Method 3: Looking for Test User submissions...")
            # Wait for Test User elements
            page.wait_for_selector('td:has-text("Test User"), tr:has-text("Test User")', timeout=15000)
            test_user_elements = page.locator('td:has-text("Test User"), tr:has-text("Test User")').all()
            if test_user_elements:
                log(f"Found {len(test_user_elements)} Test User elements")
                # Look for percentage or view links within these elements
                for element in test_user_elements:
                    try:
                        # Look for percentage links within the Test User row
                        percentage_links = element.locator('a[href*="newreport"], a:has-text("%")').all()
                        if percentage_links:
                            log(f"Found percentage links in Test User row")
                            with page.expect_popup() as page1_info:
                                percentage_links[0].click()
                            page1 = page1_info.value
                            random_wait(4, 6)
                            submission_found = True
                            log("Found submission using Method 3 with Test User row")
                            break
                    except Exception as element_error:
                        log(f"Error with Test User element: {element_error}")
                        continue
        except Exception as e3:
            log(f"Method 3 failed: {e3}")

    # Method 4: Look for any recent submissions with percentage
    if not submission_found:
        try:
            log("Method 4: Looking for any recent submissions with percentage...")
            # Wait for report links
            page.wait_for_selector('a[href*="newreport"]', timeout=15000)
            report_links = page.locator('a[href*="newreport"]').all()
            if report_links:
                log(f"Found {len(report_links)} report links")
                with page.expect_popup() as page1_info:
                    report_links[0].click()  # Click the first (most recent) report link
                page1 = page1_info.value
                random_wait(4, 6)
                submission_found = True
                log("Found submission using Method 4 with report link")
        except Exception as e4:
            log(f"Method 4 failed: {e4}")

    # Method 5: Try by User ID pattern
    if not submission_found:
        try:
            log("Method 5: Looking by User ID pattern...")
            user_pattern = f"User_{chat_id}"
            # Try finding by our user ID pattern
            page.wait_for_selector(f'a:has-text("{user_pattern}")', timeout=10000)
            user_links = page.locator(f'a:has-text("{user_pattern}")').all()
            if user_links:
                log(f"Found {len(user_links)} links with user ID pattern")
                with page.expect_popup() as page1_info:
                    user_links[0].click()
                page1 = page1_info.value
                random_wait(4, 6)
                submission_found = True
                log("Found submission using Method 5 with user ID")
        except Exception as e5:
            log(f"Method 5 failed: {e5}")

    if not submission_found:
        # Enhanced debugging
        debug_submission_search(page, submission_title, chat_id, bot)
        raise Exception(f"Could not find the submitted document using any method. Title was: {submission_title}")

    return page1

def debug_submission_search(page, submission_title, chat_id, bot):
    """Enhanced debugging for submission search"""
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
        for i, link in enumerate(all_links[:30]):  # Check more links for headless
            try:
                link_text = link.inner_text()[:100]  # First 100 chars
                link_href = link.get_attribute('href') or 'No href'
                
                # Check if this might be a submission link
                if any(keyword in link_href.lower() for keyword in ['submission', 'view', 'paper', 'newreport']):
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
                random_wait(4, 6)
                log("Found submission using debugging method with potential link")
                return page1
            except Exception as debug_click_error:
                log(f"Debug click failed: {debug_click_error}")
        
    except Exception as debug_error:
        log(f"Enhanced debugging failed: {debug_error}")

def download_reports_with_retry(page1, chat_id, timestamp, bot, processing_messages):
    """Download similarity and AI writing reports with retry logic - Enhanced for headless"""
    
    # Ensure downloads folder exists
    downloads_dir = "downloads"
    os.makedirs(downloads_dir, exist_ok=True)

    # Wait for the submission page to fully load with longer timeout
    log("Waiting for submission page to load...")
    try:
        page1.wait_for_load_state('networkidle', timeout=45000)  # Increased timeout for headless
        msg = bot.send_message(chat_id, "📊 Processing complete. Downloading reports...")
        processing_messages.append(msg.message_id)
        log("Submission page loaded successfully")
        random_wait(4, 6)  # Increased wait for headless
    except Exception as load_error:
        log(f"Page load timeout: {load_error}")
        msg = bot.send_message(chat_id, "📊 Processing complete. Attempting to download reports...")
        processing_messages.append(msg.message_id)

    # Wait extra time for reports to be ready (90 seconds as you mentioned)
    log("Waiting 90 seconds for reports to be fully ready...")
    wait_msg = bot.send_message(chat_id, "⏳ Waiting for reports to be generated... (90 seconds)")
    processing_messages.append(wait_msg.message_id)
    page1.wait_for_timeout(90000)  # 90 seconds

    # Check if the submission page has loaded correctly and reports are available
    reports_ready = check_reports_availability(page1)
    
    if not reports_ready:
        log("Reports not ready or page not loaded correctly, showing retry option")
        return show_general_retry_option(page1, chat_id, timestamp, bot, processing_messages, "reports_not_ready")

    # Try to download reports
    sim_filename = download_similarity_report(page1, chat_id, timestamp, downloads_dir)
    ai_filename = download_ai_report(page1, chat_id, timestamp, downloads_dir)
    
    # Check if any reports downloaded successfully
    sim_success = (sim_filename and os.path.exists(sim_filename))
    ai_success = (ai_filename and os.path.exists(ai_filename))
    
    # If at least one report was downloaded, send what we have and offer retry for missing ones
    if sim_success or ai_success:
        log(f"At least one report downloaded - Similarity: {sim_success}, AI: {ai_success}")
        return sim_filename, ai_filename
    else:
        log("No reports downloaded successfully, showing download retry option")
        return show_download_retry_option(page1, chat_id, timestamp, bot, processing_messages)

def check_reports_availability(page1):
    """Check if reports are available and page loaded correctly - FIXED for new Turnitin viewer"""
    try:
        log("Checking if reports are available...")
        
        # Get current URL to check if we're on the right page
        try:
            current_url = page1.url
            log(f"Current submission page URL: {current_url}")
            
            # Check if we're on the new Turnitin viewer (carta) - THIS IS THE FIX
            if "ev.turnitin.com" in current_url and "carta" in current_url:
                log("We're on the new Turnitin viewer - this is correct")
            elif "newreport" in current_url or "view" in current_url:
                log("We're on the classic Turnitin viewer - this is also correct")  
            else:
                log(f"Unknown submission page format: {current_url}")
                # Don't immediately fail - let's check for download button anyway
        except Exception as url_error:
            log(f"Could not check URL: {url_error}")
        
        # Check if download button is present and visible - enhanced selectors
        download_selectors = [
            'tii-sws-download-btn-mfe',
            '#sws-download-btn-mfe',
            '[data-testid="download-button"]',
            'button[aria-label*="Download"]',
            'button:has-text("Download")',
            '.download-btn',
            '#download-popover',
            'tii-sws-header-btn[aria-label*="Download"]'
        ]
        
        download_button_found = False
        for selector in download_selectors:
            try:
                log(f"Checking download button selector: {selector}")
                page1.wait_for_selector(selector, timeout=10000)
                button = page1.locator(selector)
                if button.count() > 0:
                    # Check if any of the buttons are visible
                    for i in range(button.count()):
                        if button.nth(i).is_visible():
                            log(f"Download button found and visible with selector: {selector}")
                            download_button_found = True
                            break
                if download_button_found:
                    break
            except Exception as selector_error:
                log(f"Selector {selector} not found: {selector_error}")
                continue
        
        if not download_button_found:
            log("No visible download button found - reports may not be ready")
            return False
        
        # Check if there are any error messages on the page
        error_indicators = [
            'text="Error"',
            'text="Not found"',
            'text="Processing"',
            'text="Please wait"',
            '.error',
            '.warning',
            ':has-text("still processing")',
            ':has-text("not ready")'
        ]
        
        for indicator in error_indicators:
            try:
                if page1.locator(indicator).count() > 0:
                    log(f"Found error indicator: {indicator}")
                    return False
            except:
                continue
        
        log("Reports appear to be available")
        return True
        
    except Exception as check_error:
        log(f"Error checking reports availability: {check_error}")
        return False

def show_general_retry_option(page1, chat_id, timestamp, bot, processing_messages, retry_type="general"):
    """Show retry option for general issues with 5-minute countdown"""
    
    # Delete processing messages
    try:
        for message_id in processing_messages:
            try:
                bot.delete_message(chat_id, message_id)
            except:
                pass
        processing_messages.clear()
    except:
        pass
    
    # Create retry keyboard with shorter callback data
    from telebot import types
    
    retry_markup = types.InlineKeyboardMarkup()
    retry_button = types.InlineKeyboardButton(
        "🔒 Retry in 5:00", 
        callback_data=f"retry_gen_locked_{chat_id}"  # Shortened callback
    )
    retry_markup.add(retry_button)
    
    if retry_type == "reports_not_ready":
        message_text = ("⚠️ <b>Reports Not Ready</b>\n\n"
                       "Your document was submitted successfully but the reports are still being generated by Turnitin. "
                       "This can take a few minutes for larger documents.\n\n"
                       "⏰ Please wait 5 minutes, then click retry to check for the reports again.")
    else:
        message_text = ("⚠️ <b>Processing Issue</b>\n\n"
                       "There was an issue accessing your submission. The document may still be processing "
                       "or there might be a temporary issue with the Turnitin system.\n\n"
                       "⏰ Please wait 5 minutes, then click retry to check again.")
    
    retry_msg = bot.send_message(
        chat_id,
        message_text,
        reply_markup=retry_markup
    )
    
    # Start countdown timer for general retry
    start_general_countdown_timer(chat_id, retry_msg.message_id, bot, page1, timestamp, retry_type)
    
    return None, None  # Return None for both files to indicate retry is needed

def start_general_countdown_timer(chat_id, message_id, bot, page1, timestamp, retry_type):
    """Start a 5-minute countdown timer for general retry"""
    
    def countdown_worker():
        from telebot import types
        
        total_seconds = 300  # 5 minutes
        
        while total_seconds > 0:
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            
            # Update button text
            retry_markup = types.InlineKeyboardMarkup()
            retry_button = types.InlineKeyboardButton(
                f"🔒 Retry in {minutes}:{seconds:02d}", 
                callback_data=f"retry_gen_locked_{chat_id}"
            )
            retry_markup.add(retry_button)
            
            try:
                bot.edit_message_reply_markup(
                    chat_id, 
                    message_id, 
                    reply_markup=retry_markup
                )
            except Exception as edit_error:
                log(f"Error updating general countdown: {edit_error}")
                break
            
            time.sleep(1)
            total_seconds -= 1
        
        # Enable retry button after countdown with shorter callback
        retry_markup = types.InlineKeyboardMarkup()
        retry_button = types.InlineKeyboardButton(
            "🔓 Retry Now", 
            callback_data=f"retry_gen_ready_{chat_id}_{timestamp[:8]}"  # Shortened timestamp
        )
        retry_markup.add(retry_button)
        
        try:
            bot.edit_message_text(
                "✅ <b>Ready to Retry</b>\n\n"
                "5 minutes have passed. Click the button below to retry checking for your reports.",
                chat_id,
                message_id,
                reply_markup=retry_markup
            )
        except Exception as final_edit_error:
            log(f"Error enabling general retry button: {final_edit_error}")
    
    # Start countdown in separate thread
    countdown_thread = threading.Thread(target=countdown_worker, daemon=True)
    countdown_thread.start()

def show_download_retry_option(page1, chat_id, timestamp, bot, processing_messages):
    """Show retry option for failed downloads"""
    
    # Delete processing messages
    try:
        for message_id in processing_messages:
            try:
                bot.delete_message(chat_id, message_id)
            except:
                pass
        processing_messages.clear()
    except:
        pass
    
    # Create retry keyboard with shorter callback data
    from telebot import types
    
    retry_markup = types.InlineKeyboardMarkup()
    retry_button = types.InlineKeyboardButton(
        "🔒 Retry Download in 5:00", 
        callback_data=f"retry_dl_locked_{chat_id}"  # Shortened callback
    )
    retry_markup.add(retry_button)
    
    retry_msg = bot.send_message(
        chat_id,
        "⚠️ <b>Download Issue</b>\n\n"
        "We found your document but couldn't download the reports. "
        "Turnitin might still be generating them.\n\n"
        "⏰ Please wait 5 minutes, then click retry to download the reports.",
        reply_markup=retry_markup
    )
    
    # Start countdown timer for download
    start_download_countdown_timer(chat_id, retry_msg.message_id, bot, page1, timestamp)
    
    return None, None  # Return None for both files to indicate retry is needed

def start_download_countdown_timer(chat_id, message_id, bot, page1, timestamp):
    """Start a 5-minute countdown timer for download retry"""
    
    def countdown_worker():
        from telebot import types
        
        total_seconds = 300  # 5 minutes
        
        while total_seconds > 0:
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            
            # Update button text
            retry_markup = types.InlineKeyboardMarkup()
            retry_button = types.InlineKeyboardButton(
                f"🔒 Retry Download in {minutes}:{seconds:02d}", 
                callback_data=f"retry_dl_locked_{chat_id}"
            )
            retry_markup.add(retry_button)
            
            try:
                bot.edit_message_reply_markup(
                    chat_id, 
                    message_id, 
                    reply_markup=retry_markup
                )
            except Exception as edit_error:
                log(f"Error updating download countdown: {edit_error}")
                break
            
            time.sleep(1)
            total_seconds -= 1
        
        # Enable retry button after countdown with shorter callback
        retry_markup = types.InlineKeyboardMarkup()
        retry_button = types.InlineKeyboardButton(
            "🔓 Retry Download Now", 
            callback_data=f"retry_dl_ready_{chat_id}_{timestamp[:8]}"  # Shortened timestamp
        )
        retry_markup.add(retry_button)
        
        try:
            bot.edit_message_text(
                "✅ <b>Ready to Retry Download</b>\n\n"
                "5 minutes have passed. Click the button below to retry downloading the reports.",
                chat_id,
                message_id,
                reply_markup=retry_markup
            )
        except Exception as final_edit_error:
            log(f"Error enabling download retry button: {final_edit_error}")
    
    # Start countdown in separate thread
    countdown_thread = threading.Thread(target=countdown_worker, daemon=True)
    countdown_thread.start()

def download_similarity_report(page1, chat_id, timestamp, downloads_dir):
    """Download the similarity report - Enhanced for headless mode"""
    log("Downloading Similarity Report...")
    sim_filename = None
    
    try:
        # Wait for page to be ready with longer timeout
        log("Waiting for download buttons to be ready...")
        page1.wait_for_load_state('domcontentloaded')
        random_wait(4, 7)  # Increased wait for headless
        
        # Click the download icon (enhanced for headless)
        log("Clicking download icon to open menu...")
        download_selectors = [
            'tii-sws-download-btn-mfe',
            '#sws-download-btn-mfe',
            '#download-popover tii-sws-header-btn svg',
            'tii-sws-download-btn-mfe svg',
            '[data-testid="download-button"]',
            'button[aria-label*="Download"]',
            'tii-sws-header-btn[aria-label*="Download"]'
        ]
        
        download_clicked = click_download_button(page1, download_selectors)
        
        if not download_clicked:
            raise Exception("Could not click download button with any method")
            
        random_wait(3, 5)  # Increased wait
        
        # Click on Similarity Report option (enhanced for headless)
        log("Clicking Similarity Report option in menu...")
        try:
            # Wait for the download menu to appear
            page1.wait_for_selector('button:has-text("Similarity Report")', timeout=15000)
            with page1.expect_download(timeout=45000) as download_info:  # Increased timeout
                page1.get_by_role("button", name="Similarity Report").click()
            download_sim = download_info.value
            sim_filename = os.path.join(downloads_dir, f"{chat_id}_{timestamp}_similarity.pdf")
            download_sim.save_as(sim_filename)
            log(f"Saved Similarity Report as {sim_filename}")
            
        except Exception as sim_error:
            log(f"Role-based similarity report download failed: {sim_error}")
            # Try alternative selectors
            sim_selectors = [
                'button[data-px="SimReportDownloadClicked"]',
                'button:has-text("Similarity Report")',
                'li.download-menu-item:has-text("Similarity Report") button',
                '.download-menu button:has-text("Similarity Report")',
                '[data-testid="similarity-report-download"]'
            ]
            
            sim_clicked = False
            for selector in sim_selectors:
                try:
                    log(f"Trying similarity report selector: {selector}")
                    page1.wait_for_selector(selector, timeout=10000)
                    sim_btn = page1.locator(selector)
                    if sim_btn.count() > 0 and sim_btn.is_visible():
                        with page1.expect_download(timeout=45000) as download_info:
                            sim_btn.click()
                        download_sim = download_info.value
                        sim_filename = os.path.join(downloads_dir, f"{chat_id}_{timestamp}_similarity.pdf")
                        download_sim.save_as(sim_filename)
                        log(f"Saved Similarity Report as {sim_filename}")
                        sim_clicked = True
                        break
                except Exception as sel_error:
                    log(f"Similarity selector {selector} failed: {sel_error}")
                    continue
            
            if not sim_clicked:
                raise Exception("Could not click similarity report button")
            
    except Exception as e:
        log(f"Error downloading Similarity Report: {e}")
        sim_filename = None
    
    return sim_filename

def download_ai_report(page1, chat_id, timestamp, downloads_dir):
    """Download the AI writing report - Enhanced for headless mode"""
    ai_filename = None
    
    try:
        log("Attempting to download AI Writing Report...")
        
        # Wait a bit before trying AI report
        random_wait(3, 5)  # Increased wait
        
        # Click the download icon again (enhanced for headless)
        log("Clicking download icon for AI report...")
        download_selectors = [
            'tii-sws-download-btn-mfe',
            '#sws-download-btn-mfe', 
            '#download-popover tii-sws-header-btn svg',
            'tii-sws-download-btn-mfe svg',
            '[data-testid="download-button"]',
            'button[aria-label*="Download"]',
            'tii-sws-header-btn[aria-label*="Download"]'
        ]
        
        download_clicked = click_download_button(page1, download_selectors)
        
        if not download_clicked:
            raise Exception("Could not click download button for AI report")
            
        random_wait(3, 5)
        
        # Click on AI Writing Report option (enhanced for headless)
        log("Clicking AI Writing Report option in menu...")
        try:
            # Wait for the AI report button to appear
            page1.wait_for_selector('button:has-text("AI Writing Report")', timeout=15000)
            with page1.expect_download(timeout=45000) as download_info:  # Increased timeout
                page1.get_by_role("button", name="AI Writing Report").click()
            download_ai = download_info.value
            ai_filename = os.path.join(downloads_dir, f"{chat_id}_{timestamp}_ai.pdf")
            download_ai.save_as(ai_filename)
            log(f"Saved AI Writing Report as {ai_filename}")
            
        except Exception as ai_error:
            log(f"Role-based AI report download failed: {ai_error}")
            # Try alternative selectors
            ai_selectors = [
                'button[data-px="AIWritingReportDownload"]',
                'button:has-text("AI Writing Report")',
                'li.download-menu-item:has-text("AI Writing Report") button',
                '.download-menu button:has-text("AI Writing Report")',
                '[data-testid="ai-report-download"]'
            ]
            
            ai_clicked = False
            for selector in ai_selectors:
                try:
                    log(f"Trying AI report selector: {selector}")
                    page1.wait_for_selector(selector, timeout=10000)
                    ai_btn = page1.locator(selector)
                    if ai_btn.count() > 0 and ai_btn.is_visible():
                        with page1.expect_download(timeout=45000) as download_info:
                            ai_btn.click()
                        download_ai = download_info.value
                        ai_filename = os.path.join(downloads_dir, f"{chat_id}_{timestamp}_ai.pdf")
                        download_ai.save_as(ai_filename)
                        log(f"Saved AI Writing Report as {ai_filename}")
                        ai_clicked = True
                        break
                except Exception as ai_sel_error:
                    log(f"AI selector {selector} failed: {ai_sel_error}")
                    continue
            
            if not ai_clicked:
                log("Could not click AI Writing Report button - might not be available")
            
    except Exception as e:
        log(f"Could not download AI Writing Report: {e}")
        # AI report might not be available for this document
    
    return ai_filename

def click_download_button(page, download_selectors):
    """Helper function to click download button with multiple selectors - Enhanced for headless"""
    try:
        download_clicked = False
        for selector in download_selectors:
            try:
                log(f"Trying download selector: {selector}")
                # Wait for the selector to be available
                page.wait_for_selector(selector, timeout=10000)
                download_btn = page.locator(selector)
                if download_btn.count() > 0:
                    # Check each instance to find a visible one
                    for i in range(download_btn.count()):
                        try:
                            btn_instance = download_btn.nth(i)
                            if btn_instance.is_visible():
                                btn_instance.click()
                                log(f"Successfully clicked download button with selector: {selector} (instance {i})")
                                download_clicked = True
                                break
                        except Exception as instance_error:
                            log(f"Instance {i} of selector {selector} failed: {instance_error}")
                            continue
                    
                    if download_clicked:
                        break
            except Exception as sel_error:
                log(f"Selector {selector} failed: {sel_error}")
                continue
        
        if not download_clicked:
            # Try using JavaScript to click the download button (enhanced for headless)
            log("Trying JavaScript click method...")
            js_click_result = page.evaluate("""
                const downloadSelectors = [
                    'tii-sws-download-btn-mfe',
                    '#sws-download-btn-mfe',
                    '[data-testid="download-button"]',
                    'button[aria-label*="Download"]',
                    'tii-sws-header-btn[aria-label*="Download"]'
                ];
                
                for (const selector of downloadSelectors) {
                    const downloadBtn = document.querySelector(selector);
                    if (downloadBtn && downloadBtn.offsetParent !== null) {
                        // Scroll into view first
                        downloadBtn.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        // Wait a bit
                        setTimeout(() => {
                            downloadBtn.click();
                        }, 500);
                        return true;
                    }
                }
                return false;
            """)
            
            if js_click_result:
                log("JavaScript click successful")
                download_clicked = True
                # Wait for the click to register
                page.wait_for_timeout(1000)
            else:
                log("JavaScript click failed - button not found")
        
        return download_clicked
        
    except Exception as download_click_error:
        log(f"Error clicking download button: {download_click_error}")
        return False

def send_reports_to_user(chat_id, sim_filename, ai_filename, bot, processing_messages):
    """Send downloaded reports to Telegram user - Enhanced to handle partial downloads"""
    
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

    # Check what we have available
    sim_available = sim_filename and os.path.exists(sim_filename)
    ai_available = ai_filename and os.path.exists(ai_filename)
    
    # Send the similarity report if available
    if sim_available:
        log("Sending Similarity Report to Telegram user...")
        try:
            with open(sim_filename, "rb") as sim_file:
                bot.send_document(chat_id, sim_file, caption="📄 Turnitin Similarity Report")
            log("Similarity Report sent successfully")
        except Exception as send_error:
            log(f"Error sending Similarity Report: {send_error}")
            bot.send_message(chat_id, f"❌ Error sending Similarity Report: {send_error}")

    # Send the AI report if available
    if ai_available:
        log("Sending AI Writing Report to Telegram user...")
        try:
            with open(ai_filename, "rb") as ai_file:
                bot.send_document(chat_id, ai_file, caption="🤖 Turnitin AI Writing Report")
            log("AI Writing Report sent successfully")
        except Exception as send_ai_error:
            log(f"Error sending AI Writing Report: {send_ai_error}")
            bot.send_message(chat_id, f"❌ Error sending AI Writing Report: {send_ai_error}")

    # Send appropriate completion message based on what was available
    if sim_available and ai_available:
        bot.send_message(chat_id, "✅ Process complete. Both reports have been sent.")
    elif sim_available and not ai_available:
        message = ("✅ Similarity report sent successfully!\n\n"
                  "⚠️ AI Writing Report could not be generated.\n\n"
                  "Please check that your document:\n"
                  "• Contains between 500-10,000 words\n"
                  "• Has sufficient original content\n"
                  "• Is in a supported format (PDF, DOC, DOCX)\n\n"
                  "💡 Try submitting a longer document with more text content.")
        bot.send_message(chat_id, message)
    elif not sim_available and ai_available:
        message = ("✅ AI Writing report sent successfully!\n\n"
                  "⚠️ Similarity Report could not be generated.\n\n"
                  "This is unusual. Please contact support if this continues to happen.")
        bot.send_message(chat_id, message)
    else:
        # Neither report was available - this shouldn't happen if we reach this function
        bot.send_message(chat_id, "❌ Could not download any reports. Please try again later.")

def cleanup_files(sim_filename, ai_filename, file_path):
    """Clean up downloaded and uploaded files"""
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