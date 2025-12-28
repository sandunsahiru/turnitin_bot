import os
import json
import random
from datetime import datetime, timedelta

# Import from turnitin_auth for browser session and logging
from turnitin_auth import browser_session, log, random_wait

# ==================== ASSIGNMENT & STUDENT TRACKING ====================

def load_assignment_tracking():
    """Load assignment tracking data from JSON file"""
    try:
        if os.path.exists("assignment_tracking.json"):
            with open("assignment_tracking.json", "r") as f:
                return json.load(f)
        else:
            # Initialize with default data
            default_data = {
                "current_assignment": "ass01",
                "submission_counts": {},
                "last_updated": datetime.now().isoformat(),
                "class_home_url": ""
            }
            save_assignment_tracking(default_data)
            return default_data
    except Exception as e:
        log(f"Error loading assignment tracking: {e}")
        return {
            "current_assignment": "ass01",
            "submission_counts": {},
            "last_updated": datetime.now().isoformat(),
            "class_home_url": ""
        }

def save_assignment_tracking(data):
    """Save assignment tracking data to JSON file"""
    try:
        data["last_updated"] = datetime.now().isoformat()
        with open("assignment_tracking.json", "w") as f:
            json.dump(data, f, indent=2)
        log(f"Assignment tracking saved: {data['current_assignment']}")
    except Exception as e:
        log(f"Error saving assignment tracking: {e}")

def get_current_assignment():
    """Get current assignment name and check if rotation needed based on student availability"""
    tracking = load_assignment_tracking()
    current = tracking["current_assignment"]

    # Check if current assignment has available students
    available_students = get_available_students(current)

    # Handle first-time use case
    if available_students == "NEEDS_STUDENT_DATA":
        log(f"Assignment {current} needs student data extraction - using this assignment")
        log("Note: Students will be extracted during first file upload")
        return current

    # Handle normal case with student list
    if isinstance(available_students, list) and len(available_students) > 0:
        log(f"Using assignment {current} with {len(available_students)} available students")
        return current

    log(f"⚠️ Assignment {current} has no available students (all at 24-hour limit)")
    log("Attempting to rotate to next assignment with available students...")

    # Try rotating through multiple assignments (up to 10) to find one with available students
    max_attempts = 10
    tried_assignments = [current]
    
    for attempt in range(1, max_attempts + 1):
        try:
            # Calculate next assignment number
            current_num = int(current.replace("ass", "").lstrip("0") or "1")
            next_num = current_num + attempt
            next_assignment = f"ass{next_num:02d}"
            
            log(f"Trying assignment {next_assignment} (attempt {attempt}/{max_attempts})...")
            tried_assignments.append(next_assignment)
            
            # Check if the new assignment has available students
            new_available = get_available_students(next_assignment)
            
            if new_available == "NEEDS_STUDENT_DATA":
                log(f"✓ Assignment {next_assignment} needs student data extraction - using this assignment")
                tracking["current_assignment"] = next_assignment
                save_assignment_tracking(tracking)
                log(f"Rotated to assignment: {next_assignment}")
                return next_assignment
            
            if isinstance(new_available, list) and len(new_available) > 0:
                log(f"✓ Assignment {next_assignment} has {len(new_available)} available students!")
                tracking["current_assignment"] = next_assignment
                save_assignment_tracking(tracking)
                log(f"Rotated to assignment: {next_assignment}")
                return next_assignment
            
            log(f"Assignment {next_assignment} also has no available students, trying next...")
            
        except Exception as e:
            log(f"Error checking assignment {next_assignment}: {e}")
            continue
    
    # If we've tried all assignments and none have available students
    log(f"⚠️ WARNING: Tried {max_attempts} assignments, none have available students!")
    log(f"Tried: {', '.join(tried_assignments)}")
    log(f"All students across multiple assignments are at their 24-hour submission limits")
    log(f"Staying on assignment {current} - documents will queue until students become available")
    
    return current

def increment_assignment_count(assignment_name, count=1):
    """Increment submission count for an assignment"""
    tracking = load_assignment_tracking()
    tracking["submission_counts"][assignment_name] = tracking["submission_counts"].get(assignment_name, 0) + count
    save_assignment_tracking(tracking)
    log(f"Assignment {assignment_name} count: {tracking['submission_counts'][assignment_name]}")

def load_student_tracking():
    """Load student tracking data from JSON file"""
    try:
        if os.path.exists("student_tracking.json"):
            with open("student_tracking.json", "r") as f:
                return json.load(f)
        else:
            return {}
    except Exception as e:
        log(f"Error loading student tracking: {e}")
        return {}

def save_student_tracking(data):
    """Save student tracking data to JSON file"""
    try:
        with open("student_tracking.json", "w") as f:
            json.dump(data, f, indent=2)
        log("Student tracking saved")
    except Exception as e:
        log(f"Error saving student tracking: {e}")

