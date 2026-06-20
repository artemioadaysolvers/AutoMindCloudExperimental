from IPython.display import HTML, display
from google.colab import output

import base64
import json
import os
import re
import time
from typing import Dict, List, Optional

# =============================================================================
# PIZARRA PERSISTENTE Y OPTIMIZADA PARA GOOGLE COLAB
#
# Principios de esta versión:
#   1. El runtime mantiene sólo el último PNG por board en un diccionario.
#   2. El .ipynb se lee sólo al iniciar/recargar/diagnosticar, nunca por trazo.
#   3. El navegador aplica debounce y envía únicamente el snapshot más reciente.
#   4. El guardado programático del notebook tiene rate limit.
#   5. El output visible se reemplaza únicamente al ocultar/salir de la pestaña,
#      para que Colab pueda restaurarlo sin volver a ejecutar la celda.
#   6. Undo/Redo guarda comandos de trazos en vez de PNG completos.
# =============================================================================

_AUDIO_FILE = "click_sound.mp3"
_SAVE_COOLDOWN_SECONDS = 2.0
_RUNTIME_PNG_DIR = "/content"

_b64_audio: Optional[str] = None
if os.path.exists(_AUDIO_FILE):
    try:
        with open(_AUDIO_FILE, "rb") as _fh:
            _b64_audio = base64.b64encode(_fh.read()).decode("ascii")
    except Exception:
        _b64_audio = None

# serial -> {serial, png_b64, revision, updated_at, source_cell, source_output}
boards_guardados: Dict[str, dict] = {}

# Handles de outputs de la sesión actual.
_SNAPSHOT_HANDLES: Dict[str, object] = {}
_BOARD_HANDLES: Dict[str, object] = {}
_REGISTERED_CALLBACKS = set()
_LAST_NOTEBOOK_SAVE_AT = 0.0


def _sanitize_serial(value: str) -> str:
    value = (value or "board").strip()
    value = re.sub(r"[^A-Za-z0-9_]+", "_", value)
    return value or "board"


def _mime_to_text(value) -> str:
    if isinstance(value, list):
        return "".join(str(item) for item in value)
    return str(value or "")


def _read_notebook_json() -> dict:
    """Lee el notebook vivo sólo para recuperación o diagnóstico."""
    try:
        from google.colab import _message

        try:
            response = _message.blocking_request("get_ipynb", timeout_sec=60)
        except TypeError:
            response = _message.blocking_request(
                "get_ipynb", request="", timeout_sec=60
            )

        response = response or {}
        raw = response.get("ipynb", response) if isinstance(response, dict) else response
        if isinstance(raw, str):
            raw = json.loads(raw)
        return raw if isinstance(raw, dict) else {}
    except Exception as exc:
        print("[boards] No se pudo leer get_ipynb:", repr(exc))
        return {}


def _snapshot_pattern_for_serial(serial: Optional[str] = None) -> re.Pattern:
    """Busca carriers persistentes y el snapshot embebido del output visible.

    ``serial=None`` sirve para el listado completo. Cuando se entrega un serial,
    la búsqueda es puntual: board("123") no necesita haber llamado get_boards().
    """
    if serial is None:
        id_pattern = (
            r"(?:amc_persisted_snapshot_(?:ext_|int_)?(?P<serial>[A-Za-z0-9_]+)"
            r"|amc_board_embedded_snapshot_(?P<embedded_serial>[A-Za-z0-9_]+))"
        )
    else:
        clean = _sanitize_serial(serial)
        exact = re.escape(clean)
        id_pattern = (
            r"(?:amc_persisted_snapshot_(?:ext_|int_)?" + exact
            + r"|amc_board_embedded_snapshot_" + exact + r")"
        )

    return re.compile(
        r'<img\b'
        r'(?=[^>]*\bid=["\']' + id_pattern + r'["\'])'
        r'(?=[^>]*\bsrc=["\'](?P<src>data:image/png;base64,[^"\']+)["\'])'
        r'(?=[^>]*\bdata-amc-revision=["\'](?P<revision>\d+)["\'])?'
        r'[^>]*>',
        re.IGNORECASE | re.DOTALL,
    )


def _select_newer_snapshot(previous: Optional[dict], candidate: dict) -> dict:
    """Elige mayor revisión; en empate, el output más reciente del notebook."""
    if previous is None:
        return candidate

    old_key = (
        int(previous.get("revision", 0) or 0),
        int(previous.get("source_cell", -1) or -1),
        int(previous.get("source_output", -1) or -1),
    )
    new_key = (
        int(candidate.get("revision", 0) or 0),
        int(candidate.get("source_cell", -1) or -1),
        int(candidate.get("source_output", -1) or -1),
    )
    return candidate if new_key >= old_key else previous


