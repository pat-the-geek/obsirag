from __future__ import annotations

import json


def build_mermaid_html_document(code: str, idx: int) -> str:
    """Build a standalone Mermaid HTML document for iframe rendering."""
    code_json = json.dumps(code)

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body  {{ background: #16213E; padding: 12px; }}
    #out  {{ display: flex; justify-content: center; align-items: flex-start; }}
    #out svg {{ max-width: 100%; height: auto; }}
    #err  {{ color: #F87171; font-family: monospace; font-size: 12px;
             white-space: pre-wrap; padding: 8px;
             background: #1f1f2e; border-radius: 4px; }}
  </style>
</head>
<body>
  <div id="out"></div>
  <div id="err"></div>
  <script>
    (async function() {{
      const code = {code_json};
      try {{
        mermaid.initialize({{
          startOnLoad: false,
          theme: 'dark',
          securityLevel: 'loose',
          fontFamily: 'ui-sans-serif, system-ui, sans-serif',
          fontSize: 14
        }});
        const {{ svg }} = await mermaid.render('mg{idx}', code);
        document.getElementById('out').innerHTML = svg;
      }} catch(e) {{
        document.getElementById('err').textContent =
          '⚠ Erreur Mermaid\\n' + e.message + '\\n\\n' + code;
      }}
    }})();
  </script>
</body>
</html>"""


def estimate_mermaid_height(code: str) -> int:
    lines = len(code.strip().splitlines())
    return max(200, min(600, 120 + lines * 22))