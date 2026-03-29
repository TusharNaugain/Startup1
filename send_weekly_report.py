"""
send_weekly_report.py
=====================
Standalone script to generate and send the weekly usage report email.
NO web form required. Just fill in the CONFIG block below and run:

    python send_weekly_report.py

The script will:
  1. Load your raw PostHog data + customer list
  2. (Optional) Merge in extra Supabase data if SUPABASE_DATA_FILE is set
  3. Generate the full Excel report
  4. Send the formatted HTML email to Lead and/or Customer recipients
"""

import os
import sys
import argparse
import tempfile
import webbrowser
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# ███████╗ ██████╗ ███╗   ██╗███████╗██╗ ██████╗
# ██╔════╝██╔═══██╗████╗  ██║██╔════╝██║██╔════╝
# ██║     ██║   ██║██╔██╗ ██║█████╗  ██║██║  ███╗
# ██║     ██║   ██║██║╚██╗██║██╔══╝  ██║██║   ██║
# ╚██████╗╚██████╔╝██║ ╚████║██║     ██║╚██████╔╝
#  ╚═════╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝     ╚═╝ ╚═════╝
#
# FILL THESE IN ONCE — then just run the script each week.
# ─────────────────────────────────────────────────────────────────────────────

CONFIG = {

    # ── Data Files ──────────────────────────────────────────────────────────
    # Raw PostHog export (.xlsx or .csv). This is the main usage data file.
    "RAW_DATA_FILE": "uploads/posthog_data.xlsx",

    # Customer list file (.xlsx or .csv). Used to tag leads vs customers.
    "CUSTOMER_FILE": "uploads/customers.xlsx",

    # (Optional) Supabase data file (.xlsx or .csv) from your Supabase script.
    # If set, these rows are appended to the raw data before processing.
    # Leave as empty string "" to skip.
    "SUPABASE_DATA_FILE": "",

    # ── SMTP Credentials ────────────────────────────────────────────────────
    # Your Gmail address that sends the email.
    "SENDER_EMAIL": "tushar@wizikey.com",

    # Gmail App Password (16-char). Generate at:
    # https://myaccount.google.com/apppasswords
    # NOTE: This is NOT your regular Gmail password.
    "SENDER_PASSWORD": "xxxx xxxx xxxx xxxx",

    # ── Recipients ──────────────────────────────────────────────────────────
    # List of emails for the Lead Sheet report. Leave [] to skip.
    "LEAD_RECIPIENTS": [
        # "lead-team@yourcompany.com",
        # "manager@yourcompany.com",
    ],

    # List of emails for the Customer Sheet report. Leave [] to skip.
    "CUSTOMER_RECIPIENTS": [
        # "customer-team@yourcompany.com",
    ],

    # ── Report Metadata ─────────────────────────────────────────────────────
    # Google Sheets URL shown as "Refer Here" link. Leave "" to hide it.
    "SHEET_LINK": "",

    # Previous week's grand total (used to compute % change arrow).
    # Set to 0 if you don't have a previous period total.
    "PREV_GRAND_TOTAL": 0,

    # Where to save the generated Excel report file.
    "OUTPUT_REPORT_PATH": "results/weekly_report.xlsx",

    # ── Signature ───────────────────────────────────────────────────────────
    "SENDER_NAME":       "Sujata Balasubramanium",
    "SENDER_TITLE":      "Product Analyst",
    "SENDER_LINKEDIN":   "https://linkedin.com/in/your-profile",
    "SENDER_WEBSITE":    "www.wizikey.com",
    "SENDER_EMAIL_ADDR": "sujata@wizikey.com",
    "SENDER_ADDRESS":    "3rd floor - Time Square Building - Sushant Lok 1 - Sector 43, Gurugram, 122009",

    # ── Signature Images ────────────────────────────────────────────────────
    # Absolute or relative path to profile photo. Leave "" to show grey box.
    "PROFILE_IMAGE_PATH": os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "sujata_profile.png"),

    # Absolute or relative path to award badge image. Leave "" to hide.
    "AWARD_IMAGE_PATH": os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "pr_tech_award.png"),
}

# ─────────────────────────────────────────────────────────────────────────────
# END OF CONFIG — do not edit below this line unless you know what you're doing
# ─────────────────────────────────────────────────────────────────────────────


