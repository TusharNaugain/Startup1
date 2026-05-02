from dotenv import load_dotenv
load_dotenv()  # Load .env for local dev (no-op in production where env vars are set directly)

from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from flask_login import login_required, current_user
from link_checker import DataFetcher, DataProcessor, expand_keywords
from news_extractor import fetch_google_news
from werkzeug.utils import secure_filename
import concurrent.futures
import os
import secrets
import json
import pandas as pd
import re
import io
from datetime import datetime, timedelta
from duckduckgo_search import DDGS

from extensions import login_manager, csrf, limiter, mail, init_firebase
from tokens import consume_token

app = Flask(__name__)

# ─── Configuration ────────────────────────────────────────────────────────
# Secrets must come from env in production. Generate one fallback so local
# dev works; never let SECRET_KEY default in a deployed environment.
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

# Session / cookie hardening
_in_production = os.environ.get('FLASK_ENV') != 'development'
app.config.update(
    SESSION_COOKIE_SECURE=_in_production,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(days=14),
    REMEMBER_COOKIE_SECURE=_in_production,
    REMEMBER_COOKIE_HTTPONLY=True,
    REMEMBER_COOKIE_SAMESITE='Lax',
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB request cap
    WTF_CSRF_TIME_LIMIT=None,
)

# Admin email — whoever signs up with this address gets is_admin=True
app.config['ADMIN_EMAIL'] = os.environ.get('ADMIN_EMAIL', 'naugaintushar@gmail.com')

# SMTP — used to email the admin when a payment is submitted
app.config['MAIL_SERVER']  = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT']    = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'false').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', app.config['ADMIN_EMAIL'])

# ─── Filesystem ───────────────────────────────────────────────────────────
_IS_SERVERLESS = bool(os.environ.get('VERCEL') or os.environ.get('AWS_LAMBDA_FUNCTION_NAME'))
_BASE_WRITE_DIR = '/tmp' if _IS_SERVERLESS else os.path.dirname(os.path.abspath(__file__))

app.config['UPLOAD_FOLDER'] = os.path.join(_BASE_WRITE_DIR, 'uploads')
app.config['Result_FOLDER'] = os.path.join(_BASE_WRITE_DIR, 'results')
app.config['PAYMENT_SCREENSHOT_FOLDER'] = os.path.join(_BASE_WRITE_DIR, 'payment_screenshots')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['Result_FOLDER'], exist_ok=True)
os.makedirs(app.config['PAYMENT_SCREENSHOT_FOLDER'], exist_ok=True)

# ─── Initialize extensions ────────────────────────────────────────────────
login_manager.init_app(app)
csrf.init_app(app)
limiter.init_app(app)
mail.init_app(app)

# Firebase
with app.app_context():
    init_firebase()

# Flask-Login user loader
from firebase_models import get_firebase_user  # noqa: E402

@login_manager.user_loader
def load_user(user_id):
    return get_firebase_user(user_id)

# Register blueprints
from auth import auth_bp      # noqa: E402
from payment import payment_bp  # noqa: E402
from admin import admin_bp    # noqa: E402
app.register_blueprint(auth_bp)
app.register_blueprint(payment_bp)
app.register_blueprint(admin_bp)

# Initialize Link Checker Components
fetcher = DataFetcher()
processor = DataProcessor()


@app.route('/')
@login_required
def home():
    return render_template('index.html')

@app.route('/news_tool')
@login_required
def news_tool():
    return render_template('news_extractor.html')

@app.route('/headline_tool')
@login_required
def headline_tool():
    return render_template('headline_analyzer.html')

@app.route('/download/<path:filename>')
@login_required
def download_file(filename):
    return send_from_directory(app.config['Result_FOLDER'], filename, as_attachment=True)


@app.route('/api/fetch_news', methods=['POST'])
@csrf.exempt
@login_required
@consume_token('news_extractor')
def api_fetch_news():
    data = request.json
    topic = data.get('topic')
    country = data.get('country', 'IN')  # Default to India if not provided
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    
    if not topic:
         return jsonify({"error": "Topic is required"}), 400
         
    try:
        articles = fetch_google_news(topic, country, start_date, end_date)
        return jsonify({"articles": articles})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/analyze_csv', methods=['POST'])
