# MJCF_Render_Script_DEPTH_ORDER_FIX_NO_IA.py
# Puente Google Colab / Jupyter <-> AutoMind MJCF Viewer modular.
#
# Correcciones incluidas:
#   1) Lee correctamente compiler meshdir/texturedir.
#   2) Indexa OBJ, MTL y texturas con rutas Windows/CAD, rutas relativas y basename.
#   3) Lee map_Kd de los MTL y crea texture/material MJCF equivalentes cuando
#      el XML no los declara.
#   4) Aplica el material MTL generado a los <geom mesh="..."> visuales,
#      reemplazando materiales MJCF negros/planos cuando corresponde.
#   5) Elimina del viewer los geoms de colisión duplicados que tapan los visuales.
#   6) Reporta las texturas faltantes en vez de ocultar silenciosamente el problema.
#   7) Hornea los mapas map_Kd a colores por vértice mediante UV para el viewport.
#      Evita el bug de Colab donde CanvasTexture funciona en thumbnails, pero se
#      vuelve negra solo en el framebuffer visible.
#
# Uso típico en Google Colab:
#   from MJCF_Render_Script import MJCF_Render, MJCF_Visualization
#   MJCF_Render("Mi_Robot_MJCF")
#   MJCF_Visualization("Mi_Robot_MJCF", debug=True)
#
# También acepta un ZIP que contenga un MJCF .xml y sus recursos:
#   MJCF_Render("/content/Mi_Robot_MJCF.zip")

from __future__ import annotations

import base64
import hashlib
import html as html_lib
import json
import os
import re
import shlex
import shutil
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote

import requests
from IPython.display import HTML


_VIEWER_REPO_DEFAULT = "artemioadaysolvers/AutoMind-USD-URDF-Loader"
_VIEWER_BRANCH_DEFAULT = "main"
_VIEWER_ENTRY_DEFAULT = "MJCF_Viewer/mjcf_viewer_main.js"

# Pixel blanco seguro para una textura declarada en el XML, pero ausente del ZIP.
# Se usa solo si placeholder_missing_textures=True.
_WHITE_PIXEL_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
    "AAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)

# Formatos que este puente entrega al assetDB. El navegador/Three decide cuáles
# puede decodificar realmente; PNG/JPG/WebP son los recomendados.
_SUPPORTED_ASSET_EXTENSIONS = {
    ".obj", ".mtl",
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg",
    ".tga", ".dds", ".ktx", ".ktx2",
}

_IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg",
    ".tga", ".dds", ".ktx", ".ktx2",
}


@dataclass
class MaterialInjectionReport:
    """Resultado de convertir referencias MTL en materiales MJCF explícitos."""

    generated_textures: int = 0
    generated_materials: int = 0
    geoms_assigned: int = 0
    geoms_overridden: int = 0
    meshes_with_multiple_mtls: list[str] = field(default_factory=list)
    mtl_files_read: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = [
            f"texturas MJCF generadas: {self.generated_textures}",
            f"materiales MJCF generados: {self.generated_materials}",
            f"geoms asociados: {self.geoms_assigned}",
            f"materiales MJCF sustituidos: {self.geoms_overridden}",
        ]
        if self.meshes_with_multiple_mtls:
            parts.append(f"OBJ con múltiples materiales: {len(self.meshes_with_multiple_mtls)}")
        if self.warnings:
            parts.append(f"advertencias: {len(self.warnings)}")
        return "; ".join(parts)


def _safe_extract_zip(zip_path: str, destination: str) -> None:
    """Extrae ZIP sin permitir rutas que escapen la carpeta destino."""
    destination_path = Path(destination).resolve()
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            target = (destination_path / member.filename).resolve()
            if target != destination_path and destination_path not in target.parents:
                raise ValueError(f"ZIP contiene una ruta insegura: {member.filename}")
        archive.extractall(destination)


def Unzip_MJCF(zip_path: str, output_folder: str | None = None) -> str:
    """Descomprime un ZIP MJCF local y devuelve la carpeta extraída."""
    if not os.path.isfile(zip_path):
        raise FileNotFoundError(f"No existe el ZIP: {zip_path}")

    if output_folder is None:
        stem = os.path.splitext(os.path.basename(zip_path))[0]
        output_folder = os.path.join(os.path.dirname(zip_path) or "/content", stem)

    if os.path.exists(output_folder):
        shutil.rmtree(output_folder)

    os.makedirs(output_folder, exist_ok=True)
    _safe_extract_zip(zip_path, output_folder)
    return output_folder


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as file:
        return file.read().lstrip("\ufeff")


def _looks_like_mjcf(xml_text: str) -> bool:
    return bool(re.search(r"<\s*mujoco(?:\s|>)", xml_text or "", flags=re.IGNORECASE))


def _find_mjcf_file(folder_path: str) -> str | None:
    """Encuentra el XML cuyo documento contiene una raíz MJCF <mujoco>."""
    candidates: list[tuple[int, int, str]] = []

    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__MACOSX"]
        for filename in files:
            if not filename.lower().endswith(".xml"):
                continue

            path = os.path.join(root, filename)
            try:
                text = _read_text(path)
            except OSError:
                continue

            if not _looks_like_mjcf(text):
                continue

            name_l = filename.lower()
            path_l = path.replace("\\", "/").lower()
            score = 0
            if re.search(r"(^|[_\-.])(model|robot|mjcf)([_\-.]|$)", name_l):
                score += 100
            if "/assets/" in path_l:
                score -= 500
            if "<worldbody" in text.lower():
                score += 30
            if "<asset" in text.lower():
                score += 10

            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0
            candidates.append((score, size, path))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (-item[0], -item[1], item[2].lower()))
    return candidates[0][2]


def _clean_asset_ref(value: str) -> str:
    """Normaliza rutas procedentes de MJCF, OBJ, MTL, Windows o CAD."""
    path = unquote(str(value or "").strip().strip('"').strip("'"))
    path = path.replace("\\", "/")
    path = re.sub(r"^file:/+", "", path, flags=re.IGNORECASE)
    path = re.sub(r"^package:/+", "", path, flags=re.IGNORECASE)
    path = re.sub(r"^\./+", "", path)
    while "//" in path:
        path = path.replace("//", "/")
    return path.lstrip("/")


def _asset_key_variants(path: str) -> list[str]:
    """Genera aliases robustos para resolver rutas de assets exportados por CAD."""
    raw = _clean_asset_ref(path)
    if not raw:
        return []

    parts = [part for part in raw.split("/") if part and part != "."]
    base = os.path.basename(raw)
    output: set[str] = set()

    def add(value: str) -> None:
        value = _clean_asset_ref(value)
        if not value:
            return
        output.add(value)
        output.add(value.lower())
        output.add("./" + value)
        output.add("./" + value.lower())

    add(raw)
    add(base)

    for index in range(len(parts)):
        add("/".join(parts[index:]))

    if base:
        stem, extension = os.path.splitext(base)
        variants = {
            base.replace("%20", " "),
            base.replace(" ", "_"),
            base.replace("_", " "),
            stem.replace(" ", "_") + extension,
            stem.replace("_", " ") + extension,
            re.sub(r"[\s_\-]+", "", stem) + extension,
        }
        for variant in variants:
            add(variant)

    return sorted(output)


