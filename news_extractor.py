import feedparser
import urllib.parse
import requests
from datetime import datetime, timedelta
from dateutil import parser
from bs4 import BeautifulSoup
import concurrent.futures
import re

# Configuration mapping for different countries
COUNTRY_CONFIGS = {
    "IN": {"gl": "IN", "hl": "en-IN", "ceid": "IN:en"},
    "US": {"gl": "US", "hl": "en-US", "ceid": "US:en"},
    "GB": {"gl": "GB", "hl": "en-GB", "ceid": "GB:en"},
    "AE": {"gl": "AE", "hl": "en-AE", "ceid": "AE:en"},
    "SG": {"gl": "SG", "hl": "en-SG", "ceid": "SG:en"},
    "AU": {"gl": "AU", "hl": "en-AU", "ceid": "AU:en"},
    "CA": {"gl": "CA", "hl": "en-CA", "ceid": "CA:en"},
    "ZA": {"gl": "ZA", "hl": "en-ZA", "ceid": "ZA:en"}
}

def fetch_article_content(url, headers, timeout=8):
    """Fetch and extract text content from an article URL."""
    try:
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove script and style elements
        for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            tag.decompose()
        
        # Get text content
        text = soup.get_text(separator=' ', strip=True)
        return text.lower()
    except Exception as e:
        return ""

def check_keyword_in_content(article, keyword, headers):
    """Check if keyword exists in article content (title, RSS summary, or body)."""
    keyword_lower = keyword.lower()
    
    # First check: Title (fast)
    if keyword_lower in article['Title'].lower():
        article['MatchLocation'] = 'Title'
        return article
    
    # Second check: RSS Summary/Description (from Google News)
    summary = article.get('Summary', '')
    if keyword_lower in summary.lower():
        article['MatchLocation'] = 'Summary'
        return article
    
    # Third check: Fetch and check body content
    content = fetch_article_content(article['Link'], headers)
    if keyword_lower in content:
        article['MatchLocation'] = 'Body'
        return article
    
    return None

def fetch_google_web_news(topic, country="IN", start_date=None, end_date=None):
    """
    Scrapes Google News web search results using cloudscraper to bypass bot detection.
    This catches articles that the RSS feed misses (smaller sites, blogs, etc.)
    Returns a list of article dicts compatible with the RSS results format.
    """
    try:
        import cloudscraper
    except ImportError:
        print("  ! cloudscraper not installed, skipping web search supplement.")
        return []

    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'darwin', 'desktop': True}
    )

    articles = []
    seen_urls = set()

    # Use Google's internal tbs=cdr format for date filtering (what the browser uses)
    # This returns significantly more results than the after:/before: text operators
    tbs_param = ""
    if start_date and end_date:
        s = datetime.strptime(start_date, "%Y-%m-%d")
        e = datetime.strptime(end_date, "%Y-%m-%d")
        tbs_param = f"&tbs={urllib.parse.quote(f'cdr:1,cd_min:{s.month}/{s.day}/{s.year},cd_max:{e.month}/{e.day}/{e.year}')}"

    encoded = urllib.parse.quote(topic)

    # Get country specific parameters, default to IN
    config = COUNTRY_CONFIGS.get(country, COUNTRY_CONFIGS["IN"])
    gl, hl = config["gl"], config["hl"]

    # Fetch multiple pages to maximize coverage
    pages_to_fetch = [
        f"https://www.google.com/search?q={encoded}&tbm=nws&num=100&gl={gl}&hl={hl}{tbs_param}",
        f"https://www.google.com/search?q={encoded}&tbm=nws&num=100&gl={gl}&hl={hl}{tbs_param}&start=100",
    ]

    s_date = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
    e_date = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None

    for page_url in pages_to_fetch:
        try:
            print(f"  Scraping: {page_url[:80]}...")
            resp = scraper.get(page_url, timeout=15)
            if resp.status_code != 200:
                print(f"  ! Web search returned status {resp.status_code}")
                continue

            soup = BeautifulSoup(resp.text, 'html.parser')

            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                text = a_tag.get_text(strip=True)

                # Google wraps real results in /url? redirects
                actual_url = None
                if href.startswith('/url?'):
                    # Extract the actual URL from the redirect
                    params = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                    url_list = params.get('url') or params.get('q')
                    if url_list:
                        actual_url = url_list[0]
                
                if not actual_url or not text or len(text) < 10:
                    continue
                if 'accounts.google' in actual_url or 'support.google' in actual_url:
                    continue
                if actual_url in seen_urls:
                    continue

                # Quick relevance check: keyword must appear in the link text/title
                if topic.lower() not in text.lower():
                    continue

                seen_urls.add(actual_url)

                # Try to extract source from URL domain
                try:
                    domain = urllib.parse.urlparse(actual_url).netloc
                    source = domain.replace('www.', '')
                except:
                    source = "Unknown"

                articles.append({
                    "Title": text,
                    "Link": actual_url,
                    "Published": "",
                    "Published_Obj": None,
                    "Source": source,
                    "Summary": "",
                    "Language": "EN",
                    "MatchLocation": "WebSearch"
                })

        except Exception as e:
            print(f"  ! Web search page error: {e}")
            continue

    print(f"  -> Found {len(articles)} articles via Google web scraping")
    return articles


