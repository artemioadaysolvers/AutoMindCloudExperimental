"""
AutoMindCloud.Board_Script
==========================
Pizarra persistente, rápida y tolerante a reconexiones para Google Colab.

Uso normal (único comando necesario):

    from AutoMindCloud.Board_Script import *
    board("alpha")

Diseño de durabilidad
---------------------
1. IndexedDB guarda un PNG binario local después de cada cambio confirmado.
2. Un carrier HTML oculto, serializable dentro del .ipynb, guarda el mismo PNG
   como respaldo portátil entre runtimes, navegadores y cuentas.
3. La restauración prioriza IndexedDB, luego carriers ya montados y, sólo si
   ambos faltan, consulta get_ipynb en segundo plano para el board solicitado.

Principios de seguridad
-----------------------
* No se redefine la misma función varias veces.
* No se envuelve globalmente google.colab.kernel.invokeFunction.
* Cada board tiene una cola de guardado secuencial: nunca hay dos escrituras
  concurrentes del mismo canvas.
* Cada snapshot usa revisión base + secuencia de cliente + hash SHA-256.
  Un snapshot viejo no puede sobrescribir un respaldo más nuevo.
* Una recuperación tardía nunca pisa un dibujo que el usuario ya comenzó.
* Cada visualizador tiene ids únicos: ejecutar board("alpha") varias veces no
  enlaza el JavaScript con un canvas viejo.
"""

from __future__ import annotations

import base64
import hashlib
import html as _html
import json
import os
import re
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple

from IPython.display import HTML, display

try:  # El módulo puede importarse fuera de Colab sin fallar de inmediato.
    from google.colab import output as _colab_output
    from google.colab import _message as _colab_message
except Exception:  # pragma: no cover - sólo para importación local.
    _colab_output = None
    _colab_message = None


# ---------------------------------------------------------------------------
# Configuración y estado de runtime
# ---------------------------------------------------------------------------
_VERSION = "11.0"
_CARRIER_PREFIX = "amc_persisted_snapshot_"
_MANIFEST_ID = "amc_board_manifest_v11"
_CACHE_DB_NAME = "amc_board_cache_v11"
_CACHE_STORE = "boards"
_CACHE_CATALOG_KEY = "amc_board_catalog_v11"
_MAX_PNG_BYTES = 45 * 1024 * 1024
_SAVE_REQUEST_MIN_INTERVAL_SECONDS = 0.65

# Compatibilidad con scripts anteriores que inspeccionan estas variables.
boards_guardados: List[Dict[str, Any]] = []
notebook_json: Dict[str, Any] = {}

_RECORDS: Dict[str, Dict[str, Any]] = {}
_CARRIER_HANDLES: Dict[str, Any] = {}
_MANIFEST_HANDLE: Any = None
_REGISTERED_SAVE_CALLBACKS: set[str] = set()
_REGISTERED_RESTORE_CALLBACKS: set[str] = set()
_LAST_NOTEBOOK_SAVE_REQUEST_AT = 0.0
_LAST_DISCOVERY_SOURCE = "runtime"
_LAST_DISCOVERY_ERROR: Optional[str] = None


# ---------------------------------------------------------------------------
# Utilidades Python puras
# ---------------------------------------------------------------------------
def _require_colab() -> None:
    if _colab_output is None or _colab_message is None:
        raise RuntimeError(
            "AutoMindCloud.Board_Script requiere Google Colab y un runtime activo."
        )


def _sanitize_serial(value: Any) -> str:
    text = str(value or "board").strip()
    text = re.sub(r"[^A-Za-z0-9_]+", "_", text)
    return text or "board"


def _mime_to_text(value: Any) -> str:
    if isinstance(value, list):
        return "".join(str(item) for item in value)
    return str(value or "")


def _data_url_to_png(data_url: Any) -> Optional[Tuple[str, bytes, str]]:
    """Valida un data:image/png;base64 y devuelve (base64, bytes, sha256)."""
    prefix = "data:image/png;base64,"
    if not isinstance(data_url, str) or not data_url.startswith(prefix):
        return None
    encoded = data_url[len(prefix):]
    if not encoded:
        return None
    try:
        payload = base64.b64decode(encoded, validate=True)
    except Exception:
        return None
    if not payload or len(payload) > _MAX_PNG_BYTES:
        return None
    digest = hashlib.sha256(payload).hexdigest()
    return encoded, payload, digest


def _record_data_url(record: Optional[Dict[str, Any]]) -> str:
    if not record or not record.get("png_b64"):
        return ""
    return "data:image/png;base64," + str(record["png_b64"])


def _public_record(record: Dict[str, Any], include_base64: bool = False) -> Dict[str, Any]:
    result = {
        "serial": record.get("serial"),
        "revision": int(record.get("revision", 0) or 0),
        "bytes_png_aprox": int(record.get("bytes_png", 0) or 0),
        "sha256": record.get("sha256", ""),
        "updated_at": float(record.get("updated_at", 0.0) or 0.0),
        "source": record.get("source", "runtime"),
    }
    if include_base64:
        result["png_b64"] = record.get("png_b64", "")
    return result


def _sync_public_records() -> None:
    boards_guardados[:] = [
        dict(_RECORDS[key]) for key in sorted(_RECORDS.keys())
    ]


def _remember_record(
    serial: str,
    data_url: str,
    revision: int = 0,
    source: str = "runtime",
    allow_equal_replace: bool = False,
) -> Optional[Dict[str, Any]]:
    """Inserta una copia recuperada sin reemplazar una revisión más nueva."""
    serial = _sanitize_serial(serial)
    checked = _data_url_to_png(data_url)
    if checked is None:
        return None
    png_b64, payload, digest = checked
    try:
        revision = max(0, int(revision or 0))
    except Exception:
        revision = 0

    previous = _RECORDS.get(serial)
    if previous:
        old_revision = int(previous.get("revision", 0) or 0)
        if old_revision > revision:
            return previous
        if old_revision == revision and not allow_equal_replace:
            # Para revisiones iguales, no sustituir silenciosamente una copia ya
            # conocida salvo que sea exactamente el mismo PNG.
            if previous.get("sha256") != digest:
                return previous
            return previous

    record = {
        "serial": serial,
        "png_b64": png_b64,
        "bytes_png": len(payload),
        "sha256": digest,
        "revision": revision,
        "updated_at": time.time(),
        "source": source,
        # Secuencias aceptadas por instancia para idempotencia de callbacks.
        "session_sequences": dict((previous or {}).get("session_sequences", {})),
    }
    _RECORDS[serial] = record
    _sync_public_records()
    return record


