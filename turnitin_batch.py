import os
import time
from datetime import datetime
from turnitin_auth import browser_session, log, random_wait
from turnitin_helpers import get_available_students, add_student_submission, load_student_tracking, save_student_tracking
from queue_manager import get_pending_items  # For dynamic queue checking

def extract_students_from_page(page):
    """Extract student list from Multiple File Upload page"""
    try:
        log("Extracting students from page...")

        # Multiple possible selectors for student dropdown (updated based on user's actual HTML)
        student_dropdown_selectors = [
            'select.constrain_dropdown',    # Primary - class-based selector from user's HTML
            'select[name="userID_0"]',      # Specific first field name
            'select[name*="userID"]',       # Any userID field (userID_0, userID_1, etc.)
            'select[name="sid"]'            # Legacy format fallback
        ]

        student_dropdown = None
        for selector in student_dropdown_selectors:
            try:
                log(f"Trying student dropdown selector: {selector}")
                page.wait_for_selector(selector, timeout=5000)
                student_dropdown = page.locator(selector).first
                if student_dropdown.count() > 0:
                    log(f"✓ Found student dropdown with selector: {selector}")
                    break
            except Exception as e:
                log(f"Selector {selector} failed: {e}")
                continue

        if not student_dropdown:
            log("⚠️ No student dropdown found with any selector")
            return []

        # Get all option elements from student dropdown
        student_options = student_dropdown.locator('option').all()
        
        students = []
        for option in student_options:
            try:
                student_id = option.get_attribute("value")
                student_name = option.inner_text().strip()
                
                # Skip empty or placeholder options
                if student_id and student_id != "" and student_name:
                    students.append({
                        "id": student_id,
                        "name": student_name
                    })
                    log(f"Found student: {student_name} (ID: {student_id})")
            except Exception as e:
                log(f"Error extracting student option: {e}")
                continue
        
        log(f"Extracted {len(students)} students from page")
        return students
        
    except Exception as e:
        log(f"Error extracting students: {e}")
        return []

def save_students_to_tracking(assignment_name, students):
    """Save extracted students to tracking file"""
    tracking = load_student_tracking()
    
    if assignment_name not in tracking:
        tracking[assignment_name] = {"students": [], "submissions": {}}
    
    tracking[assignment_name]["students"] = students
    save_student_tracking(tracking)
    log(f"Saved {len(students)} students for {assignment_name}")

def generate_submission_title(user_id, timestamp):
    """Generate unique submission title under 15 characters"""
    import hashlib

    # Use shorter components to ensure under 15 chars
    user_part = str(user_id)[-4:]  # Last 4 digits of user ID
    time_part = timestamp.replace("-", "").replace(":", "").replace("T", "").replace(" ", "")[-6:]  # Last 6 digits of timestamp

    # Add hash component for uniqueness (4 chars from user_id+timestamp hash)
    hash_input = f"{user_id}{timestamp}".encode()
    hash_part = hashlib.md5(hash_input).hexdigest()[:4]

    # Format: user4chars + time6chars + hash4chars = 14 chars max (safely under Turnitin 15 limit)
    title = f"{user_part}{time_part}{hash_part}"
    log(f"Generated unique title: {title} (length: {len(title)})")
    return title

