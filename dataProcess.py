import os
import csv
import json
import time
import re
from glob import glob
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain_core.output_parsers import StrOutputParser

API_KEYS = [""]
current_api_index = 0  # Track which API key is in use

def get_llm():
    """Returns an instance of the Gemini AI model using the current API key."""
    global current_api_index
    return ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        api_key=API_KEYS[current_api_index],
        streaming=True
    )

# Initialize LLM
llm = get_llm()

# Define system prompts
system_prompt = SystemMessagePromptTemplate.from_template("""
You are a stock market analyst. Your task is to create a detailed summary of the stock information in a clear, readable format with table with all the fields in the data except Stock Score and Potential Upside


Create a comprehensive summary that includes:
1. Company Overview
2. Current Market Performance
3. Trading Statistics
5. Recommended Stocks to buy
4. Key Metrics and Returns

Format the output as a well-structured text summary, NOT as JSON.
Use clear headings and bullet points where appropriate.
Include all relevant information in a human-readable format.



Example format:
Company Overview:
- Name: [Company Name]
- Sector: [Industry Sector]

Current Market Performance:
- Current Price: [Price]
- Daily Change: [Change] ([Percentage])
- Day Range: [Low] - [High]

[Continue with other sections...]
""")

metadata_prompt = SystemMessagePromptTemplate.from_template("""
You are a data extraction specialist. Extract the following stock information and format it EXACTLY as a JSON object.
DO NOT include any explanatory text or markdown formatting.

Required JSON Structure:
{{
    "company": {{
        "name": "string",
        "symbol": "string",
        "sector": "string"
    }},
    "price": {{
        "current": number,
        "previous_close": number,
        "day_high": number,
        "day_low": number,
        "change": number,
        "percent_change": number
    }},
    "trading": {{
        "volume": number,
        "total_asset_turnover": number,
        "market_cap": number,
        "year_high": number,
        "year_low": number
    }},
    "returns": {{
        "one_week": number,
        "one_month": number,
        "three_months": number,
        "six_months": number,
        "one_year": number,
        "three_years": number,
        "ytd": number
    }},
    "timestamp": {{
        "date": "string",
        "time": "string"
    }}
}}

Rules:
1. Return ONLY the JSON object, no other text
2. All numerical values must be numbers (not strings)
3. Use null for unavailable values
4. Maintain consistent decimal places (2 for prices, 2 for percentages)
5. Return recommended Stocks to buy
5. Dates must be in "YYYY-MM-DD" format
6. Times must be in "HH:MM:SS" format
7. Do it for all the company stocks and not just one
""")

# Create chat prompts
chat_prompt = ChatPromptTemplate.from_messages([
    system_prompt,
    HumanMessagePromptTemplate.from_template("Stock details: {raw_content}")
])

metadata_chat_prompt = ChatPromptTemplate.from_messages([
    metadata_prompt,
    HumanMessagePromptTemplate.from_template("Stock details: {raw_content}")
])

def call_llm_with_retries(prompt_chain, input_data):
    """Retries the API call up to 6 times, switching API keys if quota is exhausted."""
    global current_api_index

    retries = 6
    for attempt in range(retries):
        try:
            return prompt_chain.invoke(input_data)
        except Exception as e:
            error_message = str(e)
            print(f"⚠️ Attempt {attempt + 1}: API Error - {error_message}")

            if "429" in error_message or "ResourceExhausted" in error_message:
                current_api_index = (current_api_index + 1) % len(API_KEYS)
                print(f"🔄 Switching to API Key {current_api_index + 1}...")
                time.sleep(3)
                continue
            break

    print("❌ Failed after retries.")
    return "Error in response"

def generate_stock_summary(raw_content: str) -> str:
    """Generate a summary of stock information."""
    try:
        chain = chat_prompt | get_llm() | StrOutputParser()
        summary = call_llm_with_retries(chain, {"raw_content": raw_content})
        
        if summary == "Error in response":
            print("❌ Failed to get summary from LLM")
            return "No summary available"
            
        # Clean up the summary text
        summary = summary.strip()
        # Remove any markdown formatting
        summary = re.sub(r'```.*?```', '', summary, flags=re.DOTALL)
        return summary
    except Exception as e:
        print(f"❌ Error generating summary: {str(e)}")
        return "Error generating summary"

def generate_metadata(raw_content: str) -> str:
    """Generate structured metadata from stock information."""
    try:
        chain = metadata_chat_prompt | get_llm() | StrOutputParser()
        metadata = call_llm_with_retries(chain, {"raw_content": raw_content})
        return metadata if metadata != "Error in response" else "{}"
    except Exception as e:
        print(f"❌ Error in metadata generation: {str(e)}")
        return "{}"

def process_csv(input_csv: str, output_csv: str):
    """Process the input CSV file and generate summaries and metadata."""
    try:
        with open(input_csv, "r", encoding="utf-8") as file, \
             open(output_csv, "w", newline="", encoding="utf-8") as outfile:
            
            reader = csv.DictReader(file)
            fieldnames = reader.fieldnames + ["stock_summary", "metadata"]
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()

            for row in reader:
                raw_content = row.get("raw_content", "").strip()
                if raw_content:
                    print(f"\nProcessing: {row.get('url', 'Unknown URL')}")
                    print(f"Raw content length: {len(raw_content)} characters")
                    
                    stock_summary = generate_stock_summary(raw_content)
                    metadata = generate_metadata(raw_content)
                    
                    row["stock_summary"] = stock_summary
                    row["metadata"] = metadata
                    print(f"Generated metadata: {metadata[:200]}...")  # Print first 200 chars
                else:
                    print("⚠️ No raw content found for this row")
                    row["stock_summary"] = "No data available"
                    row["metadata"] = "{}"

                writer.writerow(row)

        print(f"✅ Processing complete. Data saved to {output_csv}")
    except Exception as e:
        print(f"❌ Error processing CSV: {str(e)}")

def get_latest_csv_file(data_dir="data"):
    """Return the path to the latest CSV file in the data directory."""
    csv_files = glob(os.path.join(data_dir, "*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {data_dir}")
    latest_file = max(csv_files, key=os.path.getmtime)
    return latest_file

if __name__ == "__main__":
    try:
        input_file = get_latest_csv_file("data")
        processed_dir = os.path.join("data", "processed")
        os.makedirs(processed_dir, exist_ok=True)
        output_file = os.path.splitext(os.path.basename(input_file))[0] + "Processed.csv"
        output_file = os.path.join(processed_dir, output_file)
        print(f"Processing latest file: {input_file}")
        process_csv(input_file, output_file)
    except Exception as e:
        print(f"❌ Error: {str(e)}")