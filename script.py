import os
import time
import pandas as pd
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from supabase import create_client
import xml.etree.ElementTree as ET
import re
import logging
from urllib.parse import urlparse, urljoin
from dotenv import load_dotenv
import google.generativeai as genai
import yfinance as yf
from alpha_vantage.fundamentaldata import FundamentalData
import requests
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("company_scraper.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()

# Load environment variables
load_dotenv()

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Google Search API configuration
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CX = os.getenv("GOOGLE_CX")  # Custom Search Engine ID

# Gemini LLM configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")

def get_financial_data(company_name, website):
    """Get financial information from multiple sources with fallback"""
    financial_data = {
        "revenue": "",
        "market_cap": "",
        "source": "",
        "last_updated": datetime.now().strftime("%Y-%m-%d")
    }
    
    # Try to find company ticker symbol
    ticker = get_company_ticker(company_name)
    
    if ticker:
        # Try Yahoo Finance first (no API key needed)
        try:
            yahoo_data = get_yahoo_finance_data(ticker)
            if yahoo_data:
                financial_data.update(yahoo_data)
                financial_data["source"] = "Yahoo Finance"
                return financial_data
        except Exception as e:
            logger.warning(f"Yahoo Finance lookup failed for {company_name}: {str(e)}")
            
        # Try Alpha Vantage as fallback
        if ALPHA_VANTAGE_API_KEY:
            try:
                alpha_data = get_alpha_vantage_data(ticker)
                if alpha_data:
                    financial_data.update(alpha_data)
                    financial_data["source"] = "Alpha Vantage"
                    return financial_data
            except Exception as e:
                logger.warning(f"Alpha Vantage lookup failed for {company_name}: {str(e)}")
    
    return financial_data

def get_company_ticker(company_name):
    """Try to find company ticker symbol"""
    try:
        # Try direct lookup
        ticker_search = yf.Ticker(company_name)
        if hasattr(ticker_search, 'info') and ticker_search.info and 'symbol' in ticker_search.info:
            return ticker_search.info['symbol']
        
        # Try search API to find potential matches
        search_url = f"https://query2.finance.yahoo.com/v1/finance/search?q={company_name}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(search_url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            if 'quotes' in data and data['quotes']:
                # Return the first match that seems reasonable
                for quote in data['quotes']:
                    if quote.get('isYahooFinance') and 'symbol' in quote:
                        return quote['symbol']
        
        return None
    except Exception as e:
        logger.warning(f"Error in ticker lookup for {company_name}: {str(e)}")
        return None

def get_yahoo_finance_data(ticker):
    """Get financial data from Yahoo Finance"""
    financial_data = {}
    
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # Get market cap
        if 'marketCap' in info and info['marketCap']:
            financial_data['market_cap'] = f"${format_number(info['marketCap'])}"
        
        # Get revenue
        if 'totalRevenue' in info and info['totalRevenue']:
            financial_data['revenue'] = f"${format_number(info['totalRevenue'])}/yr"
        
        # Get additional useful financial metrics if available
        if 'operatingCashflow' in info and info['operatingCashflow']:
            financial_data['operating_cashflow'] = f"${format_number(info['operatingCashflow'])}/yr"
            
        if 'grossProfits' in info and info['grossProfits']:
            financial_data['gross_profit'] = f"${format_number(info['grossProfits'])}/yr"
            
        return financial_data
    except Exception as e:
        logger.warning(f"Error getting Yahoo Finance data for {ticker}: {str(e)}")
        return {}

def get_alpha_vantage_data(ticker):
    """Get financial data from Alpha Vantage"""
    financial_data = {}
    
    try:
        fd = FundamentalData(key=ALPHA_VANTAGE_API_KEY)
        
        # Get income statement
        income_statement = fd.get_income_statement_annual(symbol=ticker)[0]
        if 'annualReports' in income_statement and income_statement['annualReports']:
            latest_report = income_statement['annualReports'][0]
            if 'totalRevenue' in latest_report:
                financial_data['revenue'] = f"${format_number(int(latest_report['totalRevenue']))}/yr"
            if 'grossProfit' in latest_report:
                financial_data['gross_profit'] = f"${format_number(int(latest_report['grossProfit']))}/yr"
        
        # Get company overview
        overview = fd.get_company_overview(symbol=ticker)[0]
        if 'MarketCapitalization' in overview:
            financial_data['market_cap'] = f"${format_number(int(overview['MarketCapitalization']))}"
        
        return financial_data
    except Exception as e:
        logger.warning(f"Error getting Alpha Vantage data for {ticker}: {str(e)}")
        return {}

def format_number(num):
    """Format large numbers to be more readable"""
    if num >= 1_000_000_000:
        return f"{num/1_000_000_000:.2f}B"
    elif num >= 1_000_000:
        return f"{num/1_000_000:.2f}M"
    elif num >= 1_000:
        return f"{num/1_000:.2f}K"
    else:
        return str(num)

# Configure the Gemini model
model = genai.GenerativeModel('gemini-2.0-flash')

# Constants
COMPANY_LIST_FILE = "companies.txt"
OUTPUT_EXCEL = "company_data_final.xlsx"
TABLE_NAME = "new_table"
DEFAULT_URLS = ['about', 'contact', 'team', 'investor', 'investors', 'partners', 'product', 
               'products', 'service', 'services', 'customer', 'customers', 'career', 'careers']

def setup_selenium():
    """Configure and return a Selenium WebDriver"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver

def get_company_website(company_name):
    """Use Google Search API to find the company's website"""
    try:
        search_url = f"https://www.googleapis.com/customsearch/v1?key={GOOGLE_API_KEY}&cx={GOOGLE_CX}&q={company_name} official website"
        response = requests.get(search_url)
        
        if response.status_code != 200:
            logger.error(f"Google API error: {response.status_code} - {response.text}")
            if "quota" in response.text.lower():
                raise Exception("Google Search API quota exceeded")
            return None
            
        search_results = response.json()
        
        # Extract the first result that seems like a company website
        if "items" in search_results:
            for item in search_results["items"]:
                url = item.get("link", "")
                # Skip social media and common directory sites
                if not any(domain in url for domain in ["facebook.com", "linkedin.com", "twitter.com", "instagram.com", "youtube.com", "yelp.com", "yellowpages.com"]):
                    return url
        
        logger.warning(f"No suitable website found for {company_name}")
        return None
    
    except Exception as e:
        logger.error(f"Error in get_company_website for {company_name}: {str(e)}")
        if "quota" in str(e).lower():
            raise
        return None

def get_sitemap_urls(base_url, driver):
    """Try to find and parse sitemap.xml to get URLs"""
    sitemap_urls = []
    
    # Common sitemap locations to check
    sitemap_locations = [
        "sitemap.xml",
        "sitemap_index.xml",
        "sitemap-index.xml",
        "sitemaps/sitemap.xml",
        "sitemap/sitemap.xml"
    ]
    
    for location in sitemap_locations:
        sitemap_url = urljoin(base_url, location)
        try:
            response = requests.get(sitemap_url, timeout=10)
            if response.status_code == 200:
                # Try to parse the XML
                try:
                    root = ET.fromstring(response.content)
                    # Handle both sitemap and sitemapindex formats
                    # For sitemap format
                    for url in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc"):
                        sitemap_urls.append(url.text)
                    
                    # For sitemapindex format, we need to fetch each sitemap
                    for sitemap in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap"):
                        loc = sitemap.find("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
                        if loc is not None and loc.text:
                            try:
                                sub_response = requests.get(loc.text, timeout=10)
                                if sub_response.status_code == 200:
                                    sub_root = ET.fromstring(sub_response.content)
                                    for url in sub_root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc"):
                                        sitemap_urls.append(url.text)
                            except Exception as e:
                                logger.warning(f"Error fetching sub-sitemap {loc.text}: {str(e)}")
                    
                    if sitemap_urls:
                        logger.info(f"Found {len(sitemap_urls)} URLs in sitemap at {sitemap_url}")
                        return sitemap_urls
                        
                except ET.ParseError:
                    logger.warning(f"Could not parse XML from {sitemap_url}")
                    continue
                    
        except requests.RequestException as e:
            logger.warning(f"Error accessing sitemap at {sitemap_url}: {str(e)}")
            continue
    
    logger.warning(f"No sitemap found for {base_url}")
    return []

def analyze_urls_with_gemini(urls, company_name, base_url):
    """Use Gemini to analyze which URLs are most relevant to scrape"""
    try:
        # Prepare prompt for Gemini
        prompt = f"""
        I'm researching the company '{company_name}' with website {base_url}.
        I need to gather the following information:
        1. Website
        2. Company Description
        3. Software Classification
        4. Enterprise Grade Classification
        5. Industry
        6. Customers names list
        7. Employee Headcount
        8. Investors
        9. Geography
        10. Parent company
        11. Address (Street, City, ZIP/Postal Code, Country)
        12. Financial Information
        13. Email
        14. Phone
        
        Here is a list of URLs from their sitemap:
        {urls[:200] if len(urls) > 200 else urls}
        
        Based on the URL patterns, which 10-15 URLs would be most useful to scrape to find this information?
        Return your answer as a JSON list of URLs only.
        """
        
        # Send request to Gemini
        response = model.generate_content(prompt)
        result = response.text
        
        # Extract URLs from response
        try:
            # Try to parse if it's formatted as a list or JSON
            if '[' in result and ']' in result:
                url_list_str = result[result.find('['):result.rfind(']')+1]
                url_list = eval(url_list_str)  # Safe for list literals
                
                if isinstance(url_list, list) and all(isinstance(url, str) for url in url_list):
                    logger.info(f"Gemini suggested {len(url_list)} URLs to scrape")
                    return url_list
            
            # Fallback: extract anything that looks like a URL
            urls_found = re.findall(r'https?://[^\s"\']+', result)
            if urls_found:
                logger.info(f"Extracted {len(urls_found)} URLs from Gemini response")
                return urls_found
                
            logger.warning("Could not extract structured URLs from Gemini response")
            
        except Exception as e:
            logger.warning(f"Error parsing Gemini response: {str(e)}")
        
        # If we can't parse the response properly, fall back to default URL selection
        return urls[:15] if len(urls) > 15 else urls
        
    except Exception as e:
        logger.error(f"Error using Gemini to analyze URLs: {str(e)}")
        if "quota" in str(e).lower():
            raise Exception("Gemini API quota exceeded")
        # Fall back to default selection
        return urls[:15] if len(urls) > 15 else urls

def generate_default_urls(base_url):
    """Generate default URLs to scrape if no sitemap is available"""
    urls = []
    parsed_url = urlparse(base_url)
    base = f"{parsed_url.scheme}://{parsed_url.netloc}"
    
    for path in DEFAULT_URLS:
        urls.append(f"{base}/{path}")
        urls.append(f"{base}/{path}.html")
        urls.append(f"{base}/en/{path}")
        urls.append(f"{base}/us/{path}")
    
    return urls

def scrape_page(url, driver):
    """Scrape a single page and return its content"""
    try:
        driver.get(url)
        time.sleep(2)  # Allow time for JavaScript to load
        return driver.page_source
    except Exception as e:
        logger.warning(f"Error scraping {url}: {str(e)}")
        return ""

def extract_company_info_with_gemini(company_name, website, scraped_content):
    """Use Gemini LLM to extract company information from scraped content"""
    try:
        # Clean up the content a bit to make it more manageable
        clean_content = []
        for content in scraped_content:
            # Extract meaningful text from HTML
            soup = BeautifulSoup(content, 'html.parser')
            
            # Remove scripts, styles, and other non-content elements
            for element in soup(['script', 'style', 'meta', 'noscript', 'header', 'footer', 'nav']):
                element.decompose()
                
            # Get text
            text = soup.get_text(separator=' ', strip=True)
            
            # Basic cleaning
            text = re.sub(r'\s+', ' ', text)
            text = text[:100000] if len(text) > 100000 else text  # Limit text size
            
            if text.strip():
                clean_content.append(text)
        
        # Combine and truncate content to fit in prompt
        combined_content = " ".join(clean_content)
        truncated_content = combined_content[:150000] if len(combined_content) > 150000 else combined_content
        
        # Create prompt for Gemini
        prompt = f"""
        I need to extract specific information about the company '{company_name}' with website {website}.
        
        Based on the following scraped content from their website, please extract as much of this information as possible:
        
        1. Company Description: A brief description of what the company does.
        2. Industry: What industry does the company operate in?
        3. Software Classification: What type of software does the company provide?
        4. Enterprise Grade Classification: Is their software enterprise-grade? What level?
        5. Geography: Where is the company based/headquartered?
        6. Street Address: The street address of their main office.
        7. City: City of their main office.
        8. Postal Code: ZIP/Postal code of their main office.
        9. Country: Country of their main office.
        10. Phone: Contact phone number.
        11. Email: Contact email address.
        12. Employee Count: How many employees work at the company?
        13. Customers: List of major customers or clients.
        14. Investors: List of investors or funding sources.
        15. Parent Company: Is this company owned by a parent company? If so, which one?
        16. Financial Info: Any financial information like revenue, funding, etc.
        
        Here's the content from their website:
        {truncated_content}
        
        Format your response as a JSON object with these 16 fields, with empty string values for any information you cannot find.
        """
        
        # Send request to Gemini
        response = model.generate_content(prompt)
        result = response.text
        
        # Extract JSON from response
        json_match = re.search(r'```json\n(.*?)\n```', result, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = result
        
        try:
            import json
            company_data = json.loads(json_str)
            
            # Ensure all required fields are present
            required_fields = {
                "Company Description": "Description",
                "Industry": "Industry",
                "Software Classification": "Software Classification",
                "Enterprise Grade Classification": "Enterprise Grade Classification",
                "Geography": "Geography", 
                "Street Address": "Street Address",
                "City": "City",
                "Postal Code": "Postal Code",
                "Country": "Country",
                "Phone": "Phone",
                "Email": "Email",
                "Employee Count": "Employee Count",
                "Customers": "Customers",
                "Investors": "Investors",
                "Parent Company": "Parent Company",
                "Financial Info": "Financial Info"
            }
            
            # Create properly formatted data for Supabase
            supabase_data = {
                "Company Name": company_name,
                "Website": website
            }
            
            for gemini_key, supabase_key in required_fields.items():
                if gemini_key in company_data:
                    supabase_data[supabase_key] = company_data[gemini_key]
                else:
                    supabase_data[supabase_key] = ""
            
            # Get enhanced financial data from third-party sources
            logger.info(f"Getting financial data from third-party sources for {company_name}")
            financial_data = get_financial_data(company_name, website)
            
            # Construct a detailed financial info string
            financial_info_parts = []
            
            if financial_data.get("revenue"):
                financial_info_parts.append(f"Revenue: {financial_data['revenue']}")
            
            if financial_data.get("market_cap"):
                financial_info_parts.append(f"Market Cap: {financial_data['market_cap']}")
                
            if financial_data.get("gross_profit"):
                financial_info_parts.append(f"Gross Profit: {financial_data['gross_profit']}")
                
            if financial_data.get("operating_cashflow"):
                financial_info_parts.append(f"Operating Cash Flow: {financial_data['operating_cashflow']}")
            
            if financial_data.get("source"):
                financial_info_parts.append(f"Source: {financial_data['source']} ({financial_data['last_updated']})")
            
            # If we got financial data from APIs, use it
            if financial_info_parts:
                supabase_data["Financial Info"] = " | ".join(financial_info_parts)
            # Otherwise, if Gemini found something reasonable, keep it
            elif supabase_data.get("Financial Info") and any(term in supabase_data["Financial Info"].lower() for term in 
                                                      ['revenue', 'million', 'billion', '$', 'usd', 'funding', 'raised']):
                # Keep the existing Gemini financial info
                pass
            # If nothing was found
            else:
                supabase_data["Financial Info"] = "No financial information available"
                
            return supabase_data
            
        except Exception as e:
            logger.error(f"Error parsing Gemini JSON response: {str(e)}")
            logger.debug(f"Raw response: {result}")
            
            # Fallback to simplified extraction
            basic_data = extract_fallback_info(company_name, website, truncated_content)
            
            # Add financial data to the basic extraction
            financial_data = get_financial_data(company_name, website)
            
            # Construct a detailed financial info string
            financial_info_parts = []
            
            if financial_data.get("revenue"):
                financial_info_parts.append(f"Revenue: {financial_data['revenue']}")
            
            if financial_data.get("market_cap"):
                financial_info_parts.append(f"Market Cap: {financial_data['market_cap']}")
                
            if financial_data.get("gross_profit"):
                financial_info_parts.append(f"Gross Profit: {financial_data['gross_profit']}")
                
            if financial_data.get("operating_cashflow"):
                financial_info_parts.append(f"Operating Cash Flow: {financial_data['operating_cashflow']}")
            
            if financial_data.get("source"):
                financial_info_parts.append(f"Source: {financial_data['source']} ({financial_data['last_updated']})")
            
            if financial_info_parts:
                basic_data["Financial Info"] = " | ".join(financial_info_parts)
                
            return basic_data
            
    except Exception as e:
        logger.error(f"Error using Gemini to extract company info: {str(e)}")
        if "quota" in str(e).lower():
            raise Exception("Gemini API quota exceeded")
            
        # Create basic company data
        basic_data = {
            "Company Name": company_name,
            "Website": website,
            "Description": "",
            "Industry": "",
            "Software Classification": "",
            "Enterprise Grade Classification": "",
            "Geography": "",
            "Street Address": "",
            "City": "",
            "Postal Code": "",
            "Country": "",
            "Phone": "",
            "Email": "",
            "Employee Count": "",
            "Customers": "",
            "Investors": "",
            "Parent Company": "",
            "Financial Info": ""
        }
        
        # Add financial data from third-party sources
        financial_data = get_financial_data(company_name, website)
        
        # Construct a detailed financial info string
        financial_info_parts = []
        
        if financial_data.get("revenue"):
            financial_info_parts.append(f"Revenue: {financial_data['revenue']}")
        
        if financial_data.get("market_cap"):
            financial_info_parts.append(f"Market Cap: {financial_data['market_cap']}")
            
        if financial_data.get("gross_profit"):
            financial_info_parts.append(f"Gross Profit: {financial_data['gross_profit']}")
            
        if financial_data.get("operating_cashflow"):
            financial_info_parts.append(f"Operating Cash Flow: {financial_data['operating_cashflow']}")
        
        if financial_data.get("source"):
            financial_info_parts.append(f"Source: {financial_data['source']} ({financial_data['last_updated']})")
        
        if financial_info_parts:
            basic_data["Financial Info"] = " | ".join(financial_info_parts)
            
        # Try the fallback extraction for other fields
        try:
            fallback_data = extract_fallback_info(company_name, website, " ".join(scraped_content))
            
            # Merge non-empty fields from fallback data
            for key, value in fallback_data.items():
                if key != "Financial Info" and value and not basic_data.get(key):
                    basic_data[key] = value
        except:
            pass
            
        return basic_data

def extract_fallback_info(company_name, website, content):
    """Fallback method to extract company info using regex patterns if Gemini fails"""
    company_data = {
        "Company Name": company_name,
        "Website": website,
        "Description": "",
        "Industry": "",
        "Software Classification": "",
        "Enterprise Grade Classification": "",
        "Geography": "",
        "Street Address": "",
        "City": "",
        "Postal Code": "",
        "Country": "",
        "Phone": "",
        "Email": "",
        "Employee Count": "",
        "Customers": "",
        "Investors": "",
        "Parent Company": "",
        "Financial Info": ""
    }
    
    # Extract information using regex patterns (simplified version)
    
    # Description - look for meta description or about text
    description_match = re.search(r'<meta\s+name=["\']description["\'][^>]*content=["\']([^"\']+)["\']', content, re.IGNORECASE)
    if description_match:
        company_data["Description"] = description_match.group(1).strip()
    
    # Industry
    industry_match = re.search(r'industry[:\s]+([^.<]{3,50})', content, re.IGNORECASE)
    if industry_match:
        company_data["Industry"] = industry_match.group(1).strip()
    
    # Email - find email addresses
    email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
    emails = re.findall(email_pattern, content)
    if emails:
        # Filter out common non-contact emails
        contact_emails = [email for email in emails if not any(x in email.lower() for x in ['noreply', 'donotreply', 'no-reply'])]
        if contact_emails:
            company_data["Email"] = contact_emails[0].strip()
    
    # Phone numbers
    phone_match = re.search(r'(?:phone|tel)[:\s]+([\d\s\(\)\+\-\.]{7,20})', content, re.IGNORECASE)
    if phone_match:
        company_data["Phone"] = phone_match.group(1).strip()
    
    # Address - look for address patterns
    address_match = re.search(r'address[:\s]+([^.<]{5,150})', content, re.IGNORECASE)
    if address_match:
        full_address = address_match.group(1).strip()
        
        # Try to parse components
        street_match = re.search(r'^([^,]+)', full_address)
        if street_match:
            company_data["Street Address"] = street_match.group(1).strip()
        
        city_match = re.search(r',\s*([^,]+),', full_address)
        if city_match:
            company_data["City"] = city_match.group(1).strip()
        
        country_match = re.search(r',\s*([A-Za-z\s]+)$', full_address)
        if country_match:
            company_data["Country"] = country_match.group(1).strip()
    
    return company_data

def check_company_exists(company_name):
    """Check if company already exists in Supabase"""
    try:
        response = supabase.table(TABLE_NAME).select("*").eq("Company Name", company_name).execute()
        return len(response.data) > 0, response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"Error checking if company exists: {str(e)}")
        return False, None

def save_to_supabase(company_data):
    """Save company data to Supabase table"""
    try:
        response = supabase.table(TABLE_NAME).insert(company_data).execute()
        logger.info(f"Saved {company_data['Company Name']} to Supabase")
        return True
    except Exception as e:
        logger.error(f"Error saving to Supabase: {str(e)}")
        return False

def main():
    """Main function to process companies and scrape data"""
    try:
        # Check if company list file exists
        if not os.path.exists(COMPANY_LIST_FILE):
            logger.error(f"Company list file {COMPANY_LIST_FILE} not found")
            return
            
        # Read company names from file
        with open(COMPANY_LIST_FILE, 'r') as file:
            company_names = [line.strip() for line in file if line.strip()]
            
        logger.info(f"Processing {len(company_names)} companies")
        
        # Set up Selenium
        driver = setup_selenium()
        
        # Results list
        results = []
        
        # Process each company
        for company_name in company_names:
            logger.info(f"Processing company: {company_name}")
            
            # Check if company already exists in database
            exists, existing_data = check_company_exists(company_name)
            if exists:
                logger.info(f"Company {company_name} already exists in database, skipping")
                
                # Check if we should update financial data for existing companies
                if existing_data and (not existing_data.get("Financial Info") or 
                                      "No financial information available" in existing_data.get("Financial Info", "")):
                    logger.info(f"Updating financial information for {company_name}")
                    website = existing_data.get("Website", "")
                    if website:
                        # Get enhanced financial data
                        financial_data = get_financial_data(company_name, website)
                        
                        if any(financial_data.get(key) for key in ["revenue", "market_cap", "gross_profit", "operating_cashflow"]):
                            # Construct a detailed financial info string
                            financial_info_parts = []
                            
                            if financial_data.get("revenue"):
                                financial_info_parts.append(f"Revenue: {financial_data['revenue']}")
                            
                            if financial_data.get("market_cap"):
                                financial_info_parts.append(f"Market Cap: {financial_data['market_cap']}")
                                
                            if financial_data.get("gross_profit"):
                                financial_info_parts.append(f"Gross Profit: {financial_data['gross_profit']}")
                                
                            if financial_data.get("operating_cashflow"):
                                financial_info_parts.append(f"Operating Cash Flow: {financial_data['operating_cashflow']}")
                            
                            if financial_data.get("source"):
                                financial_info_parts.append(f"Source: {financial_data['source']} ({financial_data['last_updated']})")
                            
                            # Update financial info in the database
                            if financial_info_parts:
                                updated_financial_info = " | ".join(financial_info_parts)
                                try:
                                    # Update just the financial info field
                                    supabase.table(TABLE_NAME).update({"Financial Info": updated_financial_info}).eq("Company Name", company_name).execute()
                                    logger.info(f"Updated financial information for {company_name}")
                                    
                                    # Update the existing data for results
                                    existing_data["Financial Info"] = updated_financial_info
                                except Exception as e:
                                    logger.error(f"Error updating financial info for {company_name}: {str(e)}")
                
                results.append(existing_data)
                continue
                
            # Find company website
            website = get_company_website(company_name)
            if not website:
                logger.warning(f"Could not find website for {company_name}, skipping")
                continue
                
            logger.info(f"Found website for {company_name}: {website}")
            
            # Get URLs to scrape - try sitemap first, fall back to default URLs
            sitemap_urls = get_sitemap_urls(website, driver)
            
            if sitemap_urls:
                # Use Gemini to analyze which URLs from sitemap to scrape
                logger.info(f"Using Gemini to analyze {len(sitemap_urls)} sitemap URLs")
                urls_to_scrape = analyze_urls_with_gemini(sitemap_urls, company_name, website)
            else:
                urls_to_scrape = generate_default_urls(website)
                
            logger.info(f"Will scrape {len(urls_to_scrape)} URLs for {company_name}")
            
            # Scrape pages
            pages_content = []
            for url in urls_to_scrape:
                try:
                    content = scrape_page(url, driver)
                    if content:
                        pages_content.append(content)
                except Exception as e:
                    logger.warning(f"Error scraping {url}: {str(e)}")
                    continue
                    
            # Extract information using Gemini
            if pages_content:
                logger.info(f"Using Gemini to extract information from {len(pages_content)} scraped pages")
                company_data = extract_company_info_with_gemini(company_name, website, pages_content)
                
                # Get financial data from third-party sources if not already retrieved by Gemini function
                if not company_data.get("Financial Info") or company_data.get("Financial Info") == "No financial information available":
                    logger.info(f"Getting financial data from third-party sources for {company_name}")
                    financial_data = get_financial_data(company_name, website)
                    
                    # Construct a detailed financial info string
                    financial_info_parts = []
                    
                    if financial_data.get("revenue"):
                        financial_info_parts.append(f"Revenue: {financial_data['revenue']}")
                    
                    if financial_data.get("market_cap"):
                        financial_info_parts.append(f"Market Cap: {financial_data['market_cap']}")
                        
                    if financial_data.get("gross_profit"):
                        financial_info_parts.append(f"Gross Profit: {financial_data['gross_profit']}")
                        
                    if financial_data.get("operating_cashflow"):
                        financial_info_parts.append(f"Operating Cash Flow: {financial_data['operating_cashflow']}")
                    
                    if financial_data.get("source"):
                        financial_info_parts.append(f"Source: {financial_data['source']} ({financial_data['last_updated']})")
                    
                    if financial_info_parts:
                        company_data["Financial Info"] = " | ".join(financial_info_parts)
                
                # Save to Supabase
                if save_to_supabase(company_data):
                    results.append(company_data)
                    logger.info(f"Successfully processed {company_name}")
            else:
                logger.warning(f"No content scraped for {company_name}")
                
        # Close Selenium
        driver.quit()
        
        # Export results to Excel
        if results:
            df = pd.DataFrame(results)
            df.to_excel(OUTPUT_EXCEL, index=False)
            logger.info(f"Exported data to {OUTPUT_EXCEL}")
        else:
            logger.warning("No data to export")
            
        logger.info("Process completed successfully")
        
    except Exception as e:
        logger.error(f"Process failed: {str(e)}")
        if "quota" in str(e).lower():
            logger.critical("API quota exceeded, stopping process")
if __name__ == "__main__":
    main()