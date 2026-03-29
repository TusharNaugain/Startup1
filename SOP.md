# Standard Operating Procedure (SOP) - Liberty Application

This document outlines the standard procedures for installing, running, and using the Liberty application suite.

## 1. Prerequisites & Installation

### System Requirements
- OS: Windows 10/11, macOS, or Linux
- Python 3.8 or higher installed
- Internet connection (for Google News fetching)

### Initial Setup
1.  **Extract the Package**: Unzip the `Liberty` folder to your desired location.
2.  **Open Terminal**: Open Command Prompt (Windows) or Terminal (Mac/Linux) and navigate to the folder:
    ```bash
    cd path/to/Liberty
    ```
3.  **Install Dependencies**: Run the following command to install required libraries:
    ```bash
    pip install -r requirements.txt
    ```
    *(Note: If `pip` is not recognized, try `pip3` or `python -m pip`)*

## 2. Running the Application

1.  **Start the Server**:
    In the terminal within the `Liberty` folder, run:
    ```bash
    python app.py
    ```
    *(Or `python3 app.py` on Mac/Linux)*
2.  **Access the Dashboard**:
    Open your web browser (Chrome recommended) and go to:
    `http://127.0.0.1:5000`

## 3. Workflow Procedures

### A. Generating the Excel Report
**Goal**: Create a daily usage report merged with customer data.

1.  Navigate to **"Excel Automater"** in the dashboard.
2.  **Upload Files**:
    -   **Raw Data**: Select the latest usage export (Excel/CSV).
    -   **Customer List**: Select the updated customer email list.
3.  Click **"Process & Download"**.
4.  **Result**: The tool will download `Report_[filename].xlsx`.
    -   Check "Lead Sheet" for potential new leads.
    -   Check "Other Insights" (last sheet) for Top 3 New & Top 2 Returning free users highlight.

### B. Fetching News
**Goal**: Get recent news articles for a brand or topic.

1.  Navigate to **"News Extractor"**.
2.  **Enter Details**:
    -   **Topic**: Keyword (e.g., "CompetitorName" or "Industry Trend").
    -   **Start Date**: The beginning of the period.
    -   **End Date**: The end of the period.
3.  Click **"Fetch News"**.
4.  **Review**: View results on-screen or copy them directly.

### C. Analyzing Headlines (Smart Classifier)
**Goal**: Categorize a bulk list of headlines into industry buckets.

1.  Navigate to **"Smart Classifier"**.
2.  **Upload**: Select your Excel/CSV file containing headlines.
3.  **Settings**:
    -   **Column Name**: (Optional) Specify if the column isn't named "Headline".
    -   **Industry**: Select target industry (e.g., "Automotive", "BFSI").
4.  Click **"Classify"**.
5.  **Result**: Download the classified Excel file containing:
    -   `assigned_bucket`: The category (e.g., "Product Launch").
    -   `is_relevant`: True/False.
    -   `matched_keywords`: What triggered the match.
    -   **Note**: The tool auto-filters duplicates.

### D. Checking Link Relevance
**Goal**: Verify a list of URLs against specific keywords.

1.  Navigate to **"Headline Analyzer"** (or Link Checker tool if separated).
2.  *Note: Currently this runs via backend script or specified UI route if enabled.*
3.  **Alternative (Script Check)**:
    -   Place a text file with URLs in `input_data` folder.
    -   Run `python link_checker.py`.
    -   Check `output_data/link_report.csv`.

## 4. Troubleshooting
-   **"Module Not Found" Error**: Re-run `pip install -r requirements.txt`.
-   **"403 Forbidden" in News Fetching**: The tool handles this automatically, but if it persists, wait a few minutes as Google might be rate-limiting.
-   **Excel File Error**: Ensure the file is not open in Excel while the tool is trying to write or read it. Close the file and try again.
