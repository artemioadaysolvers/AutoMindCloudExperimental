from IPython.display import HTML, display
try:
    from google.colab import output as _colab_output
except Exception:  # permite importar el módulo fuera de Colab sin ocultar el error real al usarlo
    _colab_output = None
import base64
import json
import os
import re
import time

# =============================================================================
# AutoMindCloud.Board_Script — PIZARRA PERSISTENTE PARA GOOGLE COLAB
#
# Idea clave:
# - El PNG se guarda siempre en un carrier oculto serializable del .ipynb.
# - Al abandonar la pestaña, se actualiza ADEMAS el MISMO output visible de la
#   pizarra con el PNG recién creado. Por eso, si Colab reconstruye el output
#   al volver, ya contiene la imagen correcta y no requiere hacer clic en la
#   celda ni volver a ejecutar board(...).
# =============================================================================

_AUDIO_FILE = "click_sound.mp3"
_b64_audio = None
if os.path.exists(_AUDIO_FILE):
    try:
        with open(_AUDIO_FILE, "rb") as _fh:
            _b64_audio = base64.b64encode(_fh.read()).decode("ascii")
    except Exception:
        _b64_audio = None

# Estado del runtime actual.
boards_guardados = []
notebook_json = {}
_SNAPSHOT_HANDLES = {}  # serial -> DisplayHandle de carrier oculto
_BOARD_HANDLES = {}     # serial -> DisplayHandle DEL OUTPUT VISIBLE
_REGISTERED_CALLBACKS = set()


def _sanitize_serial(value: str) -> str:
    value = (value or "board").strip()
    value = re.sub(r"[^A-Za-z0-9_]+", "_", value)
    return value or "board"


def _mime_to_text(value) -> str:
    if isinstance(value, list):
        return "".join(str(item) for item in value)
    return str(value or "")


def _read_notebook_json() -> dict:
    """Lee el JSON vivo del notebook desde el frontend de Colab."""
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


def _extract_all_boards_from_notebook(nb: dict):
    """Extrae el último carrier PNG válido de cada board guardado."""
    if not isinstance(nb, dict):
        return []

    image_pattern = re.compile(
        r'<img\b'
        r'(?=[^>]*\bid=["\']amc_persisted_snapshot_(?:ext_|int_)?(?P<serial>[A-Za-z0-9_]+)["\'])'
        r'(?=[^>]*\bsrc=["\'](?P<src>data:image/png;base64,[^"\']+)["\'])'
        r'[^>]*>',
        re.IGNORECASE | re.DOTALL,
    )

    latest = {}
    for cell_index, cell in enumerate(nb.get("cells", [])):
        if not isinstance(cell, dict):
            continue
        for output_index, out in enumerate(cell.get("outputs", [])):
            if not isinstance(out, dict):
                continue
            data = out.get("data", {}) or {}
            candidates = [
                _mime_to_text(data[mime])
                for mime in ("text/html", "text/plain", "text")
                if mime in data
            ]
            for html in candidates:
                for match in image_pattern.finditer(html):
                    serial = _sanitize_serial(match.group("serial"))
                    data_url = match.group("src")
                    try:
                        png_b64 = data_url.split(",", 1)[1]
                        base64.b64decode(png_b64, validate=True)
                    except Exception:
                        continue
                    latest[serial] = {
                        "serial": serial,
                        "png_b64": png_b64,
                        "revision": 0,
                        "updated_at": 0.0,
                        "source_cell": cell_index,
                        "source_output": output_index,
                    }
    return list(latest.values())


def _find_board_record(serial: str):
    serial = _sanitize_serial(serial)
    for record in boards_guardados:
        if record.get("serial") == serial:
            return record
    return None


def _upsert_board_record(serial: str, data_url_png: str, client_revision=None):
    """Actualiza la copia autoritativa del runtime."""
    serial = _sanitize_serial(serial)
    prefix = "data:image/png;base64,"
    if not isinstance(data_url_png, str) or not data_url_png.startswith(prefix):
        return None

    png_b64 = data_url_png[len(prefix):]
    try:
        base64.b64decode(png_b64, validate=True)
    except Exception:
        return None

    record = _find_board_record(serial)
    previous_revision = int(record.get("revision", 0) or 0) if record else 0
    try:
        requested_revision = int(client_revision or 0)
    except Exception:
        requested_revision = 0

    fresh = {
        "serial": serial,
        "png_b64": png_b64,
        "revision": max(previous_revision + 1, requested_revision),
        "updated_at": time.time(),
        "source_cell": record.get("source_cell") if record else None,
        "source_output": record.get("source_output") if record else None,
    }
    if record is None:
        boards_guardados.append(fresh)
    else:
        record.clear()
        record.update(fresh)
    return fresh


def recargar_boards_desde_notebook(conservar_runtime: bool = True):
    """Recupera los PNG Base64 almacenados en outputs del .ipynb."""
    global notebook_json
    notebook_json = _read_notebook_json()
    recovered = _extract_all_boards_from_notebook(notebook_json)

    if conservar_runtime:
        merged = {item["serial"]: dict(item) for item in recovered}
        for item in boards_guardados:
            if item.get("updated_at", 0) > 0:
                merged[item["serial"]] = dict(item)
        boards_guardados[:] = list(merged.values())
    else:
        boards_guardados[:] = recovered
    return boards_guardados


