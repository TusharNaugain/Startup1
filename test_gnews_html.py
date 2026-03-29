import requests
from bs4 import BeautifulSoup
import urllib.parse
from datetime import datetime

topic = "Happilo"
url = f"https://news.google.com/search?q={urllib.parse.quote(topic)}&hl=en-IN&gl=IN&ceid=IN%3Aen"

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
try:
    import cloudscraper
    scraper = cloudscraper.create_scraper()
    res = scraper.get(url, headers=headers)
except:
    res = requests.get(url, headers=headers)

soup = BeautifulSoup(res.text, 'html.parser')
articles = soup.find_all('article')
print(f"Found {len(articles)} articles via HTML scraping")

for a in articles:
    link_tag = a.find('a', href=True)
    if link_tag:
        title = link_tag.text.strip()
        link = link_tag['href'].replace('./', 'https://news.google.com/')
        print(f"- {title} | {link}")

