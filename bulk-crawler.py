import time
import random
import json
import csv
import logging
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from undetected_playwright import stealth_sync
from datetime import datetime, timedelta
import pytz
import os

# Configure logging
logging.basicConfig(filename="scraper.log", level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def get_output_filename():
    """Generate output filename based on current date and time"""
    ist = pytz.timezone('Asia/Kolkata')
    current_time = datetime.now(ist)
    
    # Create data directory if it doesn't exist
    os.makedirs('data', exist_ok=True)
    
    # Format: DDMonthHHMM.csv (e.g., 17June945.csv)
    month_names = {
        1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
        7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'
    }
    
    filename = f"data/{current_time.day}{month_names[current_time.month]}{current_time.hour}{current_time.minute:02d}.csv"
    return filename

# Read URLs from CSV file
def read_urls_from_csv(input_file):
    rows = []
    with open(input_file, "r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            if "url" in row and row["url"].strip():
                # Store the original row
                rows.append(row)
    return rows

# Save extracted data to CSV in real-time
def append_to_csv(data, output_csv):
    """Appends data to a CSV file, ensuring content stays in a single cell."""
    try:
        with open(output_csv, mode="a", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(
                file, 
                fieldnames=data.keys(),
                quoting=csv.QUOTE_ALL,  # Quote all fields
                escapechar='\\',
                doublequote=True  # Use double quotes for escaping
            )
            if file.tell() == 0:  # Write header if file is empty
                writer.writeheader()
                file.flush()
            
            # Clean the data to ensure it's properly formatted
            cleaned_data = {}
            for key, value in data.items():
                if isinstance(value, str):
                    # Replace any problematic characters
                    cleaned_value = value.replace('\n', ' ').replace('\r', ' ')
                    # Remove any extra whitespace
                    cleaned_value = ' '.join(cleaned_value.split())
                    cleaned_data[key] = cleaned_value
                else:
                    cleaned_data[key] = value
            
            writer.writerow(cleaned_data)
            file.flush()
    except Exception as e:
        print(f"Error writing to CSV: {str(e)}")
        logging.error(f"CSV writing error: {str(e)}")

# Filter HTML content
def filter_project_content(raw_html):
    """Original content filtering function"""
    soup = BeautifulSoup(raw_html, "html.parser")
    for element in soup(["script", "style", "meta", "link", "noscript"]):
        element.decompose()
    
    # Remove elements with specific classes
    for selector in [
        "header", "footer", ".ads", ".cookie-banner", ".popup", ".heading", 
        ".tab-content business-tab-pane", ".md\\:pt-24", ".pt-12", 
        ".lg\\:col-span-3", "main.footer"
    ]:
        for element in soup.select(selector):
            element.decompose()
    
    # Remove elements with specific class combinations
    for element in soup.find_all(class_=lambda x: x and any(cls in x for cls in ["md:pt-24", "pt-12", "lg:col-span-3", "links" , "btmFooter clearfix"])):
        element.decompose()
    
    # Remove main elements with footer class
    for element in soup.find_all("main", class_="footer"):
        element.decompose()
    
    text_content = soup.get_text(separator="\n", strip=True)
    
    # Truncate content at "Interesting Reads"
    truncate_index = text_content.find("Interesting Reads")
    if truncate_index != -1:
        text_content = text_content[:truncate_index].strip()
    
    return text_content

# Extract project data
def extract_project_data(page, raw_html, row):
    """Modified to use passed HTML content"""
    row["raw_content"] = filter_project_content(raw_html)
    return row

def windows_scraper(row, page, output_csv):
    """Robust scraper with ensured deep scrolling and fail-safe retry mechanism"""
    url = row["url"]
    try:
        # Navigate to the page with better error handling
        print(f"Navigating to {url}")
        
        # Use domcontentloaded and handle timeout gracefully
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"Initial page load timeout, continuing anyway: {str(e)}")
        
        # Mandatory wait for popups/timers (e.g., 'site will be open in X seconds')
        print("Waiting 15 seconds for any popups/timers to clear...")
        time.sleep(15)
        
        # Check for blocking overlays
        if page.query_selector('text="Access Denied"'):
            raise Exception("Security block detected")

        # Enhanced Scrolling Mechanism
        print("Starting page scroll...")
        max_attempts = 30  # Increased for smoother scrolling
        current_position = 0
        last_height = page.evaluate("document.body.scrollHeight")
        unchanged_attempts = 0
        scroll_step = 300  # Smaller scroll steps for smoother movement

        # Force initial scroll to trigger lazy loading
        page.evaluate("window.scrollTo(0, 100);")
        time.sleep(1)

        for attempt in range(max_attempts):
            try:
                # Calculate next scroll position
                current_position += scroll_step
                
                # Smooth scroll to position
                page.evaluate(f"""
                    window.scrollTo({{
                        top: {current_position},
                        left: 0,
                        behavior: 'smooth'
                    }});
                """)
                
                # Wait for scroll to complete
                time.sleep(0.5)
                
                # Get new height after scroll
                new_height = page.evaluate("document.body.scrollHeight")
                
                # Check if we've reached the bottom
                if current_position >= new_height:
                    unchanged_attempts += 1
                    if unchanged_attempts >= 3:
                        print("Reached end of page")
                        break
                else:
                    unchanged_attempts = 0
                    last_height = new_height
                
                # Try to trigger any lazy-loaded content
                page.evaluate("""
                    document.querySelectorAll('img[loading="lazy"]').forEach(img => {
                        if (img.dataset.src) img.src = img.dataset.src;
                    });
                """)
                
                # Random pause between scrolls
                time.sleep(random.uniform(0.3, 0.7))
                
            except Exception as e:
                print(f"Scroll attempt {attempt + 1} failed: {str(e)}")
                continue

        # Final scroll to bottom to ensure we got everything
        page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)

        # Get the final HTML content
        final_html = page.content()
        project_data = extract_project_data(page, final_html, row)
        logging.info(f"✅ Successfully scraped: {url}")
        append_to_csv(project_data, output_csv)
        return project_data

    except Exception as e:
        error_msg = f"❌ Scraping failed for {url}: {str(e)}"
        logging.error(error_msg)
        row["raw_content"] = error_msg
        append_to_csv(row, output_csv)
        return row

def is_market_hours():
    """Check if current time is within market hours (9:45 AM to 3:30 PM IST)"""
    ist = pytz.timezone('Asia/Kolkata')
    current_time = datetime.now(ist)
    
    # Check if it's a weekday (0-4 are Monday to Friday)
    if current_time.weekday() > 4:
        return False
    
    # Define market hours
    market_start = current_time.replace(hour=9, minute=45, second=0, microsecond=0)
    market_end = current_time.replace(hour=15, minute=30, second=0, microsecond=0)
    
    return market_start <= current_time <= market_end

def get_next_run_time():
    """Calculate the next run time (30 minutes from now)"""
    ist = pytz.timezone('Asia/Kolkata')
    current_time = datetime.now(ist)
    next_run = current_time + timedelta(minutes=30)
    
    # If next run is after market hours, set it to next day's market start
    if next_run.hour > 15 or (next_run.hour == 15 and next_run.minute > 30):
        next_run = next_run.replace(hour=9, minute=45, second=0, microsecond=0)
        next_run += timedelta(days=1)
    
    return next_run

if __name__ == "__main__":
    input_csv = "Stocks.csv"

    # Define user agents
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ]

    while True:
        # Generate new output filename for this run
        output_csv = get_output_filename()
        print(f"Starting crawler run at {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')}")
        
        if not is_market_hours():
            print("⚠️ Warning: Running outside market hours (9:45 AM to 3:30 PM IST). Data may not reflect current market conditions.")
        
        print(f"Output will be saved to: {output_csv}")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-http2",
                    "--ignore-certificate-errors",
                    "--disable-dev-shm-usage",
                    "--disable-accelerated-2d-canvas",
                    "--disable-gpu",
                    "--disable-infobars",
                    "--disable-popup-blocking",
                    "--disable-notifications",
                    f"--user-agent={random.choice(USER_AGENTS)}"
                ],
                timeout=120000
            )

            context = browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1920, "height": 1080}
            )

            page = context.new_page()
            stealth_sync(page)

            rows = read_urls_from_csv(input_csv)
            for row in rows:
                url = row["url"]
                if url == "No URLs found" or url.startswith("Error:"):
                    continue
                    
                print(f"🚀 Scraping: {url}")
                row_copy = row.copy()
                row_copy["url"] = url
                
                try:
                    scraped_data = windows_scraper(row_copy, page, output_csv)
                    print(f"✅ Successfully scraped: {url}")
                except Exception as e:
                    print(f"❌ Failed to scrape: {url} - Error: {str(e)}")

            print(f"🎯 Scraping complete. Data saved to {output_csv}")
            context.close()
            browser.close()

        # Calculate next run time
        next_run = get_next_run_time()
        wait_seconds = (next_run - datetime.now(pytz.timezone('Asia/Kolkata'))).total_seconds()
        
        if wait_seconds > 0:
            print(f"Next run scheduled at: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
            time.sleep(wait_seconds)
