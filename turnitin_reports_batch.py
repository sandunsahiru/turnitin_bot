import os
import time
from datetime import datetime
from turnitin_auth import browser_session, log, random_wait

def find_submission_row(page, title):
    """Find submission row using inbox table structure"""
    log(f"Looking for submission row with title: {title}")

    # Based on user's inbox HTML structure:
    # - Rows have data-paper-id attribute: <tr data-paper-id="2850856881">
    # - Title is in td.paper-title-column with data-title="Submission Title"
    # - Title text is in <a data-paper-title="56885365534c82">
    
    try:
        # Strategy 1: Find all rows with data-paper-id (actual submissions, not "Not yet submitted" rows)
        all_rows = page.locator('tr[data-paper-id]').all()
        log(f"Found {len(all_rows)} submission rows in inbox table")
        
        for row in all_rows:
            try:
                # Check if this row contains our title
                # Look for the title in the paper-title-column
                title_cell = row.locator('td.paper-title-column, td[data-title="Submission Title"]').first
                if title_cell.count() > 0:
                    cell_text = title_cell.inner_text()
                    if title in cell_text:
                        paper_id_attr = row.get_attribute('data-paper-id')
                        log(f"✓ Found matching row: Paper ID {paper_id_attr}, Title: {title}")
                        return row
            except Exception as row_error:
                log(f"Error checking row: {row_error}")
                continue
                
    except Exception as e:
        log(f"Error finding submission rows: {e}")

    log(f"⚠️ Could not find submission row for title: {title}")
    return None

def extract_similarity_score(row):
    """Extract similarity score using multiple selector strategies"""
    if not row:
        return None

    score_selectors = [
        '.or-score-column .similarity-text',      # Primary
        '.similarity-score',                      # Alternative 1
        '.or-percentage',                         # Alternative 2
        '[data-score]',                          # Alternative 3
        '*:has-text("%"):visible'                # Alternative 4: any element with %
    ]

    for selector in score_selectors:
        try:
            score_elem = row.locator(selector).first
            if score_elem.count() > 0 and score_elem.is_visible():
                score = score_elem.inner_text().strip()
                if '%' in score or score.replace('-', '').isdigit():
                    return score
        except Exception:
            continue

    # Manual text parsing as last resort
    try:
        row_text = row.inner_text()
        import re
        # Look for percentage pattern
        percentage_match = re.search(r'(\d{1,3}%)', row_text)
        if percentage_match:
            return percentage_match.group(1)
    except Exception:
        pass

    return None

def extract_paper_id(row):
    """Extract paper ID from row's data-paper-id attribute"""
    if not row:
        return None

    try:
        # Primary: Get from data-paper-id attribute on the row
        paper_id = row.get_attribute('data-paper-id')
        if paper_id and paper_id.isdigit():
            log(f"✓ Extracted Paper ID: {paper_id}")
            return paper_id
    except Exception as e:
        log(f"Error getting data-paper-id: {e}")

    # Fallback: Look in paper-id-column td
    try:
        id_cell = row.locator('td.paper-id-column, td[data-title="Paper ID"]').first
        if id_cell.count() > 0:
            paper_id = id_cell.inner_text().strip()
            if paper_id.isdigit():
                log(f"✓ Extracted Paper ID from cell: {paper_id}")
                return paper_id
    except Exception as e:
        log(f"Error getting paper ID from cell: {e}")

    log("⚠️ Could not extract paper ID")
    return None