def listar_boards(incluir_base64: bool = False, recargar: bool = False):
    if recargar:
        recargar_boards_desde_notebook()
    if incluir_base64:
        return [dict(item) for item in boards_guardados]
    return [
        {
            "serial": item.get("serial"),
            "bytes_png_aprox": len(item.get("png_b64", "")) * 3 // 4,
            "revision": item.get("revision", 0),
            "updated_at": item.get("updated_at", 0),
            "source_cell": item.get("source_cell"),
            "source_output": item.get("source_output"),
        }
        for item in boards_guardados
    ]


def diagnostico_boards():
    nb = _read_notebook_json()
    cells = nb.get("cells", []) if isinstance(nb, dict) else []
    return {
        "notebook_json_es_dict": isinstance(nb, dict),
        "numero_celdas": len(cells),
        "numero_outputs": sum(
            len(cell.get("outputs", []))
            for cell in cells if isinstance(cell, dict)
        ),
        "boards_en_notebook": [
            item["serial"] for item in _extract_all_boards_from_notebook(nb)
        ],
        "boards_en_runtime": [
            {
                "serial": item["serial"],
                "revision": item.get("revision", 0),
                "updated_at": item.get("updated_at", 0),
            }
            for item in boards_guardados
        ],
    }


def _carrier_html(serial: str, data_url: str, revision: int = 0) -> str:
    """Carrier mínimo que queda serializado como output del notebook."""
    serial = _sanitize_serial(serial)
    return f'''<div id="amc_persisted_snapshot_container_{serial}" aria-hidden="true"
style="position:fixed;left:-9999px;top:-9999px;width:1px;height:1px;opacity:0;overflow:hidden;pointer-events:none;">
<img id="amc_persisted_snapshot_{serial}" data-amc-revision="{int(revision or 0)}"
src="{data_url or ''}" alt="persisted snapshot" style="display:block;width:1px;height:1px;border:0;" />
</div>'''


def _file_to_dataurl(path: str) -> str:
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "rb") as fh:
            return "data:image/png;base64," + base64.b64encode(fh.read()).decode("ascii")
    except Exception:
        return ""


def _snapshot_from_notebook(serial: str) -> str:
    serial = _sanitize_serial(serial)
    for item in _extract_all_boards_from_notebook(_read_notebook_json()):
        if item.get("serial") == serial:
            return "data:image/png;base64," + item.get("png_b64", "")
    return ""


def _wait_for_carrier(serial: str, png_b64: str) -> bool:
    """Espera brevemente hasta que Colab incorpore el carrier a su modelo."""
    for pause in (0.00, 0.08, 0.18, 0.35, 0.70, 1.00):
        if pause:
            time.sleep(pause)
        try:
            for item in _extract_all_boards_from_notebook(_read_notebook_json()):
                if item.get("serial") == serial and item.get("png_b64") == png_b64:
                    return True
        except Exception:
            pass
    return False


def _request_notebook_save() -> bool:
    """Pide el guardado normal de Colab, sin simular clics del navegador."""
    try:
        from google.colab import _message
        _message.blocking_request("notebook.save", {})
        # La segunda petición ayuda cuando el modelo y la serialización pasan
        # por colas distintas dentro de Colab.
        time.sleep(0.18)
        _message.blocking_request("notebook.save", {})
        return True
    except Exception:
        return False


def _update_carrier_output(serial: str, data_url: str, revision: int):
    html = _carrier_html(serial, data_url, revision)
    handle = _SNAPSHOT_HANDLES.get(serial)
    if handle is None:
        _SNAPSHOT_HANDLES[serial] = display(HTML(html), display_id=True)
    else:
        handle.update(HTML(html))


