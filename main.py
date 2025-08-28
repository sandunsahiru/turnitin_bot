import os
import json
import time
import threading
import queue
import signal
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
import telebot
from telebot import types
from turnitin_processor import process_turnitin, shutdown_browser_session

# Load environment variables
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID"))

# Initialize standard bot
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode='HTML')

# Processing queue
processing_queue = queue.Queue()
processing_thread = None

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

def signal_handler(sig, frame):
    """Handle shutdown signals"""
    log("Shutdown signal received...")
    shutdown_browser_session()
    processing_queue.put(None)
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

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

def process_documents_worker():
    """Worker thread to process documents from queue"""
    while True:
        try:
            queue_item = processing_queue.get()
            
            if queue_item is None:  # Shutdown signal
                break
            
            log(f"Processing document for user {queue_item['user_id']}")
            
            try:
                bot.send_message(
                    queue_item['user_id'], 
                    "📄 Your document is now being processed..."
                )
            except Exception as msg_error:
                log(f"Error sending processing message: {msg_error}")
            
            # Process the document
            try:
                # Pass the bot instance to the processor
                process_turnitin(queue_item['file_path'], queue_item['user_id'], bot)
                log(f"Successfully processed document for user {queue_item['user_id']}")
                
            except Exception as process_error:
                log(f"Error processing document: {process_error}")
                try:
                    bot.send_message(
                        queue_item['user_id'], 
                        f"❌ Error processing document: {str(process_error)}\n\nPlease try again or contact support."
                    )
                except:
                    pass
            
            processing_queue.task_done()
            
        except Exception as worker_error:
            log(f"Worker thread error: {worker_error}")
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

def process_user_document(message):
    """Process uploaded document through Turnitin"""
    try:
        log(f"Received document from user {message.chat.id}: {message.document.file_name}")
        
        # Download file
        file_info = bot.get_file(message.document.file_id)
        if not file_info:
            bot.reply_to(message, "❌ Failed to get file information. Please try again.")
            return
            
        downloaded_file = bot.download_file(file_info.file_path)
        if not downloaded_file:
            bot.reply_to(message, "❌ Failed to download file. Please try again.")
            return
        
        # Save file
        original_filename = message.document.file_name or "document"
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
        
        # Notify user
        if queue_position == 1:
            queue_message = "📄 <b>Document queued for processing</b>\n\n📄 Your document will be processed next."
        else:
            estimated_wait = (queue_position - 1) * 2  # 2 minutes per document
            queue_message = f"📄 <b>Document queued for processing</b>\n\n📊 Position: <b>{queue_position}</b>\n⏳ Estimated wait: <b>{estimated_wait} minutes</b>"
        
        bot.send_message(message.chat.id, queue_message)
        log(f"Added document to queue for user {message.chat.id}. Queue size: {queue_position}")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Failed to process file: {e}")
        log(f"Error handling document: {e}")

# MESSAGE HANDLERS
@bot.message_handler(commands=['start'])
def send_welcome(message):
    """Handle /start command"""
    user_id = message.from_user.id
    
    # Admin gets admin panel
    if user_id == ADMIN_TELEGRAM_ID:
        bot.send_message(
            user_id,
            "🛠️ <b>Admin Panel</b>\n\nWelcome admin! Choose an option:",
            reply_markup=create_admin_menu()
        )
        return
    
    # Check user subscription
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
    
    log(f"DEBUG: Document received from user {user_id}")
    
    # Admin has unlimited access
    if user_id == ADMIN_TELEGRAM_ID:
        process_user_document(message)
        return
    
    # Check subscription
    is_subscribed, sub_type = is_user_subscribed(user_id)
    
    if not is_subscribed:
        bot.reply_to(
            message,
            "<b>No Active Subscription</b>\n\nPlease purchase a subscription to use this service.",
            reply_markup=create_main_menu()
        )
        return
    
    # Handle document-based subscription limits
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

if __name__ == "__main__":
    # Import and register callback handlers
    from bot_callbacks import register_callback_handlers
    register_callback_handlers(bot, ADMIN_TELEGRAM_ID, MONTHLY_PLANS, DOCUMENT_PLANS, BANK_DETAILS, 
                              load_pending_requests, save_pending_requests, load_subscriptions, 
                              save_subscriptions, is_user_subscribed, get_user_subscription_info,
                              create_main_menu, create_monthly_plans_menu, create_document_plans_menu,
                              create_admin_menu, processing_queue, log)
    
    start_processing_worker()
    
    log("🤖 Turnitin bot starting...")
    
    try:
        bot.infinity_polling(
            timeout=60,
            long_polling_timeout=60,
            restart_on_change=False
        )
    except Exception as e:
        log(f"Polling error: {e}")
    finally:
        log("Bot shutting down...")
        shutdown_browser_session()
        processing_queue.put(None)
        if processing_thread and processing_thread.is_alive():
            processing_thread.join(timeout=5)
        log("Bot shutdown complete")