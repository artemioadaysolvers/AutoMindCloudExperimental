# URDF_Render_Script_JSDELIVR_GH_THREE_V17_BUILD145.py
# Puente Colab/Jupyter <-> AutoMind URDF+ Viewer V17 / BUILD145 modular por jsDelivr directo con scripts clásicos tipo USD.
# Igual en patrón al USD_Render_Script: resuelve último commit, importa el módulo JS
# y llama mod.render(opts). No carga HTML standalone ni iframe interno.

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


def Unzip_URDF(zip_path: str, output_folder: str | None = None):
    """Descomprime un ZIP local con URDF_Export y devuelve la carpeta destino."""
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
            if not isinstance(entries, (list, tuple)):
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
                return {}
            components.sort(key=lambda c: c.get("index", 0))
            sequence_names = [c["name"] for c in components]
            sequence_str = ", ".join(sequence_names)
            results = {}
            for comp in components:
                key, name, idx, img_b64 = comp["key"], comp["name"], comp["index"], comp["image_b64"]
                images = []
                if iso_b64:
                    images.append({"image_b64": iso_b64, "mime": "image/png"})
                images.append({"image_b64": img_b64, "mime": "image/png"})
                prompt = (
                    "Eres un modelo experto en robótica, CAD mecánico y mecanismos articulados.\n"
                    "Analiza exclusivamente el componente actual usando la ISO global del sistema URDF+, "
                    "su thumbnail específico y la secuencia ordenada de nombres.\n"
                    f"Secuencia de nombres: {sequence_str}\n"
                    f"Componente actual: '{name}' (índice {idx}).\n"
                    "Explica qué es y cuál es su función con máxima precisión técnica, "
                    "estilo formal, directo y robótico. No uses frases como 'se observa' ni repitas la consigna. "
                    "Máximo 2 frases."
                )
                try:
                    r = requests.post(infer_url, json={"text": prompt, "images": images}, timeout=timeout)
                    if r.status_code != 200:
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
                except Exception:
                    results[key] = ""
            return results

        output.register_callback("describe_component_images", _describe_component_images)
        _COLAB_CALLBACK_REGISTERED = True
    except Exception:
        pass


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read().lstrip("\ufeff")


def _find_urdf_file(folder_path: str):
    candidates = []
    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__MACOSX"]
        for name in files:
            if not name.lower().endswith((".urdf", ".xml")):
                continue
            p = os.path.join(root, name)
            try:
                txt = _read_text(p)[:4096]
                if "<robot" not in txt:
                    continue
                size = os.path.getsize(p)
            except Exception:
                size = 0
            lname = name.lower()
            score = 0
            if lname.endswith(".urdf"):
                score += 20
            if "standard_tree_backup" in lname:
                score -= 30
            if any(k in lname for k in ("urdf_plus", "urdfplus", "pivotes", "reales", "corregid", "arreglad", "editado")):
                score += 12
            candidates.append((score, size, p))
    candidates.sort(reverse=True)
    return candidates[0][2] if candidates else None


def _mime_from_path(path: str) -> str:
    e = os.path.splitext(path.lower())[1]
    return {
        ".urdf": "application/xml",
        ".xml": "application/xml",
        ".dae": "model/vnd.collada+xml",
        ".stl": "model/stl",
        ".obj": "text/plain",
        ".mtl": "text/plain",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".gif": "image/gif",
        ".tga": "image/x-tga",
    }.get(e, "application/octet-stream")


_AUTOMIND_WHITE_PIXEL_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
    "AAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def _clean_asset_ref_for_dae(ref: str) -> str:
    s = str(ref or "").strip().strip("'\"")
    if s.startswith("@") and s.endswith("@"):
        s = s[1:-1]
    s = s.replace("\\", "/")
    s = re.sub(r"[?#].*$", "", s)
    # ColladaLoader can turn a DAE data/blob URL + relative texture into
    # data:model/base.jpg or blob:https://.../base.jpg. For asset matching we
    # normalize that back to base.jpg / suffix path.
    if re.match(r"^data:", s, flags=re.I) and not re.match(r"^data:[^,]+,", s, flags=re.I):
        s = re.sub(r"^data:", "", s, flags=re.I)
        s = re.sub(r"^[a-z0-9.+-]+/", "", s, flags=re.I)
    s = re.sub(r"^blob:https?://[^/]+/", "", s, flags=re.I)
    s = re.sub(r"^file:/+", "", s, flags=re.I)
    s = re.sub(r"^package:/+", "", s, flags=re.I)
    s = re.sub(r"^[A-Za-z]:/", "", s)
    s = re.sub(r"^\./", "", s).lstrip("/")
    return s


def _dae_texture_refs(dae_text: str):
    allowed = r"png|jpg|jpeg|webp|gif|bmp|tga"
    refs = []
    # <init_from>base.jpg</init_from>, attribute URLs, quoted values, etc.
    refs += re.findall(r">([^<>\r\n]+?\.(?:" + allowed + r"))(?:[?#][^<>\r\n]*)?<", dae_text or "", flags=re.I)
    refs += re.findall(r"[\"']([^\"'\r\n]+?\.(?:" + allowed + r"))(?:[?#][^\"'\r\n]*)?[\"']", dae_text or "", flags=re.I)
    out, seen = [], set()
    for ref in refs:
        clean = _clean_asset_ref_for_dae(ref)
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            out.append(clean)
    return out