def fetch_google_news(topic, country="IN", start_date=None, end_date=None, verify_content=False):
    """
    Fetches news from Google News RSS AND Google web search to maximize coverage.
    Uses when:Nd syntax to match Google's web search behavior.
    
    Args:
        topic: Search keyword
        country: Target country code (e.g., 'IN', 'US', 'GB')
        start_date: Filter articles after this date (YYYY-MM-DD)
        end_date: Filter articles before this date (YYYY-MM-DD)
        verify_content: If True, verify keyword exists in article content. If False, return all RSS results.
    """
    mode = "with content verification" if verify_content else "(all results, no verification)"
    print(f"Fetching '{topic}' via Google News RSS + Web Search {mode}...")
    
    all_articles = []
    seen_links = set()
    
    # Parse filter dates
    s_date = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
    e_date = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None
    today = datetime.now().date()

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # Calculate date parameters using after/before for better coverage
    date_param = ""
    if start_date and end_date:
        date_param = f" after:{start_date} before:{end_date}"
    elif start_date:
        date_param = f" after:{start_date}"
    elif end_date:
        date_param = f" before:{end_date}"
    
    encoded_topic = urllib.parse.quote(topic + date_param)
    quoted_topic = '"' + topic + '"' + date_param
    encoded_quoted_topic = urllib.parse.quote(quoted_topic)
    
    # Get country specific parameters, default to IN
    config = COUNTRY_CONFIGS.get(country, COUNTRY_CONFIGS["IN"])
    gl, hl, ceid = config["gl"], config["hl"], config["ceid"]
    
    # Build multiple query URLs to maximize coverage (like web search does)
    query_urls = [
        # Primary: with when:Nd parameter for date range
        f"https://news.google.com/rss/search?q={encoded_topic}&gl={gl}&ceid={ceid}&hl={hl}",
        # Fallback: without when parameter
        f"https://news.google.com/rss/search?q={urllib.parse.quote(topic)}&gl={gl}&ceid={ceid}&hl={hl}",
        # Try with quotes for exact match
        f"https://news.google.com/rss/search?q={encoded_quoted_topic}&gl={gl}&ceid={ceid}&hl={hl}",
    ]
    
    candidates = []
    
    for url in query_urls:
        try:
            print(f"  Trying RSS: {url[:80]}...")
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            feed = feedparser.parse(response.content)
            
            for entry in feed.entries:
                link = entry.link
                if link in seen_links:
                    continue
                
                # Parse Date
                pub_date = None
                pub_date_str = ""
                if hasattr(entry, 'published'):
                    pub_date_str = entry.published
                    try:
                        if entry.published_parsed:
                             pub_date = datetime(*entry.published_parsed[:6]).date()
                        else:
                             pub_date = parser.parse(entry.published).date()
                    except:
                        pass
                
                # Date filter
                if s_date and pub_date and pub_date < s_date:
                    continue
                if e_date and pub_date and pub_date > e_date:
                    continue 
                
                seen_links.add(link)
                
                source_name = "Google News"
                if 'source' in entry and 'title' in entry.source:
                     source_name = entry.source.title

                # Get RSS summary/description if available
                summary = ""
                if hasattr(entry, 'summary'):
                    summary = entry.summary
                elif hasattr(entry, 'description'):
                    summary = entry.description

                candidates.append({
                    "Title": entry.title,
                    "Link": link,
                    "Published": pub_date_str,
                    "Published_Obj": pub_date,
                    "Source": source_name,
                    "Summary": summary,
                    "Language": "EN",
                    "MatchLocation": "RSS"
                })
                
        except Exception as e:
            print(f"  ! Error fetching {url[:50]}: {e}")
            continue
    
    print(f"  -> Found {len(candidates)} total RSS items from RSS feed")
    
    # ── Supplement with Google Web Search scraping ──
    web_articles = fetch_google_web_news(topic, country, start_date, end_date)

    # Merge web articles, dedup by domain+path
    def normalize_url(u):
        """Normalize URL for dedup: strip scheme, www, trailing slash."""
        try:
            parsed = urllib.parse.urlparse(u)
            host = parsed.netloc.replace('www.', '').lower()
            path = parsed.path.rstrip('/').lower()
            return f"{host}{path}"
        except:
            return u.lower()

    rss_normalized = {normalize_url(c['Link']) for c in candidates}

    new_from_web = 0
    for art in web_articles:
        norm = normalize_url(art['Link'])
        if norm not in rss_normalized:
            rss_normalized.add(norm)
            candidates.append(art)
            new_from_web += 1

    if new_from_web:
        print(f"  -> Added {new_from_web} NEW articles from web search (not in RSS)")

    print(f"  -> Total combined articles before verification: {len(candidates)}")

    # ── Keyword Verification ──
    # Always verify the keyword is actually present in each article.
    # Check title first (fast), then RSS summary, then fetch the article body.
    print(f"Verifying keyword '{topic}' presence in all {len(candidates)} articles...")
    verified_articles = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        future_to_art = {
            executor.submit(check_keyword_in_content, art, topic, headers): art
            for art in candidates
        }
        for future in concurrent.futures.as_completed(future_to_art):
            try:
                result = future.result()
                if result is not None:
                    verified_articles.append(result)
            except Exception:
                pass

    print(f"  -> {len(verified_articles)} articles passed keyword verification (keyword found in title/summary/body)")
    print(f"  -> {len(candidates) - len(verified_articles)} articles rejected (keyword not found)")

    all_articles = verified_articles

    # Sort by Date (Newest first, web search articles without dates go last)
    all_articles.sort(
        key=lambda x: x["Published_Obj"] if x["Published_Obj"] else datetime.min.date(), 
        reverse=True
    )
    
    # Cleanup
    for a in all_articles:
        del a["Published_Obj"]
        
    print(f"Total Verified Articles: {len(all_articles)}")
    
    # Resolve links in parallel to get actual source URLs
    if all_articles:
        print(f"Resolving {len(all_articles)} links in parallel...")
        all_articles = resolve_links_parallel(all_articles)
        
    return all_articles