@csrf.exempt
@login_required
@consume_token('multifind_csv')
def analyze_csv():
    """
    CSV-based analysis mode for YouTube / Share of Voice exports.
    Reads 'Headline' + 'Youtube Channel Name' columns directly — no HTTP fetching.
    Applies the same brand / must-have / shouldnt-have keyword rules as /analyze.
    """
    if 'csv_file' not in request.files:
        return jsonify({'error': 'csv_file is required'}), 400

    csv_file = request.files['csv_file']
    configs_raw = request.form.get('configs', '[]')
    try:
        configs = json.loads(configs_raw)
    except Exception:
        return jsonify({'error': 'Invalid configs JSON'}), 400

    # Clean & compile keyword patterns (same logic as /analyze)
    for cfg in configs:
        cfg['keywords']  = expand_keywords([kw for kw in cfg.get('keywords', []) if kw.strip()])
        excl_clean = [kw.strip().lower() for kw in cfg.get('shouldntHave', []) if kw.strip()]
        cfg['_excl_patterns'] = [(kw, re.compile(r'\b' + re.escape(kw) + r'\b')) for kw in excl_clean]

    results = []
    try:
        import csv as csv_module, io
        content = csv_file.read().decode('utf-8', errors='replace')
        reader  = csv_module.DictReader(io.StringIO(content))

        # Auto-detect column names (case-insensitive)
        fieldnames_lower = {f.strip().lower(): f for f in (reader.fieldnames or [])}
        url_col      = next((fieldnames_lower[k] for k in fieldnames_lower if 'url'     in k), None)
        headline_col = next((fieldnames_lower[k] for k in fieldnames_lower if 'headline' in k or 'title' in k), None)
        channel_col  = next((fieldnames_lower[k] for k in fieldnames_lower if 'channel' in k), None)

        if not url_col:
            return jsonify({'error': 'CSV must have a URL column'}), 400

        seen_urls = set()
        for row in reader:
            url = row.get(url_col, '').strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            headline = (row.get(headline_col, '') if headline_col else '').strip()
            channel  = (row.get(channel_col,  '') if channel_col  else '').strip()
            # Combine headline + channel name as the text to match against
            search_text = (headline + ' ' + channel).lower()

            final_result = None
            for cfg in configs:
                brand_name = cfg.get('brandName', 'Unknown')
                keywords   = cfg.get('keywords', [])
                excl_pats  = cfg.get('_excl_patterns', [])
                must_kws   = [kw for kw in cfg.get('mustHave', []) if kw.strip()]

                # 1. Exclusion check (word-boundary)
                excluded = False
                for excl_kw, excl_pat in excl_pats:
                    if excl_kw in search_text and excl_pat.search(search_text):
                        excluded = True
                        break

                if excluded:
                    current_status = 'Irrelevant (Excluded)'
                    current_found  = []
                else:
                    # 2. Brand keyword check
                    found_brand = [kw for kw in keywords if kw.lower() in search_text]
                    if not found_brand:
                        current_status = 'Irrelevant'
                        current_found  = []
                    else:
                        # 3. Must-have check (OR logic — any one match passes)
                        if must_kws:
                            found_must = [kw for kw in must_kws if kw.lower() in search_text]
                            if not found_must:
                                current_status = 'Irrelevant (Context Missing)'
                                current_found  = found_brand
                            else:
                                current_status = 'Relevant'
                                current_found  = list(set(found_brand + found_must))
                        else:
                            current_status = 'Relevant'
                            current_found  = found_brand

                row_result = {
                    'brandName':     brand_name,
                    'URL':           url,
                    'Status':        current_status,
                    'Match Count':   len(current_found),
                    'Found Keywords': ', '.join(current_found),
                    # Pass through extra CSV columns for display
                    'Headline':  headline,
                    'Channel':   channel,
                    'Views':     row.get(next((v for k,v in fieldnames_lower.items() if 'view' in k), ''), ''),
                }

                if final_result is None:
                    final_result = row_result
                if current_status.startswith('Relevant'):
                    final_result = row_result
                    break

            if final_result:
                results.append(final_result)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return jsonify({'results': results})


