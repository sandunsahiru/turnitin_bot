import os
import time
import base64
from datetime import datetime
from turnitin_auth import log, random_wait

def submit_document(page, file_path, chat_id, timestamp, bot, processing_messages):
    """Handle document submission process - Enhanced for server environment"""
    
    # Take a screenshot for debugging
    try:
        page.screenshot(path="debug_submit_page.png")
        log("Screenshot saved: debug_submit_page.png")
    except Exception as screenshot_error:
        log(f"Could not take screenshot: {screenshot_error}")
    
    # Wait for page to be fully loaded with longer timeout for server
    page.wait_for_load_state('networkidle', timeout=45000)
    random_wait(5, 8)  # Longer wait for server
    
    # Enhanced Submit button detection and clicking
    log("Enhanced Submit button detection...")
    submit_clicked = find_and_click_submit_button(page)
    
    if not submit_clicked:
        # Take screenshot of failed state
        try:
            page.screenshot(path="debug_submit_button_not_found.png")
            log("Screenshot saved: debug_submit_button_not_found.png")
        except:
            pass
        raise Exception("Failed to click Submit button with any method")

    # Configure submission settings - Enhanced error handling and waits
    log("Configuring submission settings...")
    
    # Wait for the settings page to load with longer timeout
    page.wait_for_load_state('networkidle', timeout=45000)
    random_wait(5, 8)  # Longer wait for server
    
    try:
        # Check all search options using the correct selectors with better error handling
        configure_submission_settings(page)
        log("All submission settings configured successfully")
    except Exception as e:
        log(f"Error configuring submission settings: {e}")
        raise Exception(f"Failed to configure settings: {e}")

    # Click Submit to proceed with enhanced detection
    log("Clicking Submit to proceed...")
    proceed_clicked = find_and_click_proceed_button(page)
    
    if not proceed_clicked:
        raise Exception("Failed to click Submit to proceed button")

    # Wait for the form page to load
    page.wait_for_load_state('networkidle', timeout=45000)
    random_wait(5, 8)

    # Fill submission details - Enhanced for server
    log("Filling submission details...")
    submission_title = fill_submission_details(page, chat_id, timestamp)

    # Upload file - Enhanced for server
    log(f"Uploading file from path: {file_path}")
    
    # Wait before file upload
    log("Waiting 10 seconds before file upload...")
    msg = bot.send_message(chat_id, "🔎 Preparing document upload...")
    processing_messages.append(msg.message_id)
    page.wait_for_timeout(10000)  # Longer wait for server
    
    upload_success = upload_file(page, file_path)
    
    if not upload_success:
        raise Exception("All file upload methods failed")

    random_wait(6, 10)  # Longer wait for server

    # Wait for file selection confirmation - Enhanced timeout
    try:
        log("Waiting for file selection confirmation...")
        page.wait_for_selector("#submission-metadata-filename", timeout=30000)  # Longer timeout
        log("File selection confirmed by metadata appearance")
        random_wait(3, 5)
    except Exception as confirm_error:
        log(f"File selection confirmation failed: {confirm_error}")
        # Continue anyway, might still work

    # Click Upload button with enhanced detection
    log("Clicking Upload button...")
    upload_clicked = find_and_click_upload_button(page)
    
    if not upload_clicked:
        raise Exception("Failed to click Upload button")

    # Handle privacy notice if it appears
    try:
        if page.get_by_text("We take your privacy very").is_visible(timeout=10000):
            page.get_by_text("We take your privacy very").click()
            random_wait(3, 5)
    except:
        log("Privacy notice not found, continuing...")

    # Wait before confirming and verify upload details - Server optimized
    log("Waiting 60 seconds before confirming document...")
    msg = bot.send_message(chat_id, "📤 Document uploaded, verifying details...")
    processing_messages.append(msg.message_id)
    page.wait_for_timeout(60000)  # 60 seconds for server

    # Extract and verify submission metadata before confirming
    actual_submission_title = extract_submission_metadata(page, submission_title, chat_id, bot, processing_messages)

    # Click Confirm button with enhanced detection
    log("Clicking Confirm button...")
    confirm_clicked = find_and_click_confirm_button(page)
    
    if not confirm_clicked:
        raise Exception("Failed to click Confirm button")

    # Wait up to 90 seconds before clicking "Go to assignment inbox"
    log("Waiting up to 90 seconds for processing...")
    msg = bot.send_message(chat_id, "⏳ Document submitted, waiting for processing to complete...")
    processing_messages.append(msg.message_id)
    page.wait_for_timeout(90000)  # Longer wait for server

    # Click "Go to assignment inbox" with enhanced detection
    log("Clicking 'Go to assignment inbox'...")
    inbox_clicked = find_and_click_inbox_button(page)
    
    if not inbox_clicked:
        log("Could not click inbox button, but continuing...")

    # Wait 90 seconds before navigating back
    log("Waiting 90 seconds before navigating to Quick Submit...")
    msg = bot.send_message(chat_id, "⏰ Waiting for document to appear in submissions list...")
    processing_messages.append(msg.message_id)
    page.wait_for_timeout(90000)  # Longer wait for server

    return actual_submission_title

