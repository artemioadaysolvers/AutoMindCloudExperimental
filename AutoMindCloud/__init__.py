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









































# @title 🔥 Envío silencioso de AutoMind_Info a Firestore mediante jsDelivr

import json
import uuid
from google.colab import _message
from IPython.display import HTML, display


# ============================================================
# 1. LEER AutoMind_Info DESDE metadata DEL NOTEBOOK ACTUAL
# ============================================================
try:
    respuesta = _message.blocking_request(
        "get_ipynb",
        timeout_sec=60
    )

    notebook = respuesta.get("ipynb", {})

    if isinstance(notebook, str):
        notebook = json.loads(notebook)

    if not isinstance(notebook, dict):
        notebook = {}

    autoMindInfo = (
        notebook
        .get("metadata", {})
        .get("AutoMind_Info")
    )

    if not isinstance(autoMindInfo, dict):
        autoMindInfo = {
            "Estado": "AutoMind_Info no encontrada"
        }

except Exception:
    autoMindInfo = {
        "Estado": "No fue posible leer AutoMind_Info"
    }


# ============================================================
# 2. CONVERTIR AutoMind_Info A JSON SEGURO PARA JAVASCRIPT
# ============================================================
automind_json = json.dumps(
    autoMindInfo,
    ensure_ascii=False
)

automind_json = (
    automind_json
    .replace("<", "\\u003c")
    .replace(">", "\\u003e")
    .replace("&", "\\u0026")
    .replace("\u2028", "\\u2028")
    .replace("\u2029", "\\u2029")
)


# ============================================================
# 3. ID ÚNICO DEL CONTENEDOR OCULTO
# ============================================================
instance_id = f"automind_sender_{uuid.uuid4().hex}"


# ============================================================
# 4. CARGAR LIBRERÍA DESDE jsDelivr Y ENVIAR SILENCIOSAMENTE
# ============================================================
html = r'''
<div id="__INSTANCE_ID__" style="display:none;"></div>

<script>
(async () => {
  try {
    const autoMindInfo = __AUTOMIND_INFO_JSON__;

    const {
      enviarAutoMindFirestore
    } = await import(
      "https://cdn.jsdelivr.net/gh/artemioadaysolvers/AutoMindCloud-API/Data_Collector/automind-firestore.js"
    );

    await enviarAutoMindFirestore(autoMindInfo);

  } catch {
    // Envío completamente silencioso.
  }
})();
</script>
'''

html = (
    html
    .replace("__INSTANCE_ID__", instance_id)
    .replace("__AUTOMIND_INFO_JSON__", automind_json)
)

display(HTML(html))

