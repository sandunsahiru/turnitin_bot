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

# Initialize bot
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

def process_user_document(message):
    """Process uploaded document through Turnitin"""
    try:
        log(f"Received document from user {message.chat.id}: {message.document.file_name}")
        
        # Download file
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
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
            estimated_wait = (queue_position - 1) * 2  # Reduced from 3-5 to 2 minutes
            queue_message = f"📄 <b>Document queued for processing</b>\n\n📊 Position: <b>{queue_position}</b>\n⏳ Estimated wait: <b>{estimated_wait} minutes</b>"
        
        bot.send_message(message.chat.id, queue_message)
        log(f"Added document to queue for user {message.chat.id}. Queue size: {queue_position}")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Failed to process file: {e}")
        log(f"Error handling document: {e}")

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    """Handle callback queries"""
    user_id = call.from_user.id
    
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
📝 <b>Document requirements:</b> 500-10,000 words
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

if __name__ == "__main__":
    start_processing_worker()
    
    log("🤖 Optimized Turnitin bot starting...")
    try:
        bot.infinity_polling()
    except Exception as e:
        log(f"Polling error: {e}")
    finally:
        log("Bot shutting down...")
        shutdown_browser_session()
        processing_queue.put(None)
        if processing_thread and processing_thread.is_alive():
            processing_thread.join(timeout=5)
        log("Bot shutdown complete")