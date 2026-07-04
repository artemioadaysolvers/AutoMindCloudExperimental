# AutoMindCloud/__init__.py
# Consulta dentro del codigo el ultimo commit de automind-firestore.js
# y carga jsDelivr fijado a ese SHA.

import json
import os
import shutil
import uuid
import zipfile

 
__all__ = [
    "Download_Zip",
    "diagnostico_automind_firestore",
    "reenviar_automind_firestore",
]


_VERSION = "automindcloud-init-commit-lookup-2026-07-03-02"

_LOGO_URL = (
    "https://raw.githubusercontent.com/"
    "Arthemioxz/AutoMindCloudExperimental/main/"
    "AutoMindCloud/AutoMindCloud2.png"
)

_CLICK_SOUND_URL = (
    "https://raw.githubusercontent.com/"
    "Arthemioxz/AutoMindCloudExperimental/main/"
    "AutoMindCloud/click_sound.mp3"
)

_JS_GITHUB_OWNER = "artemioadaysolvers"
_JS_GITHUB_REPO = "AutoMindCloud-API"
_JS_MODULE_PATH = "Data_Collector/automind-firestore.js"
_GET_NOTEBOOK_TIMEOUT_SEC = 2
_SHOW_AUTOMIND_STATUS = True


def _mostrar_logo():
    try:
        from IPython.display import Image
        from IPython.display import display

        display(Image(url=_LOGO_URL, width=700))

    except Exception:
        pass


