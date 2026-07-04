from __future__ import annotations

import json
import os
import shutil
import time
import zipfile
from pathlib import Path


__all__ = [
    "Download_Zip",
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

ENVIAR_AUTOMATICAMENTE_AL_IMPORTAR = True
MOSTRAR_RESULTADO_AUTOMATICO = True

ULTIMO_ENVIO_AUTOMIND = {
    "ok": False,
    "code": "not-executed",
    "message": "El envío todavía no se ha ejecutado."
}


# ============================================================
# DESCARGAR Y EXTRAER ZIP DE GOOGLE DRIVE
# ============================================================
def Download_Zip(Drive_Link, Output_Name="USDModel"):
    """
    Descarga un ZIP de Google Drive, lo extrae y devuelve /content/Output_Name.
    """
    try:
        import gdown
    except ImportError as error:
        raise ImportError(
            "No se encontró gdown. Instálalo con: !pip install -q gdown"
        ) from error

    if not isinstance(Drive_Link, str) or not Drive_Link.strip():
        raise ValueError("Drive_Link debe ser un enlace o ID válido.")

    output_name = os.path.basename(str(Output_Name).strip())

    if not output_name or output_name in {".", ".."}:
        raise ValueError("Output_Name no es válido.")

    root_dir = Path("/content")
    root_dir.mkdir(parents=True, exist_ok=True)

    zip_path = root_dir / f"{output_name}.zip"
    temp_dir = root_dir / f"__tmp_extract_{output_name}"
    final_dir = root_dir / output_name

    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)

    if final_dir.exists():
        shutil.rmtree(final_dir, ignore_errors=True)

    if zip_path.exists():
        zip_path.unlink()

    temp_dir.mkdir(parents=True, exist_ok=True)

    drive_link = Drive_Link.strip()

    if drive_link.startswith(("http://", "https://")):
        drive_url = drive_link
    else:
        drive_url = f"https://drive.google.com/uc?id={drive_link}"

    try:
        downloaded = gdown.download(
            url=drive_url,
            output=str(zip_path),
            quiet=False,
            fuzzy=True
        )

        if downloaded is None or not zip_path.exists():
            raise RuntimeError("No se pudo descargar el ZIP desde Google Drive.")

        if not zipfile.is_zipfile(zip_path):
            raise zipfile.BadZipFile(
                "El archivo descargado no es un ZIP válido."
            )

        with zipfile.ZipFile(zip_path, "r") as archivo_zip:
            root_resolved = temp_dir.resolve()

            for member in archivo_zip.infolist():
                destination = (temp_dir / member.filename).resolve()

                if (
                    destination != root_resolved
                    and root_resolved not in destination.parents
                ):
                    raise RuntimeError(
                        "ZIP inseguro: ruta no permitida: "
                        f"{member.filename}"
                    )

            archivo_zip.extractall(temp_dir)

        def es_basura(nombre):
            return nombre.startswith(".") or nombre == "__MACOSX"

        visibles = [
            nombre
            for nombre in os.listdir(temp_dir)
            if not es_basura(nombre)
        ]

        if not visibles:
            raise RuntimeError("El ZIP está vacío.")

        if (
            len(visibles) == 1
            and (temp_dir / visibles[0]).is_dir()
        ):
            shutil.move(
                str(temp_dir / visibles[0]),
                str(final_dir)
            )
        else:
            final_dir.mkdir(parents=True, exist_ok=True)

            for nombre in visibles:
                shutil.move(
                    str(temp_dir / nombre),
                    str(final_dir / nombre)
                )

        return str(final_dir)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ============================================================
# LEER metadata.AutoMind_Info DEL NOTEBOOK DE COLAB
# ============================================================
def _obtener_automind_info():
    """Lee metadata.AutoMind_Info del notebook actualmente abierto en Colab."""
    try:
        from google.colab import _message

        respuesta = _message.blocking_request(
            "get_ipynb",
            timeout_sec=20
        )

        notebook = respuesta.get("ipynb", {})

        if isinstance(notebook, str):
            notebook = json.loads(notebook)

        if not isinstance(notebook, dict):
            raise TypeError("Colab no devolvió un notebook JSON válido.")

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


