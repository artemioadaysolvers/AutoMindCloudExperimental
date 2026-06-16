# USD_Render_Script.py
# Puente Colab <-> JS para visualizar sistemas USD+ con el viewer modular AutoMind.
#
# Uso típico en Colab:
#   from USD_Render_Script import USD_Render, USD_Visualization
#   USD_Render("n_262_GRIPPER_4_USD")
#   USD_Visualization("n_262_GRIPPER_4_USD", IA_Widgets=True)
#
# Este script:
#   - Busca .usda/.usd ASCII dentro de folder_path.
#   - Embebe el USD como texto y las texturas como base64.
#   - Renderiza un HTML fullscreen tipo AutoMindCloudExperimental.
#   - Mantiene el badge de AutoMind abajo a la derecha.
# #   - IA_Widgets=False: no se manda nada a API.
#   - IA_Widgets=True: registra describe_component_images para thumbnails USD.

import os
import re
import json
import base64
import shutil
import zipfile
import requests
from IPython.display import HTML

API_DEFAULT_BASE = "https://gpt-proxy-github-619255898589.us-central1.run.app"
API_INFER_PATH = "/infer"
_COLAB_CALLBACK_REGISTERED = False


def Download_USD(Drive_Link, Output_Name="USDModel"):
    """Descarga un ZIP de Google Drive, lo descomprime y devuelve /content/Output_Name."""
    root_dir = "/content"
    file_id = Drive_Link.split("/d/")[1].split("/")[0]
    url = f"https://drive.google.com/uc?id={file_id}"
    zip_path = os.path.join(root_dir, Output_Name + ".zip")
    tmp_extract = os.path.join(root_dir, f"__tmp_extract_{Output_Name}")
    final_dir = os.path.join(root_dir, Output_Name)

    if os.path.exists(tmp_extract):
        shutil.rmtree(tmp_extract)
    os.makedirs(tmp_extract, exist_ok=True)
    if os.path.exists(final_dir):
        shutil.rmtree(final_dir)

    import gdown
    gdown.download(url, zip_path, quiet=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(tmp_extract)

    def junk(name: str) -> bool:
        return name.startswith(".") or name == "__MACOSX"

    visibles = [n for n in os.listdir(tmp_extract) if not junk(n)]
    if len(visibles) == 1 and os.path.isdir(os.path.join(tmp_extract, visibles[0])):
        shutil.move(os.path.join(tmp_extract, visibles[0]), final_dir)
    else:
        os.makedirs(final_dir, exist_ok=True)
        for n in visibles:
            shutil.move(os.path.join(tmp_extract, n), os.path.join(final_dir, n))

    shutil.rmtree(tmp_extract, ignore_errors=True)
    return final_dir


def Unzip_USD(zip_path: str, output_folder: str | None = None):
    """Descomprime un ZIP local con sistema USD y devuelve la carpeta destino."""
    if not os.path.isfile(zip_path):
        raise FileNotFoundError(f"No existe el ZIP: {zip_path}")
    if output_folder is None:
        base = os.path.splitext(os.path.basename(zip_path))[0]
        output_folder = os.path.join(os.path.dirname(zip_path) or "/content", base)
    if os.path.exists(output_folder):
        shutil.rmtree(output_folder)
    os.makedirs(output_folder, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(output_folder)
    return output_folder


def _register_colab_callback(api_base: str = API_DEFAULT_BASE, timeout: int = 120):
    global _COLAB_CALLBACK_REGISTERED
    if _COLAB_CALLBACK_REGISTERED:
        return
    try:
        from google.colab import output  # type: ignore
        api_base = api_base.rstrip("/")
        infer_url = api_base + API_INFER_PATH

        def _describe_component_images(entries):
            print("[Colab] describe_component_images: payload recibido")
            if not isinstance(entries, (list, tuple)):
                print("[Colab] Payload inválido.")
                return {}

            iso_b64 = None
            components = []
            for raw in entries:
                if not isinstance(raw, dict):
                    continue
                key = (raw.get("key") or "").strip()
                img_b64 = (raw.get("image_b64") or "").strip()
                name = (raw.get("name") or "").strip()
                idx = raw.get("index", None)
                if key in ("__robot_iso__", "robot_iso", "__iso__", "robot", "full_robot"):
                    if img_b64 and not iso_b64:
                        iso_b64 = img_b64
                        print("[Colab] Detectada ISO global del sistema USD.")
                    continue
                if not img_b64:
                    continue
                if not key:
                    key = name or f"comp_{len(components)}"
                if not name:
                    name = key
                if not isinstance(idx, int) or idx < 0:
                    idx = len(components)
                components.append({"key": key, "name": name, "index": idx, "image_b64": img_b64})

            if not components:
                print("[Colab] Sin componentes válidos.")
                return {}

            components.sort(key=lambda c: c.get("index", 0))
            sequence_names = [c["name"] for c in components]
            sequence_str = ", ".join(sequence_names)
            print(f"[Colab] Componentes USD para IA: {len(components)}")

            results = {}
            for comp in components:
                key, name, idx, img_b64 = comp["key"], comp["name"], comp["index"], comp["image_b64"]
                images = []
                if iso_b64:
                    images.append({"image_b64": iso_b64, "mime": "image/png"})
                images.append({"image_b64": img_b64, "mime": "image/png"})
                prompt = (
                    "Eres un modelo experto en robótica, CAD mecánico y mecanismos articulados.\n"
                    "Analiza exclusivamente el componente actual usando la ISO global del sistema USD, "
                    "su thumbnail específico y la secuencia ordenada de nombres.\n"
                    f"Secuencia de nombres: {sequence_str}\n"
                    f"Componente actual: '{name}' (índice {idx}).\n"
                    "Explica qué es y cuál es su función con máxima precisión técnica, "
                    "estilo formal, directo y robótico. No uses frases como 'se observa' ni repitas la consigna. "
                    "Máximo 2 frases."
                )
                try:
                    r = requests.post(infer_url, json={"text": prompt, "images": images}, timeout=timeout)
                except Exception as e:
                    print(f"[Colab] Error conexión API para {key}: {e}")
                    results[key] = ""
                    continue
                if r.status_code != 200:
                    print(f"[Colab] API {r.status_code} para {key}: {r.text[:200]}")
                    results[key] = ""
                    continue
                txt = (r.text or "").strip()
                try:
                    if txt.startswith("{") and txt.endswith("}"):
                        j = json.loads(txt)
                        if isinstance(j, dict):
                            txt = j.get("text") or j.get("message") or j.get("content") or txt
                except Exception:
                    pass
                try:
                    if txt.startswith('"') and txt.endswith('"'):
                        txt = json.loads(txt)
                except Exception:
                    pass
                results[key] = txt or ""

            print(f"[Colab] Descripciones devueltas para {len(results)} componentes.")
            try:
                from google.colab import _message  # type: ignore
                _message.blocking_request("notebook.save", {})
                print("[Colab] 💾 Notebook guardado.")
            except Exception as e:
                print(f"[Colab] Aviso: no se pudo guardar auto el notebook: {e}")
            return results

        output.register_callback("describe_component_images", _describe_component_images)
        _COLAB_CALLBACK_REGISTERED = True
        print("[Colab] ✅ Callback describe_component_images registrado para USD.")
    except Exception as e:
        print(f"[Colab] (Opcional) No se pudo registrar callback: {e}")


def _find_usd_file(folder_path: str):
    candidates = []
    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__MACOSX"]
        for name in files:
            if name.lower().endswith((".usda", ".usd")):
                p = os.path.join(root, name)
                try:
                    size = os.path.getsize(p)
                except Exception:
                    size = 0
                candidates.append((size, p))
    candidates.sort(reverse=True)
    for _, p in candidates:
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                txt = f.read(4096)
            if txt.lstrip("\ufeff").lstrip().startswith("#usda") or "def Xform" in txt or "Physics" in txt:
                return p
        except Exception:
            continue
    return candidates[0][1] if candidates else None


def _collect_asset_db(folder_path: str, usd_path: str):
    allowed = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg")
    root_abs = os.path.abspath(folder_path)
    db = {}
    cache = {}

    def b64(path):
        if path not in cache:
            with open(path, "rb") as f:
                cache[path] = base64.b64encode(f.read()).decode("ascii")
        return cache[path]

    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__MACOSX"]
        for name in files:
            if not name.lower().endswith(allowed):
                continue
            p = os.path.join(root, name)
            rel = os.path.relpath(os.path.abspath(p), root_abs).replace("\\", "/")
            val = b64(p)
            db[rel] = val
            db[name] = val
            db[rel.lower()] = val
            db[name.lower()] = val
    return db


def _esc_js_template(s: str) -> str:
    return (
        s.replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("$", "\\$")
        .replace("</script>", "<\\/script>")
    )


def USD_Visualization(
    folder_path: str = "USDModel",
    select_mode: str = "link",
    background: int | None = 0xFFFFFF,
    repo: str = "artemioadaysolvers/AutoMind-USD-Loader",
    branch: str = "main",
    compFile: str = "USD_Viewer/usd_viewer_main.js",
    api_base: str = API_DEFAULT_BASE,
    IA_Widgets: bool = False,
):
    """Renderiza el AutoMind USD Viewer para Colab."""
    if IA_Widgets:
        _register_colab_callback(api_base=api_base)

    if folder_path.lower().endswith(".zip") and os.path.isfile(folder_path):
        folder_path = Unzip_USD(folder_path)

    usd_path = _find_usd_file(folder_path)
    if not usd_path:
        return HTML(f"<b style='color:red'>No se encontró .usda/.usd ASCII dentro de {folder_path}</b>")

    with open(usd_path, "r", encoding="utf-8", errors="ignore") as f:
        usd_raw = f.read().lstrip("\ufeff")

    if not (usd_raw.lstrip().startswith("#usda") or "def Xform" in usd_raw or "Physics" in usd_raw):
        return HTML("<b style='color:red'>El archivo encontrado no parece USD ASCII. Exporta .usda/.usd textual.</b>")

    asset_db = _collect_asset_db(folder_path, usd_path)
    usd_js = _esc_js_template(usd_raw)
    asset_js = json.dumps(asset_db)
    bg_js = "null" if background is None else str(int(background))
    sel_js = json.dumps(select_mode)
    ia_js = "true" if IA_Widgets else "false"

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover"/>
  <title>AutoMind USD Viewer</title>
  <style>
    :root {{ --vh: 1vh; }}
    html, body {{ margin:0; padding:0; width:100%; height:100dvh; overflow:hidden; background:#{int(background or 0xFFFFFF):06x}; }}
    @supports not (height: 100dvh) {{ html, body {{ height: calc(var(--vh) * 100); }} }}
    body {{ padding-top: env(safe-area-inset-top); padding-right: env(safe-area-inset-right); padding-bottom: env(safe-area-inset-bottom); padding-left: env(safe-area-inset-left); }}
    #app {{ position:fixed; inset:0; width:100vw; height:100dvh; touch-action:none; }}
    @supports not (height: 100dvh) {{ #app {{ height: calc(var(--vh) * 100); }} }}
    .badge {{ position:fixed; right:14px; bottom:10px; z-index:10; user-select:none; pointer-events:none; }}
    .badge img {{ max-height:40px; display:block; }}
  </style>
</head>
<body>
  <div id="app"></div>
  <div style="padding-left:20px; overflow:visible; position:fixed; right:0; bottom:0; z-index:999999;">
    <div class="badge" style="display:inline-block; transform: scale(2.5) translateX(-15px); transform-origin: bottom right; margin:0; overflow:visible; pointer-events:none;">
      <img src="https://raw.githubusercontent.com/artemioadaysolvers/AutoMindCloudExperimental/main/AutoMindCloud/AutoMindCloud2.png" alt="AutoMind" style="display:block; height:40px; width:auto;"/>
    </div>
  </div>

  <script defer src="https://cdn.jsdelivr.net/npm/three@0.132.2/build/three.min.js"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/three@0.132.2/examples/js/controls/OrbitControls.js"></script>

  <script type="module">
    function applyVHVar() {{
      const viewport = window.visualViewport?.height || window.innerHeight || 600;
      document.documentElement.style.setProperty('--vh', `${{viewport * 0.01}}px`);
    }}
    applyVHVar();

    function computeDesiredHeight() {{
      const viewportH = window.visualViewport?.height || window.innerHeight || document.documentElement.clientHeight || 0;
      const docScrollH = Math.max(document.documentElement?.scrollHeight || 0, document.body?.scrollHeight || 0);
      return Math.max(viewportH, docScrollH, 600);
    }}
    function setColabFrameHeight() {{
      const h = Math.ceil(computeDesiredHeight());
      try {{ if (window.google?.colab?.output?.setIframeHeight) window.google.colab.output.setIframeHeight(h, true); }} catch (_e) {{}}
    }}
    const ro = new ResizeObserver(() => {{ applyVHVar(); setColabFrameHeight(); }});
    ro.observe(document.body);
    window.addEventListener('resize', () => {{ applyVHVar(); setColabFrameHeight(); }});
    if (window.visualViewport) window.visualViewport.addEventListener('resize', () => {{ applyVHVar(); setColabFrameHeight(); }});
    setTimeout(setColabFrameHeight, 60);

    const repo     = {json.dumps(repo)};
    const branch   = {json.dumps(branch)};
    const compFile = {json.dumps(compFile)};

    async function latestSha() {{
      try {{
        const url = 'https://api.github.com/repos/' + repo + '/commits/' + branch + '?_=' + Date.now();
        const r = await fetch(url, {{ headers: {{ 'Accept': 'application/vnd.github+json' }}, cache: 'no-store' }});
        if (!r.ok) throw 0;
        const j = await r.json();
        return (j.sha || '').slice(0, 7) || branch;
      }} catch (_e) {{ return branch; }}
    }}

    const SELECT_MODE = {sel_js};
    const BACKGROUND  = {bg_js};
    const IA_WIDGETS  = {ia_js};

    const opts = {{
      container: document.getElementById('app'),
      usdContent: `{usd_js}`,
      assetDB: {asset_js},
      selectMode: SELECT_MODE,
      background: BACKGROUND,
      pixelRatio: Math.min(window.devicePixelRatio || 1, 2),
      autoResize: true,
      IA_Widgets: IA_WIDGETS
    }};

    let mod = null;
    try {{
      const sha = await latestSha();
      const base = 'https://cdn.jsdelivr.net/gh/' + repo + '@' + sha + '/';
      mod = await import(base + compFile + '?v=' + Date.now());
      console.debug('[USD] Módulo viewer desde', sha);
    }} catch (_e) {{
      console.debug('[USD] Fallback branch', branch);
      mod = await import('https://cdn.jsdelivr.net/gh/' + repo + '@' + branch + '/' + compFile + '?v=' + Date.now());
    }}

    if (!mod || typeof mod.render !== 'function') {{
      console.error('[USD] No se pudo cargar usd_viewer_main.js o falta render()');
    }} else {{
      const app = mod.render(opts);
      function onResize() {{
        try {{
          if (!app || typeof app.resize !== 'function') return;
          const w = window.innerWidth || document.documentElement.clientWidth || document.body.clientWidth || 800;
          const h = computeDesiredHeight();
          app.resize(w, h, Math.min(window.devicePixelRatio || 1, 2));
        }} catch (_e) {{}}
      }}
      window.addEventListener('resize', onResize);
      if (window.visualViewport) window.visualViewport.addEventListener('resize', onResize);
      setTimeout(() => {{ onResize(); setColabFrameHeight(); }}, 0);
      setTimeout(() => {{ onResize(); setColabFrameHeight(); }}, 500);
    }}
  </script>
</body>
</html>
"""
    return HTML(html)


def USD_Viewer(*args, **kwargs):
    return USD_Visualization(*args, **kwargs)
