import os
import json
import time
import threading
import signal
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
import telebot
from telebot import types

# Load environment variables
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID"))

# Initialize bot
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode='HTML')

# Processing queue for admin panel (using persistent queue system now)
from queue_manager import load_queue
processing_queue = load_queue  # Function reference for admin callbacks

# Subscription plans
MONTHLY_PLANS = {
    "1_month": {"price": 7500, "duration": 30, "name": "1 Month"},
    "3_months": {"price": 22500, "duration": 90, "name": "3 Months"},
    "6_months": {"price": 45000, "duration": 180, "name": "6 Months"},
    "12_months": {"price": 67500, "duration": 365, "name": "12 Months"}
}

DOCUMENT_PLANS = {
    "1_doc": {"price": 350, "documents": 1, "name": "1 Document"},
    "5_docs": {"price": 1500, "documents": 5, "name": "5 Documents"},
    "10_docs": {"price": 2500, "documents": 10, "name": "10 Documents"}
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
    # Browser cleanup is handled automatically by Playwright context manager
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

def safe_send_message(chat_id, text, reply_markup=None):
    """Safely send message with proper error handling"""
    try:
        return bot.send_message(chat_id, text, reply_markup=reply_markup)
    except telebot.apihelper.ApiTelegramException as e:
        if e.error_code == 403:
            log(f"User {chat_id} has blocked the bot, skipping message")
            return None
        elif e.error_code == 429:
            log(f"Rate limited, retrying message to {chat_id} in 5 seconds")
            time.sleep(5)
            try:
                return bot.send_message(chat_id, text, reply_markup=reply_markup)
            except:
                log(f"Failed to send message to {chat_id} after retry")
                return None
        else:
            log(f"Telegram API error {e.error_code} sending to {chat_id}: {e.description}")
            return None
    except Exception as e:
        log(f"Unexpected error sending message to {chat_id}: {e}")
        return None

# Old processing worker functions removed - now using processor_manager system

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
        
        # Add to new queue system and process immediately
        from queue_manager import add_to_queue
        from queue_processor import start_immediate_processing, is_processor_running

        queue_id = add_to_queue(file_path, message.chat.id, message.chat.id)
        if not queue_id:
            bot.reply_to(message, "❌ Failed to add document to queue. Please try again.")
            return

        log(f"Added document '{original_filename}' to queue for user {message.chat.id}. Queue ID: {queue_id}")

        # Check if processor is already running
        if is_processor_running():
            bot.send_message(message.chat.id, "✅ <b>Document added to batch!</b>\n\n⚡ <b>Processing Status:</b> Active batch in progress\n📊 Your document will be included in the current batch\n\n💡 You'll receive reports once the batch completes")
            return

        # Start immediate processing (single-threaded, no delays)
        bot.send_message(message.chat.id, "✅ <b>Document received!</b>\n\n🚀 Starting batch processing immediately...\n📊 Checking for additional documents to include in batch")

        try:
            processor_started = start_immediate_processing(bot)
            if processor_started:
                bot.send_message(message.chat.id, "🚀 <b>Batch processing started!</b>\n📊 Your document is being processed now")
            else:
                bot.send_message(message.chat.id, "⚠️ <b>Processing delayed</b>\nProcessor temporarily unavailable. Will retry automatically.")
        except Exception as e:
            log(f"Error starting immediate processing: {e}")
            bot.send_message(message.chat.id, "⚠️ <b>Processing Error</b>\nFailed to start processing. Please try again later.")
        
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
        safe_send_message(
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

        safe_send_message(user_id, welcome_text)
    else:
        welcome_text = """<b>Welcome to Turnitin Report Bot!</b>

<b>What I can do:</b>
• Generate Turnitin Similarity Reports
• Generate AI Writing Reports
• Support multiple document formats

<b>Choose your subscription plan:</b>"""

        safe_send_message(
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
    
    safe_send_message(request_data["user_id"], user_message)
    bot.reply_to(message, f"✅ Subscription approved for user {request_data['user_id']}")

@bot.message_handler(commands=['temp_email'])
def set_temp_email(message):
    """Admin command to set temporary email for Turnitin login"""
    if message.from_user.id != ADMIN_TELEGRAM_ID:
        return

    try:
        email = message.text.split(' ', 1)[1]

        # Store email temporarily (will be combined with password later)
        temp_data = {"temp_email": email}
        with open("temp_email_storage.json", "w") as f:
            json.dump(temp_data, f)

        bot.reply_to(message, f"✅ Temporary email set: {email}\n\nNow send: <code>/temp_password your_password</code>")

    except IndexError:
        bot.reply_to(message, "❌ Usage: /temp_email your_email@example.com")
    except Exception as e:
        bot.reply_to(message, f"❌ Error setting temporary email: {e}")

@bot.message_handler(commands=['temp_password'])
def set_temp_password(message):
    """Admin command to set temporary password for Turnitin login"""
    if message.from_user.id != ADMIN_TELEGRAM_ID:
        return

    try:
        password = message.text.split(' ', 1)[1]

        # Load previously set email
        email = None
        if os.path.exists("temp_email_storage.json"):
            with open("temp_email_storage.json", "r") as f:
                data = json.load(f)
                email = data.get("temp_email")

        if not email:
            bot.reply_to(message, "❌ Please set email first with: <code>/temp_email your_email@example.com</code>")
            return

        # Save both credentials with expiry
        from turnitin_auth import save_temp_credentials
        if save_temp_credentials(email, password):
            bot.reply_to(message, "✅ <b>Temporary credentials saved!</b>\n\n⏰ Valid for 6 hours\n🔐 Next login will use these credentials")

            # Clean up temporary email storage
            if os.path.exists("temp_email_storage.json"):
                os.remove("temp_email_storage.json")
        else:
            bot.reply_to(message, "❌ Failed to save temporary credentials")

    except IndexError:
        bot.reply_to(message, "❌ Usage: /temp_password your_password")
    except Exception as e:
        bot.reply_to(message, f"❌ Error setting temporary password: {e}")

@bot.message_handler(commands=['clear_temp_creds'])
def clear_temp_credentials_command(message):
    """Admin command to clear temporary credentials"""
    if message.from_user.id != ADMIN_TELEGRAM_ID:
        return

    try:
        from turnitin_auth import clear_temp_credentials
        if clear_temp_credentials():
            bot.reply_to(message, "✅ Temporary credentials cleared")
        else:
            bot.reply_to(message, "❌ No temporary credentials found")
    except Exception as e:
        bot.reply_to(message, f"❌ Error clearing credentials: {e}")

@bot.message_handler(commands=['check_temp_creds'])
def check_temp_credentials_command(message):
    """Admin command to check temporary credentials status"""
    if message.from_user.id != ADMIN_TELEGRAM_ID:
        return

    try:
        from turnitin_auth import load_temp_credentials
        email, password = load_temp_credentials()

        if email and password:
            # Load expiry info
            with open("temp_credentials.json", "r") as f:
                data = json.load(f)
                expires_at = datetime.fromisoformat(data.get("expires_at", ""))
                time_left = expires_at - datetime.now()

            if time_left.total_seconds() > 0:
                hours_left = int(time_left.total_seconds() // 3600)
                minutes_left = int((time_left.total_seconds() % 3600) // 60)
                bot.reply_to(message, f"✅ <b>Active temporary credentials:</b>\n\n📧 Email: {email}\n⏰ Expires in: {hours_left}h {minutes_left}m")
            else:
                bot.reply_to(message, "⚠️ Temporary credentials have expired")
        else:
            bot.reply_to(message, "❌ No active temporary credentials")

    except Exception as e:
        bot.reply_to(message, f"❌ Error checking credentials: {e}")

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

@bot.message_handler(commands=['processor_status'])
def check_processor_status_command(message):
    """Admin command to check processor status"""
    if message.from_user.id != ADMIN_TELEGRAM_ID:
        return

    try:
        from queue_processor import get_processor_status
        from queue_manager import get_pending_items

        status = get_processor_status()
        pending = get_pending_items()

        status_text = f"""🔧 <b>Queue Processor Status</b>

🟢 <b>Running:</b> {status['is_running']}
🌐 <b>Browser Active:</b> {status['browser_active']}
🔄 <b>Failure Count:</b> {status['failure_count']}
📋 <b>Queue Size:</b> {len(pending)} pending

⏱️ <b>Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

        bot.reply_to(message, status_text)

    except Exception as e:
        bot.reply_to(message, f"❌ Error checking processor status: {e}")

@bot.message_handler(commands=['force_stop_processor'])
def force_stop_processor_command(message):
    """Admin command to force stop processor"""
    if message.from_user.id != ADMIN_TELEGRAM_ID:
        return

    try:
        from queue_processor import force_stop_processor

        was_running = force_stop_processor()

        if was_running:
            bot.reply_to(message, "✅ Queue processor force stopped successfully")
        else:
            bot.reply_to(message, "ℹ️ Queue processor was not running")

    except Exception as e:
        bot.reply_to(message, f"❌ Error stopping processor: {e}")

@bot.message_handler(commands=['start_processor'])
def start_processor_command(message):
    """Admin command to manually start processor"""
    if message.from_user.id != ADMIN_TELEGRAM_ID:
        return

    try:
        from queue_processor import start_immediate_processing

        started = start_immediate_processing(bot)

        if started:
            bot.reply_to(message, "✅ Queue processor started successfully")
        else:
            bot.reply_to(message, "ℹ️ Processor already running or no pending documents")

    except Exception as e:
        bot.reply_to(message, f"❌ Error starting processor: {e}")

@bot.message_handler(commands=['reset_circuit_breaker'])
def reset_circuit_breaker_command(message):
    """Admin command to reset circuit breaker"""
    if message.from_user.id != ADMIN_TELEGRAM_ID:
        return

    try:
        from queue_processor import reset_circuit_breaker

        old_count = reset_circuit_breaker()
        bot.reply_to(message, f"✅ Circuit breaker reset successfully\n🔄 Cleared {old_count} previous failures")

    except Exception as e:
        bot.reply_to(message, f"❌ Error resetting circuit breaker: {e}")

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

def start_bot_with_restart():
    """Start bot with automatic restart on errors"""
    restart_count = 0
    max_restarts = 50  # Maximum number of restarts before giving up

    while restart_count < max_restarts:
        try:
            log("🤖 Turnitin bot starting...")

            # Start the bot polling
            bot.infinity_polling(
                timeout=60,
                long_polling_timeout=60,
                restart_on_change=False,
                none_stop=True  # Continue polling even on errors
            )

        except KeyboardInterrupt:
            log("Bot stopped by user (Ctrl+C)")
            break

        except telebot.apihelper.ApiTelegramException as e:
            if e.error_code == 403:
                log(f"Bot blocked by user, continuing polling... (restart #{restart_count + 1})")
            elif e.error_code == 429:
                log(f"Rate limited, waiting 30 seconds before restart... (restart #{restart_count + 1})")
                time.sleep(30)
            else:
                log(f"Telegram API error {e.error_code}: {e.description} (restart #{restart_count + 1})")

        except Exception as e:
            log(f"Polling error: {e} (restart #{restart_count + 1})")

        restart_count += 1

        if restart_count < max_restarts:
            wait_time = min(10, restart_count * 2)  # Exponential backoff up to 10 seconds
            log(f"Restarting bot in {wait_time} seconds...")
            time.sleep(wait_time)
        else:
            log(f"Maximum restart attempts ({max_restarts}) reached. Bot stopped.")
            break

    # Cleanup on exit
    log("Bot shutting down...")
    try:
        shutdown_browser_session()
        # Force stop processor if running
        try:
            from queue_processor import force_stop_processor, cleanup_browser_session
            force_stop_processor()
            cleanup_browser_session()
        except:
            pass
    except Exception as cleanup_error:
        log(f"Error during cleanup: {cleanup_error}")
    log("Bot shutdown complete")

if __name__ == "__main__":
    # Import and register callback handlers
    from bot_callbacks import register_callback_handlers
    register_callback_handlers(bot, ADMIN_TELEGRAM_ID, MONTHLY_PLANS, DOCUMENT_PLANS, BANK_DETAILS,
                              load_pending_requests, save_pending_requests, load_subscriptions,
                              save_subscriptions, is_user_subscribed, get_user_subscription_info,
                              create_main_menu, create_monthly_plans_menu, create_document_plans_menu,
                              create_admin_menu, processing_queue, log)

    # Processor starts automatically when documents are added to queue

    # Start bot with automatic restart capability
    start_bot_with_restart()
