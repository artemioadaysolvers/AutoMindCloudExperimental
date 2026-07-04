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
# Envía AutoMind_Info automáticamente al importar el paquete.
# Python no espera Firestore: el envío ocurre en segundo plano con IPython HTML.

import json
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
    Retorna de inmediato; Firestore continúa en segundo plano.
    """
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

    const resultado = await modulo.enviarAutoMindFirestore(
      autoMindInfo
    );

  

  } catch (error) {
    console.error(
      "[AutoMindCloud] Error durante envío:",
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


# ============================================================
# ENVÍO AUTOMÁTICO AL HACER import AutoMindCloud
# ============================================================
reenviar_automind_firestore()