def _extract_mjcf_texture_refs(mjcf_text: str) -> list[str]:
    """Obtiene atributos file de <texture ...> para detectar archivos ausentes."""
    refs = re.findall(
        r"<\s*texture\b[^>]*\bfile\s*=\s*['\"]([^'\"]+)['\"]",
        mjcf_text or "",
        flags=re.IGNORECASE,
    )
    seen: set[str] = set()
    result: list[str] = []
    for ref in refs:
        clean = _clean_asset_ref(ref)
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            result.append(clean)
    return result


def _extract_mjcf_asset_dirs(mjcf_text: str) -> tuple[str, str]:
    """Lee compiler meshdir/texturedir. Esta versión corrige el regex anterior."""
    compiler_match = re.search(
        r"<\s*compiler\b(?P<attrs>[^>]*)>", mjcf_text or "", flags=re.IGNORECASE
    )
    attrs = compiler_match.group("attrs") if compiler_match else ""

    def attr(name: str) -> str:
        # Importante: solo una pareja de llaves aquí. Las dobles buscaban el texto
        # literal '{re.escape(name)}' y anulaban meshdir/texturedir.
        match = re.search(
            rf"\b{re.escape(name)}\s*=\s*['\"]([^'\"]+)['\"]",
            attrs,
            flags=re.IGNORECASE,
        )
        return _clean_asset_ref(match.group(1)) if match else ""

    meshdir = attr("meshdir") or "assets"
    texturedir = attr("texturedir") or meshdir
    return meshdir, texturedir


def _local_file_index(folder_path: str, mjcf_path: str) -> tuple[dict[str, str], dict[str, str]]:
    """Devuelve aliases -> path físico para todos los archivos relevantes."""
    root_abs = os.path.abspath(folder_path)
    xml_dir_abs = os.path.dirname(os.path.abspath(mjcf_path))
    aliases: dict[str, str] = {}
    exact_relatives: dict[str, str] = {}

    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__MACOSX"]
        for filename in files:
            path = os.path.abspath(os.path.join(root, filename))
            for base_dir in (root_abs, xml_dir_abs):
                try:
                    relative = os.path.relpath(path, base_dir).replace("\\", "/")
                except ValueError:
                    continue
                exact_relatives.setdefault(_clean_asset_ref(relative).lower(), path)
                for variant in _asset_key_variants(relative):
                    aliases.setdefault(variant.lower(), path)
            for variant in _asset_key_variants(filename):
                aliases.setdefault(variant.lower(), path)

    return aliases, exact_relatives


def _resolve_local_asset(
    reference: str,
    search_roots: Iterable[str],
    alias_index: dict[str, str],
    exact_relatives: dict[str, str],
) -> str | None:
    """Resuelve una referencia de asset contra el disco y contra aliases tolerantes."""
    raw = str(reference or "").strip().strip('"').strip("'")
    clean = _clean_asset_ref(raw)
    if not clean:
        return None

    candidates = [raw.replace("\\", os.sep), clean.replace("/", os.sep)]
    for root in search_roots:
        if not root:
            continue
        for candidate in candidates:
            full = os.path.abspath(os.path.join(root, candidate))
            if os.path.isfile(full):
                return full

    for key in _asset_key_variants(clean):
        found = alias_index.get(key.lower()) or exact_relatives.get(key.lower())
        if found and os.path.isfile(found):
            return found
    return None


def _collect_mjcf_asset_db(
    folder_path: str,
    mjcf_path: str,
    mjcf_text: str,
    *,
    placeholder_missing_textures: bool = True,
) -> tuple[dict[str, str], list[str]]:
    """Construye el assetDB base64 y detecta texturas MJCF no localizadas."""
    root_abs = os.path.abspath(folder_path)
    xml_dir_abs = os.path.dirname(os.path.abspath(mjcf_path))
    asset_db: dict[str, str] = {}
    cache: dict[str, str] = {}

    def encode_file(path: str) -> str:
        if path not in cache:
            with open(path, "rb") as file:
                cache[path] = base64.b64encode(file.read()).decode("ascii")
        return cache[path]

    def add_entry(key: str, encoded: str) -> None:
        for variant in _asset_key_variants(key):
            asset_db.setdefault(variant, encoded)

    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__MACOSX"]
        for filename in files:
            extension = os.path.splitext(filename)[1].lower()
            if extension not in _SUPPORTED_ASSET_EXTENSIONS:
                continue

            absolute_path = os.path.abspath(os.path.join(root, filename))
            try:
                encoded = encode_file(absolute_path)
            except OSError:
                continue

            for base_dir in (root_abs, xml_dir_abs):
                try:
                    relative = os.path.relpath(absolute_path, base_dir).replace("\\", "/")
                    add_entry(relative, encoded)
                except ValueError:
                    pass
            add_entry(filename, encoded)

    meshdir, texturedir = _extract_mjcf_asset_dirs(mjcf_text)
    missing_textures: list[str] = []
    for texture_ref in _extract_mjcf_texture_refs(mjcf_text):
        variants = _asset_key_variants(texture_ref)
        if any(key in asset_db for key in variants):
            continue

        missing_textures.append(texture_ref)
        if placeholder_missing_textures:
            for candidate in (
                texture_ref,
                f"assets/{texture_ref}",
                f"{meshdir.rstrip('/')}/{texture_ref}",
                f"{texturedir.rstrip('/')}/{texture_ref}",
            ):
                add_entry(candidate, _WHITE_PIXEL_PNG_B64)

    return asset_db, missing_textures


def _parse_obj_material_usage(obj_path: str) -> tuple[list[str], list[str]]:
    """Extrae mtllib y usemtl de un OBJ sin depender de una librería externa."""
    mtllibs: list[str] = []
    used_materials: list[str] = []
    seen_mtl: set[str] = set()
    seen_used: set[str] = set()

    try:
        text = _read_text(obj_path)
    except OSError:
        return mtllibs, used_materials

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        lower = line.lower()
        if lower.startswith("mtllib "):
            tail = line[7:].strip()
            try:
                names = shlex.split(tail, posix=True)
            except ValueError:
                names = [tail]
            # Algunos exportadores escriben un único path con espacios sin comillas.
            if not names:
                names = [tail]
            for name in names:
                clean = _clean_asset_ref(name)
                if clean and clean.lower() not in seen_mtl:
                    seen_mtl.add(clean.lower())
                    mtllibs.append(clean)
        elif lower.startswith("usemtl "):
            name = line[7:].strip()
            if name and name.lower() not in seen_used:
                seen_used.add(name.lower())
                used_materials.append(name)

    return mtllibs, used_materials


