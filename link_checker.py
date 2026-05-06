import requests
from scrapling.parser import Selector
import csv
import sys
import os
import ssl
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import threading
import re
import subprocess

# --- Configuration ---
# You can add or remove keywords here
TARGET_KEYWORDS = [
    "PRADAN's", "Professional Assistance for Development Action", "Pradan", "Saroj Mahapatra",
    "FSS", "Financial Software Solutions", "Promise Technology", "Geldautomaten", "ATM", "Casino",
    "ONDC", "PAYTM ONDC", "India Stack",
    "Zahlungsbranche", "Digital Payment", "Payment Industry",
    "Ethos"
]

class LegacySSLAdapter(HTTPAdapter):
    """
    A custom HTTPAdapter that forces the use of a legacy SSL context 
    to handle servers with outdated security protocols (TLS 1.0/1.1).
    """
    def init_poolmanager(self, connections, maxsize, block=False):
        context = ssl.create_default_context()
        # Allow legacy TLS versions (dangerous but necessary for some old gov/news sites)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        # Unsafe legacy renegotiation might be needed too
        context.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
        
        # Explicitly allow TLS 1.0 and 1.1 by clearing the NO flags if they exist
        if hasattr(ssl, 'OP_NO_TLSv1'):
            context.options &= ~ssl.OP_NO_TLSv1
        if hasattr(ssl, 'OP_NO_TLSv1_1'):
            context.options &= ~ssl.OP_NO_TLSv1_1
            
        self.poolmanager = PoolManager(num_pools=connections, maxsize=maxsize, block=block, ssl_context=context)

class DataFetcher:
    """
    Handles all network-related operations:
    - URL resolution (Google News redirects)
    - Fetching content via requests, cloudscraper, or cURL
    - SSL handling
    """
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.google.com/',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"macOS"'
        }

        # --- Performance: reuse a single session across all URLs ---
        # Creating a new Session per URL wastes TCP/TLS setup time.
        self.session = requests.Session()
        ssl_adapter = LegacySSLAdapter(pool_connections=100, pool_maxsize=100)
        http_adapter = requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100)
        self.session.mount('https://', ssl_adapter)
        self.session.mount('http://', http_adapter)
        self.session.headers.update(self.headers)

        # --- Performance: reuse a single cloudscraper instance ---
        try:
            import cloudscraper
            self.scraper = cloudscraper.create_scraper(
                browser={'browser': 'chrome', 'platform': 'darwin', 'desktop': True}
            )
        except ImportError:
            self.scraper = None

    def resolve_url(self, url):
        """
        Resolves Google News RSS redirect URLs to the actual article URL.
        """
        if 'news.google.com' not in url:
            return url
            
        # print(f"Resolving Google News URL: {url[:50]}...", end=" ")
        try:
            from googlenewsdecoder import new_decoderv1
            decoded = new_decoderv1(url)
            if decoded.get("status") and decoded.get("decoded_url"):
                # print(f"-> {decoded['decoded_url'][:50]}...")
                return decoded["decoded_url"]
        except Exception as e:
            # print(f"(Resolution failed: {e})", end=" ")
            pass
        
        return url

    def fetch_content(self, url):
        """
        Fetches the content of the URL using multiple strategies (Scrapling -> Requests -> Cloudscraper -> cURL).
        Returns response object or error string.
        """
        final_url = self.resolve_url(url)
        
        # 1. Scrapling HTTP Fetcher (Best against Cloudflare/bot protections)
        try:
            from scrapling import Fetcher
            import logging
            logging.getLogger("scrapling").setLevel(logging.ERROR) # suppress configure warning
            
            # Scrapling creates stealthy headers and impersonates Chrome natively
            page = Fetcher(stealthy_headers=True).get(final_url, timeout=10)
            
            # Treat empty/suspicious responses as fail so fallbacks can trigger
            if page.status == 200 and len(page.body) >= 800:
                class MockResponse:
                    def __init__(self, p):
                        self.content = p.body
                        self.status_code = p.status
                return MockResponse(page)
            elif page.status == 404:
                return f"Error: 404 Not Found"
        except Exception:
            pass  # Fallback to requests/cloudscraper

        try:
            # 2. Try shared session (legacy connection pooling)
            response = self.session.get(final_url, timeout=5, allow_redirects=True)
            
            # Check for suspicious small content (block/JS required)
            if response.status_code == 200 and len(response.content) < 800:
                pass # Trigger fallback
            elif response.status_code not in [403, 429, 503]:
                if response.status_code == 404:
                    return f"Error: 404 Not Found"
                response.raise_for_status()
                return response

            # 2. Try shared cloudscraper instance
            if self.scraper is None:
                return f"Error: {response.status_code} (Cloudscraper not installed)"
            try:
                cs_response = self.scraper.get(final_url)
                if cs_response.status_code == 200:
                    return cs_response
            except Exception as e:
                return f"Error: {response.status_code} (Cloudscraper failed: {str(e)})"
            
            if response.status_code == 404:
                return f"Error: 404 Not Found"
            
            response.raise_for_status()
            return response
            
        except requests.exceptions.Timeout:
            return f"Error: Timeout (20s)"
        except (requests.exceptions.ConnectionError, requests.exceptions.SSLError, requests.exceptions.RequestException) as e:
            # 3. Ultimate Fallback: System cURL
            try:
                result = subprocess.run(
                    ["curl", "-L", "-k", "-A", self.headers['User-Agent'], "--max-time", "20", final_url],
                    capture_output=True, text=True, encoding='utf-8', errors='replace'
                )
                
                if result.returncode == 0 and result.stdout:
                    class MockResponse:
                        def __init__(self, content_text):
                            self.content = content_text.encode('utf-8')
                            self.text = content_text
                            self.status_code = 200
                    return MockResponse(result.stdout)
                else:
                    return f"Error: cURL failed (Exit {result.returncode})"
            except Exception as curl_e:
                return f"Error: All methods failed. Last error: {str(e)} | cURL error: {str(curl_e)}"

