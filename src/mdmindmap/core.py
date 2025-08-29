import os
import re
import pathlib
from typing import Optional, Tuple
from urllib.parse import urlparse, unquote

import yaml
import markdown as _md

MD_EXTS = (".md", ".markdown", ".mdx")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

DEBUG = False
def set_debug(v: bool):
    global DEBUG
    DEBUG = bool(v)
def _dbg(*a):
    if DEBUG:
        print("[mdmindmap:debug]", *a)

def parse_frontmatter(text: str) -> Tuple[dict, str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, flags=re.DOTALL)
    if m:
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except Exception:
            fm = {}
        return fm, m.group(2)
    return {}, text

def extract_links(mdtext: str):
    return [(m.group(1), m.group(2)) for m in LINK_RE.finditer(mdtext)]

def render_html(mdtext: str) -> str:
    # rendered HTML for tooltip/preview
    try:
        return _md.markdown(mdtext, extensions=["tables", "fenced_code"])
    except Exception:
        return "<pre>" + (mdtext[:10000] if mdtext else "") + "</pre>"

def _case_insensitive_existing(path: str) -> Optional[str]:
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
    p = urlparse(link)
    if p.scheme and p.netloc:
        return None
    raw_rel = unquote((p.path or "")).strip()
    if not raw_rel:
        return None
    base_dir = os.path.dirname(base_file)
    raw_abs = os.path.abspath(os.path.join(base_dir, raw_rel))
    candidates = [raw_abs]
    if not os.path.splitext(raw_abs)[1]:
        for e in MD_EXTS:
            candidates.append(raw_abs + e)
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

def _read_text(path: str) -> Optional[str]:
    try:
        return open(path, encoding="utf-8").read()
    except Exception:
        return None

def parse_md(path: str, seen: set, link_text: Optional[str] = None) -> Optional[dict]:
    """
    Returns node dict:
      { "path": abs_path, "name": basename, "title": label, "content": rendered_html, "children": [...] }
    """
    path = str(pathlib.Path(path).resolve())
    _dbg("parse_md called for", path, "link_text=", link_text)
    text = _read_text(path)
    if text is None:
        _dbg("cannot read", path)
        return None

    fm, body = parse_frontmatter(text)
    fm_title = (fm or {}).get("title")
    if fm_title:
        title = str(fm_title)
        _dbg("title from frontmatter:", title)
    elif link_text:
        title = str(link_text)
        _dbg("title from link text:", title)
    else:
        title = pathlib.Path(path).stem
        _dbg("title from filename stem:", title)

    node = {
        "path": path,
        "name": pathlib.Path(path).name,
        "title": title,
        "content": render_html(body),
        "children": []
    }

    # avoid infinite recursion but still return node title
    if path in seen:
        _dbg("cycle detected:", path)
        return node

    seen.add(path)

    for link_label, link_target in extract_links(body):
        if is_external_link(link_target):
            node["children"].append({
                "path": link_target,
                "name": link_target,
                "title": link_label or link_target,
                "content": f"<i>External: {link_target}</i>",
                "children": []
            })
            continue

        resolved = resolve_link(path, link_target)
        _dbg("link:", link_label, "->", link_target, "resolved:", resolved)
        if resolved:
            child = parse_md(resolved, seen, link_text=link_label)
            if child:
                node["children"].append(child)
            else:
                node["children"].append({
                    "path": resolved,
                    "name": pathlib.Path(resolved).name,
                    "title": link_label or pathlib.Path(resolved).stem,
                    "content": "<i>Could not load</i>",
                    "children": []
                })
        else:
            node["children"].append({
                "path": link_target,
                "name": link_target,
                "title": link_label or link_target,
                "content": f"<i>Unresolved: {link_target}</i>",
                "children": []
            })

    return node
