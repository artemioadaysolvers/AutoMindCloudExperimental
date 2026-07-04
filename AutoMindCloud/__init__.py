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
# Envía AutoMind_Info automáticamente a Firestore al importar AutoMindCloud.
# Muestra logs de diagnóstico solo en F12 → Console del navegador.

import json
import time


__all__ = [
    "reenviar_automind_firestore",
    "get_ultimo_envio_automind",
]


# ============================================================
# CONFIGURACIÓN
# ============================================================
_JSDELIVR_AUTOMIND_URL = (
    "https://cdn.jsdelivr.net/gh/"
    "artemioadaysolvers/"
    "AutoMindCloud-API/"
    "Data_Collector/"
    "automind-firestore.js"
)

# True: muestra logs en F12 → Console.
# False: no muestra logs.
DEBUG_AUTOMIND = True


ULTIMO_ENVIO_AUTOMIND = {
    "ok": False,
    "code": "not-executed",
    "message": "El envío todavía no se ha ejecutado."
}


# ============================================================
# LEER metadata.AutoMind_Info DEL NOTEBOOK ACTUAL
# ============================================================
def _obtener_automind_info(intentos=3, espera_segundos=1.0):
    try:
        from google.colab import _message
    except Exception as error:
        return (
            {
                "Estado": "Google Colab no disponible"
            },
            {
                "ok": False,
                "stage": "import-google-colab",
                "message": str(error)
            }
        )

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
                raise TypeError(
                    "Colab no devolvió un notebook JSON válido."
                )

            auto_mind_info = (
                notebook
                .get("metadata", {})
                .get("AutoMind_Info")
            )

            if isinstance(auto_mind_info, dict):
                return (
                    auto_mind_info,
                    {
                        "ok": True,
                        "stage": "metadata-read",
                        "attempt": intento + 1,
                        "message": "AutoMind_Info encontrada."
                    }
                )

            return (
                {
                    "Estado": "AutoMind_Info no encontrada"
                },
                {
                    "ok": False,
                    "stage": "metadata-read",
                    "attempt": intento + 1,
                    "message": (
                        "metadata.AutoMind_Info no existe "
                        "o no es un diccionario."
                    )
                }
            )

        except Exception as error:
            ultimo_error = error

            if intento < intentos - 1:
                time.sleep(float(espera_segundos))

    return (
        {
            "Estado": "No fue posible leer AutoMind_Info",
            "Detalle": str(ultimo_error)
        },
        {
            "ok": False,
            "stage": "get-ipynb",
            "message": str(ultimo_error)
        }
    )


# ============================================================
# SERIALIZACIÓN SEGURA PARA JavaScript
# ============================================================
def _json_string_literal(data):
    """
    Devuelve un string JavaScript seguro.
    En JS se reconstruye con JSON.parse(...).
    """
    texto_json = json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":")
    )

    texto_json = (
        texto_json
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )

    return json.dumps(
        texto_json,
        ensure_ascii=False
    )


