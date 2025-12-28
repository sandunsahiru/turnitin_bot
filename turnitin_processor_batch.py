"""
New Turnitin Processor with Batch Upload System
This replaces the old single-file Quick Submit workflow
"""

import os
import time
from datetime import datetime

# Import existing modules
import turnitin_auth
from turnitin_auth import log, browser_session

# Import new modules
from queue_manager import load_queue, save_queue, get_pending_items, update_queue_item
from turnitin_helpers import (
    navigate_to_class, 
    navigate_to_assignment,
    get_current_assignment,
    increment_assignment_count
)
from turnitin_batch import submit_batch
from turnitin_reports_batch import wait_for_similarity_scores, download_reports_for_batch

def process_dynamic_batch_documents(bot):
    """Process all pending documents with dynamic queue checking during upload"""
    try:
        log("=" * 60)
        log("STARTING DYNAMIC BATCH TURNITIN PROCESSING")
        log("=" * 60)

        # Get initial pending items
        pending_items = get_pending_items()
        if not pending_items:
            log("No pending documents found")
            return True

        log(f"Processing {len(pending_items)} initial pending items")

        # Get browser session (reuse existing if available)
        # Retry if session is owned by another thread
        max_retries = 3
        retry_delay = 5  # seconds
        
        for attempt in range(1, max_retries + 1):
            try:
                log(f"Attempting to get browser session (attempt {attempt}/{max_retries})...")
                page = turnitin_auth.get_session_page()
                log("✓ Browser session obtained")
                break  # Success - exit retry loop
            except Exception as e:
                error_msg = str(e)
                # Check if this is a "session owned by another thread" error
                if "owned by another thread" in error_msg and attempt < max_retries:
                    log(f"⚠️ Session is busy in another thread, waiting {retry_delay}s before retry...")
                    time.sleep(retry_delay)
                    continue  # Retry
                elif attempt >= max_retries:
                    log(f"✗ Failed to get browser session after {max_retries} attempts: {e}")
                    return False
                else:
                    log(f"✗ Failed to get browser session: {e}")
                    return False

        # Get available students for this assignment
        from turnitin_helpers import get_available_students, get_current_assignment
        assignment_name = get_current_assignment()
        available_students = get_available_students(assignment_name)

        # Handle special case where student data needs to be extracted
        if available_students == "NEEDS_STUDENT_DATA":
            log(f"Assignment {assignment_name} needs student data extraction - will extract during upload")
            available_students = []  # Will be populated during upload
            max_students = 8  # Default assumption
        elif not available_students:
            log("No available students found for assignment")
            return False
        else:
            max_students = len(available_students)
            log(f"Found {len(available_students)} available students")

        # Navigate to assignment upload page
        try:
            assignment_name = get_current_assignment()
            log(f"Current assignment: {assignment_name}")

            navigate_to_class("Business Administration")
            log("✓ Navigated to Business Administration class")

            navigate_to_assignment(assignment_name)
            log(f"✓ Navigated to assignment: {assignment_name}")

        except Exception as e:
            error_msg = str(e)
            # Check if this is a thread switching error
            if "THREAD_SWITCH_ERROR" in error_msg or "thread" in error_msg.lower() or "greenlet" in error_msg.lower():
                log(f"✗ Thread switching error detected: {e}")
                log("Forcing complete browser session reset...")
                # Force reset the browser session
                from turnitin_auth import force_reset_browser_session
                force_reset_browser_session()
                log("Browser session reset complete - next attempt will create fresh session")
            else:
                log(f"✗ Navigation failed: {e}")
            return False

        # Start dynamic batch upload with queue monitoring
        success = submit_dynamic_batch_with_queue_monitoring(bot, pending_items, assignment_name, max_students)

        if success:
            log("✅ Dynamic batch processing completed successfully")
            return True
        else:
            log("❌ Dynamic batch processing failed")
            return False

    except Exception as e:
        log(f"Error in dynamic batch processing: {e}")
        return False

