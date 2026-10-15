import re
import urllib.request
from pathlib import Path

req = urllib.request.Request(
    "http://bp3street.com/bp3l.html",
    headers={"User-Agent": "Mozilla/5.0"},
)
with urllib.request.urlopen(req, timeout=20) as response:
    text = response.read().decode("cp932", errors="replace")

links = re.findall(
    r'<A[^>]+href="([^"]+)"[^>]*>\s*(?:<IMG[^>]+src="([^"]+)"[^>]*>)?',
    text,
    re.I,
)
lines = [f"{img} -> {href}" for href, img in links]
out = Path(__file__).with_name("_bp3links.txt")
out.write_text("\n".join(lines), encoding="utf-8")
print(f"links {len(lines)} -> {out}")