def _render_board_html(serial: str, initial_data_url: str, initial_revision: int, callback_name: str) -> str:
    """Genera el único output visual de la pizarra, ya hidratado con PNG."""
    serial = _sanitize_serial(serial)
    root_id = f"amc_board_root_{serial}"
    canvas_id = f"amc_board_canvas_{serial}"
    embedded_id = f"amc_board_embedded_snapshot_{serial}"
    audio_json = json.dumps("data:audio/mpeg;base64," + _b64_audio) if _b64_audio else "null"

    script = f'''
<script>
(() => {{
  const ROOT_ID = {json.dumps(root_id)};
  const CANVAS_ID = {json.dumps(canvas_id)};
  const EMBEDDED_ID = {json.dumps(embedded_id)};
  const CALLBACK = {json.dumps(callback_name)};
  const INITIAL_DATA_URL = {json.dumps(initial_data_url or '')};
  const INITIAL_REVISION = {int(initial_revision or 0)};
  const AUDIO_DATA_URL = {audio_json};
  const MAX_HISTORY = 40;

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

  let dpr = window.devicePixelRatio || 1;
  let drawing = false;
  let last = {{x:0,y:0}};
  let tool = 'pen';
  let revision = Number(INITIAL_REVISION) || 0;
  let lastSent = '';
  let chain = Promise.resolve();
  let saveTimer = null;
  let clickAudio = null;
  const undoStack = [];
  const redoStack = [];

  if (AUDIO_DATA_URL) {{
    try {{ clickAudio = new Audio(AUDIO_DATA_URL); clickAudio.preload='auto'; clickAudio.volume=1; }} catch (_) {{ clickAudio = null; }}
  }}

  function setState(text, mode='idle') {{
    if (!stateEl) return;
    stateEl.textContent = text;
    stateEl.dataset.mode = mode;
  }}
  function isPng(v) {{ return typeof v === 'string' && v.startsWith('data:image/png;base64,'); }}
  function responseData(answer) {{ return answer && answer.data && typeof answer.data === 'object' ? answer.data : (answer || {{}}); }}
  function kernelAvailable() {{ return !!(window.google && google.colab && google.colab.kernel && google.colab.kernel.invokeFunction); }}

  function initCanvas(width, height) {{
    canvas.width = Math.max(1, Math.round(width));
    canvas.height = Math.max(1, Math.round(height));
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.globalCompositeOperation = 'source-over';
    ctx.fillStyle = '#fff';
    ctx.fillRect(0,0,canvas.width,canvas.height);
  }}

  function firstLayout() {{
    initCanvas(canvas.clientWidth*dpr, canvas.clientHeight*dpr);
  }}

  function currentDataURL() {{
    try {{ return canvas.toDataURL('image/png'); }} catch (_) {{ return ''; }}
  }}

  function paintSnapshot(dataURL, clear=true) {{
    if (!isPng(dataURL)) return Promise.resolve(false);
    return new Promise((resolve) => {{
      const image = new Image();
      image.onload = () => {{
        ctx.save();
        ctx.globalCompositeOperation = 'source-over';
        if (clear) {{ ctx.fillStyle='#fff'; ctx.fillRect(0,0,canvas.width,canvas.height); }}
        ctx.drawImage(image, 0,0,image.naturalWidth,image.naturalHeight, 0,0,canvas.width,canvas.height);
        ctx.restore();
        if (embedded) {{ embedded.src = dataURL; embedded.dataset.amcRevision = String(revision); }}
        resolve(true);
      }};
      image.onerror = () => resolve(false);
      image.src = dataURL;
    }});
  }}

  function resizeKeepPixels() {{
    if (!canvas.width || !canvas.height) return;
    const old = document.createElement('canvas');
    old.width=canvas.width; old.height=canvas.height;
    old.getContext('2d').drawImage(canvas,0,0);
    dpr = window.devicePixelRatio || 1;
    initCanvas(canvas.clientWidth*dpr, canvas.clientHeight*dpr);
    ctx.drawImage(old,0,0,old.width,old.height,0,0,canvas.width,canvas.height);
  }}

  function point(event) {{
    const rect = canvas.getBoundingClientRect();
    return {{x:(event.clientX-rect.left)*dpr, y:(event.clientY-rect.top)*dpr}};
  }}

  function stroke(a,b) {{
    ctx.save();
    ctx.globalCompositeOperation = tool === 'eraser' ? 'destination-out' : 'source-over';
    ctx.strokeStyle = tool === 'eraser' ? 'rgba(0,0,0,1)' : colorEl.value;
    ctx.lineWidth = Number(sizeEl.value)*dpr;
    ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y); ctx.stroke();
    ctx.restore();
  }}

  function pushHistory(dataURL=null) {{
    const snapshot = dataURL || currentDataURL();
    if (!snapshot) return;
    undoStack.push(snapshot);
    while (undoStack.length > MAX_HISTORY) undoStack.shift();
    redoStack.length=0;
  }}

  function sendSnapshot(reason='cambio', commitVisibleOutput=false, force=false) {{
    clearTimeout(saveTimer);
    const dataURL = currentDataURL();
    if (!dataURL) return Promise.resolve({{ok:false, error:'No se pudo serializar canvas'}});
    if (!force && !commitVisibleOutput && dataURL === lastSent) return chain;

    revision += 1;
    const clientRevision = revision;
    lastSent = dataURL;
    setState(commitVisibleOutput ? 'Actualizando salida del notebook…' : 'Guardando…', 'saving');

    chain = chain.catch(() => {{}}).then(async () => {{
      try {{
        if (!kernelAvailable()) throw new Error('Runtime de Colab no disponible');
        const answer = await google.colab.kernel.invokeFunction(
          CALLBACK, [dataURL, clientRevision, !!commitVisibleOutput], {{}}
        );
        const result = responseData(answer);
        if (result && result.ok === false) throw new Error(result.error || 'No se pudo guardar');
        revision = Math.max(revision, Number(result && result.revision) || 0);
        setState(commitVisibleOutput ? '✓ Salida actualizada automáticamente' : '✓ Guardado en notebook', 'saved');
        return Object.assign({{ok:true, reason, revision}}, result || {{}});
      }} catch (error) {{
        console.error('AMC board:', error);
        setState('No confirmado: runtime sin respuesta', 'error');
        return {{ok:false, error:String(error), reason, revision:clientRevision}};
      }}
    }});
    return chain;
  }}

  function flush(reason='final', commitVisibleOutput=false) {{
    return sendSnapshot(reason, commitVisibleOutput, true);
  }}

  function scheduleSave() {{
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => sendSnapshot('respaldo', false, false), 250);
  }}

  function finishStroke(event) {{
    if (!drawing) return;
    try {{
      if (event && Number.isFinite(event.clientX) && Number.isFinite(event.clientY)) {{
        const p = point(event); stroke(last,p); last=p;
      }}
    }} catch (_) {{}}
    drawing=false;
    try {{ if (event && canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId); }} catch (_) {{}}
    flush('trazo_final', false);
  }}

  function undo() {{
    if (!undoStack.length) return;
    const current = currentDataURL();
    const previous = undoStack.pop();
    if (current) redoStack.push(current);
    paintSnapshot(previous).then(() => flush('undo', false));
  }}
  function redo() {{
    if (!redoStack.length) return;
    const current = currentDataURL();
    const next = redoStack.pop();
    if (current) undoStack.push(current);
    paintSnapshot(next).then(() => flush('redo', false));
  }}

  canvas.addEventListener('pointerdown', (event) => {{
    drawing=true;
    pushHistory();
    try {{ canvas.setPointerCapture(event.pointerId); }} catch (_) {{}}
    last=point(event); stroke(last,last);
  }});
  canvas.addEventListener('pointermove', (event) => {{
    if (!drawing) return;
    const p=point(event); stroke(last,p); last=p;
  }});
  canvas.addEventListener('pointerup', finishStroke);
  canvas.addEventListener('pointercancel', finishStroke);

  root.querySelector('[data-amc-action="pen"]').onclick = () => {{ tool='pen'; }};
  root.querySelector('[data-amc-action="eraser"]').onclick = () => {{ tool='eraser'; }};
  root.querySelector('[data-amc-action="clear"]').onclick = () => {{
    pushHistory(); ctx.save(); ctx.globalCompositeOperation='source-over'; ctx.fillStyle='#fff'; ctx.fillRect(0,0,canvas.width,canvas.height); ctx.restore(); flush('limpiar', false);
  }};
  root.querySelector('[data-amc-action="undo"]').onclick = undo;
  root.querySelector('[data-amc-action="redo"]').onclick = redo;
  root.querySelector('[data-amc-action="download"]').onclick = () => {{
    try {{
      const a=document.createElement('a');
      const now=new Date(); const pad=(n)=>String(n).padStart(2,'0');
      a.href=currentDataURL();
      a.download='pizarra_{serial}_'+now.getFullYear()+'-'+pad(now.getMonth()+1)+'-'+pad(now.getDate())+'_'+pad(now.getHours())+'-'+pad(now.getMinutes())+'-'+pad(now.getSeconds())+'.png';
      document.body.appendChild(a); a.click(); a.remove();
    }} catch (_) {{ setState('No se pudo descargar PNG','error'); }}
  }};

  root.querySelectorAll('button').forEach((button) => {{
    button.addEventListener('click', () => {{
      try {{
        if (!clickAudio) return;
        clickAudio.pause(); clickAudio.currentTime=0;
        const p=clickAudio.play(); if (p && typeof p.catch==='function') p.catch(()=>{{}});
      }} catch (_) {{}}
    }});
  }});

  window.addEventListener('keydown', (event) => {{
    const z=event.key==='z'||event.key==='Z';
    if (!z || !(event.ctrlKey||event.metaKey)) return;
    event.preventDefault(); if (event.shiftKey) redo(); else undo();
  }});
  window.addEventListener('resize', resizeKeepPixels);

  // ÉSTE ES EL PUNTO CRÍTICO: al ocultarse la pestaña se actualiza el output
  // visual mediante DisplayHandle.update en Python. Al volver, Colab ya tiene
  // el HTML con el PNG actual, por lo que no hay que pulsar la celda.
  let outputCommitStarted = false;
  function commitOutput(reason) {{
    if (outputCommitStarted) return;
    outputCommitStarted=true;
    flush(reason, true);
  }}
  document.addEventListener('visibilitychange', () => {{
    if (document.visibilityState === 'hidden') commitOutput('pestana_oculta');
  }});
  window.addEventListener('pagehide', () => commitOutput('salida_pagina'));
  window.addEventListener('blur', () => {{
    // blur cubre algunos cambios de pestaña de Colab que no propagan
    // visibilitychange al iframe del output.
    setTimeout(() => commitOutput('perdida_foco'), 0);
  }});

  setTimeout(() => {{
    firstLayout();
    const source = isPng(INITIAL_DATA_URL) ? INITIAL_DATA_URL : (embedded && isPng(embedded.src) ? embedded.src : '');
    if (source) {{
      paintSnapshot(source).then(() => {{ pushHistory(source); setState('✓ Board restaurado', 'saved'); }});
    }} else {{
      pushHistory(); setState('Listo para dibujar', 'idle');
    }}
  }}, 0);
}})();
</script>
'''

    return f'''
<div id="{root_id}" class="amc-board-root">
  <style>
    #{root_id} {{ --amc-muted:#e2e8f0; margin:0; padding:0; background:#f8fafc; font-family:"Computer Modern","CMU Serif",Inter,system-ui,-apple-system,"Segoe UI",Roboto,Arial; }}
    #{root_id} * {{ box-sizing:border-box; }}
    #{root_id} .amc-toolbar {{ display:flex; gap:10px; flex-wrap:wrap; margin:12px; align-items:center; }}
    #{root_id} .amc-btn {{ padding:8px 12px; border-radius:12px; border:1px solid #e6e6e6; background:#fff; color:#0b3b3c; font-weight:700; cursor:pointer; box-shadow:0 10px 24px rgba(0,0,0,.12); transition:all .16s ease-out; }}
    #{root_id} .amc-btn:hover {{ transform:translateY(-1px) scale(1.02); background:#ecfeff; border-color:#0ea5a6; box-shadow:0 16px 40px rgba(0,0,0,.16); }}
    #{root_id} input[type="color"], #{root_id} input[type="range"] {{ height:36px; padding:0 4px; border:1px solid #e6e6e6; border-radius:10px; accent-color:#0ea5a6; background:#fff; }}
    #{root_id} canvas {{ border:1px solid var(--amc-muted); border-radius:12px; width:calc(100% - 24px); height:460px; touch-action:none; cursor:crosshair; background:#fff; margin:0 12px 18px; box-shadow:0 12px 32px rgba(15,23,42,.12); display:block; }}
    #{root_id} .amc-serial {{ margin:8px 12px; font:12px/1.2 ui-sans-serif,system-ui; color:#64748b; }}
    #{root_id} .amc-state {{ display:inline-block; margin-left:8px; padding:3px 8px; border-radius:999px; font:11px/1.2 ui-sans-serif,system-ui; color:#475569; background:#e2e8f0; }}
    #{root_id} .amc-state[data-mode="saving"] {{ color:#92400e; background:#fef3c7; }}
    #{root_id} .amc-state[data-mode="saved"] {{ color:#166534; background:#dcfce7; }}
    #{root_id} .amc-state[data-mode="error"] {{ color:#991b1b; background:#fee2e2; }}
    #{root_id} .amc-badge {{ position:fixed; right:14px; bottom:50px; z-index:10; user-select:none; pointer-events:none; transform:scale(2.5) translateX(-15px); transform-origin:bottom right; }}
    #{root_id} .amc-badge img {{ display:block; height:40px; width:auto; }}
  </style>

  <div class="amc-serial">Board: <strong>{serial}</strong><span data-amc-role="state" class="amc-state" data-mode="idle">Cargando…</span></div>
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
  <div style="display:none"><img id="{embedded_id}" data-amc-revision="{int(initial_revision or 0)}" src="{initial_data_url or ''}" alt="snapshot"></div>
  <canvas id="{canvas_id}"></canvas>
  <div class="amc-badge"><img src="https://raw.githubusercontent.com/Arthemioxz/AutoMindCloudExperimental/main/AutoMindCloud/AutoMindCloud2.png" alt="AutoMind"></div>
</div>
{script}
'''