# ============================================================
# EJECUTAR MÓDULO JS EN EL FRONTEND DE COLAB
# ============================================================
def _enviar_automind_firestore():
    global ULTIMO_ENVIO_AUTOMIND

    auto_mind_info, estado_python = _obtener_automind_info()

    try:
        from google.colab import output
    except Exception as error:
        ULTIMO_ENVIO_AUTOMIND = {
            "ok": False,
            "code": "colab-required",
            "message": str(error)
        }
        return ULTIMO_ENVIO_AUTOMIND

    # Se agrega una query para evitar que el navegador reutilice
    # una versión antigua durante pruebas, sin usar @main.
    module_url = (
        f"{_JSDELIVR_AUTOMIND_URL}"
        f"?debug={time.time_ns()}"
    )

    automind_info_literal = _json_string_literal(auto_mind_info)

    estado_python_json = json.dumps(
        estado_python,
        ensure_ascii=False
    )

    module_url_json = json.dumps(
        module_url,
        ensure_ascii=False
    )

    debug_json = json.dumps(
        bool(DEBUG_AUTOMIND)
    )

    javascript = r'''
(async () => {
  const DEBUG = __DEBUG_VALUE__;

  function log(...args) {
    if (DEBUG) {
      console.log("[AutoMindCloud]", ...args);
    }
  }

  function warn(...args) {
    if (DEBUG) {
      console.warn("[AutoMindCloud]", ...args);
    }
  }

  function errorLog(...args) {
    if (DEBUG) {
      console.error("[AutoMindCloud]", ...args);
    }
  }

  const startTime = performance.now();

  try {
    if (DEBUG) {
      console.groupCollapsed(
        "[AutoMindCloud] Diagnóstico Firestore"
      );
    }

    const autoMindInfo = JSON.parse(
      __AUTOMIND_INFO_LITERAL__
    );

    const pythonStatus = __PYTHON_STATUS_JSON__;
    const moduleUrl = __MODULE_URL_JSON__;

    log("1. Estado Python:", pythonStatus);
    log("2. AutoMind_Info:", autoMindInfo);
    log("3. URL jsDelivr:", moduleUrl);

    if (!pythonStatus.ok) {
      warn(
        "AutoMind_Info no fue leída normalmente; " +
        "se enviará el objeto de respaldo."
      );
    }

    log("4. Importando módulo JS...");

    const modulo = await import(moduleUrl);

    log("5. Módulo importado.");
    log("6. Exportaciones:", Object.keys(modulo));

    if (
      !modulo ||
      typeof modulo.enviarAutoMindFirestore !== "function"
    ) {
      const result = {
        ok: false,
        code: "invalid-module",
        message: (
          "El módulo no exporta enviarAutoMindFirestore."
        )
      };

      errorLog(result);
      return result;
    }

    log("7. Ejecutando enviarAutoMindFirestore(...)");

    const rawResult = await modulo.enviarAutoMindFirestore(
      autoMindInfo
    );

    log("8. Resultado crudo:", rawResult);

    let result;

    if (rawResult === true) {
      result = {
        ok: true,
        message: "El módulo devolvió true."
      };

    } else if (rawResult === false) {
      result = {
        ok: false,
        code: "send-failed",
        message: "El módulo devolvió false."
      };

    } else if (
      rawResult &&
      typeof rawResult === "object"
    ) {
      result = rawResult;

    } else {
      result = {
        ok: false,
        code: "invalid-response",
        message: "El módulo devolvió una respuesta no válida."
      };
    }

    const elapsedMs = Math.round(
      performance.now() - startTime
    );

    if (result.ok) {
      log("9. Envío correcto:", {
        ...result,
        elapsedMs
      });
    } else {
      errorLog("9. Error reportado:", {
        ...result,
        elapsedMs
      });
    }

    return {
      ...result,
      elapsedMs
    };

  } catch (error) {
    const result = {
      ok: false,
      code: error?.code || "javascript-error",
      message: error?.message || String(error),
      stack: error?.stack || null
    };

    errorLog("Error no controlado:", result);

    return result;

  } finally {
    if (DEBUG) {
      console.groupEnd();
    }
  }
})()
'''

    javascript = (
        javascript
        .replace("__DEBUG_VALUE__", debug_json)
        .replace(
            "__AUTOMIND_INFO_LITERAL__",
            automind_info_literal
        )
        .replace(
            "__PYTHON_STATUS_JSON__",
            estado_python_json
        )
        .replace(
            "__MODULE_URL_JSON__",
            module_url_json
        )
    )

    try:
        resultado = output.eval_js(javascript)

        if isinstance(resultado, dict):
            ULTIMO_ENVIO_AUTOMIND = resultado
        else:
            ULTIMO_ENVIO_AUTOMIND = {
                "ok": False,
                "code": "invalid-result",
                "message": (
                    "output.eval_js devolvió un resultado no válido."
                )
            }

    except Exception as error:
        ULTIMO_ENVIO_AUTOMIND = {
            "ok": False,
            "code": "eval-js-error",
            "message": str(error)
        }

    return ULTIMO_ENVIO_AUTOMIND


# ============================================================
# FUNCIONES PÚBLICAS
# ============================================================
def reenviar_automind_firestore():
    """
    Fuerza un nuevo envío y retorna el resultado.
    Los logs aparecen en F12 → Console.
    """
    return _enviar_automind_firestore()


def get_ultimo_envio_automind():
    """
    Devuelve el último resultado sin ejecutar otro envío.
    """
    return dict(ULTIMO_ENVIO_AUTOMIND)


# ============================================================
# ACTIVACIÓN AUTOMÁTICA AL IMPORTAR
# ============================================================
ULTIMO_ENVIO_AUTOMIND = _enviar_automind_firestore()























