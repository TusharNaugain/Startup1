from flask import Flask, render_template, request, jsonify
from link_checker import DataFetcher, DataProcessor, expand_keywords
from news_extractor import fetch_google_news
import concurrent.futures
import os
import uuid
import json

# In-memory cache: preview_id → { raw_path, cust_path, generator }
# Entries are lightweight; files are already on disk in uploads/
_PREVIEW_CACHE: dict = {}
from werkzeug.utils import secure_filename
from flask import send_file
from flask import send_file, send_from_directory
from generate_report import ReportGenerator, send_report_emails
import pandas as pd
import re
import io
from datetime import datetime
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Matching')))
from duckduckgo_search import DDGS

app = Flask(__name__)

# On serverless platforms (Vercel/AWS Lambda) only /tmp is writable.
# Detect Vercel via VERCEL env var; otherwise use local project folders.
_IS_SERVERLESS = bool(os.environ.get('VERCEL') or os.environ.get('AWS_LAMBDA_FUNCTION_NAME'))
_BASE_WRITE_DIR = '/tmp' if _IS_SERVERLESS else os.path.dirname(os.path.abspath(__file__))

app.config['UPLOAD_FOLDER'] = os.path.join(_BASE_WRITE_DIR, 'uploads')
app.config['Result_FOLDER'] = os.path.join(_BASE_WRITE_DIR, 'results')

# Initialize Link Checker Components
fetcher = DataFetcher()
processor = DataProcessor()

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['Result_FOLDER'], exist_ok=True)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/analytics')
def analytics():
    return render_template('analytics.html')

@app.route('/news_tool')
def news_tool():
    return render_template('news_extractor.html')

@app.route('/excel_automater')
def excel_automater():
    return render_template('excel_automater.html')

@app.route('/headline_tool')
def headline_tool():
    return render_template('headline_analyzer.html')

@app.route('/download/<path:filename>')
def download_file(filename):
    return send_from_directory(app.config['Result_FOLDER'], filename, as_attachment=True)

@app.route('/process_excel', methods=['POST'])
def process_excel():
    if 'raw_file' not in request.files or 'customer_file' not in request.files:
        return "Missing files", 400
    
    raw_file = request.files['raw_file']
    customer_file = request.files['customer_file']
    
    if raw_file.filename == '' or customer_file.filename == '':
        return "No selected file", 400

    # Save Uploads
    raw_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(raw_file.filename))
    customer_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(customer_file.filename))
    
    raw_file.save(raw_path)
    customer_file.save(customer_path)
    
    try:
        # Run Automation Logic
        generator = ReportGenerator(raw_path, customer_path)
        
        # Override output location to results folder
        # Ensure output filename always ends in .xlsx
        base_name = os.path.splitext(secure_filename(raw_file.filename))[0]
        output_filename = f"Report_{base_name}.xlsx"
        generator.output_file = os.path.join(app.config['Result_FOLDER'], output_filename)
        
        generator.load_data()
        generator.process_data()
        generator.generate_sheets()
        generated_file_path = generator.save_report()
        
        # Use absolute path and explicit download name
        abs_path = os.path.abspath(generated_file_path)
        return send_file(abs_path, as_attachment=True, download_name=output_filename)
        
    except Exception as e:
        return f"Error processing files: {str(e)}", 500


