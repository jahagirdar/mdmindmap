#!/usr/bin/env python3
from __future__ import annotations
import argparse
import hashlib
import json
import os
import pathlib
import sys

from .core import parse_md, set_debug
from .server import serve


def sha256(s: str) -> str:
    import hashlib
    return hashlib.sha256(s.encode()).hexdigest()


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    ap = argparse.ArgumentParser(description="mdmindmap - Markdown mindmap generator with editor integration")
    ap.add_argument("root", help="Root markdown file")
    ap.add_argument("--rebuild", action="store_true", help="Force rebuild cache")
    ap.add_argument("--port", type=int, default=5000, help="Port for the web server")
    ap.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = ap.parse_args(argv)
    set_debug(args.debug)

    root = pathlib.Path(args.root).resolve()
    if not root.exists():
        print("Root markdown not found:", root, file=sys.stderr)
        return 2

    cache_base = pathlib.Path(os.environ.get("XDG_DATA_HOME", pathlib.Path.home()/".local/share")) / "mdmindmap"
    cache_base.mkdir(parents=True, exist_ok=True)

    key = sha256(str(root))
    cachedir = cache_base / key
    cachedir.mkdir(parents=True, exist_ok=True)
    cache_json = cachedir / f"{key}.json"
    out_html = cachedir / f"{key}.html"

    # rebuild if requested or cache missing
    if args.rebuild or not cache_json.exists():
        print("Parsing markdown files...")
        data = parse_md(str(root), set())
        if not data:
            print("Parsing produced no data.", file=sys.stderr)
            return 1
        with open(cache_json, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

        # minimal HTML template
        html_template = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>mdmindmap</title>
  <script src="https://d3js.org/d3.v7.min.js"></script>
  <style>
    body {{ font-family: sans-serif; margin:0; overflow:hidden; }}
    svg {{ width:100%; height:100vh; }}
    .node circle {{
      fill: #999;
      stroke: #000;
      stroke-width: 1.5px;
    }}
    .node text {{
      font-size: 14px;
      cursor: pointer;
      user-select: none;
    }}
    .link {{
      fill: none;
      stroke: #555;
      stroke-width: 1.5px;
    }}
    .icon {{
      font-size: 12px;
      cursor: pointer;
      fill: #007acc;
      margin-left: 4px;
    }}
    #preview {{
      position: absolute;
      top: 10px;
      right: 10px;
      width: 400px;
      height: 90%;
      overflow: auto;
      border: 1px solid #aaa;
      background: #fff;
      padding: 8px;
      font-size: 14px;
      display: none;
    }}
  </style>
</head>
<body>
  <svg></svg>
  <div id="preview"></div>
  <script>
    const svg = d3.select("svg"),
          g = svg.append("g").attr("transform", "translate(40,40)");

    const zoom = d3.zoom().on("zoom", (event) => {{
      g.attr("transform", event.transform);
    }});
    svg.call(zoom);

    fetch("/data").then(r => r.json()).then(data => {{
      const root = d3.hierarchy(data);
      const treeLayout = d3.tree().nodeSize([30, 180]);
      treeLayout(root);

      // Draw links
      g.selectAll(".link")
        .data(root.links())
        .enter().append("path")
        .attr("class", "link")
        .attr("d", d3.linkHorizontal()
          .x(d => d.y)
          .y(d => d.x));

      // Draw nodes
      const node = g.selectAll(".node")
        .data(root.descendants())
        .enter().append("g")
        .attr("class", "node")
        .attr("transform", d => `translate(${{d.y}},${{d.x}})`);

      node.append("circle").attr("r", 6);

      // text label
      node.append("text")
        .attr("dy", 3)
        .attr("x", 10)
        .text(d => d.data.title || d.data.name)
        .on("mouseover", (event,d) => {{
            fetch('/reload?path=' + encodeURIComponent(d.data.path))
              .then(r => r.json())
              .then(content => {{
                document.getElementById("preview").style.display = "block";
                document.getElementById("preview").innerText = JSON.stringify(content,null,2);
              }});
        }})
        .on("mouseout", () => {{
            document.getElementById("preview").style.display = "none";
        }});

      // edit icon
      node.append("text")
        .attr("class","icon")
        .attr("x", d => 12 + (d.data.title||d.data.name).length * 7)
        .attr("dy", 3)
        .text("✎")
        .on("click", (event,d) => {{
          fetch('/edit?path=' + encodeURIComponent(d.data.path));
        }});

      // reload icon
      node.append("text")
        .attr("class","icon")
        .attr("x", d => 28 + (d.data.title||d.data.name).length * 7)
        .attr("dy", 3)
        .text("⟳")
        .on("click", (event,d) => {{
          fetch('/reload?path=' + encodeURIComponent(d.data.path))
            .then(r => r.json())
            .then(content => {{
              alert("Reloaded: " + d.data.title);
            }});
        }});
    }});
  </script>
</body>
</html>"""

        with open(out_html, "w", encoding="utf-8") as fh:
            fh.write(html_template)

    else:
        with open(cache_json, "r", encoding="utf-8") as fh:
            data = json.load(fh)

    # Start server (this blocks)
    serve(data, str(out_html), port=args.port)