@app.route('/analyze', methods=['POST'])
@csrf.exempt
@login_required
@consume_token('multifind')
def analyze():
    data = request.json
    configs = data.get('configs', [])
    links = data.get('links', [])
    
    # Handle legacy flat structure gracefully if needed
    if not configs and data.get('keywords'):
        configs = [{
            "brandName": "Brand",
            "keywords": data.get('keywords', []),
            "mustHave": data.get('context_keywords', []),
            "shouldntHave": data.get('exclude_keywords', [])
        }]

    # Pre-expand keywords; also strip empty strings from trailing commas in UI input
    for cfg in configs:
        cfg["keywords"] = expand_keywords([kw for kw in cfg.get("keywords", []) if kw.strip()])
        # Pre-compile exclusion regex patterns ONCE per config (reused across all 540 URLs)
        excl_clean = [kw.strip().lower() for kw in cfg.get("shouldntHave", []) if kw.strip()]
        cfg["_excl_patterns"] = [
            (kw, re.compile(r'\b' + re.escape(kw) + r'\b')) for kw in excl_clean
        ]

    results = []
    
    # Use threading for faster processing
    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
        future_to_url = {executor.submit(process_single_link, url, configs): url for url in links}
        for future in concurrent.futures.as_completed(future_to_url):
            try:
                # get a list of results (one for each config run against this URL)
                url_results = future.result()
                results.extend(url_results)
            except Exception as e:
                # Handle unexpected errors gracefully by returning exactly ONE error row per URL
                fallback_name = configs[0].get("brandName", "Unknown") if configs else "Unknown"
                results.append({
                    "brandName": fallback_name,
                    "URL": future_to_url[future],
                    "Status": "Error",
                    "Match Count": 0,
                    "Found Keywords": f"System Error: {str(e)}"
                })
                
    return jsonify({"results": results})


def deep_verify_link(url, keywords):
    """
    Fallback method: Uses DuckDuckGo to check if the URL is associated with the keyword
    in the search index. This helps when the page content is blocked/unreachable.
    """
    try:
        from duckduckgo_search import DDGS
        # Strategy: Search for the URL itself. 
        # If it's indexed, the snippet usually contains key info.
        try:
            results = DDGS().text(url, max_results=1)
            
            if results:
                 res = results[0]
                 # Check if result is actually for our URL (or close enough)
                 if url in res['href'] or res['href'] in url:
                     body_lower = res['body'].lower()
                     title_lower = res['title'].lower()
                     
                     found_keywords = []
                     for kw in keywords:
                         if kw.lower() in body_lower or kw.lower() in title_lower:
                             found_keywords.append(kw)
                     
                     if found_keywords:
                         return True, found_keywords
        except Exception:
            pass # Strategy 1 failed, try next
        
        # secondary strategy: site:domain keyword
        # (Only if first strategy failed)
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
            if keywords and len(keywords) > 0:
                query = f"{keywords[0]} site:{domain}"
                results = DDGS().text(query, max_results=3)
                if results:
                    for res in results:
                        if url in res['href'] or res['href'] in url:
                             return True, [keywords[0]]
        except Exception:
            pass
            
    except Exception as e:
        print(f"Deep Verification Error for {url}: {e}")
        
    return False, []

# Platforms where page body is completely JS-gated — skip fetch, check URL only.
# NOTE: YouTube is intentionally EXCLUDED here because YouTube URLs (watch?v=ID)
# never contain brand names. The brand name is in the HTML og:title/og:description
# meta tags which YouTube DOES serve without JavaScript.
_URL_ONLY_DOMAINS = (
    "instagram.com", "tiktok.com",
    "twitter.com", "x.com", "facebook.com", "fb.com", "linkedin.com"
)

def _extract_youtube_meta(response_content):
    """
    Extract this video's own metadata from a YouTube page:
      - og:title / og:description / og:video:tag  (Open Graph meta tags)
      - Channel / author name from JSON-LD        (matches CSV 'Youtube Channel Name')
      - <title> tag as fallback

    Returning ALL of these in one combined string means URL-paste mode now checks
    the same fields as CSV-upload mode (title + channel), keeping results consistent.
    """
    try:
        import json as _json
        soup = BeautifulSoup(response_content, 'html.parser')
        parts = []

        # 1. Open Graph meta tags
        for prop in ('og:title', 'og:description', 'og:video:tag'):
            tag = soup.find('meta', property=prop)
            if tag and tag.get('content'):
                parts.append(tag['content'])

        # 2. Channel / author name from JSON-LD (schema.org VideoObject)
        #    YouTube injects this as <script type="application/ld+json">
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = _json.loads(script.string or '')
                # Can be a list or a single object
                items = data if isinstance(data, list) else [data]
                for item in items:
                    # Author / channel name
                    author = item.get('author') or item.get('publisher') or {}
                    if isinstance(author, dict):
                        name = author.get('name', '')
                        if name:
                            parts.append(name)
                    # Video name as extra fallback
                    vid_name = item.get('name', '')
                    if vid_name:
                        parts.append(vid_name)
            except Exception:
                pass

        # 3. <title> tag as final fallback
        title_tag = soup.find('title')
        if title_tag and title_tag.string:
            parts.append(title_tag.string)

        combined = ' '.join(parts).lower()
        return combined
    except Exception:
        return ''



