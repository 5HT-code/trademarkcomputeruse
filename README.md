# Trademark Filing Automation

This Python script automates the process of logging into the Indian Trademark Filing website, handling CAPTCHA verification, and downloading notification data to Excel.

## Features

- Automated login to the trademark filing portal
- CAPTCHA solving using GPT-4 Vision API
- Automated navigation through notification pages
- Excel file download automation
- Screenshot capture for debugging
- Comprehensive logging

## Prerequisites

- Python 3.7+
- OpenAI API key
- Playwright browser automation
- Required Python packages:
  - playwright
  - requests
  - Pillow (PIL)
  - python-dotenv

## Installation

1. Clone the repository:
```bash
git clone https://github.com/5HT-code/trademarkcomputeruse.git
cd trademarkcomputeruse
```

2. Install required packages:
```bash
pip install playwright requests Pillow python-dotenv
playwright install
```

3. Create a `.env` file in the project root and add your OpenAI API key:
```
OPENAI_API_KEY=your_api_key_here
```

## How It Works

### 1. Login Process
- Opens the trademark filing portal (https://ipindiaonline.gov.in/trademarkefiling/user/frmloginNew.aspx)
- Enters username and password
- Captures CAPTCHA image
- Uses GPT-4 Vision API to solve CAPTCHA
- Submits login form

### 2. Navigation
- After successful login, navigates to the notifications page
- Clicks "View All Notifications"
- Navigates to detailed notifications view
- Scrolls to find export options

### 3. Export Process
- Locates and clicks "Export to Excel" button
- Handles file download
- Saves Excel file to downloads directory

### 4. Error Handling & Logging
- Comprehensive error handling for each step
- Detailed logging of all actions
- Screenshot capture for debugging
- Automatic retry mechanisms for failed operations

## Directory Structure

```
trademarkcomputeruse/
├── trademark_automation.py    # Main automation script
├── .env                      # Environment variables (not tracked in git)
├── screenshots/              # Directory for debug screenshots
├── downloads/                # Directory for downloaded Excel files
└── .gitignore               # Git ignore rules
```

## Usage

1. Ensure your `.env` file is properly configured with your OpenAI API key
2. Run the script:
```bash
python trademark_automation.py
```

The script will:
1. Launch a browser window
2. Navigate to the trademark portal
3. Handle login and CAPTCHA
4. Download the Excel file
5. Save it to the downloads directory

## Logging

The script maintains detailed logs of all operations, including:
- Login attempts
- CAPTCHA solving
- Navigation steps
- Download status
- Any errors or exceptions

Logs are printed to the console and can be used for debugging.

## Security Notes

- Never commit your `.env` file containing API keys
- The script uses secure methods for handling credentials
- Screenshots are saved locally for debugging purposes only

## Error Handling

The script includes robust error handling for:
- Failed login attempts
- CAPTCHA solving failures
- Navigation issues
- Download problems
- Network connectivity issues

## Contributing

Feel free to submit issues and enhancement requests! 