def _parse_float(value: str, fallback: float = 1.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _extract_mtl_map_path(value: str) -> str:
    """Elimina las opciones MTL habituales y devuelve el path de un mapa."""
    value = str(value or "").strip()
    if not value:
        return ""
    try:
        tokens = shlex.split(value, posix=True)
    except ValueError:
        tokens = value.split()
    if not tokens:
        return ""

    # Aridad de las opciones MTL que suelen anteceder al nombre de archivo.
    option_arity = {
        "-blendu": 1, "-blendv": 1, "-boost": 1, "-mm": 2,
        "-o": 3, "-s": 3, "-t": 3, "-texres": 1, "-clamp": 1,
        "-bm": 1, "-imfchan": 1, "-type": 1, "-cc": 1,
    }
    index = 0
    while index < len(tokens) and tokens[index].startswith("-"):
        option = tokens[index].lower()
        index += 1 + option_arity.get(option, 1)
    if index >= len(tokens):
        # Fallback: la última palabra sigue siendo preferible a descartar todo.
        return _clean_asset_ref(tokens[-1])
    return _clean_asset_ref(" ".join(tokens[index:]))


def _parse_mtl_file(mtl_path: str) -> dict[str, dict[str, Any]]:
    """Lee Kd, d/Tr y mapas de un archivo MTL."""
    materials: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None

    try:
        text = _read_text(mtl_path)
    except OSError:
        return materials

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        command = parts[0].lower()
        value = parts[1].strip() if len(parts) > 1 else ""

        if command == "newmtl":
            if not value:
                current = None
                continue
            current = {
                "name": value,
                "kd": (1.0, 1.0, 1.0),
                "alpha": 1.0,
                "map_kd": "",
                "map_d": "",
                "normal_map": "",
            }
            materials[value] = current
            continue

        if current is None:
            continue

        if command == "kd":
            values = value.split()
            if len(values) >= 3:
                current["kd"] = (
                    _parse_float(values[0]),
                    _parse_float(values[1]),
                    _parse_float(values[2]),
                )
        elif command == "d":
            current["alpha"] = max(0.0, min(1.0, _parse_float(value, 1.0)))
        elif command == "tr":
            current["alpha"] = max(0.0, min(1.0, 1.0 - _parse_float(value, 0.0)))
        elif command == "map_kd":
            current["map_kd"] = _extract_mtl_map_path(value)
        elif command == "map_d":
            current["map_d"] = _extract_mtl_map_path(value)
        elif command in {"bump", "map_bump", "norm", "map_norm", "normal"}:
            current["normal_map"] = _extract_mtl_map_path(value)

    return materials


def _safe_mjcf_name(prefix: str, *parts: str) -> str:
    original = "|".join(str(item or "") for item in parts)
    readable = re.sub(r"[^A-Za-z0-9_]+", "_", "_".join(parts)).strip("_")
    if not readable:
        readable = "asset"
    if not re.match(r"^[A-Za-z_]", readable):
        readable = "n_" + readable
    digest = hashlib.sha1(original.encode("utf-8", errors="ignore")).hexdigest()[:10]
    return f"{prefix}_{readable[:46]}_{digest}"


def _format_rgba(kd: tuple[float, float, float], alpha: float) -> str:
    values = [max(0.0, min(1.0, float(v))) for v in (*kd, alpha)]
    return " ".join(f"{value:.6g}" for value in values)


def _parse_xml_preserving_mjcf(mjcf_text: str) -> ET.Element:
    """Parsea XML estándar MJCF y entrega un error legible cuando no es posible."""
    cleaned = mjcf_text.lstrip("\ufeff")
    # ElementTree no maneja bien ciertos DOCTYPE externos, innecesarios para MJCF.
    cleaned = re.sub(r"<!DOCTYPE[^>]*(?:\[[\s\S]*?\]\s*)?>", "", cleaned, flags=re.IGNORECASE)
    return ET.fromstring(cleaned)


def _ensure_asset_node(root: ET.Element) -> ET.Element:
    asset = root.find("asset")
    if asset is not None:
        return asset

    asset = ET.Element("asset")
    children = list(root)
    insert_index = 0
    # Conserva un orden compatible: compiler/option/size antes de asset, worldbody después.
    for index, child in enumerate(children):
        if child.tag in {"compiler", "option", "size", "visual", "statistic", "default"}:
            insert_index = index + 1
        elif child.tag == "worldbody":
            break
    root.insert(insert_index, asset)
    return asset



@dataclass
class CollisionVisualFilterReport:
    """Resumen de geoms de colisión retirados del DOM que ve el viewer."""

    removed_geoms: int = 0
    names: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if not self.removed_geoms:
            return "sin geoms de colisión explícitos retirados"
        return f"geoms de colisión retirados del viewer: {self.removed_geoms}"


def _xml_local_tag(node: ET.Element) -> str:
    return str(node.tag or "").split("}")[-1].lower()


def _is_collision_geom_node(node: ET.Element) -> bool:
    """Detecta una geometría física que no debe cubrir la visual en Three.js."""
    if _xml_local_tag(node) != "geom":
        return False

    class_name = str(node.get("class") or "").strip().lower()
    name = str(node.get("name") or "").strip().lower()
    group_raw = str(node.get("group") or "").strip()

    # Exportadores CAD habituales: class="collision", "collider" o nombres
    # prefijados. No se infiere por contype/conaffinity porque muchos visuales
    # también los incluyen legítimamente.
    class_tokens = [token for token in re.split(r"[\s,;:_\-.]+", class_name) if token]
    if any(token in {"collision", "collider", "colision"} for token in class_tokens):
        return True
    if re.search(r"(?:^|[_:./\-])colli(?:sion|der|de)(?:$|[_:./\-])", name):
        return True

    try:
        # group=3 es el grupo de colisión típico de este exportador. Se elimina
        # solo cuando además la geom no declara un material visual propio.
        group = int(float(group_raw)) if group_raw else None
    except (TypeError, ValueError):
        group = None
    if group == 3 and not str(node.get("material") or "").strip():
        return True

    return False


def _strip_collision_geoms_for_viewer(mjcf_text: str) -> tuple[str, CollisionVisualFilterReport]:
    """
    Quita geoms de colisión del XML entregado al viewer, sin modificar el ZIP.

    MuJoCo sí entiende defaults/class y colisiones; este visor es visual. Cuando
    el exportador incluye una copia visual y una copia class="collision" con el
    mismo mesh, la copia física sin material queda encima y se ve negra.
    """
    report = CollisionVisualFilterReport()
    try:
        root = _parse_xml_preserving_mjcf(mjcf_text)
    except Exception as error:
        report.warnings.append(f"No se pudo filtrar colisiones del XML: {error}")
        return mjcf_text, report

    for parent in list(root.iter()):
        for node in list(parent):
            if not _is_collision_geom_node(node):
                continue
            name = str(node.get("name") or node.get("mesh") or "geom_sin_nombre")
            report.names.append(name)
            parent.remove(node)
            report.removed_geoms += 1

    if not report.removed_geoms:
        return mjcf_text, report

    return ET.tostring(root, encoding="utf-8", short_empty_elements=True).decode("utf-8"), report


def _inject_mtl_materials_into_mjcf(
    mjcf_text: str,
    folder_path: str,
    mjcf_path: str,
    *,
    force_mtl_on_visual_geoms: bool = True,
) -> tuple[str, MaterialInjectionReport]:
    """
    Traduce map_Kd de MTL a <texture>/<material> MJCF y lo asocia a geoms.

    Por defecto, sí sustituye el material explícito de una geom visual cuando
    existe un map_Kd válido en su OBJ/MTL. Esto es deliberado: muchos
    exportadores CAD dejan un material MJCF negro plano en la geom y el
    material con textura queda solamente dentro del MTL.

    Cuando un OBJ usa múltiples usemtl, no puede representarse con un solo
    material de geom sin dividir el mesh: se elige el primero y se deja aviso.
    """
    report = MaterialInjectionReport()
    try:
        root = _parse_xml_preserving_mjcf(mjcf_text)
    except Exception as error:
        report.warnings.append(f"No se pudo parsear MJCF para importar MTL: {error}")
        return mjcf_text, report

    asset = _ensure_asset_node(root)
    xml_dir = os.path.dirname(os.path.abspath(mjcf_path))
    folder_abs = os.path.abspath(folder_path)
    meshdir, texturedir = _extract_mjcf_asset_dirs(mjcf_text)
    alias_index, exact_relatives = _local_file_index(folder_path, mjcf_path)

    existing_texture_names = {
        str(node.get("name") or "").strip()
        for node in asset.findall("texture")
        if str(node.get("name") or "").strip()
    }
    existing_material_names = {
        str(node.get("name") or "").strip()
        for node in asset.findall("material")
        if str(node.get("name") or "").strip()
    }

    mesh_nodes: dict[str, ET.Element] = {}
    for node in asset.findall("mesh"):
        name = str(node.get("name") or "").strip()
        file_ref = str(node.get("file") or "").strip()
        if name and file_ref:
            mesh_nodes[name] = node

    generated_by_mesh: dict[str, str] = {}

    for mesh_name, mesh_node in mesh_nodes.items():
        mesh_ref = str(mesh_node.get("file") or "")
        mesh_search_roots = [
            xml_dir,
            folder_abs,
            os.path.join(xml_dir, meshdir),
            os.path.join(folder_abs, meshdir),
        ]
        obj_path = _resolve_local_asset(mesh_ref, mesh_search_roots, alias_index, exact_relatives)
        if not obj_path or os.path.splitext(obj_path)[1].lower() != ".obj":
            continue

        mtllibs, used_materials = _parse_obj_material_usage(obj_path)
        if not mtllibs:
            continue

        parsed_materials: dict[str, dict[str, Any]] = {}
        for mtl_ref in mtllibs:
            mtl_path = _resolve_local_asset(
                mtl_ref,
                [os.path.dirname(obj_path), xml_dir, folder_abs, os.path.join(folder_abs, meshdir)],
                alias_index,
                exact_relatives,
            )
            if not mtl_path:
                report.warnings.append(
                    f"No encontré MTL '{mtl_ref}' declarado por OBJ '{os.path.basename(obj_path)}'."
                )
                continue
            report.mtl_files_read.append(mtl_path)
            parsed_materials.update(_parse_mtl_file(mtl_path))

        if not parsed_materials:
            continue

        preferred_mtl_name = ""
        for name in used_materials:
            if name in parsed_materials:
                preferred_mtl_name = name
                break
        if not preferred_mtl_name:
            preferred_mtl_name = next(iter(parsed_materials.keys()))

        matching_used = [name for name in used_materials if name in parsed_materials]
        if len(matching_used) > 1:
            report.meshes_with_multiple_mtls.append(mesh_name)
            report.warnings.append(
                f"Mesh '{mesh_name}' contiene varios usemtl ({', '.join(matching_used[:5])}). "
                f"Se aplica '{preferred_mtl_name}' al geom completo; para conservar materiales por submesh "
                "hay que separar el OBJ o usar soporte MTL dentro del viewer."
            )

        mtl = parsed_materials[preferred_mtl_name]
        map_kd = _clean_asset_ref(str(mtl.get("map_kd") or ""))
        kd = tuple(mtl.get("kd") or (1.0, 1.0, 1.0))
        alpha = float(mtl.get("alpha", 1.0))

        generated_material_name = _safe_mjcf_name("automind_mtl", mesh_name, preferred_mtl_name)
        if generated_material_name in existing_material_names:
            generated_by_mesh[mesh_name] = generated_material_name
            continue

        material_attrs = {
            "name": generated_material_name,
            "rgba": _format_rgba((float(kd[0]), float(kd[1]), float(kd[2])), alpha),
        }

        if map_kd:
            texture_name = _safe_mjcf_name("automind_tex", mesh_name, preferred_mtl_name, map_kd)
            if texture_name not in existing_texture_names:
                texture_attrs = {"name": texture_name, "type": "2d", "file": map_kd}
                ET.SubElement(asset, "texture", texture_attrs)
                existing_texture_names.add(texture_name)
                report.generated_textures += 1
            material_attrs["texture"] = texture_name

            # Se verifica temprano y se reporta; assetDB añadirá fallback opcional después.
            texture_path = _resolve_local_asset(
                map_kd,
                [
                    os.path.dirname(report.mtl_files_read[-1]) if report.mtl_files_read else "",
                    os.path.dirname(obj_path), xml_dir, folder_abs,
                    os.path.join(xml_dir, texturedir), os.path.join(folder_abs, texturedir),
                ],
                alias_index,
                exact_relatives,
            )
            if not texture_path:
                report.warnings.append(
                    f"No encontré textura map_Kd '{map_kd}' de material '{preferred_mtl_name}' en mesh '{mesh_name}'."
                )

        ET.SubElement(asset, "material", material_attrs)
        existing_material_names.add(generated_material_name)
        generated_by_mesh[mesh_name] = generated_material_name
        report.generated_materials += 1

    if not generated_by_mesh:
        return mjcf_text, report

    # Aplicar el material derivado de MTL a cada geom visual que usa el mesh.
    #
    # El caso que corrige esta rama es exactamente el de los exportadores CAD
    # que ya escriben material="visual_..." en la geom, pero ese material
    # MJCF solo contiene rgba negro o carece de texture. La versión previa no
    # lo sobrescribía, generaba 20 materiales nuevos y los dejaba sin uso
    # (geoms_assigned=0), por lo que el robot seguía negro.
    for geom in root.iter("geom"):
        mesh_name = str(geom.get("mesh") or "").strip()
        current_material = str(geom.get("material") or "").strip()
        generated = generated_by_mesh.get(mesh_name)
        if not generated or _is_collision_geom_node(geom):
            continue

        # Una geom sin material siempre recibe el material que proviene del MTL.
        # Con force_mtl_on_visual_geoms=True (valor recomendado y por defecto),
        # también se reemplaza el material plano del XML.
        should_apply = (not current_material) or bool(force_mtl_on_visual_geoms)
        if not should_apply:
            continue

        if current_material and current_material != generated:
            report.geoms_overridden += 1
        if current_material != generated:
            geom.set("material", generated)
            report.geoms_assigned += 1

    if report.generated_materials and not report.geoms_assigned:
        report.warnings.append(
            "Se generaron materiales MTL pero no se pudo asociar ninguno a un geom visual. "
            "Revisa que los atributos geom mesh=\"...\" coincidan con asset/mesh name=\"...\"."
        )

    xml_bytes = ET.tostring(root, encoding="utf-8", short_empty_elements=True)
    xml_result = xml_bytes.decode("utf-8")
    return xml_result, report


def _esc_js_template(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("${", "\\${")
        .replace("</script>", "<\\/script>")
    )


def _html_error(title: str, detail: str) -> HTML:
    return HTML(
        "<div style='font-family:Inter,Arial,sans-serif;border:1px solid #f3b3b3;"
        "background:#fff5f5;color:#7a1111;border-radius:12px;padding:14px;line-height:1.45'>"
        f"<b>{html_lib.escape(title)}</b>"
        "<pre style='white-space:pre-wrap;margin:10px 0 0;color:#7a1111;background:#fff;"
        "border:1px solid #ffd0d0;border-radius:10px;padding:10px'>"
        f"{html_lib.escape(detail)}"
        "</pre></div>"
    )


def _resolve_latest_commit(repo: str, branch: str = "main", timeout: int = 25) -> dict[str, str]:
    """Devuelve SHA actual para fijar una versión inmutable del viewer en jsDelivr."""
    repo = str(repo or "").strip().strip("/")
    branch = str(branch or "main").strip()
    if not repo or "/" not in repo:
        raise ValueError("repo debe usar formato 'usuario/repositorio'.")

    api_url = f"https://api.github.com/repos/{repo}/commits/{branch}"
    response = requests.get(
        api_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "AutoMind-MJCF-Render-Script",
        },
        timeout=timeout,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"No pude resolver el último commit de {repo}@{branch}. "
            f"HTTP {response.status_code}: {response.text[:500]}"
        )

    data = response.json()
    sha = str(data.get("sha") or "")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        raise RuntimeError(f"GitHub devolvió un SHA inválido: {sha!r}")

    commit = data.get("commit") or {}
    message = str(commit.get("message") or "").splitlines()[0].strip()
    return {
        "repo": repo,
        "branch": branch,
        "sha": sha,
        "short_sha": sha[:7],
        "message": message,
        "html_url": str(data.get("html_url") or f"https://github.com/{repo}/commit/{sha}"),
    }