def submit_dynamic_batch_with_queue_monitoring(bot, initial_items, assignment_name, max_students):
    """Submit batch with continuous queue monitoring to add new files"""
    try:
        # Start with initial items but continuously monitor queue
        current_batch = initial_items.copy()
        max_batch_size = min(max_students, 8)  # Limit to available students or max 8

        log(f"Starting dynamic batch: {len(current_batch)} files, max capacity: {max_batch_size}")

        # Wait for a short period to collect more files that might be uploaded
        log("Waiting 5 seconds to collect additional files for batching...")
        time.sleep(5)

        # Collect all new pending items that arrived during the wait
        current_queue = load_queue()
        all_pending = [item for item in current_queue.get('queue', [])
                      if item.get('status') == 'pending']

        # Use all pending items up to our capacity
        batch_items = all_pending[:max_batch_size]
        log(f"Final batch size: {len(batch_items)} files")

        # Get browser page
        page = turnitin_auth.get_session_page()

        # Use the existing submit_batch function
        from turnitin_batch import submit_batch

        success = submit_batch(page, batch_items, assignment_name)
        if not success:
            log("❌ Batch submission failed")
            return False

        log(f"✅ Batch submitted successfully: {len(batch_items)} files")

        # Load queue and update with submission details from batch_items
        # CRITICAL: batch_items are COPIES, not references! submit_batch updated the copies.
        # We need to copy those updates back to the actual queue before saving.
        queue_data = load_queue()
        
        # Update queue items with ALL fields from batch_items (which were updated by submit_batch)
        for item in batch_items:
            # Find the corresponding item in the queue
            for queue_item in queue_data["queue"]:
                if queue_item["id"] == item["id"]:
                    # Copy ALL updated fields from batch_items to queue
                    queue_item["status"] = "submitted"
                    queue_item["submitted_at"] = datetime.now().isoformat()
                    queue_item["submission_title"] = item.get("submission_title", "")
                    queue_item["student_id"] = item.get("student_id", "")
                    queue_item["student_name"] = item.get("student_name", "")
                    queue_item["assignment"] = item.get("assignment", "")
                    break
        
        # Save the updated queue with ALL details
        save_queue(queue_data)
        log("✓ Queue saved with submission details and timestamps")

        # Wait for similarity scores and download reports
        from turnitin_reports_batch import wait_for_similarity_scores, download_reports_for_batch

        scores_ready = wait_for_similarity_scores(page, batch_items)
        if scores_ready:
            download_reports_for_batch(page, batch_items, bot)

        # Update assignment count
        from turnitin_helpers import increment_assignment_count
        increment_assignment_count(assignment_name, len(batch_items))

        return True

    except Exception as e:
        log(f"Error in dynamic batch submission: {e}")
        return False

def download_pending_reports(bot, submitted_items):
    """Download reports for items that have already been submitted"""
    try:
        log("=" * 60)
        log("DOWNLOADING REPORTS FOR SUBMITTED ITEMS")
        log("=" * 60)
        
        if not submitted_items:
            log("No submitted items to download reports for")
            return True
        
        log(f"Processing {len(submitted_items)} submitted items")
        
        # Get browser session
        try:
            log("Attempting to get browser session...")
            page = turnitin_auth.get_session_page()
            log("✓ Browser session obtained")
        except Exception as e:
            log(f"✗ Failed to get browser session: {e}")
            return False
        
        # Navigate to assignment inbox using cached URL
        try:
            assignment_name = get_current_assignment()
            log(f"Current assignment: {assignment_name}")
            
            # Try to use cached inbox URL first
            from turnitin_helpers import get_assignment_inbox_url
            inbox_url = get_assignment_inbox_url(assignment_name)
            
            if inbox_url:
                log(f"Using cached inbox URL for direct navigation")
                try:
                    page.goto(inbox_url, wait_until='networkidle', timeout=30000)
                    log(f"✓ Navigated directly to assignment inbox")
                except Exception as goto_error:
                    log(f"Direct navigation failed: {goto_error}, falling back to class navigation")
                    # Fallback to class navigation
                    navigate_to_class("Business Administration")
                    log("✓ Navigated to Business Administration class")
                    navigate_to_assignment(assignment_name)
                    log(f"✓ Navigated to assignment: {assignment_name}")
            else:
                log("No cached inbox URL, using class navigation")
                # Navigate to class
                navigate_to_class("Business Administration")
                log("✓ Navigated to Business Administration class")
                
                # Navigate to assignment inbox
                navigate_to_assignment(assignment_name)
                log(f"✓ Navigated to assignment: {assignment_name}")
            
        except Exception as e:
            log(f"✗ Failed to navigate to assignment: {e}")
            return False
        
        # Download reports for submitted items
        try:
            log("Downloading reports for submitted items...")
            download_reports_for_batch(page, submitted_items, bot)
            log("✓ Reports downloaded and sent")
        except Exception as e:
            log(f"⚠️ Error downloading reports: {e}")
        
        # Update queue with final status
        for item in submitted_items:
            if item.get("report_downloaded"):
                update_queue_item(item["id"], {"status": "completed", "report_downloaded": True})
        
        # Cleanup uploaded files after reports are sent
        for item in submitted_items:
            try:
                file_path = item.get("file_path")
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
                    log(f"✓ Cleaned up uploaded file: {file_path}")
            except Exception as e:
                log(f"Error cleaning up {file_path}: {e}")
        
        log("=" * 60)
        log("REPORT DOWNLOAD COMPLETED - BROWSER KEPT OPEN")
        log("=" * 60)
        
        return True
        
    except Exception as e:
        log(f"Error in report download: {e}")
        return False


