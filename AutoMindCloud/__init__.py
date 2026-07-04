# AutoMindCloud/**init**.py

# Muestra el logo y envía AutoMind_Info a Firestore silenciosamente.

import json
import os
import shutil
import zipfile

**all** = [
"Download_Zip",
"diagnostico_automind_firestore",
"reenviar_automind_firestore",
]

_VERSION = "automindcloud-init-silent-logo-2026-07-04-01"

_LOGO_URL = (
"https://raw.githubusercontent.com/"
"Arthemioxz/AutoMindCloudExperimental/main/"
"AutoMindCloud/AutoMindCloud2.png"
)

_JS_GITHUB_OWNER = "artemioadaysolvers"
_JS_GITHUB_REPO = "AutoMindCloud-API"
_JS_MODULE_PATH = "Data_Collector/automind-firestore.js"

_GET_NOTEBOOK_TIMEOUT_SEC = 2

def _mostrar_logo():
"""Muestra únicamente el logo de AutoMindCloud."""
try:
from IPython.display import Image, display

```
    display(Image(
        url=_LOGO_URL,
        width=700
    ))

except Exception:
    pass
```

def Download_Zip(Drive_Link, Output_Name="USDModel"):
"""Descarga un ZIP de Google Drive, lo descomprime y devuelve /content/Output_Name."""
root_dir = "/content"

```
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
```

def _obtener_automind_info():
"""Lee AutoMind_Info desde los metadatos del notebook actual."""
try:
from google.colab import _message

```
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
```

def _json_seguro_para_javascript(data):
"""Convierte datos Python a JSON seguro para insertar dentro de JavaScript."""
texto = json.dumps(data, ensure_ascii=False)

```
texto = texto.replace("<", "\\u003c")
texto = texto.replace(">", "\\u003e")
texto = texto.replace("&", "\\u0026")
texto = texto.replace("\u2028", "\\u2028")
texto = texto.replace("\u2029", "\\u2029")

return texto
```

def _crear_script_automind(auto_mind_info):
"""
Crea el script JavaScript silencioso.

```
No genera:
- <pre>
- alertas
- prints visibles
- console.log
- console.error

Para diagnóstico manual:
- window.__AutoMindCloud_lastResult
- window.__AutoMindCloud_lastError
"""
auto_mind_json = _json_seguro_para_javascript(auto_mind_info)
owner_json = json.dumps(_JS_GITHUB_OWNER)
repo_json = json.dumps(_JS_GITHUB_REPO)
module_path_json = json.dumps(_JS_MODULE_PATH)

lineas = []

lineas.append("(async function () {")
lineas.append("  try {")
lineas.append("    const autoMindInfo = " + auto_mind_json + ";")
lineas.append("    const owner = " + owner_json + ";")
lineas.append("    const repo = " + repo_json + ";")
lineas.append("    const modulePath = " + module_path_json + ";")
lineas.append("")
lineas.append("    const params = new URLSearchParams();")
lineas.append("    params.set('path', modulePath);")
lineas.append("    params.set('per_page', '1');")
lineas.append("")
lineas.append("    const githubCommitUrl =")
lineas.append("      'https://api.github.com/repos/' +")
lineas.append("      owner + '/' +")
lineas.append("      repo +")
lineas.append("      '/commits?' +")
lineas.append("      params.toString();")
lineas.append("")
lineas.append("    window.__AutoMindCloud_commitUrl = githubCommitUrl;")
lineas.append("")
lineas.append("    const commitResponse = await fetch(githubCommitUrl, {")
lineas.append("      cache: 'no-store',")
lineas.append("      headers: {")
lineas.append("        Accept: 'application/vnd.github+json'")
lineas.append("      }")
lineas.append("    });")
lineas.append("")
lineas.append("    if (!commitResponse.ok) {")
lineas.append("      throw new Error('GitHub commit lookup failed: ' + commitResponse.status);")
lineas.append("    }")
lineas.append("")
lineas.append("    const commits = await commitResponse.json();")
lineas.append("    const latestCommit = commits && commits[0];")
lineas.append("    const latestSha = latestCommit && latestCommit.sha;")
lineas.append("")
lineas.append("    if (!latestSha || !/^[0-9a-f]{40}$/i.test(latestSha)) {")
lineas.append("      throw new Error('GitHub no devolvio un SHA valido.');")
lineas.append("    }")
lineas.append("")
lineas.append("    const moduleUrl =")
lineas.append("      'https://cdn.jsdelivr.net/gh/' +")
lineas.append("      owner + '/' +")
lineas.append("      repo +")
lineas.append("      '@' +")
lineas.append("      latestSha + '/' +")
lineas.append("      modulePath;")
lineas.append("")
lineas.append("    window.__AutoMindCloud_latestSha = latestSha;")
lineas.append("    window.__AutoMindCloud_lastModuleUrl = moduleUrl;")
lineas.append("")
lineas.append("    const modulo = await import(moduleUrl);")
lineas.append("")
lineas.append("    if (!modulo || typeof modulo.enviarAutoMindFirestore !== 'function') {")
lineas.append("      throw new Error('No existe enviarAutoMindFirestore en el modulo cargado.');")
lineas.append("    }")
lineas.append("")
lineas.append("    const resultado = await modulo.enviarAutoMindFirestore(autoMindInfo);")
lineas.append("")
lineas.append("    if (!resultado || resultado.ok !== true) {")
lineas.append("      throw new Error('Firestore respondio error: ' + JSON.stringify(resultado));")
lineas.append("    }")
lineas.append("")
lineas.append("    window.__AutoMindCloud_lastResult = resultado;")
lineas.append("    window.__AutoMindCloud_lastError = null;")
lineas.append("")
lineas.append("  } catch (error) {")
lineas.append("    window.__AutoMindCloud_lastError = {")
lineas.append("      name: error && error.name ? error.name : null,")
lineas.append("      code: error && error.code ? error.code : null,")
lineas.append("      message: error && error.message ? error.message : String(error),")
lineas.append("      commitUrl: window.__AutoMindCloud_commitUrl || null,")
lineas.append("      latestSha: window.__AutoMindCloud_latestSha || null,")
lineas.append("      moduleUrl: window.__AutoMindCloud_lastModuleUrl || null")
lineas.append("    };")
lineas.append("  }")
lineas.append("})();")

return "\n".join(lineas)
```

def reenviar_automind_firestore():
"""
Inserta el script en el frontend de Colab.

```
No muestra estados, resultados ni errores.
"""
try:
    from IPython.display import HTML, display

    auto_mind_info = _obtener_automind_info()
    script = _crear_script_automind(auto_mind_info)

    display(HTML("<script>" + script + "</script>"))

    return True

except Exception:
    return False
```

def diagnostico_automind_firestore():
"""Devuelve datos técnicos sin imprimirlos."""
return {
"version": _VERSION,
"archivo": globals().get("**file**", "desconocido"),
"github_owner_js": _JS_GITHUB_OWNER,
"github_repo_js": _JS_GITHUB_REPO,
"module_path_js": _JS_MODULE_PATH,
"consulta_commit_dentro_del_codigo": True,
"usa_jsdelivr_con_sha": True,
"usa_main_en_jsdelivr": False,
"modo_silencioso": True,
"muestra_logo": True,
}

# Al importar AutoMindCloud:

# 1. Muestra solo el logo.

# 2. Envía AutoMind_Info silenciosamente a Firestore.

_mostrar_logo()
reenviar_automind_firestore()
