import os
import json
import uuid
import tempfile
import threading
import time
from datetime import datetime

# Add file locking for thread safety
try:
    import fcntl  # Unix/Linux file locking
    HAS_FCNTL = True
except ImportError:
    import msvcrt  # Windows file locking
    HAS_FCNTL = False

# Global lock for queue operations
queue_lock = threading.Lock()

def log(message: str):
    """Log a message with a timestamp to the terminal."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

# ==================== QUEUE MANAGEMENT ====================

def load_queue():
    """Load submission queue from JSON file with file locking and retry logic"""
    with queue_lock:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if os.path.exists("submission_queue.json"):
                    with open("submission_queue.json", "r") as f:
                        # Apply file lock with retry logic
                        if HAS_FCNTL:
                            fcntl.flock(f.fileno(), fcntl.LOCK_SH)  # Shared lock for reading
                            data = json.load(f)
                            fcntl.flock(f.fileno(), fcntl.LOCK_UN)  # Unlock
                        else:
                            # Windows: try without locking first, then with minimal lock
                            try:
                                data = json.load(f)
                            except json.JSONDecodeError:
                                # File might be empty or corrupted, return empty queue
                                log("Queue file empty or corrupted, starting with empty queue")
                                return {"queue": []}
                            except:
                                # If that fails, try with very brief lock
                                f.seek(0)
                                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                                data = json.load(f)
                                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                        return data
                else:
                    return {"queue": []}
            except (PermissionError, OSError) as e:
                if attempt < max_retries - 1:
                    log(f"Queue load attempt {attempt + 1} failed, retrying in 0.1s: {e}")
                    time.sleep(0.1)
                    continue
                else:
                    log(f"Error loading queue after {max_retries} attempts: {e}")
                    return {"queue": []}
            except Exception as e:
                log(f"Error loading queue: {e}")
                return {"queue": []}

def save_queue(queue_data):
    """Save submission queue to JSON file with simplified Windows-friendly approach"""
    with queue_lock:
        max_save_retries = 3
        temp_file = None

        for attempt in range(max_save_retries):
            try:
                # Create temporary file for atomic write
                queue_dir = os.path.dirname(os.path.abspath("submission_queue.json"))
                temp_fd, temp_file = tempfile.mkstemp(suffix='.tmp', prefix='queue_', dir=queue_dir)

                with os.fdopen(temp_fd, 'w') as f:
                    # For Windows: simplified approach without complex locking
                    if HAS_FCNTL:
                        # Unix/Linux: use proper file locking
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                        json.dump(queue_data, f, indent=2)
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    else:
                        # Windows: write without locking, rely on atomic rename
                        json.dump(queue_data, f, indent=2)
                        f.flush()
                        os.fsync(f.fileno())  # Force write to disk

                # Atomic move - replaces old file (Windows-friendly)
                target_file = "submission_queue.json"
                if os.path.exists(target_file):
                    # On Windows, need to remove first
                    try:
                        os.remove(target_file)
                    except (PermissionError, FileNotFoundError):
                        pass  # File might be in use, try rename anyway

                os.rename(temp_file, target_file)
                temp_file = None  # Prevent cleanup since we renamed it

                log(f"Queue saved atomically: {len(queue_data['queue'])} items")
                return  # Success, exit retry loop

            except (PermissionError, OSError) as e:
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
                temp_file = None

                if attempt < max_save_retries - 1:
                    log(f"Queue save attempt {attempt + 1} failed, retrying: {e}")
                    time.sleep(0.1)
                    continue
                else:
                    log(f"Error saving queue after {max_save_retries} attempts: {e}")
                    raise

            except Exception as e:
                log(f"Error saving queue: {e}")
                # Cleanup temp file on error
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
                raise

def add_to_queue(file_path, user_id, chat_id):
    """Add a new document to the submission queue"""
    try:
        queue_data = load_queue()
        
        queue_item = {
            "id": str(uuid.uuid4()),
            "file_path": file_path,
            "user_id": str(user_id),
            "chat_id": chat_id,
            "timestamp": datetime.now().isoformat(),
            "status": "pending",
            "assignment": "",
            "student_id": "",
            "student_name": "",
            "submission_title": "",
            "paper_id": "",
            "similarity_score": "",
            "ai_score": "",
            "report_downloaded": False
        }
        
        queue_data["queue"].append(queue_item)
        save_queue(queue_data)
        
        log(f"Added to queue: {file_path} for user {user_id}")
        return queue_item["id"]
        
    except Exception as e:
        log(f"Error adding to queue: {e}")
        return None

def get_pending_items(limit=5):
    """Get pending items from queue (up to limit)"""
    try:
        queue_data = load_queue()
        pending = [item for item in queue_data["queue"] if item["status"] == "pending"]
        log(f"Found {len(pending)} pending items in queue")
        return pending[:limit]
    except Exception as e:
        log(f"Error getting pending items: {e}")
        return []

def update_queue_item(item_id, updates):
    """Update a specific queue item"""
    try:
        queue_data = load_queue()
        
        for item in queue_data["queue"]:
            if item["id"] == item_id:
                item.update(updates)
                save_queue(queue_data)
                log(f"Updated queue item {item_id}: {updates}")
                return True
        
        log(f"Queue item {item_id} not found")
        return False
        
    except Exception as e:
        log(f"Error updating queue item: {e}")
        return False

def get_items_by_status(status):
    """Get all items with a specific status"""
    try:
        queue_data = load_queue()
        items = [item for item in queue_data["queue"] if item["status"] == status]
        return items
    except Exception as e:
        log(f"Error getting items by status: {e}")
        return []

def get_submitted_items(limit=5):
    """Get submitted items that need report downloads"""
    try:
        queue_data = load_queue()
        submitted = [item for item in queue_data["queue"] 
                    if item["status"] == "submitted" and not item.get("report_downloaded", False)]
        log(f"Found {len(submitted)} submitted items awaiting reports")
        return submitted[:limit]
    except Exception as e:
        log(f"Error getting submitted items: {e}")
        return []

def remove_completed_items():
    """Remove completed items from queue to keep it clean"""
    try:
        queue_data = load_queue()
        original_count = len(queue_data["queue"])
        
        # Keep only items that are NOT completed with downloaded reports
        queue_data["queue"] = [
            item for item in queue_data["queue"]
            if not (item["status"] == "completed" and item.get("report_downloaded", False))
        ]
        
        removed_count = original_count - len(queue_data["queue"])
        
        if removed_count > 0:
            save_queue(queue_data)
            log(f"Removed {removed_count} completed items from queue")
        
        return removed_count
        
    except Exception as e:
        log(f"Error removing completed items: {e}")
        return 0

def mark_reports_downloaded(item_id):
    """Mark reports as downloaded for a queue item"""
    return update_queue_item(item_id, {"report_downloaded": True, "status": "completed"})