def _collect_asset_db(folder_path: str):
    """Devuelve assets exactos del URDF_Export para el viewer modular.

    V17 / BUILD145: además de rutas exactas y sufijos seguros, agrega alias por
    basename *con extensión* solamente cuando ese basename es único dentro del
    export. Esto replica mejor el FileMap del HTML BUILD138, donde el navegador
    podía resolver texturas Collada tipo data:model/base.jpg, package://...,
    meshes/..., textures/... o simplemente base.jpg sin mezclar stems distintos.
    Nunca se agregan alias por stem sin extensión.
    """
    allowed_text = (".urdf", ".xml", ".dae", ".obj", ".mtl", ".txt", ".json", ".csv")
    allowed_bin = (".stl", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tga")
    root_abs = os.path.abspath(folder_path)
    db = {}
    records = []
    dae_texture_refs = []

    def add_key(key: str, val: str):
        key = str(key or "").replace("\\", "/").lstrip("/")
        if not key:
            return
        db.setdefault(key, val)
        db.setdefault(key.lower(), val)

    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__MACOSX"]
        for name in files:
            ext = os.path.splitext(name.lower())[1]
            if ext not in allowed_text and ext not in allowed_bin:
                continue
            p = os.path.join(root, name)
            rel = os.path.relpath(p, root_abs).replace("\\", "/")
            if ext in allowed_text:
                val = _read_text(p)
                if ext == ".dae":
                    dae_texture_refs.extend(_dae_texture_refs(val))
            else:
                with open(p, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
                # BUILD145: transfer image textures already as MIME-correct
                # data:image/...;base64,... values. Mesh binaries such as STL stay
                # as raw base64 because the JS mesh loaders parse them as buffers.
                if ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tga"):
                    val = f"{_mime_from_path(p)};base64,{b64}"
                    val = "data:" + val if not val.startswith("data:") else val
                else:
                    val = b64
            records.append((rel, name, ext, val))
            add_key(rel, val)
            # Suffixes are safe because the extension remains part of the key.
            parts = rel.split("/")
            for i in range(1, len(parts)):
                add_key("/".join(parts[i:]), val)
            # Common folders used by ROS/Inventor exporters and by DAE images.
            base = os.path.basename(rel)
            parent = os.path.basename(os.path.dirname(rel))
            if parent.lower() in ("mesh", "meshes", "texture", "textures", "materials", "images"):
                add_key(f"{parent}/{base}", val)

    # Add basename aliases only when unique. This fixes Collada texture refs like
    # data:model/base.jpg while avoiding dangerous collisions.
    by_base = {}
    for rel, name, ext, val in records:
        by_base.setdefault(name.lower(), []).append((name, val))
    for base_lower, vals in by_base.items():
        unique_vals = {v for _, v in vals}
        if len(unique_vals) == 1:
            name, val = vals[0]
            add_key(name, val)
            add_key(base_lower, val)

    # BUILD145: if a Collada file references textures that are absent from the
    # extracted ZIP, register a safe inline placeholder for the exact ref and
    # basename. This prevents Three/ColladaLoader from requesting fake Colab Blob
    # URLs such as blob:https://.../base.jpg, remote.jpg or camera jpgs. Existing
    # real textures are not overwritten because add_key() uses setdefault().
    for ref in dae_texture_refs:
        ref = _clean_asset_ref_for_dae(ref)
        if not ref:
            continue
        add_key(ref, _AUTOMIND_WHITE_PIXEL_DATA_URL)
        add_key(os.path.basename(ref), _AUTOMIND_WHITE_PIXEL_DATA_URL)
        for folder in ("textures", "texture", "images", "materials"):
            add_key(f"{folder}/{os.path.basename(ref)}", _AUTOMIND_WHITE_PIXEL_DATA_URL)

    return db

def _zip_folder_to_base64(folder_path: str) -> str:
    mem = bytearray()
    import io
    bio = io.BytesIO()
    root_abs = os.path.abspath(folder_path)
    with zipfile.ZipFile(bio, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(folder_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__MACOSX"]
            for name in files:
                p = os.path.join(root, name)
                arc = os.path.relpath(p, root_abs).replace("\\", "/")
                zf.write(p, arc)
    return base64.b64encode(bio.getvalue()).decode("ascii")


def _esc_js_template(s: str) -> str:
    return (
        s.replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("$", "\\$")
        .replace("</script>", "<\\/script>")
    )


def _html_error(title: str, detail: str):
    return HTML(f"""
    <div style="font-family:Inter,Arial,sans-serif;border:1px solid #f3b3b3;background:#fff5f5;color:#7a1111;border-radius:12px;padding:14px;line-height:1.45">
      <b>{title}</b>
      <pre style="white-space:pre-wrap;margin:10px 0 0;color:#7a1111;background:#fff;border:1px solid #ffd0d0;border-radius:10px;padding:10px">{detail}</pre>
    </div>
    """)


def _resolve_latest_commit(repo: str, branch: str = "main", timeout: int = 25):
    repo = str(repo or "").strip().strip("/")
    branch = str(branch or "main").strip()
    if not repo or "/" not in repo:
        raise ValueError("repo debe tener formato 'usuario/repositorio'.")
    api_url = f"https://api.github.com/repos/{repo}/commits/{branch}"
    r = requests.get(api_url, headers={"Accept": "application/vnd.github+json", "User-Agent": "AutoMind-URDF-Render-Script"}, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"No pude resolver el último commit de {repo}@{branch}. HTTP {r.status_code}: {r.text[:500]}")
    data = r.json()
    sha = data.get("sha") or ""
    if not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        raise RuntimeError(f"GitHub API respondió un SHA inválido: {sha!r}")
    commit = data.get("commit") or {}
    return {
        "repo": repo,
        "branch": branch,
        "sha": sha,
        "short_sha": sha[:7],
        "message": (commit.get("message") or "").splitlines()[0].strip(),
        "html_url": data.get("html_url") or f"https://github.com/{repo}/commit/{sha}",
    }


def _build_jsdelivr_url(repo: str, sha: str, compFile: str):
    comp = str(compFile or "").strip().replace("\\", "/").lstrip("/")
    if not comp:
        raise ValueError("compFile está vacío.")
    return f"https://cdn.jsdelivr.net/gh/{repo}@{sha}/{comp}"


def _probe_modular_viewer_entry(url: str, compFile: str, timeout: int = 35, forbid_iframe_adapter: bool = True):
    r = requests.get(url, headers={"User-Agent": "AutoMind-URDF-Render-Script"}, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"No encontré el viewer modular. HTTP {r.status_code}\nURL: {url}\nRuta: {compFile}")
    text = r.text or ""
    sample = text
    stripped = sample.lstrip().lower()
    if stripped.startswith("<!doctype") or stripped.startswith("<html"):
        raise RuntimeError(f"compFile devuelve HTML, no JS modular. URL: {url}")
    if not re.search(r"export\s+(?:async\s+)?function\s+render|export\s*\{[^}]*render|export\s+default[^;{]*\{?[^}]*render", sample, re.S):
        raise RuntimeError(
            "El módulo cargó, pero no parece exportar render(opts).\n"
            f"URL: {url}\n"
            f"Ruta usada: {compFile}\n\n"
            "Usa URDF_Viewer/urdfplus_viewer_main.js o sube el alias usdplus_viewer_main.js del ZIP corregido."
        )
    if forbid_iframe_adapter and re.search(r"srcdoc|createElement\(['\"]iframe['\"]\)|standalone\.html|urdfplus_standalone", sample, re.I):
        raise RuntimeError(
            "El módulo exporta render(opts), pero todavía es el adapter viejo con iframe/HTML standalone.\n"
            f"URL: {url}\n\n"
            "Sube al repo el contenido completo del ZIP corregido de URDF_Viewer/."
        )
    return {"ok": True, "content_type": r.headers.get("content-type", ""), "bytes_scanned": len(sample)}




def _norm_module_path(path: str) -> str:
    path = str(path or "").replace("\\", "/").split("?")[0].split("#")[0].lstrip("/")
    parts = []
    for part in path.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def _resolve_module_rel(base_path: str, rel: str) -> str:
    base = _norm_module_path(base_path)
    folder = base.rsplit("/", 1)[0] if "/" in base else ""
    return _norm_module_path((folder + "/" if folder else "") + str(rel or ""))


_IMPORT_FROM_RE = re.compile(r"(?:import|export)\s+[\s\S]*?\s+from\s*['\"](\.{1,2}/[^'\"]+)['\"]", re.M)
_IMPORT_SIDE_RE = re.compile(r"import\s*['\"](\.{1,2}/[^'\"]+)['\"]", re.M)


def _extract_static_module_deps(js_text: str):
    deps = []
    for rx in (_IMPORT_FROM_RE, _IMPORT_SIDE_RE):
        for m in rx.finditer(js_text or ""):
            dep = (m.group(1) or "").strip()
            if dep and dep not in deps:
                deps.append(dep)
    return deps


def _fetch_text_with_fallback(urls, timeout: int = 35):
    errors = []
    headers = {"User-Agent": "AutoMind-URDF-Render-Script", "Accept": "text/plain,*/*"}
    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200 and (r.text or "").strip():
                return r.text or "", url, r.headers.get("content-type", "")
            errors.append(f"{url} -> HTTP {r.status_code}: {(r.text or '')[:180]}")
        except Exception as e:
            errors.append(f"{url} -> {type(e).__name__}: {e}")
    raise RuntimeError("No pude descargar el módulo JS desde jsDelivr:\n" + "\n".join(errors))


def _collect_viewer_module_sources(repo: str, sha: str, compFile: str, timeout: int = 35):
    """Descarga y embebe el grafo ESM del viewer.

    Esto evita el punto frágil de Colab/browser: import() directo desde jsDelivr.
    Python descarga los módulos una vez, el HTML los convierte a Blob URLs y el
    navegador importa el Blob local. Las dependencias relativas se reescriben a
    Blob URLs, por lo que no queda ningún import modular remoto en runtime.
    """
    root = _norm_module_path(compFile)
    if not root:
        raise ValueError("compFile está vacío.")
    sources = {}
    meta = {}
    visiting = set()

    def fetch_module(path: str):
        path = _norm_module_path(path)
        if path in sources:
            return
        if path in visiting:
            return
        visiting.add(path)
        cdn_url = _build_jsdelivr_url(repo, sha, path)
        js, used_url, ctype = _fetch_text_with_fallback([cdn_url], timeout=timeout)
        stripped = js.lstrip().lower()
        if stripped.startswith("<!doctype") or stripped.startswith("<html"):
            raise RuntimeError(f"{path} devuelve HTML, no JS modular. URL: {used_url}")
        sources[path] = js
        meta[path] = {"url": used_url, "content_type": ctype, "bytes": len(js)}
        for rel in _extract_static_module_deps(js):
            fetch_module(_resolve_module_rel(path, rel))
        visiting.discard(path)

    fetch_module(root)
    root_text = sources.get(root, "")
    if not re.search(r"export\s+(?:async\s+)?function\s+render|export\s*\{[^}]*render|export\s+default[^;{]*\{?[^}]*render", root_text, re.S):
        # Alias modules may only re-export; accept them if their dependency has render.
        if not any(re.search(r"export\s+(?:async\s+)?function\s+render|export\s*\{[^}]*render|export\s+default[^;{]*\{?[^}]*render", src, re.S) for src in sources.values()):
            raise RuntimeError(
                "El grafo modular cargó, pero ningún módulo parece exportar render(opts).\n"
                f"Ruta usada: {compFile}"
            )
    for path, src in sources.items():
        if re.search(r"srcdoc|createElement\(['\"]iframe['\"]\)|standalone\.html|urdfplus_standalone", src, re.I):
            raise RuntimeError(
                "El grafo modular todavía contiene adapter viejo con iframe/HTML standalone.\n"
                f"Módulo: {path}\nSube al repo el contenido completo del ZIP corregido de URDF_Viewer/."
            )
    return {
        "root": root,
        "sources": sources,
        "meta": meta,
        "count": len(sources),
        "total_bytes": sum(len(s or "") for s in sources.values()),
    }

def _resolve_local_viewer_root(local_viewer_folder: str | None = None):
    candidates = []
    if local_viewer_folder:
        candidates.append(local_viewer_folder)
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.join(here, "URDF_Viewer"))
        candidates.append(here)
    except Exception:
        pass
    candidates.append(os.path.join(os.getcwd(), "URDF_Viewer"))
    candidates.append(os.getcwd())
    for c in candidates:
        if not c:
            continue
        c = os.path.abspath(c)
        if os.path.isdir(os.path.join(c, "URDF_Viewer")):
            c = os.path.join(c, "URDF_Viewer")
        if os.path.isdir(c) and os.path.isfile(os.path.join(c, "urdfplus_viewer_main.js")):
            return c
    return None


def _collect_viewer_module_sources_local(local_viewer_folder: str, compFile: str):
    """Embebe el grafo ESM desde una carpeta local URDF_Viewer/."""
    root_folder = _resolve_local_viewer_root(local_viewer_folder)
    if not root_folder:
        raise RuntimeError(f"No encontré carpeta local URDF_Viewer válida: {local_viewer_folder}")
    root = _norm_module_path(compFile)
    if root.startswith("URDF_Viewer/"):
        root_rel = root[len("URDF_Viewer/"):]
    else:
        root_rel = root
    sources = {}
    meta = {}
    visiting = set()

    def fetch_module(path: str):
        path = _norm_module_path(path)
        rel = path[len("URDF_Viewer/"):] if path.startswith("URDF_Viewer/") else path
        full = os.path.abspath(os.path.join(root_folder, rel))
        if not full.startswith(os.path.abspath(root_folder) + os.sep) and full != os.path.abspath(root_folder):
            raise RuntimeError(f"Import local fuera de URDF_Viewer no permitido: {path}")
        store_path = "URDF_Viewer/" + rel.replace("\\", "/")
        if store_path in sources:
            return
        if store_path in visiting:
            return
        visiting.add(store_path)
        if not os.path.isfile(full):
            raise RuntimeError(f"Módulo local no existe: {full}")
        js = _read_text(full)
        stripped = js.lstrip().lower()
        if stripped.startswith("<!doctype") or stripped.startswith("<html"):
            raise RuntimeError(f"{store_path} devuelve HTML, no JS modular.")
        sources[store_path] = js
        meta[store_path] = {"url": "local:" + full, "content_type": "text/javascript", "bytes": len(js)}
        for rel_dep in _extract_static_module_deps(js):
            fetch_module(_resolve_module_rel(store_path, rel_dep))
        visiting.discard(store_path)

    fetch_module("URDF_Viewer/" + root_rel)
    root_store = "URDF_Viewer/" + root_rel
    root_text = sources.get(root_store, "")
    if not re.search(r"export\s+(?:async\s+)?function\s+render|export\s*\{[^}]*render|export\s+default[^;{]*\{?[^}]*render", root_text, re.S):
        if not any(re.search(r"export\s+(?:async\s+)?function\s+render|export\s*\{[^}]*render|export\s+default[^;{]*\{?[^}]*render", src, re.S) for src in sources.values()):
            raise RuntimeError("El grafo modular local cargó, pero ningún módulo parece exportar render(opts).")
    return {
        "root": root_store,
        "sources": sources,
        "meta": meta,
        "count": len(sources),
        "total_bytes": sum(len(s or "") for s in sources.values()),
        "local_root": root_folder,
    }

def URDF_Visualization(
    folder_path: str = "URDF_Export",
    select_mode: str = "link",
    background: int | None = 0xFFFFFF,
    repo: str = "artemioadaysolvers/AutoMind-URDF-USD-MJCF-Loader",
    branch: str = "main",
    compFile: str = "URDF_Viewer/urdfplus_viewer_main.js",
    api_base: str = API_DEFAULT_BASE,
    IA_Widgets: bool = False,
    debug: bool = False,
    module_mode: str = "cdn",
    local_viewer_folder: str | None = None,
    timeout: int = 35,
    prefer_standard_backup: bool | None = None,
    force_visual_backup: bool = False,
    visual_tree_mode: str = "html_exact",
):
    """
    Renderiza AutoMind URDF+ Viewer V17 / BUILD145 modular. Por defecto importa el entrypoint modular directo desde jsDelivr.

    Patrón idéntico al USD_Render_Script:
      1) Resuelve último commit de GitHub.
      2) Construye la URL pinneada por SHA en jsDelivr.
      3) import() directo desde jsDelivr para que dependencias relativas también salgan del CDN.
      4) llama mod.render(opts).

    No carga HTML standalone. No crea iframe interno. El único contenedor es #app.

    V17 / BUILD145 sincroniza el mecanismo visual del HTML BUILD138 reparado con el viewer modular: árbol visual main-vs-backup igual al HTML, DAE/texturas sin doble escala y resolver robusto para package://, data:model/* y rutas locales.

    IMPORTANTE: el entrypoint correcto del repo público es URDF_Viewer/urdfplus_viewer_main.js.
    Si llamas URDF_Viewer/usdplus_viewer_main.js y no lo subiste como alias, jsDelivr no cargará el viewer correcto.
    """
    if IA_Widgets:
        _register_colab_callback(api_base=api_base)

    try:
        if folder_path.lower().endswith(".zip") and os.path.isfile(folder_path):
            folder_path = Unzip_URDF(folder_path)
        if not os.path.isdir(folder_path):
            return HTML(f"<b style='color:red'>No existe la carpeta: {folder_path}</b>")

        urdf_path = _find_urdf_file(folder_path)
        if not urdf_path:
            return HTML(f"<b style='color:red'>No se encontró .urdf/.xml válido dentro de {folder_path}</b>")
        urdf_raw = _read_text(urdf_path)
        if "<robot" not in urdf_raw:
            return HTML("<b style='color:red'>El archivo encontrado no parece URDF/XML porque no contiene &lt;robot&gt;.</b>")

        module_mode_norm = str(module_mode or "cdn").strip().lower()
        if module_mode_norm not in ("inline", "cdn"):
            module_mode_norm = "cdn"

        local_root = _resolve_local_viewer_root(local_viewer_folder) if module_mode_norm == "inline" else None
        use_local_modules = bool(local_root and (local_viewer_folder or os.environ.get("AUTOMIND_URDF_VIEWER_LOCAL", "").lower() in ("1", "true", "yes")))

        commit = _resolve_latest_commit(repo=repo, branch=branch, timeout=timeout)
        viewer_url = _build_jsdelivr_url(commit["repo"], commit["sha"], compFile)
        embedded_modules = {}
        if module_mode_norm == "inline":
            if use_local_modules:
                embedded_modules = _collect_viewer_module_sources_local(local_root, compFile)
            else:
                embedded_modules = _collect_viewer_module_sources(commit["repo"], commit["sha"], compFile, timeout=timeout)
            probe = {
                "ok": True,
                "mode": "inline-local" if use_local_modules else "inline",
                "local_root": embedded_modules.get("local_root"),
                "root": embedded_modules.get("root"),
                "modules": embedded_modules.get("count"),
                "total_bytes": embedded_modules.get("total_bytes"),
            }
        else:
            probe = _probe_modular_viewer_entry(viewer_url, compFile=compFile, timeout=timeout, forbid_iframe_adapter=True)

        asset_db = _collect_asset_db(folder_path)
        urdf_zip_b64 = _zip_folder_to_base64(folder_path)
        rel_urdf_path = os.path.relpath(urdf_path, os.path.abspath(folder_path)).replace("\\", "/")
        folder_name = os.path.basename(os.path.abspath(folder_path)) or "URDF_Export"

        bg_css = "transparent" if background is None else f"#{int(background):06x}"
        bg_js = "null" if background is None else str(int(background))
        # BUILD145: por defecto no fuerza backup. El core decide igual que el HTML:
        # usa *_standard_tree_backup.urdf solo si el URDF+ principal no es visual-safe.
        prefer_standard_backup_js = "null" if prefer_standard_backup is None else str(bool(prefer_standard_backup)).lower()
        force_visual_backup_js = str(bool(force_visual_backup)).lower()
        visual_tree_mode = str(visual_tree_mode or "html_exact")

        html = fr"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover"/>
  <title>AutoMind URDF+ Modular Viewer · jsDelivr Direct</title>
  <style>
    :root {{ --vh: 1vh; }}
    html, body {{ margin:0; padding:0; width:100%; height:100dvh; overflow:hidden; background:{bg_css}; }}
    @supports not (height: 100dvh) {{ html, body {{ height: calc(var(--vh) * 100); }} }}
    body {{ padding-top: env(safe-area-inset-top); padding-right: env(safe-area-inset-right); padding-bottom: env(safe-area-inset-bottom); padding-left: env(safe-area-inset-left); }}
    #app {{ position:fixed; inset:0; width:100vw; height:100dvh; touch-action:none; background:{bg_css}; }}
    @supports not (height: 100dvh) {{ #app {{ height: calc(var(--vh) * 100); }} }}
    #automindError {{ position:fixed; left:16px; top:16px; right:16px; z-index:999999; display:none; font-family:Inter,Arial,sans-serif; color:#7a1111; background:#fff5f5; border:1px solid #f3b3b3; border-radius:12px; padding:12px; white-space:pre-wrap; max-height:45vh; overflow:auto; }}
    .badge {{ position:fixed; right:14px; bottom:10px; z-index:10; user-select:none; pointer-events:none; }}
    .badge img {{ max-height:40px; display:block; }}
  </style>
</head>
<body>
  <div id="app"></div>
  <pre id="automindError"></pre>
  <div style="padding-left:20px; overflow:visible; position:fixed; right:0; bottom:0; z-index:999999; pointer-events:none;">
    <div class="badge" style="display:inline-block; transform: scale(2.5) translateX(-15px); transform-origin: bottom right; margin:0; overflow:visible; pointer-events:none;">
      <img src="https://cdn.jsdelivr.net/gh/artemioadaysolvers/AutoMindCloudExperimental@main/AutoMindCloud/AutoMindCloud2.png" alt="AutoMind" style="display:block; height:40px; width:auto;"/>
    </div>
  </div>

  <script src="https://cdn.jsdelivr.net/gh/mrdoob/three.js@r132/build/three.min.js"></script>
  <script src="https://cdn.jsdelivr.net/gh/mrdoob/three.js@r132/examples/js/controls/OrbitControls.js"></script>
  <script src="https://cdn.jsdelivr.net/gh/mrdoob/three.js@r132/examples/js/controls/TrackballControls.js"></script>
  <script src="https://cdn.jsdelivr.net/gh/mrdoob/three.js@r132/examples/js/loaders/ColladaLoader.js"></script>
  <script src="https://cdn.jsdelivr.net/gh/mrdoob/three.js@r132/examples/js/loaders/STLLoader.js"></script>
  <script src="https://cdn.jsdelivr.net/gh/mrdoob/three.js@r132/examples/js/loaders/OBJLoader.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/jszip@3.10.1/dist/jszip.min.js"></script>

  <script type="module">
    const VIEWER_ENTRY_URL = {json.dumps(viewer_url)};
    const VIEWER_COMMIT_SHA = {json.dumps(commit['sha'])};
    const VIEWER_COMMIT_URL = {json.dumps(commit['html_url'])};
    const VIEWER_COMP_FILE = {json.dumps(compFile)};
    const VIEWER_PROBE = {json.dumps(probe)};
    const VIEWER_MODULE_MODE = {json.dumps(module_mode_norm)};
    const VIEWER_MODULE_SOURCES = {json.dumps(embedded_modules.get("sources", {}))};
    const VIEWER_MODULE_META = {json.dumps(embedded_modules.get("meta", {}))};
    globalThis.AutoMindURDFPlusDebug = {str(bool(debug)).lower()};
    globalThis.AUTOMIND_DEBUG = {str(bool(debug)).lower()};

    function showError(err) {{
      const box = document.getElementById('automindError');
      if (!box) return;
      box.style.display = 'block';
      box.textContent = err && (err.stack || err.message) ? (err.stack || err.message) : String(err);
    }}

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

    async function waitForViewerDependencies() {{
      // Igual al patrón del USD_Render_Script: las dependencias vienen en tags
      // <script src="https://cdn.jsdelivr.net/gh/mrdoob/three.js@r132/..."> clásicos, sin crossorigin.
      // No usamos cdn.jsdelivr.net/npm/three@.../examples/js/... porque en Colab puede entrar en ERR_TOO_MANY_REDIRECTS.
      // Eso evita el CORS que Colab dispara cuando se inyectan scripts con
      // script.crossOrigin='anonymous'. Aquí solo esperamos a que los globals existan.
      const checks = [
        ['THREE', () => !!window.THREE],
        ['THREE.OrbitControls', () => !!(window.THREE && THREE.OrbitControls)],
        ['THREE.TrackballControls', () => !!(window.THREE && THREE.TrackballControls)],
        ['THREE.ColladaLoader', () => !!(window.THREE && THREE.ColladaLoader)],
        ['THREE.STLLoader', () => !!(window.THREE && THREE.STLLoader)],
        ['THREE.OBJLoader', () => !!(window.THREE && THREE.OBJLoader)],
        ['window.JSZip', () => !!window.JSZip]
      ];
      const missing = new Set(checks.map(x => x[0]));
      for (let i = 0; i < 240 && missing.size; i++) {{
        for (const [label, fn] of checks) {{
          if (missing.has(label) && fn()) missing.delete(label);
        }}
        if (missing.size) await new Promise(r => setTimeout(r, 25));
      }}
      if (missing.size) {{
        throw new Error(
          'No pude cargar dependencias clásicas del viewer URDF+ desde jsDelivr:\n' +
          Array.from(missing).join('\n') +
          '\n\nEsto normalmente significa bloqueo de red/CDN, no problema del URDF.'
        );
      }}
    }}

    await waitForViewerDependencies();
    installTextureSafetyPatch();

    function applyVHVar() {{
      const viewport = window.visualViewport?.height || window.innerHeight || 600;
      document.documentElement.style.setProperty('--vh', `${{viewport * 0.01}}px`);
    }}
    function computeDesiredHeight() {{
      const viewportH = window.visualViewport?.height || window.innerHeight || document.documentElement.clientHeight || 0;
      const docScrollH = Math.max(document.documentElement?.scrollHeight || 0, document.body?.scrollHeight || 0);
      return Math.max(viewportH, docScrollH, 600);
    }}
    function setColabFrameHeight() {{
      const h = Math.ceil(computeDesiredHeight());
      try {{ if (window.google?.colab?.output?.setIframeHeight) window.google.colab.output.setIframeHeight(h, true); }} catch (_e) {{}}
    }}
    applyVHVar();
    const ro = new ResizeObserver(() => {{ applyVHVar(); setColabFrameHeight(); }});
    ro.observe(document.body);
    window.addEventListener('resize', () => {{ applyVHVar(); setColabFrameHeight(); }});
    if (window.visualViewport) window.visualViewport.addEventListener('resize', () => {{ applyVHVar(); setColabFrameHeight(); }});
    setTimeout(setColabFrameHeight, 60);

    function normalizeModulePath(path) {{
      const raw = String(path || '').replaceAll('\\', '/').split('?')[0].split('#')[0].replace(/^\/+/, '');
      const out = [];
      for (const part of raw.split('/')) {{
        if (!part || part === '.') continue;
        if (part === '..') {{ out.pop(); continue; }}
        out.push(part);
      }}
      return out.join('/');
    }}

    function resolveRelativeModulePath(basePath, rel) {{
      basePath = normalizeModulePath(basePath);
      const dir = basePath.includes('/') ? basePath.split('/').slice(0, -1).join('/') + '/' : '';
      return normalizeModulePath(dir + String(rel || ''));
    }}

    function extractRelativeDeps(code) {{
      const deps = [];
      const add = (x) => {{ if (x && !deps.includes(x)) deps.push(x); }};
      let m;
      const reFrom = /(?:import|export)\s+[\s\S]*?\s+from\s*['"](\.{{1,2}}\/[^'"]+)['"]/g;
      const reSide = /import\s*['"](\.{{1,2}}\/[^'"]+)['"]/g;
      while ((m = reFrom.exec(code || ''))) add(m[1]);
      while ((m = reSide.exec(code || ''))) add(m[1]);
      return deps;
    }}

    const __viewerBlobUrls = new Map();

    function rewriteRelativeImports(code, modulePath) {{
      const rewrite = (prefix, rel, suffix) => {{
        const depPath = resolveRelativeModulePath(modulePath, rel);
        const depUrl = __viewerBlobUrls.get(depPath);
        if (!depUrl) throw new Error('Dependencia modular no registrada: ' + rel + ' -> ' + depPath);
        return prefix + depUrl + suffix;
      }};
      return String(code || '')
        .replace(/((?:import|export)\s+[\s\S]*?\s+from\s*['"])(\.{{1,2}}\/[^'"]+)(['"])/g, (all, p, rel, s) => rewrite(p, rel, s))
        .replace(/(import\s*['"])(\.{{1,2}}\/[^'"]+)(['"])/g, (all, p, rel, s) => rewrite(p, rel, s));
    }}

    function buildEmbeddedModuleBlob(modulePath, stack = []) {{
      modulePath = normalizeModulePath(modulePath);
      if (__viewerBlobUrls.has(modulePath)) return __viewerBlobUrls.get(modulePath);
      const src = VIEWER_MODULE_SOURCES[modulePath];
      if (typeof src !== 'string') {{
        const available = Object.keys(VIEWER_MODULE_SOURCES || {{}}).join('\n - ');
        throw new Error('No está embebido el módulo: ' + modulePath + '\nDisponibles:\n - ' + available);
      }}
      if (stack.includes(modulePath)) throw new Error('Ciclo de imports ESM no soportado: ' + stack.concat([modulePath]).join(' -> '));
      for (const rel of extractRelativeDeps(src)) {{
        buildEmbeddedModuleBlob(resolveRelativeModulePath(modulePath, rel), stack.concat([modulePath]));
      }}
      const rewritten = rewriteRelativeImports(src, modulePath) + '\n//# sourceURL=automind-inline://' + modulePath + '\n';
      const url = URL.createObjectURL(new Blob([rewritten], {{ type: 'text/javascript' }}));
      __viewerBlobUrls.set(modulePath, url);
      return url;
    }}

    async function importCdnModule(entryUrl) {{
      const url = entryUrl + (entryUrl.includes('?') ? '&' : '?') + 'automind_sha=' + encodeURIComponent(VIEWER_COMMIT_SHA);
      try {{
        return await import(url);
      }} catch (err) {{
        const msg = err && (err.stack || err.message) ? (err.stack || err.message) : String(err);
        throw new Error('Falló import() del sistema modular URDF+.\nArchivo: ' + VIEWER_COMP_FILE + '\nURL: ' + url + '\n\n' + msg);
      }}
    }}

    async function importViewerModule(entryUrl) {{
      if (VIEWER_MODULE_MODE === 'inline') {{
        try {{
          const blobUrl = buildEmbeddedModuleBlob(VIEWER_COMP_FILE);
          return await import(blobUrl);
        }} catch (err) {{
          const msg = err && (err.stack || err.message) ? (err.stack || err.message) : String(err);
          throw new Error('Falló import() inline del sistema modular URDF+.\nArchivo: ' + VIEWER_COMP_FILE + '\nMódulos embebidos: ' + Object.keys(VIEWER_MODULE_SOURCES || {{}}).length + '\n\n' + msg);
        }}
      }}
      return await importCdnModule(entryUrl);
    }}

    const opts = {{
      container: document.getElementById('app'),
      URDF_Zip: {json.dumps(urdf_zip_b64)},
      urdfZipBase64: {json.dumps(urdf_zip_b64)},
      zipBase64: {json.dumps(urdf_zip_b64)},
      urdfContent: `{_esc_js_template(urdf_raw)}`,
      urdfText: `{_esc_js_template(urdf_raw)}`,
      robotXml: `{_esc_js_template(urdf_raw)}`,
      urdfFilename: {json.dumps(os.path.basename(urdf_path))},
      urdfPath: {json.dumps(rel_urdf_path)},
      rootFolderName: {json.dumps(folder_name)},
      assetDB: {json.dumps(asset_db)},
      modelFormat: 'URDF+',
      isURDFPlus: true,
      selectMode: {json.dumps(select_mode)},
      background: {bg_js},
      pixelRatio: Math.min(window.devicePixelRatio || 1, 2),
      autoResize: true,
      IA_Widgets: {str(bool(IA_Widgets)).lower()},
      debug: {str(bool(debug)).lower()},
      commitSha: VIEWER_COMMIT_SHA,
      commitUrl: VIEWER_COMMIT_URL,
      probe: VIEWER_PROBE,
      build: 'BUILD145_ColladaInlineBase64Textures',
      visualTreeMode: {json.dumps(visual_tree_mode)},
      htmlExactVisualTree: true,
      preferStandardBackup: {prefer_standard_backup_js},
      forceVisualBackup: {force_visual_backup_js},
      textureResolverMode: 'html_build138',
      keepValidColladaTextures: true,
      disableDaeUnitMultiplication: true,
      forceInlineBase64ColladaTextures: true,
      colladaTextureTransferMode: 'inline_base64',
      disableStandaloneIframe: true
    }};

    try {{
      const mod = await importViewerModule(VIEWER_ENTRY_URL);
      if (!mod || typeof mod.render !== 'function') throw new Error('El módulo cargó, pero no exporta render(opts): ' + VIEWER_COMP_FILE);
      const app = mod.render(opts);
      window.AutoMindURDFPlusApp = app;
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
      if (app?.ready?.then) app.ready.catch(showError);
    }} catch (err) {{
      showError(err);
    }}
  </script>
</body>
</html>
"""
        return HTML(html)
    except Exception as e:
        return _html_error("Error preparando URDF+", str(e))


def URDF_Viewer(*args, **kwargs):
    return URDF_Visualization(*args, **kwargs)


def URDF_Render(*args, **kwargs):
    return URDF_Visualization(*args, **kwargs)