@app.route('/process_excel_pdf', methods=['POST'])
def process_excel_pdf():
    """
    Generate the Excel report then render a styled HTML summary and return it as a PDF.
    Uses weasyprint for HTML→PDF conversion (already installed).
    """
    if 'raw_file' not in request.files or 'customer_file' not in request.files:
        return "Missing files", 400

    raw_file      = request.files['raw_file']
    customer_file = request.files['customer_file']
    if raw_file.filename == '' or customer_file.filename == '':
        return "No selected file", 400

    raw_path  = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(raw_file.filename))
    cust_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(customer_file.filename))
    raw_file.save(raw_path)
    customer_file.save(cust_path)

    try:
        from weasyprint import HTML as WP_HTML

        generator = ReportGenerator(raw_path, cust_path)
        base_name = os.path.splitext(secure_filename(raw_file.filename))[0]
        output_filename = f"Report_{base_name}.xlsx"
        generator.output_file = os.path.join(app.config['Result_FOLDER'], output_filename)
        generator.load_data()
        generator.process_data()
        generator.generate_sheets()
        generator.save_report()

        # ── Build a clean HTML summary for PDF ──────────────────────────
        def pivot_to_html(rows, title):
            if not rows:
                return f'<h2>{title}</h2><p style="color:#888;">No data available.</p>'
            html = f'<h2 style="color:#2c3e6b;border-bottom:2px solid #2c3e6b;padding-bottom:6px;">{title}</h2>'
            html += '''<table style="width:100%;border-collapse:collapse;font-size:12px;margin-bottom:28px;">
                <thead><tr>
                  <th style="background:#2c3e6b;color:#fff;padding:8px 10px;text-align:left;">Status</th>
                  <th style="background:#2c3e6b;color:#fff;padding:8px 10px;text-align:left;">Usage Tier</th>
                  <th style="background:#2c3e6b;color:#fff;padding:8px 10px;text-align:left;">Email</th>
                  <th style="background:#2c3e6b;color:#fff;padding:8px 10px;text-align:right;">Total Usage</th>
                </tr></thead><tbody>'''
            for r in rows:
                rt = r.get('_row_type', 'data')
                if rt == 'grand_total':
                    bg = '#1F4E79'; fg = '#fff'; fw = 'bold'
                elif rt == 'status_total':
                    bg = '#8EA9C1'; fg = '#fff'; fw = 'bold'
                elif rt == 'usage_total':
                    bg = '#B8CCE4'; fg = '#333'; fw = 'bold'
                else:
                    bg = '#DCE6F1' if rows.index(r) % 2 == 0 else '#EAF0F8'; fg = '#333'; fw = 'normal'
                html += f'''<tr style="background:{bg};color:{fg};font-weight:{fw};">
                  <td style="padding:6px 10px;border-bottom:1px solid #ccc;">{r.get("Status","")}</td>
                  <td style="padding:6px 10px;border-bottom:1px solid #ccc;">{r.get("Usage","")}</td>
                  <td style="padding:6px 10px;border-bottom:1px solid #ccc;">{r.get("actor.properties.email","")}</td>
                  <td style="padding:6px 10px;border-bottom:1px solid #ccc;text-align:right;">{r.get("SUM of Total Usage","")}</td>
                </tr>'''
            html += '</tbody></table>'
            return html

        report_date = datetime.now().strftime('%d %B %Y')
        full_html = f'''<!DOCTYPE html><html><head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; color: #333; }}
            h1   {{ color: #2c3e6b; font-size: 22px; margin-bottom: 4px; }}
            .subtitle {{ color: #888; font-size: 13px; margin-bottom: 32px; }}
            .footer {{ margin-top: 40px; font-size: 10px; color: #aaa; border-top: 1px solid #eee; padding-top: 10px; }}
        </style></head><body>
        <h1>📊 Weekly Usage Report</h1>
        <p class="subtitle">Generated on {report_date} · Wizikey Product Analytics</p>
        {pivot_to_html(generator.lead_pivot_rows, "Lead Sheet — Usage Pivot")}
        {pivot_to_html(generator.customer_pivot_rows, "Customer Sheet — Usage Pivot")}
        <div class="footer">CONFIDENTIAL — This report is intended for internal use only.</div>
        </body></html>'''

        pdf_bytes = WP_HTML(string=full_html).write_pdf()
        pdf_filename = f"Report_{base_name}.pdf"

        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=pdf_filename,
        )

    except Exception as e:
        return f"Error generating PDF: {str(e)}", 500


# Hardcoded sender identity — all emails go from this address
_SENDER_EMAIL = "naugaintushar@gmail.com"


def _build_generator(raw_file, customer_file):
    """Save uploaded files and return an initialised, processed ReportGenerator."""
    raw_path  = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(raw_file.filename))
    cust_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(customer_file.filename))
    raw_file.save(raw_path)
    customer_file.save(cust_path)
    gen = ReportGenerator(raw_path, cust_path)
    gen.load_data()
    gen.process_data()
    gen.generate_sheets()
    return gen


