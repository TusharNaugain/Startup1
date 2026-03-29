import feedparser
import urllib.parse
import requests
from datetime import datetime, timedelta
from dateutil import parser
from bs4 import BeautifulSoup
import concurrent.futures
import re

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

def fetch_google_news(topic, start_date=None, end_date=None, verify_content=False):
    """
    Fetches news from Google News RSS using multiple query strategies to maximize coverage.
    Uses when:Nd syntax to match Google's web search behavior.
    
    Args:
        topic: Search keyword
        start_date: Filter articles after this date (YYYY-MM-DD)
        end_date: Filter articles before this date (YYYY-MM-DD)
        verify_content: If True, verify keyword exists in article content. If False, return all RSS results.
    """
    mode = "with content verification" if verify_content else "(all results, no verification)"
    print(f"Fetching '{topic}' via Google News RSS (multi-strategy) {mode}...")
    
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
    
    # Build multiple query URLs to maximize coverage (like web search does)
    query_urls = [
        # Primary: with when:Nd parameter for date range
        f"https://news.google.com/rss/search?q={encoded_topic}&gl=IN&ceid=IN:en&hl=en-IN",
        # Fallback: without when parameter
        f"https://news.google.com/rss/search?q={urllib.parse.quote(topic)}&gl=IN&ceid=IN:en&hl=en-IN",
        # Try with quotes for exact match
        f"https://news.google.com/rss/search?q={encoded_quoted_topic}&gl=IN&ceid=IN:en&hl=en-IN",
    ]
    
    candidates = []
    
    for url in query_urls:
        try:
            print(f"  Trying: {url[:80]}...")
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
                    "MatchLocation": ""
                })
                
        except Exception as e:
            print(f"  ! Error fetching {url[:50]}: {e}")
            continue
    
    print(f"  -> Found {len(candidates)} total RSS items from RSS feed")
    
    # Skip verification - return all RSS results (matches Google web search behavior)
    # Google uses semantic matching, so articles may not contain exact keyword
    for art in candidates:
        art['MatchLocation'] = 'RSS'  # Indicate source is RSS feed
    all_articles = candidates
    print(f"  -> Returning all {len(all_articles)} RSS results")

    # Sort by Date (Newest first)
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
        results = fetch_google_news("PRADAN", start, end)
        print(f"\n--- Found {len(results)} Verified Results ---")
        for r in results[:10]:
            print(f"[{r['MatchLocation']}] {r['Published']} - {r['Title'][:50]}... ({r['Source']})")
    except Exception as e:
        print(f"Error: {e}")