def _json_para_javascript(data):
    """
    Devuelve un literal JavaScript seguro que luego se usa con JSON.parse().
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

    return json.dumps(texto_json, ensure_ascii=False)


# ============================================================
# EJECUTAR EL MÓDULO JS EN EL NAVEGADOR DE COLAB
# ============================================================
def _enviar_automind_firestore(auto_mind_info):
    """
    Envía AutoMind_Info al módulo JavaScript y espera su respuesta.
    """
    try:
        from google.colab import output
    except Exception as error:
        return {
            "ok": False,
            "code": "colab-required",
            "message": (
                "Este envío automático requiere Google Colab: "
                f"{error}"
            )
        }

    module_url = (
        f"{_JSDELIVR_AUTOMIND_URL}"
        f"?v={time.time_ns()}"
    )

    javascript = r"""
(async () => {
  try {
    const autoMindInfo = JSON.parse(__AUTOMIND_JSON_STRING__);
    const moduleUrl = __MODULE_URL_JSON__;

    const modulo = await import(moduleUrl);

    if (
      !modulo ||
      typeof modulo.enviarAutoMindFirestore !== "function"
    ) {
      return JSON.stringify({
        ok: false,
        code: "invalid-module",
        message: (
          "El módulo remoto no exporta enviarAutoMindFirestore."
        ),
        moduleUrl
      });
    }

    const resultado = await modulo.enviarAutoMindFirestore(
      autoMindInfo
    );

    return JSON.stringify(
      resultado && typeof resultado === "object"
        ? resultado
        : {
            ok: false,
            code: "invalid-module-response",
            message: (
              "automind-firestore.js no devolvió un objeto válido."
            ),
            moduleUrl,
            rawResult: String(resultado)
          }
    );

  } catch (error) {
    return JSON.stringify({
      ok: false,
      code: error?.code || "javascript-error",
      message: error?.message || String(error),
      stack: error?.stack || null
    });
  }
})()
"""

    javascript = (
        javascript
        .replace(
            "__AUTOMIND_JSON_STRING__",
            _json_para_javascript(auto_mind_info)
        )
        .replace(
            "__MODULE_URL_JSON__",
            json.dumps(module_url, ensure_ascii=False)
        )
    )

    try:
        resultado = output.eval_js(javascript)

        if not isinstance(resultado, str):
            return {
                "ok": False,
                "code": "invalid-eval-js-result",
                "message": (
                    "Colab no devolvió el JSON esperado desde el navegador."
                ),
                "rawResult": str(resultado)
            }

        resultado = json.loads(resultado)

        if not isinstance(resultado, dict):
            return {
                "ok": False,
                "code": "invalid-result-json",
                "message": "El módulo devolvió JSON que no es un objeto."
            }

        return resultado

    except Exception as error:
        return {
            "ok": False,
            "code": "eval-js-error",
            "message": str(error)
        }


# ============================================================
# FUNCIONES PÚBLICAS
# ============================================================
def reenviar_automind_firestore(autoMindInfo=None):
    """
    Envía metadata.AutoMind_Info a Firestore.

    Si autoMindInfo se entrega, envía ese diccionario.
    Si no se entrega, lee metadata.AutoMind_Info del notebook.
    """
    global ULTIMO_ENVIO_AUTOMIND

    if autoMindInfo is None:
        autoMindInfo = _obtener_automind_info()

    ULTIMO_ENVIO_AUTOMIND = _enviar_automind_firestore(autoMindInfo)
    return dict(ULTIMO_ENVIO_AUTOMIND)


def get_ultimo_envio_automind():
    """Retorna el resultado del último envío."""
    return dict(ULTIMO_ENVIO_AUTOMIND)


# ============================================================
# ENVÍO AUTOMÁTICO AL IMPORTAR
# ============================================================
if ENVIAR_AUTOMATICAMENTE_AL_IMPORTAR:
    ULTIMO_ENVIO_AUTOMIND = reenviar_automind_firestore()

    if MOSTRAR_RESULTADO_AUTOMATICO:
        if ULTIMO_ENVIO_AUTOMIND.get("ok"):
            print(
                "[AutoMindCloud] Guardado en Firestore: "
                f"{ULTIMO_ENVIO_AUTOMIND.get('collectionName')}/"
                f"{ULTIMO_ENVIO_AUTOMIND.get('ipDocument')}/JSON/"
                f"{ULTIMO_ENVIO_AUTOMIND.get('documentId')}"
            )
        else:
            print(
                "[AutoMindCloud] Error Firestore: "
                f"{ULTIMO_ENVIO_AUTOMIND.get('code')} - "
                f"{ULTIMO_ENVIO_AUTOMIND.get('message')}"
            )