def _refresh_visible_output(serial: str, data_url: str, revision: int, callback_name: str) -> bool:
    """Actualiza el output visual, no sólo un carrier auxiliar."""
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


def _make_snapshot_callback(serial: str):
    serial = _sanitize_serial(serial)
    callback_name = f"amc4.persist.pushSnapshot.{serial}"
    png_path = f"/content/pizarra_cell_{serial}.png"

    def _callback(data_url_png: str, client_revision=None, commit_visible_output=False):
        record = _upsert_board_record(serial, data_url_png, client_revision)
        if record is None:
            return {"ok": False, "error": "Snapshot PNG Base64 inválido"}

        try:
            with open(png_path, "wb") as fh:
                fh.write(base64.b64decode(record["png_b64"], validate=True))
        except Exception:
            pass

        # Siempre se actualiza el carrier recuperable para futuras sesiones.
        _update_carrier_output(serial, data_url_png, record["revision"])
        embedded_in_model = _wait_for_carrier(serial, record["png_b64"])

        # Sólo al abandonar/ocultar la pestaña se reescribe el OUTPUT VISIBLE.
        # Así nunca se interrumpe un trazo que el usuario esté haciendo.
        visible_updated = False
        if bool(commit_visible_output):
            visible_updated = _refresh_visible_output(
                serial, data_url_png, record["revision"], callback_name
            )

        saved = _request_notebook_save()
        return {
            "ok": True,
            "serial": serial,
            "revision": record["revision"],
            "persisted_to_notebook_model": bool(embedded_in_model),
            "visible_output_updated": bool(visible_updated),
            "notebook_save_requested": bool(saved),
        }

    return _callback