@app.route('/preview_email', methods=['POST'])
def preview_email():
    """
    Generate email HTML for the requested sheet_type.
    Saves files to disk, caches the generator under a preview_id, and injects
    an editable toolbar into the returned HTML so the user can tweak names and
    send directly from the preview tab.
    """
    if 'raw_file' not in request.files or 'customer_file' not in request.files:
        return jsonify({'error': 'raw_file and customer_file are required.'}), 400

    raw_file      = request.files['raw_file']
    customer_file = request.files['customer_file']
    if not raw_file.filename or not customer_file.filename:
        return jsonify({'error': 'No file selected.'}), 400

    sheet_type       = request.form.get('sheet_type', 'Lead')
    lead_recipients  = request.form.get('lead_recipients', '')
    cust_recipients  = request.form.get('customer_recipients', '')
    sheet_link       = request.form.get('sheet_link', '')
    preview_password = request.form.get('sender_password', '').strip()

    try:
        gen = _build_generator(raw_file, customer_file)

        # Cache generator + file paths so /send_from_preview can reuse them
        preview_id = str(uuid.uuid4())
        _PREVIEW_CACHE[preview_id] = {
            'raw_path':  gen.raw_data_file,
            'cust_path': gen.customer_file,
            'generator': gen,
        }

        # Load profile image for signature
        _profile_img_path = os.path.join(os.path.dirname(__file__), 'static', 'sujata.jpg')
        _profile_bytes = open(_profile_img_path, 'rb').read() if os.path.isfile(_profile_img_path) else None

        # Load award image for signature
        _award_img_path = os.path.join(os.path.dirname(__file__), 'static', 'Reward.png')
        _award_bytes = open(_award_img_path, 'rb').read() if os.path.isfile(_award_img_path) else None

        html = gen.build_email_html(
            sheet_type        = sheet_type,
            sheet_link        = sheet_link,
            prev_grand_total  = 0,
            sender_name       = request.form.get('sender_name', 'Sujata Balasubramanium'),
            sender_title      = request.form.get('sender_title', 'Product Analyst'),
            sender_linkedin   = '',
            sender_website    = 'www.wizikey.com',
            sender_email_addr = 'sujata@wizikey.com',
            sender_address    = '3rd floor - Time Square Building - Sushant Lok 1 - Sector 43, Gurugram, 122009',
            has_profile_image = _profile_bytes is not None,
            has_award_image   = _award_bytes is not None,
            profile_image_bytes = _profile_bytes,
            award_image_bytes   = _award_bytes,
            preview_mode      = True,
            preview_id        = preview_id,
            preview_password  = preview_password,
            preview_sheet_type       = sheet_type,
            preview_lead_recipients  = lead_recipients,
            preview_cust_recipients  = cust_recipients,
        )
        return html, 200, {'Content-Type': 'text/html; charset=utf-8'}
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/send_from_preview', methods=['POST'])
def send_from_preview():
    """
    Send an email using a cached preview's files.
    Accepts: preview_id, sheet_type, sender_password, recipients (comma-sep),
             name_overrides (JSON string: {email: corrected_name})
    """
    data = request.get_json(force=True)
    preview_id  = data.get('preview_id', '')
    sheet_type  = data.get('sheet_type', 'Lead')
    password    = data.get('sender_password', '').strip().replace(' ', '')
    recipients  = [e.strip() for e in data.get('recipients', '').split(',') if e.strip()]
    name_overrides = data.get('name_overrides', {})
    workspace_overrides = data.get('workspace_overrides', {})
    sheet_link  = data.get('sheet_link', '')

    if not preview_id or preview_id not in _PREVIEW_CACHE:
        return jsonify({'error': 'Preview session expired or not found. Please regenerate the preview.'}), 400
    if not password:
        return jsonify({'error': 'Gmail App Password is required.'}), 400
    if not recipients:
        return jsonify({'error': 'At least one recipient is required.'}), 400

    cached = _PREVIEW_CACHE[preview_id]
    gen    = cached['generator']

    # Apply name overrides to the generator's other_insights_dfs
    if name_overrides or workspace_overrides:
        def _apply_override(df):
            if hasattr(df, 'empty') and not df.empty and 'User Email' in df.columns:
                if name_overrides and 'User Name' in df.columns:
                    df['User Name'] = df.apply(
                        lambda r: name_overrides.get(str(r['User Email']), r['User Name']),
                        axis=1
                    )
                if workspace_overrides and 'Workspace Name' in df.columns:
                    df['Workspace Name'] = df.apply(
                        lambda r: workspace_overrides.get(str(r['User Email']), r['Workspace Name']),
                        axis=1
                    )
        
        if hasattr(gen, 'other_insights_df'): _apply_override(gen.other_insights_df)
        if hasattr(gen, 'lead_other_insights'): _apply_override(gen.lead_other_insights)
        if hasattr(gen, 'customer_other_insights'): _apply_override(gen.customer_other_insights)

    try:
        output_filename = f"Report_preview_{datetime.now().strftime('%d-%m-%Y')}.xlsx"
        report_path     = os.path.join(app.config['Result_FOLDER'], output_filename)
        gen.output_file = report_path
        gen.save_report()
    except Exception as e:
        return jsonify({'error': f'Report generation failed: {str(e)}'}), 500

    lead_rec = recipients if sheet_type == 'Lead' else []
    cust_rec = recipients if sheet_type == 'Customer' else []

    # Load profile image for signature
    _profile_img_path = os.path.join(os.path.dirname(__file__), 'static', 'sujata.jpg')
    _profile_bytes = open(_profile_img_path, 'rb').read() if os.path.isfile(_profile_img_path) else None

    # Load award image for signature
    _award_img_path = os.path.join(os.path.dirname(__file__), 'static', 'Reward.png')
    _award_bytes = open(_award_img_path, 'rb').read() if os.path.isfile(_award_img_path) else None

    try:
        results = send_report_emails(
            generator           = gen,
            sender_email        = _SENDER_EMAIL,
            sender_password     = password,
            lead_recipients     = lead_rec,
            customer_recipients = cust_rec,
            report_file_path    = report_path,
            sheet_link          = sheet_link,
            prev_grand_total    = 0,
            sender_name         = 'Sujata Balasubramanium',
            sender_title        = 'Product Analyst',
            sender_linkedin     = '',
            sender_website      = 'www.wizikey.com',
            sender_email_addr   = _SENDER_EMAIL,
            sender_address      = '3rd floor - Time Square Building - Sushant Lok 1 - Sector 43, Gurugram, 122009',
            profile_image_bytes = _profile_bytes,
            award_image_bytes   = _award_bytes,
        )
    except Exception as e:
        return jsonify({'error': f'Email sending failed: {str(e)}'}), 500

    status_code = 207 if results['errors'] else 200
    return jsonify({
        'status':        'ok' if not results['errors'] else 'partial',
        'lead_sent':     results['lead_sent'],
        'customer_sent': results['customer_sent'],
        'errors':        results['errors'],
    }), status_code