def _find_record(serial: str) -> Optional[Dict[str, Any]]:
    return _RECORDS.get(_sanitize_serial(serial))


def _atomic_write_png(serial: str, payload: bytes) -> None:
    """Copia de contingencia mientras el runtime siga vivo."""
    serial = _sanitize_serial(serial)
    path = f"/content/pizarra_cell_{serial}.png"
    temporary = path + ".tmp"
    try:
        with open(temporary, "wb") as fh:
            fh.write(payload)
        os.replace(temporary, path)
    except Exception:
        try:
            if os.path.exists(temporary):
                os.remove(temporary)
        except Exception:
            pass


def _file_to_data_url(path: str) -> str:
    try:
        with open(path, "rb") as fh:
            payload = fh.read()
        if not payload or len(payload) > _MAX_PNG_BYTES:
            return ""
        return "data:image/png;base64," + base64.b64encode(payload).decode("ascii")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Carrier y manifest serializables dentro del notebook
# ---------------------------------------------------------------------------
def _carrier_html(serial: str, data_url: str = "", revision: int = 0, digest: str = "") -> str:
    serial = _sanitize_serial(serial)
    return f'''<div aria-hidden="true" data-amc-carrier-version="{_VERSION}"
style="position:fixed;left:-10000px;top:-10000px;width:1px;height:1px;overflow:hidden;opacity:0;pointer-events:none;">
<img id="{_CARRIER_PREFIX}{serial}" data-amc-revision="{int(revision or 0)}"
data-amc-sha256="{_html.escape(str(digest or ''), quote=True)}"
src="{_html.escape(str(data_url or ''), quote=True)}" alt="AutoMind persisted board" />
</div>'''


def _manifest_html() -> str:
    rows = [
        {
            "serial": item["serial"],
            "revision": int(item.get("revision", 0) or 0),
            "bytes_png_aprox": int(item.get("bytes_png", 0) or 0),
            "sha256": item.get("sha256", ""),
        }
        for item in _RECORDS.values()
    ]
    encoded = _html.escape(json.dumps(rows, separators=(",", ":")), quote=True)
    return f'''<div id="{_MANIFEST_ID}" data-amc-board-manifest="{encoded}"
aria-hidden="true" style="display:none"></div>'''


def _ensure_carrier_handle(serial: str) -> Any:
    handle = _CARRIER_HANDLES.get(serial)
    if handle is None:
        handle = display(HTML(_carrier_html(serial)), display_id=True)
        _CARRIER_HANDLES[serial] = handle
    return handle


def _update_carrier_output(record: Dict[str, Any]) -> bool:
    """Actualiza sólo el respaldo oculto; nunca recrea el canvas visible."""
    serial = record["serial"]
    html = _carrier_html(
        serial,
        _record_data_url(record),
        int(record.get("revision", 0) or 0),
        record.get("sha256", ""),
    )
    try:
        handle = _ensure_carrier_handle(serial)
        handle.update(HTML(html))
        return True
    except Exception:
        try:
            _CARRIER_HANDLES[serial] = display(HTML(html), display_id=True)
            return True
        except Exception:
            return False


def _update_manifest_output() -> bool:
    global _MANIFEST_HANDLE
    try:
        html = _manifest_html()
        if _MANIFEST_HANDLE is None:
            _MANIFEST_HANDLE = display(HTML(html), display_id=True)
        else:
            _MANIFEST_HANDLE.update(HTML(html))
        return True
    except Exception:
        return False


def _request_notebook_save() -> bool:
    """Solicita guardado con throttling; no bloquea con lecturas del notebook."""
    global _LAST_NOTEBOOK_SAVE_REQUEST_AT
    now = time.monotonic()
    if now - _LAST_NOTEBOOK_SAVE_REQUEST_AT < _SAVE_REQUEST_MIN_INTERVAL_SECONDS:
        return False
    _LAST_NOTEBOOK_SAVE_REQUEST_AT = now
    try:
        # Se da una fracción de segundo al frontend para incorporar DisplayHandle.update.
        time.sleep(0.055)
        try:
            _colab_message.blocking_request("notebook.save", {})
        except TypeError:
            _colab_message.blocking_request("notebook.save", request="")
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Lectura de respaldo del .ipynb: se usa sólo cuando no existe copia local.
# ---------------------------------------------------------------------------
def _read_notebook_json() -> Dict[str, Any]:
    global notebook_json
    _require_colab()
    try:
        try:
            response = _colab_message.blocking_request("get_ipynb", timeout_sec=90)
        except TypeError:
            response = _colab_message.blocking_request(
                "get_ipynb", request="", timeout_sec=90
            )
        raw: Any = response.get("ipynb", response) if isinstance(response, dict) else response
        if isinstance(raw, str):
            raw = json.loads(raw)
        notebook_json = raw if isinstance(raw, dict) else {}
        return notebook_json
    except Exception:
        notebook_json = {}
        return {}


_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE | re.DOTALL)
_ATTR_RE = re.compile(
    r'''\b(?P<name>[A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)''',
    re.IGNORECASE | re.DOTALL,
)


def _iter_html_outputs(nb: Dict[str, Any]) -> Iterable[Tuple[int, int, str]]:
    for cell_index, cell in enumerate(nb.get("cells", []) if isinstance(nb, dict) else []):
        if not isinstance(cell, dict):
            continue
        for output_index, output in enumerate(cell.get("outputs", []) or []):
            if not isinstance(output, dict):
                continue
            data = output.get("data", {}) or {}
            for mime in ("text/html", "text/plain", "text"):
                if mime in data:
                    yield cell_index, output_index, _mime_to_text(data[mime])


def _parse_carriers_from_html(html_text: str) -> Iterable[Dict[str, Any]]:
    for tag in _TAG_RE.findall(html_text or ""):
        attrs = {
            match.group("name").lower(): _html.unescape(match.group("value"))
            for match in _ATTR_RE.finditer(tag)
        }
        identifier = attrs.get("id", "")
        if not identifier.startswith(_CARRIER_PREFIX):
            continue
        serial = _sanitize_serial(identifier[len(_CARRIER_PREFIX):])
        src = attrs.get("src", "")
        if not src.startswith("data:image/png;base64,"):
            continue
        try:
            revision = max(0, int(attrs.get("data-amc-revision", "0") or 0))
        except Exception:
            revision = 0
        yield {
            "serial": serial,
            "data_url": src,
            "revision": revision,
            "sha256": attrs.get("data-amc-sha256", ""),
        }