def _extract_all_boards_from_notebook(nb: dict) -> List[dict]:
    """Obtiene el snapshot más nuevo de cada board guardado en el .ipynb."""
    if not isinstance(nb, dict):
        return []

    image_pattern = _snapshot_pattern_for_serial()
    latest: Dict[str, dict] = {}

    for cell_index, cell in enumerate(nb.get("cells", [])):
        if not isinstance(cell, dict):
            continue
        for output_index, out in enumerate(cell.get("outputs", [])):
            if not isinstance(out, dict):
                continue
            data = out.get("data", {}) or {}
            for mime in ("text/html", "text/plain", "text"):
                if mime not in data:
                    continue
                html = _mime_to_text(data[mime])
                for match in image_pattern.finditer(html):
                    serial = _sanitize_serial(
                        match.groupdict().get("serial")
                        or match.groupdict().get("embedded_serial")
                        or "board"
                    )
                    try:
                        png_b64 = match.group("src").split(",", 1)[1]
                        base64.b64decode(png_b64, validate=True)
                        revision = int(match.groupdict().get("revision") or 0)
                    except Exception:
                        continue

                    candidate = {
                        "serial": serial,
                        "png_b64": png_b64,
                        "revision": revision,
                        "updated_at": 0.0,
                        "source_cell": cell_index,
                        "source_output": output_index,
                    }
                    latest[serial] = _select_newer_snapshot(latest.get(serial), candidate)

    return list(latest.values())


def _recover_single_board_from_notebook(serial: str) -> Optional[dict]:
    """Recupera únicamente la board solicitada, sin poblar todas las demás.

    La API get_ipynb de Colab entrega el documento completo, pero aquí se
    analiza sólo el carrier/snapshot del serial pedido y no se reconstruye la
    lista total de boards. Esta función se usa automáticamente desde board().
    """
    serial = _sanitize_serial(serial)
    notebook = _read_notebook_json()
    if not isinstance(notebook, dict):
        return None

    image_pattern = _snapshot_pattern_for_serial(serial)
    latest: Optional[dict] = None

    for cell_index, cell in enumerate(notebook.get("cells", [])):
        if not isinstance(cell, dict):
            continue
        for output_index, out in enumerate(cell.get("outputs", [])):
            if not isinstance(out, dict):
                continue
            data = out.get("data", {}) or {}
            for mime in ("text/html", "text/plain", "text"):
                if mime not in data:
                    continue
                html = _mime_to_text(data[mime])
                for match in image_pattern.finditer(html):
                    try:
                        png_b64 = match.group("src").split(",", 1)[1]
                        base64.b64decode(png_b64, validate=True)
                        revision = int(match.groupdict().get("revision") or 0)
                    except Exception:
                        continue

                    candidate = {
                        "serial": serial,
                        "png_b64": png_b64,
                        "revision": revision,
                        "updated_at": 0.0,
                        "source_cell": cell_index,
                        "source_output": output_index,
                    }
                    latest = _select_newer_snapshot(latest, candidate)

    if latest is not None:
        boards_guardados[serial] = dict(latest)
    return latest


def _find_board_record(serial: str) -> Optional[dict]:
    return boards_guardados.get(_sanitize_serial(serial))


def _upsert_board_record(
    serial: str,
    data_url_png: str,
    client_revision=None,
) -> Optional[dict]:
    """Valida y actualiza la única copia autoritativa del runtime."""
    serial = _sanitize_serial(serial)
    prefix = "data:image/png;base64,"
    if not isinstance(data_url_png, str) or not data_url_png.startswith(prefix):
        return None

    png_b64 = data_url_png[len(prefix):]
    try:
        base64.b64decode(png_b64, validate=True)
    except Exception:
        return None

    previous = boards_guardados.get(serial, {})
    try:
        requested_revision = int(client_revision or 0)
    except Exception:
        requested_revision = 0

    previous_revision = int(previous.get("revision", 0) or 0)
    record = {
        "serial": serial,
        "png_b64": png_b64,
        "revision": max(previous_revision + 1, requested_revision),
        "updated_at": time.time(),
        "source_cell": previous.get("source_cell"),
        "source_output": previous.get("source_output"),
    }
    boards_guardados[serial] = record
    return record


def recargar_boards_desde_notebook(conservar_runtime: bool = True) -> List[dict]:
    """Recupera snapshots desde outputs del .ipynb y luego descarta su JSON."""
    notebook = _read_notebook_json()
    recovered = _extract_all_boards_from_notebook(notebook)

    if conservar_runtime:
        merged = {item["serial"]: dict(item) for item in recovered}
        for serial, item in boards_guardados.items():
            # El estado vivo del runtime tiene prioridad cuando ya fue editado.
            if item.get("updated_at", 0) > 0:
                merged[serial] = dict(item)
        boards_guardados.clear()
        boards_guardados.update(merged)
    else:
        boards_guardados.clear()
        boards_guardados.update({item["serial"]: dict(item) for item in recovered})

    return [dict(boards_guardados[key]) for key in sorted(boards_guardados)]


