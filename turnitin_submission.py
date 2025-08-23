import os
import time
import base64
from datetime import datetime
from turnitin_auth import log, random_wait

def submit_document(page, file_path, chat_id, timestamp, bot, processing_messages):
    """Handle document submission process - Enhanced for headless mode"""
    
    # Take a screenshot for debugging
    try:
        page.screenshot(path="debug_submit_page.png")
        log("Screenshot saved: debug_submit_page.png")
    except Exception as screenshot_error:
        log(f"Could not take screenshot: {screenshot_error}")
    
    # Wait for page to be fully loaded
    page.wait_for_load_state('networkidle', timeout=30000)
    
    # Analyze the page for Submit buttons
    log("Analyzing page for Submit buttons...")
    try:
        all_links = page.locator('a').all()
        all_buttons = page.locator('button').all()
        
        log(f"Found {len(all_links)} links and {len(all_buttons)} buttons on page")
        
        # Look for Submit-related elements
        submit_candidates = []
        
        # Check links
        for i, link in enumerate(all_links[:20]):
            try:
                text = link.inner_text()
                href = link.get_attribute('href') or ''
                class_name = link.get_attribute('class') or ''
                
                if any(keyword in text.lower() for keyword in ['submit', 'continue', 'next']) or 'submit' in class_name.lower():
                    submit_candidates.append(('link', i, text, href, class_name))
                    log(f"Submit candidate link {i}: '{text}' -> {href} (class: {class_name})")
            except Exception as link_error:
                log(f"Error analyzing link {i}: {link_error}")
                continue
        
        # Check buttons
        for i, button in enumerate(all_buttons[:20]):
            try:
                text = button.inner_text()
                type_attr = button.get_attribute('type') or ''
                class_name = button.get_attribute('class') or ''
                
                if any(keyword in text.lower() for keyword in ['submit', 'continue', 'next']) or type_attr == 'submit':
                    submit_candidates.append(('button', i, text, type_attr, class_name))
                    log(f"Submit candidate button {i}: '{text}' (type: {type_attr}, class: {class_name})")
            except Exception as button_error:
                log(f"Error analyzing button {i}: {button_error}")
                continue
        
        log(f"Found {len(submit_candidates)} Submit candidates")
        
    except Exception as analysis_error:
        log(f"Error analyzing page: {analysis_error}")
    
    log("Clicking Submit button...")
    
    # Try multiple Submit button selectors with better error handling
    submit_selectors = [
        'a.matte_button.submit_paper_button',
        'a:has-text("Submit")',
        'button:has-text("Submit")',
        'a[href*="submit"]',
        'a.submit_paper_button',
        '.matte_button:has-text("Submit")',
        'a.matte_button',
        'input[type="submit"]',
        'button[type="submit"]'
    ]
    
    submit_clicked = False
    
    for i, selector in enumerate(submit_selectors):
        try:
            log(f"Trying Submit selector {i+1}: {selector}")
            # Wait for elements to be available
            page.wait_for_selector(selector, timeout=10000)
            elements = page.locator(selector).all()
            
            if elements:
                log(f"Found {len(elements)} elements with selector: {selector}")
                for j, element in enumerate(elements):
                    try:
                        text = element.inner_text()
                        visible = element.is_visible()
                        log(f"  Element {j+1}: '{text}', visible: {visible}")
                        
                        if visible and 'submit' in text.lower():
                            log(f"Clicking Submit element: '{text}' with selector: {selector}")
                            element.click()
                            log("Submit button clicked successfully")
                            submit_clicked = True
                            random_wait(4, 7)  # Increased wait for headless
                            break
                    except Exception as element_error:
                        log(f"Error with element {j+1}: {element_error}")
                        continue
                
                if submit_clicked:
                    break
            else:
                log(f"No elements found with selector: {selector}")
                
        except Exception as selector_error:
            log(f"Submit selector {selector} failed: {selector_error}")
            continue
    
    if not submit_clicked:
        raise Exception("Failed to click Submit button with any selector")

    # Configure submission settings - Enhanced error handling and waits
    log("Configuring submission settings...")
    
    # Wait for the settings page to load
    page.wait_for_load_state('networkidle', timeout=30000)
    random_wait(3, 5)
    
    try:
        # Check all search options using the correct selectors with better error handling
        log("Checking 'Search the internet' option...")
        try:
            internet_checkbox = page.locator("label").filter(has_text="Search the internet").get_by_role("checkbox")
            if not internet_checkbox.is_checked():
                internet_checkbox.check()
            random_wait(2, 3)  # Increased wait
        except Exception as internet_error:
            log(f"Internet search checkbox error: {internet_error}")
        
        log("Checking 'Search student papers' option...")
        try:
            student_checkbox = page.locator("label").filter(has_text="Search student papers").get_by_role("checkbox")
            if not student_checkbox.is_checked():
                student_checkbox.check()
            random_wait(2, 3)
        except Exception as student_error:
            log(f"Student papers checkbox error: {student_error}")
        
        log("Checking 'Search periodicals, journals' option...")
        try:
            periodicals_checkbox = page.locator("label").filter(has_text="Search periodicals, journals").get_by_role("checkbox")
            if not periodicals_checkbox.is_checked():
                periodicals_checkbox.check()
            random_wait(2, 3)
        except Exception as periodicals_error:
            log(f"Periodicals checkbox error: {periodicals_error}")
        

        # Set submit papers option - Enhanced error handling
        log("Setting submit papers option...")
        try:
            submit_papers_select = page.get_by_label("Submit papers to: Standard")
            submit_papers_select.select_option("0")
            random_wait(3, 4)  # Increased wait
        except Exception as submit_papers_error:
            log(f"Submit papers option error: {submit_papers_error}")
            # Try alternative selector
            try:
                page.locator('select[name="submit_papers_to"]').select_option("0")
                random_wait(3, 4)
            except Exception as alt_submit_error:
                log(f"Alternative submit papers selector failed: {alt_submit_error}")
        
        log("All submission settings configured successfully")
    except Exception as e:
        log(f"Error configuring submission settings: {e}")
        raise Exception(f"Failed to configure settings: {e}")

    log("Clicking Submit to proceed...")
    try:
        # Wait for the submit button to be ready
        page.wait_for_selector('button:has-text("Submit")', timeout=15000)
        submit_button = page.get_by_role("button", name="Submit")
        submit_button.click()
        log("Submit button (to proceed) clicked successfully")
        random_wait(4, 7)  # Increased wait for headless
    except Exception as e:
        log(f"Error clicking Submit to proceed: {e}")
        # Try alternative selector
        try:
            log("Trying alternative Submit button selector...")
            page.locator('input[type="submit"][value="Submit"]').click()
            log("Submit button clicked with alternative selector")
            random_wait(4, 7)
        except Exception as e2:
            log(f"Alternative Submit button also failed: {e2}")
            raise Exception(f"Failed to click Submit to proceed: {e2}")

    # Wait for the form page to load
    page.wait_for_load_state('networkidle', timeout=30000)
    random_wait(3, 5)

    # Fill submission details - Fixed selectors based on HTML inspection
    log("Filling submission details...")
    
    try:
        # Wait for form fields to be available using actual IDs from HTML
        page.wait_for_selector('#author_first', timeout=15000)
        
        # Fill first name using actual ID from HTML
        log("Filling first name field...")
        first_name_field = page.locator('#author_first')
        first_name_field.click()
        first_name_field.fill("Test User")
        random_wait(2, 3)
        
        # Fill last name using actual ID from HTML
        log("Filling last name field...")
        last_name_field = page.locator('#author_last')
        last_name_field.click()
        last_name_field.fill("Document Check")
        random_wait(2, 3)
        
        # Include user ID first in submission title for easy identification
        submission_title = f"User_{chat_id}_Document_{timestamp}"
        log("Filling submission title field...")
        title_field = page.locator('#title')
        title_field.click()
        title_field.fill(submission_title)
        random_wait(3, 4)
        
        log("All form fields filled successfully")
        
    except Exception as form_error:
        log(f"Error filling form fields: {form_error}")
        # Try alternative approach with different selectors
        try:
            log("Trying alternative form field selectors...")
            
            # Alternative selectors based on name attributes
            page.wait_for_selector('input[name="author_first"]', timeout=10000)
            
            # Fill using name attributes
            page.locator('input[name="author_first"]').fill("Test User")
            random_wait(1, 2)
            
            page.locator('input[name="author_last"]').fill("Document Check")
            random_wait(1, 2)
            
            submission_title = f"User_{chat_id}_Document_{timestamp}"
            page.locator('input[name="title"]').fill(submission_title)
            random_wait(2, 3)
            
            log("Form fields filled using alternative selectors")
            
        except Exception as alt_form_error:
            log(f"Alternative form filling also failed: {alt_form_error}")
            raise Exception(f"Failed to fill submission details with any method: {alt_form_error}")

    # Upload file - Enhanced for headless mode
    log(f"Uploading file from path: {file_path}")
    
    # Wait before file upload
    log("Waiting 5 seconds before file upload...")
    msg = bot.send_message(chat_id, "📎 Preparing document upload...")
    processing_messages.append(msg.message_id)
    page.wait_for_timeout(5000)
    
    upload_success = upload_file(page, file_path)
    
    if not upload_success:
        raise Exception("All file upload methods failed")

    random_wait(4, 6)  # Increased wait for headless

    # Wait for file selection confirmation - Enhanced timeout
    try:
        log("Waiting for file selection confirmation...")
        # Try to wait for metadata to appear as confirmation
        page.wait_for_selector("#submission-metadata-filename", timeout=15000)  # Increased timeout
        log("File selection confirmed by metadata appearance")
        random_wait(2, 3)
    except Exception as confirm_error:
        log(f"File selection confirmation failed: {confirm_error}")
        # Continue anyway, might still work

    log("Clicking Upload button...")
    try:
        upload_button = page.get_by_role("button", name="Upload")
        upload_button.click()
        log("Upload button clicked successfully")
        random_wait(3, 5)  # Increased wait
    except Exception as upload_btn_error:
        log(f"Error clicking Upload button: {upload_btn_error}")
        raise Exception(f"Failed to click Upload button: {upload_btn_error}")

    # Handle privacy notice if it appears
    try:
        if page.get_by_text("We take your privacy very").is_visible(timeout=5000):
            page.get_by_text("We take your privacy very").click()
            random_wait(2, 3)
    except:
        log("Privacy notice not found, continuing...")

    # Wait before confirming and verify upload details - UPDATED TO 50 SECONDS
    log("Waiting 50 seconds before confirming document...")
    msg = bot.send_message(chat_id, "📤 Document uploaded, verifying details...")
    processing_messages.append(msg.message_id)
    page.wait_for_timeout(50000)  # Changed from 10000 to 50000 (50 seconds)

    # Extract and verify submission metadata before confirming
    actual_submission_title = extract_submission_metadata(page, submission_title, chat_id, bot, processing_messages)

    log("Clicking Confirm button...")
    try:
        # Wait for confirm button to be ready
        page.wait_for_selector("#confirm-btn", timeout=15000)
        confirm_button = page.locator("#confirm-btn")
        confirm_button.click()
        log("Confirm button clicked successfully")
    except Exception as confirm_error:
        log(f"Error clicking Confirm button: {confirm_error}")
        # Try alternative selector
        try:
            page.get_by_role("button", name="Confirm").click()
            log("Confirm button clicked with alternative selector")
        except Exception as alt_confirm_error:
            log(f"Alternative Confirm button also failed: {alt_confirm_error}")
            raise Exception(f"Failed to click Confirm button: {alt_confirm_error}")

    # Wait up to 60 seconds before clicking "Go to assignment inbox"
    log("Waiting up to 60 seconds for processing...")
    msg = bot.send_message(chat_id, "⏳ Document submitted, waiting for processing to complete...")
    processing_messages.append(msg.message_id)
    page.wait_for_timeout(60000)

    log("Clicking 'Go to assignment inbox'...")
    try:
        # Wait for the inbox button to be available
        page.wait_for_selector("#close-btn", timeout=15000)
        inbox_button = page.locator("#close-btn")
        inbox_button.click()
        log("Go to assignment inbox clicked successfully")
        random_wait(4, 6)  # Increased wait
    except Exception as inbox_error:
        log(f"Error clicking Go to assignment inbox: {inbox_error}")
        # Try alternative selector
        try:
            page.get_by_role("button", name="Go to assignment inbox").click()
            log("Go to assignment inbox clicked using alternative selector")
            random_wait(4, 6)
        except Exception as alt_inbox_error:
            log(f"Alternative inbox button also failed: {alt_inbox_error}")
            # Continue anyway, we might be able to find the submission

    # Wait 60 seconds before navigating back
    log("Waiting 60 seconds before navigating to Quick Submit...")
    msg = bot.send_message(chat_id, "⏰ Waiting for document to appear in submissions list...")
    processing_messages.append(msg.message_id)
    page.wait_for_timeout(60000)

    return actual_submission_title