def _extract_one_board_from_notebook(nb: Dict[str, Any], serial: str) -> Optional[Dict[str, Any]]:
    serial = _sanitize_serial(serial)
    winner: Optional[Dict[str, Any]] = None
    winner_order = (-1, -1)
    for cell_index, output_index, html_text in _iter_html_outputs(nb):
        # Pre-filtro barato: evita parsear tags grandes en outputs que no tienen ese serial.
        if f"{_CARRIER_PREFIX}{serial}" not in html_text:
            continue
        for candidate in _parse_carriers_from_html(html_text):
            if candidate["serial"] != serial:
                continue
            order = (cell_index, output_index)
            if (
                winner is None
                or candidate["revision"] > winner["revision"]
                or (candidate["revision"] == winner["revision"] and order >= winner_order)
            ):
                winner = candidate
                winner_order = order
    return winner


def _extract_all_boards_from_notebook(nb: Dict[str, Any]) -> List[Dict[str, Any]]:
    latest: Dict[str, Tuple[Dict[str, Any], Tuple[int, int]]] = {}
    for cell_index, output_index, html_text in _iter_html_outputs(nb):
        if _CARRIER_PREFIX not in html_text:
            continue
        for candidate in _parse_carriers_from_html(html_text):
            serial = candidate["serial"]
            previous = latest.get(serial)
            order = (cell_index, output_index)
            if (
                previous is None
                or candidate["revision"] > previous[0]["revision"]
                or (candidate["revision"] == previous[0]["revision"] and order >= previous[1])
            ):
                latest[serial] = (candidate, order)
    return [item[0] for item in latest.values()]


def _restore_one_from_portable_backup(serial: str) -> Optional[Dict[str, Any]]:
    """Último recurso. Sólo lo llama el navegador cuando no encontró cache."""
    serial = _sanitize_serial(serial)
    current = _find_record(serial)
    if current and current.get("png_b64"):
        return current

    temporary = _file_to_data_url(f"/content/pizarra_cell_{serial}.png")
    if temporary:
        restored = _remember_record(serial, temporary, revision=0, source="runtime_file")
        if restored:
            return restored

    nb = _read_notebook_json()
    candidate = _extract_one_board_from_notebook(nb, serial)
    # No retener una copia grande del notebook luego de extraer el único PNG.
    notebook_json.clear()
    if not candidate:
        return None
    return _remember_record(
        serial,
        candidate["data_url"],
        revision=int(candidate.get("revision", 0) or 0),
        source="ipynb_backup",
        allow_equal_replace=True,
    )


# ---------------------------------------------------------------------------
# Callbacks Colab: persistencia con revisión base, secuencia e idempotencia.
# ---------------------------------------------------------------------------
def _save_callback_name(serial: str) -> str:
    return f"amc.board.v11.save.{_sanitize_serial(serial)}"


def _restore_callback_name(serial: str) -> str:
    return f"amc.board.v11.restore.{_sanitize_serial(serial)}"


def _trim_session_sequences(values: Dict[str, int], limit: int = 48) -> Dict[str, int]:
    if len(values) <= limit:
        return values
    # El orden de inserción de dict se preserva en Python moderno.
    return dict(list(values.items())[-limit:])


def _make_save_callback(serial: str):
    serial = _sanitize_serial(serial)

    def _callback(
        data_url_png: str,
        base_revision: Any = 0,
        client_sequence: Any = 0,
        instance_id: Any = "",
        reason: Any = "change",
    ) -> Dict[str, Any]:
        checked = _data_url_to_png(data_url_png)
        if checked is None:
            return {"ok": False, "error": "Snapshot PNG Base64 inválido o demasiado grande."}
        png_b64, payload, digest = checked

        try:
            base = max(0, int(base_revision or 0))
        except Exception:
            base = 0
        try:
            sequence = max(0, int(client_sequence or 0))
        except Exception:
            sequence = 0
        instance = str(instance_id or "anonymous")[:160]

        current = _find_record(serial)
        current_revision = int((current or {}).get("revision", 0) or 0)
        current_digest = str((current or {}).get("sha256", "") or "")
        session_sequences = dict((current or {}).get("session_sequences", {}))
        last_sequence = int(session_sequences.get(instance, -1) or -1)

        # Reintento de una misma petición: responder de forma idempotente.
        if sequence <= last_sequence:
            if current_digest == digest:
                return {
                    "ok": True,
                    "duplicate": True,
                    "revision": current_revision,
                    "sha256": current_digest,
                    "notebook_save_requested": False,
                }
            return {
                "ok": False,
                "conflict": True,
                "error": "Llegó una escritura antigua de esta instancia; se protegió el respaldo más nuevo.",
                "revision": current_revision,
                "sha256": current_digest,
            }

        # Nunca aceptar un snapshot creado sobre una revisión antigua. Esto evita
        # que una salida vieja o una recuperación retrasada pise datos nuevos.
        if base != current_revision:
            session_sequences[instance] = sequence
            if current is not None:
                current["session_sequences"] = _trim_session_sequences(session_sequences)
            if current_digest == digest:
                return {
                    "ok": True,
                    "duplicate": True,
                    "revision": current_revision,
                    "sha256": current_digest,
                    "notebook_save_requested": False,
                }
            return {
                "ok": False,
                "conflict": True,
                "error": "Existe una revisión más nueva. Tu copia local se conserva y no sobrescribió el respaldo.",
                "revision": current_revision,
                "sha256": current_digest,
            }

        new_revision = current_revision + 1
        record = {
            "serial": serial,
            "png_b64": png_b64,
            "bytes_png": len(payload),
            "sha256": digest,
            "revision": new_revision,
            "updated_at": time.time(),
            "source": f"save:{str(reason or 'change')[:40]}",
            "session_sequences": _trim_session_sequences(
                {**session_sequences, instance: sequence}
            ),
        }
        _RECORDS[serial] = record
        _sync_public_records()
        _atomic_write_png(serial, payload)

        carrier_updated = _update_carrier_output(record)
        manifest_updated = _update_manifest_output()
        notebook_save_requested = _request_notebook_save()
        return {
            "ok": True,
            "revision": new_revision,
            "sha256": digest,
            "carrier_updated": bool(carrier_updated),
            "manifest_updated": bool(manifest_updated),
            "notebook_save_requested": bool(notebook_save_requested),
        }

    return _callback


