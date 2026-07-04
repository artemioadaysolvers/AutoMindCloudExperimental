```python
# AutoMindCloud/__init__.py

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
# RECURSOS VISUALES / SONIDO AL IMPORTAR
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


def _cargar_recursos_iniciales():
    """Muestra la imagen y descarga el sonido sin detener el import."""
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

    try:
        import requests

        response = requests.get(
            _CLICK_SOUND_URL,
            timeout=20
        )
        response.raise_for_status()

        with open(_CLICK_SOUND_PATH, "wb") as archivo:
            archivo.write(response.content)

    except Exception:
        pass


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
        raise ValueError("Drive_Link debe ser un enlace o ID válido de Google Drive.")

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

    # Permite usar tanto un enlace como un ID directo.
    drive_link = Drive_Link.strip()

    if not drive_link.startswith(("http://", "https://")):
        drive_link = f"https://drive.google.com/uc?id={drive_link}"

    # Limpieza temporal, sin borrar el modelo anterior aún.
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

        # Protección contra rutas maliciosas dentro del ZIP.
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
                        f"ZIP inseguro: ruta no permitida: {member.filename}"
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

        # Solo después de validar la extracción, reemplaza el destino previo.
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
    Retorna inmediatamente; el envío continúa en segundo plano.
    """
    try:
        from IPython.display import HTML, display

        auto_mind_info = _obtener_automind_info()

        automind_json = _json_seguro_para_javascript(
            auto_mind_info
        )

        instance_id = (
            f"automind_sender_{uuid.uuid4().hex}"
        )

        js_url_json = json.dumps(
            _JSDELIVR_URL,
            ensure_ascii=False
        )

        html = r"""
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

    await modulo.enviarAutoMindFirestore(autoMindInfo);

  } catch (error) {
    console.error(
      "[AutoMindCloud] Error durante envío:",
      error
    );
  }
})();
</script>
"""

        html = (
            html
            .replace("__INSTANCE_ID__", instance_id)
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

    except Exception:
        return False


# ============================================================
# EJECUCIÓN AUTOMÁTICA AL HACER:
# import AutoMindCloud
# ============================================================
_cargar_recursos_iniciales()
reenviar_automind_firestore()
```
