#!/usr/bin/env python3
"""page_view.py 1.00: read a saved Confluence page (html, detail=full) without loading the ID labels.

  page_view.py view FILE [SECTION]    the page (or one section, by its heading) as plain text, no IDs
  page_view.py ids FILE KEY [KEY...]  the IDs to target: table rows by first cell (:first and
                                      :last give a table's first and last data row), lines by
                                      their text (a heading also gives the line after it)
  page_view.py diff OLD NEW           what changed between two saved reads (removed, added,
                                      changed, moved, and format: same text, other marks,
                                      links or attributes)
  page_view.py meta FILE              version, snapshot token and title of a saved read,
                                      or of a saved update response
  page_view.py node FILE ID           the exact html of one node, to copy into a replaceNode value
  page_view.py textdiff A B           the lines whose text differs between two reads, ignoring IDs,
                                      marks and attributes: for a page against its draft, whose
                                      IDs are different ("same text" when they match)
  page_view.py risks FILE             what Atlassian's open bugs can change on any write: tables
                                      with a left or centre layout, non-breaking spaces, fragment links

FILE is the html body, or the tool's saved JSON response that contains it.
Exit codes: 0 ok, 1 usage, 2 key, ID or section not found (or ambiguous), 3 the file is missing or holds no page.
Read-only: stdlib only, no network, writes nothing.
"""
import json
import re
import sys
from collections import Counter
from difflib import SequenceMatcher, unified_diff
from html.parser import HTMLParser

LINE_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre", "summary", "figcaption"}
PREFIX = {"pre": "code: ", "summary": "expand: ", "figcaption": "caption: ", "div": "macro: "}
VOID = {"br", "hr", "img", "input"}
NO_TEXT = {"hr", "img", "figure", "iframe", "video", "audio"}
MEDIA_TYPES = ("media", "block-card", "embed-card", "sync-block", "bodied-sync-block")


class NoPage(Exception):
    pass


def find_key(obj, name):
    if isinstance(obj, dict):
        if name in obj:
            return obj[name]
        obj = list(obj.values())
    if isinstance(obj, list):
        for v in obj:
            hit = find_key(v, name)
            if hit is not None:
                return hit
    return None


def unwrap(data):
    """A saved tool result can hold the response as JSON text: [{"type": "text", "text": "{...}"}]."""
    if find_key(data, "body") is not None:
        return data
    for v in data.values() if isinstance(data, dict) else data:
        for x in v.values() if isinstance(v, dict) else [v]:
            if isinstance(x, str) and x.lstrip()[:1] in ("{", "["):
                try:
                    return json.loads(x)
                except ValueError:
                    pass
    return data


def load_json(path):
    raw = open(path, encoding="utf-8").read()
    if raw.lstrip()[:1] in "{[":
        try:
            return raw, unwrap(json.loads(raw))
        except ValueError:
            pass
    return raw, None


def check_error(data):
    if find_key(data, "ok") is False:
        raise NoPage(f"error response: {find_key(data, 'reason') or find_key(data, 'error') or 'ok: false'}")