def get_available_students(assignment_name):
    """Get list of students not at 24-hour submission limit"""
    tracking = load_student_tracking()

    if assignment_name not in tracking:
        log(f"No student data for {assignment_name} - this is normal for first-time use")
        # Return special marker indicating this assignment needs student data extraction
        return "NEEDS_STUDENT_DATA"

    assignment_data = tracking[assignment_name]
    students = assignment_data.get("students", [])
    submissions = assignment_data.get("submissions", {})

    # If students list is empty, need to extract students
    if not students:
        log(f"No students found in {assignment_name} - needs student extraction")
        return "NEEDS_STUDENT_DATA"

    available = []
    now = datetime.now()
    
    log(f"Checking student availability for {assignment_name} (current time: {now.strftime('%Y-%m-%d %H:%M:%S')})")
    log(f"24-hour window: submissions after {(now - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')}")

    for student in students:
        student_id = student["id"]
        student_submissions = submissions.get(student_id, [])

        # Filter submissions within last 24 hours
        recent_submissions = []
        for sub in student_submissions:
            sub_time = datetime.fromisoformat(sub["timestamp"])
            hours_ago = (now - sub_time).total_seconds() / 3600
            if hours_ago < 24:  # Within last 24 hours
                recent_submissions.append({
                    "title": sub["title"],
                    "timestamp": sub["timestamp"],
                    "hours_ago": round(hours_ago, 1)
                })

        # Student is available if less than 3 submissions in last 24 hours
        if len(recent_submissions) < 3:
            available.append(student)
            if recent_submissions:
                log(f"Student {student['name']} available ({len(recent_submissions)}/3 submissions)")
                for sub in recent_submissions:
                    log(f"  - {sub['title']} submitted {sub['hours_ago']}h ago ({sub['timestamp']})")
            else:
                log(f"Student {student['name']} available (0/3 submissions)")
        else:
            log(f"Student {student['name']} at limit (3/3 submissions)")
            for sub in recent_submissions:
                log(f"  - {sub['title']} submitted {sub['hours_ago']}h ago ({sub['timestamp']})")

    return available

def add_student_submission(assignment_name, student_id, title):
    """Record a new submission for a student"""
    tracking = load_student_tracking()
    
    if assignment_name not in tracking:
        tracking[assignment_name] = {"students": [], "submissions": {}}
    
    if student_id not in tracking[assignment_name]["submissions"]:
        tracking[assignment_name]["submissions"][student_id] = []
    
    timestamp = datetime.now().isoformat()
    tracking[assignment_name]["submissions"][student_id].append({
        "timestamp": timestamp,
        "title": title
    })
    
    total_submissions = len(tracking[assignment_name]["submissions"][student_id])
    save_student_tracking(tracking)
    log(f"Recorded submission for student {student_id}: {title}")
    log(f"  Timestamp: {timestamp}")
    log(f"  Total submissions for this student: {total_submissions}")

# ==================== NAVIGATION FUNCTIONS ====================

def navigate_to_class(class_name="Business Administration"):
    """Navigate to class from homepage with browser session validation"""
    try:
        page = browser_session['page']

        # Validate browser session is still alive
        try:
            current_url = page.url
            # Try a simple operation to check if page is responsive
            page.evaluate("() => window.location.href")
        except Exception as session_error:
            error_msg = str(session_error)
            # Check if this is a thread switching error
            if "thread" in error_msg.lower() or "greenlet" in error_msg.lower():
                log(f"Thread switching error detected in navigate_to_class: {session_error}")
                # Raise a specific error that will trigger session reset
                raise Exception(f"THREAD_SWITCH_ERROR: {session_error}")
            else:
                log(f"Browser session invalid: {session_error}")
                raise Exception(f"Browser session crashed: {session_error}")

        log(f"Navigating to class: {class_name}")

        # Ensure we're on homepage or can see class table
        if "instructor_home" not in current_url and "class/" not in current_url:
            # Try to find class table
            page.wait_for_selector('table', timeout=20000)
        
        # Find class row by name
        class_link_selectors = [
            f'td.class_name a:has-text("{class_name}")',
            f'a[title="{class_name}"]',
            f'a:has-text("{class_name}")'
        ]
        
        for selector in class_link_selectors:
            try:
                link = page.locator(selector).first
                if link.count() > 0:
                    # Get the href to save class home URL
                    href = link.get_attribute("href")
                    if href:
                        # Save full URL for future navigation
                        if href.startswith("http"):
                            class_url = href
                        else:
                            class_url = f"https://www.turnitin.com{href}"
                        
                        tracking = load_assignment_tracking()
                        tracking["class_home_url"] = class_url
                        save_assignment_tracking(tracking)
                        log(f"Saved class home URL: {class_url}")
                    
                    link.click()
                    page.wait_for_load_state('networkidle', timeout=30000)
                    log(f"Successfully navigated to {class_name}")
                    random_wait(2, 3)
                    return True
            except Exception as e:
                log(f"Selector {selector} failed: {e}")
                continue
        
        raise Exception(f"Could not find class: {class_name}")
        
    except Exception as e:
        log(f"Error navigating to class: {e}")
        raise

