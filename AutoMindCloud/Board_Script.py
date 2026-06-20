"""
AutoMindCloud.Board_Script
==========================
Pizarra persistente para Google Colab.

Versión 21: corrección de guardado repetido sobre boards existentes.

Uso único:
    from AutoMindCloud.Board_Script import *
    board("alpha")

Garantías de diseño
-------------------
* Una sola implementación: no contiene overrides ni versiones apiladas.
* board("alpha") siempre intenta restaurar alpha automáticamente.
* Prioridad de restauración: IndexedDB local -> carrier montado -> respaldo .ipynb.
* El PNG antiguo no es reemplazado por una pizarra vacía al ejecutar board().
* Cada cambio se guarda primero en IndexedDB y después en el notebook.
* El callback de guardado rehidrata el estado Python desde el .ipynb cuando
  el runtime se reconectó. Esto evita el falso conflicto revisión-alta vs 0.
* El output visible nunca se reescribe durante un trazo; sólo se actualiza un
  carrier oculto separado. Así no se destruyen listeners ni canvas a mitad de uso.

Limitación física: si el navegador y el equipo mueren antes de que termine un
trazo, ningún navegador puede persistir datos que aún no llegaron a pointerup.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
import threading
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple

from IPython.display import HTML, display

try:
    from google.colab import output as _colab_output
    from google.colab import _message as _colab_message
except Exception:
    _colab_output = None
    _colab_message = None


# -----------------------------------------------------------------------------
# Estado único del módulo
# -----------------------------------------------------------------------------
_VERSION = "21.0"
_PREFIX = "amc_persisted_snapshot_"
_DB_NAME = "AutoMindBoardCacheV20"
_DB_STORE = "boards"
_MAX_PNG_BYTES = 48 * 1024 * 1024

# Compatibilidad con scripts anteriores.
boards_guardados: List[Dict[str, Any]] = []
notebook_json: Dict[str, Any] = {}

_RECORDS: Dict[str, Dict[str, Any]] = {}
_CARRIER_HANDLES: Dict[str, Any] = {}
_REGISTERED: set[str] = set()
_LOCK = threading.RLock()


# -----------------------------------------------------------------------------
# Utilidades
# -----------------------------------------------------------------------------
def _require_colab() -> None:
    if _colab_output is None or _colab_message is None:
        raise RuntimeError("AutoMindCloud.Board_Script requiere Google Colab con runtime activo.")


def _sanitize_serial(value: Any) -> str:
    value = re.sub(r"[^A-Za-z0-9_]+", "_", str(value or "board").strip())
    return value or "board"


def _mime_text(value: Any) -> str:
    return "".join(map(str, value)) if isinstance(value, list) else str(value or "")


def _decode_png_data_url(value: Any) -> Optional[Tuple[str, bytes, str]]:
    prefix = "data:image/png;base64,"
    if not isinstance(value, str) or not value.startswith(prefix):
        return None
    encoded = value[len(prefix):]
    try:
        payload = base64.b64decode(encoded, validate=True)
    except Exception:
        return None
    if not payload or len(payload) > _MAX_PNG_BYTES:
        return None
    return encoded, payload, hashlib.sha256(payload).hexdigest()


def _record_data_url(record: Optional[Dict[str, Any]]) -> str:
    if not record or not record.get("png_b64"):
        return ""
    return "data:image/png;base64," + record["png_b64"]


def _sync_public_records() -> None:
    boards_guardados[:] = [dict(_RECORDS[key]) for key in sorted(_RECORDS)]


def _set_record(
    serial: str,
    data_url: str,
    revision: int,
    source: str,
    *,
    force_equal: bool = False,
) -> Optional[Dict[str, Any]]:
    """Guarda un record en runtime sin dejar que una revisión vieja lo pise."""
    checked = _decode_png_data_url(data_url)
    if checked is None:
        return None
    encoded, payload, digest = checked
    serial = _sanitize_serial(serial)
    revision = max(0, int(revision or 0))
    old = _RECORDS.get(serial)
    if old:
        old_revision = int(old.get("revision", 0) or 0)
        if old_revision > revision:
            return old
        if old_revision == revision and old.get("sha256") != digest and not force_equal:
            return old
    record = {
        "serial": serial,
        "png_b64": encoded,
        "revision": revision,
        "sha256": digest,
        "bytes_png": len(payload),
        "updated_at": time.time(),
        "source": source,
        "seen": dict((old or {}).get("seen", {})),
    }
    _RECORDS[serial] = record
    _sync_public_records()
    return record


def _write_runtime_copy(serial: str, payload: bytes) -> None:
    path = f"/content/pizarra_cell_{_sanitize_serial(serial)}.png"
    temporary = path + ".tmp"
    try:
        with open(temporary, "wb") as fh:
            fh.write(payload)
        os.replace(temporary, path)
    except Exception:
        try:
            os.remove(temporary)
        except Exception:
            pass


def _read_runtime_copy(serial: str) -> str:
    path = f"/content/pizarra_cell_{_sanitize_serial(serial)}.png"
    try:
        with open(path, "rb") as fh:
            payload = fh.read()
        if not payload or len(payload) > _MAX_PNG_BYTES:
            return ""
        return "data:image/png;base64," + base64.b64encode(payload).decode("ascii")
    except Exception:
        return ""


# -----------------------------------------------------------------------------
# Respaldo portable dentro del .ipynb
# -----------------------------------------------------------------------------
def _carrier_display_id(serial: str) -> str:
    return f"amc.board.v21.carrier.{_sanitize_serial(serial)}"


def _carrier_html(record: Dict[str, Any]) -> str:
    serial = _sanitize_serial(record["serial"])
    src = html.escape(_record_data_url(record), quote=True)
    digest = html.escape(str(record.get("sha256", "")), quote=True)
    revision = max(0, int(record.get("revision", 0) or 0))
    return f'''<div aria-hidden="true" data-amc-board-carrier="{_VERSION}"
style="position:fixed;left:-10000px;top:-10000px;width:1px;height:1px;overflow:hidden;opacity:0;pointer-events:none;">
<img id="{_PREFIX}{serial}" data-amc-revision="{revision}" data-amc-sha256="{digest}"
src="{src}" alt="AutoMind persisted board" style="width:1px;height:1px;display:block;border:0" />
</div>'''


def _carrier_placeholder_html(serial: str) -> str:
    serial = _sanitize_serial(serial)
    return f'''<div aria-hidden="true" data-amc-board-carrier="{_VERSION}"
style="position:fixed;left:-10000px;top:-10000px;width:1px;height:1px;overflow:hidden;opacity:0;pointer-events:none;">
<img id="{_PREFIX}{serial}" data-amc-revision="0" data-amc-sha256="" src="" alt="AutoMind board placeholder" style="width:1px;height:1px;display:block;border:0" />
</div>'''


def _ensure_carrier_handle(serial: str) -> bool:
    """Crea el output carrier ANTES de editar.

    Es decisivo para Colab: un callback posterior sólo actualiza este output
    ya asociado a la celda de board(), en lugar de intentar crear una salida
    nueva desde un callback asíncrono. El placeholder no contiene PNG y nunca
    oculta un board guardado previamente.
    """
    serial = _sanitize_serial(serial)
    if serial in _CARRIER_HANDLES:
        return True
    try:
        handle = display(
            HTML(_carrier_placeholder_html(serial)),
            display_id=_carrier_display_id(serial),
        )
        _CARRIER_HANDLES[serial] = handle
        return handle is not None
    except Exception:
        return False


def _update_carrier(record: Dict[str, Any]) -> bool:
    """Actualiza el carrier existente y nunca toca el canvas visible."""
    serial = _sanitize_serial(record["serial"])
    markup = _carrier_html(record)
    try:
        if not _ensure_carrier_handle(serial):
            return False
        handle = _CARRIER_HANDLES.get(serial)
        if handle is None:
            return False
        handle.update(HTML(markup))
        return True
    except Exception:
        # Último recurso: publicar una salida con el mismo display_id. Esto
        # permite recuperarse si Colab invalidó un DisplayHandle antiguo.
        try:
            handle = display(HTML(markup), display_id=_carrier_display_id(serial))
            _CARRIER_HANDLES[serial] = handle
            return handle is not None
        except Exception:
            return False


def _request_notebook_save() -> bool:
    """Pide dos saves reales después de actualizar el carrier.

    No hay throttle: omitir un save tras un segundo trazo era precisamente la
    causa de que un board previamente guardado no persistiera su nueva versión.
    """
    try:
        # Da una vuelta al loop de mensajes para que update_display_data llegue
        # al modelo del notebook antes de solicitar la serialización.
        time.sleep(0.16)
        try:
            _colab_message.blocking_request("notebook.save", {})
        except TypeError:
            _colab_message.blocking_request("notebook.save", request="")
        time.sleep(0.16)
        try:
            _colab_message.blocking_request("notebook.save", {})
        except TypeError:
            _colab_message.blocking_request("notebook.save", request="")
        return True
    except Exception:
        return False


# -----------------------------------------------------------------------------
# Recuperación del respaldo .ipynb. Es lenta sólo cuando no hay cache local.
# -----------------------------------------------------------------------------
def _read_ipynb() -> Dict[str, Any]:
    global notebook_json
    try:
        try:
            answer = _colab_message.blocking_request("get_ipynb", timeout_sec=90)
        except TypeError:
            answer = _colab_message.blocking_request("get_ipynb", request="", timeout_sec=90)
        raw = answer.get("ipynb", answer) if isinstance(answer, dict) else answer
        if isinstance(raw, str):
            raw = json.loads(raw)
        notebook_json = raw if isinstance(raw, dict) else {}
        return notebook_json
    except Exception:
        notebook_json = {}
        return {}


_IMG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE | re.DOTALL)
_ATTR_RE = re.compile(
    r'''\b(?P<key>[A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(?P<q>["'])(?P<value>.*?)(?P=q)''',
    re.IGNORECASE | re.DOTALL,
)


def _html_outputs(nb: Dict[str, Any]) -> Iterable[Tuple[int, int, str]]:
    for cell_i, cell in enumerate(nb.get("cells", []) if isinstance(nb, dict) else []):
        if not isinstance(cell, dict):
            continue
        for output_i, out in enumerate(cell.get("outputs", []) or []):
            if not isinstance(out, dict):
                continue
            data = out.get("data", {}) or {}
            for mime in ("text/html", "text/plain", "text"):
                if mime in data:
                    yield cell_i, output_i, _mime_text(data[mime])


def _carriers_in_html(markup: str, requested: Optional[str] = None) -> Iterable[Dict[str, Any]]:
    requested = _sanitize_serial(requested) if requested else None
    for tag in _IMG_RE.findall(markup or ""):
        attrs = {
            m.group("key").lower(): html.unescape(m.group("value"))
            for m in _ATTR_RE.finditer(tag)
        }
        ident = attrs.get("id", "")
        if not ident.startswith(_PREFIX):
            continue
        serial = _sanitize_serial(ident[len(_PREFIX):])
        if requested and serial != requested:
            continue
        src = attrs.get("src", "")
        if not src.startswith("data:image/png;base64,"):
            continue
        try:
            revision = max(0, int(attrs.get("data-amc-revision", "0") or 0))
        except Exception:
            revision = 0
        yield {"serial": serial, "data_url": src, "revision": revision, "sha256": attrs.get("data-amc-sha256", "")}


def _find_in_ipynb(serial: str) -> Optional[Dict[str, Any]]:
    serial = _sanitize_serial(serial)
    notebook = _read_ipynb()
    best: Optional[Dict[str, Any]] = None
    best_order = (-1, -1)
    needle = _PREFIX + serial
    for cell_i, out_i, markup in _html_outputs(notebook):
        # Evita parsear outputs que no contienen exactamente el board solicitado.
        if needle not in markup:
            continue
        for candidate in _carriers_in_html(markup, serial):
            order = (cell_i, out_i)
            if best is None or candidate["revision"] > best["revision"] or (
                candidate["revision"] == best["revision"] and order >= best_order
            ):
                best, best_order = candidate, order
    notebook_json.clear()  # No retener un notebook potencialmente enorme.
    return best


def _restore_record(serial: str) -> Optional[Dict[str, Any]]:
    """Fuente de verdad para un board: runtime -> archivo temporal -> .ipynb."""
    serial = _sanitize_serial(serial)
    record = _RECORDS.get(serial)
    if record and record.get("png_b64"):
        return record

    runtime_png = _read_runtime_copy(serial)
    if runtime_png:
        restored = _set_record(serial, runtime_png, 0, "runtime_file", force_equal=True)
        if restored:
            return restored

    found = _find_in_ipynb(serial)
    if not found:
        return None
    return _set_record(
        serial, found["data_url"], int(found.get("revision", 0) or 0), "ipynb", force_equal=True
    )


# -----------------------------------------------------------------------------
# Callbacks del kernel
# -----------------------------------------------------------------------------
def _save_name(serial: str) -> str:
    return f"amc.board.v20.save.{_sanitize_serial(serial)}"


def _restore_name(serial: str) -> str:
    return f"amc.board.v20.restore.{_sanitize_serial(serial)}"


def _make_save_callback(serial: str):
    serial = _sanitize_serial(serial)

    def callback(data_url: str, base_revision: Any = 0, token: Any = "") -> Dict[str, Any]:
        checked = _decode_png_data_url(data_url)
        if checked is None:
            return {"ok": False, "retryable": False, "error": "El PNG recibido no es válido."}
        png_b64, payload, digest = checked
        try:
            base = max(0, int(base_revision or 0))
        except Exception:
            base = 0
        token_text = str(token or "")[:180]

        with _LOCK:
            current = _RECORDS.get(serial)

            # Al reconectar, JS puede haber restaurado r13 desde un carrier,
            # mientras este nuevo runtime todavía cree que está en r0. Antes de
            # declarar conflicto, hidratamos el único board requerido.
            if current is None and base > 0:
                # Intentamos recuperar la versión anterior, pero la ausencia de
                # carrier NO puede bloquear el guardado de un board que el
                # navegador ya tiene en su cache local. En ese caso la base del
                # cliente se usa para mantener la revisión monotónica y el PNG
                # actual se convierte en el nuevo respaldo portátil.
                current = _restore_record(serial)

            current_revision = int((current or {}).get("revision", 0) or 0)
            current_digest = str((current or {}).get("sha256", "") or "")
            seen = dict((current or {}).get("seen", {}))

            # Reintento de la misma llamada: no crear una revisión duplicada.
            if token_text and seen.get(token_text) == digest:
                return {"ok": True, "duplicate": True, "revision": current_revision, "sha256": current_digest}

            # El browser puede tener una copia local confirmada con rN mientras
            # el runtime nuevo sólo alcanzó a leer un carrier anterior rN-1.
            # Para un canvas PNG no existe una fusión semántica útil; la regla
            # segura para una sesión personal es "el último snapshot terminado
            # gana", con revisión siempre monótona. Nunca se bloquea un nuevo
            # guardado sólo porque el runtime y el navegador difieren.
            if current_digest == digest:
                return {"ok": True, "duplicate": True, "revision": current_revision, "sha256": current_digest}

            revision = max(current_revision, base) + 1
            record = {
                "serial": serial,
                "png_b64": png_b64,
                "revision": revision,
                "sha256": digest,
                "bytes_png": len(payload),
                "updated_at": time.time(),
                "source": "save",
                "seen": {**seen, **({token_text: digest} if token_text else {})},
            }
            if len(record["seen"]) > 64:
                record["seen"] = dict(list(record["seen"].items())[-64:])

            # No avanzamos el estado autoritativo del runtime si no logramos
            # actualizar el carrier de la celda. De esa forma el reintento usa
            # la misma base y no queda atrapado en un falso conflicto.
            if not _update_carrier(record):
                return {
                    "ok": False,
                    "retryable": True,
                    "error": "Colab aún no aceptó actualizar el carrier; la copia local queda protegida y se reintentará.",
                }

            _RECORDS[serial] = record
            _sync_public_records()
            _write_runtime_copy(serial, payload)
            notebook_saved = _request_notebook_save()
            return {
                "ok": True,
                "revision": revision,
                "sha256": digest,
                "notebook_save_requested": bool(notebook_saved),
            }

    return callback


def _make_restore_callback(serial: str):
    serial = _sanitize_serial(serial)

    def callback() -> Dict[str, Any]:
        with _LOCK:
            record = _restore_record(serial)
            if not record:
                return {"ok": True, "found": False, "revision": 0}
            return {
                "ok": True,
                "found": True,
                "data_url": _record_data_url(record),
                "revision": int(record.get("revision", 0) or 0),
                "sha256": record.get("sha256", ""),
            }

    return callback


def _ensure_callbacks(serial: str) -> Tuple[str, str]:
    _require_colab()
    serial = _sanitize_serial(serial)
    save, restore = _save_name(serial), _restore_name(serial)
    if save not in _REGISTERED:
        _colab_output.register_callback(save, _make_save_callback(serial))
        _REGISTERED.add(save)
    if restore not in _REGISTERED:
        _colab_output.register_callback(restore, _make_restore_callback(serial))
        _REGISTERED.add(restore)
    return save, restore


# -----------------------------------------------------------------------------
# Interfaz HTML / JavaScript. Una instancia aislada por cada board() ejecutado.
# -----------------------------------------------------------------------------
def _board_html(serial: str, instance: str, save_callback: str, restore_callback: str) -> str:
    root = f"amc_v20_root_{instance}"
    canvas = f"amc_v20_canvas_{instance}"
    state = f"amc_v20_state_{instance}"

    template = r'''<div id="__ROOT__" class="amc-board-v20">
<style>
#__ROOT__{font-family:Inter,system-ui,-apple-system,"Segoe UI",Arial,sans-serif;background:#f8fafc;border:1px solid #e2e8f0;border-radius:14px;overflow:hidden;max-width:100%;}
#__ROOT__ *{box-sizing:border-box}#__ROOT__ .bar{padding:10px 12px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;background:#fff;border-bottom:1px solid #e2e8f0}
#__ROOT__ button{border:1px solid #cbd5e1;background:#fff;border-radius:9px;padding:7px 10px;font-weight:650;cursor:pointer;color:#0f172a}#__ROOT__ button:hover{background:#f1f5f9}
#__ROOT__ label{font-size:13px;color:#334155;display:flex;gap:5px;align-items:center}#__ROOT__ input[type=color]{height:32px;width:42px;border:1px solid #cbd5e1;border-radius:7px;padding:2px;background:#fff}#__ROOT__ input[type=range]{accent-color:#0f766e}
#__ROOT__ .head{padding:9px 12px;font-size:13px;color:#475569;background:#f8fafc}#__ROOT__ .state{margin-left:8px;padding:3px 7px;border-radius:999px;background:#e2e8f0;color:#334155;font-size:11px}.amc-board-v20 .state[data-mode=saving]{background:#fef3c7;color:#92400e}.amc-board-v20 .state[data-mode=saved]{background:#dcfce7;color:#166534}.amc-board-v20 .state[data-mode=error]{background:#fee2e2;color:#991b1b}
#__ROOT__ canvas{display:block;width:calc(100% - 24px);height:460px;margin:12px;border:1px solid #cbd5e1;border-radius:10px;background:#fff;touch-action:none;cursor:crosshair;box-shadow:0 5px 18px rgba(15,23,42,.08)}
</style>
<div class="head">Board: <b>__SERIAL_HTML__</b><span id="__STATE__" class="state" data-mode="saving">Recuperando estado guardado…</span></div>
<div class="bar"><button data-a="pen">✏️ Lápiz</button><button data-a="eraser">🧹 Borrador</button><label>Color <input data-r="color" type="color" value="#0f172a"></label><label>Grosor <input data-r="size" type="range" min="1" max="50" value="7"></label><button data-a="undo">↩ Undo</button><button data-a="redo">↪ Redo</button><button data-a="clear">🗑 Limpiar</button><button data-a="download">⬇ PNG</button></div>
<canvas id="__CANVAS__"></canvas>
<script>
(()=>{
const ROOT_ID=__ROOT_JSON__, CANVAS_ID=__CANVAS_JSON__, STATE_ID=__STATE_JSON__;
const SERIAL=__SERIAL_JSON__, INSTANCE=__INSTANCE_JSON__, SAVE_CALLBACK=__SAVE_JSON__, RESTORE_CALLBACK=__RESTORE_JSON__;
const PREFIX=__PREFIX_JSON__, DB_NAME=__DB_JSON__, STORE=__STORE_JSON__;
const root=document.getElementById(ROOT_ID), canvas=document.getElementById(CANVAS_ID), state=document.getElementById(STATE_ID);
if(!root||!canvas||!state||root.dataset.ready==='1')return; root.dataset.ready='1';
const ctx=canvas.getContext('2d'); const color=root.querySelector('[data-r=color]'), size=root.querySelector('[data-r=size]');
let dpr=Math.max(1,window.devicePixelRatio||1), ready=false, drawing=false, tool='pen', knownRevision=0, seq=0, pending=null, pumping=false, timer=null, last={x:0,y:0};
const undo=[], redo=[]; const MAX_HISTORY=24;
function status(text,mode='idle'){state.textContent=text;state.dataset.mode=mode;}
function response(answer){if(!answer)return {};if(answer.data&&typeof answer.data==='object')return answer.data;if(typeof answer.data==='string'){try{return JSON.parse(answer.data)}catch(_){}}return answer;}
function kernel(){return !!(window.google&&google.colab&&google.colab.kernel&&typeof google.colab.kernel.invokeFunction==='function');}
function identity(){try{return String(window.top.location.href).replace(/[?#].*$/,'')}catch(_){return String(location.href).replace(/[?#].*$/,'')}}
function key(){return identity()+'::'+SERIAL;}
function init(){canvas.width=Math.max(1,Math.round(canvas.clientWidth*dpr));canvas.height=Math.max(1,Math.round(canvas.clientHeight*dpr));ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.lineCap='round';ctx.lineJoin='round';}
function snapshot(){try{return canvas.toDataURL('image/png')}catch(_){return ''}}
function point(e){const r=canvas.getBoundingClientRect();return{x:(e.clientX-r.left)*dpr,y:(e.clientY-r.top)*dpr};}
function draw(a,b){ctx.save();ctx.globalCompositeOperation='source-over';ctx.strokeStyle=tool==='eraser'?'#fff':color.value;ctx.lineWidth=Math.max(1,Number(size.value)||1)*dpr;ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();ctx.restore();}
function toBlob(url){return fetch(url).then(r=>r.blob()).catch(()=>null)}
function paint(url){if(typeof url!=='string'||!url.startsWith('data:image/png;base64,'))return Promise.resolve(false);return new Promise(resolve=>{const img=new Image();img.onload=()=>{ctx.save();ctx.globalCompositeOperation='source-over';ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(img,0,0,img.naturalWidth,img.naturalHeight,0,0,canvas.width,canvas.height);ctx.restore();resolve(true)};img.onerror=()=>resolve(false);img.src=url;});}
function push(value){value=value||snapshot();if(!value)return;undo.push(value);while(undo.length>MAX_HISTORY)undo.shift();redo.length=0;}
function db(){return new Promise((resolve,reject)=>{try{const r=indexedDB.open(DB_NAME,1);r.onupgradeneeded=()=>{if(!r.result.objectStoreNames.contains(STORE))r.result.createObjectStore(STORE)};r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error)}catch(e){reject(e)}})}
async function cacheRead(){try{const d=await db();return await new Promise((resolve,reject)=>{const r=d.transaction(STORE,'readonly').objectStore(STORE).get(key());r.onsuccess=()=>resolve(r.result||null);r.onerror=()=>reject(r.error)});}catch(_){return null}}
async function cacheWrite(url,revision,dirty){try{const blob=await toBlob(url);if(!blob)return false;const d=await db();await new Promise((resolve,reject)=>{const r=d.transaction(STORE,'readwrite').objectStore(STORE).put({blob,revision:Number(revision)||0,dirty:!!dirty,updated:Date.now()},key());r.onsuccess=()=>resolve();r.onerror=()=>reject(r.error)});return true}catch(_){return false}}
async function blobToUrl(blob){return new Promise(resolve=>{try{const fr=new FileReader();fr.onload=()=>resolve(String(fr.result||''));fr.onerror=()=>resolve('');fr.readAsDataURL(blob)}catch(_){resolve('')}})}
function documents(){const docs=[document];for(const w of [window.parent,window.top]){try{if(w&&w.document&&!docs.includes(w.document))docs.push(w.document)}catch(_){}}for(const doc of docs.slice()){try{for(const f of Array.from(doc.querySelectorAll('iframe')).slice(0,180)){try{if(f.contentDocument&&!docs.includes(f.contentDocument))docs.push(f.contentDocument)}catch(_){}}}catch(_){}}return docs;}
function mounted(){let best=null,id=PREFIX+SERIAL;for(const doc of documents()){try{for(const n of doc.querySelectorAll('img[id="'+id+'"]')){const src=n.getAttribute('src')||'';if(!src.startsWith('data:image/png;base64,'))continue;const rev=Number(n.getAttribute('data-amc-revision')||0)||0;if(!best||rev>=best.revision)best={data_url:src,revision:rev};}}catch(_){}}return best;}
async function restore(){init();let local=await cacheRead(), mountedCopy=mounted(), chosen=null;
  if(local&&local.blob){const data=await blobToUrl(local.blob);if(data)chosen={data_url:data,revision:Number(local.revision)||0,dirty:!!local.dirty,from:'local'};}
  if(mountedCopy&&(!chosen||(!chosen.dirty&&mountedCopy.revision>chosen.revision)))chosen={...mountedCopy,dirty:false,from:'notebook'};
  if(chosen&&await paint(chosen.data_url)){knownRevision=chosen.revision;push(snapshot());ready=true;status(chosen.dirty?'✓ Copia local recuperada; sincronizando…':'✓ Board restaurado','saved');if(chosen.dirty)enqueue('sincronizar');return;}
  if(!kernel()){ready=true;status('Sin runtime: board nuevo local','error');return;}
  status('Buscando respaldo portátil…','saving');
  for(let attempt=0;attempt<2;attempt++){try{const answer=await google.colab.kernel.invokeFunction(RESTORE_CALLBACK,[],{});const r=response(answer);if(r&&r.ok&&r.found&&r.data_url&&await paint(r.data_url)){knownRevision=Number(r.revision)||0;push(snapshot());ready=true;await cacheWrite(snapshot(),knownRevision,false);status('✓ Board recuperado del notebook','saved');return;}if(r&&r.ok&&!r.found){ready=true;status('Listo para dibujar','idle');return;}}catch(e){console.warn('AutoMind Board restore',e);}await new Promise(r=>setTimeout(r,600));}
  ready=true;status('No se pudo verificar respaldo; puedes dibujar y la copia local se protegerá','error');
}
function enqueue(reason){clearTimeout(timer);const data=snapshot();if(!data)return;cacheWrite(data,knownRevision,true);pending={data,reason:String(reason||'cambio')};if(!pumping)void pump();}
function later(reason){clearTimeout(timer);timer=setTimeout(()=>enqueue(reason),160)}
async function pump(){if(pumping)return;pumping=true;try{while(pending){const item=pending;pending=null;if(!kernel()){status('✓ Copia local protegida; runtime desconectado','error');continue;}let result=null,failed=false;for(let attempt=0;attempt<3;attempt++){const token=INSTANCE+':'+(++seq);try{const ans=await google.colab.kernel.invokeFunction(SAVE_CALLBACK,[item.data,knownRevision,token],{});result=response(ans);if(result&&result.ok)break;if(result&&result.conflict)break;}catch(e){console.warn('AutoMind Board save',e);failed=true;}await new Promise(r=>setTimeout(r,350*(attempt+1)));}
  if(result&&result.ok){knownRevision=Math.max(knownRevision,Number(result.revision)||0);await cacheWrite(item.data,knownRevision,false);status('✓ Guardado en notebook · r'+knownRevision,'saved');continue;}
  if(result&&result.conflict){knownRevision=Math.max(knownRevision,Number(result.revision)||0);await cacheWrite(item.data,knownRevision,true);status('Conflicto: tu copia local fue preservada; no se sobrescribió el respaldo','error');continue;}
  await cacheWrite(item.data,knownRevision,true);status('✓ Copia local protegida; Colab reintentará al próximo cambio','error');if(!failed&&result&&result.retryable){pending=item;setTimeout(()=>{if(!pumping)void pump()},1200);}
}}
finally{pumping=false;if(pending)void pump();}}
function finish(e){if(!drawing)return;try{if(e&&Number.isFinite(e.clientX)){const p=point(e);draw(last,p)}}catch(_){}drawing=false;try{if(e&&canvas.hasPointerCapture(e.pointerId))canvas.releasePointerCapture(e.pointerId)}catch(_){}enqueue('trazo');}
canvas.addEventListener('pointerdown',e=>{if(!ready){status('Aún se está recuperando el board…','saving');return;}drawing=true;push();try{canvas.setPointerCapture(e.pointerId)}catch(_){}last=point(e);draw(last,last);});
canvas.addEventListener('pointermove',e=>{if(!drawing)return;const p=point(e);draw(last,p);last=p;});canvas.addEventListener('pointerup',finish);canvas.addEventListener('pointercancel',finish);canvas.addEventListener('lostpointercapture',finish);
root.querySelector('[data-a=pen]').onclick=()=>tool='pen';root.querySelector('[data-a=eraser]').onclick=()=>tool='eraser';root.querySelector('[data-a=clear]').onclick=()=>{if(!ready)return;push();ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);enqueue('limpiar')};
root.querySelector('[data-a=undo]').onclick=async()=>{if(!ready||!undo.length)return;const cur=snapshot(),prev=undo.pop();if(cur)redo.push(cur);if(await paint(prev))enqueue('undo')};root.querySelector('[data-a=redo]').onclick=async()=>{if(!ready||!redo.length)return;const cur=snapshot(),next=redo.pop();if(cur)undo.push(cur);if(await paint(next))enqueue('redo')};
root.querySelector('[data-a=download]').onclick=()=>{const a=document.createElement('a');a.href=snapshot();a.download='board_'+SERIAL+'.png';a.click();};
window.addEventListener('resize',()=>{if(!canvas.width)return;const old=document.createElement('canvas');old.width=canvas.width;old.height=canvas.height;old.getContext('2d').drawImage(canvas,0,0);dpr=Math.max(1,window.devicePixelRatio||1);init();ctx.drawImage(old,0,0,old.width,old.height,0,0,canvas.width,canvas.height);});
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden'&&ready)enqueue('pestana_oculta')});window.addEventListener('pagehide',()=>{if(ready)enqueue('salida')});window.addEventListener('blur',()=>{if(ready)setTimeout(()=>enqueue('perdida_foco'),0)});
void restore();
})();
</script></div>'''

    replacements = {
        "__ROOT__": root,
        "__CANVAS__": canvas,
        "__STATE__": state,
        "__SERIAL_HTML__": html.escape(serial),
        "__ROOT_JSON__": json.dumps(root),
        "__CANVAS_JSON__": json.dumps(canvas),
        "__STATE_JSON__": json.dumps(state),
        "__SERIAL_JSON__": json.dumps(serial),
        "__INSTANCE_JSON__": json.dumps(instance),
        "__SAVE_JSON__": json.dumps(save_callback),
        "__RESTORE_JSON__": json.dumps(restore_callback),
        "__PREFIX_JSON__": json.dumps(_PREFIX),
        "__DB_JSON__": json.dumps(_DB_NAME),
        "__STORE_JSON__": json.dumps(_DB_STORE),
    }
    for key, value in replacements.items():
        template = template.replace(key, value)
    return template


# -----------------------------------------------------------------------------
# API pública
# -----------------------------------------------------------------------------
def board(serial: str = "board") -> None:
    """Abre y recupera automáticamente un board con un único comando."""
    _require_colab()
    serial = _sanitize_serial(serial)
    save_callback, restore_callback = _ensure_callbacks(serial)

    # Establece primero un carrier vacío asociado a ESTA ejecución de celda.
    # No contiene imagen y por eso no borra ni eclipsa carriers antiguos; sólo
    # deja preparado el DisplayHandle que los guardados posteriores actualizarán.
    _ensure_carrier_handle(serial)
    display(HTML(_board_html(serial, uuid.uuid4().hex, save_callback, restore_callback)))


def listar_boards(incluir_base64: bool = False, recargar: bool = False):
    if recargar:
        get_boards()
    rows = []
    for serial in sorted(_RECORDS):
        item = dict(_RECORDS[serial])
        if not incluir_base64:
            item.pop("png_b64", None)
        rows.append(item)
    return rows


def get_boards(incluir_base64: bool = False):
    """Opcional: carga todos los carriers del notebook. board() no lo necesita."""
    _require_colab()
    notebook = _read_ipynb()
    latest: Dict[str, Dict[str, Any]] = {}
    for cell_i, out_i, markup in _html_outputs(notebook):
        if _PREFIX not in markup:
            continue
        for candidate in _carriers_in_html(markup):
            old = latest.get(candidate["serial"])
            if old is None or candidate["revision"] >= old["revision"]:
                latest[candidate["serial"]] = candidate
    notebook_json.clear()
    for candidate in latest.values():
        _set_record(candidate["serial"], candidate["data_url"], candidate["revision"], "ipynb", force_equal=True)
    return listar_boards(incluir_base64=incluir_base64)


def recargar_boards_desde_notebook(conservar_runtime: bool = True):
    return get_boards(incluir_base64=False)


def diagnostico_boards() -> Dict[str, Any]:
    return {
        "version": _VERSION,
        "boards_en_runtime": listar_boards(False),
        "callbacks_registrados": sorted(_REGISTERED),
        "carrier_handles": sorted(_CARRIER_HANDLES),
        "nota": "board(serial) recupera automáticamente sin requerir get_boards().",
    }


__all__ = [
    "board", "get_boards", "listar_boards", "recargar_boards_desde_notebook",
    "diagnostico_boards", "boards_guardados", "notebook_json",
]