def listar_boards(incluir_base64: bool = False, recargar: bool = False) -> List[dict]:
    """Lista boards sin forzar la lectura del .ipynb, salvo recargar=True."""
    if recargar:
        recargar_boards_desde_notebook()

    records = [boards_guardados[key] for key in sorted(boards_guardados)]
    if incluir_base64:
        return [dict(item) for item in records]

    return [
        {
            "serial": item.get("serial"),
            "bytes_png_aprox": len(item.get("png_b64", "")) * 3 // 4,
            "revision": item.get("revision", 0),
            "updated_at": item.get("updated_at", 0),
            "source_cell": item.get("source_cell"),
            "source_output": item.get("source_output"),
        }
        for item in records
    ]


# Alias compatible con notebooks que usaban get_boards().
def get_boards(incluir_base64: bool = False, recargar: bool = False) -> List[dict]:
    return listar_boards(incluir_base64=incluir_base64, recargar=recargar)


def diagnostico_boards() -> dict:
    """Diagnóstico explícito: aquí sí se lee el .ipynb completo."""
    notebook = _read_notebook_json()
    cells = notebook.get("cells", []) if isinstance(notebook, dict) else []
    from_notebook = _extract_all_boards_from_notebook(notebook)

    return {
        "notebook_json_es_dict": isinstance(notebook, dict),
        "numero_celdas": len(cells),
        "numero_outputs": sum(
            len(cell.get("outputs", []))
            for cell in cells
            if isinstance(cell, dict)
        ),
        "boards_en_notebook": [item["serial"] for item in from_notebook],
        "boards_en_runtime": [
            {
                "serial": item["serial"],
                "revision": item.get("revision", 0),
                "updated_at": item.get("updated_at", 0),
            }
            for item in (boards_guardados[key] for key in sorted(boards_guardados))
        ],
    }


def _carrier_html(serial: str, data_url: str, revision: int = 0) -> str:
    """Carrier mínimo que Colab serializa dentro del .ipynb."""
    serial = _sanitize_serial(serial)
    return f'''<div id="amc_persisted_snapshot_container_{serial}" aria-hidden="true"
style="position:fixed;left:-9999px;top:-9999px;width:1px;height:1px;opacity:0;overflow:hidden;pointer-events:none;">
<img id="amc_persisted_snapshot_{serial}" data-amc-revision="{int(revision or 0)}"
src="{data_url or ''}" alt="persisted snapshot" style="display:block;width:1px;height:1px;border:0;" />
</div>'''


def _file_to_dataurl(path: str) -> str:
    """Respaldo sólo para la sesión actual: no sustituye al .ipynb."""
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "rb") as fh:
            encoded = base64.b64encode(fh.read()).decode("ascii")
        return "data:image/png;base64," + encoded
    except Exception:
        return ""


def _request_notebook_save(force: bool = False) -> bool:
    """Solicita guardado con rate limit; no simula clics del navegador."""
    global _LAST_NOTEBOOK_SAVE_AT

    now = time.monotonic()
    if not force and now - _LAST_NOTEBOOK_SAVE_AT < _SAVE_COOLDOWN_SECONDS:
        return False

    try:
        from google.colab import _message

        _message.blocking_request("notebook.save", {})
        _LAST_NOTEBOOK_SAVE_AT = now
        return True
    except Exception:
        return False


def _update_carrier_output(serial: str, data_url: str, revision: int) -> bool:
    """Actualiza el carrier sin volver a leer get_ipynb()."""
    html = _carrier_html(serial, data_url, revision)
    try:
        handle = _SNAPSHOT_HANDLES.get(serial)
        if handle is None:
            _SNAPSHOT_HANDLES[serial] = display(HTML(html), display_id=True)
        else:
            handle.update(HTML(html))
        return True
    except Exception as exc:
        print("[boards] No se pudo actualizar el carrier:", repr(exc))
        return False


