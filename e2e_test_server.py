"""
Full Pipeline E2E Test Server for AutoAI-Optimize v1.0.3
=========================================================
This FastAPI server serves real HTML pages from sample_site/ with the
AutoAI-Optimize middleware applied. Open your browser and view-source
to see the injected JSON-LD that AI agents will read.

USAGE:
    pip install autoai-optimize uvicorn
    python e2e_test_server.py

Then visit:
    http://localhost:8000/                              → Homepage (skipped, no schema)
    http://localhost:8000/blog/why-fast-apis-matter     → Article JSON-LD injected!
    http://localhost:8000/shop/product/widget-pro-3000  → Product JSON-LD injected!
    http://localhost:8000/api/ai                        → Full JSON manifest (if enabled)
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

# ---- Import the library exactly as a real user would after `pip install` ----
from autoai_optimize.frameworks.fastapi import AutoAIMiddleware
from autoai_optimize.config import Config

# ---- App Setup ----
app = FastAPI(title="AutoAI-Optimize E2E Test")

# Configure middleware with security and the AI endpoint enabled
config = Config(
    deny_paths=("/admin/", "/private/"),
    serve_ai_endpoint=True,       # Enable /api/ai manifest endpoint
    ai_endpoint_key=None,         # No auth for local testing
)

app.add_middleware(AutoAIMiddleware, config=config)

# ---- Routes: serve real HTML files from sample_site/ ----
SITE_ROOT = Path(__file__).parent / "sample_site"


@app.get("/", response_class=HTMLResponse)
async def homepage():
    """Homepage — should be classified as UNKNOWN (no schema injected)."""
    return (SITE_ROOT / "index.html").read_text(encoding="utf-8")


@app.get("/blog/why-fast-apis-matter", response_class=HTMLResponse)
async def blog_article():
    """Blog article — should get Article JSON-LD injected into <head>."""
    return (SITE_ROOT / "blog" / "why-fast-apis-matter.html").read_text(encoding="utf-8")


@app.get("/shop/product/widget-pro-3000", response_class=HTMLResponse)
async def product_page():
    """Product page — should get Product JSON-LD injected into <head>."""
    return (SITE_ROOT / "shop" / "product" / "widget-pro-3000.html").read_text(encoding="utf-8")


# ---- Run the server ----
if __name__ == "__main__":
    import uvicorn

    print("\n" + "=" * 60)
    print("  AutoAI-Optimize v1.0.3 — Full Pipeline E2E Test Server")
    print("=" * 60)
    print("\n  Open these URLs in your browser and View Page Source:")
    print("    http://localhost:8000/                              → Homepage (no schema)")
    print("    http://localhost:8000/blog/why-fast-apis-matter     → Article JSON-LD ✅")
    print("    http://localhost:8000/shop/product/widget-pro-3000  → Product JSON-LD ✅")
    print("    http://localhost:8000/api/ai                        → Full AI Manifest ✅")
    print("\n  Press Ctrl+C to stop.\n")

    uvicorn.run(app, host="127.0.0.1", port=8000)
