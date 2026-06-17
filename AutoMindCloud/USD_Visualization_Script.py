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
#   - IA_Widgets=False: no se manda nada a API.
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


_WHITE_PIXEL_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
    "AAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def _clean_asset_ref(ref: str) -> str:
    s = str(ref or "").strip()
    if (s.startswith("@") and s.endswith("@")) or (s.startswith("\"") and s.endswith("\"")):
        s = s[1:-1]
    s = s.replace("\\", "/")
    s = re.sub(r"^file:/+", "", s, flags=re.I)
    s = re.sub(r"^package:/+", "", s, flags=re.I)
    s = re.sub(r"^\./", "", s)
    s = s.lstrip("/")
    return s


def _asset_key_variants(path: str):
    raw = _clean_asset_ref(path)
    if not raw:
        return []

    parts = [x for x in raw.split("/") if x]
    base = os.path.basename(raw)
    out = set()

    def add(x):
        x = _clean_asset_ref(x)
        if not x:
            return
        out.add(x)
        out.add(x.lower())
        out.add("./" + x)
        out.add(("./" + x).lower())

    add(raw)
    add(base)

    # Suffixes: useful when USD references textures/foo.png but ZIP has model/textures/foo.png.
    for i in range(len(parts)):
        add("/".join(parts[i:]))

    # Spacing/underscore variants for CAD exporters.
    if base:
        stem, ext = os.path.splitext(base)
        for b in {
            base.replace("%20", " "),
            base.replace(" ", "_"),
            base.replace("_", " "),
            stem.replace(" ", "_") + ext,
            stem.replace("_", " ") + ext,
            re.sub(r"[\s_\-]+", "", stem) + ext,
        }:
            add(b)

    return list(out)


def _extract_usd_texture_refs(usd_raw: str):
    allowed = r"png|jpg|jpeg|webp|gif|bmp|svg"
    refs = []

    # USD asset syntax: @textures/albedo.png@
    refs += re.findall(r"@([^@\r\n]+?\.(?:" + allowed + r"))@", usd_raw or "", flags=re.I)

    # Some exporters put image paths inside quoted strings.
    refs += re.findall(r"[\"']([^\"'\r\n]+?\.(?:" + allowed + r"))[\"']", usd_raw or "", flags=re.I)

    seen = set()
    out = []
    for r in refs:
        rr = _clean_asset_ref(r)
        k = rr.lower()
        if rr and k not in seen:
            seen.add(k)
            out.append(rr)
    return out


