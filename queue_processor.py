import os
import json
import time
import threading
from datetime import datetime
from queue_manager import get_pending_items, get_submitted_items, update_queue_item, remove_completed_items, load_queue

# Global processor lock to ensure single-threaded processing
_processing_lock = threading.Lock()

# Global processor state (single-threaded)
processor_state = {
    "is_running": False,
    "current_session": None,
    "browser_page": None,
    "failure_count": 0,
    "last_failure_time": None
}

def log(message: str):
    """Log a message with a timestamp to the terminal."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] QUEUE_PROCESSOR: {message}")

def is_processor_running():
    """Check if processor is currently running"""
    return processor_state["is_running"]

def start_immediate_processing(bot):
    """Start processing immediately when documents are added to queue"""
    # Try to acquire lock - if already held, another thread is processing
    if not _processing_lock.acquire(blocking=False):
        log("Processor already running in another thread - new documents will be picked up automatically")
        return False
    
    try:
        if processor_state["is_running"]:
            log("Processor already running - new documents will be picked up automatically")
            return False

        # Circuit breaker: prevent excessive failures
        if processor_state["failure_count"] >= 5:
            last_failure = processor_state.get("last_failure_time")
            if last_failure:
                time_since_failure = datetime.now() - datetime.fromisoformat(last_failure)
                cooldown_time = 60  # 1 minute cooldown
                if time_since_failure.total_seconds() < cooldown_time:
                    log(f"Circuit breaker active: {processor_state['failure_count']} failures, waiting {cooldown_time - int(time_since_failure.total_seconds())} more seconds")
                    return False
                else:
                    # Reset failure count after cooldown
                    processor_state["failure_count"] = 0
                    log("Circuit breaker reset after cooldown period")

        # Start processing immediately (no threading)
        processor_state["is_running"] = True
        log("Starting immediate batch processing...")

        try:
            success = process_all_pending_documents(bot)
            if success:
                log("Batch processing completed successfully")
                processor_state["failure_count"] = 0
            else:
                log("Batch processing failed")
                processor_state["failure_count"] += 1
                processor_state["last_failure_time"] = datetime.now().isoformat()

        except Exception as e:
            log(f"Processing error: {e}")
            processor_state["failure_count"] += 1
            processor_state["last_failure_time"] = datetime.now().isoformat()

        finally:
            processor_state["is_running"] = False
            log("Processor finished and available for next batch")
    
    finally:
        # Always release the lock
        _processing_lock.release()

        # Keep browser alive for next batch
        # Check for more work and process automatically
        cleanup_if_idle(bot)

    return True

def process_all_pending_documents(bot):
    """Process all pending documents in a single batch with dynamic queue checking"""
    try:
        # Import here to avoid circular imports
        from turnitin_processor_batch import process_dynamic_batch_documents

        return process_dynamic_batch_documents(bot)

    except Exception as e:
        log(f"Error in batch processing: {e}")
        return False

def cleanup_if_idle(bot):
    """Clean up browser if idle for too long, and automatically process new pending items"""
    try:
        # Check for more work first
        time.sleep(2)  # Small delay

        # Clean up completed items
        removed = remove_completed_items()
        if removed > 0:
            log(f"Cleaned up {removed} completed items from queue")

        # Check for submitted items needing reports
        submitted_items = get_submitted_items()
        if submitted_items:
            log(f"Found {len(submitted_items)} submitted items needing reports")
            processor_state["is_running"] = True
            try:
                from turnitin_processor_batch import download_pending_reports
                success = download_pending_reports(bot, submitted_items)
                if success:
                    log("Report downloading completed successfully")
                else:
                    log("Report downloading failed")
            finally:
                processor_state["is_running"] = False
                # Check again for more work after downloading reports
                cleanup_if_idle(bot)
            return

        # Check for new pending items
        pending_items = get_pending_items()
        if pending_items:
            log(f"Found {len(pending_items)} new pending items, starting another batch")
            # Automatically start processing new batch
            processor_state["is_running"] = True
            try:
                from turnitin_processor_batch import process_dynamic_batch_documents
                success = process_dynamic_batch_documents(bot)
                if success:
                    log("New batch processing completed successfully")
                    processor_state["failure_count"] = 0
                else:
                    log("New batch processing failed")
                    processor_state["failure_count"] += 1
                    processor_state["last_failure_time"] = datetime.now().isoformat()
            except Exception as e:
                log(f"Error processing new batch: {e}")
                processor_state["failure_count"] += 1
                processor_state["last_failure_time"] = datetime.now().isoformat()
            finally:
                processor_state["is_running"] = False
                # Recursively check again for more items
                cleanup_if_idle(bot)
            return

        # No more work - keep browser alive but close after extended idle time
        log("Queue empty - browser kept alive for new documents")

    except Exception as e:
        log(f"Error during cleanup check: {e}")

def force_stop_processor():
    """Force stop processor (admin command)"""
    was_running = processor_state["is_running"]
    processor_state["is_running"] = False
    log("Processor force stopped by admin")
    return was_running

def cleanup_browser_session():
    """Clean up browser session when needed"""
    try:
        if processor_state["browser_page"]:
            processor_state["browser_page"].close()
        processor_state["browser_page"] = None
        processor_state["current_session"] = None
        log("Browser session cleaned up")
    except Exception as e:
        log(f"Error cleaning up browser: {e}")

def reset_circuit_breaker():
    """Reset circuit breaker failure count (admin command)"""
    old_count = processor_state["failure_count"]
    processor_state["failure_count"] = 0
    processor_state["last_failure_time"] = None
    log(f"Circuit breaker reset: cleared {old_count} failures")
    return old_count

def get_processor_status():
    """Get current processor status for admin monitoring"""
    return {
        "is_running": processor_state["is_running"],
        "current_session": processor_state["current_session"] is not None,
        "browser_active": processor_state["browser_page"] is not None,
        "failure_count": processor_state["failure_count"]
    }