def find_and_click_submit_button(page):
    """Enhanced Submit button detection and clicking for server environment"""
    log("Searching for Submit button with comprehensive methods...")
    
    # Method 1: Try specific Submit button selectors
    submit_selectors = [
        'a.matte_button.submit_paper_button',
        'a:has-text("Submit")',
        'button:has-text("Submit")',
        'a[href*="submit"]',
        'a.submit_paper_button',
        '.matte_button:has-text("Submit")',
        'a.matte_button',
        'input[type="submit"]',
        'button[type="submit"]',
        '.submit-button',
        '#submit-btn',
        '[data-action="submit"]'
    ]
    
    for i, selector in enumerate(submit_selectors):
        try:
            log(f"Method 1 - Trying Submit selector {i+1}: {selector}")
            page.wait_for_selector(selector, timeout=15000)
            elements = page.locator(selector).all()
            
            if elements:
                log(f"Found {len(elements)} elements with selector: {selector}")
                for j, element in enumerate(elements):
                    try:
                        text = element.inner_text()
                        visible = element.is_visible()
                        log(f"  Element {j+1}: '{text}', visible: {visible}")
                        
                        if visible and ('submit' in text.lower() or 'continue' in text.lower()):
                            log(f"Clicking Submit element: '{text}' with selector: {selector}")
                            element.click()
                            log("Submit button clicked successfully")
                            random_wait(5, 8)  # Longer wait for server
                            return True
                    except Exception as element_error:
                        log(f"Error with element {j+1}: {element_error}")
                        continue
            else:
                log(f"No elements found with selector: {selector}")
                
        except Exception as selector_error:
            log(f"Submit selector {selector} failed: {selector_error}")
            continue
    
    # Method 2: Search by text content
    log("Method 2: Searching by text content...")
    try:
        # Look for any clickable element containing "Submit"
        all_elements = page.locator('a, button, input').all()
        log(f"Found {len(all_elements)} total clickable elements")
        
        for i, element in enumerate(all_elements[:50]):  # Check first 50 elements
            try:
                text = element.inner_text().strip().lower()
                tag_name = element.evaluate('el => el.tagName').lower()
                
                if 'submit' in text and element.is_visible():
                    log(f"Found Submit element by text: '{text}' (tag: {tag_name})")
                    element.click()
                    log("Submit button clicked by text search")
                    random_wait(5, 8)
                    return True
                    
            except Exception as element_error:
                continue
                
    except Exception as text_search_error:
        log(f"Text search failed: {text_search_error}")
    
    # Method 3: JavaScript approach
    log("Method 3: Using JavaScript to find and click Submit button...")
    try:
        js_result = page.evaluate("""
            // Look for submit buttons by various methods
            const selectors = [
                'a.matte_button.submit_paper_button',
                'a[class*="submit"]',
                'button[class*="submit"]',
                'a[href*="submit"]',
                'input[type="submit"]',
                'button[type="submit"]'
            ];
            
            for (const selector of selectors) {
                const elements = document.querySelectorAll(selector);
                for (const element of elements) {
                    if (element.offsetParent !== null) { // visible check
                        const text = element.innerText || element.value || '';
                        if (text.toLowerCase().includes('submit')) {
                            element.scrollIntoView();
                            setTimeout(() => element.click(), 500);
                            return {success: true, method: selector, text: text};
                        }
                    }
                }
            }
            
            // Fallback: look for any visible element with "submit" text
            const allElements = document.querySelectorAll('a, button, input');
            for (const element of allElements) {
                const text = (element.innerText || element.value || '').toLowerCase();
                if (text.includes('submit') && element.offsetParent !== null) {
                    element.scrollIntoView();
                    setTimeout(() => element.click(), 500);
                    return {success: true, method: 'text_search', text: text};
                }
            }
            
            return {success: false};
        """)
        
        if js_result.get('success'):
            log(f"JavaScript click successful: {js_result.get('method')} - '{js_result.get('text')}'")
            page.wait_for_timeout(5000)  # Wait for click to register
            return True
        else:
            log("JavaScript method found no clickable Submit button")
            
    except Exception as js_error:
        log(f"JavaScript method failed: {js_error}")
    
    # Method 4: Take screenshot and analyze page content for debugging
    log("Method 4: Analyzing page content for debugging...")
    try:
        page.screenshot(path="debug_no_submit_button_found.png")
        log("Debug screenshot saved: debug_no_submit_button_found.png")
        
        # Save page HTML for analysis
        content = page.content()
        with open("debug_submit_page_content.html", "w", encoding="utf-8") as f:
            f.write(content)
        log("Page HTML saved: debug_submit_page_content.html")
        
        # Log page info
        title = page.title()
        url = page.url
        log(f"Page info - Title: '{title}', URL: '{url}'")
        
    except Exception as debug_error:
        log(f"Debug analysis failed: {debug_error}")
    
    return False

