import base64
import time
import os
import logging
import requests
import uuid
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from datetime import datetime

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
    return screenshot_base64

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

def computer_use_loop(page, response_data):
    """Run the loop that executes computer actions until no 'computer_call' is found."""
    step_counter = 1
    captcha_detected = False
    manual_intervention_needed = False
    captcha_attempts = 0
    
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
                    if any(phrase in message_text.lower() for phrase in ["manual", "human", "enter", "input"]):
                        manual_intervention_needed = True
        
        # Check if model provided any computer actions
        computer_calls = [item for item in output_items if item.get("type") == "computer_call"]
        if not computer_calls:
            # Check if we're at the CAPTCHA stage and need to handle it
            current_page_content = page.content().lower()
            if captcha_detected or "captcha" in current_page_content:
                captcha_attempts += 1
                if captcha_attempts <= 3:  # Limit retries
                    logging.info("\n" + "!" * 50)
                    logging.info("CAPTCHA DETECTED - MODEL STOPPED PROVIDING ACTIONS")
                    logging.info("Taking a better screenshot and trying to continue...")
                    logging.info("!" * 50 + "\n")
                    
                    # Take a new screenshot focused on the CAPTCHA
                    screenshot_base64 = get_screenshot(page)
                    
                    # Try to continue by instructing the model more explicitly
                    new_task = (
                        "I need your help to complete this form. Please do the following:\n"
                        "1. The username and password are already entered.\n"
                        "2. The CAPTCHA is shown in the image. Please read the CAPTCHA text and enter it in the field.\n"
                        "3. After entering the CAPTCHA, click the Login button.\n"
                        "4. Once logged in, look for and click 'View All Notifications'.\n"
                        "5. Then find and click the 'Export to Excel' button."
                    )
                    
                    logging.info(f"Sending new instructions: {new_task}")
                    
                    # Create a new response with fresh instructions
                    response_data = create_response(
                        api_key=os.getenv("OPENAI_API_KEY"),
                        screenshot_base64=screenshot_base64,
                        task_description=new_task
                    )
                    
                    if not response_data:
                        logging.error("Failed to get response after CAPTCHA handling attempt. Exiting loop.")
                        return None
                    
                    step_counter += 1
                    continue
                else:
                    logging.info("Maximum CAPTCHA handling attempts reached. Manual intervention required.")
                    logging.info("\n" + "*" * 50)
                    logging.info("CAPTCHA NEEDS TO BE ENTERED MANUALLY")
                    logging.info("Please enter the captcha shown in the browser window")
                    logging.info("*" * 50 + "\n")
                    
                    # Wait for user to enter CAPTCHA
                    input("Press Enter after manually entering the CAPTCHA and clicking Login...")
                    
                    # Capture new screenshot after login
                    screenshot_base64 = get_screenshot(page)
                    
                    # Try to continue with the next steps
                    new_task = (
                        "We're now logged in. Please continue with:\n"
                        "1. Finding and clicking 'View All Notifications'\n"
                        "2. Finding and clicking 'Export to Excel'"
                    )
                    
                    response_data = create_response(
                        api_key=os.getenv("OPENAI_API_KEY"),
                        screenshot_base64=screenshot_base64,
                        task_description=new_task
                    )
                    
                    if not response_data:
                        logging.error("Failed to get response after manual CAPTCHA entry. Exiting loop.")
                        return None
                    
                    step_counter += 1
                    continue
            
            # Not at CAPTCHA stage or couldn't handle it, exit loop
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
        
        # Execute the action
        handle_model_action(page, action)
        logging.info("Waiting for page to settle after action...")
        time.sleep(1)  # Allow time for changes to take effect.
        
        # Check if we're at a download stage
        action_text = str(action).lower()
        if "export" in action_text or "excel" in action_text:
            logging.info("Export action detected. Setting up download handler...")
            
            # Set up download handler
            download_path = os.path.join(os.getcwd(), "downloads")
            if not os.path.exists(download_path):
                os.makedirs(download_path)
            
            # Give extra time for download to start
            logging.info("Waiting for download to start...")
            time.sleep(5)
            
            # Check if files were downloaded
            files_before = set(os.listdir(download_path))
            
            # Wait a bit longer for download to complete
            time.sleep(5)
            
            # Check again for new files
            files_after = set(os.listdir(download_path))
            new_files = files_after - files_before
            
            if new_files:
                logging.info(f"New files downloaded: {new_files}")
            else:
                logging.info("No new files detected. Download may have failed or gone to default location.")

        # Get current URL if possible
        try:
            current_url = page.url
            logging.info(f"Current URL: {current_url}")
        except:
            current_url = None
            logging.info("Could not determine current URL")

        # Take a screenshot after the action
        screenshot_base64 = get_screenshot(page)
        
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
        
        # Take initial screenshot
        initial_screenshot = get_screenshot(page)
        
        # Start the computer use task
        task_description = (
            f"I need to automate a task on this trademark filing website. "
            f"Please help me with this workflow: "
            f"1. Enter username '{username}' and password '{password}' in the login form. "
            f"2. Look at the CAPTCHA image and enter the text you see in the CAPTCHA field. "
            f"3. Click the Login button. "
            f"4. Once logged in, find and click on 'View All Notifications'. "
            f"5. Then find and click the 'Export to Excel' button. "
            f"Note: Please try to interpret the CAPTCHA - it's crucial for this task."
        )
        
        logging.info("Sending initial request to OpenAI Computer Use API...")
        
        # Make the initial request
        response_data = create_response(
            api_key=os.getenv("OPENAI_API_KEY"),
            screenshot_base64=initial_screenshot,
            task_description=task_description
        )
        
        if not response_data:
            logging.error("Failed to get initial response from OpenAI. Exiting.")
            browser.close()
            return
        
        logging.info("Initial response received from OpenAI. Starting automation loop...")
        
        # Run the computer use loop
        final_response = computer_use_loop(page, response_data)
        
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
        logging.error("1. Installed all required packages: pip install requests openai playwright python-dotenv")
        logging.error("2. Set your OpenAI API key in a .env file or as an environment variable")
        logging.error("3. Initialized Playwright: playwright install")
        logging.exception("Error details:")