def _build_jsdelivr_url(repo: str, sha: str, component_file: str) -> str:
    component_file = str(component_file or "").strip().replace("\\", "/").lstrip("/")
    if not component_file:
        raise ValueError("compFile está vacío.")
    return f"https://cdn.jsdelivr.net/gh/{repo}@{sha}/{component_file}"


def _runtime_script_dir() -> str:
    """Devuelve una carpeta estable aunque el código se ejecute pegado en Colab.

    En una celda de Colab/Jupyter ``__file__`` no existe. Por eso nunca debe
    usarse directamente para localizar el ZIP local del viewer.
    """
    source_file = globals().get("__file__")
    if isinstance(source_file, str) and source_file.strip():
        try:
            return os.path.dirname(os.path.abspath(source_file))
        except Exception:
            pass
    return os.getcwd()


def _viewer_zip_candidates(explicit_zip: str | None = None) -> list[str]:
    """Busca el bundle local del viewer, sin requerir GitHub ni jsDelivr."""
    here = _runtime_script_dir()
    cwd = os.getcwd()
    colab_root = "/content"
    raw = [
        explicit_zip or "",
        os.path.join(cwd, "MJCF_Viewer_Mecanismo_DEPTH_ORDER_FIX.zip"),
        os.path.join(cwd, "MJCF_Viewer_Mecanismo_TEXTURE_MAP_FIX.zip"),
        os.path.join(cwd, "MJCF_Viewer_Mecanismo_TEXTURE_FIX.zip"),
        os.path.join(cwd, "MJCF_Viewer_Mecanismo_Arreglado.zip"),
        os.path.join(here, "MJCF_Viewer_Mecanismo_DEPTH_ORDER_FIX.zip"),
        os.path.join(here, "MJCF_Viewer_Mecanismo_TEXTURE_MAP_FIX.zip"),
        os.path.join(here, "MJCF_Viewer_Mecanismo_TEXTURE_FIX.zip"),
        os.path.join(here, "MJCF_Viewer_Mecanismo_Arreglado.zip"),
        os.path.join(colab_root, "MJCF_Viewer_Mecanismo_DEPTH_ORDER_FIX.zip"),
        os.path.join(colab_root, "MJCF_Viewer_Mecanismo_TEXTURE_MAP_FIX.zip"),
        os.path.join(colab_root, "MJCF_Viewer_Mecanismo_TEXTURE_FIX.zip"),
        os.path.join(colab_root, "MJCF_Viewer_Mecanismo_Arreglado.zip"),
    ]
    out: list[str] = []
    seen: set[str] = set()
    for value in raw:
        if not value:
            continue
        path = os.path.abspath(os.path.expanduser(str(value)))
        if path.lower().endswith(".zip") and os.path.isfile(path) and path not in seen:
            out.append(path)
            seen.add(path)
    return out