def wait_for_similarity_scores(page, queue_items, max_wait_minutes=10):
    """Poll for similarity scores with 10-second intervals"""
    try:
        log(f"Waiting for similarity scores for {len(queue_items)} submissions...")

        max_attempts = (max_wait_minutes * 60) // 10  # 10 second intervals
        log(f"Will poll every 10 seconds for up to {max_wait_minutes} minutes ({max_attempts} attempts)")

        for attempt in range(max_attempts):
            log(f"Polling attempt {attempt + 1}/{max_attempts} - checking similarity scores...")

            try:
                # Refresh page safely
                page.reload()
                page.wait_for_load_state('networkidle', timeout=20000)
                random_wait(2, 3)
            except Exception as reload_error:
                log(f"Page reload failed (attempt {attempt + 1}): {reload_error}")
                # Don't crash, continue checking

            # Check each submission with enhanced resilience
            all_ready = True
            for queue_item in queue_items:
                title = queue_item.get("submission_title")
                if not title:
                    continue

                try:
                    # Find row using resilient selector strategy
                    row = find_submission_row(page, title)

                    if row:
                        # Extract similarity score using resilient method
                        score = extract_similarity_score(row)
                        if score:
                            queue_item["similarity_score"] = score
                            log(f"✓ {title}: Similarity {score}")

                            # Try to get paper ID with multiple selectors
                            paper_id = extract_paper_id(row)
                            if paper_id:
                                queue_item["paper_id"] = paper_id
                        else:
                            all_ready = False
                            log(f"⏳ {title}: Score not ready yet")
                    else:
                        all_ready = False
                        log(f"⏳ {title}: Submission not found yet")
                        
                except Exception as e:
                    log(f"Error checking {title}: {e}")
                    all_ready = False
            
            if all_ready:
                log("✅ All similarity scores ready!")
                return True

            # Wait 10 seconds before next check
            if attempt < max_attempts - 1:
                log("Waiting 10 seconds before next check...")
                time.sleep(10)
        
        log("⚠️ Timeout waiting for all scores")
        return False
        
    except Exception as e:
        log(f"Error waiting for scores: {e}")
        return False

def download_reports_for_batch(page, queue_items, bot):
    """Download similarity and AI reports for batch submissions"""
    try:
        log(f"Downloading reports for {len(queue_items)} submissions...")
        
        for queue_item in queue_items:
            title = queue_item.get("submission_title")
            chat_id = queue_item.get("chat_id")
            
            # Check if submission_title is missing - this means queue wasn't saved properly
            if not title or title.strip() == "":
                log(f"⚠️ Submission {queue_item.get('id')} has empty submission_title - marking as failed")
                log(f"This indicates the queue wasn't saved after batch submission")
                from queue_manager import update_queue_item
                update_queue_item(queue_item["id"], {
                    "status": "failed",
                    "error": "Empty submission_title - queue not saved properly after upload"
                })
                continue
            
            if not queue_item.get("similarity_score"):
                log(f"Skipping {title}: No score available yet")
                continue
            
            try:
                log(f"Downloading reports for: {title}")

                # Find submission row to ensure we click the correct link
                row = find_submission_row(page, title)
                if not row:
                    log(f"Could not find submission row for {title}")
                    continue

                # CRITICAL: All link selectors MUST search within 'row' only
                # This prevents clicking links from other submissions
                link_selectors = [
                    'a.similarity-open',                    # Primary: similarity score link (most reliable)
                    'a.btn-link.default-open',             # Fallback 1: title link
                    'a.btn-link',                          # Fallback 2: any button link in row
                ]

                report_page = None
                for selector in link_selectors:
                    try:
                        log(f"Trying link selector within row: {selector}")

                        # CRITICAL: Search ONLY within the row, never the entire page
                        links = row.locator(selector).all()
                        
                        if not links:
                            log(f"No links found with selector: {selector}")
                            continue

                        # Try only the first matching link within this row
                        link = links[0]
                        
                        if not link.is_visible():
                            log("Link not visible, trying next selector")
                            continue
                        
                        link_text = link.inner_text()[:30] if link.is_visible() else ""
                        log(f"Found link in row: '{link_text}...'")

                        # Click the link to open Feedback Studio
                        # Use force=True to bypass intercepting elements
                        with page.expect_popup(timeout=60000) as page1_info:
                            link.click(force=True, timeout=10000)
                            log(f"✓ Clicked link for '{title}' (forced click)")

                        report_page = page1_info.value
                        random_wait(2, 3)
                        log(f"✓ Opened report page for {title}")
                        break  # Success - exit selector loop

                    except Exception as link_error:
                        log(f"Link click failed: {link_error}")
                        continue

                    if report_page:
                        break

                # Check if we successfully opened the report page
                if not report_page:
                    log(f"⚠️ Could not open report page for {title}")
                    continue

                page1 = report_page
                
                # Wait for Feedback Studio to load by checking for tab navigator
                # Don't use networkidle - the page has dynamic content that never settles
                log("Waiting for Feedback Studio to load completely...")
                try:
                    # Wait for the tab navigator to appear (indicates page is ready)
                    page1.wait_for_selector('div.tab-navigator-container', timeout=120000)  # 2 minutes
                    log("✓ Tab navigator found - Feedback Studio loaded")
                    random_wait(2, 3)
                    
                    # Verify tabs are visible
                    similarity_tab = page1.locator('#tab-similarity').first
                    if similarity_tab.count() > 0:
                        log("✓ Similarity tab visible")
                    else:
                        log("⚠️ Similarity tab not found, but continuing...")
                        
                except Exception as load_error:
                    log(f"⚠️ Tab navigator not found after 2 minutes: {load_error}")
                    log("Continuing anyway - page may still be usable")
                
                # Download similarity report
                sim_file = download_similarity_report_new(page1, queue_item)
                
                # Download AI report
                ai_file = download_ai_report_new(page1, queue_item)
                
                # Send reports to user
                if sim_file or ai_file:
                    send_reports_to_user_queue(chat_id, sim_file, ai_file, bot, queue_item)
                    
                    # Update queue item to mark reports as downloaded and status as completed
                    from queue_manager import update_queue_item
                    update_queue_item(queue_item["id"], {
                        "report_downloaded": True,
                        "status": "completed"
                    })
                    log(f"✓ Marked {title} as completed with reports downloaded")
                
                # Close report page
                page1.close()
                random_wait(2, 3)
                
                # Go back to inbox
                page.bring_to_front()
                
            except Exception as e:
                log(f"Error downloading reports for {title}: {e}")
                continue
        
        log("Batch report download completed")
        return True
        
    except Exception as e:
        log(f"Error in batch report download: {e}")
        return False

