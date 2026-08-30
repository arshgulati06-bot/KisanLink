"""
Development entry point.

    python run.py

For production use a WSGI server instead, e.g.
    gunicorn "run:app" --bind 0.0.0.0:5000
"""
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_ENV", "development") != "production"
    print(f"KisanLink API starting on http://0.0.0.0:{port} (debug={debug})")
    app.run(host="0.0.0.0", port=port, debug=debug)
