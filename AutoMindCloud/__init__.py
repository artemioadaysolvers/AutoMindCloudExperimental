from __future__ import annotations

import json
import os
import shutil
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

# Solo limita la lectura de metadata.AutoMind_Info.
# El envío a GitHub/Firebase se hace después en el navegador, sin bloquear
# la celda de Colab.
TIEMPO_MAXIMO_LEER_NOTEBOOK_SEGUNDOS = 3

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

# Se consulta GitHub en CADA envío para obtener el SHA más reciente
# que modificó exactamente este archivo.
_GITHUB_OWNER = "artemioadaysolvers"
_GITHUB_REPO = "AutoMindCloud-API"
_GITHUB_JS_PATH = "Data_Collector/automind-firestore.js"


# ============================================================
# RECURSOS VISUALES
# ============================================================
def _mostrar_banner():
    """Muestra el banner sin descargarlo mediante Python."""
    try:
        from IPython.display import Image, display
        display(Image(url=_BANNER_URL, width=700))
    except Exception:
        pass


def _descargar_click_sound():
    """
    Descarga click_sound.mp3 solamente si esta función se llama.
    No se descarga durante import AutoMindCloud.
    """
    try:
        import requests

        response = requests.get(_CLICK_SOUND_URL, timeout=8)
        response.raise_for_status()

        with open(_CLICK_SOUND_PATH, "wb") as file:
            file.write(response.content)

        return _CLICK_SOUND_PATH

    except Exception:
        return None


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
        raise ValueError(
            "Drive_Link debe ser un enlace o ID válido de Google Drive."
        )

    output_name = os.path.basename(str(Output_Name).strip())

    if not output_name or output_name in {".", ".."}:
        raise ValueError("Output_Name no es válido.")

    root_dir = Path("/content")
    root_dir.mkdir(parents=True, exist_ok=True)

    zip_path = root_dir / f"{output_name}.zip"
    temp_dir = root_dir / f"__tmp_extract_{uuid.uuid4().hex}"
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
        downloaded_path = gdown.download(
            url=drive_url,
            output=str(zip_path),
            quiet=False,
            fuzzy=True
        )

        if downloaded_path is None or not zip_path.exists():
            raise RuntimeError(
                "No se pudo descargar el ZIP desde Google Drive."
            )

        if not zipfile.is_zipfile(zip_path):
            raise zipfile.BadZipFile(
                "El archivo descargado no es un ZIP válido."
            )

        root_resolved = temp_dir.resolve()

        with zipfile.ZipFile(zip_path, "r") as zip_file:
            for member in zip_file.infolist():
                destination = (temp_dir / member.filename).resolve()

                if (
                    destination != root_resolved
                    and root_resolved not in destination.parents
                ):
                    raise RuntimeError(
                        "ZIP inseguro: ruta no permitida: "
                        f"{member.filename}"
                    )

            zip_file.extractall(temp_dir)

        def es_basura(name):
            return name.startswith(".") or name == "__MACOSX"

        visibles = [
            name
            for name in os.listdir(temp_dir)
            if not es_basura(name)
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

            for name in visibles:
                shutil.move(
                    str(temp_dir / name),
                    str(final_dir / name)
                )

        return str(final_dir)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ============================================================
# LEER AutoMind_Info
# ============================================================
def _obtener_automind_info(timeout_segundos):
    """
    Lee metadata.AutoMind_Info del notebook actual de Colab.
    """
    try:
        from google.colab import _message

        timeout = max(
            1,
            min(
                int(timeout_segundos),
                TIEMPO_MAXIMO_LEER_NOTEBOOK_SEGUNDOS
            )
        )

        response = _message.blocking_request(
            "get_ipynb",
            timeout_sec=timeout
        )

        notebook = response.get("ipynb", {})

        if isinstance(notebook, str):
            notebook = json.loads(notebook)

        if not isinstance(notebook, dict):
            return {"Estado": "Notebook no válido"}

        auto_mind_info = (
            notebook
            .get("metadata", {})
            .get("AutoMind_Info")
        )

        if not isinstance(auto_mind_info, dict):
            return {"Estado": "AutoMind_Info no encontrada"}

        return auto_mind_info

    except Exception as error:
        return {
            "Estado": "No fue posible leer AutoMind_Info",
            "Detalle": str(error)
        }


def _json_seguro_para_javascript(data):
    """
    Convierte un dict de Python a JSON seguro para una etiqueta script.
    """
    text = json.dumps(data, ensure_ascii=False)

    return (
        text
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


# ============================================================
# ENVÍO NO BLOQUEANTE DESDE EL FRONTEND
# ============================================================
def _inyectar_envio_frontend(auto_mind_info):
    """
    Inserta un script no bloqueante en la salida actual de Colab.

    El navegador:
      1. consulta GitHub para obtener el último SHA del JS;
      2. importa jsDelivr usando @SHA;
      3. llama enviarAutoMindFirestore(autoMindInfo);
      4. muestra el resultado en la salida de la celda.

    Python no espera GitHub, jsDelivr ni Firestore; por eso import no queda
    congelado aunque alguno de esos servicios tarde o falle.
    """
    try:
        from IPython.display import HTML, display

        if not isinstance(auto_mind_info, dict):
            auto_mind_info = {
                "Estado": "AutoMind_Info no válida"
            }

        auto_mind_json = _json_seguro_para_javascript(auto_mind_info)

        instance_id = f"automind_sender_{uuid.uuid4().hex}"
        status_id = f"automind_status_{uuid.uuid4().hex}"

        github_api_url = (
            "https://api.github.com/repos/"
            f"{_GITHUB_OWNER}/{_GITHUB_REPO}/commits"
            "?path=Data_Collector%2Fautomind-firestore.js"
            "&per_page=1"
        )

        html = r"""
<div id="__INSTANCE_ID__" style="display:none;"></div>

<pre id="__STATUS_ID__" style="
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
">⏳ AutoMindCloud: preparando envío…</pre>

<script type="module">
(async () => {
  const status = document.getElementById("__STATUS_ID__");

  function show(text, isError = false) {
    if (!status) return;
    status.style.borderColor = isError ? "#ff6b6b" : "#51cf66";
    status.textContent = text;
  }

  function withTimeout(promise, ms, label) {
    return Promise.race([
      promise,
      new Promise((_, reject) => {
        window.setTimeout(() => {
          reject(new Error(label + " superó " + ms + " ms."));
        }, ms);
      })
    ]);
  }

  async function getLatestCommitSha() {
    const controller = new AbortController();
    const timer = window.setTimeout(
      () => controller.abort(),
      6000
    );

    try {
      const response = await fetch(
        __GITHUB_API_URL_JSON__,
        {
          method: "GET",
          cache: "no-store",
          headers: {
            "Accept": "application/vnd.github+json"
          },
          signal: controller.signal
        }
      );

      if (!response.ok) {
        throw new Error(
          "GitHub respondió HTTP " + response.status + "."
        );
      }

      const commits = await response.json();
      const sha = commits?.[0]?.sha;

      if (
        typeof sha !== "string" ||
        !/^[0-9a-f]{40}$/i.test(sha)
      ) {
        throw new Error(
          "GitHub no devolvió un SHA válido para automind-firestore.js."
        );
      }

      return sha.toLowerCase();

    } finally {
      window.clearTimeout(timer);
    }
  }

  try {
    const autoMindInfo = __AUTOMIND_INFO_JSON__;

    show("⏳ AutoMindCloud: consultando último commit del JS…");

    const commitSha = await getLatestCommitSha();

    const moduleUrl =
      "https://cdn.jsdelivr.net/gh/" +
      "__GITHUB_OWNER__/" +
      "__GITHUB_REPO__@" +
      commitSha +
      "/__GITHUB_JS_PATH__";

    show(
      "⏳ AutoMindCloud: cargando JS del commit\\n" +
      commitSha
    );

    const modulo = await withTimeout(
      import(moduleUrl),
      12000,
      "La importación del módulo"
    );

    if (
      !modulo ||
      typeof modulo.enviarAutoMindFirestore !== "function"
    ) {
      throw new Error(
        "El módulo no exporta enviarAutoMindFirestore."
      );
    }

    show("⏳ AutoMindCloud: enviando a Firestore…");

    const resultado = await withTimeout(
      modulo.enviarAutoMindFirestore(autoMindInfo),
      20000,
      "El envío a Firestore"
    );

    if (
      !resultado ||
      typeof resultado !== "object" ||
      Array.isArray(resultado)
    ) {
      throw new Error(
        "automind-firestore.js devolvió: " +
        String(resultado)
      );
    }

    console.log(
      "[AutoMindCloud] Resultado Firestore:",
      resultado
    );

    if (resultado.ok !== true) {
      show(
        "❌ AutoMindCloud no pudo guardar en Firestore.\\n\\n" +
        "Código:\\n" +
        (resultado.code || "unknown-error") +
        "\\n\\nDetalle:\\n" +
        (resultado.message || JSON.stringify(resultado, null, 2)) +
        "\\n\\nCommit JS:\\n" +
        commitSha +
        "\\n\\nURL JS:\\n" +
        moduleUrl,
        true
      );
      return;
    }

    show(
      "✅ AutoMindCloud: guardado correctamente.\\n\\n" +
      "Ruta:\\n" +
      resultado.collectionName + "/" +
      resultado.ipDocument + "/JSON/" +
      resultado.documentId +
      "\\n\\nCommit JS:\\n" +
      commitSha,
      false
    );

  } catch (error) {
    console.error(
      "[AutoMindCloud] Error al guardar en Firestore:",
      error
    );

    show(
      "❌ AutoMindCloud no pudo guardar en Firestore.\\n\\n" +
      "Código:\\n" +
      (error?.code || "frontend-error") +
      "\\n\\nDetalle:\\n" +
      (error?.message || String(error)),
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
            .replace("__AUTOMIND_INFO_JSON__", auto_mind_json)
            .replace(
                "__GITHUB_API_URL_JSON__",
                json.dumps(github_api_url, ensure_ascii=False)
            )
            .replace("__GITHUB_OWNER__", _GITHUB_OWNER)
            .replace("__GITHUB_REPO__", _GITHUB_REPO)
            .replace("__GITHUB_JS_PATH__", _GITHUB_JS_PATH)
        )

        display(HTML(html))
        return True

    except Exception as error:
        print(
            "[AutoMindCloud] No se pudo iniciar el envío a Firestore: "
            f"{type(error).__name__}: {error}"
        )
        return False


# ============================================================
# FUNCIÓN PÚBLICA
# ============================================================
def reenviar_automind_firestore(
    autoMindInfo=None,
    timeout_segundos=TIEMPO_MAXIMO_LEER_NOTEBOOK_SEGUNDOS
):
    """
    Inicia un envío no bloqueante.

    La función retorna cuando el navegador recibió el trabajo; el resultado
    final aparece dentro del cuadro de salida de Colab.
    """
    if autoMindInfo is None:
        autoMindInfo = _obtener_automind_info(timeout_segundos)

    return _inyectar_envio_frontend(autoMindInfo)


# ============================================================
# ACTIVACIÓN AUTOMÁTICA AL IMPORTAR
# ============================================================
if MOSTRAR_BANNER_AL_IMPORTAR:
    _mostrar_banner()

if ENVIAR_AUTOMATICAMENTE_AL_IMPORTAR:
    reenviar_automind_firestore()