def process_batch_documents(bot, pending_items):
    """Process pending submissions in batch mode - called by processor manager"""
    try:
        log("=" * 60)
        log("STARTING BATCH TURNITIN PROCESSING")
        log("=" * 60)
        
        # Use provided pending_items instead of getting from queue
        if not pending_items:
            log("No pending items provided")
            return True
        
        log(f"Processing {len(pending_items)} pending items")
        
        # Get browser session
        try:
            log("Attempting to get browser session...")
            page = turnitin_auth.get_session_page()
            log("✓ Browser session obtained")
        except Exception as e:
            log(f"✗ Failed to get browser session: {e}")
            import traceback
            log(f"Full traceback: {traceback.format_exc()}")

            # Try to recover browser session once
            if "crashed" in str(e).lower() or "thread" in str(e).lower() or "session" in str(e).lower():
                log("Attempting browser session recovery...")
                try:
                    turnitin_auth.cleanup_browser_session()
                    page = turnitin_auth.get_session_page()  # Try again after cleanup
                    log("✓ Browser session recovered")
                except Exception as recovery_error:
                    log(f"✗ Browser session recovery failed: {recovery_error}")
                    return False
            else:
                return False
        
        # Get current assignment
        assignment_name = get_current_assignment()
        log(f"Current assignment: {assignment_name}")
        
        # Check if already on Multiple File Upload page
        current_url = page.url
        if "t_submit_bulk.asp" in current_url:
            log("✓ Already on Multiple File Upload page, proceeding with submission")
        else:
            # Navigate to class with recovery logic
            try:
                navigate_to_class("Business Administration")
                log("✓ Navigated to Business Administration class")
            except Exception as e:
                log(f"✗ Failed to navigate to class: {e}")

                # Try to recover browser session once
                if "crashed" in str(e).lower() or "thread" in str(e).lower():
                    log("Attempting browser session recovery...")
                    try:
                        turnitin_auth.cleanup_browser_session()
                        page = turnitin_auth.get_session_page()  # This will create a new session
                        navigate_to_class("Business Administration")
                        log("✓ Browser session recovered and class navigation successful")
                    except Exception as recovery_error:
                        log(f"✗ Browser session recovery failed: {recovery_error}")
                        return False
                else:
                    return False
        
        # Navigate to assignment (if not already on upload page)
        current_url = page.url
        if "t_submit_bulk.asp" in current_url:
            log(f"✓ Already on Multiple File Upload page for assignment")
        else:
            try:
                navigate_to_assignment(assignment_name)
                log(f"✓ Navigated to assignment: {assignment_name}")
            except Exception as e:
                log(f"✗ Failed to navigate to assignment: {e}")
                return False
        
        # Submit batch
        try:
            success = submit_batch(page, pending_items, assignment_name)
            if not success:
                log("✗ Batch submission failed")
                return False
            log("✓ Batch submitted successfully")
        except Exception as e:
            log(f"✗ Batch submission error: {e}")
            return False
        
        # Increment assignment count
        increment_assignment_count(assignment_name, len(pending_items))
        
        # Save updated queue
        queue_data = load_queue()
        save_queue(queue_data)
        
        # After batch submission, we're already on the assignment inbox page
        # Just verify we're on the right page
        try:
            current_url = page.url
            log(f"Current URL after submission: {current_url}")
            
            if "inbox" in current_url.lower() or "paper" in current_url.lower():
                log("✓ Already on assignment inbox page")
            else:
                log("⚠️ Not on expected inbox page, but continuing...")
                
        except Exception as e:
            log(f"Error checking current page: {e}")
        
        # Wait for similarity scores
        try:
            log("Waiting for similarity scores...")
            wait_for_similarity_scores(page, pending_items, max_wait_minutes=10)
            log("✓ Similarity scores received")
        except Exception as e:
            log(f"⚠️ Error waiting for scores: {e}")
        
        # Download reports
        try:
            log("Downloading reports...")
            download_reports_for_batch(page, pending_items, bot)
            log("✓ Reports downloaded and sent")
        except Exception as e:
            log(f"⚠️ Error downloading reports: {e}")
        
        # Update queue with final status
        for item in pending_items:
            if item.get("report_downloaded"):
                update_queue_item(item["id"], {"status": "completed", "report_downloaded": True})
            elif item.get("status") == "submitted":
                update_queue_item(item["id"], {"status": "submitted"})
        
        # Cleanup uploaded files after reports are sent
        for item in pending_items:
            try:
                file_path = item.get("file_path")
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
                    log(f"✓ Cleaned up uploaded file: {file_path}")
            except Exception as e:
                log(f"Error cleaning up {file_path}: {e}")
        
        log("=" * 60)
        log("BATCH PROCESSING COMPLETED - BROWSER KEPT OPEN")
        log("=" * 60)
        
        # DON'T close browser - it will be reused for next batch
        return True
        
    except Exception as e:
        log(f"Error in batch processing: {e}")
        return False

def check_assignments_exhausted():
    """Check if all assignments are exhausted and notify admin"""
    try:
        from turnitin_helpers import get_available_students, load_assignment_tracking
        
        tracking = load_assignment_tracking()
        current_assignment = tracking.get("current_assignment", "ass01")
        
        # Check next 5 assignments
        for i in range(5):
            assignment_num = int(current_assignment.replace("ass", "").lstrip("0") or "1") + i
            assignment_name = f"ass{assignment_num:02d}"
            
            available = get_available_students(assignment_name)
            if len(available) > 0:
                return False  # Found available students
        
        # All assignments exhausted
        log("⚠️ ALL ASSIGNMENTS EXHAUSTED - No available students")
        return True
        
    except Exception as e:
        log(f"Error checking assignments: {e}")
        return False
