#!/usr/bin/env python3
"""Bind gallery pixels to the adjacent feedback key, retaining exact labels."""
import base64
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
from recover import CORPUS, HERE, ROOT


class Gallery(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.image = None
        self.srcdoc = None
        self.cards = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "img" and a.get("src", "").startswith("data:image/"):
            self.image = a["src"]
        if tag == "iframe" and "srcdoc" in a:
            self.srcdoc = a["srcdoc"]
        if tag == "textarea" and a.get("data-fb") and not a["data-fb"].endswith("overall"):
            self.cards.append((a["data-fb"], self.image, self.srcdoc))
            self.image, self.srcdoc = None, None


def main():
    recovery = json.loads((HERE / "recovery.json").read_text())
    key_map = {
        "lib-atlas": "library-E", "lib-herbarium": "library-D", "lib-seedbank": "library-C", "lib-ledger": "library-A", "lib-null": "library-B",
        "eng-watchlog": "engine-D", "eng-null": "engine-C", "eng-checklist": "engine-B", "eng-nightlog": "engine-A", "eng-timetable": "engine-E",
    }
    groups = {"lib": "concept2", "eng": "concept2", "l3": "lib3", "l4": "lib4", "e3": "eng3", "e5": "eng5", "e6": "eng6", "e7": "eng7"}
    output = []
    for gallery in recovery["galleries"]:
        parser = Gallery()
        parser.feed((ROOT / gallery["archive"]).read_text())
        feedback = next(f for f in recovery["feedback"] if f.get("url") == gallery["url"])
        for key, image, srcdoc in parser.cards:
            prefix, name = key.split("-", 1)
            group = groups[prefix]
            name = key_map.get(key, name)
            row = {"id": f"{group}/{name}", "key": key, "round": group, "name": name,
                   "quote": feedback["state"]["feedback"].get(key), "source": {"gallery_sha256": gallery["sha256"], "gallery_url": gallery["url"], "transcript_line": feedback["line"], "submitted_at": feedback["state"].get("submitted_at")}}
            if image:
                header, encoded = image.split(",", 1)
                ext = ".png" if "image/png" in header else ".jpg"
                target = CORPUS / group / "gallery-renders" / (name + ext)
                raw = base64.b64decode(encoded, validate=True)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
                row["image"] = str(target.relative_to(ROOT))
                row["image_sha256"] = hashlib.sha256(raw).hexdigest()
            if srcdoc:
                target = CORPUS / group / "gallery-html" / (name + ".html")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(srcdoc)
                row["html"] = str(target.relative_to(ROOT))
            else:
                target = CORPUS / group / (name + ".html")
                if group == "concept2":
                    target = CORPUS / group / ("library" if prefix == "lib" else "engine") / (key.split("-", 1)[1] + ".html")
                if target.exists():
                    row["html"] = str(target.relative_to(ROOT))
                    row["html_provenance"] = "Latest successful Write/Edit recovered from transcript; not assumed pixel-identical"
            output.append(row)
    (HERE / "gallery-corpus.json").write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"cards": len(output), "images": sum("image" in r for r in output), "html": sum("html" in r for r in output)}))


if __name__ == "__main__":
    main()