def _find_viewer_root(folder: str, comp_file: str) -> str | None:
    """Encuentra la carpeta que contiene MJCF_Viewer/mjcf_viewer_main.js."""
    folder_abs = os.path.abspath(folder)
    normalized = str(comp_file or _VIEWER_ENTRY_DEFAULT).replace("\\", "/").lstrip("/")
    direct = os.path.join(folder_abs, normalized)
    if os.path.isfile(direct):
        return folder_abs
    for root, dirs, files in os.walk(folder_abs):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__MACOSX"]
        candidate = os.path.join(root, normalized)
        if os.path.isfile(candidate):
            return root
    return None


def _local_viewer_data_url(viewer_zip: str, component_file: str) -> tuple[str, dict[str, str]]:
    """
    Convierte el viewer modular local a un entrypoint data: URL.

    Los módulos internos se reescriben recursivamente con URLs data: para que
    import() funcione dentro del iframe de Colab sin publicar ni subir nada a
    GitHub. Esto garantiza que el ZIP entregado sea el viewer que realmente se
    está ejecutando.
    """
    zip_abs = os.path.abspath(viewer_zip)
    if not os.path.isfile(zip_abs):
        raise FileNotFoundError(f"No existe el ZIP local del viewer: {viewer_zip}")

    digest = hashlib.sha256(Path(zip_abs).read_bytes()).hexdigest()
    cache_dir = os.path.join("/tmp", f"automind_mjcf_viewer_{digest[:16]}")
    if not os.path.isdir(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)
        _safe_extract_zip(zip_abs, cache_dir)

    root = _find_viewer_root(cache_dir, component_file)
    if not root:
        raise RuntimeError(
            "El ZIP local no contiene el entrypoint modular esperado.\n"
            f"Se esperaba: {component_file}"
        )

    root_path = Path(root).resolve()
    entry_path = (root_path / component_file.replace("\\", "/")).resolve()
    if not entry_path.is_file() or root_path not in entry_path.parents:
        raise RuntimeError(f"Entry local inválido: {entry_path}")

    module_cache: dict[Path, str] = {}
    visiting: set[Path] = set()
    import_pattern = re.compile(
        r"(?P<prefix>\bfrom\s*['\"]|\bimport\s*['\"])(?P<spec>\.[^'\"]+)(?P<suffix>['\"])",
        flags=re.MULTILINE,
    )

    def build_module(path: Path) -> str:
        path = path.resolve()
        if path in module_cache:
            return module_cache[path]
        if path in visiting:
            raise RuntimeError(f"Import circular no soportado en bundle local: {path.name}")
        if not path.is_file() or (path != root_path and root_path not in path.parents):
            raise RuntimeError(f"Import local inválido: {path}")
        visiting.add(path)
        source = path.read_text(encoding="utf-8", errors="ignore").lstrip("\\ufeff")

        def replace_import(match: re.Match[str]) -> str:
            spec = match.group("spec")
            target = (path.parent / spec).resolve()
            if target.suffix.lower() != ".js":
                target = target.with_suffix(".js")
            target_url = build_module(target)
            return match.group("prefix") + target_url + match.group("suffix")

        source = import_pattern.sub(replace_import, source)
        data_url = "data:text/javascript;base64," + base64.b64encode(source.encode("utf-8")).decode("ascii")
        module_cache[path] = data_url
        visiting.remove(path)
        return data_url

    entry_url = build_module(entry_path)
    return entry_url, {
        "source": "local-zip",
        "sha": digest,
        "short_sha": "local-" + digest[:7],
        "html_url": "file://" + zip_abs.replace("\\", "/"),
        "entry": component_file,
    }


