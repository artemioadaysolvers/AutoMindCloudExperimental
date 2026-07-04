from __future__ import annotations

import json
import os
import re
import shutil
import time
import uuid
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


# ============================================================
# EXPORTACIONES PÚBLICAS
# ============================================================
__all__ = [
    "Download_Zip",
    "reenviar_automind_firestore",
    "get_ultimo_envio_automind",
]


# ============================================================
# CONFIGURACIÓN
# ============================================================
MOSTRAR_BANNER_AL_IMPORTAR = True
ENVIAR_AUTOMATICAMENTE_AL_IMPORTAR = True
MOSTRAR_RESULTADO_AUTOMATICO = True
TIEMPO_MAXIMO_LEER_NOTEBOOK_SEGUNDOS = 12
TIEMPO_MAXIMO_GITHUB_SEGUNDOS = 20

_BANNER_URL = (
    "https://raw.githubusercontent.com/"
    "Arthemioxz/"
    "AutoMindCloudExperimental/main/"
    "AutoMindCloud/AutoMindCloud2.png"
)

_CLICK_SOUND_URL = (
    "https://raw.githubusercontent.com/"
    "Arthemioxz/"
    "AutoMindCloudExperimental/main/"
    "AutoMindCloud/click_sound.mp3"
)

_CLICK_SOUND_PATH = "/content/click_sound.mp3"

# El SHA se obtiene desde GitHub en CADA envío.
# No se usa @main ni un SHA escrito manualmente.
_GITHUB_OWNER = "artemioadaysolvers"
_GITHUB_REPO = "AutoMindCloud-API"
_GITHUB_JS_PATH = "Data_Collector/automind-firestore.js"

ULTIMO_ENVIO_AUTOMIND = {
    "ok": False,
    "code": "not-executed",
    "message": "El envío todavía no se ha ejecutado."
}


# ============================================================
# RECURSOS VISUALES
# ============================================================
def _mostrar_banner():
    """Muestra el banner mediante URL."""
    try:
        from IPython.display import Image, display
        display(Image(url=_BANNER_URL, width=700))
    except Exception:
        pass


def _descargar_click_sound():
    """Descarga el sonido solo si se llama explícitamente."""
    try:
        import requests

        respuesta = requests.get(_CLICK_SOUND_URL, timeout=15)
        respuesta.raise_for_status()

        with open(_CLICK_SOUND_PATH, "wb") as archivo:
            archivo.write(respuesta.content)

        return _CLICK_SOUND_PATH

    except Exception:
        return None


# ============================================================
# DESCARGAR Y EXTRAER ZIP DESDE GOOGLE DRIVE
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
        raise ValueError(
            "Drive_Link debe ser un enlace o ID válido de Google Drive."
        )

    output_name = os.path.basename(str(Output_Name).strip())

    if not output_name or output_name in {".", ".."}:
        raise ValueError("Output_Name no es válido.")

    root_dir = Path("/content")
    root_dir.mkdir(parents=True, exist_ok=True)

    zip_path = root_dir / f"{output_name}.zip"
    tmp_extract = root_dir / f"__tmp_extract_{uuid.uuid4().hex}"
    final_dir = root_dir / output_name

    drive_link = Drive_Link.strip()

    if not drive_link.startswith(("http://", "https://")):
        drive_link = f"https://drive.google.com/uc?id={drive_link}"

    if tmp_extract.exists():
        shutil.rmtree(tmp_extract, ignore_errors=True)

    if zip_path.exists():
        zip_path.unlink()

    if final_dir.exists():
        shutil.rmtree(final_dir, ignore_errors=True)

    tmp_extract.mkdir(parents=True, exist_ok=True)

    try:
        downloaded_path = gdown.download(
            url=drive_link,
            output=str(zip_path),
            quiet=False,
            fuzzy=True
        )

        if downloaded_path is None or not zip_path.exists():
            raise RuntimeError(
                "No se pudo descargar el archivo desde Google Drive. "
                "Verifica que el enlace sea público."
            )

        if not zipfile.is_zipfile(zip_path):
            raise zipfile.BadZipFile(
                "El archivo descargado no es un ZIP válido."
            )

        root_resolved = tmp_extract.resolve()

        with zipfile.ZipFile(zip_path, "r") as archivo_zip:
            for member in archivo_zip.infolist():
                destino = (tmp_extract / member.filename).resolve()

                if (
                    destino != root_resolved
                    and root_resolved not in destino.parents
                ):
                    raise RuntimeError(
                        "ZIP inseguro: contiene una ruta no permitida: "
                        f"{member.filename}"
                    )

            archivo_zip.extractall(tmp_extract)

        def es_basura(nombre):
            return nombre.startswith(".") or nombre == "__MACOSX"

        visibles = [
            nombre
            for nombre in os.listdir(tmp_extract)
            if not es_basura(nombre)
        ]

        if not visibles:
            raise RuntimeError(
                "El ZIP se descargó correctamente, pero está vacío."
            )

        if (
            len(visibles) == 1
            and (tmp_extract / visibles[0]).is_dir()
        ):
            shutil.move(
                str(tmp_extract / visibles[0]),
                str(final_dir)
            )
        else:
            final_dir.mkdir(parents=True, exist_ok=True)

            for nombre in visibles:
                shutil.move(
                    str(tmp_extract / nombre),
                    str(final_dir / nombre)
                )

        return str(final_dir)

    finally:
        shutil.rmtree(tmp_extract, ignore_errors=True)