def process_single_link(url, configs, deep_verify=False):
    url_lower = url.lower()

    # ── YouTube path: fetch page but match ONLY against og: meta tags ──
    # Full YouTube HTML contains recommended video titles which pollute keyword matching.
    # og:title / og:description / og:video:tag are this video's OWN metadata only.
    is_youtube = "youtube.com" in url_lower or "youtu.be" in url_lower
    if is_youtube:
        response = fetcher.fetch_content(url)
        final_result = None

        if not isinstance(response, str):
            # Extract ONLY this video's own metadata (not the full page with recommendations)
            meta_text = _extract_youtube_meta(response.content)
            # Fallback: if meta extraction returned nothing useful, use the url itself
            search_text = meta_text if len(meta_text) > 20 else url_lower
        else:
            # Fetch failed — fall back to URL-only matching
            search_text = url_lower

        for cfg in configs:
            brand_name       = cfg.get("brandName", "Unknown")
            keywords         = cfg.get("keywords", [])
            excl_pats        = cfg.get("_excl_patterns", [])
            context_keywords = [kw for kw in cfg.get("mustHave", []) if kw.strip()]

            # Exclusion — against video metadata only
            excluded = False
            for excl_kw, excl_pat in excl_pats:
                if excl_kw in search_text:
                    if excl_pat.search(search_text):
                        excluded = True
                        break

            if excluded:
                current_status = "Irrelevant (Excluded)"
                current_count, current_found = 0, []
            else:
                # Brand keyword check against title/description
                found_brand_kws = [kw for kw in keywords if kw.lower() in search_text]
                if not found_brand_kws:
                    current_status = "Irrelevant"
                    current_count, current_found = 0, []
                else:
                    # Must-have check (OR logic — any one match passes)
                    if context_keywords:
                        found_must = [kw for kw in context_keywords if kw.lower() in search_text]
                        if not found_must:
                            current_status = "Irrelevant (Context Missing)"
                            current_count  = len(found_brand_kws)
                            current_found  = found_brand_kws
                        else:
                            current_status = "Relevant"
                            current_found  = list(set(found_brand_kws + found_must))
                            current_count  = len(current_found)
                    else:
                        current_status = "Relevant"
                        current_found  = found_brand_kws
                        current_count  = len(current_found)

            if final_result is None:
                final_result = {"brandName": brand_name, "URL": url,
                                "Status": current_status, "Match Count": current_count,
                                "Found Keywords": ", ".join(current_found)}
            if current_status.startswith("Relevant"):
                final_result = {"brandName": brand_name, "URL": url,
                                "Status": current_status, "Match Count": current_count,
                                "Found Keywords": ", ".join(current_found)}
                break
        return [final_result] if final_result else []

    # ── Fast-path for pure JS-gated social platforms: skip fetch, URL-only ──
    is_url_only = any(d in url_lower for d in _URL_ONLY_DOMAINS)
    if is_url_only:
        final_result = None
        for cfg in configs:
            brand_name = cfg.get("brandName", "Unknown")
            keywords   = cfg.get("keywords", [])
            excl_pats  = cfg.get("_excl_patterns", [])
            context_keywords = [kw for kw in cfg.get("mustHave", []) if kw.strip()]

            # Exclusion — URL only
            excluded = any(pat.search(url_lower) for _, pat in excl_pats)
            if excluded:
                current_status = "Irrelevant (Excluded)"
                current_count, current_found = 0, []
            else:
                found_brand_kws = [kw for kw in keywords if kw.lower() in url_lower]
                if not found_brand_kws:
                    current_status = "Irrelevant"
                    current_count, current_found = 0, []
                else:
                    # Must-have: on URL-only pages we skip must-have (can't verify body)
                    current_status = "Relevant (URL Match)"
                    current_found  = found_brand_kws
                    current_count  = len(current_found)

            if final_result is None:
                final_result = {"brandName": brand_name, "URL": url,
                                "Status": current_status, "Match Count": current_count,
                                "Found Keywords": ", ".join(current_found)}
            if current_status.startswith("Relevant"):
                final_result = {"brandName": brand_name, "URL": url,
                                "Status": current_status, "Match Count": current_count,
                                "Found Keywords": ", ".join(current_found)}
                break
        return [final_result] if final_result else []

    # ── Normal path: fetch full page ──
    response = fetcher.fetch_content(url)
    
    # A single result dictionary for this URL
    final_result = None
    
    if not isinstance(response, str):
        text = processor.extract_text(response.content)
        html_lower = response.content.decode('utf-8', errors='ignore').lower()
        text_lower = text.lower()
        
        url_lower = url.lower()
        
        # Check overall block indicators (once per URL)
        block_indicators = [
            "enable javascript", "javascript is disabled", "requires javascript",
            "attention required! | cloudflare", "sorry, you have been blocked", 
            "cloudflare ray id", "security service to protect itself",
            "subscribe to read", "paywall",
            "verify you are human", "captcha", "bot behavior", "access denied", 
            "unusual traffic", "please wait while we verify", "checking your browser",
            "not a robot", "robot check", "turn on javascript", "pardon our interruption"
        ]
        is_blocked = any(indicator in text_lower or indicator in html_lower for indicator in block_indicators)
        if len(text_lower) < 150:
            is_blocked = True


        for cfg in configs:
            brand_name = cfg.get("brandName", "Unknown")
            keywords = cfg.get("keywords", [])
            # Strip empty strings caused by trailing commas in UI input
            context_keywords = [kw for kw in cfg.get("mustHave", []) if kw.strip()]
            excl_pats = cfg.get("_excl_patterns", [])  # pre-compiled at request level

            # 1. Exclusions Check — pre-compiled whole-word regex (fast: substring pre-check gates regex)
            excluded = False
            for excl_kw, excl_pat in excl_pats:
                # Fast pre-check: substring must exist before running regex
                if excl_kw in text_lower or excl_kw in html_lower or excl_kw in url_lower:
                    if (excl_pat.search(text_lower) or
                        excl_pat.search(html_lower) or
                        excl_pat.search(url_lower)):
                        excluded = True
                        break
                    
            if excluded:
                current_status = "Irrelevant (Excluded)"
                current_count = 0
                current_found = []
            else:
                # 2. Must-Have Check (Must be in Body or HTML)
                has_must_have = False
                found_context_kws = []
                if not context_keywords:
                    has_must_have = True
                else:
                    for kw in context_keywords:
                        if kw.lower() in text_lower or kw.lower() in html_lower:
                            found_context_kws.append(kw)
                    if found_context_kws:
                        has_must_have = True
                
                # 3. Brand Check (Body, HTML, URL)
                brand_match_source = None
                found_brand_kws = []
                
                for kw in keywords:
                    if kw.lower() in text_lower:
                        found_brand_kws.append(kw)
                
                if found_brand_kws:
                    brand_match_source = "Body"
                else:
                    for kw in keywords:
                        if kw.lower() in html_lower:
                            found_brand_kws.append(kw)
                    if found_brand_kws:
                        brand_match_source = "HTML Match"
                    else:
                        for kw in keywords:
                            if kw.lower() in url_lower:
                                found_brand_kws.append(kw)
                        if found_brand_kws:
                            brand_match_source = "URL Match"

                # 4. Final Evaluation
                if not found_brand_kws:
                    current_status = "Irrelevant"
                    current_count = 0
                    current_found = []
                    
                    # Fallback 3: Deep Verification (Search Engine Check)
                    if deep_verify:
                        is_verified, verified_kws = deep_verify_link(url, keywords)
                        if is_verified:
                            current_count = len(verified_kws)
                            current_found = verified_kws
                            current_status = "Relevant (Deep Verification)"
                
                elif not has_must_have:
                    current_status = "Irrelevant (Context Missing)"
                    current_count = len(found_brand_kws)
                    current_found = found_brand_kws
                else:
                    if brand_match_source == "Body":
                        current_status = "Relevant"
                    else:
                        current_status = f"Relevant ({brand_match_source})"
                        if is_blocked and brand_match_source == "URL Match":
                            current_status += " - Blocked by the site so insure it from yourself"
                    
                    current_found = list(set(found_brand_kws + found_context_kws))
                    current_count = len(current_found)

            # If this is the FIRST config we are evaluating, store it as the fallback baseline
            if final_result is None:
                final_result = {
                    "brandName": brand_name,
                    "URL": url,
                    "Status": current_status,
                    "Match Count": current_count,
                    "Found Keywords": ", ".join(current_found) if current_found else ""
                }
            
            # If this config matches successfully, replace the baseline, and stop checking other configs
            if current_status.startswith("Relevant"):
                final_result = {
                    "brandName": brand_name,
                    "URL": url,
                    "Status": current_status,
                    "Match Count": current_count,
                    "Found Keywords": ", ".join(current_found) if current_found else ""
                }
                break
            
        # Return exactly ONE item per URL
        return [final_result] if final_result else []
    else:
        # Error fetching URL, return just ONE "Missing" status tied to the first config
        cfg = configs[0] if configs else {}
        
        status_msg = "Missing"
        if any(code in response for code in ["403", "429", "503", "406", "Timeout", "captcha"]):
            status_msg = "Blocked by the site so insure it from yourself"
        elif "404" in response:
            status_msg = "Page Not Found (404)"
            
        return [{
            "brandName": cfg.get("brandName", "Unknown"),
            "URL": url,
            "Status": status_msg,
            "Match Count": 0,
            "Found Keywords": f"Failed to fetch content ({response})"
        }]

