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


# =============================================================================
# SMART BOARD INDEX (v7)
# -----------------------------------------------------------------------------
# Goal:
#   * get_boards() never downloads the entire .ipynb in normal use.
#   * It reads a tiny persisted index (local browser cache / compact manifest).
#   * A PNG Base64 is fetched only when board("serial") actually opens it.
#   * get_ipynb remains available only as an explicit recovery path:
#       get_boards(modo="seguro")
#     or when a board is explicitly opened from a new browser with no cache.
#
# Why:
#   A notebook can contain tens of megabytes of 3D, plots and data outputs.
#   Using get_ipynb merely to discover board names is a brute-force operation.
# =============================================================================

_SMART_INDEX_VERSION = "7"
_SMART_INDEX_ATTR = "data-amc-board-index"
_SMART_INDEX_ID = "amc_board_manifest_v7"
_SMART_MANIFEST_HANDLE = None
_LAST_DISCOVERY_SOURCE = "none"
_LAST_SMART_ERROR = None
_FULL_NOTEBOOK_READ_THIS_RUNTIME = False


def _board_metadata(record):
    """Return only the light metadata required to list a board."""
    if not isinstance(record, dict) or not record.get("serial"):
        return None
    payload = record.get("png_b64", "")
    estimated = int(record.get("bytes_png_aprox", 0) or 0)
    if payload:
        estimated = len(payload) * 3 // 4
    return {
        "serial": _sanitize_serial(record["serial"]),
        "revision": int(record.get("revision", 0) or 0),
        "bytes_png_aprox": max(0, estimated),
        "updated_at": float(record.get("updated_at", 0.0) or 0.0),
    }


def _manifest_rows():
    rows = []
    seen = set()
    for record in boards_guardados:
        row = _board_metadata(record)
        if row and row["serial"] not in seen:
            rows.append(row)
            seen.add(row["serial"])
    return sorted(rows, key=lambda item: item["serial"].lower())


def _manifest_html():
    """
    A compact carrier which contains only names/revisions/byte estimates.
    It never duplicates any PNG Base64.
    """
    payload = {
        "version": _SMART_INDEX_VERSION,
        "updated_at": time.time(),
        "boards": _manifest_rows(),
    }
    packed = base64.b64encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).decode("ascii")
    return (
        f'<div id="{_SMART_INDEX_ID}" {_SMART_INDEX_ATTR}="1" '
        f'data-amc-index-b64="{packed}" aria-hidden="true" '
        'style="position:fixed;left:-9999px;top:-9999px;width:1px;height:1px;'
        'opacity:0;overflow:hidden;pointer-events:none"></div>'
    )


def _update_manifest_output():
    """
    Update a tiny notebook output after each confirmed snapshot.
    Unlike a full notebook scan, this output is a few hundred bytes.
    """
    global _SMART_MANIFEST_HANDLE
    html = _manifest_html()
    try:
        if _SMART_MANIFEST_HANDLE is None:
            _SMART_MANIFEST_HANDLE = display(HTML(html), display_id=True)
        else:
            _SMART_MANIFEST_HANDLE.update(HTML(html))
        return True
    except Exception:
        return False


def _safe_json_from_js(value, default):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            return default
    return value if isinstance(value, type(default)) else default