def _probe_modular_viewer_entry(url: str, component_file: str, timeout: int = 35) -> dict[str, Any]:
    """Comprueba que el entrypoint exista y no sea un HTML standalone."""
    response = requests.get(
        url,
        headers={"User-Agent": "AutoMind-MJCF-Render-Script"},
        timeout=timeout,
    )
    if response.status_code != 200:
        raise RuntimeError(
            "No encontré el viewer modular MJCF en el último commit.\n"
            f"HTTP {response.status_code}: {url}\n\n"
            f"Ruta compFile usada: {component_file}\n"
            "Debe ser: MJCF_Viewer/mjcf_viewer_main.js"
        )

    sample = (response.text or "")[:8192]
    stripped = sample.lstrip().lower()
    if stripped.startswith("<!doctype") or stripped.startswith("<html"):
        raise RuntimeError(
            "La ruta compFile está devolviendo HTML, no un módulo JavaScript.\n\n"
            f"compFile: {component_file}\nURL: {url}"
        )
    if "export" not in sample or "render" not in sample:
        raise RuntimeError(
            "El entrypoint no parece exportar render(opts).\n\n"
            f"compFile: {component_file}\nURL: {url}"
        )
    return {
        "ok": True,
        "content_type": response.headers.get("content-type", ""),
        "bytes_sampled": len(sample),
    }



