import requests
import json
import re

def search_ddg_html(query, timelimit='w'):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:102.0) Gecko/20100101 Firefox/102.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    }
    
    # First, get the vqd token
    res = requests.get(f"https://html.duckduckgo.com/html/?q={query}", headers=headers)
    vqd_match = re.search(r'name="vqd" value="([^"]+)"', res.text)
    if not vqd_match:
        return []
        
    vqd = vqd_match.group(1)
    
    # Second request with the date limit
    payload = {
        'q': query,
        'b': '',
        'df': timelimit,
        'vqd': vqd
    }
    
    res = requests.post("https://html.duckduckgo.com/html/", data=payload, headers=headers)
    
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(res.text, 'html.parser')
    results = []
    
    for a in soup.find_all('a', class_='result__url'):
        href = a.get('href', '')
        # DuckDuckGo wraps links in a redirect, we need the real URL
        if 'uddg=' in href:
            import urllib.parse
            parsed = urllib.parse.urlparse(href)
            qs = urllib.parse.parse_qs(parsed.query)
            if 'uddg' in qs:
                real_link = qs['uddg'][0]
                # Try to get the title from the sibling snippet
                title_elem = a.find_parent('div', class_='result__body').find_previous_sibling('h2', class_='result__title')
                title = title_elem.text.strip() if title_elem else "Unknown Title"
                
                snippet_elem = a.find_parent('div', class_='result__body').find('a', class_='result__snippet')
                snippet = snippet_elem.text.strip() if snippet_elem else ""
                
                results.append({
                    "title": title,
                    "href": real_link,
                    "body": snippet
                })
                
    return results

if __name__ == "__main__":
    links = search_ddg_html("Happilo")
    print(f"Found {len(links)}")
    for l in links[:5]:
        print(f"{l['title']} | {l['href']}")
