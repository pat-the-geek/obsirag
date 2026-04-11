from __future__ import annotations

import base64
import json


def build_mermaid_fullscreen_html(code: str, idx: int) -> str:
    """Build the standalone fullscreen Mermaid viewer used by the chat."""
    code_json = json.dumps(code)
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Diagramme — ObsiRAG</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/svg-pan-zoom@3.6.1/dist/svg-pan-zoom.min.js"></script>
<style>
  *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
  html,body{{width:100%;height:100%;overflow:hidden;background:#1e1e1e;color:#d4d4d4}}
  @media(prefers-color-scheme:light){{html,body{{background:#ffffff;color:#1a1a1a}}}}
  #toolbar{{
    position:fixed;top:0;left:0;right:0;z-index:100;
    display:flex;align-items:center;gap:8px;padding:7px 16px;
    background:rgba(37,37,38,0.95);border-bottom:1px solid #3e3e42;
    font-family:'Consolas','Menlo',monospace;font-size:12px;color:#d4d4d4;
  }}
  @media(prefers-color-scheme:light){{
    #toolbar{{background:rgba(247,247,247,0.97);border-color:#e2e2e2;color:#1a1a1a}}
  }}
  #toolbar .logo{{font-weight:700;color:#569cd6;margin-right:4px}}
  @media(prefers-color-scheme:light){{#toolbar .logo{{color:#0066b8}}}}
  #toolbar .hint{{opacity:0.45;font-size:10px;margin-left:auto}}
  #container{{position:absolute;inset:0;top:40px}}
  #container svg{{position:absolute;inset:0;width:100%;height:100%;display:block}}
  #err{{position:fixed;top:50px;left:50%;transform:translateX(-50%);
        color:#f87171;font-size:12px;z-index:30;text-align:center}}
  #loading{{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;
            background:#1e1e1e;z-index:50;font-size:13px;opacity:0.7}}
  @media(prefers-color-scheme:light){{#loading{{background:#ffffff}}}}
</style>
</head>
<body>
<div id="toolbar">
  <span class="logo">ObsiRAG</span>
  <span style="opacity:.35">—</span>
  <span>Diagramme</span>
  <span class="hint">🖱 molette = zoom · glisser = déplacer · dbl-clic = ajuster</span>
</div>
<div id="loading">Rendu en cours…</div>
<div id="container"></div>
<div id="err"></div>
<script>
(function(){{
  'use strict';
  var CODE={code_json};
  var isDark=!window.matchMedia('(prefers-color-scheme:light)').matches;
  var TV_LIGHT={{
    fontFamily:"system-ui,-apple-system,'Segoe UI',Helvetica,Arial,sans-serif",fontSize:'14px',
    background:'#ffffff',
    primaryColor:'#dbeafe',primaryTextColor:'#1a1a1a',
    primaryBorderColor:'#0066b8',lineColor:'#0066b8',
    secondaryColor:'#ffedd5',tertiaryColor:'#ede9fe',
    mainBkg:'#dbeafe',nodeBorder:'#0066b8',
    clusterBkg:'#f0f4ff',clusterBorder:'#d97706',
    titleColor:'#7c3aed',
    edgeLabelBackground:'#ffffff'
  }};
  var TV_DARK={{
    fontFamily:"system-ui,-apple-system,'Segoe UI',Helvetica,Arial,sans-serif",fontSize:'14px',
    background:'#0d1117',
    primaryColor:'#1f3a5f',primaryTextColor:'#e6edf3',
    primaryBorderColor:'#58a6ff',lineColor:'#58a6ff',
    secondaryColor:'#431407',tertiaryColor:'#2d1b52',
    mainBkg:'#1f3a5f',nodeBorder:'#58a6ff',
    clusterBkg:'#161b22',clusterBorder:'#a371f7',
    titleColor:'#a371f7',
    edgeLabelBackground:'#0d1117'
  }};

  mermaid.initialize({{
    startOnLoad:false,securityLevel:'loose',theme:'base',
    themeVariables:isDark?TV_DARK:TV_LIGHT
  }});

  mermaid.render('diag_{idx}',CODE).then(function(r){{
    var loading=document.getElementById('loading');
    if(loading)loading.remove();
    var container=document.getElementById('container');
    container.innerHTML=r.svg;
    var svgEl=container.querySelector('svg');
    if(!svgEl)return;
    if(!svgEl.getAttribute('viewBox'))
      svgEl.setAttribute('viewBox','0 0 '+(parseFloat(svgEl.getAttribute('width'))||800)+' '+(parseFloat(svgEl.getAttribute('height'))||600));
    svgEl.removeAttribute('width');svgEl.removeAttribute('height');
    svgEl.style.cssText='position:absolute;inset:0;width:100%;height:100%;display:block;';
    setTimeout(function(){{
      var pz=svgPanZoom(svgEl,{{
        zoomEnabled:true,panEnabled:true,controlIconsEnabled:true,
        fit:true,center:true,minZoom:0.02,maxZoom:80,zoomScaleSensitivity:0.3,dblClickZoomEnabled:false
      }});
      pz.resize();pz.fit();pz.center();
      window.addEventListener('resize',function(){{pz.resize();pz.fit();pz.center();}});
      document.addEventListener('dblclick',function(e){{if(!e.target.closest('#toolbar')){{pz.resize();pz.fit();pz.center();}}}})
    }},120);
  }}).catch(function(e){{
    var loading=document.getElementById('loading');
    if(loading)loading.remove();
    document.getElementById('err').textContent='⚠ '+e.message;
  }});
}})();
</script>
</body>
</html>"""


def build_mermaid_chat_preview_html(code: str, idx: int) -> str:
    """Build the inline Mermaid preview used inside the chat."""
    code_json = json.dumps(code)
    fullscreen_b64 = base64.b64encode(
        build_mermaid_fullscreen_html(code, idx).encode("utf-8")
    ).decode("ascii")
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<style>
  *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:transparent;padding:2px 0}}
  #out{{display:flex;justify-content:center;cursor:zoom-in;border-radius:6px;overflow:hidden}}
  #out svg{{max-width:100%;height:auto;border-radius:6px}}
  #err{{color:#F87171;font-family:monospace;font-size:11px;white-space:pre-wrap;padding:4px}}
  #hint{{font-size:10px;text-align:center;margin-top:4px;opacity:0.45;
         font-family:'Consolas','Courier New',monospace}}
</style>
</head><body>
<div id="out"></div>
<div id="hint">🔍 Cliquer pour plein écran</div>
<div id="err"></div>
<script>
(function(){{
  var CODE={code_json};
  var FS_B64="{fullscreen_b64}";
  var isDark=!window.matchMedia('(prefers-color-scheme:light)').matches;
  var TV_LIGHT={{
    fontFamily:"system-ui,-apple-system,'Segoe UI',Helvetica,Arial,sans-serif",fontSize:'13px',
    background:'#ffffff',
    primaryColor:'#dbeafe',primaryTextColor:'#1a1a1a',primaryBorderColor:'#0066b8',lineColor:'#0066b8',
    secondaryColor:'#ffedd5',tertiaryColor:'#ede9fe',mainBkg:'#dbeafe',
    nodeBorder:'#0066b8',clusterBkg:'#f0f4ff',clusterBorder:'#d97706',titleColor:'#7c3aed',
    edgeLabelBackground:'#ffffff'
  }};
  var TV_DARK={{
    fontFamily:"system-ui,-apple-system,'Segoe UI',Helvetica,Arial,sans-serif",fontSize:'13px',
    background:'#0d1117',
    primaryColor:'#1f3a5f',primaryTextColor:'#e6edf3',primaryBorderColor:'#58a6ff',lineColor:'#58a6ff',
    secondaryColor:'#431407',tertiaryColor:'#2d1b52',mainBkg:'#1f3a5f',
    nodeBorder:'#58a6ff',clusterBkg:'#161b22',clusterBorder:'#a371f7',titleColor:'#a371f7',
    edgeLabelBackground:'#0d1117'
  }};
  mermaid.initialize({{startOnLoad:false,securityLevel:'loose',theme:'base',
    themeVariables:isDark?TV_DARK:TV_LIGHT}});
  mermaid.render('prev_{idx}',CODE).then(function(r){{
    document.getElementById('out').innerHTML=r.svg;
  }}).catch(function(e){{
    document.getElementById('err').textContent='⚠ '+e.message;
  }});
  function openFullscreen(){{
    try{{
      var html=atob(FS_B64);
      var win=window.open('','_blank');
      if(!win){{alert('Autorisez les popups pour cette page.');return;}}
      win.document.open();
      win.document.write(html);
      win.document.close();
    }}catch(e){{
      console.error('Fullscreen error',e);
    }}
  }}
  document.getElementById('out').addEventListener('click',openFullscreen);
}})();
</script>
</body></html>"""


def estimate_chat_mermaid_height(code: str) -> int:
    lines = code.splitlines()
    return max(220, min(600, 120 + len(lines) * 22))