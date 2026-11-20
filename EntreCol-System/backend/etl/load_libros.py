import calendar
import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import BOOKS_JSON, CHUNK_SIZE
from database.connection import (
    Error,
    cerrar_archivo,
    en_bloques,
    guardar_errores,
    normalizar_clave,
    registrar_archivo,
    resolver_catalogo,
    transaccion,
)
from services.audit_logger import registrar_auditoria

PATRON_FECHA = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$")


def _leer_registros(ruta):
    with open(ruta, "r", encoding="utf-8-sig") as archivo:
        contenido = archivo.read()
    try:
        datos = json.loads(contenido)
    except json.JSONDecodeError:
        datos = []
        for numero, linea in enumerate(contenido.splitlines(), start=1):
            linea = linea.strip().rstrip(",")
            if not linea or linea in ("[", "]"):
                continue
            try:
                datos.append(json.loads(linea))
            except json.JSONDecodeError:
                datos.append({"__linea_invalida__": linea, "__numero__": numero})
    if isinstance(datos, dict):
        listas = [v for v in datos.values() if isinstance(v, list)]
        if not listas:
            raise ValueError("El JSON no contiene una lista de registros")
        datos = max(listas, key=len)
    if not isinstance(datos, list):
        raise ValueError("El JSON no contiene una lista de registros")
    return datos


def _limpiar_llaves(registro):
    return {str(k).strip(): v for k, v in registro.items()}


def _texto(valor):
    if valor is None:
        return None
    texto = re.sub(r"\s+", " ", str(valor)).strip()
    return texto or None


def _numero(valor):
    texto = _texto(valor)
    if texto is None:
        return None
    try:
        numero = Decimal(texto.replace(",", "."))
    except InvalidOperation:
        return None
    return numero if numero.is_finite() else None


def _entero_no_negativo(valor):
    numero = _numero(valor)
    if numero is None or numero < 0:
        return 0
    return int(numero)


def _calificacion(valor):
    numero = _numero(valor)
    if numero is None or numero < 0 or numero > 5:
        return Decimal("0")
    return numero.quantize(Decimal("0.01"))


def _parsear_fecha(valor):
    texto = _texto(valor)
    if texto is None:
        return None, None
    coincidencia = PATRON_FECHA.match(texto)
    if not coincidencia:
        return None, f"formato de fecha no reconocido: {texto!r}"
    mes, dia, anio = (int(g) for g in coincidencia.groups())
    if not 1000 <= anio <= 9999:
        return None, f"año fuera de rango: {texto!r}"
    try:
        return date(anio, mes, dia), None
    except ValueError:
        if 1 <= mes <= 12:
            ultimo = calendar.monthrange(anio, mes)[1]
            return date(anio, mes, ultimo), f"fecha inválida {texto!r}; se ajustó al último día del mes conservando el año"
        return date(anio, 1, 1), f"fecha inválida {texto!r}; se conservó únicamente el año"


def _normalizar_registro(numero_fila, bruto):
    registro = _limpiar_llaves(bruto)
    if "__linea_invalida__" in registro:
        raise ValueError("línea JSON inválida")
    texto_id = _texto(registro.get("bookID"))
    if texto_id is None or not texto_id.isdigit():
        raise ValueError(f"bookID inválido: {texto_id!r}")
    titulo = _texto(registro.get("title"))
    if not titulo:
        raise ValueError("título vacío")
    autores = []
    vistos = set()
    for nombre in str(registro.get("authors") or "").split("/"):
        nombre = _texto(nombre)
        if nombre and normalizar_clave(nombre) not in vistos:
            vistos.add(normalizar_clave(nombre))
            autores.append(nombre[:150])
    if not autores:
        raise ValueError("el libro no tiene autores")
    fecha, aviso = _parsear_fecha(registro.get("publication_date"))
    idioma = _texto(registro.get("language_code"))
    editorial = _texto(registro.get("publisher"))
    fila = {
        "id_libro": int(texto_id),
        "titulo": titulo[:500],
        "autores": autores,
        "editorial": editorial[:150] if editorial else None,
        "idioma": idioma[:10] if idioma else None,
        "isbn": (_texto(registro.get("isbn")) or "")[:20] or None,
        "isbn13": (_texto(registro.get("isbn13")) or "")[:20] or None,
        "calificacion": _calificacion(registro.get("average_rating")),
        "paginas": _entero_no_negativo(registro.get("num_pages")),
        "calificaciones": _entero_no_negativo(registro.get("ratings_count")),
        "resenas": _entero_no_negativo(registro.get("text_reviews_count")),
        "fecha": fecha,
    }
    return fila, aviso


