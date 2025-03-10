import os
import time
import random
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import telebot

# Load environment variables from .env
load_dotenv()
TURNITIN_EMAIL = os.getenv("TURNITIN_EMAIL")
TURNITIN_PASSWORD = os.getenv("TURNITIN_PASSWORD")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Initialize the Telegram bot
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode=None)

def log(message: str):
    """Log a message with a timestamp to the terminal."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def re_login(page):
    """
    Perform a full login sequence using credentials.
    Returns the popup page for the originality interface.
    """
    log("Session expired. Re-logging in using credentials...")
    page.goto("https://lspr.turnitin.com/home/sign-in", timeout=60000)
    time.sleep(random.uniform(2, 4))
    log("Filling in username...")
    page.locator('[data-test-id="username-input"]').click()
    page.locator('[data-test-id="username-input"]').fill(TURNITIN_EMAIL)
    time.sleep(random.uniform(2, 4))
    log("Filling in password...")
    page.locator('[data-test-id="password-input"]').click()
    page.locator('[data-test-id="password-input"]').fill(TURNITIN_PASSWORD)
    time.sleep(random.uniform(2, 4))
    log("Clicking 'Sign in' button...")
    page.get_by_role("button", name="Sign in").click()
    log("Waiting for login to complete...")
    page.wait_for_timeout(5000)
    log("Clicking 'Launch' button to enter originality interface...")
    with page.expect_popup() as popup_info:
        page.get_by_role("button", name="Launch").click()
    popup_page = popup_info.value
    # Update cookies
    page.context.storage_state(path="cookies.json")
    log("Re-login complete. Cookies updated.")
    return popup_page

def process_turnitin(file_path: str, chat_id: int):
    """
    Automate Turnitin processing:
      - Log in (or reuse cookies; if session expired, re-login)
      - Upload the document using the file chooser
      - Wait for processing (up to 2 minutes), then download the Similarity Report
      - Wait 1 minute, then download the AI Writing Report
      - Save downloaded files in the local 'downloads' folder
      - Send the downloaded files to the Telegram user
      - Delete the downloaded and uploaded files afterwards
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        bot.send_message(chat_id, "ℹ️ Starting Turnitin process...")
        log("Starting Turnitin process...")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            cookies_path = "cookies.json"

            # Create or load browser context with cookies
            if os.path.exists(cookies_path):
                log("Found saved cookies. Using them for the session.")
                context = browser.new_context(storage_state=cookies_path)
            else:
                log("No saved cookies found. Creating a new session.")
                context = browser.new_context()

            page = context.new_page()

            # Navigate to homepage using cookies
            page.goto("https://lspr.turnitin.com/home/", timeout=60000)
            time.sleep(random.uniform(2, 4))
            # If session expired, we may be redirected to sign-in page.
            if "sign-in" in page.url:
                log("Detected redirection to sign-in page. Session expired.")
                popup_page = re_login(page)
            else:
                log("Session valid. Proceeding with existing session.")
                # Click Launch button
                try:
                    with page.expect_popup() as popup_info:
                        page.get_by_role("button", name="Launch").click()
                    popup_page = popup_info.value
                except PlaywrightTimeout:
                    # If Launch doesn't appear, re-login.
                    log("Launch button not found. Re-logging in...")
                    popup_page = re_login(page)

            # Continue on originality submission page
            page1 = popup_page
            time.sleep(random.uniform(2, 4))
            log("On originality submission page. Clicking 'Upload' button...")
            page1.locator('[data-test-id="upload-button"]').click()
            time.sleep(random.uniform(2, 4))

            # Use file chooser instead of calling set_input_files on a button element
            log("Clicking 'Select File' button to trigger file chooser...")
            with page1.expect_file_chooser() as fc_info:
                page1.locator('[data-test-id="select-file-btn"]').click()
            file_chooser = fc_info.value
            log(f"Uploading file from path: {file_path}")
            file_chooser.set_files(file_path)
            time.sleep(random.uniform(2, 4))

            log("Clicking 'Confirm' to submit the file...")
            page1.get_by_role("button", name="Confirm").click()

            log("Waiting for submission status to become complete (up to 2 minutes)...")
            page1.wait_for_selector('[data-test-id="submission-status-complete-0"]', timeout=120000)
            page1.locator('[data-test-id="submission-status-complete-0"]').click()
            time.sleep(random.uniform(2, 4))

            log("Opening submission viewer...")
            with page1.expect_popup() as popup2_info:
                page1.locator('[data-test-id="open-submission-button"]').click()
            page2 = popup2_info.value

            log("Waiting 2 minutes for the report to process...")
            page2.wait_for_timeout(120000)

            # Ensure downloads folder exists
            downloads_dir = "downloads"
            os.makedirs(downloads_dir, exist_ok=True)

            log("Downloading Similarity Report...")
            page2.locator("tii-sws-download-btn-mfe").click()
            with page2.expect_download() as download_info:
                page2.get_by_role("button", name="Similarity Report", exact=True).click()
            download_sim = download_info.value
            sim_filename = os.path.join(downloads_dir, f"{chat_id}_{timestamp}.pdf")
            download_sim.save_as(sim_filename)
            log(f"Saved Similarity Report as {sim_filename}")

            log("Waiting 1 minute before downloading the AI Writing Report...")
            page2.wait_for_timeout(60000)
            log("Downloading AI Writing Report...")
            page2.locator("tii-sws-download-btn-mfe").click()
            with page2.expect_download() as download1_info:
                page2.get_by_role("button", name="AI Writing Report").click()
            download_ai = download1_info.value
            ai_filename = os.path.join(downloads_dir, f"{chat_id}_{timestamp}_AI.pdf")
            download_ai.save_as(ai_filename)
            log(f"Saved AI Writing Report as {ai_filename}")

            context.close()
            browser.close()

            # Send the downloaded files to Telegram user
            log("Sending Similarity Report to Telegram user...")
            with open(sim_filename, "rb") as sim_file:
                bot.send_document(chat_id, sim_file, caption="📄 Turnitin Similarity Report")
            log("Sending AI Writing Report to Telegram user...")
            with open(ai_filename, "rb") as ai_file:
                bot.send_document(chat_id, ai_file, caption="🤖 Turnitin AI Writing Report")

            bot.send_message(chat_id, "✅ Process complete. Reports have been sent.")
            log("Turnitin process complete and reports sent.")

            # Delete downloaded files and the uploaded file after sending
            if os.path.exists(sim_filename):
                os.remove(sim_filename)
                log(f"Deleted downloaded file {sim_filename}")
            if os.path.exists(ai_filename):
                os.remove(ai_filename)
                log(f"Deleted downloaded file {ai_filename}")
            if os.path.exists(file_path):
                os.remove(file_path)
                log(f"Deleted uploaded file {file_path}")
    except Exception as e:
        error_msg = f"❌ An error occurred: {e}"
        bot.send_message(chat_id, error_msg)
        log(f"ERROR: {error_msg}")

# Telegram command handler (for /start and /help)
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "Hello! Send me a document, and I'll return its Turnitin reports (Similarity and AI) as PDF files from the downloads folder.")

# Telegram document handler
@bot.message_handler(content_types=['document'])
def handle_docs(message):
    try:
        log(f"Received document from user {message.chat.id}: {message.document.file_name}")
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        original_filename = message.document.file_name or "document"
        ext = os.path.splitext(original_filename)[1]  # extract file extension
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_filename = f"{message.chat.id}_{timestamp}{ext}"
        upload_dir = "uploads"
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, new_filename)
        with open(file_path, 'wb') as f:
            f.write(downloaded_file)
        bot.reply_to(message, f"📥 Document received and saved as {new_filename}. Starting Turnitin analysis...")
        log(f"Saved document to {file_path}. Initiating Turnitin process.")
        process_turnitin(file_path, message.chat.id)
    except Exception as e:
        bot.reply_to(message, f"❌ Failed to process file: {e}")
        log(f"Error handling document: {e}")

if __name__ == "__main__":
    log("🤖 Telegram bot is running... (press Ctrl+C to stop)")
    try:
        bot.infinity_polling()
    except Exception as e:
        log(f"Infinity polling error: {e}")