_FRONTEND_INDEX_READ_JS = r"""
(async () => {
  const INDEX_ATTR = 'data-amc-board-index';
  const INDEX_ID = 'amc_board_manifest_v7';
  const PREFIX = 'amc_persisted_snapshot_';

  function windows() {
    const out = [];
    const add = (w) => { if (w && !out.includes(w)) out.push(w); };
    add(window);
    try { add(window.parent); } catch (_) {}
    try { add(window.top); } catch (_) {}
    return out;
  }

  function notebookIdentity() {
    for (const w of windows()) {
      try {
        const href = String(w.location && w.location.href || '');
        if (href && href !== 'about:blank') {
          return href.split('#')[0].split('?')[0];
        }
      } catch (_) {}
    }
    return 'unknown-notebook';
  }

  function storageList() {
    const out = [];
    for (const w of windows()) {
      try {
        const storage = w.localStorage;
        if (storage && !out.includes(storage)) out.push(storage);
      } catch (_) {}
    }
    return out;
  }

  const cacheKey = 'amc_board_index_v7:' + notebookIdentity();

  function normalize(rows) {
    const latest = new Map();
    for (const raw of (Array.isArray(rows) ? rows : [])) {
      if (!raw || !raw.serial) continue;
      const serial = String(raw.serial).replace(/[^A-Za-z0-9_]+/g, '_') || 'board';
      const row = {
        serial,
        revision: Number.parseInt(raw.revision || 0, 10) || 0,
        bytes_png_aprox: Math.max(0, Number.parseInt(raw.bytes_png_aprox || 0, 10) || 0),
        updated_at: Number(raw.updated_at || 0) || 0,
      };
      const previous = latest.get(serial);
      if (!previous || row.revision >= previous.revision) latest.set(serial, row);
    }
    return Array.from(latest.values()).sort((a,b) => a.serial.localeCompare(b.serial));
  }

  function decodeManifest(encoded) {
    try {
      const json = atob(String(encoded || ''));
      const parsed = JSON.parse(json);
      return normalize(parsed && parsed.boards);
    } catch (_) {
      return [];
    }
  }

  // 1) O(1): browser cache written immediately after a board is saved.
  for (const storage of storageList()) {
    try {
      const raw = storage.getItem(cacheKey);
      if (!raw) continue;
      const parsed = JSON.parse(raw);
      const boards = normalize(parsed && parsed.boards);
      if (boards.length) {
        return JSON.stringify({source:'browser-index', cache_key:cacheKey, boards});
      }
    } catch (_) {}
  }

  // 2) Small, targeted DOM query. It does NOT walk every DOM node and never
  // reads a Base64 image. It only checks the compact index/carrier selectors.
  const roots = [];
  const addRoot = (doc) => {
    if (doc && !roots.includes(doc)) roots.push(doc);
  };
  for (const w of windows()) {
    try { addRoot(w.document); } catch (_) {}
  }

  // Usually notebook output iframes are direct descendants. Limit scanning to
  // a small number, so a notebook with complex widgets cannot turn this into a
  // full DOM traversal.
  for (let i = 0; i < roots.length && roots.length < 48; i++) {
    const root = roots[i];
    try {
      const frames = root.querySelectorAll ? root.querySelectorAll('iframe') : [];
      for (const frame of frames) {
        if (roots.length >= 48) break;
        try { addRoot(frame.contentDocument); } catch (_) {}
      }
    } catch (_) {}
  }

  for (const root of roots) {
    try {
      const node = root.getElementById && root.getElementById(INDEX_ID);
      const candidates = node
        ? [node]
        : (root.querySelectorAll ? root.querySelectorAll('[' + INDEX_ATTR + '][data-amc-index-b64]') : []);
      for (const item of candidates) {
        const boards = decodeManifest(item.getAttribute('data-amc-index-b64'));
        if (boards.length) {
          return JSON.stringify({source:'manifest-dom', cache_key:cacheKey, boards});
        }
      }
    } catch (_) {}
  }

  // 3) Metadata-only carrier query for notebooks written by v4/v5/v6.
  // No image src is returned; bytes are calculated from its already-rendered
  // length. This is still bounded and selector-based.
  const carrierRows = [];
  for (const root of roots) {
    try {
      const images = root.querySelectorAll
        ? root.querySelectorAll('img[id^="' + PREFIX + '"]')
        : [];
      for (const image of images) {
        const id = String(image.id || '');
        let serial = id.slice(PREFIX.length).replace(/^(?:ext_|int_)/, '');
        serial = serial.replace(/[^A-Za-z0-9_]+/g, '_') || 'board';
        const src = image.getAttribute('src') || '';
        if (!src.startsWith('data:image/png;base64,')) continue;
        carrierRows.push({
          serial,
          revision: Number.parseInt(image.getAttribute('data-amc-revision') || '0', 10) || 0,
          bytes_png_aprox: Math.max(0, Math.floor((src.length - 22) * 3 / 4)),
          updated_at: 0,
        });
      }
    } catch (_) {}
  }

  const boards = normalize(carrierRows);
  return JSON.stringify({
    source: boards.length ? 'carrier-dom' : 'no-smart-index',
    cache_key: cacheKey,
    boards
  });
})()
"""


