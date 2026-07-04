import json
import os
import shutil
import time
import uuid
import zipfile
from pathlib import Path


# ============================================================
# EXPORTACIONES PÚBLICAS
# ============================================================
__all__ = [
    "Download_Zip",
    "reenviar_automind_firestore",
]


# ============================================================
# CONFIGURACIÓN
# ============================================================
MOSTRAR_BANNER_AL_IMPORTAR = True
ENVIAR_AUTOMATICAMENTE_AL_IMPORTAR = True
TIEMPO_MAXIMO_LEER_NOTEBOOK_SEGUNDOS = 6

_AUTO_ENVIO_INICIADO = False

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

_JSDELIVR_URL = (
    "https://cdn.jsdelivr.net/gh/"
    "artemioadaysolvers/"
    "AutoMindCloud-API/"
    "Data_Collector/"
    "automind-firestore.js"
)


# ============================================================
# UTILIDADES VISUALES
# ============================================================
def _mostrar_banner():
    """Muestra el banner sin descargarlo en Python."""
    try:
        from IPython.display import Image, display

        display(Image(url=_BANNER_URL, width=700))
    except Exception:
        pass


def _descargar_click_sound():
    """
    Descarga el sonido solo cuando se llama explícitamente.
    """
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
    Descarga un ZIP de Google Drive, lo extrae y retorna la carpeta final.

    Ejemplo:
        ruta = Download_Zip(
            Drive_Link="https://drive.google.com/file/d/...",
            Output_Name="StepModel"
        )
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

        if final_dir.exists():
            shutil.rmtree(final_dir, ignore_errors=True)

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
# AUTO MIND INFO: LECTURA DESDE METADATA DEL NOTEBOOK
# ============================================================
def _obtener_automind_info(timeout_segundos):
    """
    Lee metadata.AutoMind_Info del notebook abierto actualmente en Colab.
    """
    try:
        from google.colab import _message

        timeout = max(1, min(int(timeout_segundos), 12))

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