class DataProcessor:
    """
    Handles data extraction and analysis:
    - Text extraction from HTML
    - Keyword matching
    - File reading (CSV/TXT)
    """
    def extract_text(self, html_content):
        """
        Extracts meaningful text from HTML, preferring article body over ads/sidebars.
        Tries semantic containers (article, main) before falling back to full-page.
        """
        if not html_content:
            return ""
        
        # Decode bytes if needed
        if isinstance(html_content, bytes):
            html_content = html_content.decode('utf-8', errors='replace')
            
        page = Selector(html_content)
        
        # 1. Try <article> tag first — most news sites wrap article body here
        #    This excludes sidebars, ads, recommended articles, etc.
        article = page.find('article')
        if article:
            art_text = article.get_all_text(separator=' ', strip=True, ignore_tags=('script', 'style'))
            if len(str(art_text)) > 300:  # Only use if it has meaningful content
                return ' '.join(str(art_text).split())
        
        # 2. Try <main> or role="main" — accessibility-compliant sites use this
        main = page.find('main') or page.css('[role="main"]').first
        if main:
            main_text = main.get_all_text(separator=' ', strip=True, ignore_tags=('script', 'style'))
            if len(str(main_text)) > 300:
                return ' '.join(str(main_text).split())
        
        # 3. Full-page fallback: exclude noisy structural elements
        text = page.get_all_text(
            separator=' ',
            strip=True,
            ignore_tags=('script', 'style', 'nav', 'header', 'footer', 'aside')
        )
        return ' '.join(str(text).split())

    def analyze_relevance(self, text, main_keywords, context_keywords=None, exclude_keywords=None):
        """
        Checks if keywords exist in the text using word-boundary matching.
        Prevents partial matches like 'SEX' matching 'SENSEX'.
        Returns: Status, Match Count, List of Found Keywords
        """
        text_lower = text if text.islower() else text.lower()

        # 1. Check exclusions first (word-boundary)
        if exclude_keywords and len(exclude_keywords) > 0:
            for keyword in exclude_keywords:
                kw_low = keyword.lower()
                if kw_low in text_lower:  # fast pre-check before regex
                    if re.search(r'\b' + re.escape(kw_low) + r'\b', text_lower):
                        return "Irrelevant (Excluded)", 0, [keyword]

        # 2. Check main keywords (word-boundary)
        found_main = []
        for keyword in main_keywords:
            kw_low = keyword.lower()
            if re.search(r'\b' + re.escape(kw_low) + r'\b', text_lower):
                found_main.append(keyword)
                
        if not found_main:
            return "Irrelevant", 0, []

        # 3. Check context keywords (word-boundary)
        found_context = []
        if context_keywords and len(context_keywords) > 0:
            for keyword in context_keywords:
                kw_low = keyword.lower()
                if re.search(r'\b' + re.escape(kw_low) + r'\b', text_lower):
                    found_context.append(keyword)
            
            if not found_context:
                return "Irrelevant (Context Missing)", len(found_main), found_main

        all_found = found_main + found_context
        return "Relevant", len(found_main), all_found

    def load_links(self, input_dir):
        """
        Scans input_dir for valid files (.csv or .txt) and extracts links.
        """
        # ... (implementation omitted for brevity in replace call, assuming context is correct)
        if not os.path.exists(input_dir):
            print(f"Error: Directory '{input_dir}' not found.")
            return []

        files = [f for f in os.listdir(input_dir) if not f.startswith('.')]
        if not files:
            print(f"Error: No files found in '{input_dir}'.")
            return []

        file_to_read = "test_urls_all.txt" if "test_urls_all.txt" in files else files[0]
        file_path = os.path.join(input_dir, file_to_read)
        print(f"Reading input from: {file_to_read}")
        
        links = []
        try:
            if file_path.endswith('.csv'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    headers = next(reader, None)
                    if headers:
                        url_index = -1
                        for i, h in enumerate(headers):
                            if 'url' in h.lower():
                                url_index = i
                                break
                        
                        if url_index != -1:
                            for row in reader:
                                if len(row) > url_index and row[url_index].strip():
                                    links.append(row[url_index].strip())
                                elif len(row) == 1 and row[0].startswith('http'):
                                    links.append(row[0].strip())
                        else:
                            f.seek(0)
                            for line in f:
                                if line.startswith('http'):
                                    links.append(line.strip())
            else:
                with open(file_path, 'r', encoding='utf-8') as f:
                    links = [line.strip() for line in f if line.strip()]
                    
            return links
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            return []

def expand_keywords(keywords):
    """
    Intelligently expands keywords with common synonyms to improve recall.
    Moved from app.py to keep code clean.
    """
    expanded = list(keywords)
    # Common Crypto Synonyms Map
    synonyms = {
        'binance': ['BSC', 'Smart Chain'], # Removed 'BNB' per user request
        'bnb': ['Binance', 'BSC'],
        'bitcoin': ['BTC', 'Satoshi'],
        'btc': ['Bitcoin'],
        'ethereum': ['ETH', 'Vitalik'],
        'eth': ['Ethereum'],
        'ripple': ['XRP'],
        'xrp': ['Ripple'],
        'solana': ['SOL'],
        'sol': ['Solana'],
        'cardano': ['ADA'],
        'ada': ['Cardano'],
        'dogecoin': ['DOGE'],
        'doge': ['Dogecoin'],
        'polkadot': ['DOT'],
        'dot': ['Polkadot'],
        'polygon': ['MATIC'],
        'matic': ['Polygon'],
        'chainlink': ['LINK'],
        'link': ['Chainlink'],
        'litecoin': ['LTC'],
        'ltc': ['Litecoin']
    }
    
    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower in synonyms:
            for syn in synonyms[kw_lower]:
                if syn not in expanded:
                    expanded.append(syn)
                    
    return list(set(expanded))

def process_single_url_task(url, target_keywords, fetcher, processor):
    """
    Task function for processing a single URL using Fetcher and Processor.
    """
    response_or_error = fetcher.fetch_content(url)
    
    status = "Unknown"
    count = 0
    found = []
    
    if not isinstance(response_or_error, str):
        response = response_or_error
        text = processor.extract_text(response.content)
        status, count, found = processor.analyze_relevance(text, target_keywords)
        
        # Fallback for blocked content mechanism
        if status not in ["Relevant", "Irrelevant (Excluded)", "Relevant (HTML Match)"] and count == 0:
            block_indicators = [
                "enable javascript", "javascript is disabled", "requires javascript",
                "attention required! | cloudflare", "sorry, you have been blocked", 
                "cloudflare ray id", "security service to protect itself",
                "subscribe to read", "paywall",
                "verify you are human", "captcha", "bot behavior", "access denied", 
                "unusual traffic", "please wait while we verify", "checking your browser",
                "not a robot", "robot check", "turn on javascript", "pardon our interruption"
            ]
            text_lower = text.lower()
            html_lower = response.content.decode('utf-8', errors='ignore').lower()
            is_blocked = any(indicator in text_lower or indicator in html_lower for indicator in block_indicators)
            if len(text_lower) < 150:
                is_blocked = True
                
            url_text = url.lower()
            found_in_url = []
            for kw in target_keywords:
                if kw.lower() in url_text:
                    found_in_url.append(kw)
            
            if found_in_url:
                count = len(found_in_url)
                found = found_in_url
                status = "Relevant (URL Match)"
                if is_blocked:
                    status += " - Blocked by the site so insure it from yourself"
            elif is_blocked:
                status = "Access Denied / Blocked by the site so insure it from yourself"
    else:
        status_msg = "Missing"
        if any(code in response_or_error for code in ["403", "429", "503", "406", "Timeout", "captcha"]):
            status_msg = "Blocked by the site so insure it from yourself"
        elif "404" in response_or_error:
            status_msg = "Page Not Found (404)"
            
        status = status_msg

    return {
        "URL": url,
        "Status": status,
        "Match Count": count,
        "Found Keywords": ", ".join(found) if found else "No keyword matched"
    }

def main():
    print(f"Starting Link Relevance Checker...")
    print(f"Target Keywords: {TARGET_KEYWORDS}\n")
    
    input_dir = "input_data"
    output_dir = "output_data"
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Initialize Classes
    fetcher = DataFetcher()
    processor = DataProcessor()
    
    links = processor.load_links(input_dir)
    if not links:
        print("No valid links found to process.")
        return

    print(f"Found {len(links)} links to check.\n")
    
    csv_filename = f"{output_dir}/link_report.csv"
    fieldnames = ['URL', 'Status', 'Match Count', 'Found Keywords']
    
    try:
        with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            print(f"Processing links with ThreadPoolExecutor (max_workers=100)...")
            
            with ThreadPoolExecutor(max_workers=100) as executor:
                # Pass fetcher and processor instances to the task
                future_to_url = {
                    executor.submit(process_single_url_task, url, TARGET_KEYWORDS, fetcher, processor): url 
                    for url in links
                }
                
                for future in tqdm(as_completed(future_to_url), total=len(links), unit="link"):
                    url = future_to_url[future]
                    try:
                        result = future.result()
                        writer.writerow(result)
                        csvfile.flush()
                    except Exception as exc:
                        tqdm.write(f"Generated an exception for {url}: {exc}")
                        error_row = {
                            "URL": url,
                            "Status": f"Script Error: {exc}",
                            "Match Count": 0,
                            "Found Keywords": ""
                        }
                        writer.writerow(error_row)
                        csvfile.flush()

        print(f"\nProcessing complete. Report saved to {csv_filename}")

    except IOError as e:
        print(f"\nError using file {csv_filename}: {e}")

if __name__ == "__main__":
    main()