def load_html(path):
    raw, data = load_json(path)
    if data is None:
        return raw
    check_error(data)
    body = find_key(data, "body")
    if isinstance(body, dict) and isinstance(body.get("value"), str):
        return body["value"]
    found = []

    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str) and "<" in x:
            found.append(x)
    walk(data)
    if found:
        return max(found, key=len)
    raise NoPage("the JSON response holds no page html")


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks, self.table, self.row, self.cell, self.line = [], None, None, None, None
        self.depth, self.skip, self.lists, self.links, self.details = 0, 0, [], [], ""

    def new_line(self, tag, lid, text=None):
        if tag == "summary" and not lid:
            lid = self.details
        marker = "-"
        if tag == "li" and self.lists:
            self.lists[-1][1] += 1
            marker = f"{self.lists[-1][1]}." if self.lists[-1][0] == "ol" else "-"
        self.line = {"kind": "line", "tag": tag, "id": lid, "text": text or [],
                     "level": max(len(self.lists), 1), "marker": marker}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        lid = a.get("data-local-id", "")
        if tag == "table":
            self.depth += 1
            if self.depth == 1:
                self.table = {"kind": "table", "id": lid, "rows": []}
        elif self.depth == 1 and tag == "tr":
            self.row = {"id": lid, "cells": [], "header": False}
        elif self.depth == 1 and tag in ("td", "th") and self.row is not None:
            self.cell = []
            self.row["header"] = self.row["header"] or tag == "th"
        elif tag == "time":
            self.add(a.get("datetime", ""))
            self.skip += 1
        elif tag == "br":
            self.add(" ")
        elif tag == "a":
            self.links.append(a.get("href", ""))
        elif tag == "input" and a.get("type") == "checkbox":
            self.add("[x] " if "checked" in a else "[ ] ")
        elif self.depth == 0 and tag == "details":
            self.details = lid
        elif self.depth == 0 and tag in ("ul", "ol"):
            self.lists.append([tag, int(a["start"]) - 1 if tag == "ol" and str(a.get("start", "")).isdigit() else 0])
        elif self.depth == 0 and tag == "div" and a.get("data-type") == "extension" and self.line is None:
            self.new_line("div", lid, [f"[{a.get('data-extension-key', '')}] "])
        elif self.depth == 0 and tag in LINE_TAGS:
            if self.line is not None and tag == "li":
                self.end_line()
            if self.line is None:
                self.new_line(tag, lid)
            elif not self.line["id"]:
                self.line["id"] = lid
            elif self.line["tag"] == "li" and tag == "p" and lid and not self.line.get("pid"):
                self.line["pid"] = lid

    def handle_endtag(self, tag):
        if tag in ("p", "li", "td", "th"):
            self.add(" ")
        if tag == "table":
            if self.depth == 1 and self.table is not None:
                self.blocks.append(self.table)
                self.table = None
            self.depth = max(0, self.depth - 1)
        elif self.depth == 1 and tag in ("td", "th") and self.cell is not None:
            self.row["cells"].append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif self.depth == 1 and tag == "tr" and self.row is not None:
            self.table["rows"].append(self.row)
            self.row = None
        elif tag == "time":
            self.skip = max(0, self.skip - 1)
        elif tag == "a" and self.links:
            href = self.links.pop()
            if href:
                self.add(f" ({href})")
        elif self.depth == 0 and tag in ("ul", "ol"):
            if self.lists:
                self.lists.pop()
        elif self.depth == 0 and self.line is not None and tag == self.line["tag"]:
            self.end_line()

    def end_line(self):
        self.line["text"] = " ".join("".join(self.line["text"]).split())
        if self.line["text"]:
            self.blocks.append(self.line)
        self.line = None

    def handle_data(self, data):
        if not self.skip:
            self.add(data)

    def add(self, text):
        if self.cell is not None:
            self.cell.append(text)
        elif self.line is not None and self.depth == 0:
            self.line["text"].append(text)
        elif self.depth == 0 and self.lists and text.strip():
            self.line = {"kind": "line", "tag": "li", "id": "", "text": [text], "level": len(self.lists), "marker": "-"}


def parse(path):
    p = Page()
    p.feed(load_html(path))
    p.close()
    if not p.blocks:
        raise NoPage("no page content in the file")
    return p.blocks


def section(blocks, name):
    for i, b in enumerate(blocks):
        if b["kind"] == "line" and b["tag"][0] == "h" and b["text"].lower() == name.lower():
            level, out = int(b["tag"][1]), [b]
            for nb in blocks[i + 1:]:
                if nb["kind"] == "line" and nb["tag"][0] == "h" and int(nb["tag"][1]) <= level:
                    break
                out.append(nb)
            return out
    return None


def show(block):
    if block["kind"] == "line":
        tag = block["tag"]
        if tag == "li":
            prefix = "  " * (block["level"] - 1) + block["marker"] + " "
        elif tag[0] == "h":
            prefix = "#" * int(tag[1]) + " "
        else:
            prefix = PREFIX.get(tag, "")
        return prefix + block["text"]
    out = []
    for r in block["rows"]:
        out.append("| " + " | ".join(r["cells"]) + " |")
        if r["header"]:
            out.append("|" + " --- |" * len(r["cells"]))
    return "\n".join(out)


