import os
import re
import pathlib
from typing import Optional, Tuple
from urllib.parse import urlparse, unquote

import yaml
import markdown as _md

# Supported markdown file extensions we will try for bare links
MD_EXTS = (".md", ".markdown", ".mdx")

# Markdown link pattern: [text](target)
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
DEBUG = False

def set_debug(flag: bool):
    global DEBUG
    DEBUG = flag

def _dbg(*args):
    if DEBUG:
        print("[mdmindmap:debug]", *args)

def parse_frontmatter(text: str) -> Tuple[dict, str]:
    """
    If text starts with YAML frontmatter (--- ... ---), return (fm_dict, body).
    Otherwise return ({}, full_text).
    """
    # Use a robust regex to capture frontmatter block
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, flags=re.DOTALL)
    if m:
        fm_text = m.group(1)
        body = m.group(2)
        try:
            fm = yaml.safe_load(fm_text) or {}
        except Exception:
            fm = {}
        return fm, body
    return {}, text

def extract_links(mdtext: str):
    return [(m.group(1), m.group(2)) for m in LINK_RE.finditer(mdtext)]

def render_html(mdtext: str) -> str:
    """Render markdown to HTML for tooltips / previews."""
    return _md.markdown(mdtext, extensions=["tables", "fenced_code"])

def _case_insensitive_existing(path: str) -> Optional[str]:
    """
    If path exists return it; otherwise try to find a case-insensitive match
    for the basename in the same directory and return that path.
    """
    if os.path.exists(path):
        return os.path.abspath(path)
    d = os.path.dirname(path)
    b = os.path.basename(path)
    if not os.path.isdir(d):
        return None
    try:
        for entry in os.listdir(d):
            if entry.lower() == b.lower():
                cand = os.path.join(d, entry)
                if os.path.exists(cand):
                    return os.path.abspath(cand)
    except PermissionError:
        return None
    return None

def resolve_link(base_file: str, link: str) -> Optional[str]:
    """
    Resolve a link relative to base_file.
    Handles:
      - absolute/relative paths
      - bare names => try adding .md/.markdown/.mdx
      - directory -> index.md variants
      - strips fragments/queries
      - returns absolute path to existing file or None
    """
    p = urlparse(link)
    # treat http, mailto, etc. as external
    if p.scheme and p.netloc:
        return None

    raw_rel = unquote((p.path or "")).strip()
    if not raw_rel:
        return None

    base_dir = os.path.dirname(base_file)
    raw_abs = os.path.abspath(os.path.join(base_dir, raw_rel))

    candidates = [raw_abs]
    # if no extension, try typical md extensions
    if not os.path.splitext(raw_abs)[1]:
        for e in MD_EXTS:
            candidates.append(raw_abs + e)
    # if it is a directory (or looks like one), look for index.md
    if os.path.isdir(raw_abs) or raw_abs.endswith(os.sep):
        for e in MD_EXTS:
            candidates.append(os.path.join(raw_abs, "index" + e))

    for c in candidates:
        hit = _case_insensitive_existing(c)
        if hit and os.path.splitext(hit)[1].lower() in MD_EXTS:
            return os.path.abspath(hit)

    return None

def is_external_link(link: str) -> bool:
    p = urlparse(link)
    return bool(p.scheme and p.netloc)

def _read_file_text(path: str) -> Optional[str]:
    try:
        return open(path, encoding="utf-8").read()
    except Exception:
        return None

def parse_md(path: str, seen: set, link_text: Optional[str] = None) -> Optional[dict]:
    """
    Parse a markdown file into a node dict:
      { "id": absolute_path, "title": ..., "content": rendered_html, "children": [...] }

    `link_text` is the text from the parent link (e.g. [Label](file.md)). If provided,
    it is used as the title when the target file has no frontmatter title.
    `seen` prevents infinite recursion; if a path is already in `seen` we return a
    lightweight node (no recursion), but still attempt to read its frontmatter title.
    """
    path = str(pathlib.Path(path).resolve())
    _dbg(f"Parsing {path!r} (link_text={link_text!r})")

    text = _read_file_text(path)
    if text is None:
        return None

    fm, body = parse_frontmatter(text)
    fm_title = (fm or {}).get("title")

    # Determine node title: prefer frontmatter, then link_text, then filename stem
    if fm_title:
        title = str(fm_title)
        _dbg(f"Title from frontmatter: {title}")
    elif link_text:
        title = str(link_text)
        _dbg(f"Title from link text: {title}")
    else:
        # filename without extension
        title = pathlib.Path(path).stem
        _dbg(f"Title from filename stem: {title}")

    # Prepare content preview (rendered HTML of body)
    html_preview = render_html(body)

    node = {
        "id": path,
        "title": title,
        "content": html_preview,
        "children": []
    }

    # If we've already visited this file (cycle), do not recurse into children.
    if path in seen:
        return node

    # Mark visited and traverse links in the BODY (frontmatter stripped)
    seen.add(path)

    for link_label, link_target in extract_links(body):
        # external links -> leaf node
        if is_external_link(link_target):
            node["children"].append({
                "id": link_target,
                "title": (link_label or link_target),
                "content": f"<i>External link: {link_target}</i>",
                "children": []
            })
            continue

        resolved = resolve_link(path, link_target)
        _dbg(f"Link: '{link_label}' -> '{link_target}' | resolved={resolved}")
        if resolved:
            # Pass the link_label so the child's title can use it if frontmatter title missing
            child = parse_md(resolved, seen, link_text=link_label)
            if child:
                # Ensure we prefer the child's own frontmatter title if present.
                # The recursive call already applied the rule, but if child has no fm-title
                # it will have used link_text; that is what the user wants.
                node["children"].append(child)
            else:
                # Could not parse child for some reason; add fallback node
                node["children"].append({
                    "id": resolved,
                    "title": (link_label or pathlib.Path(resolved).stem),
                    "content": "<i>Could not load</i>",
                    "children": []
                })
        else:
            # unresolved internal-looking link -> show label if present
            node["children"].append({
                "id": link_target,
                "title": (link_label or link_target),
                "content": f"<i>Unresolved link: {link_target}</i>",
                "children": []
            })

    return node