def _run_smart_js(script):
    """Execute a very small browser query through Colab's supported eval_js."""
    global _LAST_SMART_ERROR
    _require_colab()
    try:
        evaluator = getattr(_colab_output, "eval_js", None)
        if evaluator is None:
            raise RuntimeError("google.colab.output.eval_js no está disponible")
        value = evaluator(script)
        _LAST_SMART_ERROR = None
        return value
    except Exception as exc:
        _LAST_SMART_ERROR = repr(exc)
        return None


def _browser_read_catalog():
    raw = _run_smart_js(_FRONTEND_INDEX_READ_JS)
    result = _safe_json_from_js(raw, {})
    if not isinstance(result, dict):
        return {"source": "browser-error", "boards": []}
    boards = result.get("boards", [])
    if not isinstance(boards, list):
        boards = []
    normalized = []
    for item in boards:
        if not isinstance(item, dict) or not item.get("serial"):
            continue
        normalized.append({
            "serial": _sanitize_serial(item["serial"]),
            "revision": int(item.get("revision", 0) or 0),
            "bytes_png_aprox": max(0, int(item.get("bytes_png_aprox", 0) or 0)),
            "updated_at": float(item.get("updated_at", 0.0) or 0.0),
            "source_cell": "smart-index",
            "source_output": result.get("source", "browser-index"),
        })
    return {
        "source": str(result.get("source", "browser-index")),
        "cache_key": str(result.get("cache_key", "")),
        "boards": normalized,
    }


_FRONTEND_INDEX_WRITE_JS = r"""
(async () => {
  const rows = __AMC_ROWS_JSON__;

  function windows() {
    const out = [];
    const add = (w) => { if (w && !out.includes(w)) out.push(w); };
    add(window);
    try { add(window.parent); } catch (_) {}
    try { add(window.top); } catch (_) {}
    return out;
  }

  function notebookIdentity() {
    for (const w of windows()) {
      try {
        const href = String(w.location && w.location.href || '');
        if (href && href !== 'about:blank') return href.split('#')[0].split('?')[0];
      } catch (_) {}
    }
    return 'unknown-notebook';
  }

  const cacheKey = 'amc_board_index_v7:' + notebookIdentity();
  const payload = JSON.stringify({version:'7', updated_at:Date.now()/1000, boards:rows});
  let written = false;
  for (const w of windows()) {
    try {
      w.localStorage.setItem(cacheKey, payload);
      written = true;
    } catch (_) {}
  }
  return JSON.stringify({ok:written, cache_key:cacheKey});
})()
"""


def _browser_write_catalog():
    """Mirror lightweight metadata in localStorage; never writes PNG Base64."""
    rows = _manifest_rows()
    js = _FRONTEND_INDEX_WRITE_JS.replace(
        "__AMC_ROWS_JSON__", json.dumps(rows, separators=(",", ":"))
    )
    return _run_smart_js(js)


def _merge_board_records(recovered, conservar_runtime=True):
    """
    Merge metadata and full records without replacing a known image with
    metadata-only information from the smart index.
    """
    current = {}
    if conservar_runtime:
        for old in boards_guardados:
            if isinstance(old, dict) and old.get("serial"):
                current[_sanitize_serial(old["serial"])] = dict(old)

    for incoming in recovered or []:
        if not isinstance(incoming, dict) or not incoming.get("serial"):
            continue
        serial = _sanitize_serial(incoming["serial"])
        candidate = dict(incoming)
        candidate["serial"] = serial
        old = current.get(serial)

        old_revision = int(old.get("revision", 0) or 0) if old else -1
        new_revision = int(candidate.get("revision", 0) or 0)

        if old and old.get("png_b64") and old_revision >= new_revision:
            # Existing image is newer/equal; update only its metadata if useful.
            old["bytes_png_aprox"] = max(
                int(old.get("bytes_png_aprox", 0) or 0),
                int(candidate.get("bytes_png_aprox", 0) or 0),
            )
            current[serial] = old
        elif old and old.get("png_b64") and not candidate.get("png_b64"):
            # A newer metadata row does not contain pixels; preserve old pixels
            # only when they belong to that exact same revision.
            if old_revision == new_revision:
                merged = dict(candidate)
                merged["png_b64"] = old["png_b64"]
                current[serial] = merged
            else:
                current[serial] = candidate
        else:
            current[serial] = candidate

    boards_guardados[:] = [
        current[key] for key in sorted(current, key=lambda value: value.lower())
    ]
    return boards_guardados