def _render_board_html(
    serial: str,
    initial_data_url: str,
    initial_revision: int,
    callback_name: str,
) -> str:
    """HTML visual. El PNG se incrusta una sola vez en este output."""
    serial = _sanitize_serial(serial)
    root_id = f"amc_board_root_{serial}"
    canvas_id = f"amc_board_canvas_{serial}"
    embedded_id = f"amc_board_embedded_snapshot_{serial}"
    audio_url = "data:audio/mpeg;base64," + _b64_audio if _b64_audio else ""

    template = r'''
<div id="__ROOT_ID__" class="amc-board-root">
  <style>
    #__ROOT_ID__ { --amc-muted:#e2e8f0; margin:0; padding:0; background:#f8fafc; font-family:"Computer Modern","CMU Serif",Inter,system-ui,-apple-system,"Segoe UI",Roboto,Arial; }
    #__ROOT_ID__ * { box-sizing:border-box; }
    #__ROOT_ID__ .amc-toolbar { display:flex; gap:10px; flex-wrap:wrap; margin:12px; align-items:center; }
    #__ROOT_ID__ .amc-btn { padding:8px 12px; border-radius:12px; border:1px solid #e6e6e6; background:#fff; color:#0b3b3c; font-weight:700; cursor:pointer; box-shadow:0 10px 24px rgba(0,0,0,.12); transition:all .16s ease-out; }
    #__ROOT_ID__ .amc-btn:hover { transform:translateY(-1px) scale(1.02); background:#ecfeff; border-color:#0ea5a6; box-shadow:0 16px 40px rgba(0,0,0,.16); }
    #__ROOT_ID__ input[type="color"], #__ROOT_ID__ input[type="range"] { height:36px; padding:0 4px; border:1px solid #e6e6e6; border-radius:10px; accent-color:#0ea5a6; background:#fff; }
    #__ROOT_ID__ canvas { border:1px solid var(--amc-muted); border-radius:12px; width:calc(100% - 24px); height:460px; touch-action:none; cursor:crosshair; background:#fff; margin:0 12px 18px; box-shadow:0 12px 32px rgba(15,23,42,.12); display:block; }
    #__ROOT_ID__ .amc-serial { margin:8px 12px; font:12px/1.2 ui-sans-serif,system-ui; color:#64748b; }
    #__ROOT_ID__ .amc-state { display:inline-block; margin-left:8px; padding:3px 8px; border-radius:999px; font:11px/1.2 ui-sans-serif,system-ui; color:#475569; background:#e2e8f0; }
    #__ROOT_ID__ .amc-state[data-mode="saving"] { color:#92400e; background:#fef3c7; }
    #__ROOT_ID__ .amc-state[data-mode="saved"] { color:#166534; background:#dcfce7; }
    #__ROOT_ID__ .amc-state[data-mode="error"] { color:#991b1b; background:#fee2e2; }
    #__ROOT_ID__ .amc-badge { position:fixed; right:14px; bottom:50px; z-index:10; user-select:none; pointer-events:none; transform:scale(2.5) translateX(-15px); transform-origin:bottom right; }
    #__ROOT_ID__ .amc-badge img { display:block; height:40px; width:auto; }
  </style>

  <div class="amc-serial">Board: <strong>__SERIAL__</strong><span data-amc-role="state" class="amc-state" data-mode="idle">Cargando…</span></div>
  <div class="amc-toolbar">
    <button data-amc-action="pen" class="amc-btn">✏️ Lápiz</button>
    <button data-amc-action="eraser" class="amc-btn">🧹 Borrador</button>
    <label>Color <input data-amc-role="color" type="color" value="#0f172a"></label>
    <label>Grosor <input data-amc-role="size" type="range" min="1" max="50" value="8"></label>
    <button data-amc-action="undo" class="amc-btn">↩️ Undo</button>
    <button data-amc-action="redo" class="amc-btn">↪️ Redo</button>
    <button data-amc-action="clear" class="amc-btn">🗑️ Limpiar</button>
    <button data-amc-action="download" class="amc-btn">⬇️ Descargar PNG</button>
  </div>
  <div style="display:none"><img id="__EMBEDDED_ID__" data-amc-revision="__INITIAL_REVISION__" src="__INITIAL_DATA_URL__" alt="snapshot"></div>
  <canvas id="__CANVAS_ID__" tabindex="0" aria-label="Pizarra editable"></canvas>
  <div class="amc-badge"><img src="https://raw.githubusercontent.com/Arthemioxz/AutoMindCloudExperimental/main/AutoMindCloud/AutoMindCloud2.png" alt="AutoMind"></div>
</div>

<script>
(() => {
  const ROOT_ID = __ROOT_JSON__;
  const CANVAS_ID = __CANVAS_JSON__;
  const EMBEDDED_ID = __EMBEDDED_JSON__;
  const CALLBACK = __CALLBACK_JSON__;
  const INITIAL_REVISION = __INITIAL_REVISION__;
  const AUDIO_DATA_URL = __AUDIO_JSON__;

  // Ajustes de rendimiento.
  const SAVE_DELAY_MS = 900;
  const MAX_HISTORY = 120;
  const MAX_CANVAS_PIXELS = 1600000;

  const root = document.getElementById(ROOT_ID);
  if (!root || root.dataset.amcReady === '1') return;
  root.dataset.amcReady = '1';

  const canvas = document.getElementById(CANVAS_ID);
  const ctx = canvas && canvas.getContext ? canvas.getContext('2d') : null;
  const colorEl = root.querySelector('[data-amc-role="color"]');
  const sizeEl = root.querySelector('[data-amc-role="size"]');
  const stateEl = root.querySelector('[data-amc-role="state"]');
  const embedded = document.getElementById(EMBEDDED_ID);
  if (!canvas || !ctx || !colorEl || !sizeEl) return;

  let dpr = 1;
  let drawing = false;
  let isRendering = false;
  let activeStroke = null;
  let tool = 'pen';
  let revision = Number(INITIAL_REVISION) || 0;
  let baseSnapshot = '';
  let saveTimer = null;
  let commitStarted = false;
  let sending = false;
  let pendingSnapshot = null;
  let lastConfirmed = '';
  let clickAudio = null;

  // Comandos vectoriales: mucho más livianos que guardar 40 PNG en Undo/Redo.
  const history = [];
  const redoStack = [];

  if (AUDIO_DATA_URL) {
    try {
      clickAudio = new Audio(AUDIO_DATA_URL);
      clickAudio.preload = 'auto';
      clickAudio.volume = 1;
    } catch (_) {
      clickAudio = null;
    }
  }

  function setState(text, mode = 'idle') {
    if (!stateEl) return;
    stateEl.textContent = text;
    stateEl.dataset.mode = mode;
  }

  function isPng(value) {
    return typeof value === 'string' && value.startsWith('data:image/png;base64,');
  }

  function responseData(answer) {
    return answer && answer.data && typeof answer.data === 'object'
      ? answer.data
      : (answer || {});
  }

  function kernelAvailable() {
    return !!(window.google && google.colab && google.colab.kernel && google.colab.kernel.invokeFunction);
  }

  function computeDpr() {
    const width = Math.max(1, canvas.clientWidth || 1);
    const height = Math.max(1, canvas.clientHeight || 1);
    const nativeDpr = Math.min(window.devicePixelRatio || 1, 2);
    const nativePixels = width * height * nativeDpr * nativeDpr;
    return nativePixels <= MAX_CANVAS_PIXELS
      ? nativeDpr
      : Math.sqrt(MAX_CANVAS_PIXELS / (width * height));
  }

  function configureCanvas() {
    dpr = computeDpr();
    canvas.width = Math.max(1, Math.round(canvas.clientWidth * dpr));
    canvas.height = Math.max(1, Math.round(canvas.clientHeight * dpr));
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.imageSmoothingEnabled = true;
  }

  function clearCanvas() {
    ctx.save();
    ctx.globalCompositeOperation = 'source-over';
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.restore();
  }

  function currentDataURL() {
    try {
      return canvas.toDataURL('image/png');
    } catch (_) {
      return '';
    }
  }

  function point(event) {
    const rect = canvas.getBoundingClientRect();
    return {
      x: (event.clientX - rect.left) * dpr,
      y: (event.clientY - rect.top) * dpr,
    };
  }

  function drawSegment(a, b, command) {
    ctx.save();
    ctx.globalCompositeOperation = command.tool === 'eraser' ? 'destination-out' : 'source-over';
    ctx.strokeStyle = command.tool === 'eraser' ? 'rgba(0,0,0,1)' : command.color;
    ctx.lineWidth = command.width;
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();
    ctx.restore();
  }

  function drawStroke(command) {
    const points = command.points || [];
    if (!points.length) return;
    if (points.length === 1) {
      const p = points[0];
      drawSegment(p, { x: p.x + 0.01, y: p.y + 0.01 }, command);
      return;
    }
    for (let i = 1; i < points.length; i += 1) {
      drawSegment(points[i - 1], points[i], command);
    }
  }

  function drawImageDataURL(dataURL) {
    if (!isPng(dataURL)) return Promise.resolve(false);
    return new Promise((resolve) => {
      const image = new Image();
      image.onload = () => {
        ctx.save();
        ctx.globalCompositeOperation = 'source-over';
        ctx.drawImage(image, 0, 0, image.naturalWidth, image.naturalHeight, 0, 0, canvas.width, canvas.height);
        ctx.restore();
        resolve(true);
      };
      image.onerror = () => resolve(false);
      image.src = dataURL;
    });
  }

  async function renderFromHistory() {
    isRendering = true;
    clearCanvas();
    if (isPng(baseSnapshot)) {
      await drawImageDataURL(baseSnapshot);
    }
    for (const command of history) {
      if (command.type === 'clear') clearCanvas();
      else if (command.type === 'stroke') drawStroke(command);
    }
    isRendering = false;
  }

  function compactHistoryBeforeNewCommand() {
    if (history.length < MAX_HISTORY) return;
    // El PNG base conserva el resultado actual; se descartan sólo Undo antiguos.
    baseSnapshot = currentDataURL();
    history.length = 0;
    redoStack.length = 0;
  }

  function addCommand(command) {
    compactHistoryBeforeNewCommand();
    history.push(command);
    redoStack.length = 0;
  }

  function scheduleSave() {
    clearTimeout(saveTimer);
    setState('Cambios pendientes…', 'saving');
    saveTimer = setTimeout(() => {
      queueSnapshot('debounce', false, false);
    }, SAVE_DELAY_MS);
  }

  function queueSnapshot(reason = 'cambio', commitVisibleOutput = false, force = false) {
    clearTimeout(saveTimer);
    const dataURL = currentDataURL();
    if (!dataURL) {
      return Promise.resolve({ ok: false, error: 'No se pudo serializar canvas' });
    }

    // Un cambio normal idéntico no vuelve a viajar al runtime. Un commit forzado sí.
    if (!force && !commitVisibleOutput && dataURL === lastConfirmed && !pendingSnapshot) {
      return Promise.resolve({ ok: true, skipped: true, revision });
    }

    revision += 1;
    // "Latest wins": mientras una llamada está en curso, sólo queda el último PNG.
    pendingSnapshot = {
      dataURL,
      reason,
      commitVisibleOutput: !!commitVisibleOutput,
      clientRevision: revision,
    };

    setState(commitVisibleOutput ? 'Actualizando salida del notebook…' : 'Guardando…', 'saving');
    return drainSnapshotQueue();
  }

  async function drainSnapshotQueue() {
    if (sending) return { ok: true, queued: true };
    sending = true;
    let lastResult = { ok: true };

    try {
      while (pendingSnapshot) {
        const job = pendingSnapshot;
        pendingSnapshot = null;

        try {
          if (!kernelAvailable()) throw new Error('Runtime de Colab no disponible');

          const answer = await google.colab.kernel.invokeFunction(
            CALLBACK,
            [job.dataURL, job.clientRevision, job.commitVisibleOutput],
            {}
          );
          const result = responseData(answer);
          if (result && result.ok === false) {
            throw new Error(result.error || 'No se pudo guardar el snapshot');
          }

          lastConfirmed = job.dataURL;
          revision = Math.max(revision, Number(result && result.revision) || 0);
          lastResult = Object.assign({ ok: true }, result || {});
          setState(
            job.commitVisibleOutput ? '✓ Salida actualizada' : '✓ Snapshot guardado',
            'saved'
          );
        } catch (error) {
          console.error('AMC board:', error);
          lastResult = { ok: false, error: String(error) };
          setState('No confirmado: runtime sin respuesta', 'error');
        }
      }
    } finally {
      sending = false;
    }

    return lastResult;
  }

  function finalizeStroke(event) {
    if (!drawing || !activeStroke) return;

    try {
      if (event && Number.isFinite(event.clientX) && Number.isFinite(event.clientY)) {
        const p = point(event);
        const previous = activeStroke.points[activeStroke.points.length - 1];
        if (previous) {
          activeStroke.points.push(p);
          drawSegment(previous, p, activeStroke);
        }
      }
    } catch (_) {}

    drawing = false;
    try {
      if (event && canvas.hasPointerCapture(event.pointerId)) {
        canvas.releasePointerCapture(event.pointerId);
      }
    } catch (_) {}

    if (activeStroke.points.length) addCommand(activeStroke);
    activeStroke = null;
    scheduleSave();
  }

  function undo() {
    if (!history.length || isRendering) return;
    redoStack.push(history.pop());
    renderFromHistory().then(scheduleSave);
  }

  function redo() {
    if (!redoStack.length || isRendering) return;
    history.push(redoStack.pop());
    renderFromHistory().then(scheduleSave);
  }

  function resizeKeepPixels() {
    if (!canvas.width || !canvas.height || isRendering) return;
    // Al cambiar resolución se consolida la historia previa en un único baseline.
    baseSnapshot = currentDataURL();
    history.length = 0;
    redoStack.length = 0;
    configureCanvas();
    renderFromHistory().then(scheduleSave);
  }

  canvas.addEventListener('pointerdown', (event) => {
    if (isRendering) return;
    canvas.focus({ preventScroll: true });
    drawing = true;
    try { canvas.setPointerCapture(event.pointerId); } catch (_) {}

    const p = point(event);
    activeStroke = {
      type: 'stroke',
      tool,
      color: colorEl.value,
      width: Math.max(1, Number(sizeEl.value) * dpr),
      points: [p],
    };
    drawStroke(activeStroke);
  });

  canvas.addEventListener('pointermove', (event) => {
    if (!drawing || !activeStroke || isRendering) return;
    const p = point(event);
    const previous = activeStroke.points[activeStroke.points.length - 1];
    activeStroke.points.push(p);
    drawSegment(previous, p, activeStroke);
  });

  canvas.addEventListener('pointerup', finalizeStroke);
  canvas.addEventListener('pointercancel', finalizeStroke);

  root.querySelector('[data-amc-action="pen"]').onclick = () => { tool = 'pen'; };
  root.querySelector('[data-amc-action="eraser"]').onclick = () => { tool = 'eraser'; };
  root.querySelector('[data-amc-action="clear"]').onclick = () => {
    if (isRendering) return;
    addCommand({ type: 'clear' });
    clearCanvas();
    scheduleSave();
  };
  root.querySelector('[data-amc-action="undo"]').onclick = undo;
  root.querySelector('[data-amc-action="redo"]').onclick = redo;
  root.querySelector('[data-amc-action="download"]').onclick = () => {
    try {
      const a = document.createElement('a');
      const now = new Date();
      const pad = (n) => String(n).padStart(2, '0');
      a.href = currentDataURL();
      a.download = 'pizarra___SERIAL___' + now.getFullYear() + '-' + pad(now.getMonth() + 1) + '-' + pad(now.getDate()) + '_' + pad(now.getHours()) + '-' + pad(now.getMinutes()) + '-' + pad(now.getSeconds()) + '.png';
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (_) {
      setState('No se pudo descargar PNG', 'error');
    }
  };

  root.querySelectorAll('button').forEach((button) => {
    button.addEventListener('click', () => {
      try {
        if (!clickAudio) return;
        clickAudio.pause();
        clickAudio.currentTime = 0;
        const promise = clickAudio.play();
        if (promise && typeof promise.catch === 'function') promise.catch(() => {});
      } catch (_) {}
    });
  });

  canvas.addEventListener('keydown', (event) => {
    const z = event.key === 'z' || event.key === 'Z';
    if (!z || !(event.ctrlKey || event.metaKey)) return;
    event.preventDefault();
    if (event.shiftKey) redo(); else undo();
  });

  window.addEventListener('resize', resizeKeepPixels);

  // Al salir u ocultar la pestaña se reemplaza el OUTPUT VISIBLE con el PNG
  // más reciente. Eso evita tener que hacer clic otra vez al volver a Colab.
  function commitOutput(reason) {
    if (commitStarted) return;
    commitStarted = true;
    queueSnapshot(reason, true, true);
  }

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') commitOutput('pestana_oculta');
  });

  window.addEventListener('pagehide', () => commitOutput('salida_pagina'));

  // Algunos cambios de pestaña internos de Colab no propagan visibilitychange
  // al iframe. Este respaldo se desactiva solo después del primer commit.
  window.addEventListener('blur', () => {
    window.setTimeout(() => {
      if (!root.isConnected || commitStarted) return;
      if (document.visibilityState === 'hidden' || !document.hasFocus()) {
        commitOutput('perdida_foco');
      }
    }, 180);
  });

  setTimeout(async () => {
    configureCanvas();
    const source = embedded && isPng(embedded.getAttribute('src') || '')
      ? embedded.getAttribute('src')
      : '';
    baseSnapshot = source || '';
    await renderFromHistory();
    setState(source ? '✓ Board restaurado' : 'Listo para dibujar', source ? 'saved' : 'idle');
  }, 0);
})();
</script>
'''

    replacements = {
        "__ROOT_ID__": root_id,
        "__ROOT_JSON__": json.dumps(root_id),
        "__CANVAS_ID__": canvas_id,
        "__CANVAS_JSON__": json.dumps(canvas_id),
        "__EMBEDDED_ID__": embedded_id,
        "__EMBEDDED_JSON__": json.dumps(embedded_id),
        "__CALLBACK_JSON__": json.dumps(callback_name),
        "__INITIAL_REVISION__": str(int(initial_revision or 0)),
        "__INITIAL_DATA_URL__": initial_data_url or "",
        "__AUDIO_JSON__": json.dumps(audio_url),
        "__SERIAL__": serial,
    }

    for old, new in replacements.items():
        template = template.replace(old, new)
    return template


