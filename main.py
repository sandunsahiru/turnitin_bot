import os
import json
import time
import threading
import queue
from datetime import datetime, timedelta
from dotenv import load_dotenv
import telebot
from telebot import types
from turnitin_processor import process_turnitin, handle_retry_submission, handle_retry_download

# Load environment variables
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID"))

# Initialize bot
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode='HTML')  # Set default parse mode

# Processing queue
processing_queue = queue.Queue()
processing_thread = None
processing_lock = threading.Lock()

# Subscription plans
MONTHLY_PLANS = {
    "1_month": {"price": 1500, "duration": 30, "name": "1 Month"},
    "3_months": {"price": 4000, "duration": 90, "name": "3 Months"},
    "6_months": {"price": 6000, "duration": 180, "name": "6 Months"},
    "12_months": {"price": 8000, "duration": 365, "name": "12 Months"}
}

DOCUMENT_PLANS = {
    "1_doc": {"price": 150, "documents": 1, "name": "1 Document"},
    "5_docs": {"price": 800, "documents": 5, "name": "5 Documents"},
    "10_docs": {"price": 1000, "documents": 10, "name": "10 Documents"}
}

BANK_DETAILS = """🏦 Commercial Bank
📍 Kurunegala (016) - Suratissa Mawatha
💳 Account No: 8160103864
📌 Name: SMSS BANDARA
📝 Include your name in the bank description!

📱 Send payment slip via WhatsApp to: +94702947854"""

def log(message: str):
    """Log with timestamp"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def load_subscriptions():
    """Load subscription data from file"""
    try:
        if os.path.exists("subscriptions.json"):
            with open("subscriptions.json", "r") as f:
                return json.load(f)
        return {}
    except:
        return {}

def save_subscriptions(data):
    """Save subscription data to file"""
    with open("subscriptions.json", "w") as f:
        json.dump(data, f, indent=2)

def load_pending_requests():
    """Load pending subscription requests"""
    try:
        if os.path.exists("pending_requests.json"):
            with open("pending_requests.json", "r") as f:
                return json.load(f)
        return {}
    except:
        return {}

def save_pending_requests(data):
    """Save pending subscription requests"""
    with open("pending_requests.json", "w") as f:
        json.dump(data, f, indent=2)

def load_processing_queue():
    """Load processing queue from file"""
    try:
        if os.path.exists("processing_queue.json"):
            with open("processing_queue.json", "r") as f:
                return json.load(f)
        return []
    except:
        return []

def save_processing_queue(queue_list):
    """Save processing queue to file"""
    with open("processing_queue.json", "w") as f:
        json.dump(queue_list, f, indent=2)

def update_queue_file():
    """Update queue file by removing completed items"""
    try:
        queue_list = list(processing_queue.queue)
        queue_data = []
        for item in queue_list:
            queue_data.append({
                'user_id': item['user_id'],
                'file_path': item['file_path'],
                'original_filename': item['original_filename'],
                'added_time': item['added_time'],
                'status': item.get('status', 'pending')
            })
        save_processing_queue(queue_data)
        log(f"Updated queue file with {len(queue_data)} items")
    except Exception as e:
        log(f"Error updating queue file: {e}")

def is_user_subscribed(user_id):
    """Check if user has active subscription"""
    subscriptions = load_subscriptions()
    user_id_str = str(user_id)
    
    if user_id_str not in subscriptions:
        return False, None
    
    user_data = subscriptions[user_id_str]
    
    # Check monthly subscription
    if "end_date" in user_data:
        end_date = datetime.fromisoformat(user_data["end_date"])
        if datetime.now() < end_date:
            return True, "monthly"
    
    # Check document-based subscription
    if "documents_remaining" in user_data and user_data["documents_remaining"] > 0:
        return True, "document"
    
    return False, None

def get_user_subscription_info(user_id):
    """Get detailed subscription info for user"""
    subscriptions = load_subscriptions()
    user_id_str = str(user_id)
    
    if user_id_str not in subscriptions:
        return None
    
    return subscriptions[user_id_str]

def create_main_menu():
    """Create main menu keyboard"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    markup.add(
        types.InlineKeyboardButton("📅 Monthly Subscription", callback_data="monthly_plans"),
        types.InlineKeyboardButton("📄 Document Based", callback_data="document_plans")
    )
    markup.add(
        types.InlineKeyboardButton("📊 My Subscription", callback_data="my_subscription"),
        types.InlineKeyboardButton("ℹ️ Help", callback_data="help")
    )
    
    return markup

def create_monthly_plans_menu():
    """Create monthly plans menu"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    for plan_id, plan_info in MONTHLY_PLANS.items():
        button_text = f"{plan_info['name']} - Rs.{plan_info['price']}"
        markup.add(types.InlineKeyboardButton(button_text, callback_data=f"request_monthly_{plan_id}"))
    
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_to_main"))
    return markup

def create_document_plans_menu():
    """Create document plans menu"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for plan_id, plan_info in DOCUMENT_PLANS.items():
        button_text = f"{plan_info['name']} - Rs.{plan_info['price']}"
        markup.add(types.InlineKeyboardButton(button_text, callback_data=f"request_document_{plan_id}"))
    
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_to_main"))
    return markup

