#!/usr/bin/env python3
"""autoai-optimize demo: scan a website codebase, emit a JSON-LD manifest.

USAGE
    python demo.py <path-to-website-folder> [-o output.json]
    python demo.py --folder <path-to-website-folder> --domain www.example.com

WHAT IT DOES
    Walks the given folder for *.html / *.htm files, runs the autoai-optimize
    classifier + extractor on each, and writes every generated JSON-LD node
    into a single output JSON file. Nothing in your codebase is modified —
    this is a read-only preview of what the middleware WOULD inject.

The output file shape:
    {
      "generated_at": "2026-07-10T...",
      "source": "<the folder you passed>",
      "summary": {"scanned": N, "enriched": M, "skipped": K},
      "pages": [
        {"file": "...", "url": "...", "type": "Article", "jsonld": {...}},
        ...
      ]
    }

    python demo.py sample_site -o website_schemas.json
    python demo.py --folder sample_site --domain www.mysite.com
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

# Make the library importable whether or not it's pip-installed: add the
# project's src/ directory to sys.path when running from a checkout.
_HERE = Path(__file__).resolve().parent
_SRC = _HERE / "src"
if _SRC.is_dir():
    sys.path.insert(0, str(_SRC))

from autoai_optimize import generate_jsonld  # noqa: E402


def discover_html_files(root: Path) -> list[Path]:
    """Find all *.html / *.htm files under `root`, sorted for stable output."""
    return sorted(
        p for p in root.rglob("*") if p.suffix.lower() in {".html", ".htm"} and p.is_file()
    )


def normalize_domain(domain: str | None) -> str | None:
    """Return a normalized https://domain.tld form, or None."""
    if not domain:
        return None
    value = domain.strip()
    if not value:
        return None
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    parsed = urlparse(value)
    host = parsed.netloc or parsed.path
    if not host:
        return None
    return f"{parsed.scheme or 'https'}://{host.rstrip('/')}"


def default_output_filename(domain: str | None) -> str:
    """Choose a default output filename.

    With --domain, produce a readable <site>_schemas.json style name.
    Without --domain, use website_schemas.json for middleware compatibility.
    """
    normalized = normalize_domain(domain)
    if normalized is None:
        return "website_schemas.json"
    host = (urlparse(normalized).netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    labels = [label for label in host.split(".") if label]
    stem = labels[-2] if len(labels) >= 2 else (labels[0] if labels else "website")
    safe = "".join(ch if ch.isalnum() else "_" for ch in stem).strip("_") or "website"
    return f"{safe}_schemas.json"


def file_to_url(root: Path, file_path: Path, domain: str | None = None) -> str:
    """Derive a best-guess URL path from a file's location under `root`.

    Maps index.html -> "/", foo.html -> "/foo", blog/post.html -> "/blog/post".
    Purely for classification hints + the JSON-LD `url` field; not a real
    router.
    """
    rel = file_path.relative_to(root).with_suffix("")
    parts = rel.parts
    if not parts or parts[-1] == "index":
        path = "/" + "/".join(parts[:-1])
    else:
        path = "/" + "/".join(parts)
    path = path or "/"
    normalized = normalize_domain(domain)
    if normalized:
        return f"{normalized}{path}"
    return path


def process_site(root: Path, domain: str | None = None) -> list[dict]:
    """Run generate_jsonld against every HTML file under `root`."""
    pages: list[dict] = []
    for html_file in discover_html_files(root):
        try:
            html = html_file.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            pages.append({"file": str(html_file), "error": f"could not read: {exc}"})
            continue
        url = file_to_url(root, html_file, domain=domain)
        node = generate_jsonld(html, url=url)
        if node is None:
            pages.append(
                {"file": str(html_file), "url": url, "type": None, "jsonld": None}
            )
        else:
            pages.append(
                {
                    "file": str(html_file),
                    "url": url,
                    "type": node.get("@type"),
                    "jsonld": node,
                }
            )
    return pages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan a website codebase and emit an autoai-optimize JSON-LD manifest.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="Folder containing your website HTML files (or use --folder).",
    )
    parser.add_argument(
        "--folder",
        dest="folder",
        help="Alias for path, kept for README/backward compatibility.",
    )
    parser.add_argument(
        "--domain",
        help="Optional domain used to generate absolute URLs (e.g. www.mysite.com).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output JSON file path (default: website_schemas.json or <domain>_schemas.json).",
    )
    args = parser.parse_args(argv)

    input_path = args.path or args.folder
    if not input_path:
        parser.error("Provide a folder path as positional argument or via --folder.")

    root = Path(input_path).expanduser().resolve()
    if not root.is_dir():
        print(f"error: '{root}' is not a directory.", file=sys.stderr)
        return 2

    pages = process_site(root, domain=args.domain)
    enriched = sum(1 for p in pages if p.get("jsonld"))
    skipped = len(pages) - enriched
    type_counts = collections.Counter(
        str(p.get("type")) for p in pages if p.get("type")
    )

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": str(root),
        "summary": {"scanned": len(pages), "enriched": enriched, "skipped": skipped},
        "pages": pages,
    }

    out_name = args.output or default_output_filename(args.domain)
    out_path = Path(out_name).resolve()
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Scanned {len(pages)} HTML file(s) under: {root}")
    print(f"  enriched (JSON-LD generated): {enriched}")
    print(f"  skipped (no confident match): {skipped}")
    if type_counts:
        summary = ", ".join(f"{name}={count}" for name, count in sorted(type_counts.items()))
        print(f"  generated types: {summary}")
    print(f"Wrote manifest -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