def _refresh_visible_output(
    serial: str,
    data_url: str,
    revision: int,
    callback_name: str,
) -> bool:
    """Actualiza el output visual sólo para commits críticos de salida."""
    handle = _BOARD_HANDLES.get(serial)
    if handle is None:
        return False

    try:
        html = _render_board_html(serial, data_url, revision, callback_name)
        handle.update(HTML(html))
        return True
    except Exception as exc:
        print("[boards] No se pudo actualizar output visible:", repr(exc))
        return False


def _write_runtime_png(serial: str, png_b64: str) -> None:
    """Pequeño respaldo local para reejecuciones dentro del mismo runtime."""
    try:
        path = os.path.join(_RUNTIME_PNG_DIR, f"pizarra_cell_{serial}.png")
        with open(path, "wb") as fh:
            fh.write(base64.b64decode(png_b64, validate=True))
    except Exception:
        pass


def _make_snapshot_callback(serial: str):
    serial = _sanitize_serial(serial)
    callback_name = f"amc5.persist.pushSnapshot.{serial}"

    def _callback(data_url_png: str, client_revision=None, commit_visible_output=False):
        record = _upsert_board_record(serial, data_url_png, client_revision)
        if record is None:
            return {"ok": False, "error": "Snapshot PNG Base64 inválido"}

        _write_runtime_png(serial, record["png_b64"])

        # No se lee el notebook para comprobarlo: eso era el principal cuello
        # de botella. El carrier se actualiza y Colab lo serializa normalmente.
        carrier_updated = _update_carrier_output(
            serial,
            data_url_png,
            record["revision"],
        )

        visible_updated = False
        if bool(commit_visible_output):
            visible_updated = _refresh_visible_output(
                serial,
                data_url_png,
                record["revision"],
                callback_name,
            )

        # Se guarda como máximo una vez cada _SAVE_COOLDOWN_SECONDS, excepto
        # cuando la pestaña se oculta o la página sale.
        save_requested = _request_notebook_save(
            force=bool(commit_visible_output)
        )

        return {
            "ok": bool(carrier_updated),
            "serial": serial,
            "revision": record["revision"],
            "carrier_updated": bool(carrier_updated),
            "visible_output_updated": bool(visible_updated),
            "notebook_save_requested": bool(save_requested),
        }

    return _callback