def _collect_asset_db(folder_path: str, usd_path: str, usd_raw: str = ""):
    allowed = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg")
    root_abs = os.path.abspath(folder_path)
    usd_dir_abs = os.path.dirname(os.path.abspath(usd_path))
    db = {}
    cache = {}

    def b64(path):
        if path not in cache:
            with open(path, "rb") as f:
                cache[path] = base64.b64encode(f.read()).decode("ascii")
        return cache[path]

    def add_entry(key, val):
        for k in _asset_key_variants(key):
            db.setdefault(k, val)

    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__MACOSX"]
        for name in files:
            if not name.lower().endswith(allowed):
                continue

            p = os.path.abspath(os.path.join(root, name))
            val = b64(p)

            # Register paths relative to both the extraction root and the USD file folder.
            # USD texture paths are usually relative to the .usda file, not always the ZIP root.
            for base_dir in (root_abs, usd_dir_abs):
                try:
                    rel = os.path.relpath(p, base_dir).replace("\\", "/")
                    add_entry(rel, val)
                except Exception:
                    pass

            add_entry(name, val)

    # Add a safe 1x1 white placeholder for texture references that are present in USD
    # but missing from the extracted ZIP. This prevents Three.js from trying to upload
    # a texture whose image is undefined.
    missing = []
    for ref in _extract_usd_texture_refs(usd_raw):
        if not any(k in db for k in _asset_key_variants(ref)):
            missing.append(ref)
            add_entry(ref, _WHITE_PIXEL_PNG_B64)

    if missing:
        shown = ", ".join(missing[:8])
        extra = "" if len(missing) <= 8 else f" ... +{len(missing) - 8} más"
        print(f"[USD] Aviso: {len(missing)} textura(s) referenciada(s) no estaban en el ZIP. Se usó placeholder blanco: {shown}{extra}")

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

    asset_db = _collect_asset_db(folder_path, usd_path, usd_raw)
    usd_js = _esc_js_template(usd_raw)
    asset_js = json.dumps(asset_db)
    bg_js = "null" if background is None else str(int(background))
    sel_js = json.dumps(select_mode)
    ia_js = "true" if IA_Widgets else "false"

    html = fr"""<!doctype html>
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
    // Colab iframe sandbox warnings are normal. The filter below only hides the
    // repeated Three.js warning produced by missing/late texture images.
    const __AutoMindOriginalConsoleWarn = console.warn.bind(console);
    console.warn = (...args) => {{
      const msg = String(args?.[0] || '');
      if (msg.includes('THREE.WebGLRenderer: Texture marked for update but image is undefined')) return;
      __AutoMindOriginalConsoleWarn(...args);
    }};

    function installTextureSafetyPatch() {{
      if (!window.THREE || !THREE.WebGLRenderer || THREE.WebGLRenderer.__AutoMindTextureSafe) return;
      const slots = ['map','alphaMap','aoMap','bumpMap','normalMap','emissiveMap','roughnessMap','metalnessMap','specularMap','envMap','lightMap','displacementMap'];
      const originalRender = THREE.WebGLRenderer.prototype.render;
      THREE.WebGLRenderer.prototype.render = function(scene, camera) {{
        try {{
          scene?.traverse?.((obj) => {{
            if (!obj?.isMesh || !obj.material) return;
            const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
            for (const mat of mats) {{
              if (!mat) continue;
              for (const slot of slots) {{
                const tex = mat[slot];
                if (tex && tex.needsUpdate && !tex.image) tex.needsUpdate = false;
              }}
            }}
          }});
        }} catch (_e) {{}}
        return originalRender.call(this, scene, camera);
      }};
      THREE.WebGLRenderer.__AutoMindTextureSafe = true;
    }}

    // three.min.js is loaded with defer above. Wait until it exists, then patch once.
    for (let i = 0; i < 80 && !window.THREE; i++) {{
      await new Promise(r => setTimeout(r, 25));
    }}
    installTextureSafetyPatch();

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

    const RAW_VIEWER_URL = 'https://raw.githubusercontent.com/artemioadaysolvers/AutoMind-USD-Loader/main/USD_Viewer/usd_viewer_main.js';

    async function importRawGithubModule(rawUrl) {{
      // raw.githubusercontent.com entrega el JS con MIME no ideal para import() directo.
      // Además usd_viewer_main.js usa imports relativos como ./Theme.js.
      // Por eso este cargador:
      //   1) descarga cada módulo desde raw GitHub,
      //   2) reescribe imports relativos a Blob URLs,
      //   3) importa el módulo raíz desde Blob sin romper ./Theme.js, ./Parser.js, etc.
      const moduleCache = new Map();
      const version = Date.now();

      function bust(url) {{
        return url + (url.includes('?') ? '&' : '?') + 'v=' + version;
      }}

      function isRelativeSpecifier(spec) {{
        return typeof spec === 'string' && (spec.startsWith('./') || spec.startsWith('../'));
      }}

      function collectRelativeSpecifiers(source) {{
        const specs = new Set();
        const patterns = [
          /\b(?:import|export)\s+[^'"]*?\s+from\s*(['"])(\.{{1,2}}\/[^'"]+)\1/g,
          /\bimport\s*(['"])(\.{{1,2}}\/[^'"]+)\1/g,
          /\bimport\s*\(\s*(['"])(\.{{1,2}}\/[^'"]+)\1\s*\)/g
        ];

        for (const re of patterns) {{
          let m;
          while ((m = re.exec(source)) !== null) {{
            if (isRelativeSpecifier(m[2])) specs.add(m[2]);
          }}
        }}
        return [...specs];
      }}

      function rewriteRelativeSpecifiers(source, replacements) {{
        source = source.replace(
          /(\b(?:import|export)\s+[^'"]*?\s+from\s*['"])(\.{{1,2}}\/[^'"]+)(['"])/g,
          (all, p1, spec, p3) => p1 + (replacements.get(spec) || spec) + p3
        );

        source = source.replace(
          /(\bimport\s*['"])(\.{{1,2}}\/[^'"]+)(['"])/g,
          (all, p1, spec, p3) => p1 + (replacements.get(spec) || spec) + p3
        );

        source = source.replace(
          /(\bimport\s*\(\s*['"])(\.{{1,2}}\/[^'"]+)(['"]\s*\))/g,
          (all, p1, spec, p3) => p1 + (replacements.get(spec) || spec) + p3
        );

        return source;
      }}

      async function toBlobModuleUrl(moduleUrl) {{
        moduleUrl = new URL(moduleUrl, window.location.href).href;

        if (moduleCache.has(moduleUrl)) {{
          return moduleCache.get(moduleUrl);
        }}

        const promise = (async () => {{
          const r = await fetch(bust(moduleUrl), {{ cache: 'no-store' }});
          if (!r.ok) {{
            throw new Error('HTTP ' + r.status + ' al cargar ' + moduleUrl);
          }}

          let source = await r.text();
          if (!source || !source.trim()) {{
            throw new Error('Módulo JS vacío desde raw.githubusercontent.com: ' + moduleUrl);
          }}

          const specs = collectRelativeSpecifiers(source);
          const replacements = new Map();

          for (const spec of specs) {{
            const childUrl = new URL(spec, moduleUrl).href;
            const childBlobUrl = await toBlobModuleUrl(childUrl);
            replacements.set(spec, childBlobUrl);
          }}

          source = rewriteRelativeSpecifiers(source, replacements);

          const blob = new Blob([source + '\n//# sourceURL=' + moduleUrl], {{
            type: 'text/javascript;charset=utf-8'
          }});

          const blobUrl = URL.createObjectURL(blob);
          window.__AutoMindUSDViewerBlobURLs = window.__AutoMindUSDViewerBlobURLs || [];
          window.__AutoMindUSDViewerBlobURLs.push(blobUrl);
          return blobUrl;
        }})();

        moduleCache.set(moduleUrl, promise);
        return promise;
      }}

      const entryBlobUrl = await toBlobModuleUrl(rawUrl);
      return await import(entryBlobUrl);
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
      mod = await importRawGithubModule(RAW_VIEWER_URL);
      console.debug('[USD] Módulo viewer cargado desde raw.githubusercontent.com con imports relativos reescritos');
    }} catch (err) {{
      console.error('[USD] No se pudo cargar usd_viewer_main.js desde raw.githubusercontent.com', err);
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


def USD_Render(*args, **kwargs):
    return USD_Visualization(*args, **kwargs)
