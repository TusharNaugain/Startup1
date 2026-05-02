import sys
import os

# Add project root to path so we can import app.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402

# Vercel's @vercel/python builder looks for a WSGI callable named `app`
