# AutoMindCloud/__init__.py
# Envia AutoMind_Info automaticamente al importar el paquete.

import json
import uuid
import html as html_lib


__all__ = [
    "diagnostico_automind_firestore",
    "reenviar_automind_firestore",
]


_VERSION = "automind-html-debug-2026-07-03-04"
_GITHUB_OWNER = "artemioadaysolvers"
_GITHUB_REPO = "AutoMindCloud-API"
_MODULE_PATH = "Data_Collector/automind-firestore.js"
_GET_NOTEBOOK_TIMEOUT_SEC = 2


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


def _crear_script(auto_mind_info, status_id):
    auto_mind_json = _json_seguro_para_javascript(auto_mind_info)
    owner_json = json.dumps(_GITHUB_OWNER)
    repo_json = json.dumps(_GITHUB_REPO)
    path_json = json.dumps(_MODULE_PATH)
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
    lineas.append("    show('Iniciando envio...');")
    lineas.append("    const autoMindInfo = " + auto_mind_json + ";")
    lineas.append("    const owner = " + owner_json + ";")
    lineas.append("    const repo = " + repo_json + ";")
    lineas.append("    const modulePath = " + path_json + ";")
    lineas.append("    const params = new URLSearchParams();")
    lineas.append("    params.set('path', modulePath);")
    lineas.append("    params.set('per_page', '1');")
    lineas.append("    const githubApiUrl = 'https://api.github.com/repos/' + owner + '/' + repo + '/commits?' + params.toString();")
    lineas.append("    show('Consultando ultimo commit...', { githubApiUrl });")
    lineas.append("    const commitResponse = await fetch(githubApiUrl, {")
    lineas.append("      cache: 'no-store',")
    lineas.append("      headers: { Accept: 'application/vnd.github+json' }")
    lineas.append("    });")
    lineas.append("    if (!commitResponse.ok) {")
    lineas.append("      throw new Error('GitHub commit lookup failed: ' + commitResponse.status);")
    lineas.append("    }")
    lineas.append("    const commits = await commitResponse.json();")
    lineas.append("    const latestSha = commits && commits[0] && commits[0].sha;")
    lineas.append("    if (!latestSha || !/^[0-9a-f]{40}$/i.test(latestSha)) {")
    lineas.append("      throw new Error('GitHub no devolvio un SHA valido.');")
    lineas.append("    }")
    lineas.append("    const moduleUrl = 'https://cdn.jsdelivr.net/gh/' + owner + '/' + repo + '@' + latestSha + '/' + modulePath;")
    lineas.append("    window.__AutoMindCloud_lastModuleUrl = moduleUrl;")
    lineas.append("    show('Cargando modulo desde jsDelivr...', { latestSha, moduleUrl });")
    lineas.append("    const modulo = await import(moduleUrl);")
    lineas.append("    if (!modulo || typeof modulo.enviarAutoMindFirestore !== 'function') {")
    lineas.append("      throw new Error('No existe enviarAutoMindFirestore en el modulo cargado.');")
    lineas.append("    }")
    lineas.append("    show('Modulo cargado. Enviando a Firestore...', { latestSha, moduleUrl });")
    lineas.append("    const resultado = await modulo.enviarAutoMindFirestore(autoMindInfo);")
    lineas.append("    window.__AutoMindCloud_lastResult = resultado;")
    lineas.append("    if (!resultado || resultado.ok !== true) {")
    lineas.append("      throw new Error('Firestore respondio error: ' + JSON.stringify(resultado));")
    lineas.append("    }")
    lineas.append("    show('Guardado correctamente.', resultado);")
    lineas.append("  } catch (error) {")
    lineas.append("    const errorInfo = {")
    lineas.append("      name: error && error.name,")
    lineas.append("      code: error && error.code,")
    lineas.append("      message: error && error.message,")
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

        print("[AutoMindCloud] __init__ cargado")
        print("version:", _VERSION)
        print("archivo:", globals().get("__file__", "desconocido"))

        auto_mind_info = _obtener_automind_info()
        instance_id = "automind_sender_" + uuid.uuid4().hex
        status_id = instance_id + "_status"
        script = _crear_script(auto_mind_info, status_id)

        header = "[AutoMindCloud] __init__ cargado"
        header += "\nversion: " + _VERSION
        header += "\narchivo: " + globals().get("__file__", "desconocido")

        html = '<pre style="'
        html += "white-space:pre-wrap;"
        html += "font:12px/1.45 monospace;"
        html += "background:#1f2937;"
        html += "color:#e5e7eb;"
        html += "border:1px solid #4b5563;"
        html += "border-radius:6px;"
        html += "padding:10px;"
        html += "margin:8px 0;"
        html += '">' + html_lib.escape(header) + "</pre>"

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
        "github_owner": _GITHUB_OWNER,
        "github_repo": _GITHUB_REPO,
        "module_path": _MODULE_PATH,
    }

    print(json.dumps(info, indent=2, ensure_ascii=False))
    return info