def submit_batch(page, queue_items, assignment_name):
    """Submit multiple files in batch with correct workflow: upload first, then extract students"""
    try:
        log(f"Starting batch submission for {len(queue_items)} files to {assignment_name}")

        # Validate browser session is still alive before starting
        try:
            current_url = page.url
            page.evaluate("() => window.location.href")  # Test page responsiveness
            log(f"✓ Browser session validated - Current URL: {current_url}")
        except Exception as session_error:
            log(f"⚠️ Browser session validation failed: {session_error}")
            return False

        # STEP 1: Upload ONE file first to trigger student dropdown
        log("Uploading first file to reveal student dropdown...")
        first_file = queue_items[0]["file_path"]

        # Find the file upload input (handle multiple file inputs on page)
        try:
            # Wait for page to be ready
            page.wait_for_load_state('networkidle', timeout=10000)
            log("Page loaded, looking for file input...")

            # Look for file input with multiple strategies
            file_input = None
            selectors = [
                'input[type="file"][name="userfile"]',
                'input[type="file"]',
                '.file_browse_container input[type="file"]'
            ]

            for selector in selectors:
                try:
                    elements = page.locator(selector).all()
                    log(f"Found {len(elements)} file inputs with selector: {selector}")

                    if elements:
                        # Use the first visible/enabled input
                        for elem in elements:
                            try:
                                if elem.is_visible() and elem.is_enabled():
                                    file_input = elem
                                    log(f"Using visible file input")
                                    break
                            except:
                                continue

                        if not file_input and elements:
                            # If no visible inputs, just use first one
                            file_input = elements[0]
                            log(f"Using first file input (not checking visibility)")

                        if file_input:
                            break
                except Exception as e:
                    log(f"Selector {selector} failed: {e}")
                    continue

            if not file_input:
                log("⚠️ No file input found on page, but continuing...")
                return False

            # Upload the file
            log(f"Uploading file: {os.path.basename(first_file)}")
            try:
                file_input.set_input_files(first_file)
                log(f"✓ File selected for upload: {os.path.basename(first_file)}")
            except Exception as upload_error:
                log(f"⚠️ File upload selection failed: {upload_error}")
                return False

        except Exception as e:
            log(f"⚠️ File upload process error: {e}")
            return False

        # STEP 2: Wait for file to appear AND student dropdown to become visible with polling
        log("Waiting for file upload to complete and student dropdown to become visible...")

        # Poll every 10 seconds for up to 2 minutes (12 attempts) - file uploads can take time
        max_attempts = 12  # 2 minutes total
        attempt = 0
        dropdown_ready = False

        while attempt < max_attempts and not dropdown_ready:
            attempt += 1
            log(f"Polling attempt {attempt}/{max_attempts} - waiting for upload completion and dropdown visibility...")

            try:
                # First check if file appeared in table
                file_appeared = False
                file_rows = page.locator('#attached_files_table_body tr.file_row').all()
                if file_rows and len(file_rows) > 0:
                    log(f"✓ Found {len(file_rows)} file(s) in attached files table")
                    file_appeared = True
                else:
                    # Alternative selectors for file table
                    alt_selectors = [
                        'table tr:has(td:text("' + os.path.basename(first_file) + '"))',
                        'tr.uploaded_file',
                        'tr[class*="file"]',
                        'tbody tr'
                    ]

                    for selector in alt_selectors:
                        try:
                            alt_rows = page.locator(selector).all()
                            if alt_rows and len(alt_rows) > 0:
                                log(f"✓ Found file using alternative selector: {selector}")
                                file_appeared = True
                                break
                        except:
                            continue

                # Now check for student dropdown visibility
                if file_appeared:
                    log("File found in table, checking for student dropdown visibility...")

                    # Try multiple dropdown selectors to find visible one
                    dropdown_selectors = [
                        'select.constrain_dropdown',
                        'select[name*="userID"]',
                        'select[name="userID_0"]',
                        'select[name="userID_1"]'
                    ]

                    for dropdown_selector in dropdown_selectors:
                        try:
                            dropdowns = page.locator(dropdown_selector).all()
                            log(f"Found {len(dropdowns)} dropdowns with selector: {dropdown_selector}")

                            for i, dropdown in enumerate(dropdowns):
                                try:
                                    is_visible = dropdown.is_visible()
                                    is_enabled = dropdown.is_enabled()
                                    log(f"Dropdown {i+1}: visible={is_visible}, enabled={is_enabled}")

                                    if is_visible and is_enabled:
                                        options = dropdown.locator('option').all()
                                        if len(options) > 1:  # More than just placeholder option
                                            log(f"✓ Student dropdown is ready with {len(options)} options!")
                                            dropdown_ready = True
                                            break
                                except Exception as dropdown_error:
                                    log(f"Error checking dropdown {i+1}: {dropdown_error}")

                            if dropdown_ready:
                                break

                        except Exception as selector_error:
                            log(f"Dropdown selector {dropdown_selector} failed: {selector_error}")
                            continue

                    if dropdown_ready:
                        break

                # Log current status
                status = "File appeared" if file_appeared else "File not appeared"
                status += ", Dropdown ready" if dropdown_ready else ", Dropdown not ready"
                log(f"Status: {status}")

                if attempt < max_attempts:
                    log(f"Not ready yet, waiting 10 seconds... (attempt {attempt}/{max_attempts})")
                    time.sleep(10)  # Wait exactly 10 seconds as requested
                    
                    # Validate browser is still alive after wait
                    try:
                        page.evaluate("() => window.location.href")
                    except Exception as browser_check:
                        log(f"⚠️ Browser session lost during polling: {browser_check}")
                        return False

            except Exception as e:
                log(f"Error during polling (attempt {attempt}): {e}")
                if attempt < max_attempts:
                    time.sleep(10)

        if not dropdown_ready:
            log("⚠️ Student dropdown not visible after 2 minutes, but continuing with extraction anyway...")
        else:
            log("✅ Upload completed and student dropdown is visible and ready!")

        # STEP 3: NOW extract students from page (dropdown should be populated)
        log("Now extracting students from populated dropdown...")
        page_students = extract_students_from_page(page)
        if not page_students:
            # Try to get page HTML for debugging
            try:
                page_content = page.content()
                log(f"Page content preview: {page_content[:500]}...")
            except:
                pass
            log("⚠️ No students found on page, but continuing with workflow...")
            # Don't crash - return False to indicate failure but don't throw exception
            return False

        # Save students to tracking
        save_students_to_tracking(assignment_name, page_students)
        log(f"✓ Extracted and saved {len(page_students)} students")

        # STEP 4: Get available students (not at 24h limit)
        available_students = get_available_students(assignment_name)

        # After extracting students, should have a valid student list
        if available_students == "NEEDS_STUDENT_DATA":
            log("⚠️ Still no student data after extraction - continuing anyway")
            return False

        if not isinstance(available_students, list) or len(available_students) == 0:
            log("⚠️ No available students in current assignment")
            return False

        log(f"Found {len(available_students)} available students")

        # DYNAMIC FORM FIELD DETECTION
        log("Detecting form fields dynamically...")

        # Find all file input fields - these are pre-existing on the page
        # Turnitin typically provides 8 file input fields by default
        file_inputs = page.locator('input[type="file"]').all()
        log(f"Found {len(file_inputs)} file input fields")

        # Find all student dropdown fields by looking for ALL dropdowns with userID pattern
        # Don't filter by file_row yet - we want to count total available capacity
        # CRITICAL: Must filter out the template row which has name="userID_" (hidden)
        student_selects = []
        
        # Strategy: Get all dropdowns with numbered userID fields (userID_0, userID_1, etc.)
        # These exist on the page even before files are uploaded
        try:
            # Get all select elements with userID pattern
            all_selects = page.locator('select[name^="userID_"]').all()
            log(f"Found {len(all_selects)} total userID dropdowns")
            
            # Filter to only numbered ones (userID_0, userID_1, etc.), exclude template (userID_)
            for select in all_selects:
                try:
                    name_attr = select.get_attribute('name')
                    # Check if name ends with a digit (userID_0, userID_1, etc.)
                    if name_attr and name_attr != 'userID_' and name_attr[-1].isdigit():
                        student_selects.append(select)
                        log(f"Added dropdown: {name_attr}")
                except Exception as e:
                    log(f"Error checking dropdown: {e}")
                    continue
                    
        except Exception as e:
            log(f"Error finding userID dropdowns: {e}")
            
        # Fallback: If no numbered dropdowns found, try the constrain_dropdown class approach
        if not student_selects:
            log("No numbered dropdowns found, trying class-based selection...")
            try:
                all_selects = page.locator('select.constrain_dropdown').all()
                # Filter to only visible ones (excludes hidden template)
                for select in all_selects:
                    try:
                        if select.is_visible():
                            student_selects.append(select)
                            log(f"Added visible dropdown")
                    except:
                        continue
            except Exception:
                pass
                    
        log(f"Found {len(student_selects)} student dropdown fields (excluding template)")

        # Find all title input fields by looking for ALL title inputs with numbered pattern
        # These exist on the page even before files are uploaded
        title_inputs = []
        
        # Strategy: Get all title inputs with numbered pattern (title_0, title_1, etc.)
        try:
            all_inputs = page.locator('input[name^="title_"]').all()
            log(f"Found {len(all_inputs)} total title inputs")
            
            # Filter to only numbered ones (title_0, title_1, etc.), exclude template (title_)
            for input_elem in all_inputs:
                try:
                    name_attr = input_elem.get_attribute('name')
                    # Check if name ends with a digit (title_0, title_1, etc.)
                    if name_attr and name_attr != 'title_' and name_attr[-1].isdigit():
                        title_inputs.append(input_elem)
                        log(f"Added title input: {name_attr}")
                except Exception as e:
                    log(f"Error checking title input: {e}")
                    continue
                    
        except Exception as e:
            log(f"Error finding title inputs: {e}")
            
        # Fallback: If no numbered title inputs found, try visible text inputs
        if not title_inputs:
            log("No numbered title inputs found, trying visible text inputs...")
            try:
                all_inputs = page.locator('input[type="text"]').all()
                # Filter to only visible ones (excludes hidden template)
                for input_elem in all_inputs:
                    try:
                        if input_elem.is_visible():
                            title_inputs.append(input_elem)
                            log(f"Added visible title input")
                    except:
                        continue
            except Exception:
                pass
                    
        log(f"Found {len(title_inputs)} title input fields (excluding template)")

        # Calculate maximum submissions based on available form fields and students
        max_form_submissions = min(len(file_inputs), len(student_selects), len(title_inputs))
        max_student_submissions = len(available_students)
        max_queue_submissions = len(queue_items)

        max_submissions = min(max_form_submissions, max_student_submissions, max_queue_submissions)

        log(f"Maximum submissions: {max_submissions} (Form fields: {max_form_submissions}, Available students: {max_student_submissions}, Queue items: {max_queue_submissions})")

        if max_submissions == 0:
            log("⚠️ No valid form fields or available students found")
            return False

        # Special handling for single file submission (as requested)
        if len(queue_items) == 1 and max_submissions >= 1:
            log("Single file submission detected - optimizing workflow")

        # Process each file in the queue with safety checks
        # Note: First file (index 0) is already uploaded to reveal student dropdown
        submitted_count = 0
        for i in range(max_submissions):
            try:
                queue_item = queue_items[i]
                student = available_students[i]
                file_path = queue_item["file_path"]
                user_id = queue_item["user_id"]
                timestamp = queue_item["timestamp"]

                log(f"Processing file {i+1}/{max_submissions}: {os.path.basename(file_path)}")

                # Use actual form elements detected dynamically
                file_input = file_inputs[i]
                student_select = student_selects[i]
                title_input = title_inputs[i]

                # Upload file using detected input (skip first file - already uploaded)
                if i == 0:
                    log(f"✓ First file already uploaded: {os.path.basename(file_path)}")
                else:
                    file_input.set_input_files(file_path)
                    log(f"✓ Uploaded file to field {i+1}")
                    random_wait(1, 2)

                # Select student - this triggers onchange="fill_name(this, i)" which auto-fills first/last name
                try:
                    log(f"Selecting student: {student['name']} (ID: {student['id']})")
                    student_select.select_option(student["id"])
                    log(f"✓ Selected student in dropdown")
                    
                    # Wait for auto-fill to complete (first name and last name fields should populate)
                    # The onchange event should trigger fill_name() which populates author_first_i and author_last_i
                    random_wait(2, 3)  # Give JavaScript time to execute
                    
                    # Verify the name fields were populated (optional but good for debugging)
                    try:
                        first_name_field = page.locator(f'input[name="author_first_{i}"]').first
                        last_name_field = page.locator(f'input[name="author_last_{i}"]').first
                        
                        first_name_value = first_name_field.input_value()
                        last_name_value = last_name_field.input_value()
                        
                        if first_name_value or last_name_value:
                            log(f"✓ Name auto-filled: {first_name_value} {last_name_value}")
                        else:
                            log(f"⚠️ Name fields empty - onchange may not have triggered")
                    except Exception as verify_error:
                        log(f"Could not verify name auto-fill: {verify_error}")
                    
                except Exception as select_error:
                    log(f"⚠️ Error selecting student: {select_error}")
                    queue_items[i]["status"] = "failed"
                    queue_items[i]["error"] = f"Could not select student: {select_error}"
                    continue

                # Generate and fill submission title using detected input
                title = generate_submission_title(user_id, timestamp)
                title_input.fill(title)
                log(f"✓ Filled title: {title}")
                random_wait(1, 2)

                # Update queue item with success status
                queue_item["student_id"] = student["id"]
                queue_item["student_name"] = student["name"]
                queue_item["submission_title"] = title
                queue_item["assignment"] = assignment_name
                queue_item["status"] = "processing"

                # Record submission in student tracking
                add_student_submission(assignment_name, student["id"], title)

                submitted_count += 1
                log(f"✓ Successfully prepared submission {submitted_count}")

            except Exception as file_error:
                log(f"✗ Error processing file {i+1}: {file_error}")
                queue_items[i]["status"] = "failed"
                queue_items[i]["error"] = str(file_error)
                continue
        
        if submitted_count == 0:
            log("No files were successfully prepared for submission")
            return False
        
        log(f"Prepared {submitted_count} files for submission")
        
        # ===== DYNAMIC QUEUE CHECKING =====
        # Check if there are files from the original batch that weren't uploaded yet
        # This happens when max_submissions was less than len(queue_items)
        log("Checking for remaining files from original batch...")
        try:
            # Files that were in the original batch but not uploaded yet
            remaining_files = queue_items[submitted_count:]  # Files after the ones we processed
            
            if remaining_files:
                log(f"✓ Found {len(remaining_files)} file(s) from original batch not yet uploaded!")
                
                # Check if we have capacity for more files
                # Now that form fields are correctly detected, we should have more capacity
                remaining_capacity = len(file_inputs) - submitted_count
                available_students_remaining = len(available_students) - submitted_count
                files_to_add = min(len(remaining_files), remaining_capacity, available_students_remaining)
                
                if files_to_add > 0:
                    log(f"Adding {files_to_add} remaining file(s) to current batch")
                    
                    for j in range(files_to_add):
                        try:
                            remaining_item = remaining_files[j]
                            file_index = submitted_count + j
                            student_index = submitted_count + j
                            
                            if student_index >= len(available_students):
                                log(f"No more students available, stopping at {file_index} files")
                                break
                            
                            student = available_students[student_index]
                            file_path = remaining_item["file_path"]
                            user_id = remaining_item["user_id"]
                            timestamp = remaining_item["timestamp"]
                            
                            log(f"Processing remaining file {file_index+1}: {os.path.basename(file_path)}")
                            
                            # Upload the file
                            if file_index < len(file_inputs):
                                file_input = file_inputs[file_index]
                                file_input.set_input_files(file_path)
                                log(f"✓ Uploaded file: {os.path.basename(file_path)}")
                                
                                # Wait for file to appear in table and dropdown to be ready
                                log(f"Waiting for file {file_index+1} to appear in table...")
                                file_appeared = False
                                dropdown_ready = False
                                
                                # Poll for up to 2 minutes (12 attempts x 10 seconds)
                                for wait_attempt in range(12):
                                    try:
                                        # Check if file appeared in table
                                        file_rows = page.locator('tr.file_row').all()
                                        if len(file_rows) >= file_index + 1:
                                            file_appeared = True
                                            log(f"✓ File {file_index+1} appeared in table ({len(file_rows)} total rows)")
                                            
                                            # Check if dropdown is ready for this file
                                            try:
                                                dropdown_selector = f'select[name="userID_{file_index}"]'
                                                dropdown = page.locator(dropdown_selector).first
                                                if dropdown.count() > 0 and dropdown.is_visible():
                                                    options = dropdown.locator('option').all()
                                                    if len(options) > 1:
                                                        dropdown_ready = True
                                                        log(f"✓ Dropdown for file {file_index+1} is ready")
                                                        break
                                            except:
                                                pass
                                        
                                        if wait_attempt < 11:
                                            log(f"File {file_index+1} not ready yet, waiting 10 seconds... (attempt {wait_attempt+1}/12)")
                                            time.sleep(10)
                                    except Exception as wait_error:
                                        log(f"Error during wait (attempt {wait_attempt+1}): {wait_error}")
                                        if wait_attempt < 11:
                                            time.sleep(10)
                                
                                if not file_appeared or not dropdown_ready:
                                    log(f"⚠️ File {file_index+1} upload timeout - file appeared: {file_appeared}, dropdown ready: {dropdown_ready}")
                                    continue
                                
                                # Now select student and fill title
                                # Re-locate the dropdown for this file (don't use student_selects which was populated before this file was uploaded)
                                try:
                                    dropdown_selector = f'select[name="userID_{file_index}"]'
                                    student_select = page.locator(dropdown_selector).first
                                    student_select.select_option(student["id"])
                                    log(f"✓ Selected student: {student['name']}")
                                    random_wait(2, 3)
                                    
                                    # Re-locate the title input for this file
                                    title_selector = f'input[name="title_{file_index}"]'
                                    title_input = page.locator(title_selector).first
                                    title = generate_submission_title(user_id, timestamp)
                                    title_input.fill(title)
                                    log(f"✓ Filled title: {title}")
                                    random_wait(1, 2)
                                    
                                    # Record submission
                                    add_student_submission(assignment_name, student["id"], title)
                                    
                                    # Update queue item
                                    remaining_item["student_id"] = student["id"]
                                    remaining_item["student_name"] = student["name"]
                                    remaining_item["submission_title"] = title
                                    remaining_item["assignment"] = assignment_name
                                    remaining_item["status"] = "processing"
                                    
                                    submitted_count += 1
                                    log(f"✓ Successfully added file to batch (total: {submitted_count})")
                                except Exception as fill_error:
                                    log(f"Error filling student/title for file {file_index+1}: {fill_error}")
                                    
                        except Exception as e:
                            log(f"Error adding remaining file {j+1}: {e}")
                            continue
                    
                    log(f"✅ Dynamic queue check complete! Total files in batch: {submitted_count}")
                else:
                    log(f"No capacity to add remaining files (capacity: {remaining_capacity}, remaining: {len(remaining_files)})")
            else:
                log("No remaining files from original batch")
                
        except Exception as e:
            log(f"Error during dynamic queue check: {e}")
            log("Continuing with current batch...")
        
        # ===== END DYNAMIC QUEUE CHECKING =====
        
        # Click "Upload All" button with polling - using exact selector from user's HTML
        log("Looking for Upload All button...")
        upload_success = False
        upload_all_selectors = [
            '#submit-button',                              # Primary - exact ID from user's HTML
            'button#submit-button',                        # More specific
            'button[name="submit"]#submit-button',         # Most specific from user's HTML
            'input[type="submit"][value*="Upload"]',       # Legacy fallback
            'button:has-text("Upload All")',              # Text-based fallback
            'input[name="submit"]'                         # Generic fallback
        ]

        # Poll for upload button for up to 1 minute
        upload_button_attempts = 6

        for upload_attempt in range(1, upload_button_attempts + 1):
            log(f"Looking for Upload All button (attempt {upload_attempt}/{upload_button_attempts})...")

            for selector in upload_all_selectors:
                try:
                    upload_button = page.locator(selector).first
                    if upload_button.count() > 0 and upload_button.is_visible():
                        upload_button.click()
                        log("✓ Upload All button clicked")
                        page.wait_for_load_state('networkidle', timeout=60000)
                        random_wait(3, 4)
                        upload_success = True
                        break
                except Exception as e:
                    log(f"Upload All selector {selector} failed: {e}")
                    continue

            if upload_success:
                break

            if upload_attempt < upload_button_attempts:
                log("Upload All button not ready, waiting 10 seconds...")
                time.sleep(10)

        if not upload_success:
            log("⚠️ Could not find or click Upload All button after 1 minute")
            return False
        
        # Now on confirmation page (t_submit_bulk_confirm.asp)
        log("On confirmation page, verifying submissions...")

        # Wait for confirmation page to load with polling
        confirmation_ready = False
        confirmation_attempts = 6

        for confirm_attempt in range(1, confirmation_attempts + 1):
            log(f"Waiting for confirmation page to load (attempt {confirm_attempt}/{confirmation_attempts})...")

            try:
                # Check if table is available
                table = page.locator('table').first
                if table.count() > 0:
                    log("✓ Confirmation page loaded")
                    confirmation_ready = True
                    break
            except Exception as e:
                log(f"Confirmation page not ready: {e}")

            if confirm_attempt < confirmation_attempts:
                log("Confirmation page not ready, waiting 10 seconds...")
                time.sleep(10)

        if not confirmation_ready:
            log("⚠️ Confirmation page not ready after 1 minute, but continuing...")

        random_wait(3, 4)

        # Click final Submit button with polling - using exact selector from user's confirmation page HTML
        submit_success = False
        submit_selectors = [
            '#upload_submit_button',                       # Primary - exact ID from user's HTML
            'button#upload_submit_button',                 # More specific
            'button[name="submit"]#upload_submit_button',  # Most specific from user's HTML
            'input[type="submit"][value*="Submit"]',       # Legacy fallback
            'button:has-text("Submit")',                   # Text-based fallback
            'input[name="submit"]'                         # Generic fallback
        ]

        # Poll for submit button for up to 1 minute
        submit_button_attempts = 6

        for submit_attempt in range(1, submit_button_attempts + 1):
            log(f"Looking for final Submit button (attempt {submit_attempt}/{submit_button_attempts})...")

            for selector in submit_selectors:
                try:
                    submit_button = page.locator(selector).first
                    if submit_button.count() > 0 and submit_button.is_visible():
                        submit_button.click()
                        log("✓ Final Submit button clicked")
                        page.wait_for_load_state('networkidle', timeout=60000)
                        random_wait(4, 5)
                        submit_success = True
                        break
                except Exception as e:
                    log(f"Submit selector {selector} failed: {e}")
                    continue

            if submit_success:
                break

            if submit_attempt < submit_button_attempts:
                log("Final Submit button not ready, waiting 10 seconds...")
                time.sleep(10)

        if submit_success:
            log(f"✅ Batch submission completed: {submitted_count} files submitted")
            
            # Wait for redirect to assignment inbox page
            log("Waiting for redirect to assignment inbox...")
            try:
                # After clicking Submit, Turnitin redirects to the inbox page
                # Wait for URL to change to inbox page
                page.wait_for_url("**/inbox/**", timeout=30000)
                log("✓ Redirected to assignment inbox page")
                
                # Save inbox URL for future direct navigation
                inbox_url = page.url
                from turnitin_helpers import save_assignment_inbox_url
                save_assignment_inbox_url(assignment_name, inbox_url)
                log(f"Saved inbox URL for {assignment_name}")
                
                random_wait(2, 3)
            except Exception as redirect_error:
                log(f"⚠️ Did not detect inbox redirect, checking current URL: {redirect_error}")
                current_url = page.url
                log(f"Current URL: {current_url}")
                
                # Check if we're already on an inbox-like page
                if "inbox" not in current_url.lower() and "paper" not in current_url.lower():
                    log("⚠️ Not on inbox page, submission may have failed")
                    # Don't return False - continue anyway as submission might have succeeded

            # Update queue items status
            for queue_item in queue_items[:submitted_count]:
                queue_item["status"] = "submitted"

            return True
        else:
            log("⚠️ Could not find or click final Submit button")
            return False
        
    except Exception as e:
        log(f"Error in batch submission: {e}")
        return False