def _extract_one_board_from_notebook(nb, serial):
    """
    Targeted extractor used only if a board is explicitly opened from a browser
    that has no smart index/cache. It decodes one PNG, not every board.
    """
    serial = _sanitize_serial(serial)
    if not isinstance(nb, dict):
        return None

    escaped = re.escape(serial)
    pattern = re.compile(
        r'<img\b'
        r'(?=[^>]*\bid=["\']amc_persisted_snapshot_(?:ext_|int_)?' + escaped + r'["\'])'
        r'(?=[^>]*\bsrc=["\'](?P<src>data:image/png;base64,[^"\']+)["\'])'
        r'[^>]*>',
        re.IGNORECASE | re.DOTALL,
    )

    selected = None
    for cell_index, cell in enumerate(nb.get("cells", [])):
        if not isinstance(cell, dict):
            continue
        for output_index, output in enumerate(cell.get("outputs", [])):
            if not isinstance(output, dict):
                continue
            data = output.get("data", {}) or {}
            for mime in ("text/html", "text/plain", "text"):
                if mime not in data:
                    continue
                html = _mime_to_text(data[mime])
                for match in pattern.finditer(html):
                    data_url = match.group("src")
                    try:
                        png_b64 = data_url.split(",", 1)[1]
                        base64.b64decode(png_b64, validate=True)
                    except Exception:
                        continue
                    selected = {
                        "serial": serial,
                        "png_b64": png_b64,
                        "bytes_png_aprox": len(png_b64) * 3 // 4,
                        "revision": 0,
                        "updated_at": 0.0,
                        "source_cell": cell_index,
                        "source_output": output_index,
                    }
    return selected


def _legacy_scan_entire_notebook(conservar_runtime=True):
    """
    Explicit recovery/migration path. Never called by default get_boards().
    It reads the complete notebook only when the caller deliberately asks for
    modo="seguro"/"compatibilidad".
    """
    global notebook_json, _FULL_NOTEBOOK_READ_THIS_RUNTIME, _LAST_DISCOVERY_SOURCE
    notebook_json = _read_notebook_json()
    recovered = _extract_all_boards_from_notebook(notebook_json)
    notebook_json = {}
    _FULL_NOTEBOOK_READ_THIS_RUNTIME = True
    _LAST_DISCOVERY_SOURCE = "ipynb-explicit"
    _merge_board_records(recovered, conservar_runtime=conservar_runtime)
    _update_manifest_output()
    _browser_write_catalog()
    return boards_guardados


def _legacy_load_one_board_payload(serial):
    """
    Last-resort recovery, triggered only by board(serial) when the requested
    board is absent from cache and the current DOM. It extracts that one PNG.
    """
    global notebook_json, _LAST_DISCOVERY_SOURCE
    serial = _sanitize_serial(serial)
    notebook_json = _read_notebook_json()
    record = _extract_one_board_from_notebook(notebook_json, serial)
    notebook_json = {}
    _LAST_DISCOVERY_SOURCE = "ipynb-single-board-explicit"
    if record:
        _merge_board_records([record], conservar_runtime=True)
        _update_manifest_output()
        _browser_write_catalog()
    return _find_board_record(serial)


