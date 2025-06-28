import os
import csv
import json
import re
import time
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_community.document_loaders import AsyncChromiumLoader, SeleniumURLLoader
from langchain_community.document_transformers import Html2TextTransformer
from dotenv import load_dotenv

# Hard‐code your Gemini API keys (no ADC)
API_KEYS = [
    "AIzaSyCkCdLByf38L5CcH88hf8WSTR_HJYvL738",
    "AIzaSyAhyUH4sCLskS5428llGsaCQoLVAQlWDhw"
]
current_api_index = 0

def get_llm():
    global current_api_index
    return ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        api_key=API_KEYS[current_api_index],
        temperature=0,
        disable_streaming=False
    )

def call_llm_with_retries(prompt_chain, input_data, max_retries=6):
    global current_api_index
    for attempt in range(max_retries):
        try:
            llm = get_llm()
            chain = prompt_chain | llm | StrOutputParser()
            return chain.invoke(input_data)
        except Exception as e:
            msg = str(e)
            print(f"⚠️ LLM attempt {attempt+1} error: {msg}")
            if "429" in msg or "ResourceExhausted" in msg:
                current_api_index = (current_api_index + 1) % len(API_KEYS)
                print(f"🔄 Switching to API Key #{current_api_index+1}...")
                time.sleep(3)
                continue
            break
    return "Error in response"

# Set user agent as environment variable
os.environ["PLAYWRIGHT_USER_AGENT"] = "MyProjectCrawler/1.0"

# 1) URLs to crawl
urls = [
    "https://m.economictimes.com/markets"
]

# 2) Load pages via Playwright or Selenium
try:
    loader = AsyncChromiumLoader(urls=urls)
    docs = loader.load()
except Exception as e:
    print(f"AsyncChromiumLoader failed: {e}, trying SeleniumURLLoader...")
    selenium_loader = SeleniumURLLoader(
        urls=urls,
        executable_path="/usr/local/bin/chromedriver",
        browser="chrome",
        headless=True,
        arguments=["--no-sandbox", "--disable-gpu"]
    )
    docs = selenium_loader.load()

# 3) HTML → plain text
transformer = Html2TextTransformer(ignore_links=False)
docs_txt = transformer.transform_documents(docs)

# 4) Prepare department-specific data extraction prompt
extract_data_system = SystemMessagePromptTemplate.from_template("""
You are a precise stock market data extraction specialist. Your task is to analyze the provided webpage content and extract stock market data in the following format:

Required fields:
1. Company Name
2. High
3. Low
4. Last Price
5. Prev Close
6. Change
7. % Gain

Important guidelines:
- Extract only numerical values for prices and percentages, removing any currency symbols or text
- Ensure percentage changes include the correct sign (+ for gainers, - for losers)
- If any data point is not available, use null
- Format the output as a JSON array of objects, where each object represents one stock
- Double-check all numerical values for accuracy
- Ignore any promotional or non-stock related content

Example output format:
[
    {{
        "company_name": "RELIANCE",
        "high": 2460.00,
        "low": 2390.00,
        "last_price": 2456.75,
        "prev_close": 2396.00,
        "change": 60.75,
        "percent_gain": 2.5
    }}
]
""")

human_message_template = HumanMessagePromptTemplate.from_template("Page Text: {page_text}")

extract_data_prompt = ChatPromptTemplate.from_messages([
    extract_data_system,
    human_message_template
])

# 5) Write CSV and extract data on the fly
output_path = "stocksData.csv"
with open(output_path, mode="w", newline="", encoding="utf-8-sig") as csvfile:
    writer = csv.writer(csvfile)
    # Write header
    writer.writerow(["department_url", "department_data"])
    
    for idx, doc in enumerate(docs_txt, start=1):
        raw = doc.page_content.replace("\n", " ").strip()
        url = doc.metadata.get("source", "")
        print(f"🔍 Processing department page {idx}: {url}")
        
        # Limit content length to avoid token limits
        content_to_process = raw[:50000] if len(raw) > 50000 else raw
        
        # Extract department-specific data
        extracted_data = call_llm_with_retries(extract_data_prompt, {"page_text": content_to_process})
        
        # Clean the extracted data
        cleaned_data = re.sub(r'\s+', ' ', extracted_data).strip()
        
        writer.writerow([
            url,
            cleaned_data
        ])
        csvfile.flush()  # ensure it's written immediately
        time.sleep(2)  # Add delay between API calls

print(f"✅ Saved department-specific data to {output_path}")