def _insertar_bloque(cursor, bloque, mapas):
    mapa_autores, mapa_editoriales, mapa_idiomas = mapas
    filas = []
    for _, f in bloque:
        filas.append((
            f["id_libro"],
            mapa_idiomas.get(normalizar_clave(f["idioma"])) if f["idioma"] else None,
            mapa_autores[normalizar_clave(f["autores"][0])],
            mapa_editoriales.get(normalizar_clave(f["editorial"])) if f["editorial"] else None,
            f["titulo"], f["isbn"], f["isbn13"], f["calificacion"], f["paginas"],
            f["calificaciones"], f["resenas"], f["fecha"],
        ))
    cursor.executemany(
        "INSERT INTO libros (id_libro, id_idioma, id_autor, id_editorial, titulo, isbn, isbn13, "
        "calificacion_promedio, numero_paginas, cantidad_calificaciones, numero_resenas, fecha_publicacion) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON DUPLICATE KEY UPDATE id_idioma = VALUES(id_idioma), id_autor = VALUES(id_autor), "
        "id_editorial = VALUES(id_editorial), titulo = VALUES(titulo), isbn = VALUES(isbn), "
        "isbn13 = VALUES(isbn13), calificacion_promedio = VALUES(calificacion_promedio), "
        "numero_paginas = VALUES(numero_paginas), cantidad_calificaciones = VALUES(cantidad_calificaciones), "
        "numero_resenas = VALUES(numero_resenas), fecha_publicacion = VALUES(fecha_publicacion)",
        filas,
    )
    ids = [f["id_libro"] for _, f in bloque]
    marcadores = ",".join(["%s"] * len(ids))
    cursor.execute(f"DELETE FROM libro_autores WHERE id_libro IN ({marcadores})", ids)
    relaciones = []
    for _, f in bloque:
        for orden, autor in enumerate(f["autores"][:255], start=1):
            relaciones.append((f["id_libro"], mapa_autores[normalizar_clave(autor)], orden))
    cursor.executemany(
        "INSERT IGNORE INTO libro_autores (id_libro, id_autor, orden_autor) VALUES (%s, %s, %s)",
        relaciones,
    )


def ejecutar_etl_libros(ruta_archivo=None, id_usuario=None):
    ruta = Path(ruta_archivo or BOOKS_JSON)
    if not ruta.is_file():
        raise FileNotFoundError(f"No se encontró el archivo {ruta}")

    id_archivo = registrar_archivo(ruta.name, "LIBROS", id_usuario)
    errores = []
    cargados = 0

    try:
        brutos = _leer_registros(ruta)
        registros = {}
        for numero_fila, bruto in enumerate(brutos, start=1):
            if not isinstance(bruto, dict):
                errores.append((numero_fila, "el registro no es un objeto JSON", json.dumps(bruto, ensure_ascii=False, default=str)))
                continue
            try:
                fila, aviso = _normalizar_registro(numero_fila, bruto)
            except ValueError as exc:
                errores.append((numero_fila, str(exc), json.dumps(bruto, ensure_ascii=False, default=str)))
                continue
            if aviso:
                errores.append((numero_fila, aviso, json.dumps(bruto, ensure_ascii=False, default=str)))
            registros[fila["id_libro"]] = (numero_fila, fila)
        registros = list(registros.values())

        autores = {a for _, f in registros for a in f["autores"]}
        editoriales = {f["editorial"] for _, f in registros if f["editorial"]}
        idiomas = {f["idioma"] for _, f in registros if f["idioma"]}
        with transaccion(id_usuario) as cursor:
            mapa_autores = resolver_catalogo(cursor, "autores", "id_autor", "nombre_autor", sorted(autores), 150)
            mapa_editoriales = resolver_catalogo(cursor, "editoriales", "id_editorial", "nombre_editorial", sorted(editoriales), 150)
            mapa_idiomas = resolver_catalogo(cursor, "idiomas", "id_idioma", "codigo_idioma", sorted(idiomas), 10)
        mapas = (mapa_autores, mapa_editoriales, mapa_idiomas)

        for bloque in en_bloques(registros, CHUNK_SIZE):
            try:
                with transaccion(id_usuario) as cursor:
                    _insertar_bloque(cursor, bloque, mapas)
                cargados += len(bloque)
            except Error:
                for registro in bloque:
                    try:
                        with transaccion(id_usuario) as cursor:
                            _insertar_bloque(cursor, [registro], mapas)
                        cargados += 1
                    except Error as exc:
                        errores.append((registro[0], f"Error al insertar: {exc}", json.dumps(
                            {"bookID": registro[1]["id_libro"], "title": registro[1]["titulo"]}, ensure_ascii=False,
                        )))
    except Exception as exc:
        errores.append((None, f"Fallo general de la carga: {exc}", None))
        guardar_errores(id_archivo, errores)
        cerrar_archivo(id_archivo, "FALLIDO")
        registrar_auditoria(
            id_usuario, "ETL_LIBROS", f"Falló la carga de {ruta.name}: {exc}", "FALLIDO",
            tabla_afectada="archivos", datos_nuevos={"id_archivo": id_archivo},
        )
        return {"id_archivo": id_archivo, "estado": "FALLIDO", "error": str(exc), "errores": len(errores)}

    guardar_errores(id_archivo, errores)
    estado = "CON_ERRORES" if errores else "PROCESADO"
    cerrar_archivo(id_archivo, estado)
    resumen = {"leidos": len(brutos), "cargados": cargados, "errores": len(errores)}
    registrar_auditoria(
        id_usuario, "ETL_LIBROS", f"Carga de {ruta.name} finalizada con estado {estado}", "EXITOSO",
        tabla_afectada="archivos", datos_nuevos={"id_archivo": id_archivo, **resumen},
    )
    return {"id_archivo": id_archivo, "estado": estado, **resumen}


if __name__ == "__main__":
    resultado = ejecutar_etl_libros(sys.argv[1] if len(sys.argv) > 1 else BOOKS_JSON)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    sys.exit(0 if resultado["estado"] != "FALLIDO" else 1)
