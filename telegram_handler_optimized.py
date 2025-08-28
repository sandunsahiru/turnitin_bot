import telebot
import time
import threading
import os
from telebot import apihelper
from telebot.types import InputFile
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import logging
from datetime import datetime

class OptimizedTelegramBot:
    def __init__(self, token, parse_mode='HTML'):
        self.token = token
        self.parse_mode = parse_mode
        
        # Configure connection pooling and retry strategy
        self._setup_session()
        
        # Initialize bot with optimized settings (without session parameter)
        self.bot = telebot.TeleBot(
            token,
            parse_mode=parse_mode,
            threaded=False,  # Better control over threading
            skip_pending=True,  # Skip old updates on startup
            num_threads=2  # Limit concurrent threads
        )
        
        # Apply our optimized session to the bot's internal mechanisms
        self._apply_session_optimization()
        
        # Rate limiting
        self.last_request_time = {}
        self.request_lock = threading.Lock()
        
        # Setup logging
        self._setup_logging()
        
    def _setup_session(self):
        """Setup optimized HTTP session with connection pooling"""
        self.session = requests.Session()
        
        # Connection pooling and retry strategy
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            backoff_factor=1,
            respect_retry_after_header=True
        )
        
        adapter = HTTPAdapter(
            pool_connections=10,  # Number of connection pools
            pool_maxsize=20,     # Max connections per pool
            max_retries=retry_strategy
        )
        
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set default timeout
        self.session.timeout = 30
        
    def _apply_session_optimization(self):
        """Apply our optimized session to telebot's internal mechanisms"""
        try:
            # Try to apply to bot's session if it exists
            if hasattr(self.bot, 'session'):
                self.bot.session = self.session
            # For older versions, replace the global apihelper session
            elif hasattr(apihelper, 'session'):
                apihelper.session = self.session
            # As fallback, monkey patch the requests module used by apihelper
            else:
                # Store original get/post methods
                original_get = requests.get
                original_post = requests.post
                
                # Replace with session methods
                requests.get = self.session.get
                requests.post = self.session.post
                
        except Exception as e:
            self.logger.warning(f"Could not optimize session: {e}")
        
    def _setup_logging(self):
        """Setup logging for Telegram operations"""
        self.logger = logging.getLogger('telegram_bot')
        handler = logging.StreamHandler()
        formatter = logging.Formatter('[%(asctime)s] Telegram: %(message)s')
        handler.setFormatter(formatter)
        if not self.logger.handlers:
            self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
        
    def _rate_limit_check(self, chat_id, method_name):
        """Check and enforce rate limits per chat"""
        with self.request_lock:
            current_time = time.time()
            key = f"{chat_id}_{method_name}"
            
            if key in self.last_request_time:
                time_diff = current_time - self.last_request_time[key]
                if time_diff < 0.05:  # 50ms minimum between same operations
                    sleep_time = 0.05 - time_diff
                    time.sleep(sleep_time)
            
            self.last_request_time[key] = current_time
    
    def _handle_telegram_error(self, func, *args, max_retries=3, **kwargs):
        """Generic error handler with retry logic for Telegram API calls"""
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            
            except telebot.apihelper.ApiTelegramException as e:
                if e.error_code == 429:  # Too Many Requests
                    retry_after = int(e.result_json.get('parameters', {}).get('retry_after', 1))
                    self.logger.warning(f"Rate limited, waiting {retry_after} seconds")
                    time.sleep(retry_after)
                    continue
                elif e.error_code in [400, 403, 404]:  # Client errors - don't retry
                    self.logger.error(f"Telegram API error {e.error_code}: {e.description}")
                    return None
                elif attempt < max_retries - 1:  # Server errors - retry
                    wait_time = (attempt + 1) * 2  # Exponential backoff
                    self.logger.warning(f"Telegram error {e.error_code}, retrying in {wait_time}s")
                    time.sleep(wait_time)
                    continue
                else:
                    self.logger.error(f"Telegram API failed after {max_retries} attempts: {e.description}")
                    return None
            
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    self.logger.warning(f"Timeout, retrying in {wait_time}s")
                    time.sleep(wait_time)
                    continue
                else:
                    self.logger.error("Request timed out after all retries")
                    return None
            
            except requests.exceptions.ConnectionError:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 3
                    self.logger.warning(f"Connection error, retrying in {wait_time}s")
                    time.sleep(wait_time)
                    continue
                else:
                    self.logger.error("Connection failed after all retries")
                    return None
            
            except Exception as e:
                self.logger.error(f"Unexpected error: {e}")
                return None
        
        return None
    
    def send_message(self, chat_id, text, reply_markup=None, disable_web_page_preview=True):
        """Optimized send_message with error handling"""
        self._rate_limit_check(chat_id, 'send_message')
        
        # Split long messages to avoid Telegram limits
        if len(text) > 4096:
            messages = []
            for i in range(0, len(text), 4000):
                chunk = text[i:i+4000]
                result = self._handle_telegram_error(
                    self.bot.send_message,
                    chat_id=chat_id,
                    text=chunk,
                    reply_markup=reply_markup if i == 0 else None,
                    disable_web_page_preview=disable_web_page_preview
                )
                if result:
                    messages.append(result)
            return messages
        
        return self._handle_telegram_error(
            self.bot.send_message,
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            disable_web_page_preview=disable_web_page_preview
        )
    
    def send_document(self, chat_id, document, caption=None, timeout=60):
        """Optimized send_document with chunked upload for large files"""
        self._rate_limit_check(chat_id, 'send_document')
        
        try:
            # Check file size
            if hasattr(document, 'name'):
                file_size = os.path.getsize(document.name)
                if file_size > 50 * 1024 * 1024:  # 50MB limit
                    self.logger.error(f"File too large: {file_size} bytes")
                    return None
            
            # Use longer timeout for file uploads
            original_timeout = getattr(self.bot, 'timeout', 30)
            
            result = self._handle_telegram_error(
                self.bot.send_document,
                chat_id=chat_id,
                document=document,
                caption=caption,
                timeout=timeout
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Document upload failed: {e}")
            return None
    
    def delete_message(self, chat_id, message_id):
        """Optimized delete_message with proper error handling"""
        self._rate_limit_check(chat_id, 'delete_message')
        
        return self._handle_telegram_error(
            self.bot.delete_message,
            chat_id=chat_id,
            message_id=message_id,
            max_retries=1  # Don't retry deletions aggressively
        )
    
    def delete_messages_batch(self, chat_id, message_ids, delay=0.1):
        """Delete multiple messages with rate limiting"""
        results = []
        for message_id in message_ids:
            result = self.delete_message(chat_id, message_id)
            results.append(result)
            if delay > 0:
                time.sleep(delay)
        return results
    
    def edit_message_text(self, text, chat_id, message_id, reply_markup=None):
        """Optimized edit_message_text"""
        self._rate_limit_check(chat_id, 'edit_message_text')
        
        # Handle long messages
        if len(text) > 4096:
            text = text[:4090] + "..."
        
        return self._handle_telegram_error(
            self.bot.edit_message_text,
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=reply_markup
        )
    
    def edit_message_reply_markup(self, chat_id, message_id, reply_markup=None):
        """Optimized edit_message_reply_markup"""
        self._rate_limit_check(chat_id, 'edit_markup')
        
        return self._handle_telegram_error(
            self.bot.edit_message_reply_markup,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=reply_markup
        )
    
    def get_file(self, file_id):
        """Optimized get_file"""
        return self._handle_telegram_error(self.bot.get_file, file_id)
    
    def download_file(self, file_path, timeout=60):
        """Optimized download_file with chunked download"""
        try:
            url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
            
            response = self.session.get(url, timeout=timeout, stream=True)
            response.raise_for_status()
            
            content = b''
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    content += chunk
            
            return content
            
        except requests.exceptions.Timeout:
            self.logger.error("File download timed out")
            return None
        except requests.exceptions.RequestException as e:
            self.logger.error(f"File download failed: {e}")
            return None
    
    def reply_to(self, message, text, reply_markup=None):
        """Optimized reply_to"""
        return self.send_message(
            message.chat.id, 
            text, 
            reply_markup=reply_markup
        )
    
    def register_message_handler(self, func, **kwargs):
        """Register message handlers"""
        # Apply the decorator to the function and register it
        decorated_func = self.bot.message_handler(**kwargs)(func)
        return decorated_func
    
    def register_callback_query_handler(self, func, **kwargs):
        """Register callback query handlers"""
        return self.bot.callback_query_handler(**kwargs)(func)
    
    def infinity_polling(self, **kwargs):
        """Start infinity polling with error recovery"""
        while True:
            try:
                self.logger.info("Starting Telegram polling...")
                self.bot.infinity_polling(
                    timeout=kwargs.get('timeout', 60),
                    long_polling_timeout=kwargs.get('long_polling_timeout', 60),
                    **kwargs
                )
            except Exception as e:
                self.logger.error(f"Polling error: {e}")
                self.logger.info("Restarting polling in 5 seconds...")
                time.sleep(5)
    
    def stop_polling(self):
        """Stop polling gracefully"""
        try:
            self.bot.stop_polling()
            self.session.close()
            self.logger.info("Bot stopped gracefully")
        except Exception as e:
            self.logger.error(f"Error stopping bot: {e}")
    
    def get_stats(self):
        """Get connection and request statistics"""
        return {
            'session_active': self.session is not None,
            'total_requests': len(self.last_request_time),
            'last_request_times': dict(list(self.last_request_time.items())[-5:])  # Last 5 requests
        }