def download_similarity_report_new(page1, queue_item):
    """Download similarity report with polling for button availability"""
    try:
        chat_id = queue_item.get("chat_id")
        timestamp = queue_item.get("timestamp", "").replace(":", "").replace("-", "").replace("T", "")[:14]
        downloads_dir = "downloads"
        os.makedirs(downloads_dir, exist_ok=True)

        # Poll for download button availability (10-second intervals, up to 2 minutes)
        download_attempts = 12
        download_button_ready = False

        # Multiple selector strategies for download button (Shadow DOM)
        download_button_selectors = [
            'tii-sws-download-btn-mfe',                           # Primary - custom element
            '#sws-download-btn-mfe',                              # ID selector
            'tii-sws-header-btn',                                 # Inner button element
            'button:has-text("Download")',                        # Text-based
            'tdl-labeled-button',                                 # Shadow DOM button
            '[withdatapx="DownloadMenuClicked"]'                  # Data attribute
        ]

        for download_attempt in range(1, download_attempts + 1):
            log(f"Looking for download button (attempt {download_attempt}/{download_attempts})...")

            for selector in download_button_selectors:
                try:
                    download_button = page1.locator(selector).first
                    if download_button.count() > 0:
                        # Try to click - use force if needed
                        try:
                            download_button.click(timeout=5000)
                            log(f"✓ Download button clicked with selector: {selector}")
                            download_button_ready = True
                            break
                        except Exception as click_error:
                            # Try force click
                            try:
                                download_button.click(force=True, timeout=5000)
                                log(f"✓ Download button clicked (forced) with selector: {selector}")
                                download_button_ready = True
                                break
                            except:
                                log(f"Selector {selector} found but not clickable: {click_error}")
                                continue
                                
                except Exception as selector_error:
                    continue
            
            if download_button_ready:
                break

            if download_attempt < download_attempts:
                log("Download button not ready, waiting 10 seconds...")
                time.sleep(10)

        if not download_button_ready:
            log("⚠️ Download button not available after 2 minutes")
            return None

        random_wait(2, 3)

        # Poll for Similarity Report button (10-second intervals, up to 1 minute)
        sim_button_attempts = 6
        sim_report_downloaded = False
        
        # Multiple selector strategies for Similarity Report button
        sim_button_selectors = [
            'button[data-px="SimReportDownloadClicked"]',         # Primary - data attribute
            'button:has-text("Similarity Report")',               # Text-based
            'li.download-menu-item button',                       # Menu item button
            '.download-menu button:first-child'                   # First button in menu
        ]

        for sim_attempt in range(1, sim_button_attempts + 1):
            log(f"Looking for Similarity Report button (attempt {sim_attempt}/{sim_button_attempts})...")

            for selector in sim_button_selectors:
                try:
                    sim_button = page1.locator(selector).first
                    if sim_button.count() > 0:
                        # Try to click and download
                        try:
                            with page1.expect_download(timeout=60000) as download_info:  # Increased to 60s
                                sim_button.click(timeout=5000)
                                log(f"✓ Similarity Report button clicked with selector: {selector}")

                            download_sim = download_info.value
                            sim_filename = os.path.join(downloads_dir, f"{chat_id}_{timestamp}_similarity.pdf")
                            download_sim.save_as(sim_filename)
                            log(f"✓ Saved Similarity Report: {sim_filename}")
                            sim_report_downloaded = True
                            return sim_filename
                            
                        except Exception as click_error:
                            # Try force click
                            try:
                                with page1.expect_download(timeout=60000) as download_info:  # Increased to 60s
                                    sim_button.click(force=True, timeout=5000)
                                    log(f"✓ Similarity Report button clicked (forced) with selector: {selector}")

                                download_sim = download_info.value
                                sim_filename = os.path.join(downloads_dir, f"{chat_id}_{timestamp}_similarity.pdf")
                                download_sim.save_as(sim_filename)
                                log(f"✓ Saved Similarity Report: {sim_filename}")
                                sim_report_downloaded = True
                                return sim_filename
                            except:
                                log(f"Selector {selector} found but click/download failed: {click_error}")
                                continue

                except Exception as selector_error:
                    continue
            
            if sim_report_downloaded:
                break

            if sim_attempt < sim_button_attempts:
                log("Similarity Report button not ready, waiting 10 seconds...")
                time.sleep(10)

        if not sim_report_downloaded:
            log("⚠️ Similarity Report button not available after 1 minute")
            return None

    except Exception as e:
        log(f"Error downloading similarity report: {e}")
        return None