def items(blocks):
    out, noid = {}, 0
    for n, b in enumerate(blocks):
        if b["kind"] == "line":
            noid += not b["id"]
            out[b["id"] or f"line-{n}"] = b["text"]
        else:
            for m, r in enumerate(b["rows"]):
                noid += not r["id"]
                out[r["id"] or f"row-{n}-{m}"] = "| " + " | ".join(r["cells"]) + " |"
    if noid:
        print(f"warning: {noid} item(s) without an ID, compared by position", file=sys.stderr)
    return out


def cell_key(cell):
    """A first cell without its link: "ABC-2 (https://...)" gives ABC-2, a bare smart link its URL's last part."""
    m = re.fullmatch(r"(.*?)\s*\((\S+)\)", cell)
    if not m:
        return cell
    return m.group(1) or re.split(r"[?#]", m.group(2))[0].rstrip("/").rsplit("/", 1)[-1]


def node_html(html, lid):
    key = f'data-local-id="{lid}"'
    i = html.find(key)
    if i < 0 or html.find(key, i + 1) >= 0:
        return None
    start = html.rfind("<", 0, i)
    tag = re.match(r"<([a-zA-Z0-9]+)", html[start:start + 20]).group(1)
    end = html.find(">", i)
    if tag.lower() in VOID or html[end - 1] == "/":
        return html[start:end + 1]
    depth = 0
    for m in re.compile(rf"<(/?){tag}(?=[\s>/])", re.I).finditer(html, start):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return html[start:html.find(">", m.end()) + 1]
    return None


def open_tag(html, lid):
    i = html.find(f'data-local-id="{lid}"')
    return html[html.rfind("<", 0, i):html.find(">", i) + 1] if i >= 0 else ""


def tag_text(tag, attrs):
    return "<" + tag + "".join(f" {k}={v!r}" for k, v in sorted(attrs) if k != "data-local-id") + ">"