def _json_seguro_para_javascript(data):
    """
    Convierte un objeto Python en JSON seguro para insertarlo dentro de
    una etiqueta <script>.
    """
    texto = json.dumps(data, ensure_ascii=False)

    return (
        texto
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


# ============================================================
# ENVÍO A FIRESTORE DESDE EL FRONTEND
# ============================================================
def _inyectar_envio_frontend(auto_mind_info, mostrar_estado=True):
    """
    Inserta el módulo JavaScript en la salida de la celda actual.

    No usa threading: en Colab, display(HTML(...)) debe ejecutarse en
    el hilo principal para que el navegador reciba el script.

    Si Firestore falla, se muestra:
      - el código exacto del error;
      - la respuesta cruda del módulo;
      - la URL exacta del módulo que cargó el navegador.
    """
    try:
        from IPython.display import HTML, display

        if not isinstance(auto_mind_info, dict):
            auto_mind_info = {
                "Estado": "AutoMind_Info no válida"
            }

        automind_json = _json_seguro_para_javascript(auto_mind_info)
        module_url_json = _json_seguro_para_javascript(_JSDELIVR_URL)

        instance_id = f"automind_sender_{uuid.uuid4().hex}"
        status_id = f"automind_status_{uuid.uuid4().hex}"
        status_visible = "block" if mostrar_estado else "none"
        mostrar_estado_js = "true" if mostrar_estado else "false"

        html = r"""
<div id="__INSTANCE_ID__" style="display:none;"></div>

<pre id="__STATUS_ID__" style="
  display: __STATUS_VISIBLE__;
  margin: 8px 0;
  padding: 10px 12px;
  border: 1px solid #555;
  border-radius: 8px;
  background: #111;
  color: #eee;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  white-space: pre-wrap;
  overflow: auto;
">⏳ AutoMindCloud: enviando información a Firestore…</pre>

<script type="module">
(async () => {
  const estado = document.getElementById("__STATUS_ID__");
  const mostrarEstado = __SHOW_STATUS__;

  function stringifySeguro(valor) {
    try {
      const texto = JSON.stringify(valor, null, 2);
      return typeof texto === "string" ? texto : String(valor);
    } catch (_) {
      try {
        return String(valor);
      } catch (_) {
        return "[No fue posible convertir el resultado a texto]";
      }
    }
  }

  function mostrar(texto, error) {
    if (!estado) return;

    if (!mostrarEstado && !error) {
      estado.style.display = "none";
      return;
    }

    estado.style.display = "block";
    estado.style.borderColor = error ? "#ff6b6b" : "#51cf66";
    estado.textContent = texto;
  }

  try {
    const autoMindInfo = __AUTOMIND_INFO_JSON__;
    const baseModuleUrl = __MODULE_URL_JSON__;

    // Fuerza una versión fresca al actualizar el archivo en GitHub/jsDelivr.
    const separador = baseModuleUrl.includes("?") ? "&" : "?";
    const moduleUrl = (
      baseModuleUrl +
      separador +
      "v=" +
      Date.now() +
      "_" +
      Math.random().toString(36).slice(2)
    );

    const modulo = await import(moduleUrl);

    if (
      !modulo ||
      typeof modulo.enviarAutoMindFirestore !== "function"
    ) {
      const error = new Error(
        "El módulo remoto no exporta enviarAutoMindFirestore.\n" +
        "URL cargada: " + moduleUrl
      );
      error.code = "module-export-missing";
      throw error;
    }

    const resultado = await modulo.enviarAutoMindFirestore(autoMindInfo);

    console.log("[AutoMindCloud] URL cargada:", moduleUrl);
    console.log(
      "[AutoMindCloud] Resultado crudo de Firestore:",
      resultado
    );

    if (resultado === undefined || resultado === null) {
      const error = new Error(
        "El módulo remoto devolvió " + String(resultado) + ".\n\n" +
        "Tu archivo automind-firestore.js debe retornar:\n" +
        "{ ok: true, collectionName, ipDocument, documentId }\n" +
        "o bien:\n" +
        "{ ok: false, code, message }\n\n" +
        "URL cargada:\n" + moduleUrl
      );
      error.code = "invalid-module-response";
      throw error;
    }

    if (resultado.ok !== true) {
      const error = new Error(
        "Respuesta exacta del módulo Firestore:\n" +
        stringifySeguro(resultado) +
        "\n\nURL cargada:\n" +
        moduleUrl
      );
      error.code = resultado.code || "unknown-error";
      error.firestoreResult = resultado;
      throw error;
    }

    mostrar(
      "✅ AutoMindCloud: guardado correctamente.\n\n" +
      "Ruta:\n" +
      resultado.collectionName + "/" +
      resultado.ipDocument + "/JSON/" +
      resultado.documentId,
      false
    );

  } catch (error) {
    console.error(
      "[AutoMindCloud] Error completo al guardar en Firestore:",
      error
    );

    if (error && error.firestoreResult !== undefined) {
      console.error(
        "[AutoMindCloud] Respuesta cruda del módulo:",
        error.firestoreResult
      );
    }

    mostrar(
      "❌ AutoMindCloud no pudo guardar en Firestore.\n\n" +
      "Código:\n" +
      (error && error.code ? error.code : "unknown-error") +
      "\n\nDetalle:\n" +
      (error && error.message ? error.message : String(error)),
      true
    );
  }
})();
</script>
"""

        html = (
            html
            .replace("__INSTANCE_ID__", instance_id)
            .replace("__STATUS_ID__", status_id)
            .replace("__STATUS_VISIBLE__", status_visible)
            .replace("__SHOW_STATUS__", mostrar_estado_js)
            .replace("__AUTOMIND_INFO_JSON__", automind_json)
            .replace("__MODULE_URL_JSON__", module_url_json)
        )

        display(HTML(html))
        return True

    except Exception as error:
        print(
            "[AutoMindCloud] No se pudo inyectar el envío a Firestore:\n"
            f"{type(error).__name__}: {error}"
        )
        return False


def reenviar_automind_firestore(
    autoMindInfo=None,
    timeout_segundos=TIEMPO_MAXIMO_LEER_NOTEBOOK_SEGUNDOS
):
    """
    Envía AutoMind_Info a Firestore manualmente.

    Uso:
        import AutoMindCloud
        AutoMindCloud.reenviar_automind_firestore()

    También puedes entregar un diccionario de forma explícita:
        AutoMindCloud.reenviar_automind_firestore(
            {"Modelo": "Prueba"}
        )
    """
    if autoMindInfo is None:
        autoMindInfo = _obtener_automind_info(timeout_segundos)

    return _inyectar_envio_frontend(
        autoMindInfo,
        mostrar_estado=True
    )


# ============================================================
# ENVÍO AUTOMÁTICO AL IMPORTAR
# ============================================================
def _envio_automatico_al_importar():
    """
    Realiza el envío durante la ejecución de la celda de importación.

    No usa un thread porque Colab no garantiza que un display generado
    fuera del hilo principal llegue al frontend del navegador.
    """
    global _AUTO_ENVIO_INICIADO

    if _AUTO_ENVIO_INICIADO:
        return False

    _AUTO_ENVIO_INICIADO = True

    auto_mind_info = _obtener_automind_info(
        TIEMPO_MAXIMO_LEER_NOTEBOOK_SEGUNDOS
    )

    return _inyectar_envio_frontend(
        auto_mind_info,
        mostrar_estado=True
    )


if MOSTRAR_BANNER_AL_IMPORTAR:
    _mostrar_banner()

if ENVIAR_AUTOMATICAMENTE_AL_IMPORTAR:
    _envio_automatico_al_importar()