def download_ai_report_new(page1, queue_item):
    """Download AI report with polling for button availability"""
    try:
        chat_id = queue_item.get("chat_id")
        timestamp = queue_item.get("timestamp", "").replace(":", "").replace("-", "").replace("T", "")[:14]
        downloads_dir = "downloads"

        random_wait(2, 3)

        # After similarity report download, the dropdown closes
        # Need to click download button AGAIN to reopen dropdown for AI report
        log("Reopening download menu for AI report...")
        
        # Poll for download button (10-second intervals, up to 1 minute)
        download_attempts = 6
        download_button_ready = False
        
        download_button_selectors = [
            'tii-sws-download-btn-mfe',                           # Primary - web component
            'button:has-text(\"Download\")',                      # Text-based
            '[data-px=\"DownloadMenuClicked\"]',                  # Data attribute
            'button.download-button'                              # Class-based
        ]

        for download_attempt in range(1, download_attempts + 1):
            log(f"Looking for download button to reopen menu (attempt {download_attempt}/{download_attempts})...")

            for selector in download_button_selectors:
                try:
                    download_button = page1.locator(selector).first
                    if download_button.count() > 0:
                        # Try to click - use force if needed
                        try:
                            download_button.click(timeout=5000)
                            log(f"✓ Download button clicked to reopen menu with selector: {selector}")
                            download_button_ready = True
                            break
                        except Exception as click_error:
                            # Try force click
                            try:
                                download_button.click(force=True, timeout=5000)
                                log(f"✓ Download button clicked (forced) to reopen menu with selector: {selector}")
                                download_button_ready = True
                                break
                            except:
                                log(f"Selector {selector} found but not clickable: {click_error}")
                                continue
                                
                except Exception as selector_error:
                    continue
            
            if download_button_ready:
                break

            if download_attempt < download_attempts:
                log("Download button not ready, waiting 10 seconds...")
                time.sleep(10)

        if not download_button_ready:
            log("⚠️ Download button not available to reopen menu after 1 minute")
            return None

        random_wait(2, 3)
        
        # CRITICAL: Wait for menu to fully open before trying to click AI report button
        time.sleep(3)  # Extra wait to ensure menu is fully visible
        log("✓ Download menu reopened, waiting for menu to stabilize...")

        # Poll for AI Writing Report button (10-second intervals, up to 1 minute)
        ai_button_attempts = 6
        ai_report_downloaded = False
        
        # Multiple selector strategies for AI Writing Report button
        ai_button_selectors = [
            'button[data-px="AIWritingReportDownload"]',          # Primary - data attribute
            'button:has-text("AI Writing Report")',               # Text-based
            'li.download-menu-item:nth-child(2) button',          # Second menu item
            '.download-menu button:nth-of-type(2)'                # Second button in menu
        ]

        for ai_attempt in range(1, ai_button_attempts + 1):
            log(f"Looking for AI Writing Report button (attempt {ai_attempt}/{ai_button_attempts})...")

            for selector in ai_button_selectors:
                try:
                    ai_button = page1.locator(selector).first
                    if ai_button.count() > 0:
                        try:
                            with page1.expect_download(timeout=60000) as download_info:  # Increased to 60s
                                ai_button.click(timeout=5000)
                                log(f"✓ AI Writing Report button clicked with selector: {selector}")

                            download_ai = download_info.value
                            ai_filename = os.path.join(downloads_dir, f"{chat_id}_{timestamp}_ai.pdf")
                            download_ai.save_as(ai_filename)
                            log(f"✓ Saved AI Report: {ai_filename}")
                            ai_report_downloaded = True
                            return ai_filename
                            
                        except Exception as click_error:
                            try:
                                with page1.expect_download(timeout=60000) as download_info:  # Increased to 60s
                                    ai_button.click(force=True, timeout=5000)
                                    log(f"✓ AI Writing Report button clicked (forced) with selector: {selector}")

                                download_ai = download_info.value
                                ai_filename = os.path.join(downloads_dir, f"{chat_id}_{timestamp}_ai.pdf")
                                download_ai.save_as(ai_filename)
                                log(f"✓ Saved AI Report: {ai_filename}")
                                ai_report_downloaded = True
                                return ai_filename
                            except:
                                log(f"Selector {selector} found but click/download failed: {click_error}")
                                continue

                except Exception as selector_error:
                    continue
            
            if ai_report_downloaded:
                break

            if ai_attempt < ai_button_attempts:
                log("AI Writing Report button not ready, waiting 10 seconds...")
                time.sleep(10)

        if not ai_report_downloaded:
            log("⚠️ AI Writing Report button not available after 1 minute")
            return None

    except Exception as e:
        log(f"Error downloading AI report: {e}")
        return None

