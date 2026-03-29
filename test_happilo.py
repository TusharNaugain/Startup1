from news_extractor import fetch_google_news

articles = fetch_google_news("Happilo", start_date="2026-02-18", end_date="2026-02-23")
print(f"Found {len(articles)}")
for a in articles:
    print(f"- {a['Source']}: {a['Title']} | {a['Link']}")