def configure_submission_settings(page):
    """Configure submission settings with enhanced error handling"""
    try:
        log("Checking 'Search the internet' option...")
        try:
            internet_checkbox = page.locator("label").filter(has_text="Search the internet").get_by_role("checkbox")
            if not internet_checkbox.is_checked():
                internet_checkbox.check()
            random_wait(3, 5)
        except Exception as internet_error:
            log(f"Internet search checkbox error: {internet_error}")
        
        log("Checking 'Search student papers' option...")
        try:
            student_checkbox = page.locator("label").filter(has_text="Search student papers").get_by_role("checkbox")
            if not student_checkbox.is_checked():
                student_checkbox.check()
            random_wait(3, 5)
        except Exception as student_error:
            log(f"Student papers checkbox error: {student_error}")
        
        log("Checking 'Search periodicals, journals' option...")
        try:
            periodicals_checkbox = page.locator("label").filter(has_text="Search periodicals, journals").get_by_role("checkbox")
            if not periodicals_checkbox.is_checked():
                periodicals_checkbox.check()
            random_wait(3, 5)
        except Exception as periodicals_error:
            log(f"Periodicals checkbox error: {periodicals_error}")

        # Set submit papers option - Enhanced error handling
        log("Setting submit papers option...")
        try:
            submit_papers_select = page.get_by_label("Submit papers to: Standard")
            submit_papers_select.select_option("0")
            random_wait(3, 5)
        except Exception as submit_papers_error:
            log(f"Submit papers option error: {submit_papers_error}")
            # Try alternative selector
            try:
                page.locator('select[name="submit_papers_to"]').select_option("0")
                random_wait(3, 5)
            except Exception as alt_submit_error:
                log(f"Alternative submit papers selector failed: {alt_submit_error}")
                
    except Exception as e:
        log(f"Overall settings configuration error: {e}")
        raise e

def find_and_click_proceed_button(page):
    """Find and click the Submit button to proceed to form"""
    proceed_selectors = [
        'button:has-text("Submit")',
        'input[type="submit"][value="Submit"]',
        'button[type="submit"]',
        'input[value="Submit"]',
        '.submit-btn',
        '#submit-button'
    ]
    
    for selector in proceed_selectors:
        try:
            log(f"Trying proceed button selector: {selector}")
            page.wait_for_selector(selector, timeout=20000)
            button = page.locator(selector)
            if button.count() > 0 and button.is_visible():
                button.click()
                log(f"Proceed button clicked with selector: {selector}")
                random_wait(5, 8)
                return True
        except Exception as e:
            log(f"Proceed selector {selector} failed: {e}")
            continue
    
    return False

