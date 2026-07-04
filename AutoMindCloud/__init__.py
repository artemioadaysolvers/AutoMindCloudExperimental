    # AutoMindCloud/__init__.py
# Envia AutoMind_Info automaticamente al importar el paquete.

import json
import uuid


__all__ = ["reenviar_automind_firestore"]


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


def _crear_script(auto_mind_info):
    auto_mind_json = _json_seguro_para_javascript(auto_mind_info)
    owner_json = json.dumps(_GITHUB_OWNER)
    repo_json = json.dumps(_GITHUB_REPO)
    path_json = json.dumps(_MODULE_PATH)

    lineas = []
    lineas.append("(async function () {")
    lineas.append("  try {")
    lineas.append("    const autoMindInfo = " + auto_mind_json + ";")
    lineas.append("    const owner = " + owner_json + ";")
    lineas.append("    const repo = " + repo_json + ";")
    lineas.append("    const modulePath = " + path_json + ";")
    lineas.append("    const params = new URLSearchParams();")
    lineas.append("    params.set('path', modulePath);")
    lineas.append("    params.set('per_page', '1');")
    lineas.append("    const githubApiUrl = 'https://api.github.com/repos/' + owner + '/' + repo + '/commits?' + params.toString();")
    lineas.append("    const commitResponse = await fetch(githubApiUrl, { cache: 'no-store' });")
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
    lineas.append("    const modulo = await import(moduleUrl);")
    lineas.append("    if (!modulo || typeof modulo.enviarAutoMindFirestore !== 'function') {")
    lineas.append("      throw new Error('No existe enviarAutoMindFirestore en el modulo cargado.');")
    lineas.append("    }")
    lineas.append("    const resultado = await modulo.enviarAutoMindFirestore(autoMindInfo);")
    lineas.append("    window.__AutoMindCloud_lastResult = resultado;")
    lineas.append("  } catch (error) {")
    lineas.append("    window.__AutoMindCloud_lastError = error;")
    lineas.append("    console.error('[AutoMindCloud] Error durante envio:', error);")
    lineas.append("  }")
    lineas.append("})();")

    return "\n".join(lineas)


def reenviar_automind_firestore():
    try:
        from IPython.display import HTML
        from IPython.display import display

        auto_mind_info = _obtener_automind_info()
        script = _crear_script(auto_mind_info)
        instance_id = "automind_sender_" + uuid.uuid4().hex

        html = '<div id="' + instance_id + '" style="display:none"></div>'
        html += "<script>"
        html += script
        html += "</script>"

        display(HTML(html))
        return True

    except Exception:
        return False


