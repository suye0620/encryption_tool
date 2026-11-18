#!/usr/bin/env python3
"""Download pinned platform wheels from TUNA, verify against PyPI metadata."""
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple/pyrage/"
METADATA = "https://pypi.org/pypi/pyrage/1.4.0/json"

class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = {}
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href", "")
            self.links[unquote(urlsplit(href).path.rsplit("/", 1)[-1])] = urljoin(INDEX, href).split("#")[0]

def main():
    with urlopen(METADATA, timeout=60) as response:
        metadata = json.load(response)
    with urlopen(INDEX, timeout=60) as response:
        links = Links()
        links.feed(response.read().decode())
    wheelhouse = ROOT / "wheelhouse"
    wheelhouse.mkdir(exist_ok=True)
    records = []
    for record in metadata["urls"]:
        name = record["filename"]
        if not name.endswith(".whl"):
            continue
        expected = record["digests"]["sha256"]
        target = wheelhouse / name
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == expected:
            print("Verified cached:", name)
        else:
            if name not in links.links:
                raise RuntimeError("TUNA mirror missing wheel: " + name)
            try:
                with urlopen(links.links[name], timeout=120) as response:
                    data = response.read()
            except Exception as exc:
                print(f"Mirror unavailable ({exc}); using official PyPI artifact: {name}")
                with urlopen(record["url"], timeout=120) as response:
                    data = response.read()
                links.links[name] = record["url"]
            if hashlib.sha256(data).hexdigest() != expected:
                raise RuntimeError("SHA256 mismatch: " + name)
            target.write_bytes(data)
            print("Downloaded and verified:", name)
        records.append({"filename": name, "sha256": expected, "size": record["size"], "source": links.links.get(name), "official_metadata": METADATA})
    (wheelhouse / "provenance.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    (wheelhouse / "SHA256SUMS").write_text("".join(f'{r["sha256"]}  {r["filename"]}\n' for r in records), encoding="ascii")
    print(f"Verified {len(records)} wheels; requires_dist={metadata['info']['requires_dist']}")

if __name__ == "__main__":
    main()
