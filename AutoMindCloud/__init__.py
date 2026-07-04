import json
import os
import shutil
import uuid
import zipfile
from pathlib import Path


# ============================================================
# FUNCIONES QUE SE EXPORTAN CON:
# from AutoMindCloud import *
# ============================================================
__all__ = [
    "Download_Zip",
    "reenviar_automind_firestore",
]


# ============================================================
# CONFIGURACIÓN
# ============================================================
MOSTRAR_BANNER_AL_IMPORTAR = True

# Se envía automáticamente al importar el paquete.
# Colab requiere que la inyección HTML ocurra en el hilo principal.
ENVIAR_AUTOMATICAMENTE_AL_IMPORTAR = True

# Límite de espera solo para leer metadata.AutoMind_Info.
TIEMPO_MAXIMO_LEER_NOTEBOOK_SEGUNDOS = 6

_AUTO_ENVIO_INICIADO = False


# ============================================================
# RECURSOS VISUALES / SONIDO
# ============================================================
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


def _mostrar_banner():
    """
    Muestra el banner mediante URL.
    No descarga el archivo desde Python.
    """
    try:
        from IPython.display import Image, display

        display(
            Image(
                url=_BANNER_URL,
                width=700
            )
        )
    except Exception:
        pass


def _descargar_click_sound():
    """
    Descarga el sonido solo si se llama explícitamente.
    No se ejecuta al importar AutoMindCloud.
    """
    try:
        import requests

        response = requests.get(
            _CLICK_SOUND_URL,
            timeout=10
        )
        response.raise_for_status()

        with open(_CLICK_SOUND_PATH, "wb") as archivo:
            archivo.write(response.content)

        return _CLICK_SOUND_PATH

    except Exception:
        return None


# ============================================================
# DESCARGAR Y EXTRAER ZIP DE GOOGLE DRIVE
# ============================================================
def Download_Zip(Drive_Link, Output_Name="USDModel"):
    """
    Descarga un ZIP de Google Drive, lo extrae y devuelve la carpeta final.

    Ejemplo:
        ruta = Download_Zip(
            Drive_Link=Link,
            Output_Name="StepModel"
        )

    Retorna:
        /content/StepModel
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

    output_name = os.path.basename(
        str(Output_Name).strip()
    )

    if not output_name or output_name in {".", ".."}:
        raise ValueError("Output_Name no es válido.")

    root_dir = Path("/content")
    root_dir.mkdir(parents=True, exist_ok=True)

    zip_path = root_dir / f"{output_name}.zip"
    tmp_extract = root_dir / f"__tmp_extract_{output_name}"
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

        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.infolist():
                destination = (
                    tmp_extract / member.filename
                ).resolve()

                if (
                    destination != root_resolved
                    and root_resolved not in destination.parents
                ):
                    raise RuntimeError(
                        "ZIP inseguro: ruta no permitida: "
                        f"{member.filename}"
                    )

            zf.extractall(tmp_extract)

        def es_basura(nombre):
            return (
                nombre.startswith(".")
                or nombre == "__MACOSX"
            )

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
# ENVÍO DE AutoMind_Info A FIRESTORE
# ============================================================
_JSDELIVR_URL = (
    "https://cdn.jsdelivr.net/gh/"
    "artemioadaysolvers/"
    "AutoMindCloud-API/"
    "Data_Collector/"
    "automind-firestore.js"
)


def _obtener_automind_info(timeout_segundos):
    """
    Lee metadata.AutoMind_Info del notebook actual.

    Esta función puede tardar algunos segundos. Se ejecuta antes
    de inyectar el JavaScript en la salida de la celda actual.
    """
    try:
        from google.colab import _message

        timeout_segundos = max(
            1,
            min(int(timeout_segundos), 12)
        )

        respuesta = _message.blocking_request(
            "get_ipynb",
            timeout_sec=timeout_segundos
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
    Convierte objetos Python a JSON seguro para insertarlos
    dentro de una etiqueta <script>.
    """
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