_FRONTEND_PAYLOAD_READ_JS = r"""
(async () => {
  const SERIAL = __AMC_SERIAL_JSON__;
  const PREFIX = 'data:image/png;base64,';

  function windows() {
    const out = [];
    const add = (w) => { if (w && !out.includes(w)) out.push(w); };
    add(window);
    try { add(window.parent); } catch (_) {}
    try { add(window.top); } catch (_) {}
    return out;
  }

  function notebookIdentity() {
    for (const w of windows()) {
      try {
        const href = String(w.location && w.location.href || '');
        if (href && href !== 'about:blank') return href.split('#')[0].split('?')[0];
      } catch (_) {}
    }
    return 'unknown-notebook';
  }

  const payloadKey = 'amc_board_payload_v7:' + notebookIdentity() + ':' + SERIAL;

  // 1) A local payload is available only for boards small enough to remain
  // inside browser storage. This is fast and avoids reading the notebook.
  for (const w of windows()) {
    try {
      const raw = w.localStorage.getItem(payloadKey);
      if (!raw) continue;
      const parsed = JSON.parse(raw);
      const dataUrl = parsed && parsed.data_url;
      if (typeof dataUrl === 'string' && dataUrl.startsWith(PREFIX)) {
        return JSON.stringify({source:'browser-payload', data_url:dataUrl,
          revision:Number(parsed.revision || 0) || 0});
      }
    } catch (_) {}
  }

  // 2) Bounded direct selector for a mounted old/new carrier.
  const wanted = 'amc_persisted_snapshot_' + SERIAL;
  const roots = [];
  const addRoot = (doc) => { if (doc && !roots.includes(doc)) roots.push(doc); };
  for (const w of windows()) { try { addRoot(w.document); } catch (_) {} }
  for (let i=0; i<roots.length && roots.length<48; i++) {
    try {
      const frames = roots[i].querySelectorAll ? roots[i].querySelectorAll('iframe') : [];
      for (const frame of frames) {
        if (roots.length >= 48) break;
        try { addRoot(frame.contentDocument); } catch (_) {}
      }
    } catch (_) {}
  }

  for (const root of roots) {
    try {
      let node = root.getElementById && root.getElementById(wanted);
      if (!node && root.querySelector) {
        node = root.querySelector('img[id="amc_persisted_snapshot_ext_' + SERIAL + '"],'
          + 'img[id="amc_persisted_snapshot_int_' + SERIAL + '"]');
      }
      const src = node && (node.getAttribute('src') || node.src || '');
      if (typeof src === 'string' && src.startsWith(PREFIX)) {
        return JSON.stringify({source:'carrier-dom', data_url:src,
          revision:Number.parseInt(node.getAttribute('data-amc-revision') || '0',10) || 0});
      }
    } catch (_) {}
  }

  return JSON.stringify({source:'payload-not-cached', data_url:''});
})()
"""


def _browser_load_one_payload(serial):
    """Retrieve exactly one PNG from the browser cache or one mounted carrier."""
    serial = _sanitize_serial(serial)
    js = _FRONTEND_PAYLOAD_READ_JS.replace("__AMC_SERIAL_JSON__", json.dumps(serial))
    raw = _run_smart_js(js)
    result = _safe_json_from_js(raw, {})
    data_url = result.get("data_url", "") if isinstance(result, dict) else ""
    if not isinstance(data_url, str) or not data_url.startswith("data:image/png;base64,"):
        return None
    record = _upsert_board_record(
        serial, data_url, int(result.get("revision", 0) or 0)
    )
    if record:
        record["source_cell"] = "smart-index"
        record["source_output"] = result.get("source", "browser-payload")
    return record


def _smart_snapshot_from_sources(serial):
    """Fast single-board hydration: memory -> browser payload -> mounted carrier."""
    serial = _sanitize_serial(serial)
    record = _find_board_record(serial)
    if record and record.get("png_b64"):
        return "data:image/png;base64," + record["png_b64"]

    record = _browser_load_one_payload(serial)
    if record and record.get("png_b64"):
        return "data:image/png;base64," + record["png_b64"]
    return ""