def validate_config(cfg: dict, preview: bool = False) -> list[str]:
    """Return a list of human-readable error messages for missing/bad config."""
    errors = []

    if not os.path.isfile(cfg["RAW_DATA_FILE"]):
        errors.append(f"RAW_DATA_FILE not found: {cfg['RAW_DATA_FILE']!r}")

    if not os.path.isfile(cfg["CUSTOMER_FILE"]):
        errors.append(f"CUSTOMER_FILE not found: {cfg['CUSTOMER_FILE']!r}")

    if cfg["SUPABASE_DATA_FILE"] and not os.path.isfile(cfg["SUPABASE_DATA_FILE"]):
        errors.append(f"SUPABASE_DATA_FILE not found: {cfg['SUPABASE_DATA_FILE']!r}")

    # SMTP checks only needed when actually sending
    if not preview:
        if not cfg["SENDER_EMAIL"] or "@" not in cfg["SENDER_EMAIL"]:
            errors.append("SENDER_EMAIL is missing or invalid.")

        if not cfg["SENDER_PASSWORD"] or cfg["SENDER_PASSWORD"] == "xxxx xxxx xxxx xxxx":
            errors.append("SENDER_PASSWORD is not set. Generate one at https://myaccount.google.com/apppasswords")

        if not cfg["LEAD_RECIPIENTS"] and not cfg["CUSTOMER_RECIPIENTS"]:
            errors.append("No recipients configured. Add at least one email to LEAD_RECIPIENTS or CUSTOMER_RECIPIENTS.")

    if cfg["PROFILE_IMAGE_PATH"] and not os.path.isfile(cfg["PROFILE_IMAGE_PATH"]):
        errors.append(f"PROFILE_IMAGE_PATH not found: {cfg['PROFILE_IMAGE_PATH']!r}")

    if cfg["AWARD_IMAGE_PATH"] and not os.path.isfile(cfg["AWARD_IMAGE_PATH"]):
        errors.append(f"AWARD_IMAGE_PATH not found: {cfg['AWARD_IMAGE_PATH']!r}")

    return errors


def load_image_bytes(path: str) -> bytes | None:
    """Read an image file and return its bytes, or None if path is empty."""
    if not path:
        return None
    with open(path, "rb") as f:
        return f.read()


def merge_supabase_data(raw_df: pd.DataFrame, supabase_path: str) -> pd.DataFrame:
    """
    Append rows from the Supabase data file into raw_df and return the merged
    DataFrame. Only columns that exist in raw_df are kept from the Supabase
    file to avoid schema mismatches.
    """
    print(f"\n[Supabase] Loading extra data from: {supabase_path!r}")

    if supabase_path.lower().endswith(".csv"):
        try:
            supa_df = pd.read_csv(supabase_path)
        except UnicodeDecodeError:
            supa_df = pd.read_csv(supabase_path, encoding="latin1")
    else:
        supa_df = pd.read_excel(supabase_path, sheet_name=0)

    print(f"[Supabase] Loaded {len(supa_df)} rows with columns: {list(supa_df.columns)}")

    # Only keep columns present in raw_df to avoid merge mismatches
    common_cols = [c for c in supa_df.columns if c in raw_df.columns]
    if not common_cols:
        print("[Supabase] WARNING: No matching columns found — Supabase data will be skipped.")
        return raw_df

    supa_trimmed = supa_df[common_cols].copy()
    merged = pd.concat([raw_df, supa_trimmed], ignore_index=True)
    print(f"[Supabase] Merged successfully → total rows: {len(merged)}")
    return merged


def preview_emails(generator, cfg: dict):
    """
    Renders both Lead and Customer email HTML and opens them in the
    default browser as local temp files — no SMTP, no sending.
    """
    print("\n🔍 Preview mode — opening emails in browser (nothing is sent)...")

    for sheet_type in ["Lead", "Customer"]:
        html = generator.build_email_html(
            sheet_type        = sheet_type,
            sheet_link        = cfg["SHEET_LINK"],
            prev_grand_total  = cfg["PREV_GRAND_TOTAL"],
            sender_name       = cfg["SENDER_NAME"],
            sender_title      = cfg["SENDER_TITLE"],
            sender_linkedin   = cfg["SENDER_LINKEDIN"],
            sender_website    = cfg["SENDER_WEBSITE"],
            sender_email_addr = cfg["SENDER_EMAIL_ADDR"],
            sender_address    = cfg["SENDER_ADDRESS"],
            has_profile_image = bool(cfg["PROFILE_IMAGE_PATH"]),
            has_award_image   = bool(cfg["AWARD_IMAGE_PATH"]),
        )

        # Write to a temp HTML file and open in browser
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=f"_{sheet_type}_email_preview.html",
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(html)
            tmp_path = f.name

        webbrowser.open(f"file://{tmp_path}")
        print(f"   ✅ {sheet_type} email preview opened → {tmp_path}")

    print("\n   Both previews are open in your browser tabs.")
    print("   (Images won't show in preview — they load at send time via inline CID)\n")