def _make_restore_callback(serial: str):
    serial = _sanitize_serial(serial)

    def _callback() -> Dict[str, Any]:
        record = _restore_one_from_portable_backup(serial)
        if not record:
            return {"ok": False, "not_found": True, "revision": 0}
        return {
            "ok": True,
            "data_url": _record_data_url(record),
            "revision": int(record.get("revision", 0) or 0),
            "sha256": record.get("sha256", ""),
            "source": record.get("source", "runtime"),
        }

    return _callback


def _ensure_callbacks(serial: str) -> Tuple[str, str]:
    _require_colab()
    serial = _sanitize_serial(serial)
    save_name = _save_callback_name(serial)
    restore_name = _restore_callback_name(serial)
    if save_name not in _REGISTERED_SAVE_CALLBACKS:
        _colab_output.register_callback(save_name, _make_save_callback(serial))
        _REGISTERED_SAVE_CALLBACKS.add(save_name)
    if restore_name not in _REGISTERED_RESTORE_CALLBACKS:
        _colab_output.register_callback(restore_name, _make_restore_callback(serial))
        _REGISTERED_RESTORE_CALLBACKS.add(restore_name)
    return save_name, restore_name


# ---------------------------------------------------------------------------
# Catálogo liviano. Nunca descarga el .ipynb salvo modo="completo" explícito.
# ---------------------------------------------------------------------------
_FRONTEND_CATALOG_JS = r'''
(async () => {
  const PREFIX = "__PREFIX__";
  const MANIFEST = "__MANIFEST__";
  const CATALOG = "__CATALOG__";
  function windows() {
    const out = [];
    for (const candidate of [window, window.parent, window.top]) {
      try { if (candidate && !out.includes(candidate)) out.push(candidate); } catch (_) {}
    }
    return out;
  }
  function identity() {
    try { return String(window.top.location.href).replace(/[?#].*$/, ""); }
    catch (_) { return String(location.href).replace(/[?#].*$/, ""); }
  }
  const rows = new Map();
  function add(serial, revision, bytes, source) {
    serial = String(serial || "").replace(/[^A-Za-z0-9_]+/g, "_") || "board";
    revision = Number(revision || 0) || 0;
    bytes = Number(bytes || 0) || 0;
    const old = rows.get(serial);
    if (!old || revision >= old.revision) rows.set(serial, {serial, revision, bytes_png_aprox: bytes, source});
  }
  for (const w of windows()) {
    try {
      const raw = w.localStorage.getItem(CATALOG + ":" + identity());
      if (raw) {
        const list = JSON.parse(raw);
        for (const item of Array.isArray(list) ? list : []) add(item.serial, item.revision, item.bytes_png_aprox, "browser_cache");
      }
    } catch (_) {}
    try {
      const manifests = w.document.querySelectorAll('[id="' + MANIFEST + '"]');
      for (const node of manifests) {
        const raw = node.getAttribute("data-amc-board-manifest") || "[]";
        const list = JSON.parse(raw);
        for (const item of Array.isArray(list) ? list : []) add(item.serial, item.revision, item.bytes_png_aprox, "mounted_manifest");
      }
    } catch (_) {}
    try {
      const images = w.document.querySelectorAll('img[id^="' + PREFIX + '"]');
      for (const image of images) {
        const src = image.getAttribute("src") || "";
        if (!src.startsWith("data:image/png;base64,")) continue;
        const serial = image.id.slice(PREFIX.length);
        const revision = Number(image.getAttribute("data-amc-revision") || 0) || 0;
        const bytes = Math.floor(Math.max(0, src.length - "data:image/png;base64,".length) * 3 / 4);
        add(serial, revision, bytes, "mounted_carrier");
      }
    } catch (_) {}
  }
  return JSON.stringify([...rows.values()]);
})()
'''


def _browser_catalog() -> List[Dict[str, Any]]:
    global _LAST_DISCOVERY_ERROR
    try:
        _require_colab()
        evaluator = getattr(_colab_output, "eval_js", None)
        if evaluator is None:
            return []
        script = (
            _FRONTEND_CATALOG_JS
            .replace("__PREFIX__", _CARRIER_PREFIX)
            .replace("__MANIFEST__", _MANIFEST_ID)
            .replace("__CATALOG__", _CACHE_CATALOG_KEY)
        )
        raw = evaluator(script)
        rows = json.loads(raw) if isinstance(raw, str) else raw
        normalized: List[Dict[str, Any]] = []
        for item in rows if isinstance(rows, list) else []:
            if not isinstance(item, dict):
                continue
            normalized.append({
                "serial": _sanitize_serial(item.get("serial")),
                "revision": max(0, int(item.get("revision", 0) or 0)),
                "bytes_png": max(0, int(item.get("bytes_png_aprox", 0) or 0)),
                "source": str(item.get("source", "browser")),
            })
        _LAST_DISCOVERY_ERROR = None
        return normalized
    except Exception as exc:
        _LAST_DISCOVERY_ERROR = repr(exc)
        return []


def recargar_boards_desde_notebook(
    conservar_runtime: bool = True,
    modo: str = "rapido",
) -> List[Dict[str, Any]]:
    """Actualiza catálogo. modo='rapido' no lee get_ipynb; 'completo' sí."""
    global _LAST_DISCOVERY_SOURCE
    mode = str(modo or "rapido").strip().lower()
    if mode in {"completo", "compatibilidad", "ipynb", "legacy"}:
        nb = _read_notebook_json()
        candidates = _extract_all_boards_from_notebook(nb)
        notebook_json.clear()
        if not conservar_runtime:
            _RECORDS.clear()
        for candidate in candidates:
            _remember_record(
                candidate["serial"], candidate["data_url"], candidate.get("revision", 0),
                source="ipynb_catalog", allow_equal_replace=True,
            )
        _LAST_DISCOVERY_SOURCE = "ipynb"
        return boards_guardados

    for item in _browser_catalog():
        serial = item["serial"]
        current = _RECORDS.get(serial)
        if current is None:
            _RECORDS[serial] = {
                "serial": serial,
                "png_b64": "",
                "bytes_png": item["bytes_png"],
                "sha256": "",
                "revision": item["revision"],
                "updated_at": 0.0,
                "source": item["source"],
                "session_sequences": {},
            }
        elif int(item["revision"]) > int(current.get("revision", 0) or 0) and not current.get("png_b64"):
            current["revision"] = int(item["revision"])
            current["bytes_png"] = int(item["bytes_png"])
            current["source"] = item["source"]
    _sync_public_records()
    _LAST_DISCOVERY_SOURCE = "browser"
    return boards_guardados