# ============================================================
# LEER metadata.AutoMind_Info DEL NOTEBOOK ACTUAL
# ============================================================
def _obtener_automind_info(timeout_segundos):
    """Lee metadata.AutoMind_Info desde el notebook abierto en Colab."""
    try:
        from google.colab import _message

        timeout = max(
            1,
            min(int(timeout_segundos), TIEMPO_MAXIMO_LEER_NOTEBOOK_SEGUNDOS)
        )

        respuesta = _message.blocking_request(
            "get_ipynb",
            timeout_sec=timeout
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
# OBTENER ÚLTIMO COMMIT DEL JS
# ============================================================
def _obtener_ultimo_commit_del_js():
    """
    Consulta GitHub en cada ejecución y retorna el SHA del último commit
    que modificó exactamente Data_Collector/automind-firestore.js.
    """
    query = urlencode({
        "path": _GITHUB_JS_PATH,
        "per_page": 1
    })

    api_url = (
        "https://api.github.com/repos/"
        f"{_GITHUB_OWNER}/{_GITHUB_REPO}/commits?"
        f"{query}"
    )

    request = Request(
        api_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "AutoMindCloud-Colab"
        }
    )

    try:
        with urlopen(
            request,
            timeout=TIEMPO_MAXIMO_GITHUB_SEGUNDOS
        ) as response:
            commits = json.loads(
                response.read().decode("utf-8")
            )

    except HTTPError as error:
        detalle = error.read().decode(
            "utf-8",
            errors="replace"
        )

        raise RuntimeError(
            "GitHub rechazó la consulta del último commit del JS. "
            f"HTTP {error.code}: {detalle}"
        ) from error

    except URLError as error:
        raise RuntimeError(
            "No fue posible conectar con GitHub para obtener el "
            f"último commit del JS: {error.reason}"
        ) from error

    if not isinstance(commits, list) or not commits:
        raise RuntimeError(
            "GitHub no devolvió commits para: "
            f"{_GITHUB_JS_PATH}"
        )

    commit_sha = str(
        commits[0].get("sha", "")
    ).strip().lower()

    if not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
        raise RuntimeError(
            "GitHub devolvió un SHA no válido: "
            f"{commit_sha!r}"
        )

    return commit_sha


def _crear_url_js_por_sha(commit_sha):
    """
    Construye la URL inmutable de jsDelivr con el SHA obtenido de GitHub.
    """
    return (
        "https://cdn.jsdelivr.net/gh/"
        f"{_GITHUB_OWNER}/"
        f"{_GITHUB_REPO}@{commit_sha}/"
        f"{_GITHUB_JS_PATH}"
    )


def _json_string_literal(data):
    """
    Python dict -> JSON -> string literal seguro para JSON.parse() en JS.
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
# ENVIAR A FIRESTORE DESDE EL FRONTEND DE COLAB
# ============================================================
def _enviar_automind_firestore(auto_mind_info):
    """
    En cada llamada:
      1. obtiene desde GitHub el último SHA que modificó el JS;
      2. importa ese JS desde jsDelivr usando @SHA;
      3. envía AutoMind_Info;
      4. retorna la respuesta exacta del JS.
    """
    try:
        from google.colab import output
    except Exception as error:
        return {
            "ok": False,
            "code": "colab-required",
            "message": (
                "Este envío requiere Google Colab: "
                f"{error}"
            )
        }

    try:
        commit_sha = _obtener_ultimo_commit_del_js()
        module_url = _crear_url_js_por_sha(commit_sha)

    except Exception as error:
        return {
            "ok": False,
            "code": "github-latest-commit-error",
            "message": str(error)
        }

    javascript = r"""