def upload_file(page, file_path):
    """Handle file upload with multiple methods - Fixed based on actual HTML"""
    try:
        # Method 1: Use the correct selectors from HTML inspection
        log("Method 1: Using actual HTML selectors...")
        try:
            # Wait for the choose file button using actual ID from HTML
            page.wait_for_selector("#choose-file-btn", timeout=15000)
            choose_button = page.locator("#choose-file-btn")
            choose_button.click()
            log("Clicked choose file button successfully")
            random_wait(2, 3)
            
            # Set the file using the actual hidden input ID from HTML
            file_input = page.locator("#selected-file")
            file_input.set_input_files(file_path)
            log("File uploaded using Method 1 with actual HTML selectors")
            return True
            
        except Exception as method1_error:
            log(f"Method 1 failed: {method1_error}")
        
        # Method 2: Try using the name attribute from HTML
        log("Method 2: Using name attribute selector...")
        try:
            # Set the file directly using name attribute from HTML
            file_input = page.locator('input[name="userfile"]')
            file_input.set_input_files(file_path)
            log("File uploaded using Method 2 with name attribute")
            return True
            
        except Exception as method2_error:
            log(f"Method 2 failed: {method2_error}")
        
        # Method 3: Try the codegen approach from your working example
        log("Method 3: Using codegen approach...")
        try:
            # Based on your working codegen example
            choose_link = page.get_by_role("link", name="Choose from this computer")
            choose_link.click()
            log("Clicked choose button with role selector")
            random_wait(2, 3)
            
            # Set the file using the role selector approach
            choose_link.set_input_files(file_path)
            log("File uploaded using Method 3 with codegen approach")
            return True
            
        except Exception as method3_error:
            log(f"Method 3 failed: {method3_error}")
        
        # Method 4: Direct file input approach with multiple selectors
        log("Method 4: Direct file input with multiple selectors...")
        try:
            # Wait for the page to be fully loaded
            page.wait_for_load_state('domcontentloaded')
            random_wait(2, 3)
            
            # Try to find file input by different selectors based on HTML
            file_input_selectors = [
                '#selected-file',           # From HTML inspection
                'input[name="userfile"]',   # From HTML inspection
                'input[type="file"]',       # Generic file input
                '#userfile'                 # Alternative ID
            ]
            
            for selector in file_input_selectors:
                try:
                    log(f"Trying file input selector: {selector}")
                    page.wait_for_selector(selector, timeout=5000)
                    file_input = page.locator(selector)
                    if file_input.count() > 0:
                        file_input.set_input_files(file_path)
                        log(f"File uploaded using Method 4 with selector: {selector}")
                        return True
                except Exception as selector_error:
                    log(f"Selector {selector} failed: {selector_error}")
                    continue
                    
        except Exception as method4_error:
            log(f"Method 4 failed: {method4_error}")
        
        # Method 5: JavaScript approach for stubborn cases
        log("Method 5: JavaScript file upload...")
        try:
            # Read the file content and convert to base64
            with open(file_path, 'rb') as f:
                file_content = f.read()
            
            file_base64 = base64.b64encode(file_content).decode('utf-8')
            file_name = os.path.basename(file_path)
            
            # Use JavaScript to create and trigger file selection
            js_code = f"""
            const fileInput = document.querySelector('#selected-file') || 
                             document.querySelector('input[name="userfile"]') || 
                             document.querySelector('input[type="file"]');
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
                return True
            else:
                log("JavaScript method failed - no file input found")
                
        except Exception as js_error:
            log(f"JavaScript upload method failed: {js_error}")
        
        return False
        
    except Exception as upload_error:
        log(f"File upload error: {upload_error}")
        return False

def extract_submission_metadata(page, submission_title, chat_id, bot, processing_messages):
    """Extract and verify submission metadata before confirming - Fixed selectors from HTML"""
    try:
        log("Extracting submission metadata...")
        
        # Wait for the metadata to be loaded with longer timeout
        page.wait_for_load_state('domcontentloaded')
        random_wait(3, 4)
        
        # Get submission details using actual IDs from HTML inspection
        try:
            author = page.locator("#submission-metadata-author").inner_text(timeout=10000)
        except:
            author = "Unknown"
        
        try:
            assignment_title = page.locator("#submission-metadata-assignment").inner_text(timeout=10000)
        except:
            assignment_title = "Quick Submit"
        
        try:
            actual_submission_title = page.locator("#submission-metadata-title").inner_text(timeout=10000)
        except:
            actual_submission_title = submission_title  # Use our original title as fallback
        
        try:
            filename = page.locator("#submission-metadata-filename").inner_text(timeout=10000)
        except:
            filename = "Unknown"
        
        try:
            filesize = page.locator("#submission-metadata-filesize").inner_text(timeout=10000)
        except:
            filesize = ""
        
        try:
            page_count = page.locator("#submission-metadata-pagecount").inner_text(timeout=10000)
        except:
            page_count = ""
        
        try:
            word_count = page.locator("#submission-metadata-wordcount").inner_text(timeout=10000)
        except:
            word_count = ""
        
        try:
            character_count = page.locator("#submission-metadata-charactercount").inner_text(timeout=10000)
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
        
        # Only send verification message if we have valid data
        if page_count and word_count and character_count and all(x and x != "Unknown" and x != "" for x in [page_count, word_count, character_count]):
            # Send simplified metadata to user (only essential info)
            metadata_msg = f"""✅ <b>Document Verified</b>

📃 <b>Pages:</b> {page_count}
📤 <b>Words:</b> {word_count}
🔢 <b>Characters:</b> {character_count}

🚀 Submitting to Turnitin..."""
            
            verification_msg = bot.send_message(chat_id, metadata_msg)
            processing_messages.append(verification_msg.message_id)
        else:
            # If we can't get the metadata, show a generic message
            log("Could not extract all metadata, showing generic verification message")
            generic_msg = bot.send_message(chat_id, "✅ <b>Document Verified</b>\n\n🚀 Submitting to Turnitin...")
            processing_messages.append(generic_msg.message_id)
        
        # Update our submission title to match what Turnitin assigned
        log(f"Updated submission title to: {actual_submission_title}")
        return actual_submission_title
        
    except Exception as metadata_error:
        log(f"Error extracting metadata: {metadata_error}")
        # Continue anyway, but warn user
        warning_msg = bot.send_message(chat_id, "⚠️ Could not verify upload details, but proceeding with submission...")
        processing_messages.append(warning_msg.message_id)
        return submission_title