def _descargar_click_sound():
    try:
        import requests

        if os.path.exists("click_sound.mp3"):
            return

        response = requests.get(_CLICK_SOUND_URL, timeout=10)

        if response.status_code == 200:
            with open("click_sound.mp3", "wb") as archivo:
                archivo.write(response.content)

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

    os.makedirs(tmp_extract, exist_ok=True)

    if os.path.exists(final_dir):
        shutil.rmtree(final_dir)

    import gdown

    gdown.download(url, zip_path, quiet=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(tmp_extract)

    def junk(name):
        return name.startswith(".") or name == "__MACOSX"

    visibles = [n for n in os.listdir(tmp_extract) if not junk(n)]

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

        auto_mind_info = notebook.get("metadata", {}).get("AutoMind_Info")

        if not isinstance(auto_mind_info, dict):
            return {"Estado": "AutoMind_Info no encontrada"}

        return auto_mind_info

    except Exception as error:
        return {
            "Estado": "No fue posible leer AutoMind_Info",
            "Detalle": str(error)
        }


def _json_seguro_para_javascript(data):
    texto = json.dumps(data, ensure_ascii=False)
    texto = texto.replace("<", "\\u003c")
    texto = texto.replace(">", "\\u003e")
    texto = texto.replace("&", "\\u0026")
    texto = texto.replace("\u2028", "\\u2028")
    texto = texto.replace("\u2029", "\\u2029")
    return texto


def _crear_script_automind(auto_mind_info, status_id):
    auto_mind_json = _json_seguro_para_javascript(auto_mind_info)
    owner_json = json.dumps(_JS_GITHUB_OWNER)
    repo_json = json.dumps(_JS_GITHUB_REPO)
    module_path_json = json.dumps(_JS_MODULE_PATH)
    status_id_json = json.dumps(status_id)

    lineas = []
    lineas.append("(async function () {")
    lineas.append("  const statusId = " + status_id_json + ";")
    lineas.append("  const statusEl = document.getElementById(statusId);")
    lineas.append("  function show(message, data) {")
    lineas.append("    if (!statusEl) return;")
    lineas.append("    let text = '[AutoMindCloud] ' + message;")
    lineas.append("    if (data !== undefined) {")
    lineas.append("      try {")
    lineas.append("        text += '\\n' + JSON.stringify(data, null, 2);")
    lineas.append("      } catch (_) {")
    lineas.append("        text += '\\n' + String(data);")
    lineas.append("      }")
    lineas.append("    }")
    lineas.append("    statusEl.textContent = text;")
    lineas.append("  }")
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
    lineas.append("    show('Consultando commit real en GitHub...', { githubCommitUrl });")
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
    lineas.append("    show('Commit encontrado. Cargando jsDelivr con SHA...', {")
    lineas.append("      latestSha,")
    lineas.append("      moduleUrl,")
    lineas.append("      commitMessage: latestCommit.commit && latestCommit.commit.message")
    lineas.append("    });")
    lineas.append("")
    lineas.append("    const modulo = await import(moduleUrl);")
    lineas.append("")
    lineas.append("    if (!modulo || typeof modulo.enviarAutoMindFirestore !== 'function') {")
    lineas.append("      throw new Error('No existe enviarAutoMindFirestore en el modulo cargado.');")
    lineas.append("    }")
    lineas.append("")
    lineas.append("    show('Modulo cargado. Enviando a Firestore...', { latestSha, moduleUrl });")
    lineas.append("    const resultado = await modulo.enviarAutoMindFirestore(autoMindInfo);")
    lineas.append("    window.__AutoMindCloud_lastResult = resultado;")
    lineas.append("")
    lineas.append("    if (!resultado || resultado.ok !== true) {")
    lineas.append("      throw new Error('Firestore respondio error: ' + JSON.stringify(resultado));")
    lineas.append("    }")
    lineas.append("")
    lineas.append("    show('Guardado correctamente en Firestore.', resultado);")
    lineas.append("  } catch (error) {")
    lineas.append("    const errorInfo = {")
    lineas.append("      name: error && error.name,")
    lineas.append("      code: error && error.code,")
    lineas.append("      message: error && error.message,")
    lineas.append("      commitUrl: window.__AutoMindCloud_commitUrl || null,")
    lineas.append("      latestSha: window.__AutoMindCloud_latestSha || null,")
    lineas.append("      moduleUrl: window.__AutoMindCloud_lastModuleUrl || null")
    lineas.append("    };")
    lineas.append("    window.__AutoMindCloud_lastError = errorInfo;")
    lineas.append("    show('ERROR', errorInfo);")
    lineas.append("    console.error('[AutoMindCloud] Error durante envio:', error);")
    lineas.append("  }")
    lineas.append("})();")

    return "\n".join(lineas)


def reenviar_automind_firestore():
    try:
        from IPython.display import HTML
        from IPython.display import display

        auto_mind_info = _obtener_automind_info()
        instance_id = "automind_sender_" + uuid.uuid4().hex
        status_id = instance_id + "_status"
        script = _crear_script_automind(auto_mind_info, status_id)

        html = ""

        if _SHOW_AUTOMIND_STATUS:
            html += '<pre id="' + status_id + '" style="'
            html += "white-space:pre-wrap;"
            html += "font:12px/1.45 monospace;"
            html += "background:#111827;"
            html += "color:#d1fae5;"
            html += "border:1px solid #374151;"
            html += "border-radius:6px;"
            html += "padding:10px;"
            html += "margin:8px 0;"
            html += '">[AutoMindCloud] Preparando envio...</pre>'
        else:
            html += '<div id="' + status_id + '" style="display:none"></div>'

        html += "<script>"
        html += script
        html += "</script>"

        display(HTML(html))
        return True

    except Exception as error:
        try:
            from IPython.display import HTML
            from IPython.display import display

            mensaje = json.dumps(str(error))
            display(HTML("<pre>[AutoMindCloud] Error Python: " + mensaje + "</pre>"))
        except Exception:
            pass

        return False


def diagnostico_automind_firestore():
    info = {
        "version": _VERSION,
        "archivo": globals().get("__file__", "desconocido"),
        "github_owner_js": _JS_GITHUB_OWNER,
        "github_repo_js": _JS_GITHUB_REPO,
        "module_path_js": _JS_MODULE_PATH,
        "consulta_commit_dentro_del_codigo": True,
        "usa_jsdelivr_con_sha": True,
        "usa_main_en_jsdelivr": False,
    }

    print(json.dumps(info, indent=2, ensure_ascii=False))
    return info


_mostrar_logo()
_descargar_click_sound()
reenviar_automind_firestore()
