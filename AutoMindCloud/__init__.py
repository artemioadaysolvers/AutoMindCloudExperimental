# AutoMindCloud/__init__.py
# Envia AutoMind_Info automaticamente al importar el paquete.
# El envio ocurre desde el navegador de Colab.

import json
import uuid


__all__ = [
    "reenviar_automind_firestore",
]


_GITHUB_OWNER = "artemioadaysolvers"
_GITHUB_REPO = "AutoMindCloud-API"
_GITHUB_BRANCH = "main"
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
            return {
                "Estado": "Notebook no valido"
            }

        auto_mind_info = (
            notebook
            .get("metadata", {})
            .get("AutoMind_Info")
        )

        if not isinstance(auto_mind_info, dict):
            return {
                "Estado": "AutoMind_Info no encontrada"
            }

        return auto_mind_info

    except Exception as error:
        return {
            "Estado": "No fue posible leer AutoMind_Info",
            "Detalle": str(error)
        }


def _json_seguro_para_javascript(data):
    texto = json.dumps(
        data,
        ensure_ascii=False
    )

    return (
        texto
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _crear_javascript(auto_mind_info):
    auto_mind_json = _json_seguro_para_javascript(auto_mind_info)
    github_owner_json = json.dumps(_GITHUB_OWNER)
    github_repo_json = json.dumps(_GITHUB_REPO)
    github_branch_json = json.dumps(_GITHUB_BRANCH)
    module_path_json = json.dumps(_MODULE_PATH)

    lineas = [
        "(async () => {",
        "  try {",
        f"    const autoMindInfo = {auto_mind_json};",
        f"    const githubOwner = {github_owner_json};",
        f"    const githubRepo = {github_repo_json};",
        f"    const githubBranch = {github_branch_json};",
        f"    const modulePath = {module_path_json};",
        "",
        "    const params = new URLSearchParams({",
        "      sha: githubBranch,",
        "      path: modulePath,",
        "      per_page: '1'",
        "    });",
        "",
        "    const githubApiUrl =",
        "      'https://api.github.com/repos/' +",
        "      githubOwner + '/' +",
        "      githubRepo +",
        "      '/commits?' +",
        "      params.toString();",
        "",
        "    const commitResponse = await fetch(githubApiUrl, {",
        "      cache: 'no-store',",
        "      headers: {",
        "        Accept: 'application/vnd.github+json'",
        "      }",
        "    });",
        "",
        "    if (!commitResponse.ok) {",
        "      throw new Error(",
        "        'GitHub commit lookup failed: ' + commitResponse.status",
        "      );",
        "    }",
        "",
        "    const commits = await commitResponse.json();",
        "    const latestSha = commits && commits[0] && commits[0].sha;",
        "",
        "    if (!latestSha || !/^[0-9a-f]{40}$/i.test(latestSha)) {",
        "      throw new Error('GitHub no devolvio un SHA valido.');",
        "    }",
        "",
        "    const moduleUrl =",
        "      'https://cdn.jsdelivr.net/gh/' +",
        "      githubOwner + '/' +",
        "      githubRepo +",
        "      '@' +",
        "      latestSha + '/' +",
        "      modulePath;",
        "",
        "    window.__AutoMindCloud_lastModuleUrl = moduleUrl;",
        "",
        "    const modulo = await import(moduleUrl);",
        "",
        "    if (",
        "      !modulo ||",
        "      typeof modulo.enviarAutoMindFirestore !== 'function'",
        "    ) {",
        "      throw new Error(",
        "        'No existe enviarAutoMindFirestore en el modulo cargado.'",
        "      );",
        "    }",
        "",
        "    const resultado = await modulo.enviarAutoMindFirestore(",
        "      autoMindInfo",
        "    );",
        "",
        "    window.__AutoMindCloud_lastResult = resultado;",
        "",
        "  } catch (error) {",
        "    window.__AutoMindCloud_lastError = error;",
        "    console.error('[AutoMindCloud] Error durante envio:', error);",
        "  }",
        "})();",
    ]

    return "\n".join(lineas)


def reenviar_automind_firestore():
    """
    Inserta JavaScript en el frontend de Colab.
    El navegador consulta GitHub, obtiene el ultimo SHA publicado del
    archivo automind-firestore.js y carga jsDelivr fijado a ese SHA.
    """
    try:
        from IPython.display import HTML, display

        auto_mind_info = _obtener_automind_info()
        js_code = _crear_javascript(auto_mind_info)
        instance_id = f"automind_sender_{uuid.uuid4().hex}"

        html = (
            '<div id="' +
            instance_id +
            '" style="display:none;"></div><script>' +
            js_code +
            "</script>"