def _cache_injection_script(serial, callback_name):
    """
    The board canvas writes its compact index immediately in the browser after
    a successful Python callback. The Base64 cache is bounded: it is helpful
    after a runtime reconnect but never allowed to consume all localStorage.
    """
    return f"""
<script>
(() => {{
  const SERIAL = {json.dumps(_sanitize_serial(serial))};
  const CALLBACK = {json.dumps(callback_name)};
  const PREFIX = 'data:image/png;base64,';
  const MAX_PAYLOAD_CHARS = 1200000;
  const MAX_TOTAL_PAYLOAD_CHARS = 3400000;

  function windows() {{
    const out = [];
    const add = (w) => {{ if (w && !out.includes(w)) out.push(w); }};
    add(window);
    try {{ add(window.parent); }} catch (_) {{}}
    try {{ add(window.top); }} catch (_) {{}}
    return out;
  }}

  function notebookIdentity() {{
    for (const w of windows()) {{
      try {{
        const href = String(w.location && w.location.href || '');
        if (href && href !== 'about:blank') return href.split('#')[0].split('?')[0];
      }} catch (_) {{}}
    }}
    return 'unknown-notebook';
  }}

  const identity = notebookIdentity();
  const indexKey = 'amc_board_index_v7:' + identity;
  const payloadPrefix = 'amc_board_payload_v7:' + identity + ':';

  function storages() {{
    const out = [];
    for (const w of windows()) {{
      try {{
        const s = w.localStorage;
        if (s && !out.includes(s)) out.push(s);
      }} catch (_) {{}}
    }}
    return out;
  }}

  function readIndex(storage) {{
    try {{
      const parsed = JSON.parse(storage.getItem(indexKey) || '');
      if (parsed && Array.isArray(parsed.boards)) return parsed;
    }} catch (_) {{}}
    return {{version:'7', boards:[]}};
  }}

  function writeIndex(serial, revision, bytes) {{
    for (const storage of storages()) {{
      try {{
        const index = readIndex(storage);
        const bySerial = new Map();
        for (const item of index.boards || []) {{
          if (item && item.serial) bySerial.set(String(item.serial), item);
        }}
        const old = bySerial.get(serial) || {{}};
        bySerial.set(serial, {{
          serial,
          revision: Math.max(Number(old.revision || 0) || 0, Number(revision || 0) || 0),
          bytes_png_aprox: Math.max(0, Number(bytes || 0) || 0),
          updated_at: Date.now() / 1000
        }});
        index.version = '7';
        index.updated_at = Date.now() / 1000;
        index.boards = Array.from(bySerial.values())
          .sort((a,b) => String(a.serial).localeCompare(String(b.serial)));
        storage.setItem(indexKey, JSON.stringify(index));
      }} catch (_) {{}}
    }}
  }}

  function evictPayloads(storage) {{
    try {{
      const rows = [];
      let total = 0;
      for (let i=0; i<storage.length; i++) {{
        const key = storage.key(i);
        if (!key || !key.startsWith(payloadPrefix)) continue;
        try {{
          const value = storage.getItem(key) || '';
          const item = JSON.parse(value);
          const size = String(item.data_url || '').length;
          total += size;
          rows.push({{key, size, updated_at:Number(item.updated_at || 0) || 0}});
        }} catch (_) {{}}
      }}
      rows.sort((a,b) => a.updated_at - b.updated_at);
      while (total > MAX_TOTAL_PAYLOAD_CHARS && rows.length > 1) {{
        const victim = rows.shift();
        storage.removeItem(victim.key);
        total -= victim.size;
      }}
    }} catch (_) {{}}
  }}

  function writePayload(dataUrl, revision, mustRefresh) {{
    if (!mustRefresh || typeof dataUrl !== 'string' ||
        !dataUrl.startsWith(PREFIX) || dataUrl.length > MAX_PAYLOAD_CHARS) return;
    const key = payloadPrefix + SERIAL;
    for (const storage of storages()) {{
      try {{
        storage.setItem(key, JSON.stringify({{
          version:'7', revision:Number(revision || 0) || 0,
          updated_at:Date.now()/1000, data_url:dataUrl
        }}));
        evictPayloads(storage);
      }} catch (_) {{}}
    }}
  }}

  function responseData(answer) {{
    return answer && answer.data && typeof answer.data === 'object'
      ? answer.data : (answer || {{}});
  }}

  try {{
    if (!window.google || !google.colab || !google.colab.kernel) return;
    const kernel = google.colab.kernel;
    const previous = kernel.invokeFunction;
    if (typeof previous !== 'function') return;

    const priorCallbacks = previous.__amcBoardV7Callbacks || {{}};
    if (priorCallbacks[CALLBACK]) return;

    const wrapper = async function(...args) {{
      const answer = await previous.apply(this, args);
      try {{
        const called = args[0];
        const callArgs = args[1] || [];
        if (called === CALLBACK) {{
          const dataUrl = callArgs[0] || '';
          const requestedRevision = Number(callArgs[1] || 0) || 0;
          const commitVisible = !!callArgs[2];
          const result = responseData(answer);
          const revision = Math.max(
            requestedRevision, Number(result && result.revision || 0) || 0
          );
          const bytes = dataUrl.startsWith(PREFIX)
            ? Math.max(0, Math.floor((dataUrl.length - PREFIX.length) * 3 / 4))
            : 0;
          writeIndex(SERIAL, revision, bytes);
          // The payload is cached only for the important notebook-output
          // commit (tab switch/page hide), not after every tiny pen segment.
          writePayload(dataUrl, revision, commitVisible);
        }}
      }} catch (_) {{}}
      return answer;
    }};
    wrapper.__amcBoardV7Callbacks = Object.assign({{}}, priorCallbacks, {{[CALLBACK]:true}});
    kernel.invokeFunction = wrapper;
  }} catch (_) {{}}
}})();
</script>
"""


