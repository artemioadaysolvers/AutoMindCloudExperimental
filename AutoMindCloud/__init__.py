```python
# AutoMindCloud/__init__.py
# Muestra el logo y envía AutoMind_Info a Firestore silenciosamente.
#
# Sistema de carga:
# 1. Python consulta GitHub para obtener el SHA actual de main.
# 2. Python valida la URL inmutable de jsDelivr con ese SHA.
# 3. El navegador importa exactamente ese módulo JS.
# 4. No se muestran estados, resultados ni errores en la celda.

import json
import os
import re
import shutil
import zipfile

import requests


__all__ = [
    "Download_Zip",
    "diagnostico_automind_firestore",
    "reenviar_automind_firestore",
]


_VERSION = "automindcloud-init-python-sha-jsdelivr-silent-2026-07-04-01"

_LOGO_URL = (
    "https://raw.githubusercontent.com/"
    "Arthemioxz/AutoMindCloudExperimental/main/"
    "AutoMindCloud/AutoMindCloud2.png"
)

_JS_GITHUB_OWNER = "artemioadaysolvers"
_JS_GITHUB_REPO = "AutoMindCloud-API"
_JS_BRANCH = "main"
_JS_MODULE_PATH = "Data_Collector/automind-firestore.js"

_GET_NOTEBOOK_TIMEOUT_SEC = 2
_GITHUB_TIMEOUT_SEC = 25
_JSDELIVR_TIMEOUT_SEC = 35

_LAST_PYTHON_ERROR = None
_LAST_COMMIT = None
_LAST_MODULE_URL = None


def _mostrar_logo():
    """Muestra únicamente el logo de AutoMindCloud."""
    try:
        from IPython.display import Image, display

        display(Image(
            url=_LOGO_URL,
            width=700
        ))
    except Exception:
        pass


def Download_Zip(Drive_Link, Output_Name="USDModel"):
    """Descarga un ZIP de Google Drive, lo descomprime y devuelve /content/Output_Name."""
    root_dir = "/content"

    file_id = Drive_Link.split("/d/")[1].split("/")[0]
    url = "https://drive.google.com/uc?id=" + file_id

    zip_path = os.path.join(root_dir, Output_Name + ".zip")
    tmp_extract = os.path.join(root_dir, "__tmp_extract_" + Output_Name)
    final_dir = os.path.join(root_dir, Output_Name)

    if os.path.exists(tmp_extract):
        shutil.rmtree(tmp_extract)

    if os.path.exists(final_dir):
        shutil.rmtree(final_dir)

    os.makedirs(tmp_extract, exist_ok=True)

    import gdown

    gdown.download(url, zip_path, quiet=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(tmp_extract)

    def es_archivo_oculto(nombre):
        return nombre.startswith(".") or nombre == "__MACOSX"

    visibles = [
        nombre
        for nombre in os.listdir(tmp_extract)
        if not es_archivo_oculto(nombre)
    ]

    if len(visibles) == 1:
        posible_dir = os.path.join(tmp_extract, visibles[0])

        if os.path.isdir(posible_dir):
            shutil.move(posible_dir, final_dir)
            shutil.rmtree(tmp_extract, ignore_errors=True)
            return final_dir

    os.makedirs(final_dir, exist_ok=True)

    for nombre in visibles:
        shutil.move(
            os.path.join(tmp_extract, nombre),
            os.path.join(final_dir, nombre)
        )

    shutil.rmtree(tmp_extract, ignore_errors=True)

    return final_dir


def _obtener_automind_info():
    """Lee AutoMind_Info desde los metadatos del notebook actual."""
    try:
        from google.colab import _message

        respuesta = _message.blocking_request(
            "get_ipynb",
            timeout_sec=_GET_NOTEBOOK_TIMEOUT_SEC
        )

        notebook = respuesta.get("ipynb", {})

        if isinstance(notebook, str):
            notebook = json.loads(notebook)

        if not isinstance(notebook, dict):
            return {"Estado": "Notebook no valido"}

        auto_mind_info = (
            notebook
            .get("metadata", {})
            .get("AutoMind_Info")
        )

        if not isinstance(auto_mind_info, dict):
            return {"Estado": "AutoMind_Info no encontrada"}

        return auto_mind_info

    except Exception as error:
        return {
            "Estado": "No fue posible leer AutoMind_Info",
            "Detalle": str(error)
        }


def _json_seguro_para_javascript(data):
    """Convierte datos Python a JSON seguro para insertar en JavaScript."""
    texto = json.dumps(data, ensure_ascii=False)

    texto = texto.replace("<", "\\u003c")
    texto = texto.replace(">", "\\u003e")
    texto = texto.replace("&", "\\u0026")
    texto = texto.replace("\u2028", "\\u2028")
    texto = texto.replace("\u2029", "\\u2029")

    return texto


def _resolver_ultimo_commit(repo, branch="main", timeout=25):
    """
    Obtiene en Python el SHA actual de repo@branch.

    Así el navegador recibe una URL inmutable:
    https://cdn.jsdelivr.net/gh/usuario/repositorio@SHA/archivo.js
    """
    repo = str(repo or "").strip().strip("/")
    branch = str(branch or "main").strip()

    if not repo or "/" not in repo:
        raise ValueError(
            "repo debe tener formato 'usuario/repositorio'."
        )

    api_url = f"https://api.github.com/repos/{repo}/commits/{branch}"

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "AutoMindCloud",
    }

    response = requests.get(
        api_url,
        headers=headers,
        timeout=timeout
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"GitHub no pudo resolver {repo}@{branch}. "
            f"HTTP {response.status_code}: {response.text[:500]}"
        )

    data = response.json()

    sha = str(data.get("sha") or "").strip()

    if not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        raise RuntimeError(
            f"GitHub devolvió un SHA inválido: {sha!r}"
        )

    commit = data.get("commit") or {}

    return {
        "repo": repo,
        "branch": branch,
        "sha": sha,
        "short_sha": sha[:7],
        "message": str(commit.get("message") or "").splitlines()[0].strip(),
        "html_url": data.get("html_url") or (
            f"https://github.com/{repo}/commit/{sha}"
        ),
        "api_url": api_url,
    }


def _crear_url_jsdelivr(repo, sha, module_path):
    """Construye una URL jsDelivr inmutable, fijada al SHA."""
    ruta = str(module_path or "").strip().replace("\\", "/").lstrip("/")

    if not ruta:
        raise ValueError("La ruta del módulo JavaScript está vacía.")

    return f"https://cdn.jsdelivr.net/gh/{repo}@{sha}/{ruta}"


def _validar_modulo_jsdelivr(url, timeout=35):
    """
    Comprueba desde Python que jsDelivr responde un archivo y no HTML de error.
    """
    response = requests.get(
        url,
        headers={"User-Agent": "AutoMindCloud"},
        timeout=timeout
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"jsDelivr no encontró el módulo. "
            f"HTTP {response.status_code}: {url}"
        )

    muestra = (response.text or "")[:4096]
    muestra_limpia = muestra.lstrip().lower()

    if (
        muestra_limpia.startswith("<!doctype")
        or muestra_limpia.startswith("<html")
    ):
        raise RuntimeError(
            "La URL de jsDelivr devolvió HTML en vez de JavaScript."
        )

    return {
        "ok": True,
        "content_type": response.headers.get("content-type", ""),
        "bytes_sampled": len(muestra),
    }


def _crear_script_automind(auto_mind_info, commit, module_url):
    """
    Crea el JavaScript embebido.

    Silencia exclusivamente mensajes que contengan [AutoMindCloud].
    Conserva el resultado y errores para diagnóstico manual:
      - window.__AutoMindCloud_lastResult
      - window.__AutoMindCloud_lastError
      - window.__AutoMindCloud_lastModuleUrl
    """
    auto_mind_json = _json_seguro_para_javascript(auto_mind_info)
    commit_json = _json_seguro_para_javascript(commit)
    module_url_json = json.dumps(module_url)

    lineas = []

    lineas.append("(async function () {")
    lineas.append("  const autoMindInfo = " + auto_mind_json + ";")
    lineas.append("  const commitInfo = " + commit_json + ";")
    lineas.append("  const moduleUrl = " + module_url_json + ";")
    lineas.append("")
    lineas.append("  function instalarFiltroAutoMindConsole() {")
    lineas.append("    if (window.__AutoMindCloud_consoleFilterInstalled) return;")
    lineas.append("")
    lineas.append("    window.__AutoMindCloud_consoleFilterInstalled = true;")
    lineas.append("")
    lineas.append("    const metodos = ['log', 'info', 'warn', 'error', 'debug'];")
    lineas.append("")
    lineas.append("    for (const metodo of metodos) {")
    lineas.append("      const original = console[metodo];")
    lineas.append("")
    lineas.append("      if (typeof original !== 'function') continue;")
    lineas.append("")
    lineas.append("      console[metodo] = function (...args) {")
    lineas.append("        const esMensajeAutoMind = args.some((arg) => {")
    lineas.append("          try {")
    lineas.append("            return String(arg).includes('[AutoMindCloud]');")
    lineas.append("          } catch (_) {")
    lineas.append("            return false;")
    lineas.append("          }")
    lineas.append("        });")
    lineas.append("")
    lineas.append("        if (esMensajeAutoMind) return;")
    lineas.append("")
    lineas.append("        return original.apply(console, args);")
    lineas.append("      };")
    lineas.append("    }")
    lineas.append("  }")
    lineas.append("")
    lineas.append("  instalarFiltroAutoMindConsole();")
    lineas.append("")
    lineas.append("  try {")
    lineas.append("    window.__AutoMindCloud_commitUrl = commitInfo.api_url || null;")
    lineas.append("    window.__AutoMindCloud_latestSha = commitInfo.sha || null;")
    lineas.append("    window.__AutoMindCloud_lastModuleUrl = moduleUrl;")
    lineas.append("    window.__AutoMindCloud_lastCommit = commitInfo;")
    lineas.append("")
    lineas.append("    const importUrl = moduleUrl +")
    lineas.append("      (moduleUrl.includes('?') ? '&' : '?') +")
    lineas.append("      'automind_sha=' + encodeURIComponent(commitInfo.sha || '');")
    lineas.append("")
    lineas.append("    const modulo = await import(importUrl);")
    lineas.append("")
    lineas.append("    if (!modulo || typeof modulo.enviarAutoMindFirestore !== 'function') {")
    lineas.append("      throw new Error(")
    lineas.append("        'No existe enviarAutoMindFirestore en el módulo cargado.'")
    lineas.append("      );")
    lineas.append("    }")
    lineas.append("")
    lineas.append("    const resultado = await modulo.enviarAutoMindFirestore(autoMindInfo);")
    lineas.append("")
    lineas.append("    if (!resultado || resultado.ok !== true) {")
    lineas.append("      throw new Error(")
    lineas.append("        'Firestore respondió error: ' + JSON.stringify(resultado)")
    lineas.append("      );")
    lineas.append("    }")
    lineas.append("")
    lineas.append("    window.__AutoMindCloud_lastResult = resultado;")
    lineas.append("    window.__AutoMindCloud_lastError = null;")
    lineas.append("")
    lineas.append("  } catch (error) {")
    lineas.append("    window.__AutoMindCloud_lastError = {")
    lineas.append("      name: error && error.name ? error.name : null,")
    lineas.append("      code: error && error.code ? error.code : null,")
    lineas.append("      message: error && error.message")
    lineas.append("        ? error.message")
    lineas.append("        : String(error),")
    lineas.append("      commitUrl: window.__AutoMindCloud_commitUrl || null,")
    lineas.append("      latestSha: window.__AutoMindCloud_latestSha || null,")
    lineas.append("      moduleUrl: window.__AutoMindCloud_lastModuleUrl || null")
    lineas.append("    };")
    lineas.append("  }")
    lineas.append("})();")

    return "\n".join(lineas)


def reenviar_automind_firestore():
    """
    Consulta GitHub y jsDelivr desde Python, luego inserta el script silencioso.
    """
    global _LAST_PYTHON_ERROR
    global _LAST_COMMIT
    global _LAST_MODULE_URL

    try:
        from IPython.display import HTML, display

        repo = f"{_JS_GITHUB_OWNER}/{_JS_GITHUB_REPO}"

        commit = _resolver_ultimo_commit(
            repo=repo,
            branch=_JS_BRANCH,
            timeout=_GITHUB_TIMEOUT_SEC
        )

        module_url = _crear_url_jsdelivr(
            repo=commit["repo"],
            sha=commit["sha"],
            module_path=_JS_MODULE_PATH
        )

        _validar_modulo_jsdelivr(
            url=module_url,
            timeout=_JSDELIVR_TIMEOUT_SEC
        )

        _LAST_COMMIT = commit
        _LAST_MODULE_URL = module_url
        _LAST_PYTHON_ERROR = None

        auto_mind_info = _obtener_automind_info()

        script = _crear_script_automind(
            auto_mind_info=auto_mind_info,
            commit=commit,
            module_url=module_url
        )

        display(HTML("<script>" + script + "</script>"))

        return True

    except Exception as error:
        _LAST_PYTHON_ERROR = {
            "name": type(error).__name__,
            "message": str(error),
        }

        return False


def diagnostico_automind_firestore():
    """
    Devuelve diagnóstico sin imprimir ni mostrar nada automáticamente.
    """
    return {
        "version": _VERSION,
        "archivo": globals().get("__file__", "desconocido"),
        "github_owner_js": _JS_GITHUB_OWNER,
        "github_repo_js": _JS_GITHUB_REPO,
        "branch_js": _JS_BRANCH,
        "module_path_js": _JS_MODULE_PATH,
        "usa_github_api_en_python": True,
        "usa_jsdelivr_fijado_a_sha": True,
        "usa_main_directamente_en_jsdelivr": False,
        "modo_silencioso": True,
        "muestra_logo": True,
        "ultimo_commit": _LAST_COMMIT,
        "ultima_url_jsdelivr": _LAST_MODULE_URL,
        "ultimo_error_python": _LAST_PYTHON_ERROR,
    }


# Al importar AutoMindCloud:
# 1. Se muestra el logo.
# 2. Python consulta el SHA actual de main.
# 3. Se valida jsDelivr.
# 4. Se ejecuta el envío sin mensajes visibles.
_mostrar_logo()
reenviar_automind_firestore()
```
