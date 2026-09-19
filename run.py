"""
Entry point for the Marketing ROI Intelligence Platform.

Local development:
    python run.py

Production (recommended):
    gunicorn run:app
"""

import os

from backend.app import create_app

app = create_app(os.environ.get("FLASK_ENV", "development"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=app.config.get("DEBUG", True))
