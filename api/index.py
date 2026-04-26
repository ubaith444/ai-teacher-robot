import os
import sys

# Add the 'backend' directory to sys.path so we can import 'app'
path = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, path)

from app.main import app

# Vercel needs the 'app' object
# (Our app is already exported as 'app' in app.main)
