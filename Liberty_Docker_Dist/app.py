from flask import Flask, render_template, request, jsonify
from link_checker import DataFetcher, DataProcessor
from news_extractor import fetch_google_news
import concurrent.futures
import os
import uuid  # Added missing import
from werkzeug.utils import secure_filename
from flask import send_file
from flask import send_file, send_from_directory
from generate_report import ReportGenerator
import pandas as pd
import re
import io # Added for BytesIO # Added missing import
# Add Matching folder to path to import components
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Matching')))
from classifier_engine import HeadlineClassifier, Deduplicator, INDUSTRY_CONFIG

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['Result_FOLDER'] = 'results'

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

@app.route('/smart_classifier')
def smart_classifier():
    return render_template('smart_classifier.html', industry_config=INDUSTRY_CONFIG)

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

@app.route('/api/fetch_news', methods=['POST'])
def api_fetch_news():
    data = request.json
    topic = data.get('topic')
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    
    if not topic:
         return jsonify({"error": "Topic is required"}), 400
         
    try:
        articles = fetch_google_news(topic, start_date, end_date)
        return jsonify({"articles": articles})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.json
    keywords = data.get('keywords', [])
    context_keywords = data.get('context_keywords', []) # New field
    links = data.get('links', [])
    
    if not keywords or not links:
        return jsonify({"error": "Missing keywords or links"}), 400
        
    results = []
    
    # Use threading for faster processing
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(process_single_link, url, keywords, context_keywords): url for url in links}
        for future in concurrent.futures.as_completed(future_to_url):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                # Handle unexpected errors gracefully
                results.append({
                    "URL": future_to_url[future],
                    "Status": "Error",
                    "Match Count": 0,
                    "Found Keywords": f"System Error: {str(e)}"
                })
                
    return jsonify({"results": results})

def process_single_link(url, keywords, context_keywords):
    # Reuse our existing robust logic
    response = fetcher.fetch_content(url)
    
    if not isinstance(response, str):
        text = processor.extract_text(response.content)
        # Pass context keywords to the logic
        status, count, found = processor.analyze_relevance(text, keywords, context_keywords)
        return {
            "URL": url,
            "Status": status,
            "Match Count": count,
            "Found Keywords": ", ".join(found) if found else ""
        }
    else:
        return {
            "URL": url,
            "Status": "Missing",
            "Match Count": 0,
            "Found Keywords": ""
        }

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
        sheet_name = request.form.get('sheet_name', '').strip()
        
        # Determine file type and read accordingly
        filename = file.filename.lower()
        if filename.endswith('.xlsx') or filename.endswith('.xls'):
            try:
                # If sheet_name is provided, use it; otherwise default (None = first sheet)
                sheet_to_read = sheet_name if sheet_name else 0
                df = pd.read_excel(file, sheet_name=sheet_to_read)
            except ValueError as ve:
                # This error usually occurs if the sheet name is not found
                # Re-read to get available sheet names for the error message
                try:
                    xl = pd.ExcelFile(file)
                    return render_template('headline_analyzer.html', 
                                         error=f"Sheet '{sheet_name}' not found. Available sheets: {', '.join(xl.sheet_names)}")
                except:
                     return render_template('headline_analyzer.html', error=f"Invalid sheet name: {str(ve)}")
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