def main():
    parser = argparse.ArgumentParser(description="Weekly Usage Report — Email Sender")
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Generate email HTML and open in browser WITHOUT sending. Great for checking layout.",
    )
    args = parser.parse_args()

    cfg = CONFIG

    # ── Step 0: Validate config ──────────────────────────────────────────
    print("=" * 60)
    if args.preview:
        print("  Weekly Usage Report — EMAIL PREVIEW (no send)")
    else:
        print("  Weekly Usage Report — Email Sender")
    print("=" * 60)
    errors = validate_config(cfg, preview=args.preview)
    if errors:
        print("\n❌ CONFIG ERROR(s) — fix these before running:\n")
        for e in errors:
            print(f"   • {e}")
        print()
        sys.exit(1)

    # Import here so validation errors surface first (better UX)
    from generate_report import ReportGenerator, send_report_emails

    # ── Step 1: Load images ──────────────────────────────────────────────
    print("\n[1/5] Loading image assets...")
    profile_bytes = load_image_bytes(cfg["PROFILE_IMAGE_PATH"])
    award_bytes   = load_image_bytes(cfg["AWARD_IMAGE_PATH"])
    print(f"      Profile image : {'✅ loaded' if profile_bytes else '— not set'}")
    print(f"      Award image   : {'✅ loaded' if award_bytes else '— not set'}")

    # ── Step 2: Ensure output directory exists ───────────────────────────
    os.makedirs(os.path.dirname(cfg["OUTPUT_REPORT_PATH"]) or ".", exist_ok=True)

    # ── Step 3: Generate report (with optional Supabase merge) ───────────
    print("\n[2/5] Loading & processing data...")
    generator = ReportGenerator(cfg["RAW_DATA_FILE"], cfg["CUSTOMER_FILE"])
    generator.output_file = cfg["OUTPUT_REPORT_PATH"]

    # Load raw data first so we can optionally merge Supabase data into it
    generator.load_data()

    if cfg["SUPABASE_DATA_FILE"]:
        print("\n[3/5] Merging Supabase data...")
        generator.raw_df = merge_supabase_data(generator.raw_df, cfg["SUPABASE_DATA_FILE"])
    else:
        print("\n[3/5] Supabase merge — skipped (SUPABASE_DATA_FILE not set)")

    print("\n[4/5] Processing & generating report sheets...")
    generator.process_data()
    generator.generate_sheets()

    # ── Preview mode: open HTML in browser and exit ──────────────────────
    if args.preview:
        preview_emails(generator, cfg)
        sys.exit(0)

    saved_path = generator.save_report()
    print(f"      ✅ Report saved → {saved_path}")

    # ── Step 4: Send emails ──────────────────────────────────────────────
    print("\n[5/5] Sending emails...")

    lead_recipients     = cfg["LEAD_RECIPIENTS"]
    customer_recipients = cfg["CUSTOMER_RECIPIENTS"]

    # Safeguard — if no recipients after validation, this line is never reached,
    # but double-check anyway.
    if not lead_recipients and not customer_recipients:
        print("      ⚠️  No recipients configured — skipping email send.")
        sys.exit(0)

    results = send_report_emails(
        generator           = generator,
        sender_email        = cfg["SENDER_EMAIL"],
        sender_password     = cfg["SENDER_PASSWORD"],
        lead_recipients     = lead_recipients,
        customer_recipients = customer_recipients,
        report_file_path    = saved_path,
        sheet_link          = cfg["SHEET_LINK"],
        prev_grand_total    = cfg["PREV_GRAND_TOTAL"],
        sender_name         = cfg["SENDER_NAME"],
        sender_title        = cfg["SENDER_TITLE"],
        sender_linkedin     = cfg["SENDER_LINKEDIN"],
        sender_website      = cfg["SENDER_WEBSITE"],
        sender_email_addr   = cfg["SENDER_EMAIL_ADDR"],
        sender_address      = cfg["SENDER_ADDRESS"],
        profile_image_bytes = profile_bytes,
        award_image_bytes   = award_bytes,
    )

    # ── Step 5: Summary ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  RESULTS")
    print("=" * 60)
    if results["lead_sent"]:
        print(f"  ✅ Lead email sent     → {lead_recipients}")
    elif lead_recipients:
        print(f"  ❌ Lead email FAILED   → {lead_recipients}")

    if results["customer_sent"]:
        print(f"  ✅ Customer email sent → {customer_recipients}")
    elif customer_recipients:
        print(f"  ❌ Customer email FAILED → {customer_recipients}")

    if results["errors"]:
        print("\n  Errors:")
        for err in results["errors"]:
            print(f"    • {err}")

    if not results["errors"]:
        print("\n  🎉 All done! Check your inbox.")
    else:
        print("\n  ⚠️  Some emails failed — see errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
