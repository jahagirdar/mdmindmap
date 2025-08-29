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
    ap = argparse.ArgumentParser(description="mdmindmap - Markdown mindmap generator")
    ap.add_argument("root", help="Root markdown file")
    ap.add_argument("--rebuild", action="store_true", help="Force rebuild cache")
    ap.add_argument("--port", type=int, default=5000, help="Port for the web server")
    ap.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = ap.parse_args(argv)

    set_debug(args.debug)

    root = pathlib.Path(args.root).resolve()
    if not root.exists():
        print("Root not found:", root, file=sys.stderr); return 2

    cache_base = pathlib.Path(os.environ.get("XDG_DATA_HOME", pathlib.Path.home()/".local/share")) / "mdmindmap"
    cache_base.mkdir(parents=True, exist_ok=True)

    key = sha256(str(root))
    cachedir = cache_base / key
    cachedir.mkdir(parents=True, exist_ok=True)
    cache_json = cachedir / f"{key}.json"
    out_html = cachedir / f"{key}.html"

    if args.rebuild or not cache_json.exists():
        print("Parsing markdown files...")
        data = parse_md(str(root), set())
        if not data:
            print("No data produced", file=sys.stderr); return 1
        with open(cache_json, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

        # write cleaned-up HTML (based on the snippet you provided)
        html_template = """<!DOCTYPE html>
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>mdmindmap</title>
  <script src="https://d3js.org/d3.v7.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <style>
    body { font-family: sans-serif; margin: 0; }
    svg { width: 100%; height: 100vh; cursor: grab; }
    .node circle {
      fill: #999;
      stroke: #000;
      stroke-width: 1.5px;
    }
    .node text {
      font-size: 14px;
      cursor: pointer;
      dominant-baseline: middle;
    }
    .link {
      fill: none;
      stroke: #555;
      stroke-width: 1.5px;
    }
    .tooltip {

  position: absolute;
  background: #fff;
  border: 1px solid #ccc;
  padding: 6px;
  font-size: 13px;
  max-width: 600px;      /* initial max width */
  max-height: 400px;     /* initial max height */
  overflow: auto;
  pointer-events: auto;   /* allow scrolling and interaction */
  box-shadow: 2px 2px 6px rgba(0,0,0,0.2);
  white-space: pre-wrap;
  display: none;
  resize: both;           /* allow resizing in both directions */
    }
    .icon {
      font-size: 12px;
      margin-right: 3px;
      cursor: pointer;
      vertical-align: middle;
    }
    .icon:hover { opacity: 0.7; }
  </style>
</head>
<body>
  <svg></svg>
  <div class="tooltip"></div>
  <script>
    const svg = d3.select("svg"),
          g = svg.append("g").attr("transform", "translate(100,100)");

    const tooltip = d3.select(".tooltip");

    // enable pan + zoom
    const zoom = d3.zoom()
      .scaleExtent([0.3, 3])
      .on("zoom", (event) => g.attr("transform", event.transform));
    svg.call(zoom);

    // reset zoom on double-click background
    svg.on("dblclick.zoom", null);
    svg.on("dblclick", () => {
      svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity);
    });

    fetch("/data").then(r => r.json()).then(data => {
      const root = d3.hierarchy(data);

      if(root.children) root.children.forEach(collapse);
      update(root);

      function collapse(d) {
        if(d.children) {
          d._children = d.children;
          d._children.forEach(collapse);
          d.children = null;
        }
      }

      function update(source) {
        const treeLayout = d3.tree().nodeSize([40, 200]);
        treeLayout(root);

        const nodes = root.descendants();
        const links = root.links();

        const x0 = d3.min(nodes, d => d.x) - 50;
        const x1 = d3.max(nodes, d => d.x) + 50;
        const y1 = d3.max(nodes, d => d.y) + 200;
        svg.attr("viewBox", [0, x0, y1, x1 - x0 + 200]);

        const link = g.selectAll(".link")
          .data(links, d => d.target.data.path);

        link.enter().append("path")
          .attr("class", "link")
          .merge(link)
          .attr("d", d3.linkHorizontal()
            .x(d => d.y)
            .y(d => d.x));
        link.exit().remove();

        const node = g.selectAll(".node")
          .data(nodes, d => d.data.path);

        const nodeEnter = node.enter().append("g")
          .attr("class", "node")
          .attr("transform", d => `translate(${d.y},${d.x})`)
          .on("click", (event, d) => {
            if(d.children) { d._children = d.children; d.children = null; }
            else { d.children = d._children; d._children = null; }
            update(d);
          })
          .on("mouseover", (event, d) => {
            if(!d.data.path) return;
            fetch(`/reload?path=${encodeURIComponent(d.data.path)}`)
              .then(r => r.json())
              .then(fileData => {
                tooltip.style("display", "block")
                       .style("left", (event.pageX + 10) + "px")
                       .style("top", (event.pageY + 10) + "px")
                       .html(marked.parse(fileData.content));
              });
          })
          .on("mousemove", (event) => {
            tooltip.style("left", (event.pageX + 10) + "px")
                   .style("top", (event.pageY + 10) + "px");
          });

        nodeEnter.append("circle").attr("r", 6);

        // emoji icons before text
        nodeEnter.append("foreignObject")
          .attr("x", 10)
          .attr("y", -10)
          .attr("width", 50)
          .attr("height", 20)
          .append("xhtml:div")
          .html(d => d.data.path ? `
            <span class="icon" onclick="fetch('/edit?path=${encodeURIComponent(d.data.path)}')">✏️</span>
            <span class="icon" onclick="fetch('/reload?path=${encodeURIComponent(d.data.path)}').then(()=>location.reload())">🔄</span>
          ` : "");

        nodeEnter.append("text")
          .attr("dy", 4)
          .attr("x", 60)
          .text(d => d.data.title || d.data.name);

        node.exit().remove();
      }
    });

    // keep tooltip visible if mouse enters it
    tooltip.on("mouseleave", () => tooltip.style("display", "none"));
  </script>
</body>
</html>


"""

        with open(out_html, "w", encoding="utf-8") as fh:
            fh.write(html_template)
    else:
        with open(cache_json, "r", encoding="utf-8") as fh:
            data = json.load(fh)

    serve(data, str(out_html), port=args.port)

if __name__ == "__main__":
    raise SystemExit(main())
