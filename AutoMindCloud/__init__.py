# AutoMindCloud/__init__.py
# Envia AutoMind_Info automaticamente al importar el paquete.
# Python no espera Firestore: el envio ocurre en segundo plano con IPython HTML.

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


def reenviar_automind_firestore():
    """
    Inserta JavaScript en el frontend de Colab.
    El navegador resuelve el ultimo commit de GitHub y despues carga
    jsDelivr fijado a ese SHA.
    """
    try:
        from IPython.display import HTML, display

        auto_mind_info = _obtener_automind_info()

        automind_json = _json_seguro_para_javascript(
            auto_mind_info
        )

        instance_id = f"automind_sender_{uuid.uuid4().hex}"
        github_owner_json = json.dumps(_GITHUB_OWNER)
        github_repo_json = json.dumps(_GITHUB_REPO)
        github_branch_json = json.dumps(_GITHUB_BRANCH)
        module_path_json = json.dumps(_MODULE_PATH)

        html = r'''
<div id="__INSTANCE_ID__" style="display:none;"></div>

<script>
(async () => {
  try {
    const autoMindInfo = __AUTOMIND_INFO_JSON__;
    const githubOwner = __GITHUB_OWNER_JSON__;
    const githubRepo = __GITHUB_REPO_JSON__;
    const githubBranch = __GITHUB_BRANCH_JSON__;
    const modulePath = __MODULE_PATH_JSON__;

    const githubApiUrl = [
      "https://api.github.com/repos",
      githubOwner,
      githubRepo,
      "commits"
    ].join("/") + "?" + new URLSearchParams({
      sha: githubBranch,
      path: modulePath,
      per_page: "1"
    }).toString();

    const commitResponse = await fetch(githubApiUrl, {
      cache: "no-store",
      headers: {
        Accept: "application/vnd.github+json"
      }
    });

    if (!commitResponse.ok) {
      throw new Error(
        `GitHub commit lookup failed: ${commitResponse.status}`
      );
    }

    const commits = await commitResponse.json();
    const latestSha = commits?.[0]?.sha;

    if (!/^[0-9a-f]{40}$/i.test(latestSha || "")) {
      throw new Error("GitHub no devolvio un SHA valido.");
    }

    const moduleUrl = (
      `https://cdn.jsdelivr.net/gh/${githubOwner}/${githubRepo}` +
      `@${latestSha}/${modulePath}`
    );

    const modulo = await import(moduleUrl);

    if (
      !modulo ||
      typeof modulo.enviarAutoMindFirestore !== "function"
    ) {
      console.error(
        "[AutoMindCloud] No existe enviarAutoMindFirestore."
      );
      return;
    }

    void modulo.enviarAutoMindFirestore(
      autoMindInfo
    ).catch((error) => {
      console.error(
        "[AutoMindCloud] Error durante guardado:",
        error
      );
    });

  } catch (error) {
    console.error(
      "[AutoMindCloud] Error durante envio:",
      error
    );
  }
})();
</script>