def listar_boards(incluir_base64: bool = False, recargar: bool = False, modo: str = "rapido") -> List[Dict[str, Any]]:
    if recargar:
        recargar_boards_desde_notebook(modo=modo)
    return [_public_record(item, include_base64=incluir_base64) for item in _RECORDS.values()]


def get_boards(incluir_base64: bool = False, recargar: bool = True, modo: str = "rapido") -> List[Dict[str, Any]]:
    if recargar:
        recargar_boards_desde_notebook(modo=modo)
    return listar_boards(incluir_base64=incluir_base64, recargar=False)


def diagnostico_boards() -> Dict[str, Any]:
    return {
        "version": _VERSION,
        "boards_runtime": [
            _public_record(record, include_base64=False) for record in _RECORDS.values()
        ],
        "ultima_fuente_catalogo": _LAST_DISCOVERY_SOURCE,
        "ultimo_error_catalogo": _LAST_DISCOVERY_ERROR,
        "carrier_handles_runtime": sorted(_CARRIER_HANDLES.keys()),
        "estrategia": "IndexedDB -> carrier montado -> .ipynb asíncrono",
        "conflictos": "revisión base + secuencia por instancia + SHA-256",
    }


# ---------------------------------------------------------------------------
# Interfaz y cliente JavaScript. Un único script autocontenido por instancia.
# ---------------------------------------------------------------------------
def _board_html(serial: str, instance_id: str, save_callback: str, restore_callback: str, seed_revision: int) -> str:
    root_id = f"amc_board_root_{serial}_{instance_id}"
    canvas_id = f"amc_board_canvas_{serial}_{instance_id}"
    state_id = f"amc_board_state_{serial}_{instance_id}"

    template = r'''
<div id="__ROOT_ID__" class="amc-board-root" data-amc-instance="__INSTANCE__">
  <style>
    #__ROOT_ID__ { margin:0; padding:0; background:#f8fafc; color:#0f172a; font-family:Inter,system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif; }
    #__ROOT_ID__ * { box-sizing:border-box; }
    #__ROOT_ID__ .amc-head { display:flex; align-items:center; gap:9px; flex-wrap:wrap; padding:10px 12px 0; font-size:12px; color:#475569; }
    #__ROOT_ID__ .amc-head strong { color:#0f172a; }
    #__ROOT_ID__ .amc-state { display:inline-flex; align-items:center; padding:4px 8px; border-radius:999px; background:#e2e8f0; color:#334155; font-weight:600; }
    #__ROOT_ID__ .amc-state[data-mode="saving"] { background:#fef3c7; color:#92400e; }
    #__ROOT_ID__ .amc-state[data-mode="saved"] { background:#dcfce7; color:#166534; }
    #__ROOT_ID__ .amc-state[data-mode="error"] { background:#fee2e2; color:#991b1b; }
    #__ROOT_ID__ .amc-toolbar { display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin:10px 12px; }
    #__ROOT_ID__ button { padding:8px 11px; border:1px solid #cbd5e1; border-radius:10px; background:#fff; color:#0f172a; cursor:pointer; font-weight:650; transition:transform .12s ease, background .12s ease; }
    #__ROOT_ID__ button:hover { transform:translateY(-1px); background:#f1f5f9; }
    #__ROOT_ID__ button:focus-visible { outline:3px solid #93c5fd; outline-offset:2px; }
    #__ROOT_ID__ label { display:flex; align-items:center; gap:5px; font-size:12px; color:#334155; }
    #__ROOT_ID__ input[type="color"] { width:38px; height:34px; padding:2px; border:1px solid #cbd5e1; border-radius:8px; background:#fff; }
    #__ROOT_ID__ input[type="range"] { accent-color:#0f766e; }
    #__ROOT_ID__ canvas { width:calc(100% - 24px); height:460px; margin:0 12px 16px; display:block; touch-action:none; cursor:crosshair; background:#fff; border:1px solid #cbd5e1; border-radius:12px; box-shadow:0 10px 28px rgba(15,23,42,.10); }
    @media (max-width:680px) { #__ROOT_ID__ canvas { height:360px; } }
  </style>
  <div class="amc-head">Board: <strong>__SERIAL__</strong><span id="__STATE_ID__" class="amc-state" data-mode="idle">Preparando board…</span></div>
  <div class="amc-toolbar">
    <button type="button" data-action="pen">✏️ Lápiz</button>
    <button type="button" data-action="eraser">🧹 Borrador</button>
    <label>Color <input data-role="color" type="color" value="#0f172a"></label>
    <label>Grosor <input data-role="size" type="range" min="1" max="50" value="8"></label>
    <button type="button" data-action="undo">↩️ Undo</button>
    <button type="button" data-action="redo">↪️ Redo</button>
    <button type="button" data-action="clear">🗑️ Limpiar</button>
    <button type="button" data-action="save">💾 Guardar ahora</button>
    <button type="button" data-action="download">⬇️ Descargar PNG</button>
  </div>
  <canvas id="__CANVAS_ID__"></canvas>
</div>
<script>
(() => {
  "use strict";
  const ROOT_ID = __ROOT_ID_JSON__;
  const CANVAS_ID = __CANVAS_ID_JSON__;
  const STATE_ID = __STATE_ID_JSON__;
  const SERIAL = __SERIAL_JSON__;
  const INSTANCE = __INSTANCE_JSON__;
  const SAVE_CALLBACK = __SAVE_CALLBACK_JSON__;
  const RESTORE_CALLBACK = __RESTORE_CALLBACK_JSON__;
  const SEED_REVISION = __SEED_REVISION__;
  const PREFIX = __PREFIX_JSON__;
  const DB_NAME = __DB_NAME_JSON__;
  const STORE = __STORE_JSON__;
  const CATALOG_KEY = __CATALOG_JSON__;
  const MAX_HISTORY = 28;

  const root = document.getElementById(ROOT_ID);
  const canvas = document.getElementById(CANVAS_ID);
  const stateEl = document.getElementById(STATE_ID);
  if (!root || !canvas || !stateEl || root.dataset.amcReady === "1") return;
  root.dataset.amcReady = "1";
  const ctx = canvas.getContext("2d", {willReadFrequently:false});
  const colorEl = root.querySelector('[data-role="color"]');
  const sizeEl = root.querySelector('[data-role="size"]');
  if (!ctx || !colorEl || !sizeEl) return;

  let dpr = Math.max(1, window.devicePixelRatio || 1);
  let tool = "pen";
  let drawing = false;
  let active = false;
  let userTouched = false;
  let hydrated = false;
  let restorationStarted = false;
  let knownRevision = Math.max(0, Number(SEED_REVISION) || 0);
  let clientSequence = 0;
  let lastPoint = {x:0, y:0};
  let pending = null;
  let pumping = false;
  let saveTimer = null;
  let statusLockedByConflict = false;
  const undoStack = [];
  const redoStack = [];

  function setState(text, mode="idle") {
    if (statusLockedByConflict && mode !== "error") return;
    stateEl.textContent = text;
    stateEl.dataset.mode = mode;
  }
  function responseData(answer) {
    return answer && answer.data && typeof answer.data === "object" ? answer.data : (answer || {});
  }
  function kernelAvailable() {
    return !!(window.google && google.colab && google.colab.kernel && typeof google.colab.kernel.invokeFunction === "function");
  }
  function notebookIdentity() {
    try { return String(window.top.location.href).replace(/[?#].*$/, ""); }
    catch (_) { return String(location.href).replace(/[?#].*$/, ""); }
  }
  function cacheKey() { return notebookIdentity() + "::" + SERIAL; }
  function initCanvas(w, h) {
    canvas.width = Math.max(1, Math.round(w));
    canvas.height = Math.max(1, Math.round(h));
    ctx.globalCompositeOperation = "source-over";
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
  }
  function layout() { initCanvas(canvas.clientWidth * dpr, canvas.clientHeight * dpr); }
  function resizeKeepPixels() {
    if (!canvas.width || !canvas.height) return;
    const old = document.createElement("canvas");
    old.width = canvas.width; old.height = canvas.height;
    old.getContext("2d").drawImage(canvas, 0, 0);
    dpr = Math.max(1, window.devicePixelRatio || 1);
    initCanvas(canvas.clientWidth * dpr, canvas.clientHeight * dpr);
    ctx.drawImage(old, 0, 0, old.width, old.height, 0, 0, canvas.width, canvas.height);
  }
  function dataUrl() { try { return canvas.toDataURL("image/png"); } catch (_) { return ""; } }
  function point(event) {
    const rect = canvas.getBoundingClientRect();
    return {x:(event.clientX - rect.left) * dpr, y:(event.clientY - rect.top) * dpr};
  }
  function stroke(a, b) {
    ctx.save();
    ctx.globalCompositeOperation = "source-over";
    ctx.strokeStyle = tool === "eraser" ? "#ffffff" : colorEl.value;
    ctx.lineWidth = Math.max(1, Number(sizeEl.value) || 1) * dpr;
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    ctx.restore();
  }
  function pushHistory(snapshot) {
    const value = snapshot || dataUrl();
    if (!value) return;
    undoStack.push(value);
    while (undoStack.length > MAX_HISTORY) undoStack.shift();
    redoStack.length = 0;
  }
  function dataUrlToBlob(value) {
    if (typeof value !== "string" || !value.startsWith("data:image/png;base64,")) return Promise.resolve(null);
    try {
      const binary = atob(value.slice("data:image/png;base64,".length));
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      return Promise.resolve(new Blob([bytes], {type:"image/png"}));
    } catch (_) { return Promise.resolve(null); }
  }
  function paintBlob(blob) {
    if (!blob) return Promise.resolve(false);
    return new Promise((resolve) => {
      const url = URL.createObjectURL(blob);
      const image = new Image();
      image.onload = () => {
        try {
          ctx.save();
          ctx.globalCompositeOperation = "source-over";
          ctx.fillStyle = "#ffffff";
          ctx.fillRect(0, 0, canvas.width, canvas.height);
          ctx.drawImage(image, 0, 0, image.naturalWidth || canvas.width, image.naturalHeight || canvas.height, 0, 0, canvas.width, canvas.height);
          ctx.restore();
          URL.revokeObjectURL(url);
          resolve(true);
        } catch (_) { URL.revokeObjectURL(url); resolve(false); }
      };
      image.onerror = () => { URL.revokeObjectURL(url); resolve(false); };
      image.src = url;
    });
  }

  // ---------------- IndexedDB: cache local binario ----------------
  function openDb() {
    return new Promise((resolve, reject) => {
      if (!window.indexedDB) { reject(new Error("IndexedDB no disponible")); return; }
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, {keyPath:"key"});
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error || new Error("No se pudo abrir IndexedDB"));
    });
  }
  async function readCache() {
    try {
      const db = await openDb();
      return await new Promise((resolve, reject) => {
        const tx = db.transaction(STORE, "readonly");
        const req = tx.objectStore(STORE).get(cacheKey());
        req.onsuccess = () => resolve(req.result || null);
        req.onerror = () => reject(req.error);
      });
    } catch (_) { return null; }
  }
  function writeCatalog(revision, bytes) {
    try {
      const key = CATALOG_KEY + ":" + notebookIdentity();
      const old = JSON.parse(localStorage.getItem(key) || "[]");
      const rows = Array.isArray(old) ? old.filter(x => String(x && x.serial || "") !== SERIAL) : [];
      rows.push({serial:SERIAL, revision:Number(revision)||0, bytes_png_aprox:Number(bytes)||0, updated_at:Date.now()});
      rows.sort((a,b) => String(a.serial).localeCompare(String(b.serial)));
      localStorage.setItem(key, JSON.stringify(rows.slice(-240)));
    } catch (_) {}
  }
  async function writeCache(blob, revision, dirty) {
    if (!blob) return false;
    try {
      const db = await openDb();
      const key = cacheKey();
      const written = await new Promise((resolve, reject) => {
        const tx = db.transaction(STORE, "readwrite");
        const store = tx.objectStore(STORE);
        const get = store.get(key);
        get.onsuccess = () => {
          const old = get.result;
          const oldRevision = Number(old && old.revision || 0) || 0;
          // Nunca dejar que una recuperación antigua borre una edición local no sincronizada.
          if (old && old.dirty && !dirty && oldRevision >= Number(revision || 0)) { resolve(false); return; }
          if (old && oldRevision > Number(revision || 0) && !dirty) { resolve(false); return; }
          const value = {key, serial:SERIAL, revision:Number(revision)||0, blob, dirty:!!dirty, updated_at:Date.now()};
          store.put(value);
          resolve(true);
        };
        get.onerror = () => reject(get.error);
      });
      if (written) writeCatalog(revision, blob.size || 0);
      return written;
    } catch (_) { return false; }
  }
  async function cacheDataUrl(value, revision, dirty) {
    const blob = await dataUrlToBlob(value);
    return writeCache(blob, revision, dirty);
  }

  // ---------------- Restauración dirigida, sin escanear todo el DOM ----------------
  function directDocuments() {
    const docs = [document];
    // El acceso a parent/top puede lanzar si Colab cambia el aislamiento del
    // iframe. Se consulta dentro de try, nunca al construir un array literal.
    for (const candidateWindow of [window.parent, window.top]) {
      try {
        const candidate = candidateWindow && candidateWindow.document;
        if (candidate && !docs.includes(candidate)) docs.push(candidate);
      } catch (_) {}
    }
    // Colab suele aislar outputs en iframes. Sólo consultamos el id exacto en
    // cada iframe, sin recorrer sus nodos ni shadow roots.
    for (const parentDoc of docs.slice()) {
      try {
        const frames = Array.from(parentDoc.querySelectorAll("iframe")).slice(0, 160);
        for (const frame of frames) {
          try { if (frame.contentDocument && !docs.includes(frame.contentDocument)) docs.push(frame.contentDocument); } catch (_) {}
        }
      } catch (_) {}
    }
    return docs;
  }
  function mountedCarrier() {
    const exactId = PREFIX + SERIAL;
    let best = null;
    for (const doc of directDocuments()) {
      try {
        const nodes = doc.querySelectorAll('img[id="' + exactId + '"]');
        for (const node of nodes) {
          const src = node.getAttribute("src") || "";
          if (!src.startsWith("data:image/png;base64,")) continue;
          const revision = Number(node.getAttribute("data-amc-revision") || 0) || 0;
          if (!best || revision >= best.revision) best = {data_url:src, revision};
        }
      } catch (_) {}
    }
    return best;
  }
  async function restoreFromBrowser() {
    const cached = await readCache();
    if (cached && cached.blob) {
      knownRevision = Math.max(knownRevision, Number(cached.revision || 0) || 0);
      if (await paintBlob(cached.blob)) {
        hydrated = true; pushHistory(dataUrl());
        setState(cached.dirty ? "✓ Copia local pendiente de sincronizar" : "✓ Board restaurado localmente", cached.dirty ? "saving" : "saved");
        return true;
      }
    }
    const mounted = mountedCarrier();
    if (mounted) {
      const blob = await dataUrlToBlob(mounted.data_url);
      if (blob && await paintBlob(blob)) {
        knownRevision = Math.max(knownRevision, Number(mounted.revision || 0) || 0);
        hydrated = true; pushHistory(dataUrl());
        writeCache(blob, knownRevision, false).catch(() => {});
        setState("✓ Board restaurado desde el notebook", "saved");
        return true;
      }
    }
    return false;
  }
  async function restoreFromKernelIfNeeded() {
    if (restorationStarted || userTouched || hydrated) return;
    if (!kernelAvailable()) { setState("Sin runtime: se conserva la copia local si existe", "error"); return; }
    restorationStarted = true;
    setState("Buscando respaldo portátil…", "saving");
    try {
      const answer = await google.colab.kernel.invokeFunction(RESTORE_CALLBACK, [], {});
      const result = responseData(answer);
      if (userTouched || hydrated) return;
      if (!result || !result.ok || !result.data_url) {
        setState("Listo para dibujar", "idle");
        return;
      }
      const blob = await dataUrlToBlob(result.data_url);
      if (!blob || userTouched || hydrated) return;
      if (!await paintBlob(blob) || userTouched) return;
      knownRevision = Math.max(knownRevision, Number(result.revision || 0) || 0);
      hydrated = true; pushHistory(dataUrl());
      await writeCache(blob, knownRevision, false);
      setState("✓ Board recuperado automáticamente", "saved");
    } catch (error) {
      if (!userTouched) setState("Listo para dibujar (respaldo no disponible aún)", "idle");
      console.warn("AutoMind Board restore:", error);
    }
  }

  // ---------------- Cola de persistencia: una escritura a la vez ----------------
  function enqueueSave(reason, force=false) {
    clearTimeout(saveTimer);
    const snapshot = dataUrl();
    if (!snapshot) { setState("No se pudo crear el PNG", "error"); return; }
    // Primero proteger la edición local. Incluso si se cae el runtime, el
    // mismo navegador no pierde el trazo ya terminado.
    cacheDataUrl(snapshot, knownRevision, true).catch(() => {});
    pending = {snapshot, reason:String(reason || "change"), force:!!force};
    if (!pumping) void pumpSaveQueue();
  }
  function debounceSave(reason) {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => enqueueSave(reason, false), 180);
  }
  async function pumpSaveQueue() {
    if (pumping) return;
    pumping = true;
    try {
      while (pending) {
        const item = pending;
        pending = null;
        if (!kernelAvailable()) {
          setState("Copia local guardada; runtime desconectado", "error");
          continue;
        }
        const sequence = ++clientSequence;
        setState("Guardando respaldo del notebook…", "saving");
        let result;
        try {
          const answer = await google.colab.kernel.invokeFunction(
            SAVE_CALLBACK,
            [item.snapshot, knownRevision, sequence, INSTANCE, item.reason],
            {}
          );
          result = responseData(answer);
        } catch (error) {
          console.warn("AutoMind Board save:", error);
          setState("Copia local guardada; no se confirmó el runtime", "error");
          continue;
        }
        if (result && result.ok) {
          knownRevision = Math.max(knownRevision, Number(result.revision || 0) || 0);
          await cacheDataUrl(item.snapshot, knownRevision, false);
          statusLockedByConflict = false;
          setState("✓ Guardado en notebook · r" + knownRevision, "saved");
          continue;
        }
        if (result && result.conflict) {
          knownRevision = Math.max(knownRevision, Number(result.revision || 0) || 0);
          // La copia local queda marcada dirty: no se oculta el conflicto ni se
          // permite que el servidor nuevo sea reemplazado silenciosamente.
          await cacheDataUrl(item.snapshot, knownRevision, true);
          statusLockedByConflict = true;
          setState("Conflicto: tu copia local se preservó; no sobrescribió r" + knownRevision, "error");
          pending = null;
          continue;
        }
        setState((result && result.error) || "No se pudo confirmar el guardado", "error");
      }
    } finally {
      pumping = false;
      if (pending) void pumpSaveQueue();
    }
  }

  // ---------------- Edición ----------------
  function finishStroke(event) {
    if (!drawing) return;
    try {
      if (event && Number.isFinite(event.clientX) && Number.isFinite(event.clientY)) {
        const p = point(event); stroke(lastPoint, p); lastPoint = p;
      }
    } catch (_) {}
    drawing = false;
    try { if (event && canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId); } catch (_) {}
    enqueueSave("stroke", true);
  }
  async function restoreHistory(snapshot) {
    const blob = await dataUrlToBlob(snapshot);
    if (blob && await paintBlob(blob)) enqueueSave("history", true);
  }
  function undo() {
    if (!undoStack.length) return;
    const current = dataUrl(); const previous = undoStack.pop();
    if (current) redoStack.push(current);
    void restoreHistory(previous);
  }
  function redo() {
    if (!redoStack.length) return;
    const current = dataUrl(); const next = redoStack.pop();
    if (current) undoStack.push(current);
    void restoreHistory(next);
  }

  canvas.addEventListener("pointerdown", (event) => {
    active = true; userTouched = true; statusLockedByConflict = false;
    pushHistory(); drawing = true;
    try { canvas.setPointerCapture(event.pointerId); } catch (_) {}
    lastPoint = point(event); stroke(lastPoint, lastPoint);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!drawing) return;
    const p = point(event); stroke(lastPoint, p); lastPoint = p;
  });
  canvas.addEventListener("pointerup", finishStroke);
  canvas.addEventListener("pointercancel", finishStroke);
  canvas.addEventListener("pointerleave", (event) => { if (drawing && event.buttons === 0) finishStroke(event); });

  root.querySelector('[data-action="pen"]').addEventListener("click", () => { tool = "pen"; active = true; });
  root.querySelector('[data-action="eraser"]').addEventListener("click", () => { tool = "eraser"; active = true; });
  root.querySelector('[data-action="clear"]').addEventListener("click", () => {
    active = true; userTouched = true; statusLockedByConflict = false; pushHistory();
    ctx.save(); ctx.globalCompositeOperation = "source-over"; ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, canvas.width, canvas.height); ctx.restore();
    enqueueSave("clear", true);
  });
  root.querySelector('[data-action="undo"]').addEventListener("click", () => { active = true; userTouched = true; statusLockedByConflict = false; undo(); });
  root.querySelector('[data-action="redo"]').addEventListener("click", () => { active = true; userTouched = true; statusLockedByConflict = false; redo(); });
  root.querySelector('[data-action="save"]').addEventListener("click", () => { active = true; enqueueSave("manual", true); });
  root.querySelector('[data-action="download"]').addEventListener("click", () => {
    try {
      const link = document.createElement("a");
      link.href = dataUrl(); link.download = "pizarra_" + SERIAL + ".png";
      document.body.appendChild(link); link.click(); link.remove();
    } catch (_) { setState("No se pudo descargar el PNG", "error"); }
  });
  window.addEventListener("keydown", (event) => {
    if (!active || !(event.ctrlKey || event.metaKey) || String(event.key).toLowerCase() !== "z") return;
    event.preventDefault();
    if (event.shiftKey) redo(); else undo();
  });
  window.addEventListener("resize", resizeKeepPixels);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") enqueueSave("visibility", true);
  });
  window.addEventListener("pagehide", () => enqueueSave("pagehide", true));
  window.addEventListener("beforeunload", () => enqueueSave("beforeunload", true));
  window.addEventListener("blur", () => { if (drawing || pending) debounceSave("blur"); });

  // Inicialización en dos fases: primero canvas listo; luego cache local; y
  // finalmente fallback portátil asíncrono. Nunca bloquea board("alpha").
  setTimeout(async () => {
    layout();
    const restored = await restoreFromBrowser();
    if (!restored) {
      pushHistory();
      setState("Recuperando si existe un respaldo…", "saving");
      setTimeout(() => { void restoreFromKernelIfNeeded(); }, 220);
    }
  }, 0);
})();
</script>
'''
    replacements = {
        "__ROOT_ID__": root_id,
        "__CANVAS_ID__": canvas_id,
        "__STATE_ID__": state_id,
        "__SERIAL__": _html.escape(serial),
        "__INSTANCE__": _html.escape(instance_id),
        "__ROOT_ID_JSON__": json.dumps(root_id),
        "__CANVAS_ID_JSON__": json.dumps(canvas_id),
        "__STATE_ID_JSON__": json.dumps(state_id),
        "__SERIAL_JSON__": json.dumps(serial),
        "__INSTANCE_JSON__": json.dumps(instance_id),
        "__SAVE_CALLBACK_JSON__": json.dumps(save_callback),
        "__RESTORE_CALLBACK_JSON__": json.dumps(restore_callback),
        "__SEED_REVISION__": str(max(0, int(seed_revision or 0))),
        "__PREFIX_JSON__": json.dumps(_CARRIER_PREFIX),
        "__DB_NAME_JSON__": json.dumps(_CACHE_DB_NAME),
        "__STORE_JSON__": json.dumps(_CACHE_STORE),
        "__CATALOG_JSON__": json.dumps(_CACHE_CATALOG_KEY),
    }
    for old, new in replacements.items():
        template = template.replace(old, new)
    return template


# ---------------------------------------------------------------------------
# API principal
# ---------------------------------------------------------------------------
def board(serial: str = "board") -> None:
    """Abre, recupera y deja editable un board con un único comando.

    La celda no descarga el notebook completo: el canvas aparece de inmediato.
    La recuperación portátil ocurre automáticamente sólo si no existe IndexedDB
    ni un carrier ya montado.
    """
    _require_colab()
    serial = _sanitize_serial(serial)
    save_callback, restore_callback = _ensure_callbacks(serial)
    record = _find_record(serial)
    revision = int((record or {}).get("revision", 0) or 0)
    instance_id = uuid.uuid4().hex

    # La pizarra visible se crea primero. El carrier vacío separado no puede
    # ganar una restauración porque el cliente ignora src que no sea data PNG.
    display(HTML(_board_html(serial, instance_id, save_callback, restore_callback, revision)))
    _ensure_carrier_handle(serial)


__all__ = [
    "board",
    "get_boards",
    "listar_boards",
    "recargar_boards_desde_notebook",
    "diagnostico_boards",
    "boards_guardados",
    "notebook_json",
]
