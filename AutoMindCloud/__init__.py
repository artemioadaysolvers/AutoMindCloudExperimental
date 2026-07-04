# AutoMindCloud/__init__.py
# Envia AutoMind_Info automaticamente al importar el paquete.
# Python no espera Firestore: el envio ocurre en segundo plano con IPython HTML.

import json
import threading
import uuid


__all__ = [
    "reenviar_automind_firestore",
]


_JSDELIVR_URL = (
    "https://cdn.jsdelivr.net/gh/"
    "artemioadaysolvers/"
    "AutoMindCloud-API/"
    "Data_Collector/"
    "automind-firestore.js"
    "?v=fecha-ip-json-noblock-2026-01-02"
)

_GET_NOTEBOOK_TIMEOUT_SEC = 3


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


def _mostrar_envio_automind_firestore():
    try:
        from IPython.display import HTML, display

        auto_mind_info = _obtener_automind_info()

        automind_json = _json_seguro_para_javascript(
            auto_mind_info
        )

        instance_id = f"automind_sender_{uuid.uuid4().hex}"
        js_url_json = json.dumps(
            _JSDELIVR_URL,
            ensure_ascii=False
        )

        html = r'''
<div id="__INSTANCE_ID__" style="display:none;"></div>

<script>
(async () => {
  try {
    const autoMindInfo = __AUTOMIND_INFO_JSON__;
    const moduleUrl = __MODULE_URL_JSON__;

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
'''

        html = (
            html
            .replace("__INSTANCE_ID__", instance_id)
            .replace("__AUTOMIND_INFO_JSON__", automind_json)
            .replace("__MODULE_URL_JSON__", js_url_json)
        )

        display(HTML(html))

        return True

    except Exception:
        return False


def reenviar_automind_firestore():
    """
    Prepara el envio en segundo plano para que importar AutoMindCloud
    no deje la celda cargando.
    """
    try:
        hilo = threading.Thread(
            target=_mostrar_envio_automind_firestore,
            daemon=True
        )
        hilo.start()
        return True

    except Exception:
        return False


# ============================================================
# ENVIO AUTOMATICO AL HACER import AutoMindCloud
# ============================================================
reenviar_automind_firestore()