def _ensure_callback_registered(serial: str) -> str:
    serial = _sanitize_serial(serial)
    callback_name = f"amc4.persist.pushSnapshot.{serial}"
    if callback_name not in _REGISTERED_CALLBACKS:
        _require_colab()
        _colab_output.register_callback(callback_name, _make_snapshot_callback(serial))
        _REGISTERED_CALLBACKS.add(callback_name)
    return callback_name


# `get_boards()` carga explícitamente los snapshots desde el .ipynb.
# No se consulta el frontend al importar el módulo: así `from AutoMindCloud.Board_Script import *`
# queda libre de efectos secundarios y se puede ejecutar una vez al inicio del notebook.
_BOARDS_INITIALIZED = False


def _require_colab():
    if _colab_output is None:
        raise RuntimeError(
            "AutoMindCloud.Board_Script requiere Google Colab. "
            "Ejecuta este módulo desde un notebook de Colab."
        )


def get_boards(incluir_base64: bool = False, recargar: bool = True):
    """
    Carga la información de los boards ya embebidos en el .ipynb y la devuelve.

    Uso al iniciar el runtime:
        from AutoMindCloud.Board_Script import *
        get_boards()

    El retorno no incluye el Base64 salvo que `incluir_base64=True`.
    """
    global _BOARDS_INITIALIZED
    _require_colab()
    if recargar or not _BOARDS_INITIALIZED:
        # Se conservan cambios recibidos en este runtime y se fusionan con los
        # snapshots del notebook que fueron creados en runtimes anteriores.
        recargar_boards_desde_notebook(conservar_runtime=True)
        _BOARDS_INITIALIZED = True
    return listar_boards(incluir_base64=incluir_base64, recargar=False)