@app.route('/api/get_sheets', methods=['POST'])
@csrf.exempt
@login_required
def get_sheets():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    filename = file.filename.lower()
    
    if not (filename.endswith('.xlsx') or filename.endswith('.xls')):
        # It's maybe CSV or unsupported
        return jsonify({'sheets': []})
        
    try:
        xl = pd.ExcelFile(file)
        return jsonify({'sheets': xl.sheet_names})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/process_headlines', methods=['POST'])
@csrf.exempt
@login_required
@consume_token('headline_analyzer')
def process_headlines():
    if 'csv_file' not in request.files:
        return render_template('headline_analyzer.html', error="No file part")
    
    file = request.files['csv_file']
    if file.filename == '':
        return render_template('headline_analyzer.html', error="No selected file")
    
    try:
        top_n = int(request.form.get('top_n', 50))
        min_freq = int(request.form.get('min_freq', 1))

        # We now expect an actual sheet name from the dynamic dropdown
        sheet_name = request.form.get('sheet_name')
        
        # Determine file type and read accordingly
        filename = file.filename.lower()
        if filename.endswith('.xlsx') or filename.endswith('.xls'):
            try:
                # read specific sheet if provided, otherwise default to first (0)
                if sheet_name:
                    df = pd.read_excel(file, sheet_name=sheet_name)
                else:
                    df = pd.read_excel(file, sheet_name=0)
            except Exception as e:

                try:
                    xl = pd.ExcelFile(file)
                    total = len(xl.sheet_names)
                    return render_template('headline_analyzer.html',
                                         error=f"Sheet {sheet_number} not found. This file only has {total} sheet(s): {', '.join(xl.sheet_names)}")
                except Exception:
                    return render_template('headline_analyzer.html', error=f"Sheet {sheet_number} not found in this file.")
            except Exception as e:
                return render_template('headline_analyzer.html', error=f"Error reading Excel file: {str(e)}")

        else:
            # Read as CSV
            try:
                df = pd.read_csv(file)
            except Exception:
                file.seek(0)
                df = pd.read_csv(file, encoding='latin1')
            
        # Normalize columns
        df.columns = df.columns.str.strip().str.lower()
        
        # Check for headline column
        if 'headline' not in df.columns:
            # Try to find similar
            found_col = None
            for col in df.columns:
                if 'headline' in col or 'title' in col:
                    found_col = col
                    break
            
            if found_col:
                target_col = found_col
            else:
                return render_template('headline_analyzer.html', error=f"Column 'headline' not found. Available: {', '.join(df.columns)}")
        else:
            target_col = 'headline'
            
        # Analyze
        counts = df[target_col].value_counts().reset_index()
        counts.columns = ['headline', 'count']
        
        # Filter by Minimum Frequency
        filtered_counts = counts[counts['count'] >= min_freq]
        
        # Get Top N from the filtered results
        top_results = filtered_counts.head(top_n).to_dict('records')
        
        return render_template('headline_analyzer.html', 
                             result={'top': top_results},
                             top_n=top_n,
                             min_freq=min_freq)
                             
    except Exception as e:
        return render_template('headline_analyzer.html', error=str(e))

if __name__ == '__main__':
    # Host 0.0.0.0 is required for Docker containers to be accessible from outside
    app.run(host='0.0.0.0', port=5000, debug=True)