def _inyectar_envio_frontend(
    auto_mind_info,
    mostrar_estado=True
):
    """
    Inserta JavaScript en la salida de la celda actual.

    IMPORTANTE:
    display(HTML(...)) debe ejecutarse desde el hilo principal de
    la celda de Colab. Así el navegador recibe y ejecuta el módulo.
    """
    try:
        from IPython.display import HTML, display

        if not isinstance(auto_mind_info, dict):
            auto_mind_info = {
                "Estado": "AutoMind_Info no válida"
            }

        automind_json = _json_seguro_para_javascript(
            auto_mind_info
        )

        js_url_json = _json_seguro_para_javascript(
            _JSDELIVR_URL
        )

        instance_id = (
            f"automind_sender_{uuid.uuid4().hex}"
        )
        estado_id = (
            f"automind_estado_{uuid.uuid4().hex}"
        )
        mostrar_estado_json = (
            "true" if mostrar_estado else "false"
        )

        html = r"""
<div id="__INSTANCE_ID__" style="display:none;"></div>

<div id="__STATUS_ID__" style="
  display: __STATUS_DISPLAY__;
  margin: 8px 0;
  padding: 10px 12px;
  border: 1px solid #555;
  border-radius: 8px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  white-space: pre-wrap;
">
⏳ AutoMindCloud: enviando información a Firestore…
</div>

<script type="module">
(async () => {
  const estado = document.getElementById("__STATUS_ID__");
  const mostrarEstado = __SHOW_STATUS__;

  function mostrar(texto, esError) {
    if (!estado) return;

    if (!mostrarEstado && !esError) {
      estado.style.display = "none";
      return;
    }

    estado.style.display = "block";
    estado.style.borderColor = esError ? "#b42318" : "#188038";
    estado.textContent = texto;
  }

  try {
    const autoMindInfo = __AUTOMIND_INFO_JSON__;
    const moduleUrl = __MODULE_URL_JSON__;

    // Evita usar una copia antigua retenida por caché de jsDelivr.
    const separador = moduleUrl.includes("?") ? "&" : "?";
    const modulo = await import(
      moduleUrl + separador + "v=" + Date.now()
    );

    if (
      !modulo ||
      typeof modulo.enviarAutoMindFirestore !== "function"
    ) {
      throw new Error(
        "El módulo no exporta enviarAutoMindFirestore."
      );
    }

    const resultado = await modulo.enviarAutoMindFirestore(
      autoMindInfo
    );

    if (!resultado || resultado.ok !== true) {
      const error = new Error(
        resultado?.message ||
        "Firestore no confirmó el guardado."
      );
      error.code = resultado?.code || "unknown-error";
      throw error;
    }

    mostrar(
      "✅ AutoMindCloud: guardado en " +
      resultado.collectionName + "/" +
      resultado.ipDocument + "/JSON/" +
      resultado.documentId,
      false
    );

  } catch (error) {
    console.error(
      "[AutoMindCloud] Error al guardar en Firestore:",
      error
    );

    mostrar(
      "❌ AutoMindCloud no pudo guardar.\n" +
      "Código: " + (error?.code || "unknown-error") + "\n" +
      "Detalle: " + (
        error?.message || String(error)
      ),
      true
    );
  }
})();
</script>
"""

        html = (
            html
            .replace("__INSTANCE_ID__", instance_id)
            .replace("__STATUS_ID__", estado_id)
            .replace(
                "__STATUS_DISPLAY__",
                "block" if mostrar_estado else "none"
            )
            .replace(
                "__SHOW_STATUS__",
                mostrar_estado_json
            )
            .replace(
                "__AUTOMIND_INFO_JSON__",
                automind_json
            )
            .replace(
                "__MODULE_URL_JSON__",
                js_url_json
            )
        )

        display(HTML(html))
        return True

    except Exception as error:
        print(
            "[AutoMindCloud] No se pudo inyectar "
            f"el envío a Firestore: {error}"
        )
        return False
def reenviar_automind_firestore(
    autoMindInfo=None,
    timeout_segundos=TIEMPO_MAXIMO_LEER_NOTEBOOK_SEGUNDOS
):
    """
    Envío manual.

    Si no se recibe autoMindInfo, lee metadata.AutoMind_Info
    desde el notebook actual y luego inyecta el JavaScript.
    """
    if autoMindInfo is None:
        autoMindInfo = _obtener_automind_info(
            timeout_segundos
        )

    return _inyectar_envio_frontend(
        autoMindInfo
    )


# ============================================================
# ENVÍO AUTOMÁTICO AL HACER:
# import AutoMindCloud
# ============================================================
def _envio_automatico_al_importar():
    """
    Ejecuta el envío en el hilo principal.

    No se usa threading: Colab debe recibir display(HTML(...))
    durante la ejecución de la celda para que el JavaScript exista
    en el frontend y pueda guardar en Firestore.
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