def board(serial: str = "board"):
    """Muestra una pizarra editable y la deja preparada para persistir sola."""
    _require_colab()
    # `get_boards()` es el uso recomendado al inicio. Este fallback evita
    # abrir una pizarra vacía si se olvidó llamarlo.
    if not _BOARDS_INITIALIZED:
        get_boards()
    serial = _sanitize_serial(serial)
    callback_name = _ensure_callback_registered(serial)
    png_path = f"/content/pizarra_cell_{serial}.png"

    record = _find_board_record(serial)
    initial_data_url = (
        "data:image/png;base64," + record["png_b64"] if record else ""
    )
    if not initial_data_url:
        initial_data_url = _snapshot_from_notebook(serial) or _file_to_dataurl(png_path)
    if initial_data_url and record is None:
        record = _upsert_board_record(serial, initial_data_url, 1)

    initial_revision = int(record.get("revision", 0) or 0) if record else 0

    # Carrier recuperable para la próxima sesión/runtime.
    _update_carrier_output(serial, initial_data_url, initial_revision)

    # Este DisplayHandle corresponde al output VISIBLE y será actualizado por
    # el callback al cambiar de pestaña.
    html = _render_board_html(serial, initial_data_url, initial_revision, callback_name)
    _BOARD_HANDLES[serial] = display(HTML(html), display_id=True)


# API pública del módulo.
__all__ = [
    "board",
    "get_boards",
    "listar_boards",
    "recargar_boards_desde_notebook",
    "diagnostico_boards",
    "boards_guardados",
    "notebook_json",
]

# Uso desde Colab:
# from AutoMindCloud.Board_Script import *
# get_boards()
# board("numero_123")


# =============================================================================
# FAST BOARD DISCOVERY OVERRIDE (v5)
# -----------------------------------------------------------------------------
# IMPORTANT:
# `get_boards()` must NEVER call `get_ipynb` by default. In notebooks with
# large visualization outputs, `get_ipynb` transfers the whole notebook and
# becomes extremely slow. This override asks the browser only for the carrier
# elements whose ids begin with `amc_persisted_snapshot_`.
#
# Metadata-only mode is the default: it returns serial/revision/estimated bytes
# without transferring any PNG Base64. A Base64 is read only when board(serial)
# actually opens that particular board.
# =============================================================================

_FAST_DISCOVERY_VERSION = "5"
_LAST_FAST_DISCOVERY_ERROR = None

_FRONTEND_BOARD_SCAN_JS = r"""
(async () => {
  const TARGET_SERIAL = __AMC_TARGET_SERIAL__;
  const INCLUDE_PAYLOAD = __AMC_INCLUDE_PAYLOAD__;
  const PREFIX = 'amc_persisted_snapshot_';
  const rows = new Map();
  const seenRoots = new WeakSet();

  function cleanSerial(id) {
    let serial = String(id || '').slice(PREFIX.length);
    serial = serial.replace(/^(?:ext_|int_)/, '');
    return serial.replace(/[^A-Za-z0-9_]+/g, '_') || 'board';
  }

  function addImage(img) {
    try {
      const id = img && img.id ? img.id : '';
      if (!id.startsWith(PREFIX)) return;
      const serial = cleanSerial(id);
      if (TARGET_SERIAL && serial !== TARGET_SERIAL) return;
      const src = img.getAttribute('src') || img.src || '';
      if (!src.startsWith('data:image/png;base64,')) return;
      const revision = Number.parseInt(img.getAttribute('data-amc-revision') || '0', 10) || 0;
      const bytes = Math.max(0, Math.floor((src.length - 'data:image/png;base64,'.length) * 3 / 4));
      const candidate = { serial, revision, bytes_png_aprox: bytes };
      if (INCLUDE_PAYLOAD) candidate.data_url = src;

      const previous = rows.get(serial);
      // A newer revision always wins. If the revisions are equal, the element
      // found later in the notebook DOM wins, matching notebook output order.
      if (!previous || revision >= previous.revision) rows.set(serial, candidate);
    } catch (_) {}
  }

  function walk(root) {
    if (!root || seenRoots.has(root)) return;
    seenRoots.add(root);

    try {
      const images = root.querySelectorAll
        ? root.querySelectorAll('img[id^="amc_persisted_snapshot_"]')
        : [];
      for (const image of images) addImage(image);
    } catch (_) {}

    try {
      const all = root.querySelectorAll ? root.querySelectorAll('*') : [];
      for (const node of all) {
        try {
          if (node.shadowRoot) walk(node.shadowRoot);
        } catch (_) {}
      }
    } catch (_) {}

    try {
      const frames = root.querySelectorAll ? root.querySelectorAll('iframe') : [];
      for (const frame of frames) {
        try {
          if (frame.contentDocument) walk(frame.contentDocument);
        } catch (_) {}
      }
    } catch (_) {}
  }

  // Depending on the Colab version eval_js may run in the main document or
  // inside an output iframe. Scan every same-origin ancestor document.
  try { walk(document); } catch (_) {}
  try { if (window.parent && window.parent !== window) walk(window.parent.document); } catch (_) {}
  try { if (window.top && window.top !== window) walk(window.top.document); } catch (_) {}

  return JSON.stringify(Array.from(rows.values()));
})()
"""