def create_admin_menu():
    """Create admin menu"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    markup.add(
        types.InlineKeyboardButton("👥 View Subscriptions", callback_data="admin_view_subs"),
        types.InlineKeyboardButton("📋 Pending Requests", callback_data="admin_pending")
    )
    markup.add(
        types.InlineKeyboardButton("✏️ Edit Subscription", callback_data="admin_edit"),
        types.InlineKeyboardButton("📊 Statistics", callback_data="admin_stats")
    )
    markup.add(
        types.InlineKeyboardButton("📄 Processing Queue", callback_data="admin_queue")
    )
    
    return markup

def process_documents_worker():
    """Worker thread to process documents from queue"""
    while True:
        try:
            # Get item from queue (blocking)
            queue_item = processing_queue.get()
            
            if queue_item is None:  # Shutdown signal
                break
            
            log(f"Processing document for user {queue_item['user_id']}")
            
            # Update queue file to mark as processing
            queue_item['status'] = 'processing'
            update_queue_file()
            
            # Update user about processing start
            try:
                bot.send_message(
                    queue_item['user_id'], 
                    "📄 <b>Your document is now being processed...</b>\n\n⏳ Please wait, this may take a few minutes."
                )
            except Exception as msg_error:
                log(f"Error sending processing message: {msg_error}")
            
            # Process the document
            try:
                process_turnitin(queue_item['file_path'], queue_item['user_id'], bot)
                log(f"Successfully processed document for user {queue_item['user_id']}")
                
                # Mark as completed
                queue_item['status'] = 'completed'
                
            except Exception as process_error:
                log(f"Error processing document for user {queue_item['user_id']}: {process_error}")
                try:
                    bot.send_message(
                        queue_item['user_id'], 
                        f"❌ <b>Error processing document:</b>\n\n{str(process_error)}\n\n💡 Please try again or contact support."
                    )
                except:
                    pass
                
                # Mark as failed
                queue_item['status'] = 'failed'
            
            # Update queue file after processing
            update_queue_file()
            
            # Mark task as done
            processing_queue.task_done()
            
        except Exception as worker_error:
            log(f"Worker thread error: {worker_error}")
            # Mark task as done even if there was an error
            try:
                processing_queue.task_done()
            except:
                pass

def start_processing_worker():
    """Start the document processing worker thread"""
    global processing_thread
    
    if processing_thread is None or not processing_thread.is_alive():
        processing_thread = threading.Thread(target=process_documents_worker, daemon=True)
        processing_thread.start()
        log("Document processing worker thread started")

def get_queue_position(user_id):
    """Get user's position in processing queue"""
    queue_list = list(processing_queue.queue)
    for i, item in enumerate(queue_list):
        if item['user_id'] == user_id:
            return i + 1
    return None

@bot.message_handler(commands=['approve'])
def approve_subscription(message):
    """Admin command to approve subscription requests"""
    if message.from_user.id != ADMIN_TELEGRAM_ID:
        return
    
    try:
        request_id = message.text.split(' ', 1)[1]
    except IndexError:
        bot.reply_to(message, "❌ Please provide request ID: /approve [request_id]")
        return
    
    pending_requests = load_pending_requests()
    
    if request_id not in pending_requests:
        bot.reply_to(message, "❌ Request ID not found")
        return
    
    request_data = pending_requests[request_id]
    
    if request_data["status"] != "pending":
        bot.reply_to(message, "❌ Request already processed")
        return
    
    # Approve the request
    subscriptions = load_subscriptions()
    user_id_str = str(request_data["user_id"])
    
    if request_data["plan_type"] == "monthly":
        # Add monthly subscription
        start_date = datetime.now()
        end_date = start_date + timedelta(days=request_data["duration"])
        
        subscriptions[user_id_str] = {
            "plan_type": "monthly",
            "plan_name": request_data["plan_name"],
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "price": request_data["price"]
        }
    
    else:  # document subscription
        subscriptions[user_id_str] = {
            "plan_type": "document",
            "plan_name": request_data["plan_name"],
            "documents_total": request_data["documents"],
            "documents_remaining": request_data["documents"],
            "purchase_date": datetime.now().isoformat(),
            "price": request_data["price"]
        }
    
    # Update request status
    request_data["status"] = "approved"
    request_data["approved_date"] = datetime.now().isoformat()
    
    save_subscriptions(subscriptions)
    save_pending_requests(pending_requests)
    
    # Notify user
    user_message = f"""✅ <b>Subscription Approved!</b>

📅 <b>Plan:</b> {request_data['plan_name']}
💰 <b>Price:</b> Rs.{request_data['price']}

🎉 Your subscription is now active! You can start uploading documents.

📄 Send me a document to get your Turnitin reports!"""
    
    bot.send_message(request_data["user_id"], user_message)
    
    # Confirm to admin
    bot.reply_to(message, f"✅ Subscription approved for user {request_data['user_id']}")

@bot.message_handler(commands=['edit_subscription'])
def edit_subscription_command(message):
    """Admin command to edit subscription end date"""
    if message.from_user.id != ADMIN_TELEGRAM_ID:
        return
    
    try:
        parts = message.text.split(' ')
        user_id = parts[1]
        new_end_date = parts[2]  # Format: YYYY-MM-DD
    except IndexError:
        bot.reply_to(message, "❌ Usage: /edit_subscription [user_id] [YYYY-MM-DD]")
        return
    
    try:
        datetime.strptime(new_end_date, "%Y-%m-%d")
    except ValueError:
        bot.reply_to(message, "❌ Invalid date format. Use YYYY-MM-DD")
        return
    
    subscriptions = load_subscriptions()
    
    if user_id not in subscriptions:
        bot.reply_to(message, "❌ User not found in subscriptions")
        return
    
    # Update end date
    subscriptions[user_id]["end_date"] = f"{new_end_date}T23:59:59"
    save_subscriptions(subscriptions)
    
    bot.reply_to(message, f"✅ Updated subscription end date for user {user_id} to {new_end_date}")