def _ensure_callback_registered(serial: str) -> str:
    serial = _sanitize_serial(serial)
    callback_name = f"amc5.persist.pushSnapshot.{serial}"
    if callback_name not in _REGISTERED_CALLBACKS:
        output.register_callback(callback_name, _make_snapshot_callback(serial))
        _REGISTERED_CALLBACKS.add(callback_name)
    return callback_name


# No se recargan todas las boards al importar el módulo. Así, en notebooks
# grandes no se procesa todo el .ipynb si sólo necesitas abrir una board. La
# recuperación puntual ocurre automáticamente al llamar board("serial").


def board(serial: str = "board") -> None:
    """Muestra una pizarra y recupera su Base64 automáticamente si existe.

    No necesitas ejecutar get_boards() antes. Si la board no está en memoria ni
    en el respaldo local del runtime, busca sólo ese serial dentro del .ipynb.
    La función no retorna el DisplayHandle para que Colab no imprima
    ``<DisplayHandle display_id=...>`` debajo de la pizarra.
    """
    serial = _sanitize_serial(serial)
    callback_name = _ensure_callback_registered(serial)
    png_path = os.path.join(_RUNTIME_PNG_DIR, f"pizarra_cell_{serial}.png")

    record = _find_board_record(serial)
    initial_data_url = ""

    if record and record.get("png_b64"):
        initial_data_url = "data:image/png;base64," + record["png_b64"]
    else:
        # Primero se intenta el archivo local: es inmediato si sigues en el
        # mismo runtime. Si no existe, se hace una única recuperación puntual
        # desde los outputs serializados del notebook.
        initial_data_url = _file_to_dataurl(png_path)
        if initial_data_url:
            record = _upsert_board_record(serial, initial_data_url, 1)
        else:
            record = _recover_single_board_from_notebook(serial)
            if record and record.get("png_b64"):
                initial_data_url = "data:image/png;base64," + record["png_b64"]
                _write_runtime_png(serial, record["png_b64"])

    initial_revision = int(record.get("revision", 0) or 0) if record else 0

    # Carrier mínimo recuperable. No hace una segunda lectura de get_ipynb().
    _update_carrier_output(serial, initial_data_url, initial_revision)

    html = _render_board_html(
        serial,
        initial_data_url,
        initial_revision,
        callback_name,
    )
    _BOARD_HANDLES[serial] = display(HTML(html), display_id=True)
    # No retornar el handle: evita la línea <DisplayHandle display_id=...>.


# USO
# 1) Ejecuta/importa este módulo una vez por runtime.
# 2) En otra celda usa directamente: board("numero_123")
#    La función encuentra automáticamente el Base64 de esa board si existe.
# 3) Dibuja normalmente. El snapshot se envía tras ~0.9 s sin cambios.
# 4) Al cambiar de pestaña, Colab actualiza el output visual y solicita guardar.
# 5) Tras reconectar runtime, vuelve a importar el módulo y usa board("numero_123").
# 6) get_boards() lista sólo boards ya cargadas en memoria. Para inventariar
#    todas las guardadas en outputs usa get_boards(recargar=True).