def _fast_scan_js(target_serial="", include_payload=False):
    """Reads only Board carrier elements already rendered by Colab's frontend."""
    global _LAST_FAST_DISCOVERY_ERROR
    _require_colab()
    try:
        evaluator = getattr(_colab_output, "eval_js", None)
        if evaluator is None:
            raise RuntimeError("google.colab.output.eval_js no está disponible")

        safe_target = _sanitize_serial(target_serial) if target_serial else ""
        js = _FRONTEND_BOARD_SCAN_JS.replace(
            "__AMC_TARGET_SERIAL__", json.dumps(safe_target)
        ).replace(
            "__AMC_INCLUDE_PAYLOAD__", "true" if include_payload else "false"
        )
        raw = evaluator(js)
        if isinstance(raw, str):
            raw = json.loads(raw)
        if not isinstance(raw, list):
            raw = []

        normalized = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            serial = _sanitize_serial(item.get("serial"))
            revision = int(item.get("revision", 0) or 0)
            bytes_png_aprox = int(item.get("bytes_png_aprox", 0) or 0)
            record = {
                "serial": serial,
                "revision": revision,
                "bytes_png_aprox": max(0, bytes_png_aprox),
                "updated_at": 0.0,
                "source_cell": "frontend",
                "source_output": "carrier",
            }
            data_url = item.get("data_url", "")
            if include_payload and data_url:
                prefix = "data:image/png;base64,"
                if not isinstance(data_url, str) or not data_url.startswith(prefix):
                    continue
                png_b64 = data_url[len(prefix):]
                # Validate only the selected boards/payloads, never all notebook outputs.
                try:
                    base64.b64decode(png_b64, validate=True)
                except Exception:
                    continue
                record["png_b64"] = png_b64
                record["bytes_png_aprox"] = len(png_b64) * 3 // 4
            normalized.append(record)

        _LAST_FAST_DISCOVERY_ERROR = None
        return normalized
    except Exception as exc:
        _LAST_FAST_DISCOVERY_ERROR = repr(exc)
        return []


def _merge_board_records(recovered, conservar_runtime=True):
    """Merge metadata loaded from the frontend without discarding live edits."""
    by_serial = {}
    for item in recovered or []:
        if isinstance(item, dict) and item.get("serial"):
            by_serial[_sanitize_serial(item["serial"])] = dict(item)

    if conservar_runtime:
        for live in boards_guardados:
            if not isinstance(live, dict) or not live.get("serial"):
                continue
            serial = _sanitize_serial(live["serial"])
            prior = by_serial.get(serial)
            live_revision = int(live.get("revision", 0) or 0)
            prior_revision = int(prior.get("revision", 0) or 0) if prior else -1

            # A live image always wins over metadata with the same/older revision.
            if live.get("png_b64") and (live.get("updated_at", 0) > 0 or live_revision >= prior_revision):
                by_serial[serial] = dict(live)
            elif prior is None:
                by_serial[serial] = dict(live)

    boards_guardados[:] = list(by_serial.values())
    return boards_guardados


def _legacy_scan_entire_notebook(conservar_runtime=True):
    """
    Compatibility-only reader for outputs written by an old notebook when the
    browser cannot render their carrier nodes. It intentionally scans get_ipynb
    and is therefore NOT used by get_boards() unless explicitly requested.
    """
    global notebook_json
    nb = _read_notebook_json()
    recovered = _extract_all_boards_from_notebook(nb)
    # Do not retain a giant copy of a notebook that may contain 3D outputs.
    notebook_json = {}
    return _merge_board_records(recovered, conservar_runtime=conservar_runtime)


def recargar_boards_desde_notebook(conservar_runtime: bool = True, modo: str = "rapido"):
    """
    Loads Board information only.

    modo="rapido" (default): scans carrier elements in the already-open browser
    DOM; it does not transfer the notebook JSON.
    modo="compatibilidad": legacy full get_ipynb scan. Use it only once for an
    old notebook whose carriers are not currently mounted in the browser DOM.
    """
    mode = str(modo or "rapido").strip().lower()
    if mode in {"compatibilidad", "legacy", "ipynb", "completo"}:
        return _legacy_scan_entire_notebook(conservar_runtime=conservar_runtime)

    recovered = _fast_scan_js(include_payload=False)
    return _merge_board_records(recovered, conservar_runtime=conservar_runtime)


def _load_one_board_payload(serial: str):
    """Transfers exactly one PNG Base64: the board being opened."""
    serial = _sanitize_serial(serial)
    rows = _fast_scan_js(target_serial=serial, include_payload=True)
    if not rows:
        return None
    # The scanner deduplicates per serial; nevertheless pick max revision.
    item = max(rows, key=lambda x: int(x.get("revision", 0) or 0))
    return _upsert_board_record(
        serial,
        "data:image/png;base64," + item.get("png_b64", ""),
        item.get("revision", 0),
    )


def _snapshot_from_notebook(serial: str) -> str:
    """
    Fast replacement for the old get_ipynb lookup.
    It checks the in-memory cache and then reads only the requested carrier from
    the browser DOM. It never copies the complete .ipynb.
    """
    serial = _sanitize_serial(serial)
    record = _find_board_record(serial)
    if record and record.get("png_b64"):
        return "data:image/png;base64," + record["png_b64"]

    record = _load_one_board_payload(serial)
    if record and record.get("png_b64"):
        return "data:image/png;base64," + record["png_b64"]
    return ""


def _wait_for_carrier(serial: str, _unused_png_b64=None) -> bool:
    """
    Waits only for Board carrier metadata in the frontend DOM. The previous
    implementation requested the full notebook six times here.
    """
    serial = _sanitize_serial(serial)
    current = _find_board_record(serial)
    expected_revision = int(current.get("revision", 0) or 0) if current else 0
    for pause in (0.08, 0.16, 0.30):
        time.sleep(pause)
        rows = _fast_scan_js(target_serial=serial, include_payload=False)
        if rows and int(rows[0].get("revision", 0) or 0) >= expected_revision:
            return True
    return False