def resolve_url(url):
    """
    Resolves Google News RSS redirect URLs to the actual article URL.
    Uses 'googlenewsdecoder' to decode the URL.
    """
    if 'news.google.com' not in url:
        return url
        
    try:
        from googlenewsdecoder import new_decoderv1
        decoded = new_decoderv1(url)
        if decoded.get("status") and decoded.get("decoded_url"):
             return decoded["decoded_url"]
    except Exception:
        pass
    
    return url

def resolve_links_parallel(articles):
    """
    Resolves links for a list of articles in parallel.
    Updates the 'Link' key in each article dictionary.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        # Create a map of future -> article_dict
        future_to_article = {
            executor.submit(resolve_url, art['Link']): art 
            for art in articles
        }
        
        for future in concurrent.futures.as_completed(future_to_article):
            article = future_to_article[future]
            try:
                resolved_link = future.result()
                if resolved_link != article['Link']:
                    article['Link'] = resolved_link
                    # Optional: Update source if it was generic "Google News"
                    # But we usually trust the RSS feed's source name
            except Exception as e:
                # If resolution fails, keep original link
                pass
                
    return articles

if __name__ == "__main__":
    try:
        start = "2026-01-18"
        end = "2026-01-29"
        country = "US"
        results = fetch_google_news("PRADAN", country, start, end)
        print(f"\n--- Found {len(results)} Verified Results ---")
        for r in results[:10]:
            print(f"[{r['MatchLocation']}] {r['Published']} - {r['Title'][:50]}... ({r['Source']})")
    except Exception as e:
        print(f"Error: {e}")