def MJCF_Visualization(
    folder_path: str = "MJCFModel",
    select_mode: str = "link",
    background: int | None = 0xFFFFFF,
    repo: str = _VIEWER_REPO_DEFAULT,
    branch: str = _VIEWER_BRANCH_DEFAULT,
    compFile: str = _VIEWER_ENTRY_DEFAULT,
    timeout: int = 35,
    debug: bool = False,
    auto_import_mtl_textures: bool = True,
    force_mtl_on_visual_geoms: bool = True,
    hide_collision_geoms: bool = True,
    placeholder_missing_textures: bool = True,
    viewer_zip: str | None = None,
    viewer_source: str = "auto",
    force_visible_materials: bool = True,
    force_direct_mtl_maps: bool = True,
    viewport_texture_proxy: bool = True,
    vertex_color_texture_bake: bool = True,
) -> HTML:
    """
    Renderiza el AutoMind MJCF Viewer modular en Google Colab o Jupyter.

    auto_import_mtl_textures=True convierte map_Kd de los MTL en materiales MJCF.
    force_direct_mtl_maps=True conserva el bitmap map_Kd como map de Three.js
    con color blanco, evitando que un Kd=0 0 0 multiplique la textura a negro.

    force_mtl_on_visual_geoms=True (recomendado) hace que el material generado
    desde MTL sustituya el material plano/negro que el exportador ya hubiera
    puesto en las geoms visuales. Desactívalo solo si el XML MJCF ya tiene sus
    propias texturas correctas y quieres conservarlas.

    hide_collision_geoms=True retira del XML que recibe el viewer las copias
    class="collision". El archivo dentro del ZIP no se cambia: esta medida solo
    evita que una malla física negra tape exactamente a su copia visual.

    viewer_zip permite ejecutar el ZIP local entregado junto con este script.
    En modo viewer_source="auto" se usa el ZIP local cuando está disponible;
    así ninguna corrección queda ignorada por la versión antigua de GitHub.

    viewport_texture_proxy=True activa una capa visual para el canvas principal.
    vertex_color_texture_bake=True (recomendado) convierte cada mapa decodificado
    en colores RGB por vértice usando UV. Así el viewer no depende de que
    Chromium/Colab muestree CanvasTexture en el framebuffer visible. Los meshes
    originales permanecen activos para cinemática, selección y arrastre.
    """
    if folder_path.lower().endswith(".zip") and os.path.isfile(folder_path):
        folder_path = Unzip_MJCF(folder_path)
    if not os.path.isdir(folder_path):
        return _html_error("Carpeta MJCF no encontrada", f"No existe: {folder_path}")

    mjcf_path = _find_mjcf_file(folder_path)
    if not mjcf_path:
        return _html_error(
            "No se encontró un MJCF válido",
            "No encontré un .xml con raíz <mujoco> dentro de:\n" + folder_path,
        )

    try:
        mjcf_raw = _read_text(mjcf_path)
    except Exception as error:
        return _html_error("No pude leer el XML MJCF", str(error))
    if not _looks_like_mjcf(mjcf_raw):
        return _html_error("El XML encontrado no es MJCF", "La raíz debe contener <mujoco>.")

    collision_report = CollisionVisualFilterReport()
    if hide_collision_geoms:
        try:
            mjcf_raw, collision_report = _strip_collision_geoms_for_viewer(mjcf_raw)
        except Exception as error:
            collision_report.warnings.append(f"Error no fatal filtrando colisiones: {error}")

    injection_report = MaterialInjectionReport()
    if auto_import_mtl_textures:
        try:
            mjcf_raw, injection_report = _inject_mtl_materials_into_mjcf(
                mjcf_raw, folder_path, mjcf_path,
                force_mtl_on_visual_geoms=force_mtl_on_visual_geoms,
            )
        except Exception as error:
            injection_report.warnings.append(f"Error no fatal importando MTL: {error}")

    viewer_source = str(viewer_source or "auto").strip().lower()
    if viewer_source not in {"auto", "local", "remote"}:
        return _html_error("viewer_source inválido", "Usa 'auto', 'local' o 'remote'.")

    try:
        local_candidates = _viewer_zip_candidates(viewer_zip)
        use_local = viewer_source == "local" or (viewer_source == "auto" and bool(local_candidates))
        if use_local:
            if not local_candidates:
                raise FileNotFoundError(
                    "No encontré el ZIP local del viewer. Pasa viewer_zip='/content/MJCF_Viewer_Mecanismo_DEPTH_ORDER_FIX.zip'."
                )
            viewer_url, commit = _local_viewer_data_url(local_candidates[0], compFile)
        else:
            commit = _resolve_latest_commit(repo=repo, branch=branch, timeout=timeout)
            viewer_url = _build_jsdelivr_url(commit["repo"], commit["sha"], compFile)
            _probe_modular_viewer_entry(viewer_url, component_file=compFile, timeout=timeout)
    except Exception as error:
        return _html_error("Error cargando el sistema modular AutoMind MJCF", str(error))

    try:
        asset_db, missing_textures = _collect_mjcf_asset_db(
            folder_path,
            mjcf_path,
            mjcf_raw,
            placeholder_missing_textures=placeholder_missing_textures,
        )
    except Exception as error:
        return _html_error("Error preparando OBJ, MTL y texturas", str(error))

    relative_xml_path = os.path.relpath(mjcf_path, folder_path).replace("\\", "/")
    mjcf_js = _esc_js_template(mjcf_raw)
    asset_js = json.dumps(asset_db, ensure_ascii=False, separators=(",", ":"))
    background_value = 0xFFFFFF if background is None else int(background)
    background_js = "null" if background is None else str(background_value)
    background_css_hex = f"{background_value & 0xFFFFFF:06x}"
    select_mode_js = json.dumps(select_mode)
    debug_js = "true" if debug else "false"
    force_visible_js = "true" if force_visible_materials else "false"
    force_direct_mtl_js = "true" if force_direct_mtl_maps else "false"
    viewport_proxy_js = "true" if viewport_texture_proxy else "false"
    vertex_color_bake_js = "true" if vertex_color_texture_bake else "false"
    mjcf_path_js = json.dumps(relative_xml_path)
    viewer_url_js = json.dumps(viewer_url)
    commit_sha_js = json.dumps(commit["sha"])
    commit_short_js = json.dumps(commit["short_sha"])
    commit_url_js = json.dumps(commit["html_url"])
    comp_file_js = json.dumps(compFile)
    missing_textures_js = json.dumps(missing_textures, ensure_ascii=False)
    import_report_js = json.dumps(
        {
            "summary": injection_report.summary(),
            "generated_textures": injection_report.generated_textures,
            "generated_materials": injection_report.generated_materials,
            "geoms_assigned": injection_report.geoms_assigned,
            "geoms_overridden": injection_report.geoms_overridden,
            "multiple_mtl_meshes": injection_report.meshes_with_multiple_mtls,
            "warnings": injection_report.warnings,
        },
        ensure_ascii=False,
    )
    collision_report_js = json.dumps(
        {
            "summary": collision_report.summary(),
            "removed_geoms": collision_report.removed_geoms,
            "names": collision_report.names,
            "warnings": collision_report.warnings,
        },
        ensure_ascii=False,
    )

    html = fr"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover"/>
  <title>AutoMind MJCF Modular Viewer</title>
  <style>
    :root {{ --vh: 1vh; }}
    html, body {{ margin:0; padding:0; width:100%; height:100dvh; overflow:hidden; background:#{background_css_hex}; }}
    @supports not (height: 100dvh) {{ html, body {{ height:calc(var(--vh) * 100); }} }}
    body {{ padding-top:env(safe-area-inset-top); padding-right:env(safe-area-inset-right); padding-bottom:env(safe-area-inset-bottom); padding-left:env(safe-area-inset-left); }}
    #app {{ position:fixed; inset:0; width:100vw; height:100dvh; touch-action:none; }}
    @supports not (height: 100dvh) {{ #app {{ height:calc(var(--vh) * 100); }} }}
    #automind-error {{ display:none; position:fixed; inset:18px; z-index:999999; overflow:auto; box-sizing:border-box; background:#fff5f5; color:#7a1111; border:1px solid #f3b3b3; border-radius:12px; padding:16px; font:14px/1.45 Inter,Arial,sans-serif; white-space:pre-wrap; }}
    .badge {{ position:fixed; right:14px; bottom:10px; z-index:10; user-select:none; pointer-events:none; }}
    .badge img {{ max-height:40px; display:block; }}
  </style>
</head>
<body>
  <div id="app"></div>
  <pre id="automind-error"></pre>
  <div style="padding-left:20px; overflow:visible; position:fixed; right:0; bottom:0; z-index:999999;">
    <div class="badge" style="display:inline-block; transform:scale(2.5) translateX(-15px); transform-origin:bottom right; margin:0; overflow:visible; pointer-events:none;">
      <img src="https://raw.githubusercontent.com/artemioadaysolvers/AutoMindCloudExperimental/main/AutoMindCloud/AutoMindCloud2.png" alt="AutoMind" style="display:block; height:40px; width:auto;"/>
    </div>
  </div>

  <script defer src="https://cdn.jsdelivr.net/npm/three@0.132.2/build/three.min.js"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/three@0.132.2/examples/js/controls/OrbitControls.js"></script>

  <script type="module">
    const VIEWER_ENTRY_URL = {viewer_url_js};
    const VIEWER_COMMIT_SHA = {commit_sha_js};
    const VIEWER_COMMIT_SHORT_SHA = {commit_short_js};
    const VIEWER_COMMIT_URL = {commit_url_js};
    const VIEWER_COMP_FILE = {comp_file_js};
    const MISSING_TEXTURES = {missing_textures_js};
    const MTL_IMPORT_REPORT = {import_report_js};
    const COLLISION_FILTER_REPORT = {collision_report_js};

    window.AutoMindMJCFDebug = {debug_js};
    window.AutoMindMJCFForceVisibleMaterials = {force_visible_js};
    window.AutoMindMJCFForceDirectMTLMaps = {force_direct_mtl_js};
    window.AutoMindMJCFViewportTextureProxy = {viewport_proxy_js};
    window.AutoMindMJCFVertexColorTextureBake = {vertex_color_bake_js};

    function showError(error) {{
      const panel = document.getElementById('automind-error');
      const detail = error && (error.stack || error.message) ? (error.stack || error.message) : String(error);
      panel.textContent =
        'AutoMind MJCF Viewer no pudo iniciar.\n\n' +
        'Archivo del viewer: ' + VIEWER_COMP_FILE + '\n' +
        'Commit: ' + VIEWER_COMMIT_SHORT_SHA + '\n' +
        'URL: ' + VIEWER_ENTRY_URL + '\n\n' + detail;
      panel.style.display = 'block';
      console.error('[AutoMind MJCF]', error);
    }}

    const originalWarn = console.warn.bind(console);
    console.warn = (...args) => {{
      const message = String(args?.[0] || '');
      if (message.includes('THREE.WebGLRenderer: Texture marked for update but image is undefined')) return;
      originalWarn(...args);
    }};

    function installTextureSafetyPatch() {{
      if (!window.THREE || !THREE.WebGLRenderer || THREE.WebGLRenderer.__AutoMindTextureSafe) return;
      const slots = ['map', 'alphaMap', 'aoMap', 'bumpMap', 'normalMap', 'emissiveMap', 'roughnessMap', 'metalnessMap', 'specularMap', 'envMap', 'lightMap', 'displacementMap'];
      const originalRender = THREE.WebGLRenderer.prototype.render;
      THREE.WebGLRenderer.prototype.render = function(scene, camera) {{
        try {{
          scene?.traverse?.((object) => {{
            if (!object?.isMesh || !object.material) return;
            const materials = Array.isArray(object.material) ? object.material : [object.material];
            for (const material of materials) {{
              if (!material) continue;
              for (const slot of slots) {{
                const texture = material[slot];
                if (texture && texture.needsUpdate && !texture.image) texture.needsUpdate = false;
              }}
            }}
          }});
        }} catch (_ignore) {{}}
        return originalRender.call(this, scene, camera);
      }};
      THREE.WebGLRenderer.__AutoMindTextureSafe = true;
    }}

    for (let index = 0; index < 100 && !window.THREE; index++) {{
      await new Promise(resolve => setTimeout(resolve, 25));
    }}
    installTextureSafetyPatch();

    function applyViewportHeight() {{
      const height = window.visualViewport?.height || window.innerHeight || 600;
      document.documentElement.style.setProperty('--vh', `${{height * 0.01}}px`);
    }}

    function desiredHeight() {{
      const viewportHeight = window.visualViewport?.height || window.innerHeight || document.documentElement.clientHeight || 0;
      const scrollHeight = Math.max(document.documentElement?.scrollHeight || 0, document.body?.scrollHeight || 0);
      return Math.max(viewportHeight, scrollHeight, 600);
    }}

    function setColabFrameHeight() {{
      try {{
        const height = Math.ceil(desiredHeight());
        window.google?.colab?.output?.setIframeHeight?.(height, true);
      }} catch (_ignore) {{}}
    }}

    applyViewportHeight();
    const resizeObserver = new ResizeObserver(() => {{ applyViewportHeight(); setColabFrameHeight(); }});
    resizeObserver.observe(document.body);
    window.addEventListener('resize', () => {{ applyViewportHeight(); setColabFrameHeight(); }});
    window.visualViewport?.addEventListener('resize', () => {{ applyViewportHeight(); setColabFrameHeight(); }});

    async function importCdnModule(entryUrl) {{
      // Los módulos locales llegan como data: URL ya auto-contenida; agregar un
      // query string los invalida. Los módulos remotos mantienen cache-busting.
      const importUrl = /^data:/i.test(entryUrl)
        ? entryUrl
        : entryUrl + (entryUrl.includes('?') ? '&' : '?') + 'automind_sha=' + encodeURIComponent(VIEWER_COMMIT_SHA);
      try {{
        return await import(importUrl);
      }} catch (error) {{
        const detail = error && (error.stack || error.message) ? (error.stack || error.message) : String(error);
        throw new Error(
          'Falló import() del sistema modular.\n' +
          'Archivo: ' + VIEWER_COMP_FILE + '\n' +
          'URL: ' + importUrl + '\n\n' + detail
        );
      }}
    }}

    const opts = {{
      container: document.getElementById('app'),
      mjcfContent: `{mjcf_js}`,
      mjcfPath: {mjcf_path_js},
      assetDB: {asset_js},
      selectMode: {select_mode_js},
      background: {background_js},
      pixelRatio: Math.min(window.devicePixelRatio || 1, 2),
      autoResize: true,
      debug: {debug_js},
      commitSha: VIEWER_COMMIT_SHA,
      commitUrl: VIEWER_COMMIT_URL,
      viewportTextureProxy: window.AutoMindMJCFViewportTextureProxy !== false,
      vertexColorTextureBake: window.AutoMindMJCFVertexColorTextureBake !== false
    }};

    try {{
      if (COLLISION_FILTER_REPORT.removed_geoms || COLLISION_FILTER_REPORT.warnings.length) {{
        console.info('[AutoMind MJCF] Filtro visual de colisiones:', COLLISION_FILTER_REPORT.summary, COLLISION_FILTER_REPORT);
      }}
      if (MTL_IMPORT_REPORT.generated_materials || MTL_IMPORT_REPORT.warnings.length) {{
        console.info('[AutoMind MJCF] Importación MTL:', MTL_IMPORT_REPORT.summary, MTL_IMPORT_REPORT);
      }}
      if (MISSING_TEXTURES.length) {{
        console.warn('[AutoMind MJCF] Texturas MJCF ausentes; se usó fallback blanco si está habilitado:', MISSING_TEXTURES);
      }}

      const module = await importCdnModule(VIEWER_ENTRY_URL);
      if (!module || typeof module.render !== 'function') {{
        throw new Error('El módulo cargó, pero no exporta render(opts).');
      }}

      const app = module.render(opts);
      if (app?.ready && typeof app.ready.then === 'function') await app.ready;
      if (window.AutoMindMJCFViewportTextureProxyReport) {{
        console.info('[AutoMind MJCF] Diagnóstico viewport-texture:', window.AutoMindMJCFViewportTextureProxyReport);
      }}

      function onResize() {{
        try {{
          if (!app || typeof app.resize !== 'function') return;
          const width = window.innerWidth || document.documentElement.clientWidth || document.body.clientWidth || 800;
          app.resize(width, desiredHeight(), Math.min(window.devicePixelRatio || 1, 2));
        }} catch (_ignore) {{}}
      }}

      window.addEventListener('resize', onResize);
      window.visualViewport?.addEventListener('resize', onResize);
      setTimeout(() => {{ onResize(); setColabFrameHeight(); }}, 0);
      setTimeout(() => {{ onResize(); setColabFrameHeight(); }}, 500);
    }} catch (error) {{
      showError(error);
    }}
  </script>
</body>
</html>
"""
    return HTML(html)


def MJCF_Viewer(*args: Any, **kwargs: Any) -> HTML:
    """Alias compatible con el nombre del viewer."""
    return MJCF_Visualization(*args, **kwargs)


def MJCF_Render(*args: Any, **kwargs: Any) -> HTML:
    """Alias corto para renderizar MJCF en Colab."""
    return MJCF_Visualization(*args, **kwargs)