def navigate_to_assignment(assignment_name):
    """Navigate to assignment and open Multiple File Upload page"""
    page = browser_session['page']
    
    try:
        log(f"Navigating to assignment: {assignment_name}")
        
        # Ensure we're on class instructor home page
        current_url = page.url
        if "instructor_home" not in current_url:
            # Navigate to saved class home URL
            tracking = load_assignment_tracking()
            class_url = tracking.get("class_home_url")
            if class_url:
                page.goto(class_url, timeout=30000)
                page.wait_for_load_state('networkidle', timeout=20000)
                log("Navigated to class home page")
            else:
                raise Exception("Class home URL not saved")
        
        # Find assignment row by title
        assignment_selectors = [
            f'tr[data-assignment-title="{assignment_name}"]',
            f'span.assignment-title:has-text("{assignment_name}")'
        ]
        
        assignment_found = False
        for selector in assignment_selectors:
            try:
                row = page.locator(selector).first
                if row.count() > 0:
                    assignment_found = True
                    # Find "View" link in the same row or parent
                    view_link = row.locator('..').locator('a:has-text("View")').first
                    if view_link.count() > 0:
                        view_link.click()
                        page.wait_for_load_state('networkidle', timeout=30000)
                        log(f"Clicked View for {assignment_name}")
                        random_wait(2, 3)
                        break
            except Exception as e:
                log(f"Assignment selector {selector} failed: {e}")
                continue
        
        if not assignment_found:
            raise Exception(f"Could not find assignment: {assignment_name}")
        
        # Now on assignment inbox page, click Submit button
        submit_selectors = [
            'a[href*="t_submit.asp"] button.btn-primary',
            'button:has-text("Submit")',
            '.cms-submit a'
        ]
        
        for selector in submit_selectors:
            try:
                page.wait_for_selector(selector, timeout=10000)
                page.click(selector)
                page.wait_for_load_state('networkidle', timeout=30000)
                log("Clicked Submit button")
                random_wait(2, 3)
                break
            except Exception as e:
                log(f"Submit selector {selector} failed: {e}")
                continue
        
        # Now on submit page, click "Multiple File Upload" from dropdown
        try:
            # Click dropdown to open menu
            dropdown_selectors = [
                '#submit_type',
                'a.dropdown-toggle:has-text("Single File Upload")'
            ]
            
            for selector in dropdown_selectors:
                try:
                    page.click(selector)
                    log("Opened submit type dropdown")
                    random_wait(1, 2)
                    break
                except:
                    continue
            
            # Click "Multiple File Upload" option
            multiple_upload_selectors = [
                'a[href*="t_submit_bulk.asp"]',
                'a:has-text("Multiple File Upload")'
            ]
            
            for selector in multiple_upload_selectors:
                try:
                    page.click(selector)
                    page.wait_for_load_state('networkidle', timeout=30000)
                    log("Navigated to Multiple File Upload page")
                    random_wait(2, 3)
                    return True
                except Exception as e:
                    log(f"Multiple upload selector {selector} failed: {e}")
                    continue
            
            raise Exception("Could not click Multiple File Upload")
            
        except Exception as e:
            log(f"Error switching to Multiple File Upload: {e}")
            raise
        
    except Exception as e:
        log(f"Error navigating to assignment: {e}")
        raise


def save_assignment_inbox_url(assignment_name, inbox_url):
    """Save assignment inbox URL for direct navigation"""
    try:
        tracking = load_assignment_tracking()
        if 'assignment_inbox_urls' not in tracking:
            tracking['assignment_inbox_urls'] = {}
        tracking['assignment_inbox_urls'][assignment_name] = inbox_url
        save_assignment_tracking(tracking)
        log(f"Saved inbox URL for {assignment_name}")
    except Exception as e:
        log(f"Error saving inbox URL: {e}")

def get_assignment_inbox_url(assignment_name):
    """Get saved assignment inbox URL"""
    try:
        tracking = load_assignment_tracking()
        return tracking.get('assignment_inbox_urls', {}).get(assignment_name)
    except Exception as e:
        log(f"Error getting inbox URL: {e}")
        return None

# Alias for backward compatibility
def get_available_students_for_assignment(assignment_name):
    """Alias for get_available_students for backward compatibility"""
    return get_available_students(assignment_name)