# Retain the tested canvas/UI implementation and add the cache interceptor
# after its own script. It is installed before the user can draw.
_RENDER_BOARD_HTML_CORE = _render_board_html


def _render_board_html(serial, initial_data_url, initial_revision, callback_name):
    return _RENDER_BOARD_HTML_CORE(
        serial, initial_data_url, initial_revision, callback_name
    ) + _cache_injection_script(serial, callback_name)


def _wait_for_carrier(serial, _unused_png_b64=None):
    """
    Keep a small synchronization window before notebook.save. The old version
    performed repeated get_ipynb/full-DOM operations here; the output update is
    already issued synchronously through DisplayHandle, so waiting is enough.
    """
    time.sleep(0.12)
    return True


def _make_snapshot_callback(serial):
    serial = _sanitize_serial(serial)
    callback_name = f"amc7.persist.pushSnapshot.{serial}"
    png_path = f"/content/pizarra_cell_{serial}.png"

    def _callback(data_url_png, client_revision=None, commit_visible_output=False):
        record = _upsert_board_record(serial, data_url_png, client_revision)
        if record is None:
            return {"ok": False, "error": "Snapshot PNG Base64 inválido"}

        canonical_data_url = "data:image/png;base64," + record["png_b64"]
        try:
            with open(png_path, "wb") as fh:
                fh.write(base64.b64decode(record["png_b64"], validate=True))
        except Exception:
            pass

        # Persist the actual image and a separate compact catalog. No get_ipynb
        # is required for this write path.
        _update_carrier_output(serial, canonical_data_url, record["revision"])
        _update_manifest_output()
        embedded_in_model = _wait_for_carrier(serial, record["png_b64"])

        visible_updated = False
        if bool(commit_visible_output):
            visible_updated = _refresh_visible_output(
                serial, canonical_data_url, record["revision"], callback_name
            )

        saved = _request_notebook_save()
        return {
            "ok": True,
            "serial": serial,
            "revision": record["revision"],
            "bytes_png_aprox": len(record["png_b64"]) * 3 // 4,
            "persisted_to_notebook_model": bool(embedded_in_model),
            "visible_output_updated": bool(visible_updated),
            "notebook_save_requested": bool(saved),
        }

    return _callback


def _ensure_callback_registered(serial):
    serial = _sanitize_serial(serial)
    callback_name = f"amc7.persist.pushSnapshot.{serial}"
    if callback_name not in _REGISTERED_CALLBACKS:
        _require_colab()
        _colab_output.register_callback(callback_name, _make_snapshot_callback(serial))
        _REGISTERED_CALLBACKS.add(callback_name)
    return callback_name