def listar_boards(incluir_base64: bool = False, recargar: bool = False):
    """
    Lists boards without reading their PNGs unless incluir_base64=True.
    """
    if recargar:
        recargar_boards_desde_notebook(conservar_runtime=True, modo="rapido")

    if incluir_base64:
        # This is intentionally opt-in: load every payload only if requested.
        loaded = _fast_scan_js(include_payload=True)
        _merge_board_records(loaded, conservar_runtime=True)

    rows = []
    for item in boards_guardados:
        b64 = item.get("png_b64", "")
        estimated = int(item.get("bytes_png_aprox", 0) or 0)
        if b64:
            estimated = len(b64) * 3 // 4
        row = {
            "serial": item.get("serial"),
            "bytes_png_aprox": estimated,
            "revision": item.get("revision", 0),
            "updated_at": item.get("updated_at", 0),
            "source_cell": item.get("source_cell", "frontend"),
            "source_output": item.get("source_output", "carrier"),
        }
        if incluir_base64:
            row["png_b64"] = b64
        rows.append(row)
    return rows


def get_boards(incluir_base64: bool = False, recargar: bool = True, modo: str = "rapido"):
    """
    Fast startup API.

    Default `get_boards()` reads only Board carrier metadata from the browser;
    it does not call get_ipynb and does not transfer any PNG Base64. A PNG is
    fetched only when `board("serial")` opens that board.

    Use `get_boards(modo="compatibilidad")` only to migrate an old notebook
    whose hidden carrier outputs cannot be found in the currently mounted DOM.
    """
    global _BOARDS_INITIALIZED
    _require_colab()

    if recargar or not _BOARDS_INITIALIZED:
        recargar_boards_desde_notebook(
            conservar_runtime=True,
            modo=modo,
        )
        _BOARDS_INITIALIZED = True

    return listar_boards(incluir_base64=incluir_base64, recargar=False)


def diagnostico_boards():
    """Fast diagnostics; never serializes the whole notebook."""
    frontend = _fast_scan_js(include_payload=False)
    return {
        "modo_carga_predeterminado": "rapido: DOM de carriers, sin get_ipynb",
        "version_descubrimiento": _FAST_DISCOVERY_VERSION,
        "error_ultimo_escaneo_rapido": _LAST_FAST_DISCOVERY_ERROR,
        "boards_detectados_en_frontend": frontend,
        "boards_en_runtime": listar_boards(incluir_base64=False, recargar=False),
        "notebook_json_en_memoria": bool(notebook_json),
    }


def board(serial: str = "board"):
    """
    Opens a board. The full Base64 is loaded only for this one requested board.
    """
    _require_colab()
    if not _BOARDS_INITIALIZED:
        get_boards()

    serial = _sanitize_serial(serial)
    callback_name = _ensure_callback_registered(serial)
    png_path = f"/content/pizarra_cell_{serial}.png"

    record = _find_board_record(serial)
    initial_data_url = (
        "data:image/png;base64," + record["png_b64"]
        if record and record.get("png_b64") else ""
    )
    if not initial_data_url:
        # Fast single-board lookup. No full notebook scan.
        initial_data_url = _snapshot_from_notebook(serial) or _file_to_dataurl(png_path)

    if initial_data_url and (record is None or not record.get("png_b64")):
        record = _upsert_board_record(serial, initial_data_url, (record or {}).get("revision", 0))

    initial_revision = int((record or {}).get("revision", 0) or 0)

    # Do NOT create a new carrier merely by opening a saved board. The existing
    # carrier already in the notebook is enough. A carrier is updated only when
    # the user actually changes the canvas through the persistence callback.
    html = _render_board_html(serial, initial_data_url, initial_revision, callback_name)
    _BOARD_HANDLES[serial] = display(HTML(html), display_id=True)


# Export the optimized public API.
__all__ = [
    "board",
    "get_boards",
    "listar_boards",
    "recargar_boards_desde_notebook",
    "diagnostico_boards",
    "boards_guardados",
    "notebook_json",
]


# Keep persisted revisions stable when a board is merely read from the frontend.
# The older implementation incremented the revision even during a read, which
# could make a just-opened board look newer than its saved carrier.
def _upsert_board_record(serial: str, data_url_png: str, client_revision=None):
    serial = _sanitize_serial(serial)
    prefix = "data:image/png;base64,"
    if not isinstance(data_url_png, str) or not data_url_png.startswith(prefix):
        return None

    png_b64 = data_url_png[len(prefix):]
    try:
        base64.b64decode(png_b64, validate=True)
    except Exception:
        return None

    record = _find_board_record(serial)
    previous_revision = int(record.get("revision", 0) or 0) if record else 0
    try:
        requested_revision = int(client_revision or 0)
    except Exception:
        requested_revision = 0

    # Ignore an already superseded client snapshot. Persist calls are queued in
    # JavaScript, but this also protects against delayed callbacks in Colab.
    if record and requested_revision and requested_revision < previous_revision:
        return record

    if requested_revision > 0:
        revision = requested_revision
    else:
        revision = previous_revision + 1 if record else 1

    fresh = {
        "serial": serial,
        "png_b64": png_b64,
        "bytes_png_aprox": len(png_b64) * 3 // 4,
        "revision": revision,
        "updated_at": time.time(),
        "source_cell": record.get("source_cell") if record else "frontend",
        "source_output": record.get("source_output") if record else "carrier",
    }
    if record is None:
        boards_guardados.append(fresh)
    else:
        record.clear()
        record.update(fresh)
    return fresh