@bot.message_handler(content_types=['document'])
def handle_document(message):
    """Handle document uploads"""
    user_id = message.from_user.id
    
    # Check if user is admin (unlimited access)
    if user_id == ADMIN_TELEGRAM_ID:
        process_user_document(message)
        return
    
    # Check subscription status
    is_subscribed, sub_type = is_user_subscribed(user_id)
    
    if not is_subscribed:
        bot.reply_to(
            message,
            "<b>No Active Subscription</b>\n\nPlease purchase a subscription to use this service.",
            reply_markup=create_main_menu()
        )
        return
    
    # Check document limits for document-based subscriptions
    if sub_type == "document":
        subscriptions = load_subscriptions()
        user_data = subscriptions[str(user_id)]
        
        if user_data["documents_remaining"] <= 0:
            bot.reply_to(
                message,
                "<b>No Documents Remaining</b>\n\nYour document allowance has been used up. Please purchase a new plan.",
                reply_markup=create_main_menu()
            )
            return
        
        # Decrease document count
        user_data["documents_remaining"] -= 1
        save_subscriptions(subscriptions)
        
        remaining = user_data["documents_remaining"]
        bot.reply_to(message, f"📄 Processing document... ({remaining} documents remaining)")
    
    else:
        bot.reply_to(message, "📄 Processing your document...")
    
    # Process the document
    process_user_document(message)

def process_user_document(message):
    """Process uploaded document through Turnitin"""
    try:
        log(f"Received document from user {message.chat.id}: {message.document.file_name}")
        
        # Download file
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # Save file with user ID first in filename
        original_filename = message.document.file_name or "document"
        ext = os.path.splitext(original_filename)[1]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_filename = f"{message.chat.id}_{timestamp}_{original_filename}"
        
        upload_dir = "uploads"
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, new_filename)
        
        with open(file_path, 'wb') as f:
            f.write(downloaded_file)
        
        log(f"Saved document to {file_path}")
        
        # Add to processing queue
        queue_item = {
            'user_id': message.chat.id,
            'file_path': file_path,
            'original_filename': original_filename,
            'added_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'status': 'queued'
        }
        
        processing_queue.put(queue_item)
        queue_position = processing_queue.qsize()
        
        # Update queue file
        update_queue_file()
        
        # Notify user about queue position
        if queue_position == 1:
            queue_message = "📄 <b>Document added to processing queue</b>\n\n📄 Your document will be processed next."
        else:
            queue_message = f"📄 <b>Document added to processing queue</b>\n\n📊 Position in queue: <b>{queue_position}</b>\n⏳ Estimated wait time: <b>{(queue_position-1) * 3-5} minutes</b>"
        
        bot.send_message(message.chat.id, queue_message)
        log(f"Added document to queue for user {message.chat.id}. Queue size: {queue_position}")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Failed to process file: {e}")
        log(f"Error handling document: {e}")

