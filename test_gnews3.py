from gnews import GNews
from datetime import datetime

google_news = GNews(language='en', country='IN')
google_news.start_date = (2026, 2, 18)
google_news.end_date = (2026, 2, 23)

try:
    news = google_news.get_news("Happilo")
    print(f"Found {len(news)} articles for Happilo")
    for n in news[:5]:
        print(f"- {n.get('publisher', {}).get('title')}: {n.get('title')} | {n.get('url')}")
except Exception as e:
    print("Error:", e)
