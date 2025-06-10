import base64
import time
import os
import logging
import requests
import uuid
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from datetime import datetime
import json
from PIL import Image
from io import BytesIO

# Load environment variables from .env file
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

# Create screenshots directory
screenshots_dir = os.path.join(os.getcwd(), "screenshots")
if not os.path.exists(screenshots_dir):
    os.makedirs(screenshots_dir)
    logging.info(f"Created screenshots directory at: {screenshots_dir}")

def extract_captcha_with_gpt4o(screenshot_bytes):
    """Use GPT-4o Vision to extract CAPTCHA text from the image"""
    logging.info("Attempting to extract CAPTCHA text with GPT-4o...")
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logging.error("No OpenAI API key found in environment variables")
        return None
    
    # Convert bytes to base64
    screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
    
    # Save a copy of the full screenshot
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    full_screenshot_path = os.path.join(screenshots_dir, f"captcha_full_{timestamp}.png")
    with open(full_screenshot_path, "wb") as f:
        f.write(screenshot_bytes)
    
    # Prepare the API request
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # Create a system prompt and user prompt specifically for CAPTCHA extraction
    payload = {
        "model": "gpt-4o",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a specialized CAPTCHA recognition system. Your sole task is to identify and extract "
                    "the text or characters shown in CAPTCHA images. Provide ONLY the exact characters you see in "
                    "the CAPTCHA - no explanations, no additional text. If you're uncertain about a character, make "
                    "your best guess. Respond with just the raw CAPTCHA text."
                )
            },
            {
                "role": "user", 
                "content": [
                    {
                        "type": "text", 
                        "text": "This image contains a CAPTCHA from a trademark filing website. Extract ONLY the text from the CAPTCHA. Provide just the characters, nothing else."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{screenshot_base64}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 50
    }
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload
        )
        
        if response.status_code == 200:
            result = response.json()
            captcha_text = result["choices"][0]["message"]["content"].strip()
            logging.info(f"GPT-4o extracted CAPTCHA text: '{captcha_text}'")
            return captcha_text
        else:
            logging.error(f"GPT-4o API call failed with status code: {response.status_code}")
            logging.error(f"Response: {response.text}")
            return None
    except Exception as e:
        logging.error(f"Error calling GPT-4o API: {e}")
        return None

def crop_captcha_region(screenshot_bytes):
    """Attempt to isolate just the CAPTCHA region from the screenshot"""
    try:
        # Open the image
        img = Image.open(BytesIO(screenshot_bytes))
        
        # The CAPTCHA is typically in the middle-right section of the login page
        # These are approximate coordinates - may need adjustment
        width, height = img.size
        
        # Try to find the CAPTCHA area - this is a heuristic approach
        # For the Indian trademark site, the CAPTCHA is usually in the form section
        # Typical location might be in the middle-bottom part of the form
        
        # These values are approximations and might need adjustments
        left = width * 0.4  # Start from 40% of width
        top = height * 0.5   # Start from 50% of height
        right = width * 0.7  # End at 70% of width
        bottom = height * 0.6 # End at 60% of height
        
        # Crop the image
        captcha_region = img.crop((left, top, right, bottom))
        
        # Save the cropped image
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        captcha_path = os.path.join(screenshots_dir, f"captcha_crop_{timestamp}.png")
        captcha_region.save(captcha_path)
        logging.info(f"Saved cropped CAPTCHA image to: {captcha_path}")
        
        # Convert back to bytes
        buffered = BytesIO()
        captcha_region.save(buffered, format="PNG")
        return buffered.getvalue()
    except Exception as e:
        logging.error(f"Error cropping CAPTCHA region: {e}")
        return screenshot_bytes  # Return original if cropping fails

def get_screenshot(page, save=True):
    """Take a screenshot of the current page state and optionally save it to file"""
    logging.info("Taking screenshot of current page state")
    screenshot_bytes = page.screenshot()
    screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
    
    if save:
        # Generate timestamp for filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Generate a short unique ID
        short_uuid = str(uuid.uuid4())[:8]
        # Create filename
        filename = f"screen_{timestamp}_{short_uuid}.png"
        filepath = os.path.join(screenshots_dir, filename)
        
        # Save the screenshot
        with open(filepath, "wb") as f:
            f.write(base64.b64decode(screenshot_base64))
        logging.info(f"Screenshot saved to: {filepath}")
    
    logging.info("Screenshot captured successfully")
    return screenshot_base64, screenshot_bytes

def create_response(api_key, screenshot_base64=None, task_description=None, previous_response_id=None, call_id=None, acknowledged_safety_checks=None, current_url=None):
    """
    Create a response using the Responses API directly
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # Base payload
    payload = {
        "model": "computer-use-preview",
        "tools": [{
            "type": "computer_use_preview",
            "display_width": 1024,
            "display_height": 768,
            "environment": "browser"
        }],
        "truncation": "auto",
        "reasoning": {
            "summary": "concise",
        }
    }
    
    # Add inputs based on the request type
    if previous_response_id and call_id:
        # This is a follow-up request
        payload["previous_response_id"] = previous_response_id
        
        computer_call_output = {
            "type": "computer_call_output",
            "call_id": call_id,
            "output": {
                "type": "input_image",
                "image_url": f"data:image/png;base64,{screenshot_base64}"
            }
        }
        
        # Add safety checks if present
        if acknowledged_safety_checks:
            computer_call_output["acknowledged_safety_checks"] = acknowledged_safety_checks
            
        # Add current URL if available
        if current_url:
            computer_call_output["current_url"] = current_url
            
        payload["input"] = [computer_call_output]
        
    elif screenshot_base64 and task_description:
        # This is an initial request with screenshot
        payload["input"] = [{
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": task_description
                },
                {
                    "type": "input_image",
                    "image_url": f"data:image/png;base64,{screenshot_base64}"
                }
            ]
        }]
    else:
        # This is a basic request
        payload["input"] = "Hello"
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers=headers,
            json=payload
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            logging.error(f"API call failed with status code: {response.status_code}")
            logging.error(f"Response: {response.text}")
            return None
    except Exception as e:
        logging.error(f"API call error: {e}")
        return None

def handle_model_action(page, action):
    """Execute the action suggested by the model"""
    action_type = action.get("type")
    
    try:
        if action_type == "click":
            x, y = action.get("x"), action.get("y")
            button = action.get("button", "left")
            logging.info(f"EXECUTING: Click at ({x}, {y}) with button '{button}'")
            if button != "left" and button != "right":
                button = "left"
            page.mouse.click(x, y, button=button)
            logging.info(f"SUCCESS: Click performed at ({x}, {y})")

        elif action_type == "scroll":
            x, y = action.get("x"), action.get("y")
            scroll_x, scroll_y = action.get("scroll_x"), action.get("scroll_y")
            logging.info(f"EXECUTING: Scroll at ({x}, {y}) with offsets (scroll_x={scroll_x}, scroll_y={scroll_y})")
            page.mouse.move(x, y)
            page.evaluate(f"window.scrollBy({scroll_x}, {scroll_y})")
            logging.info(f"SUCCESS: Scroll performed")

        elif action_type == "keypress":
            keys = action.get("keys", [])
            logging.info(f"EXECUTING: Keypress sequence: {keys}")
            for k in keys:
                logging.info(f"Pressing key: '{k}'")
                if k.lower() == "enter":
                    page.keyboard.press("Enter")
                elif k.lower() == "space":
                    page.keyboard.press(" ")
                else:
                    page.keyboard.press(k)
            logging.info(f"SUCCESS: All keys pressed")
        
        elif action_type == "type":
            text = action.get("text", "")
            logging.info(f"EXECUTING: Type text: '{text}'")
            page.keyboard.type(text)
            logging.info(f"SUCCESS: Text typed")
        
        elif action_type == "wait":
            wait_time = 2
            logging.info(f"EXECUTING: Wait for {wait_time} seconds")
            time.sleep(wait_time)
            logging.info(f"SUCCESS: Wait completed")

        elif action_type == "screenshot":
            logging.info(f"EXECUTING: Screenshot action (no actual action needed)")
            
        else:
            logging.warning(f"UNKNOWN ACTION: {action}")

    except Exception as e:
        logging.error(f"ERROR: Failed to execute action {action_type}: {e}")

def extract_text_content(item):
    """Extract text content from message items"""
    if isinstance(item, dict):
        if item.get("type") == "output_text":
            return item.get("text", "")
        elif "content" in item:
            content = item.get("content", [])
            if isinstance(content, list):
                return " ".join([extract_text_content(c) for c in content])
            return str(content)
    return ""

def click_view_all_notifications(page):
    """Specifically look for and click the View All Notifications link"""
    logging.info("Attempting to find and click 'View All Notifications'...")
    
    # Try multiple strategies to find the link
    found = False
    
    # Strategy 1: Try to find by exact text
    try:
        view_all = page.locator("a:has-text('View All Notifications')").first
        if view_all:
            logging.info("Found 'View All Notifications' using exact text match")
            view_all.click()
            found = True
    except Exception as e:
        logging.warning(f"Couldn't find by exact text: {e}")
    
    # Strategy 2: Try to find link containing "View All"
    if not found:
        try:
            view_all = page.locator("a:has-text('View All')").first
            if view_all:
                logging.info("Found 'View All' link")
                view_all.click()
                found = True
        except Exception as e:
            logging.warning(f"Couldn't find 'View All' link: {e}")
    
    # Strategy 3: Look for specific coordinates on the notifications page
    if not found and "welcomeForm" in page.url:
        try:
            # Try clicking where the "View All Notifications" link typically is
            # These coordinates are approximate based on the screenshot
            logging.info("Trying to click at the coordinates where 'View All Notifications' should be")
            page.mouse.click(724, 473)  # Adjust these coordinates based on your screenshots
            found = True
        except Exception as e:
            logging.warning(f"Couldn't click at View All coordinates: {e}")
    
    return found

def click_second_view_all(page):
    """Specifically look for and click the View All link in the notifications page (second screen)"""
    logging.info("Attempting to find and click 'View All' in the notifications page...")
    
    # Try multiple strategies to find the link
    found = False
    
    # Strategy 1: Try to find by exact text in the circled area (from Image 2)
    try:
        # Look for the View All link in the upper right area (circled in red in Image 2)
        view_all = page.locator("a:has-text('View All')").first
        if view_all:
            logging.info("Found 'View All' link in notifications page")
            view_all.click()
            found = True
    except Exception as e:
        logging.warning(f"Couldn't find 'View All' link by text: {e}")
    
    # Strategy 2: Look for specific coordinates on the notifications page based on Image 2
    if not found:
        try:
            # Try clicking in the area circled in red in Image 2
            logging.info("Trying to click at the coordinates where 'View All' should be in the notifications page")
            page.mouse.click(1050, 315)  # These coordinates target the circled 'View All' in Image 2
            found = True
        except Exception as e:
            logging.warning(f"Couldn't click at View All coordinates in notifications page: {e}")
    
    return found

def click_export_to_excel(page):
    """Specifically look for and click the Export to Excel button"""
    logging.info("Attempting to find and click 'Export to Excel'...")
    
    # Try multiple strategies to find the button
    found = False
    
    # Strategy 1: Try to find by exact text (looking for the input button at the bottom)
    try:
        export_button = page.locator("input[value='Export to Excel']").first
        if export_button:
            logging.info("Found 'Export to Excel' button using exact match")
            export_button.click()
            found = True
    except Exception as e:
        logging.warning(f"Couldn't find Export button by exact match: {e}")
    
    # Strategy 2: Try to find by containing text
    if not found:
        try:
            export_button = page.locator("input:has-text('Export')").first
            if export_button:
                logging.info("Found Export button by partial text")
                export_button.click()
                found = True
        except Exception as e:
            logging.warning(f"Couldn't find Export button by partial text: {e}")
    
    # Strategy 3: Look for specific coordinates on the notifications page
    if not found and "Notification" in page.url:
        try:
            # Try clicking where the "Export to Excel" button typically is (from Image 3)
            logging.info("Trying to click at the coordinates where 'Export to Excel' should be")
            page.mouse.click(476, 842)  # Coordinates from Image 3 where Export to Excel button is
            found = True
        except Exception as e:
            logging.warning(f"Couldn't click at Export coordinates: {e}")
    
    return found

def check_and_scroll_to_bottom(page):
    """Scroll to the bottom of the page to find the Export to Excel button"""
    logging.info("Scrolling to the bottom of the page to find Export to Excel button...")
    
    # Scroll down in multiple steps to ensure we reach the bottom
    try:
        # First scroll attempt
        page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.7)")
        time.sleep(0.5)
        
        # Second scroll attempt to reach bottom
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(0.5)
        
        logging.info("Successfully scrolled to the bottom of the page")
        return True
    except Exception as e:
        logging.error(f"Error scrolling to bottom: {e}")
        return False

def computer_use_loop(page, response_data, captcha_text=None):
    """Run the loop that executes computer actions until no 'computer_call' is found."""
    step_counter = 1
    captcha_detected = False
    captcha_entered = False
    view_all_notifications_clicked = False
    second_view_all_clicked = False
    export_clicked = False
    login_done = False
    
    while True:
        logging.info(f"\n=== STEP {step_counter} ===")
        
        if not response_data:
            logging.error("No valid response data. Exiting loop.")
            return None
        
        # Extract relevant data from response
        output_items = response_data.get("output", [])
        
        # Check for text messages that might indicate a captcha or need for manual input
        for item in output_items:
            if item.get("type") == "message":
                message_content = item.get("content", [])
                for content in message_content:
                    message_text = extract_text_content(content)
                    if "captcha" in message_text.lower():
                        captcha_detected = True
                    if "logged in" in message_text.lower() or "welcome" in message_text.lower():
                        login_done = True
        
        # Check if model provided any computer actions
        computer_calls = [item for item in output_items if item.get("type") == "computer_call"]
        if not computer_calls:
            # Check if we're at the CAPTCHA stage and need to enter it
            if captcha_detected and not captcha_entered and captcha_text and "frmloginNew" in page.url:
                logging.info("\n" + "!" * 50)
                logging.info(f"MODEL STOPPED BUT CAPTCHA DETECTED - ENTERING CAPTCHA: '{captcha_text}'")
                logging.info("!" * 50 + "\n")
                
                # Find and click the CAPTCHA field
                try:
                    captcha_field = page.locator('input[name="txtCaptcha"]').first
                    if captcha_field:
                        captcha_field.click()
                        time.sleep(0.5)
                        
                        # Enter the CAPTCHA text
                        page.keyboard.type(captcha_text)
                        captcha_entered = True
                        
                        # Now click the login button
                        login_button = page.locator('input[value="Login"]').first
                        if login_button:
                            login_button.click()
                            time.sleep(3)  # Wait for login to complete
                            
                            # Take a new screenshot
                            screenshot_base64, _ = get_screenshot(page)
                            
                            # Continue the automation with new instructions
                            new_task = "We've entered the CAPTCHA and logged in. Now please follow these steps exactly:\n" + \
                                       "1. First, click on 'View All Notifications' link\n" + \
                                       "2. Next, on the following page, click on the 'View All' link in the upper right (circled in red)\n" + \
                                       "3. Finally, scroll to the bottom and click 'Export to Excel' button"
                            
                            response_data = create_response(
                                api_key=os.getenv("OPENAI_API_KEY"),
                                screenshot_base64=screenshot_base64,
                                task_description=new_task
                            )
                            
                            if response_data:
                                step_counter += 1
                                continue
                except Exception as e:
                    logging.error(f"Error handling CAPTCHA entry: {e}")
            
            # Check if we need to click View All Notifications after login
            elif login_done and not view_all_notifications_clicked and "welcomeForm" in page.url:
                logging.info("Logged in but model stopped. Attempting to click View All Notifications manually...")
                
                # Try to click View All Notifications
                if click_view_all_notifications(page):
                    view_all_notifications_clicked = True
                    time.sleep(2)  # Wait for navigation
                    
                    # Take a new screenshot
                    screenshot_base64, _ = get_screenshot(page)
                    
                    # Continue with new instructions
                    new_task = "We've clicked on 'View All Notifications'. Now please click on the 'View All' link in the upper right corner (circled in red in the screenshot). After that page loads, scroll to the bottom and click 'Export to Excel'."
                    
                    response_data = create_response(
                        api_key=os.getenv("OPENAI_API_KEY"),
                        screenshot_base64=screenshot_base64,
                        task_description=new_task
                    )
                    
                    if response_data:
                        step_counter += 1
                        continue
            
            # Check if we need to click on the second "View All" link (after View All Notifications)
            elif view_all_notifications_clicked and not second_view_all_clicked:
                logging.info("Need to click on the second 'View All' link in the notifications page...")
                
                # Try to click the second View All link
                if click_second_view_all(page):
                    second_view_all_clicked = True
                    time.sleep(3)  # Wait for navigation
                    
                    # Take a new screenshot
                    screenshot_base64, _ = get_screenshot(page)
                    
                    # Continue with new instructions
                    new_task = "Great! Now we're on the detailed notifications page. Please scroll to the bottom of this page and click the 'Export to Excel' button."
                    
                    response_data = create_response(
                        api_key=os.getenv("OPENAI_API_KEY"),
                        screenshot_base64=screenshot_base64,
                        task_description=new_task
                    )
                    
                    if response_data:
                        step_counter += 1
                        continue
            
            # Check if we need to click Export to Excel after clicking View All
            elif second_view_all_clicked and not export_clicked and "Notification" in page.url:
                logging.info("On notifications page but model stopped. Attempting to scroll down and click Export to Excel...")
                
                # First, scroll to the bottom to find the Export to Excel button
                check_and_scroll_to_bottom(page)
                time.sleep(1)  # Give time for any page adjustments
                
                # Try to click Export to Excel
                if click_export_to_excel(page):
                    export_clicked = True
                    time.sleep(5)  # Wait for download to start
                    
                    # Take a new screenshot and finish
                    screenshot_base64, _ = get_screenshot(page)
                    
                    # Just log completion
                    logging.info("Export to Excel clicked successfully. Task should be complete.")
                    break
            
            # Not at any of the key stages or couldn't handle them, exit loop
            logging.info("No more computer actions requested. Task may be complete or requires human input.")
            logging.info("Final output from model:")
            for item in output_items:
                if item.get("type") == "message":
                    message_content = item.get("content", [])
                    for content in message_content:
                        text = extract_text_content(content)
                        if text:
                            logging.info(f"- Message: {text}")
                else:
                    logging.info(f"- {item.get('type')}")
            break

        # Process reasoning if present
        reasoning_items = [item for item in output_items if item.get("type") == "reasoning"]
        for item in reasoning_items:
            if "summary" in item:
                for summary in item.get("summary", []):
                    if "text" in summary:
                        logging.info(f"MODEL THINKING: {summary.get('text')}")

        # Get the computer action
        computer_call = computer_calls[0]
        call_id = computer_call.get("call_id")
        action = computer_call.get("action", {})
        
        logging.info(f"MODEL ACTION: {action.get('type')} - {action}")
        
        # Check if there are any pending safety checks
        pending_safety_checks = computer_call.get("pending_safety_checks", [])
        acknowledged_safety_checks = []
        
        if pending_safety_checks:
            logging.warning("⚠️ SAFETY CHECKS DETECTED ⚠️")
            for check in pending_safety_checks:
                logging.warning(f" - {check.get('code')}: {check.get('message')}")
                acknowledged_safety_checks.append(check)
            
            logging.info("Acknowledging safety checks and proceeding...")
        
        # Check action text for key stages
        action_text = str(action).lower()
        
        # Check if we're clicking View All Notifications
        if "view all notification" in action_text:
            view_all_notifications_clicked = True
            logging.info("Model is clicking View All Notifications")
        
        # Check if we're clicking the second View All link
        elif view_all_notifications_clicked and "view all" in action_text and not second_view_all_clicked:
            second_view_all_clicked = True
            logging.info("Model is clicking the second View All link")
        
        # Check if we're clicking Export to Excel
        elif "export" in action_text or "excel" in action_text:
            export_clicked = True
            logging.info("Model is clicking Export to Excel")
            
            # Special handling for the export action
            handle_model_action(page, action)
            logging.info("Export action executed. Waiting for download...")
            time.sleep(5)  # Give extra time for download
            
            # Check for downloads
            download_path = os.path.join(os.getcwd(), "downloads")
            if not os.path.exists(download_path):
                os.makedirs(download_path)
            
            # Take a final screenshot
            screenshot_base64, _ = get_screenshot(page)
            
            # Send final response to model to complete the task
            response_data = create_response(
                api_key=os.getenv("OPENAI_API_KEY"),
                screenshot_base64=screenshot_base64,
                previous_response_id=response_data.get("id"),
                call_id=call_id,
                acknowledged_safety_checks=acknowledged_safety_checks,
                current_url=page.url if "url" in dir(page) else None
            )
            
            step_counter += 1
            continue
        
        # Execute the regular action
        handle_model_action(page, action)
        logging.info("Waiting for page to settle after action...")
        time.sleep(1)  # Allow time for changes to take effect.
        
        # Get current URL if possible
        try:
            current_url = page.url
            logging.info(f"Current URL: {current_url}")
            
            # Check for successful login
            if "welcomeForm" in current_url and not login_done:
                login_done = True
                logging.info("LOGIN SUCCESSFUL! Now on welcome page.")
        except:
            current_url = None
            logging.info("Could not determine current URL")

        # Take a screenshot after the action
        screenshot_base64, _ = get_screenshot(page)
        
        # Send the screenshot back as a computer_call_output
        logging.info(f"Sending screenshot to OpenAI for next action...")
        
        # Send the next request
        response_data = create_response(
            api_key=os.getenv("OPENAI_API_KEY"),
            screenshot_base64=screenshot_base64,
            previous_response_id=response_data.get("id"),
            call_id=call_id,
            acknowledged_safety_checks=acknowledged_safety_checks,
            current_url=current_url
        )
        
        if not response_data:
            logging.error("Failed to get response from OpenAI. Exiting loop.")
            break
            
        logging.info(f"Received response from OpenAI")
        
        step_counter += 1

    return response_data
def main():
    # Set up parameters for the task
    login_url = "https://ipindiaonline.gov.in/trademarkefiling/user/frmloginNew.aspx"
    username = "Adv.Karan"
    password = "Ls123vs32!"
    
    # Create a downloads directory if it doesn't exist
    downloads_path = os.path.join(os.getcwd(), "downloads")
    if not os.path.exists(downloads_path):
        os.makedirs(downloads_path)
        logging.info(f"Created downloads directory at: {downloads_path}")
    
    logging.info("=" * 70)
    logging.info("TRADEMARK FILING AUTOMATION SCRIPT STARTING")
    logging.info("=" * 70)
    logging.info(f"Task: Login to {login_url} and export notifications to Excel")
    logging.info(f"Username: {username}")
    logging.info(f"Screenshots will be saved to: {screenshots_dir}")
    logging.info(f"Downloads will be saved to: {downloads_path}")
    logging.info("=" * 70)
    
    # Launch Playwright browser
    logging.info("Initializing browser...")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            chromium_sandbox=True,
            env={},
            args=[
                "--disable-extensions",
                "--disable-file-system"
            ]
        )
        
        # Create browser context with downloads enabled
        try:
            context = browser.new_context(
                accept_downloads=True,
                viewport={"width": 1024, "height": 768},
                downloads_path=downloads_path  # Try with downloads_path first
            )
        except TypeError:
            # If downloads_path is not supported, try without it
            logging.info("Your Playwright version doesn't support downloads_path parameter. Using default downloads location.")
            context = browser.new_context(
                accept_downloads=True,
                viewport={"width": 1024, "height": 768}
            )
        
        page = context.new_page()
        
        # Event listener for downloads
        download_count = 0
        
        def handle_download(download):
            nonlocal download_count
            download_count += 1
            logging.info(f"Download #{download_count} started: {download.suggested_filename}")
            download.save_as(os.path.join(downloads_path, download.suggested_filename))
            
        page.on("download", handle_download)
        
        logging.info("Browser launched successfully - you should see a browser window")
        
        # Navigate to the login page
        logging.info(f"Navigating to login page: {login_url}")
        page.goto(login_url)
        logging.info("Waiting for page to load completely...")
        time.sleep(2)  # Give time for the page to fully load
        
        # Take initial screenshot to extract CAPTCHA
        _, initial_screenshot_bytes = get_screenshot(page)
        
        # Use GPT-4o to extract the CAPTCHA text
        captcha_text = extract_captcha_with_gpt4o(initial_screenshot_bytes)
        
        if not captcha_text:
            # Try with a cropped version focusing on just the CAPTCHA area
            logging.info("Trying with cropped CAPTCHA region...")
            cropped_captcha_bytes = crop_captcha_region(initial_screenshot_bytes)
            captcha_text = extract_captcha_with_gpt4o(cropped_captcha_bytes)
        
        if captcha_text:
            # Clean up the captcha text (remove any spaces or non-alphanumeric characters)
            captcha_text = ''.join(c for c in captcha_text if c.isalnum())
            logging.info(f"CAPTCHA EXTRACTED: '{captcha_text}'")
        else:
            logging.warning("Could not extract CAPTCHA text. Will rely on model to guide CAPTCHA entry.")
        
        # Take initial screenshot for Computer Use API
        initial_screenshot_base64, _ = get_screenshot(page)
        
        # Start the computer use task
        task_description = (
            f"I need to automate this task on the trademark filing website. "
            f"Please follow these exact steps in order:\n"
            f"1. Enter username '{username}' in the username field\n"
            f"2. Enter password '{password}' in the password field\n"
        )
        
        # Add CAPTCHA instruction if we have the text
        if captcha_text:
            task_description += f"3. Enter '{captcha_text}' in the CAPTCHA field\n"
            task_description += f"4. Click the Login button\n"
            task_description += f"5. After logging in, find and click specifically on the 'View All Notifications' link\n"
            task_description += f"6. Then click on the 'View All' link in the upper right corner of the next page\n"
            task_description += f"7. Finally, scroll to the bottom of the notifications page and click the 'Export to Excel' button\n"
        else:
            task_description += f"3. Click on the CAPTCHA field so I can enter it manually\n"
            task_description += f"4. After I enter the CAPTCHA, click the Login button\n"
            task_description += f"5. After logging in, find and click specifically on the 'View All Notifications' link\n"
            task_description += f"6. Then click on the 'View All' link in the upper right corner of the next page\n"
            task_description += f"7. Finally, scroll to the bottom of the notifications page and click the 'Export to Excel' button\n"
        
        task_description += f"Please guide me through each step precisely. It's very important to follow this exact sequence."
        
        logging.info("Sending initial request to OpenAI Computer Use API...")
        
        # Make the initial request
        response_data = create_response(
            api_key=os.getenv("OPENAI_API_KEY"),
            screenshot_base64=initial_screenshot_base64,
            task_description=task_description
        )
        
        if not response_data:
            logging.error("Failed to get initial response from OpenAI. Exiting.")
            browser.close()
            return
        
        logging.info("Initial response received from OpenAI. Starting automation loop...")
        
        # Run the computer use loop
        final_response = computer_use_loop(page, response_data, captcha_text)
        
        # Display the final result
        logging.info("\n" + "=" * 70)
        logging.info("TASK COMPLETED")
        logging.info("=" * 70)
        
        # Check if any files were downloaded
        files_in_download_dir = os.listdir(downloads_path)
        if files_in_download_dir:
            excel_files = [f for f in files_in_download_dir if f.endswith('.xls') or f.endswith('.xlsx')]
            if excel_files:
                logging.info(f"Excel files downloaded: {excel_files}")
                logging.info(f"Download location: {downloads_path}")
            else:
                logging.info(f"Files in download directory, but no Excel files: {files_in_download_dir}")
        else:
            logging.info(f"No files were downloaded to {downloads_path}")
            
            # Check in default downloads directory if available
            home_dir = os.path.expanduser("~")
            default_downloads = os.path.join(home_dir, "Downloads")
            if os.path.exists(default_downloads):
                logging.info(f"Checking default downloads directory: {default_downloads}")
                try:
                    recent_files = sorted(
                        [os.path.join(default_downloads, f) for f in os.listdir(default_downloads)],
                        key=os.path.getctime,
                        reverse=True
                    )[:5]  # Get 5 most recent files
                    
                    if recent_files:
                        logging.info("Most recent files in default downloads directory:")
                        for f in recent_files:
                            file_time = time.ctime(os.path.getctime(f))
                            logging.info(f" - {os.path.basename(f)} (created: {file_time})")
                except Exception as e:
                    logging.error(f"Error checking default downloads: {e}")
        
        # Report on screenshots
        num_screenshots = len([f for f in os.listdir(screenshots_dir) if f.endswith('.png')])
        logging.info(f"Total screenshots saved: {num_screenshots}")
        logging.info(f"Screenshots location: {screenshots_dir}")
        
        # Keep the browser open for a moment
        logging.info("Keeping browser open for 10 seconds for you to see the final state...")
        time.sleep(10)
        logging.info("Closing browser...")
        browser.close()
        logging.info("Browser closed. Script execution complete.")

if __name__ == "__main__":
    try:
        # Check if OPENAI_API_KEY is set
        if not os.environ.get("OPENAI_API_KEY"):
            logging.error("ERROR: OPENAI_API_KEY environment variable is not set!")
            logging.error("Please set your OpenAI API key using:")
            logging.error("  export OPENAI_API_KEY='your-api-key'  # For Linux/Mac")
            logging.error("  set OPENAI_API_KEY=your-api-key  # For Windows")
            exit(1)
            
        # Check required packages
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logging.error("ERROR: Playwright is not installed!")
            logging.error("Please install it using:")
            logging.error("  pip install playwright")
            logging.error("  playwright install")
            exit(1)
            
        try:
            import requests
        except ImportError:
            logging.error("ERROR: Requests is not installed!")
            logging.error("Please install it using:")
            logging.error("  pip install requests")
            exit(1)
            
        try:
            from PIL import Image
        except ImportError:
            logging.error("ERROR: Pillow is not installed!")
            logging.error("Please install it using:")
            logging.error("  pip install Pillow")
            exit(1)
            
        try:
            from dotenv import load_dotenv
        except ImportError:
            logging.error("ERROR: python-dotenv is not installed!")
            logging.error("Please install it using:")
            logging.error("  pip install python-dotenv")
            exit(1)
            
        logging.info("Environment checks passed. Starting automation...")
        main()
    except Exception as e:
        logging.error(f"Unexpected error occurred: {e}")
        logging.error("Please ensure you have:")
        logging.error("1. Installed all required packages: pip install requests openai playwright python-dotenv Pillow")
        logging.error("2. Set your OpenAI API key in a .env file or as an environment variable")
        logging.error("3. Initialized Playwright: playwright install")
        logging.exception("Error details:")