@app.route('/process_classification', methods=['POST'])
def process_classification():
    try:
        if 'file' not in request.files:
            return render_template('smart_classifier.html', error="No file part", industry_config=INDUSTRY_CONFIG)
        
        file = request.files['file']
        if file.filename == '':
             return render_template('smart_classifier.html', error="No selected file", industry_config=INDUSTRY_CONFIG)

        selected_industry = request.form.get('industry', 'Automotive').strip()
        headline_col_name = request.form.get('headline_col', '').strip()
        sheet_name = request.form.get('sheet_name', '').strip() # User override for single sheet
        
        all_results = []
        
        # Helper to process a single file/dataframe
        def process_dataframe(df, industry, forced_bucket=None, forced_bucket_id=0):
            # Normalize cols
            df.columns = df.columns.str.strip()
            
            target_col = None
            if headline_col_name and headline_col_name in df.columns:
                target_col = headline_col_name
            else:
                 # Auto-detect
                 lower_cols = df.columns.str.lower()
                 possible = ['headline', 'title', 'news', 'article']
                 for p in possible:
                     for col in df.columns:
                         if p in col.lower():
                             target_col = col
                             break
                     if target_col: break
            
            if not target_col:
                return None, f"Could not find headline column. Available: {', '.join(df.columns)}"
            
            # Drop empty rows
            df = df.dropna(subset=[target_col])
            headlines = df[target_col].astype(str).tolist()
            
            # --- Phase 1: Deduplication ---
            deduplicator = Deduplicator(similarity_threshold=0.85)
            dedupe_results = deduplicator.process(headlines)
            
            dedupe_df = pd.DataFrame(dedupe_results)
            
            # Merge dedupe info back to main DF
            # Reset index to ensure alignment if dropna changed things
            df = df.reset_index(drop=True) 
            # (Note: Deduplicator returns list matching input 'headlines' len, which matches df len after dropna)
            
            df['is_master'] = dedupe_df['is_master']
            df['master_headline'] = dedupe_df['master_headline']
            df['similarity_score'] = dedupe_df['similarity_score']
            df['duplicacy_count'] = dedupe_df['duplicacy_count']
            
            # --- Phase 2: Classification ---
            classifier = HeadlineClassifier(industry=industry)
            
            classification_results = []
            
            # Optimization: If forced_bucket is known, avoid scanning all buckets
            target_patterns = None
            if forced_bucket and forced_bucket in classifier.compiled_buckets:
                target_patterns = classifier.compiled_buckets[forced_bucket]

            for index, row in df.iterrows():
                text_to_classify = row['master_headline']
                
                if forced_bucket:
                    # Optimized Path: check ONLY the forced bucket for reasoning
                    classification = {
                        "text": text_to_classify,
                        "is_relevant": True, # Trust user assignment ALWAYS
                        "assigned_bucket": forced_bucket,
                        "bucket_id": forced_bucket_id if forced_bucket_id > 0 else 999,
                        "reasoning": "User Assigned Bucket via Sheet Name",
                        "confidence_score": 1.0 # Trust user assignment
                    }
                    
                    if target_patterns:
                        g1_match = target_patterns['group1'].search(str(text_to_classify))
                        g2_match = target_patterns['group2'].search(str(text_to_classify))
                        if g1_match and g2_match:
                             g1_found = g1_match.group(1)
                             g2_found = g2_match.group(1)
                             classification["reasoning"] = f"Found '{g1_found}' (G1) AND '{g2_found}' (G2)"
                else:
                    # Standard Full Scan
                    classification = classifier.classify(text_to_classify)
                
                classification_results.append(classification)
                
            class_df = pd.DataFrame(classification_results)
            
            df['is_relevant'] = class_df['is_relevant']
            df['assigned_bucket'] = class_df['assigned_bucket']
            df['bucket_id'] = class_df['bucket_id']
            df['matched_keywords'] = class_df['reasoning']
            df['confidence_score'] = class_df['confidence_score']
            
            return df, None

        # --- EXECUTION STRATEGY ---
        
        # 1. Resolve Industry Key in Config
        industry_key = None
        for key in INDUSTRY_CONFIG.keys():
            if selected_industry.lower() in key.lower() or key.lower() in selected_industry.lower():
                industry_key = key
                break
        
        buckets_config = INDUSTRY_CONFIG.get(industry_key, {}) if industry_key else {}
        
        final_df_list = []
        is_multi_sheet_processed = False
        
        # 2. Check File Type
        filename = file.filename.lower()
        if filename.endswith(('.xlsx', '.xls')):
            # It's Excel. Check sheets.
            try:
                # Read into memory to ensure seekable stream for ExcelFile
                file.seek(0)
                file_bytes = io.BytesIO(file.read())
                xl = pd.ExcelFile(file_bytes)
                sheet_names = xl.sheet_names
                
                # Filter if user specified a sheet (Fix for "Only one bucket per sheet")
                if sheet_name and sheet_name in sheet_names:
                    sheet_names = [sheet_name]
                
                # Filter sheets that match buckets?
                # or process ALL sheets?
                # User Requirement: "7 sheets are there who represents the page.. we have to do it"
                # Strategy: Try to match sheet name to bucket.
                
                # Create ordered list of buckets for k1-k7 mapping
                ordered_buckets = list(buckets_config.keys())
                
                # ID Mapping for buckets
                bucket_id_map = {name: i+1 for i, name in enumerate(ordered_buckets)}
                
                for sheet in sheet_names:
                    matched_bucket = None
                    matched_bucket_id = 0
                    
                    sheet_clean = sheet.strip().lower()
                    
                    # 1. Check for k1-k7 pattern
                    k_match = re.match(r'^k([1-7])$', sheet_clean)
                    if k_match:
                        try:
                            idx = int(k_match.group(1)) - 1
                            if 0 <= idx < len(ordered_buckets):
                                matched_bucket = ordered_buckets[idx]
                                matched_bucket_id = bucket_id_map[matched_bucket]
                        except:
                            pass
                    
                    # 2. If no k-match, try Fuzzy match
                    if not matched_bucket:
                        for bucket in buckets_config.keys():
                            bucket_clean = bucket.strip().lower()
                            
                            # Basic substring match
                            if sheet_clean in bucket_clean or bucket_clean in sheet_clean:
                                matched_bucket = bucket
                                matched_bucket_id = bucket_id_map.get(bucket, 999)
                                break
                            
                            # Split bucket into sub-phrases
                            sub_phrases = [p.strip() for p in re.split(r'[,&]', bucket_clean) if len(p.strip()) > 3]
                            for phrase in sub_phrases:
                                if phrase in sheet_clean:
                                    matched_bucket = bucket
                                    matched_bucket_id = bucket_id_map.get(bucket, 999)
                                    break
                            if matched_bucket: break
                    
                    if matched_bucket:
                        # Process this sheet as this bucket
                        # Use xl.parse() for speed (avoids re-opening stream)
                        print(f"Processing sheet '{sheet}' as bucket '{matched_bucket}'")
                        try:
                            df = xl.parse(sheet)
                            processed_df, err = process_dataframe(df, selected_industry, forced_bucket=matched_bucket, forced_bucket_id=matched_bucket_id)
                            if not err:
                                final_df_list.append(processed_df)
                                is_multi_sheet_processed = True
                            else:
                                print(f"Error processing sheet {sheet}: {err}")
                        except Exception as e:
                             print(f"Error parsing sheet {sheet}: {e}")

                    else:
                        # Sheet didn't match a bucket. 
                        pass
                
                # If we processed at least one sheet via matching, great.
                if not is_multi_sheet_processed:
                    # Fallback: Process First Sheet (or specified sheet) normally
                    target_sheet = sheet_name if sheet_name else 0
                    print(f"No bucket-matched sheets found. Falling back to simple classification on sheet: {target_sheet}")
                    df = xl.parse(target_sheet) # Use parse here too
                    processed_df, err = process_dataframe(df, selected_industry)
                    if err: return render_template('smart_classifier.html', error=err, industry_config=INDUSTRY_CONFIG)
                    final_df_list.append(processed_df)
                    
            except Exception as e:
                return render_template('smart_classifier.html', error=f"Error reading Excel: {str(e)}", industry_config=INDUSTRY_CONFIG)
                
        else:
            # CSV - Single File Auto Classify
            try:
                df = pd.read_csv(file) # might need encoding handling
            except:
                file.seek(0)
                df = pd.read_csv(file, encoding='latin1')
            
            processed_df, err = process_dataframe(df, selected_industry)
            if err: return render_template('smart_classifier.html', error=err, industry_config=INDUSTRY_CONFIG)
            final_df_list.append(processed_df)

        # --- AGGREGATION ---
        
        if not final_df_list:
             return render_template('smart_classifier.html', error="No valid data found to process.", industry_config=INDUSTRY_CONFIG)
             
        master_df = pd.concat(final_df_list, ignore_index=True)

        # --- FILTERING & RESPONSE ---

        
        # Filter: Only matches (bucket_id > 0) AND (Master rows OR duplicates of valid masters)
        raw_matches_df = master_df[(master_df['bucket_id'] > 0) & (master_df['is_master'] == True)].copy()
        
        # --- Apply "Top 3 per Bucket" Rule ---
        # Sort by Duplicacy Count (Highest First)
        raw_matches_df.sort_values(by=['assigned_bucket', 'duplicacy_count'], ascending=[True, False], inplace=True)
        
        # Group by bucket and take top 10
        matched_results_df = raw_matches_df.groupby('assigned_bucket').head(10)
        
        # Use first filename or a generic name
        base_filename = secure_filename(file.filename)
        output_filename = f"Classified_{base_filename}"
        if not output_filename.endswith('.xlsx'):
             output_filename = os.path.splitext(output_filename)[0] + '.xlsx'
        
        output_path = os.path.join(app.config['Result_FOLDER'], output_filename)
        matched_results_df.to_excel(output_path, index=False)
        
        matches_to_display = matched_results_df.to_dict('records')
        bucket_stats = raw_matches_df['assigned_bucket'].value_counts().to_dict()
        
        return render_template('smart_classifier.html', 
                               matches=matches_to_display, 
                               total_matches=len(matched_results_df),
                               result_file=output_filename,
                               headline_col='headline', # Just default for now since we normalized
                               bucket_stats=bucket_stats,
                               industry_config=INDUSTRY_CONFIG)

    except Exception as e:
        return render_template('smart_classifier.html', error=str(e), industry_config=INDUSTRY_CONFIG)

if __name__ == '__main__':
    # Host 0.0.0.0 is required for Docker containers to be accessible from outside
    app.run(host='0.0.0.0', port=5000, debug=True)
