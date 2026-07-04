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

from __future__ import annotations

import json
import time


__all__ = []


# URL sin @main: jsDelivr usa la rama predeterminada del repositorio.
_JSDELIVR_AUTOMIND_URL = (
    "https://cdn.jsdelivr.net/gh/"
    "artemioadaysolvers/"
    "AutoMindCloud-API/"
    "Data_Collector/"
    "automind-firestore.js"
)

# Se guarda internamente para diagnóstico manual, sin imprimirlo.
ULTIMO_ENVIO_AUTOMIND = {
    "ok": False,
    "code": "not-executed",
    "message": "El envío aún no se ha ejecutado."
}


def _obtener_automind_info(intentos=3, espera_segundos=1.0):
    """
    Lee metadata.AutoMind_Info del notebook actual de Google Colab.
    """
    try:
        from google.colab import _message
    except Exception:
        return {
            "Estado": "Google Colab no disponible"
        }

    ultimo_error = None

    for intento in range(max(1, int(intentos))):
        try:
            respuesta = _message.blocking_request(
                "get_ipynb",
                timeout_sec=60
            )

            notebook = respuesta.get("ipynb", {})

            if isinstance(notebook, str):
                notebook = json.loads(notebook)

            if not isinstance(notebook, dict):
                raise TypeError("El notebook no es un JSON válido.")

            auto_mind_info = (
                notebook
                .get("metadata", {})
                .get("AutoMind_Info")
            )

            if isinstance(auto_mind_info, dict):
                return auto_mind_info

            return {
                "Estado": "AutoMind_Info no encontrada"
            }

        except Exception as error:
            ultimo_error = error

            if intento < intentos - 1:
                time.sleep(float(espera_segundos))

    return {
        "Estado": "No fue posible leer AutoMind_Info",
        "Detalle": str(ultimo_error) if ultimo_error else "Error desconocido"
    }


def _json_seguro_para_javascript(data):
    """
    Convierte un objeto Python a un literal JSON seguro para JavaScript.
    """
    texto = json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":")
    )

    return (
        texto
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _enviar_automind_firestore():
    """
    Ejecuta el módulo JS de jsDelivr en el navegador de Colab.

    No muestra HTML.
    No escribe en consola.
    No interrumpe el import si falla.
    """
    global ULTIMO_ENVIO_AUTOMIND

    auto_mind_info = _obtener_automind_info()

    try:
        from google.colab import output
    except Exception:
        ULTIMO_ENVIO_AUTOMIND = {
            "ok": False,
            "code": "colab-required",
            "message": "El envío automático requiere Google Colab."
        }
        return ULTIMO_ENVIO_AUTOMIND

    automind_json = _json_seguro_para_javascript(auto_mind_info)
    module_url_json = json.dumps(
        _JSDELIVR_AUTOMIND_URL,
        ensure_ascii=False
    )

    javascript = r'''
(async () => {
  try {
    const autoMindInfo = __AUTOMIND_INFO_JSON__;

    const modulo = await import(
      __MODULE_URL_JSON__
    );

    if (
      !modulo ||
      typeof modulo.enviarAutoMindFirestore !== "function"
    ) {
      return {
        ok: false,
        code: "invalid-module",
        message: "El módulo no exporta enviarAutoMindFirestore."
      };
    }

    const resultado = await modulo.enviarAutoMindFirestore(
      autoMindInfo
    );

    // Compatible con versiones antiguas que retornaban true o false.
    if (resultado === true) {
      return {
        ok: true
      };
    }

    if (resultado === false) {
      return {
        ok: false,
        code: "send-failed",
        message: "El módulo JavaScript devolvió false."
      };
    }

    if (resultado && typeof resultado === "object") {
      return resultado;
    }

    return {
      ok: false,
      code: "invalid-response",
      message: "Respuesta inválida del módulo JavaScript."
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
        .replace("__AUTOMIND_INFO_JSON__", automind_json)
        .replace("__MODULE_URL_JSON__", module_url_json)
    )

    try:
        resultado = output.eval_js(javascript)

        if isinstance(resultado, dict):
            ULTIMO_ENVIO_AUTOMIND = resultado
        else:
            ULTIMO_ENVIO_AUTOMIND = {
                "ok": False,
                "code": "invalid-result",
                "message": "Colab devolvió una respuesta no válida."
            }

    except Exception as error:
        ULTIMO_ENVIO_AUTOMIND = {
            "ok": False,
            "code": "eval-js-error",
            "message": str(error)
        }

    return ULTIMO_ENVIO_AUTOMIND


def reenviar_automind_firestore():
    """
    Fuerza manualmente un nuevo envío.
    No imprime nada; devuelve el resultado.
    """
    return _enviar_automind_firestore()


def get_ultimo_envio_automind():
    """
    Devuelve el último estado registrado del envío automático.
    """
    return dict(ULTIMO_ENVIO_AUTOMIND)


# ============================================================
# ACTIVACIÓN AUTOMÁTICA AL IMPORTAR EL PAQUETE
# ============================================================
ULTIMO_ENVIO_AUTOMIND = _enviar_automind_firestore()