if __name__ == "__main__":
    # Start the processing worker thread
    start_processing_worker()
    
    log("🤖 Subscription Telegram bot is running... (press Ctrl+C to stop)")
    try:
        bot.infinity_polling()
    except Exception as e:
        log(f"Infinity polling error: {e}")
    finally:
        # Shutdown the worker thread
        processing_queue.put(None)  # Signal to stop
        if processing_thread and processing_thread.is_alive():
            processing_thread.join(timeout=5)
        log("Bot shutdown complete")
    
    # Check subscription status
    is_subscribed, sub_type = is_user_subscribed(user_id)
    
    if is_subscribed:
        user_info = get_user_subscription_info(user_id)
        if sub_type == "monthly":
            end_date = datetime.fromisoformat(user_info["end_date"]).strftime("%Y-%m-%d")
            welcome_text = f"<b>Welcome back!</b>\n\nYour monthly subscription is active until: <b>{end_date}</b>\n\nSend me a document to get Turnitin reports!"
        else:
            docs_remaining = user_info["documents_remaining"]
            welcome_text = f"<b>Welcome back!</b>\n\nYou have <b>{docs_remaining}</b> document(s) remaining.\n\nSend me a document to get Turnitin reports!"
        
        bot.send_message(user_id, welcome_text)
    else:
        welcome_text = """<b>Welcome to Turnitin Report Bot!</b>

<b>What I can do:</b>
• Generate Turnitin Similarity Reports
• Generate AI Writing Reports
• Support multiple document formats

<b>Choose your subscription plan:</b>"""
        
        bot.send_message(
            user_id,
            welcome_text,
            reply_markup=create_main_menu()
        )

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    
    # Handle retry callbacks first
    if call.data.startswith("retry_"):
        handle_retry_callbacks(call)
        return
    
    # Admin callbacks
    if user_id == ADMIN_TELEGRAM_ID:
        handle_admin_callbacks(call)
        return
    
    # User callbacks
    if call.data == "monthly_plans":
        bot.edit_message_text(
            "<b>Monthly Subscription Plans</b>\n\nChoose your plan:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=create_monthly_plans_menu()
        )
    
    elif call.data == "document_plans":
        bot.edit_message_text(
            "<b>Document-Based Plans</b>\n\nChoose your plan:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=create_document_plans_menu()
        )
    
    elif call.data == "my_subscription":
        show_user_subscription(call)
    
    elif call.data == "help":
        help_text = """ℹ️ <b>How to use this bot:</b>

1️⃣ Choose a subscription plan
2️⃣ Make payment to bank account
3️⃣ Send payment slip via WhatsApp
4️⃣ Wait for admin approval
5️⃣ Start uploading documents!

📄 <b>Supported formats:</b> PDF, DOC, DOCX
📏 <b>Document requirements:</b> 500-10,000 words
📊 <b>Reports generated:</b> Similarity + AI Writing

💬 For support, contact: +94702947854"""
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_to_main"))
        
        bot.edit_message_text(
            help_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif call.data == "back_to_main":
        welcome_text = """🤖 <b>Turnitin Report Bot</b>

💳 <b>Choose your subscription plan:</b>"""
        
        bot.edit_message_text(
            welcome_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=create_main_menu()
        )
    
    elif call.data.startswith("request_monthly_"):
        plan_id = call.data.replace("request_monthly_", "")
        handle_monthly_request(call, plan_id)
    
    elif call.data.startswith("request_document_"):
        plan_id = call.data.replace("request_document_", "")
        handle_document_request(call, plan_id)

def handle_general_retry(chat_id, timestamp, retry_type, bot):
    """Handle general retry for various issues"""
    log(f"Handling general retry for user: {chat_id}, type: {retry_type}")
    
    # Get stored browser session
    from turnitin_processor import load_retry_session, remove_retry_session, cleanup_browser_resources
    
    browser_data = load_retry_session(chat_id)
    if not browser_data:
        bot.send_message(chat_id, "❌ Session expired. Please submit your document again.")
        return
    
    processing_messages = []
    
    try:
        # Extract browser objects
        page1 = browser_data.get('page1')
        
        if not page1:
            bot.send_message(chat_id, "❌ Browser session lost. Please submit your document again.")
            remove_retry_session(chat_id)
            return
        
        msg = bot.send_message(chat_id, "🔄 Retrying to access your submission...")
        processing_messages.append(msg.message_id)
        
        # Refresh the page and try again
        try:
            current_url = page1.url
            log(f"Refreshing page: {current_url}")
            page1.reload(timeout=30000)
            page1.wait_for_load_state('networkidle', timeout=30000)
            log("Page refreshed successfully")
        except Exception as refresh_error:
            log(f"Error refreshing page: {refresh_error}")
            # Try to navigate back to the submission
            try:
                # If we have the submission URL, navigate back to it
                page1.goto(current_url, timeout=30000)
                log("Navigated back to submission page")
            except Exception as nav_error:
                log(f"Error navigating back: {nav_error}")
                bot.send_message(chat_id, "❌ Could not access submission page. Please submit again.")
                remove_retry_session(chat_id)
                return
        
        # Try to download reports again
        from turnitin_reports import download_similarity_report, download_ai_report, send_reports_to_user, cleanup_files
        
        downloads_dir = "downloads"
        os.makedirs(downloads_dir, exist_ok=True)
        
        # Check if reports are now available
        from turnitin_reports import check_reports_availability
        reports_ready = check_reports_availability(page1)
        
        if not reports_ready:
            bot.send_message(chat_id, "⚠️ Reports are still not ready. Please wait longer and try submitting a new document if the issue persists.")
            remove_retry_session(chat_id)
            return
        
        # Try downloading reports
        sim_filename = download_similarity_report(page1, chat_id, timestamp, downloads_dir)
        ai_filename = download_ai_report(page1, chat_id, timestamp, downloads_dir)
        
        # Check if download was successful
        if sim_filename and os.path.exists(sim_filename):
            log("General retry successful - reports downloaded")
            
            # Send reports to user
            send_reports_to_user(chat_id, sim_filename, ai_filename, bot, processing_messages)
            
            # Clean up files
            file_path = browser_data.get('file_path')
            cleanup_files(sim_filename, ai_filename, file_path)
            
            # Clean up browser and remove from retry queue
            p = browser_data.get('p')
            browser = browser_data.get('browser')
            context = browser_data.get('context')
            page = browser_data.get('page')
            cleanup_browser_resources(p, browser, context, page, page1)
            remove_retry_session(chat_id)
            
            log("General retry process completed successfully")
        else:
            # Still couldn't download
            bot.send_message(chat_id, "❌ Still couldn't access the reports. Please try submitting a new document.")
            
            # Clean up browser and remove from retry queue
            p = browser_data.get('p')
            browser = browser_data.get('browser')
            context = browser_data.get('context')
            page = browser_data.get('page')
            cleanup_browser_resources(p, browser, context, page, page1)
            remove_retry_session(chat_id)
            
    except Exception as e:
        log(f"Error during general retry: {e}")
        bot.send_message(chat_id, f"❌ General retry failed: {e}")
        
        # Clean up on retry failure
        if browser_data:
            p = browser_data.get('p')
            browser = browser_data.get('browser')
            context = browser_data.get('context')
            page = browser_data.get('page')
            page1 = browser_data.get('page1')
            cleanup_browser_resources(p, browser, context, page, page1)
        
        remove_retry_session(chat_id)
    
    finally:
        # Clean up processing messages
        for message_id in processing_messages:
            try:
                bot.delete_message(chat_id, message_id)
            except:
                pass

def show_user_subscription(call):
    """Show user's current subscription details"""
    user_id = call.from_user.id
    is_subscribed, sub_type = is_user_subscribed(user_id)
    
    if not is_subscribed:
        bot.edit_message_text(
            "❌ <b>No Active Subscription</b>\n\nYou don't have an active subscription. Please choose a plan:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=create_main_menu()
        )
        return
    
    user_info = get_user_subscription_info(user_id)
    
    if sub_type == "monthly":
        end_date = datetime.fromisoformat(user_info["end_date"]).strftime("%Y-%m-%d")
        plan_name = user_info.get("plan_name", "Monthly")
        
        subscription_text = f"""✅ <b>Active Monthly Subscription</b>

📅 <b>Plan:</b> {plan_name}
📆 <b>End Date:</b> {end_date}
💳 <b>Status:</b> Active

📄 Send me a document to get your Turnitin reports!"""
    
    else:  # document-based
        docs_remaining = user_info["documents_remaining"]
        docs_total = user_info.get("documents_total", docs_remaining)
        docs_used = docs_total - docs_remaining
        
        subscription_text = f"""✅ <b>Active Document Subscription</b>

📄 <b>Documents Remaining:</b> {docs_remaining}
📊 <b>Documents Used:</b> {docs_used}/{docs_total}
💳 <b>Status:</b> Active

📄 Send me a document to get your Turnitin reports!"""
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_to_main"))
    
    bot.edit_message_text(
        subscription_text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

def handle_monthly_request(call, plan_id):
    """Handle monthly subscription request"""
    user_id = call.from_user.id
    plan_info = MONTHLY_PLANS[plan_id]
    
    # Save pending request
    pending_requests = load_pending_requests()
    request_id = f"{user_id}_{int(time.time())}"
    
    pending_requests[request_id] = {
        "user_id": user_id,
        "username": call.from_user.username or "No username",
        "first_name": call.from_user.first_name or "No name",
        "plan_type": "monthly",
        "plan_id": plan_id,
        "plan_name": plan_info["name"],
        "price": plan_info["price"],
        "duration": plan_info["duration"],
        "request_date": datetime.now().isoformat(),
        "status": "pending"
    }
    
    save_pending_requests(pending_requests)
    
    # Message to user
    user_message = f"""📋 <b>Subscription Request Submitted</b>

📅 <b>Plan:</b> {plan_info['name']}
💰 <b>Price:</b> Rs.{plan_info['price']}
🆔 <b>Your Telegram ID:</b> <code>{user_id}</code>

💳 <b>Payment Details:</b>
{BANK_DETAILS}

✅ Your request has been sent to admin for approval.
📧 You'll be notified once approved."""
    
    bot.edit_message_text(
        user_message,
        call.message.chat.id,
        call.message.message_id
    )
    
    # Notify admin
    admin_message = f"""📢 <b>New Subscription Request</b>

👤 <b>User:</b> {call.from_user.first_name} (@{call.from_user.username or 'No username'})
🆔 <b>Telegram ID:</b> {user_id}
📅 <b>Plan:</b> {plan_info['name']}
💰 <b>Price:</b> Rs.{plan_info['price']}
📝 <b>Request ID:</b> {request_id}

Use /approve {request_id} to approve this request."""
    
    bot.send_message(ADMIN_TELEGRAM_ID, admin_message)

def handle_document_request(call, plan_id):
    """Handle document-based subscription request"""
    user_id = call.from_user.id
    plan_info = DOCUMENT_PLANS[plan_id]
    
    # Save pending request
    pending_requests = load_pending_requests()
    request_id = f"{user_id}_{int(time.time())}"
    
    pending_requests[request_id] = {
        "user_id": user_id,
        "username": call.from_user.username or "No username",
        "first_name": call.from_user.first_name or "No name",
        "plan_type": "document",
        "plan_id": plan_id,
        "plan_name": plan_info["name"],
        "price": plan_info["price"],
        "documents": plan_info["documents"],
        "request_date": datetime.now().isoformat(),
        "status": "pending"
    }
    
    save_pending_requests(pending_requests)
    
    # Message to user
    user_message = f"""📋 <b>Subscription Request Submitted</b>

📄 <b>Plan:</b> {plan_info['name']}
💰 <b>Price:</b> Rs.{plan_info['price']}
🆔 <b>Your Telegram ID:</b> <code>{user_id}</code>

💳 <b>Payment Details:</b>
{BANK_DETAILS}

✅ Your request has been sent to admin for approval.
📧 You'll be notified once approved."""
    
    bot.edit_message_text(
        user_message,
        call.message.chat.id,
        call.message.message_id
    )
    
    # Notify admin
    admin_message = f"""📢 <b>New Document Subscription Request</b>

👤 <b>User:</b> {call.from_user.first_name} (@{call.from_user.username or 'No username'})
🆔 <b>Telegram ID:</b> {user_id}
📄 <b>Plan:</b> {plan_info['name']}
💰 <b>Price:</b> Rs.{plan_info['price']}
📝 <b>Request ID:</b> {request_id}

Use /approve {request_id} to approve this request."""
    
    bot.send_message(ADMIN_TELEGRAM_ID, admin_message)

def handle_admin_callbacks(call):
    """Handle admin callback queries"""
    if call.data == "admin_view_subs":
        show_all_subscriptions(call)
    elif call.data == "admin_pending":
        show_pending_requests(call)
    elif call.data == "admin_stats":
        show_admin_stats(call)
    elif call.data == "admin_queue":
        show_processing_queue(call)
    elif call.data == "back_to_admin":
        bot.edit_message_text(
            "<b>Admin Panel</b>\n\nWelcome admin! Choose an option:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=create_admin_menu()
        )

def show_all_subscriptions(call):
    """Show all active subscriptions to admin"""
    subscriptions = load_subscriptions()
    
    if not subscriptions:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_to_admin"))
        bot.edit_message_text(
            "📋 <b>No Active Subscriptions</b>",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        return
    
    subscription_text = "👥 <b>Active Subscriptions</b>\n\n"
    
    for user_id, user_data in subscriptions.items():
        if "end_date" in user_data:
            end_date = datetime.fromisoformat(user_data["end_date"])
            if datetime.now() < end_date:
                subscription_text += f"🆔 {user_id}\n📅 Until: {end_date.strftime('%Y-%m-%d')}\n📋 Plan: {user_data.get('plan_name', 'Unknown')}\n\n"
        
        if "documents_remaining" in user_data and user_data["documents_remaining"] > 0:
            subscription_text += f"🆔 {user_id}\n📄 Docs: {user_data['documents_remaining']} remaining\n\n"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_to_admin"))
    
    bot.edit_message_text(
        subscription_text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

def show_pending_requests(call):
    """Show pending subscription requests to admin"""
    pending_requests = load_pending_requests()
    pending_only = {k: v for k, v in pending_requests.items() if v["status"] == "pending"}
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_to_admin"))
    
    if not pending_only:
        bot.edit_message_text(
            "📋 <b>No Pending Requests</b>",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        return
    
    requests_text = "📋 <b>Pending Requests</b>\n\n"
    
    for request_id, request_data in pending_only.items():
        requests_text += f"🆔 {request_data['user_id']}\n"
        requests_text += f"👤 {request_data['first_name']}\n"
        requests_text += f"📅 {request_data['plan_name']}\n"
        requests_text += f"💰 Rs.{request_data['price']}\n"
        requests_text += f"📝 ID: {request_id}\n\n"
    
    requests_text += "\nUse /approve [request_id] to approve"
    
    bot.edit_message_text(
        requests_text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

def show_admin_stats(call):
    """Show admin statistics"""
    subscriptions = load_subscriptions()
    pending_requests = load_pending_requests()
    
    active_monthly = 0
    active_document = 0
    total_pending = len([r for r in pending_requests.values() if r["status"] == "pending"])
    queue_size = processing_queue.qsize()
    
    for user_data in subscriptions.values():
        if "end_date" in user_data:
            end_date = datetime.fromisoformat(user_data["end_date"])
            if datetime.now() < end_date:
                active_monthly += 1
        
        if "documents_remaining" in user_data and user_data["documents_remaining"] > 0:
            active_document += 1
    
    stats_text = f"""📊 <b>Bot Statistics</b>

📅 <b>Active Monthly Subscriptions:</b> {active_monthly}
📄 <b>Active Document Subscriptions:</b> {active_document}
⏳ <b>Pending Requests:</b> {total_pending}
📄 <b>Processing Queue:</b> {queue_size} documents
👥 <b>Total Users in System:</b> {len(subscriptions)}

📈 <b>Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_to_admin"))
    
    bot.edit_message_text(
        stats_text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

def show_processing_queue(call):
    """Show current processing queue to admin"""
    queue_list = list(processing_queue.queue)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_to_admin"))
    
    if not queue_list:
        bot.edit_message_text(
            "📄 <b>Processing Queue</b>\n\nQueue is empty.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        return
    
    queue_text = f"📄 <b>Processing Queue ({len(queue_list)} items)</b>\n\n"
    
    for i, item in enumerate(queue_list[:10]):  # Show first 10 items
        status = item.get('status', 'pending')
        queue_text += f"{i+1}. User ID: {item['user_id']}\n"
        queue_text += f"   File: {os.path.basename(item['file_path'])}\n"
        queue_text += f"   Status: {status}\n"
        queue_text += f"   Added: {item.get('added_time', 'Unknown')}\n\n"
    
    if len(queue_list) > 10:
        queue_text += f"... and {len(queue_list) - 10} more items"
    
    bot.edit_message_text(
        queue_text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )
    
    try:
        datetime.strptime(new_end_date, "%Y-%m-%d")
    except ValueError:
        bot.reply_to(message, "❌ Invalid date format. Use YYYY-MM-DD")
        return
    
    subscriptions = load_subscriptions()
    
    if user_id not in subscriptions:
        bot.reply_to(message, "❌ User not found in subscriptions")
        return
    
    # Update end date
    subscriptions[user_id]["end_date"] = f"{new_end_date}T23:59:59"
    save_subscriptions(subscriptions)
    
    bot.reply_to(message, f"✅ Updated subscription end date for user {user_id} to {new_end_date}")

@bot.message_handler(content_types=['document'])
def handle_document(message):
    """Handle document uploads"""
    user_id = message.from_user.id
    
    # Check if user is admin (unlimited access)
    if user_id == ADMIN_TELEGRAM_ID:
        process_user_document(message)
        return
    
    # Check subscription status
    is_subscribed, sub_type = is_user_subscribed(user_id)
    
    if not is_subscribed:
        bot.reply_to(
            message,
            "<b>No Active Subscription</b>\n\nPlease purchase a subscription to use this service.",
            reply_markup=create_main_menu()
        )
        return
    
    # Check document limits for document-based subscriptions
    if sub_type == "document":
        subscriptions = load_subscriptions()
        user_data = subscriptions[str(user_id)]
        
        if user_data["documents_remaining"] <= 0:
            bot.reply_to(
                message,
                "<b>No Documents Remaining</b>\n\nYour document allowance has been used up. Please purchase a new plan.",
                reply_markup=create_main_menu()
            )
            return
        
        # Decrease document count
        user_data["documents_remaining"] -= 1
        save_subscriptions(subscriptions)
        
        remaining = user_data["documents_remaining"]
        bot.reply_to(message, f"📄 Processing document... ({remaining} documents remaining)")
    
    else:
        bot.reply_to(message, "📄 Processing your document...")
    
    # Process the document
    process_user_document(message)

def process_user_document(message):
    """Process uploaded document through Turnitin"""
    try:
        log(f"Received document from user {message.chat.id}: {message.document.file_name}")
        
        # Download file
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # Save file with user ID first in filename
        original_filename = message.document.file_name or "document"
        # We'll keep ext even if it's not directly used - it might be needed in future
        ext = os.path.splitext(original_filename)[1]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_filename = f"{message.chat.id}_{timestamp}_{original_filename}"
        
        upload_dir = "uploads"
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, new_filename)
        
        with open(file_path, 'wb') as f:
            f.write(downloaded_file)
        
        log(f"Saved document to {file_path}")
        
        # Add to processing queue
        queue_item = {
            'user_id': message.chat.id,
            'file_path': file_path,
            'original_filename': original_filename,
            'added_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'status': 'queued'
        }
        
        processing_queue.put(queue_item)
        queue_position = processing_queue.qsize()
        
        # Update queue file
        update_queue_file()
        
        # Notify user about queue position
        if queue_position == 1:
            queue_message = "📄 <b>Document added to processing queue</b>\n\n📄 Your document will be processed next."
        else:
            queue_message = f"📄 <b>Document added to processing queue</b>\n\n📊 Position in queue: <b>{queue_position}</b>\n⏳ Estimated wait time: <b>{(queue_position-1) * 3-5} minutes</b>"
        
        bot.send_message(message.chat.id, queue_message)
        log(f"Added document to queue for user {message.chat.id}. Queue size: {queue_position}")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Failed to process file: {e}")
        log(f"Error handling document: {e}")
def handle_retry_callbacks(call):
    """Handle retry-related callback queries - Updated for shortened callback data"""
    user_id = call.from_user.id
    data = call.data
    
    if data.startswith("retry_locked_"):
        # User clicked locked retry button
        bot.answer_callback_query(call.id, "⏰ Please wait for the countdown to finish.", show_alert=True)
    
    elif data.startswith("retry_ready_"):
        # User clicked ready retry button for submission finding
        parts = data.split("_", 3)
        if len(parts) >= 4:
            chat_id = int(parts[2])
            title_hash = parts[3]  # This is now a hash instead of full title
            
            if chat_id == user_id:
                bot.edit_message_text(
                    "🔄 <b>Starting Retry Process...</b>\n\nPlease wait while we search for your document again.",
                    call.message.chat.id,
                    call.message.message_id
                )
                
                # Start retry process in a separate thread
                # We'll use the stored submission title from browser data instead of reconstructing from hash
                retry_thread = threading.Thread(
                    target=handle_retry_submission_by_id,
                    args=(chat_id, bot),
                    daemon=True
                )
                retry_thread.start()
            else:
                bot.answer_callback_query(call.id, "❌ This retry is not for you.", show_alert=True)
    
    # Handle download retry callbacks (shortened)
    elif data.startswith("retry_dl_locked_"):
        # User clicked locked download retry button
        bot.answer_callback_query(call.id, "⏰ Please wait for the countdown to finish.", show_alert=True)
    
    elif data.startswith("retry_dl_ready_"):
        # User clicked ready download retry button
        parts = data.split("_", 4)
        if len(parts) >= 5:
            chat_id = int(parts[3])
            timestamp_short = parts[4]  # Shortened timestamp
            
            if chat_id == user_id:
                bot.edit_message_text(
                    "🔄 <b>Starting Download Retry...</b>\n\nPlease wait while we attempt to download your reports again.",
                    call.message.chat.id,
                    call.message.message_id
                )
                
                # Start download retry process in a separate thread
                retry_thread = threading.Thread(
                    target=handle_retry_download_by_id,
                    args=(chat_id, bot),
                    daemon=True
                )
                retry_thread.start()
            else:
                bot.answer_callback_query(call.id, "❌ This retry is not for you.", show_alert=True)
    
    # Handle general retry callbacks (shortened)
    elif data.startswith("retry_gen_locked_"):
        # User clicked locked general retry button
        bot.answer_callback_query(call.id, "⏰ Please wait for the countdown to finish.", show_alert=True)
    
    elif data.startswith("retry_gen_ready_"):
        # User clicked ready general retry button
        parts = data.split("_", 4)
        if len(parts) >= 5:
            chat_id = int(parts[3])
            timestamp_short = parts[4]  # Shortened timestamp
            
            if chat_id == user_id:
                bot.edit_message_text(
                    "🔄 <b>Starting General Retry...</b>\n\nPlease wait while we check your submission again.",
                    call.message.chat.id,
                    call.message.message_id
                )
                
                # Start general retry process in a separate thread
                retry_thread = threading.Thread(
                    target=handle_general_retry_by_id,
                    args=(chat_id, bot),
                    daemon=True
                )
                retry_thread.start()
            else:
                bot.answer_callback_query(call.id, "❌ This retry is not for you.", show_alert=True)

def handle_retry_submission_by_id(chat_id, bot):
    """Handle retry for finding submission using stored browser data"""
    log(f"Handling retry for submission by chat_id: {chat_id}")
    
    # Get stored browser session
    from turnitin_processor import load_retry_session, remove_retry_session, cleanup_browser_resources
    
    browser_data = load_retry_session(chat_id)
    if not browser_data:
        bot.send_message(chat_id, "❌ Session expired. Please submit your document again.")
        return
    
    # Get the actual submission title from stored data
    submission_title = browser_data.get('submission_title')
    if not submission_title:
        bot.send_message(chat_id, "❌ Could not retrieve submission details. Please submit again.")
        remove_retry_session(chat_id)
        return
    
    # Use the existing retry handler with the actual submission title
    handle_retry_submission(chat_id, submission_title, bot)

def handle_retry_download_by_id(chat_id, bot):
    """Handle retry for downloading reports using stored browser data"""
    log(f"Handling download retry by chat_id: {chat_id}")
    
    # Get stored browser session  
    from turnitin_processor import load_retry_session, remove_retry_session
    
    browser_data = load_retry_session(chat_id)
    if not browser_data:
        bot.send_message(chat_id, "❌ Session expired. Please submit your document again.")
        return
    
    # Get the actual timestamp from stored data
    timestamp = browser_data.get('timestamp')
    if not timestamp:
        bot.send_message(chat_id, "❌ Could not retrieve session details. Please submit again.")
        remove_retry_session(chat_id)
        return
    
    # Use the existing retry handler with the actual timestamp
    handle_retry_download(chat_id, timestamp, bot)

def handle_general_retry_by_id(chat_id, bot):
    """Handle general retry using stored browser data"""
    log(f"Handling general retry by chat_id: {chat_id}")
    
    # Get stored browser session
    from turnitin_processor import load_retry_session, remove_retry_session, cleanup_browser_resources
    
    browser_data = load_retry_session(chat_id)
    if not browser_data:
        bot.send_message(chat_id, "❌ Session expired. Please submit your document again.")
        return
    
    # Get the actual timestamp from stored data
    timestamp = browser_data.get('timestamp')
    if not timestamp:
        bot.send_message(chat_id, "❌ Could not retrieve session details. Please submit again.")
        remove_retry_session(chat_id)
        return
    
    # Use a generic retry type since we don't store it
    retry_type = "general"
    
    processing_messages = []
    
    try:
        # Extract browser objects
        page1 = browser_data.get('page1')
        
        if not page1:
            bot.send_message(chat_id, "❌ Browser session lost. Please submit your document again.")
            remove_retry_session(chat_id)
            return
        
        msg = bot.send_message(chat_id, "🔄 Retrying to access your submission...")
        processing_messages.append(msg.message_id)
        
        # Refresh the page and try again
        try:
            current_url = page1.url
            log(f"Refreshing page: {current_url}")
            page1.reload(timeout=30000)
            page1.wait_for_load_state('networkidle', timeout=30000)
            log("Page refreshed successfully")
        except Exception as refresh_error:
            log(f"Error refreshing page: {refresh_error}")
            # Try to navigate back to the submission
            try:
                page1.goto(current_url, timeout=30000)
                log("Navigated back to submission page")
            except Exception as nav_error:
                log(f"Error navigating back: {nav_error}")
                bot.send_message(chat_id, "❌ Could not access submission page. Please submit again.")
                remove_retry_session(chat_id)
                return
        
        # Try to download reports again
        from turnitin_reports import download_similarity_report, download_ai_report, send_reports_to_user, cleanup_files
        
        downloads_dir = "downloads"
        os.makedirs(downloads_dir, exist_ok=True)
        
        # Check if reports are now available
        from turnitin_reports import check_reports_availability
        reports_ready = check_reports_availability(page1)
        
        if not reports_ready:
            bot.send_message(chat_id, "⚠️ Reports are still not ready. Please wait longer and try submitting a new document if the issue persists.")
            remove_retry_session(chat_id)
            return
        
        # Try downloading reports
        sim_filename = download_similarity_report(page1, chat_id, timestamp, downloads_dir)
        ai_filename = download_ai_report(page1, chat_id, timestamp, downloads_dir)
        
        # Check if download was successful
        if sim_filename and os.path.exists(sim_filename):
            log("General retry successful - reports downloaded")
            
            # Send reports to user
            send_reports_to_user(chat_id, sim_filename, ai_filename, bot, processing_messages)
            
            # Clean up files
            file_path = browser_data.get('file_path')
            cleanup_files(sim_filename, ai_filename, file_path)
            
            # Clean up browser and remove from retry queue
            p = browser_data.get('p')
            browser = browser_data.get('browser')
            context = browser_data.get('context')
            page = browser_data.get('page')
            cleanup_browser_resources(p, browser, context, page, page1)
            remove_retry_session(chat_id)
            
            log("General retry process completed successfully")
        else:
            # Still couldn't download
            bot.send_message(chat_id, "❌ Still couldn't access the reports. Please try submitting a new document.")
            
            # Clean up browser and remove from retry queue
            p = browser_data.get('p')
            browser = browser_data.get('browser')
            context = browser_data.get('context')
            page = browser_data.get('page')
            cleanup_browser_resources(p, browser, context, page, page1)
            remove_retry_session(chat_id)
            
    except Exception as e:
        log(f"Error during general retry: {e}")
        bot.send_message(chat_id, f"❌ General retry failed: {e}")
        
        # Clean up on retry failure
        if browser_data:
            p = browser_data.get('p')
            browser = browser_data.get('browser')
            context = browser_data.get('context')
            page = browser_data.get('page')
            page1 = browser_data.get('page1')
            cleanup_browser_resources(p, browser, context, page, page1)
        
        remove_retry_session(chat_id)
    
    finally:
        # Clean up processing messages
        for message_id in processing_messages:
            try:
                bot.delete_message(chat_id, message_id)
            except:
                pass
if __name__ == "__main__":
    # Start the processing worker thread
    start_processing_worker()
    
    log("🤖 Subscription Telegram bot is running... (press Ctrl+C to stop)")
    try:
        bot.infinity_polling()
    except Exception as e:
        log(f"Infinity polling error: {e}")
    finally:
        # Shutdown the worker thread
        processing_queue.put(None)  # Signal to stop
        if processing_thread and processing_thread.is_alive():
            processing_thread.join(timeout=5)
        log("Bot shutdown complete")