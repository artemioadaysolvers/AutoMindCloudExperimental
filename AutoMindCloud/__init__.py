import IPython 

from IPython.display import Image

from IPython.display import Image, display

display(Image(
    url="https://raw.githubusercontent.com/Arthemioxz/AutoMindCloudExperimental/main/AutoMindCloud/AutoMindCloud2.png",
    width=700   # Ajusta el ancho aquí
))


import requests

url = "https://raw.githubusercontent.com/Arthemioxz/AutoMindCloudExperimental/main/AutoMindCloud/click_sound.mp3"
local_filename = "click_sound.mp3"

response = requests.get(url)
if response.status_code == 200:
    with open(local_filename, "wb") as f:
        f.write(response.content)



import os 
import shutil
import zipfile

def Download_Zip(Drive_Link, Output_Name="USDModel"):
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


































# AutoMindCloud/__init__.py

import json
import time

__all__ = [
    "reenviar_automind_firestore",
    "get_ultimo_envio_automind",
    "ULTIMO_ENVIO_AUTOMIND",
]


# ============================================================
# URL DEL MÓDULO JS EN jsDelivr
# ============================================================
AUTOMIND_FIRESTORE_JS_URL = (
    "https://cdn.jsdelivr.net/gh/"
    "artemioadaysolvers/"
    "AutoMindCloud-API/"
    "Data_Collector/"
    "automind-firestore.js"
)


ULTIMO_ENVIO_AUTOMIND = {
    "ok": False,
    "code": "not-executed",
    "message": "Todavía no se ha ejecutado el envío.",
}


# ============================================================
# 1. LEER AutoMind_Info DESDE METADATA DEL NOTEBOOK
# ============================================================
def _obtener_automind_info():
    try:
        from google.colab import _message

        respuesta = _message.blocking_request(
            "get_ipynb",
            timeout_sec=60
        )

        notebook = respuesta.get("ipynb", {})

        if isinstance(notebook, str):
            notebook = json.loads(notebook)

        if not isinstance(notebook, dict):
            return {
                "Estado": "Notebook no válido"
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


# ============================================================
# 2. ENVIAR AutoMind_Info + User_Info A FIRESTORE
# ============================================================
def _enviar_automind_firestore():
    global ULTIMO_ENVIO_AUTOMIND

    try:
        from google.colab import output

        auto_mind_info = _obtener_automind_info()

        automind_json = json.dumps(
            auto_mind_info,
            ensure_ascii=False,
            separators=(",", ":")
        )

        # Se serializa otra vez para insertarlo como string JS seguro.
        automind_json_literal = json.dumps(
            automind_json,
            ensure_ascii=False
        )

        # Cache buster para evitar que Colab/jsDelivr use una versión vieja.
        module_url = f"{AUTOMIND_FIRESTORE_JS_URL}?v={int(time.time())}"

        module_url_literal = json.dumps(
            module_url,
            ensure_ascii=False
        )

        javascript = r'''
(async () => {
  try {
    const autoMindInfo = JSON.parse(__AUTOMIND_JSON_LITERAL__);
    const moduleUrl = __MODULE_URL_LITERAL__;

    const modulo = await import(moduleUrl);

    if (
      !modulo ||
      typeof modulo.enviarAutoMindFirestore !== "function"
    ) {
      return {
        ok: false,
        code: "invalid-module",
        message: "El módulo JS no exporta enviarAutoMindFirestore."
      };
    }

    const resultado = await modulo.enviarAutoMindFirestore(
      autoMindInfo
    );

    if (resultado === true) {
      return {
        ok: true
      };
    }

    if (resultado === false) {
      return {
        ok: false,
        code: "send-failed",
        message: "El módulo JS devolvió false."
      };
    }

    if (resultado && typeof resultado === "object") {
      return resultado;
    }

    return {
      ok: false,
      code: "invalid-response",
      message: "Respuesta inválida del módulo JS."
    };

  } catch (error) {
    return {
      ok: false,
      code: error?.code || "javascript-error",
      message: error?.message || String(error)
    };
  }
})()
'''

        javascript = (
            javascript
            .replace("__AUTOMIND_JSON_LITERAL__", automind_json_literal)
            .replace("__MODULE_URL_LITERAL__", module_url_literal)
        )

        resultado = output.eval_js(javascript)

        if isinstance(resultado, dict):
            ULTIMO_ENVIO_AUTOMIND = resultado
        else:
            ULTIMO_ENVIO_AUTOMIND = {
                "ok": False,
                "code": "invalid-result",
                "message": "Colab devolvió un resultado no válido."
            }

        return ULTIMO_ENVIO_AUTOMIND

    except Exception as error:
        ULTIMO_ENVIO_AUTOMIND = {
            "ok": False,
            "code": "python-error",
            "message": str(error)
        }

        return ULTIMO_ENVIO_AUTOMIND


# ============================================================
# 3. FUNCIONES PÚBLICAS OPCIONALES
# ============================================================
def reenviar_automind_firestore():
    """
    Fuerza un nuevo envío sin reiniciar el runtime.
    """
    return _enviar_automind_firestore()


def get_ultimo_envio_automind():
    """
    Devuelve el último resultado del envío.
    """
    return dict(ULTIMO_ENVIO_AUTOMIND)


# ============================================================
# 4. ACTIVACIÓN AUTOMÁTICA AL IMPORTAR
# ============================================================
ULTIMO_ENVIO_AUTOMIND = _enviar_automind_firestore()














