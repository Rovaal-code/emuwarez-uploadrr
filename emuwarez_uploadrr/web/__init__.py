"""Web backend package for eMuwarez Uploadrr.

Install web dependencies:
    pip install -e ".[web]"

Start the server:
    python3 emuwarez_uploader.py web serve --port 9494
    uvicorn emuwarez_uploadrr.web.app:app --host 0.0.0.0 --port 9494
"""