@app.route('/send_email', methods=['POST'])
def send_email():
    """
    Generate report and send Lead / Customer emails.
    Sender is always tushar@wizikey.com.
    Requires: raw_file, customer_file, sender_password, lead_recipients / customer_recipients.
    """
    if 'raw_file' not in request.files or 'customer_file' not in request.files:
        return jsonify({'error': 'raw_file and customer_file are required.'}), 400

    raw_file      = request.files['raw_file']
    customer_file = request.files['customer_file']
    if not raw_file.filename or not customer_file.filename:
        return jsonify({'error': 'No file selected.'}), 400

    sender_password = request.form.get('sender_password', '').strip().replace(' ', '')
    print(f"[SMTP DEBUG] Password received — length: {len(sender_password)} chars (expected 16)")
    if not sender_password:
        return jsonify({'error': 'sender_password is required.'}), 400

    lead_recipients = [e.strip() for e in request.form.get('lead_recipients', '').split(',') if e.strip()]
    cust_recipients = [e.strip() for e in request.form.get('customer_recipients', '').split(',') if e.strip()]
    if not lead_recipients and not cust_recipients:
        return jsonify({'error': 'At least one recipient is required.'}), 400

    try:
        gen             = _build_generator(raw_file, customer_file)
        output_filename = f"Report_web_{datetime.now().strftime('%d-%m-%Y')}.xlsx"
        report_path     = os.path.join(app.config['Result_FOLDER'], output_filename)
        gen.output_file = report_path
        gen.save_report()
    except Exception as e:
        return jsonify({'error': f'Report generation failed: {str(e)}'}), 500

    # Load profile image for signature
    _profile_img_path = os.path.join(os.path.dirname(__file__), 'static', 'sujata_profile.png')
    _profile_bytes = open(_profile_img_path, 'rb').read() if os.path.isfile(_profile_img_path) else None

    # Load award image for signature
    _award_img_path = os.path.join(os.path.dirname(__file__), 'static', 'pr_tech_award.png')
    _award_bytes = open(_award_img_path, 'rb').read() if os.path.isfile(_award_img_path) else None

    try:
        results = send_report_emails(
            generator           = gen,
            sender_email        = _SENDER_EMAIL,
            sender_password     = sender_password,
            lead_recipients     = lead_recipients,
            customer_recipients = cust_recipients,
            report_file_path    = report_path,
            sheet_link          = request.form.get('sheet_link', ''),
            prev_grand_total    = 0,
            sender_name         = 'Sujata Balasubramanium',
            sender_title        = 'Product Analyst',
            sender_linkedin     = '',
            sender_website      = 'www.wizikey.com',
            sender_email_addr   = _SENDER_EMAIL,
            sender_address      = '3rd floor - Time Square Building - Sushant Lok 1 - Sector 43, Gurugram, 122009',
            profile_image_bytes = _profile_bytes,
            award_image_bytes   = _award_bytes,
        )
    except Exception as e:
        return jsonify({'error': f'Email sending failed: {str(e)}'}), 500

    status_code = 207 if results['errors'] else 200
    return jsonify({
        'status':        'ok' if not results['errors'] else 'partial',
        'lead_sent':     results['lead_sent'],
        'customer_sent': results['customer_sent'],
        'errors':        results['errors'],
    }), status_code


@app.route('/api/fetch_news', methods=['POST'])
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