def send_reports_to_user_queue(chat_id, sim_filename, ai_filename, bot, queue_item):
    """Send downloaded reports to Telegram user with automatic retry on failure"""
    max_retries = 3
    retry_delay = 5  # seconds
    
    def send_with_retry(send_func, description):
        """Helper function to retry sending with delays"""
        for attempt in range(1, max_retries + 1):
            try:
                send_func()
                log(f"✓ {description} (attempt {attempt}/{max_retries})")
                return True
            except Exception as e:
                if attempt < max_retries:
                    log(f"⚠️ {description} failed (attempt {attempt}/{max_retries}): {e}")
                    log(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    log(f"✗ {description} failed after {max_retries} attempts: {e}")
                    return False
        return False
    
    try:
        title = queue_item.get("submission_title", "Unknown")
        sim_score = queue_item.get("similarity_score", "N/A")
        
        # Send similarity report with retry
        if sim_filename and os.path.exists(sim_filename):
            def send_sim():
                with open(sim_filename, "rb") as sim_file:
                    bot.send_document(
                        chat_id, 
                        sim_file, 
                        caption=f"📄 Similarity Report\n📋 Title: {title}\n🎯 Score: {sim_score}"
                    )
            
            send_with_retry(send_sim, f"Sent Similarity Report to {chat_id}")
        
        
        # Send AI report with retry
        if ai_filename and os.path.exists(ai_filename):
            def send_ai():
                with open(ai_filename, "rb") as ai_file:
                    bot.send_document(
                        chat_id, 
                        ai_file, 
                        caption=f"🤖 AI Writing Report\n📋 Title: {title}"
                    )
            
            send_with_retry(send_ai, f"Sent AI Report to {chat_id}")
        
        # Send completion message with retry
        if sim_filename and ai_filename:
            def send_completion():
                bot.send_message(chat_id, "✅ <b>Reports Delivered!</b>\n\n📊 Both reports sent successfully!", parse_mode="HTML")
            
            send_with_retry(send_completion, "Sent completion message")
        
        # Cleanup downloaded report files
        if sim_filename and os.path.exists(sim_filename):
            os.remove(sim_filename)
        if ai_filename and os.path.exists(ai_filename):
            os.remove(ai_filename)
        
        # Cleanup uploaded file from uploads folder
        try:
            file_path = queue_item.get("file_path")
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                log(f"✓ Cleaned up uploaded file: {file_path}")
        except Exception as cleanup_error:
            log(f"Error cleaning up uploaded file: {cleanup_error}")
        
    except Exception as e:
        log(f"Error sending reports: {e}")