def recargar_boards_desde_notebook(conservar_runtime=True, modo="inteligente"):
    """
    Smart board discovery.

    modo="inteligente" (default)
        Read browser index, compact manifest or mounted carrier metadata only.
        It never asks Colab for the full .ipynb.

    modo="seguro" / "compatibilidad"
        Explicit migration/recovery path. It reads the whole notebook once,
        extracts only board carriers and immediately discards the large JSON.
        Use it only in a different browser/account with no local index.

    modo="rapido"
        Alias for "inteligente".
    """
    global _LAST_DISCOVERY_SOURCE
    mode = str(modo or "inteligente").strip().lower()

    if mode in {"seguro", "compatibilidad", "legacy", "ipynb", "completo"}:
        return _legacy_scan_entire_notebook(conservar_runtime=conservar_runtime)

    catalog = _browser_read_catalog()
    rows = catalog.get("boards", [])
    _LAST_DISCOVERY_SOURCE = catalog.get("source", "smart-index")
    _merge_board_records(rows, conservar_runtime=conservar_runtime)
    return boards_guardados


def listar_boards(incluir_base64=False, recargar=False, modo="inteligente"):
    """
    Return metadata by default. incluir_base64=True does not launch a notebook
    scan; it attaches only payloads already available in memory/browser cache.
    """
    if recargar:
        recargar_boards_desde_notebook(conservar_runtime=True, modo=modo)

    if incluir_base64:
        for row in list(boards_guardados):
            if row.get("png_b64"):
                continue
            _browser_load_one_payload(row.get("serial", ""))

    result = []
    for item in boards_guardados:
        row = _board_metadata(item)
        if not row:
            continue
        row["source_cell"] = item.get("source_cell", "smart-index")
        row["source_output"] = item.get("source_output", _LAST_DISCOVERY_SOURCE)
        if incluir_base64:
            row["png_b64"] = item.get("png_b64", "")
        result.append(row)
    return result


def get_boards(incluir_base64=False, recargar=True, modo="inteligente"):
    """
    Instant board catalog for normal use.

    This function is intentionally metadata-only and never reads the  notebook
    JSON by default. After a normal disconnect/reconnect in the same browser,
    the local compact index returns the list immediately.

    For a new browser/account whose local cache and compact DOM manifest are
    unavailable, run once:
        get_boards(modo="seguro")
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


def _snapshot_from_notebook(serial):
    """
    Open one board intelligently. Full notebook parsing is a last resort for
    that one explicitly requested board, never for get_boards().
    """
    serial = _sanitize_serial(serial)
    data_url = _smart_snapshot_from_sources(serial)
    if data_url:
        return data_url

    # New browser/account with no cached payload: only now is full retrieval
    # justified, because the user explicitly requested this particular board.
    record = _legacy_load_one_board_payload(serial)
    if record and record.get("png_b64"):
        return "data:image/png;base64," + record["png_b64"]
    return ""


def board(serial="board"):
    """Open one editable board; only this board's Base64 is hydrated."""
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
        initial_data_url = _snapshot_from_notebook(serial) or _file_to_dataurl(png_path)

    if initial_data_url and (record is None or not record.get("png_b64")):
        record = _upsert_board_record(
            serial, initial_data_url, (record or {}).get("revision", 0)
        )

    initial_revision = int((record or {}).get("revision", 0) or 0)
    html = _render_board_html(serial, initial_data_url, initial_revision, callback_name)
    _BOARD_HANDLES[serial] = display(HTML(html), display_id=True)


def diagnostico_boards():
    """Diagnostics without get_ipynb or recursive full-DOM scanning."""
    catalog = _browser_read_catalog()
    return {
        "version_descubrimiento": _SMART_INDEX_VERSION,
        "modo_predeterminado": "inteligente: índice pequeño, sin get_ipynb",
        "origen_ultima_carga": _LAST_DISCOVERY_SOURCE,
        "origen_catalogo_actual": catalog.get("source", "desconocido"),
        "error_ultimo_indice_inteligente": _LAST_SMART_ERROR,
        "lectura_completa_del_notebook_en_este_runtime": bool(
            _FULL_NOTEBOOK_READ_THIS_RUNTIME
        ),
        "boards_catalogo_inteligente": catalog.get("boards", []),
        "boards_en_runtime": listar_boards(incluir_base64=False, recargar=False),
        "notebook_json_en_memoria": bool(notebook_json),
    }


__all__ = [
    "board",
    "get_boards",
    "listar_boards",
    "recargar_boards_desde_notebook",
    "diagnostico_boards",
    "boards_guardados",
    "notebook_json",
]