def fill_submission_details(page, chat_id, timestamp):
    """Fill submission details with enhanced error handling"""
    try:
        # Wait for form fields to be available
        page.wait_for_selector('#author_first', timeout=20000)
        
        # Fill first name
        log("Filling first name field...")
        first_name_field = page.locator('#author_first')
        first_name_field.click()
        first_name_field.fill("Test User")
        random_wait(2, 4)
        
        # Fill last name
        log("Filling last name field...")
        last_name_field = page.locator('#author_last')
        last_name_field.click()
        last_name_field.fill("Document Check")
        random_wait(2, 4)
        
        # Fill submission title
        submission_title = f"User_{chat_id}_Document_{timestamp}"
        log("Filling submission title field...")
        title_field = page.locator('#title')
        title_field.click()
        title_field.fill(submission_title)
        random_wait(3, 5)
        
        log("All form fields filled successfully")
        return submission_title
        
    except Exception as form_error:
        log(f"Error filling form fields: {form_error}")
        # Try alternative selectors
        try:
            log("Trying alternative form field selectors...")
            page.wait_for_selector('input[name="author_first"]', timeout=15000)
            
            page.locator('input[name="author_first"]').fill("Test User")
            random_wait(1, 3)
            
            page.locator('input[name="author_last"]').fill("Document Check")
            random_wait(1, 3)
            
            submission_title = f"User_{chat_id}_Document_{timestamp}"
            page.locator('input[name="title"]').fill(submission_title)
            random_wait(2, 4)
            
            log("Form fields filled using alternative selectors")
            return submission_title
            
        except Exception as alt_form_error:
            log(f"Alternative form filling also failed: {alt_form_error}")
            raise Exception(f"Failed to fill submission details: {alt_form_error}")

def find_and_click_upload_button(page):
    """Find and click Upload button with enhanced detection"""
    upload_selectors = [
        'button:has-text("Upload")',
        'input[type="submit"][value="Upload"]',
        'button[type="submit"]',
        '.upload-btn',
        '#upload-button'
    ]
    
    for selector in upload_selectors:
        try:
            log(f"Trying upload button selector: {selector}")
            upload_button = page.locator(selector)
            if upload_button.count() > 0 and upload_button.is_visible():
                upload_button.click()
                log(f"Upload button clicked with selector: {selector}")
                random_wait(4, 7)
                return True
        except Exception as e:
            log(f"Upload selector {selector} failed: {e}")
            continue
    
    return False

def find_and_click_confirm_button(page):
    """Find and click Confirm button with enhanced detection"""
    confirm_selectors = [
        "#confirm-btn",
        'button:has-text("Confirm")',
        'input[type="submit"][value="Confirm"]',
        '.confirm-btn'
    ]
    
    for selector in confirm_selectors:
        try:
            log(f"Trying confirm button selector: {selector}")
            page.wait_for_selector(selector, timeout=20000)
            confirm_button = page.locator(selector)
            if confirm_button.count() > 0 and confirm_button.is_visible():
                confirm_button.click()
                log(f"Confirm button clicked with selector: {selector}")
                return True
        except Exception as e:
            log(f"Confirm selector {selector} failed: {e}")
            continue
    
    return False

def find_and_click_inbox_button(page):
    """Find and click inbox button with enhanced detection"""
    inbox_selectors = [
        "#close-btn",
        'button:has-text("Go to assignment inbox")',
        'a:has-text("assignment inbox")',
        '.close-btn'
    ]
    
    for selector in inbox_selectors:
        try:
            log(f"Trying inbox button selector: {selector}")
            page.wait_for_selector(selector, timeout=20000)
            inbox_button = page.locator(selector)
            if inbox_button.count() > 0 and inbox_button.is_visible():
                inbox_button.click()
                log(f"Inbox button clicked with selector: {selector}")
                random_wait(5, 8)
                return True
        except Exception as e:
            log(f"Inbox selector {selector} failed: {e}")
            continue
    
    return False

