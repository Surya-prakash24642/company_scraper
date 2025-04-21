# CompanyScraper README

## Overview

CompanyScraper is a Python application that seeks to automate the extraction of company data from web pages and financial data sources. It employs a mix of web scraping, artificial intelligence-based extraction (through Google's Gemini API), and financial data APIs to retrieve extensive company profiles and save them in a Supabase database.

## Features

- Finds company websites automatically using Google Search API
- Explors website sitemaps to locate relevant pages
- Extracts company information from webpage content using AI (Gemini)
- Retrieves reliable financial data from Yahoo Finance and Alpha Vantage
- Saves data in a formatted Supabase database
- Exports results to Excel spreadsheet
- Manages errors robustly with extensive logging

## Requirements

- Python 3.7+
- Python packages required (see `requirements.txt`)
- API keys:
- Google Search API and Custom Search Engine ID
- Google Gemini API
- Alpha Vantage API (for financial data)
- Supabase credentials

## Installation

1. Clone the repository:
```bash
git clone https://github.com/Surya-prakash24642/company_scraper.git
cd company-scraper
```

2. Install the packages that are needed:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file with your API keys and credentials:
```bash
GOOGLE_API_KEY=your_google_api_key
GOOGLE_CX=your_custom_search_engine_id
GEMINI_API_KEY=your_gemini_api_key
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_api_key
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
```

## Usage

1. Write a text file called `companies.txt` with one company name per line:
```
Microsoft
Apple
Tesla
```

2. Execute the script:
```
python company_scraper.py
```

3. The script will:
- Process each company in the list
- Find their official website
- Scrape relevant pages
- Extract company information
- Fetch financial data
- Save results to Supabase
- Export results to `company_data.xlsx`

## Key Functions

### Main Functions

#### `main()`
The entry point of the script. It reads the company list, processes each company, and manages the overall workflow.

#### `setup_selenium()`
Configures and returns a headless Selenium WebDriver to browse websites.

### Website Discovery

#### `get_company_website(company_name)`
Uses Google Search API to determine the official company website.

### URL Collection

#### `get_sitemap_urls(base_url, driver)`
Tries to discover and parse sitemap.xml file to get URLs to scrape.

#### `analyze_urls_with_gemini(urls, company_name, base_url)`
Uses Gemini AI to determine the most relevant URLs to use for scraping company data.

#### `generate_default_urls(base_url)`
Generates a list of typical URLs to scrape when there's no sitemap.

### Data Extraction

#### `scrape_page(url, driver)`
Extracts the contents of one webpage.

#### `extract_company_info_with_gemini(company_name, website, scraped_content)`
Extracts structured company information from scraped content using Gemini AI and adds it with financial information retrieved from APIs.

#### `extract_fallback_info(company_name, website, content)`
Fallback function that extracts company information using regex patterns if AI extraction is unsuccessful.

### Financial Data Retrieval

#### `get_financial_data(company_name, website)`
Retrieves verified financial data from several sources with fallbacks.

#### `get_company_ticker(company_name)`
Tries to retrieve the stock ticker symbol of a company.

#### `get_yahoo_finance_data(ticker)`
Retrieves financial data from Yahoo Finance API (market cap, revenue, etc.).

#### `get_alpha_vantage_data(ticker)`
Retrieves financial data from Alpha Vantage API as a fallback.

#### `format_number(num)`
Formats large numbers to be more readable (e.g., $1.5B instead of $1,500,000,000).

### Database Operations

#### `check_company_exists(company_name)`
Checks if a company already exists in the Supabase database.

#### `save_to_supabase(company_data)`
Saves company data to the Supabase table.

## Data Structure

The script gathers the following data for each firm:

1. Company Name
2. Website
3. Company Description
4. Software Classification
5. Enterprise Grade Classification
6. Industry
7. Customers
8. Employee Headcount
9. Investors
10. Geography
11. Parent Company
12. Address (Street, City, ZIP/Postal Code, Country)
13. Financial Information (Revenue, Market Cap, etc.)
14. Email
15. Phone

## Error Handling

The script incorporates extensive error handling and logging:
- All errors are written to `company_scraper.log`
- The script continues processing other firms in case one fails
- API quota violations are caught and dealt with elegantly

## Challenges

- Google Search API and Custom Search Engine are subject to usage limits
- Alpha Vantage free tier restricts API calls (5/min, 500/day)
- Financial information may not be shown for private companies
- Sites can block automated scraping

## Scaling the Script

- To include additional data fields, refactor the `extract_company_info_with_gemini` function
- To include additional financial data sources, introduce new functions like `get_yahoo_finance_data`
- To accommodate more website structures, improve the `get_sitemap_urls` and `generate_default_urls` functions

## Troubleshooting

1. **API Quota Exceeded**: If you encounter "API quota exceeded" errors, wait for your quota to expire or use an alternative API key.

2. **No Website Found**: When the script cannot find a website for a company, simply insert the site's URL straight into your `companies.txt` file in the style `CompanyName|website.com`.

3. **No Financial Data**: Some private companies have no financial information or if you have exceeded the quota on your Alpha Vantage API key.

4. **Selenium Issues**: If there are Selenium problems, ensure the appropriate ChromeDriver is installed.

## Third-Party websites used for collecting financial data

1. **Alpha Vantage**

2. **Yahoo Finance**