class Canon(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []

    def handle_starttag(self, tag, attrs):
        self.out.append(tag_text(tag, attrs))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        self.out.append(data)


def canon(html):
    c = Canon()
    c.feed(html or "")
    c.close()
    return "".join(c.out)


class Marks(HTMLParser):
    """Nodes that hold no text, so comparing lines and rows cannot see them."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found = Counter()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if (tag in NO_TEXT or str(a.get("data-type", "")).startswith(MEDIA_TYPES)
                or (tag == "table" and not a.get("data-local-id"))):
            self.found[tag_text(tag, attrs)] += 1


def marks(html):
    m = Marks()
    m.feed(html)
    m.close()
    return m.found


def risks(html):
    counts = ((len(re.findall(r'<table\b[^>]*\bdata-layout="(?:align-start|center)"', html)), "table(s) with a left or centre layout"),
              (len(re.findall("&nbsp;|&#160;|&#[xX][aA]0;|\u00a0", html)), "non-breaking space(s)"),
              (len(re.findall(r'<a\b[^>]*\bhref="#', html)), "fragment link(s)"))
    return [f"{n}\t{what}" for n, what in counts if n]


def main(argv):
    if (len(argv) < 3 or argv[1] not in ("view", "ids", "diff", "meta", "node", "textdiff", "risks")
            or (argv[1] in ("ids", "diff", "node", "textdiff") and len(argv) < 4)):
        print(__doc__)
        return 1
    cmd = argv[1]
    try:
        return run(cmd, argv)
    except (NoPage, OSError, UnicodeDecodeError) as e:
        print(f"NO PAGE: {e}", file=sys.stderr)
        return 3


def run(cmd, argv):
    if cmd == "meta":
        _, data = load_json(argv[2])
        if data is None:
            raise NoPage("meta needs the tool's saved JSON response, not bare html")
        check_error(data)
        version = find_key(data, "version")
        version = version.get("number") if isinstance(version, dict) else version
        snap = find_key(data, "snapshot")
        token = (snap.get("token") if isinstance(snap, dict) else None) or find_key(data, "snapshotToken")
        print(f"version\t{version}\ntoken\t{token}\ntitle\t{find_key(data, 'title')}")
        return 0
    if cmd == "node":
        found = node_html(load_html(argv[2]), argv[3])
        print(found if found else f"{argv[3]}\tNOT FOUND (or not unique)")
        return 0 if found else 2
    if cmd == "risks":
        found = risks(load_html(argv[2]))
        print("\n".join(found) if found else "no known risks")
        return 0
    if cmd == "view":
        blocks = parse(argv[2])
        if len(argv) > 3:
            same = [b for b in blocks if b["kind"] == "line" and b["tag"][0] == "h" and b["text"].lower() == argv[3].lower()]
            if len(same) > 1:
                print(f"{argv[3]}\tAMBIGUOUS: {len(same)} headings")
                return 2
            blocks = section(blocks, argv[3])
            if blocks is None:
                print(f"{argv[3]}\tNOT FOUND")
                return 2
        print("\n".join(show(b) for b in blocks))
        return 0
    if cmd == "ids":
        blocks, status = parse(argv[2]), 0
        for key in argv[3:]:
            hits = []
            for n, b in enumerate(blocks):
                if b["kind"] == "table" and key in (":first", ":last"):
                    data = [r for r in b["rows"] if not r["header"]]
                    if data:
                        r = data[0] if key == ":first" else data[-1]
                        hits.append(f"{key}\trow\t{r['id']}\t{(r['cells'] or [''])[0]}")
                elif b["kind"] == "table":
                    hits += [f"{key}\trow\t{r['id']}" for r in b["rows"] if r["cells"] and key in (r["cells"][0], cell_key(r["cells"][0]))]
                elif key not in (":first", ":last") and (b["text"] == key or b["text"].startswith(key + ":") or b["text"].startswith(key + " ")):
                    pid = f"\tparagraph inside: {b['pid']}" if b.get("pid") else ""
                    hits.append(f"{key}\tline\t{b['id']}\t{b['text'][:60]}{pid}")
                    nxt = blocks[n + 1] if n + 1 < len(blocks) else None
                    if b["tag"][0] == "h" and nxt and nxt["kind"] == "line":
                        hits.append(f"{key}\tnext line\t{nxt['id']}\t{nxt['text'][:60]}")
            if not hits or len([h for h in hits if "\tnext line\t" not in h]) > 1:
                status = 2
            print("\n".join(hits) if hits else f"{key}\tNOT FOUND")
        return status
    if cmd == "textdiff":
        a = "\n".join(show(b) for b in parse(argv[2])).split("\n")
        b = "\n".join(show(x) for x in parse(argv[3])).split("\n")
        out = [l for l in unified_diff(a, b, "A", "B", lineterm="", n=0) if not l.startswith(("---", "+++", "@@"))]
        print("\n".join(out) if out else "same text")
        print(f"{len(out)} line(s) differ")
        return 0
    ob, nb = parse(argv[2]), parse(argv[3])
    old, new = items(ob), items(nb)
    diffs = [f"removed\t{k}\t{old[k]}" for k in old if k not in new]
    diffs += [f"added\t{k}\t{new[k]}" for k in new if k not in old]
    diffs += [f"changed\t{k}\t{old[k]}  ->  {new[k]}" for k in old if k in new and old[k] != new[k]]
    a, b = [k for k in old if k in new], [k for k in new if k in old]
    kept = {k for blk in SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks() for k in a[blk.a:blk.a + blk.size]}
    diffs += [f"moved\t{k}\t{new[k]}" for k in b if k not in kept]
    oh, nh = load_html(argv[2]), load_html(argv[3])
    touched = [d.split("\t")[1] for d in diffs]
    for k in a:
        if old[k] != new[k] or k.startswith(("line-", "row-")):
            continue
        x, y = node_html(oh, k), node_html(nh, k)
        if x and y and canon(x) != canon(y) and not any(f'"{t}"' in x + y for t in touched):
            diffs.append(f"format\t{k}\t{new[k][:80]}")
    tables = {t["id"] for t in ob if t["kind"] == "table" and t["id"]} & {t["id"] for t in nb if t["kind"] == "table" and t["id"]}
    diffs += [f"format\t{t}\ttable attributes" for t in tables if canon(open_tag(oh, t)) != canon(open_tag(nh, t))]
    mo, mn = marks(oh), marks(nh)
    diffs += [f"removed\t-\t{k}" for k in (mo - mn).elements()]
    diffs += [f"added\t-\t{k}" for k in (mn - mo).elements()]
    if not diffs and re.sub(r">\s+<", "><", canon(oh)) != re.sub(r">\s+<", "><", canon(nh)):
        diffs.append("format\t-\tthe html differs outside every line and row")
    print("\n".join(diffs) if diffs else "no differences")
    print(f"{len(diffs)} difference(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