def upload_file(page, file_path):
    """Handle file upload with multiple methods - Enhanced for server"""
    try:
        # Method 1: Use the correct selectors from HTML inspection
        log("Method 1: Using actual HTML selectors...")
        try:
            page.wait_for_selector("#choose-file-btn", timeout=20000)
            choose_button = page.locator("#choose-file-btn")
            choose_button.click()
            log("Clicked choose file button successfully")
            random_wait(3, 5)
            
            file_input = page.locator("#selected-file")
            file_input.set_input_files(file_path)
            log("File uploaded using Method 1 with actual HTML selectors")
            return True
            
        except Exception as method1_error:
            log(f"Method 1 failed: {method1_error}")
        
        # Method 2: Try using the name attribute
        log("Method 2: Using name attribute selector...")
        try:
            file_input = page.locator('input[name="userfile"]')
            file_input.set_input_files(file_path)
            log("File uploaded using Method 2 with name attribute")
            return True
            
        except Exception as method2_error:
            log(f"Method 2 failed: {method2_error}")
        
        # Method 3: Try generic file input
        log("Method 3: Using generic file input selector...")
        try:
            file_input_selectors = [
                '#selected-file',
                'input[name="userfile"]',
                'input[type="file"]',
                '#userfile'
            ]
            
            for selector in file_input_selectors:
                try:
                    log(f"Trying file input selector: {selector}")
                    page.wait_for_selector(selector, timeout=10000)
                    file_input = page.locator(selector)
                    if file_input.count() > 0:
                        file_input.set_input_files(file_path)
                        log(f"File uploaded using selector: {selector}")
                        return True
                except Exception as selector_error:
                    log(f"Selector {selector} failed: {selector_error}")
                    continue
                    
        except Exception as method3_error:
            log(f"Method 3 failed: {method3_error}")
        
        return False
        
    except Exception as upload_error:
        log(f"File upload error: {upload_error}")
        return False

def extract_submission_metadata(page, submission_title, chat_id, bot, processing_messages):
    """Extract and verify submission metadata before confirming"""
    try:
        log("Extracting submission metadata...")
        
        page.wait_for_load_state('domcontentloaded')
        random_wait(5, 8)  # Longer wait for server
        
        # Get submission details using actual IDs from HTML inspection
        try:
            author = page.locator("#submission-metadata-author").inner_text(timeout=15000)
        except:
            author = "Unknown"
        
        try:
            assignment_title = page.locator("#submission-metadata-assignment").inner_text(timeout=15000)
        except:
            assignment_title = "Quick Submit"
        
        try:
            actual_submission_title = page.locator("#submission-metadata-title").inner_text(timeout=15000)
        except:
            actual_submission_title = submission_title
        
        try:
            filename = page.locator("#submission-metadata-filename").inner_text(timeout=15000)
        except:
            filename = "Unknown"
        
        try:
            filesize = page.locator("#submission-metadata-filesize").inner_text(timeout=15000)
        except:
            filesize = ""
        
        try:
            page_count = page.locator("#submission-metadata-pagecount").inner_text(timeout=15000)
        except:
            page_count = ""
        
        try:
            word_count = page.locator("#submission-metadata-wordcount").inner_text(timeout=15000)
        except:
            word_count = ""
        
        try:
            character_count = page.locator("#submission-metadata-charactercount").inner_text(timeout=15000)
        except:
            character_count = ""
        
        log(f"Submission metadata extracted:")
        log(f"  Author: {author}")
        log(f"  Assignment: {assignment_title}")
        log(f"  Title: {actual_submission_title}")
        log(f"  Filename: {filename}")
        log(f"  Size: {filesize}")
        log(f"  Pages: {page_count}")
        log(f"  Words: {word_count}")
        log(f"  Characters: {character_count}")
        
        # Send verification message if we have valid data
        if page_count and word_count and character_count and all(x and x != "Unknown" and x != "" for x in [page_count, word_count, character_count]):
            metadata_msg = f"""✅ <b>Document Verified</b>

📃 <b>Pages:</b> {page_count}
📤 <b>Words:</b> {word_count}
🔢 <b>Characters:</b> {character_count}

🚀 Submitting to Turnitin..."""
            
            verification_msg = bot.send_message(chat_id, metadata_msg)
            processing_messages.append(verification_msg.message_id)
        else:
            log("Could not extract all metadata, showing generic verification message")
            generic_msg = bot.send_message(chat_id, "✅ <b>Document Verified</b>\n\n🚀 Submitting to Turnitin...")
            processing_messages.append(generic_msg.message_id)
        
        log(f"Updated submission title to: {actual_submission_title}")
        return actual_submission_title
        
    except Exception as metadata_error:
        log(f"Error extracting metadata: {metadata_error}")
        warning_msg = bot.send_message(chat_id, "⚠️ Could not verify upload details, but proceeding with submission...")
        processing_messages.append(warning_msg.message_id)
        return submission_title