(async () => {
  try {
    const autoMindInfo = JSON.parse(__AUTOMIND_INFO_STRING__);
    const moduleUrl = __MODULE_URL_JSON__;
    const jsCommit = __JS_COMMIT_JSON__;

    const modulo = await import(moduleUrl);

    if (
      !modulo ||
      typeof modulo.enviarAutoMindFirestore !== "function"
    ) {
      return JSON.stringify({
        ok: false,
        code: "invalid-module",
        message: "El módulo no exporta enviarAutoMindFirestore.",
        moduleUrl,
        jsCommit,
        exportaciones: modulo ? Object.keys(modulo) : []
      });
    }

    const resultado = await modulo.enviarAutoMindFirestore(
      autoMindInfo
    );

    if (
      !resultado ||
      typeof resultado !== "object" ||
      Array.isArray(resultado)
    ) {
      return JSON.stringify({
        ok: false,
        code: "invalid-module-response",
        message: (
          "automind-firestore.js no devolvió un objeto válido."
        ),
        rawResult: String(resultado),
        moduleUrl,
        jsCommit
      });
    }

    return JSON.stringify({
      ...resultado,
      moduleUrl,
      jsCommit
    });

  } catch (error) {
    return JSON.stringify({
      ok: false,
      code: error?.code || "javascript-error",
      message: error?.message || String(error),
      stack: error?.stack || null,
      moduleUrl: __MODULE_URL_JSON__,
      jsCommit: __JS_COMMIT_JSON__
    });
  }
})()
"""

    javascript = (
        javascript
        .replace(
            "__AUTOMIND_INFO_STRING__",
            _json_string_literal(auto_mind_info)
        )
        .replace(
            "__MODULE_URL_JSON__",
            json.dumps(module_url, ensure_ascii=False)
        )
        .replace(
            "__JS_COMMIT_JSON__",
            json.dumps(commit_sha, ensure_ascii=False)
        )
    )

    try:
        raw_result = output.eval_js(javascript)

    except Exception as error:
        return {
            "ok": False,
            "code": "eval-js-error",
            "message": str(error),
            "moduleUrl": module_url,
            "jsCommit": commit_sha
        }

    if not isinstance(raw_result, str):
        return {
            "ok": False,
            "code": "invalid-eval-js-result",
            "message": (
                "Colab no devolvió el JSON esperado desde el navegador."
            ),
            "rawResult": str(raw_result),
            "moduleUrl": module_url,
            "jsCommit": commit_sha
        }

    try:
        result = json.loads(raw_result)

    except json.JSONDecodeError:
        return {
            "ok": False,
            "code": "invalid-result-json",
            "message": (
                "El navegador devolvió una respuesta que no es JSON válido."
            ),
            "rawResult": raw_result,
            "moduleUrl": module_url,
            "jsCommit": commit_sha
        }

    if not isinstance(result, dict):
        return {
            "ok": False,
            "code": "invalid-result-object",
            "message": "El JS devolvió JSON que no es un objeto.",
            "rawResult": result,
            "moduleUrl": module_url,
            "jsCommit": commit_sha
        }

    return result


# ============================================================
# FUNCIONES PÚBLICAS
# ============================================================
def reenviar_automind_firestore(
    autoMindInfo=None,
    timeout_segundos=TIEMPO_MAXIMO_LEER_NOTEBOOK_SEGUNDOS
):
    """
    Fuerza un envío.

    Si autoMindInfo es None, lee metadata.AutoMind_Info del notebook.
    Cada llamada consulta el último commit del JS en GitHub.
    """
    global ULTIMO_ENVIO_AUTOMIND

    if autoMindInfo is None:
        autoMindInfo = _obtener_automind_info(timeout_segundos)

    ULTIMO_ENVIO_AUTOMIND = _enviar_automind_firestore(
        autoMindInfo
    )

    return dict(ULTIMO_ENVIO_AUTOMIND)


def get_ultimo_envio_automind():
    """Retorna el resultado del último envío."""
    return dict(ULTIMO_ENVIO_AUTOMIND)


# ============================================================
# ACTIVACIÓN AUTOMÁTICA AL IMPORTAR
# ============================================================
if MOSTRAR_BANNER_AL_IMPORTAR:
    _mostrar_banner()

if ENVIAR_AUTOMATICAMENTE_AL_IMPORTAR:
    ULTIMO_ENVIO_AUTOMIND = reenviar_automind_firestore()

    if MOSTRAR_RESULTADO_AUTOMATICO:
        if ULTIMO_ENVIO_AUTOMIND.get("ok"):
            print(
                "[AutoMindCloud] Guardado en Firestore: "
                f"{ULTIMO_ENVIO_AUTOMIND.get('collectionName')}/"
                f"{ULTIMO_ENVIO_AUTOMIND.get('ipDocument')}/JSON/"
                f"{ULTIMO_ENVIO_AUTOMIND.get('documentId')}\n"
                f"[AutoMindCloud] JS commit: "
                f"{ULTIMO_ENVIO_AUTOMIND.get('jsCommit')}"
            )
        else:
            print(
                "[AutoMindCloud] Error Firestore: "
                f"{ULTIMO_ENVIO_AUTOMIND.get('code')} - "
                f"{ULTIMO_ENVIO_AUTOMIND.get('message')}\n"
                f"[AutoMindCloud] URL JS: "
                f"{ULTIMO_ENVIO_AUTOMIND.get('moduleUrl', 'No disponible')}\n"
                f"[AutoMindCloud] JS commit: "
                f"{ULTIMO_ENVIO_AUTOMIND.get('jsCommit', 'No disponible')}"
            )
