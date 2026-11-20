import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import CHUNK_SIZE, MOVIES_DAT
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

PATRON_ANIO = re.compile(r"\s*\((\d{4})\)\s*$")
GENERO_VACIO = "(no genres listed)"


def _parsear_linea(linea):
    partes = linea.rstrip("\r\n").split("::")
    if len(partes) < 3:
        raise ValueError("la línea no tiene el formato ID::Título (Año)::Géneros")
    texto_id = partes[0].strip()
    if not texto_id.isdigit():
        raise ValueError(f"ID no numérico: {texto_id!r}")
    titulo = "::".join(partes[1:-1]).strip()
    if not titulo:
        raise ValueError("título vacío")
    anio = None
    coincidencia = PATRON_ANIO.search(titulo)
    if coincidencia:
        anio = int(coincidencia.group(1))
        titulo = titulo[:coincidencia.start()].strip()
        if not 1800 <= anio <= 2100:
            anio = None
    if not titulo:
        raise ValueError("título vacío")
    generos = []
    vistos = set()
    for genero in partes[-1].split("|"):
        genero = genero.strip()
        if not genero or genero.lower() == GENERO_VACIO:
            continue
        clave = normalizar_clave(genero)
        if clave not in vistos:
            vistos.add(clave)
            generos.append(genero[:80])
    return int(texto_id), titulo[:500], anio, generos


def _insertar_bloque(cursor, bloque, mapa_generos):
    cursor.executemany(
        "INSERT INTO peliculas (id_pelicula, titulo, anio_estreno) VALUES (%s, %s, %s) "
        "ON DUPLICATE KEY UPDATE titulo = VALUES(titulo), anio_estreno = VALUES(anio_estreno)",
        [(i, t, a) for _, i, t, a, _ in bloque],
    )
    ids = [i for _, i, _, _, _ in bloque]
    marcadores = ",".join(["%s"] * len(ids))
    cursor.execute(f"DELETE FROM pelicula_generos WHERE id_pelicula IN ({marcadores})", ids)
    relaciones = []
    for _, id_pelicula, _, _, generos in bloque:
        for genero in generos:
            relaciones.append((id_pelicula, mapa_generos[normalizar_clave(genero)]))
    if relaciones:
        cursor.executemany(
            "INSERT IGNORE INTO pelicula_generos (id_pelicula, id_genero) VALUES (%s, %s)",
            relaciones,
        )


def ejecutar_etl_peliculas(ruta_archivo=None, id_usuario=None):
    ruta = Path(ruta_archivo or MOVIES_DAT)
    if not ruta.is_file():
        raise FileNotFoundError(f"No se encontró el archivo {ruta}")

    id_archivo = registrar_archivo(ruta.name, "PELICULAS", id_usuario)
    errores = []
    registros = []
    leidos = 0

    try:
        with open(ruta, "r", encoding="latin1", newline="") as archivo:
            for numero_fila, linea in enumerate(archivo, start=1):
                if not linea.strip():
                    continue
                leidos += 1
                try:
                    id_pelicula, titulo, anio, generos = _parsear_linea(linea)
                except ValueError as exc:
                    errores.append((numero_fila, str(exc), linea.rstrip("\r\n")))
                    continue
                registros.append((numero_fila, id_pelicula, titulo, anio, generos))

        todos_generos = {g for *_, generos in registros for g in generos}
        with transaccion(id_usuario) as cursor:
            mapa_generos = resolver_catalogo(
                cursor, "generos", "id_genero", "nombre_genero", sorted(todos_generos), 80
            )

        cargados = 0
        for bloque in en_bloques(registros, CHUNK_SIZE):
            try:
                with transaccion(id_usuario) as cursor:
                    _insertar_bloque(cursor, bloque, mapa_generos)
                cargados += len(bloque)
            except Error:
                for registro in bloque:
                    try:
                        with transaccion(id_usuario) as cursor:
                            _insertar_bloque(cursor, [registro], mapa_generos)
                        cargados += 1
                    except Error as exc:
                        errores.append((registro[0], f"Error al insertar: {exc}", json.dumps(
                            {"id": registro[1], "titulo": registro[2], "anio": registro[3], "generos": registro[4]},
                            ensure_ascii=False,
                        )))
    except Exception as exc:
        errores.append((None, f"Fallo general de la carga: {exc}", None))
        guardar_errores(id_archivo, errores)
        cerrar_archivo(id_archivo, "FALLIDO")
        registrar_auditoria(
            id_usuario, "ETL_PELICULAS", f"Falló la carga de {ruta.name}: {exc}", "FALLIDO",
            tabla_afectada="archivos", datos_nuevos={"id_archivo": id_archivo},
        )
        return {"id_archivo": id_archivo, "estado": "FALLIDO", "error": str(exc), "errores": len(errores)}

    guardar_errores(id_archivo, errores)
    estado = "CON_ERRORES" if errores else "PROCESADO"
    cerrar_archivo(id_archivo, estado)
    resumen = {"leidos": leidos, "cargados": cargados, "generos": len(mapa_generos), "errores": len(errores)}
    registrar_auditoria(
        id_usuario, "ETL_PELICULAS", f"Carga de {ruta.name} finalizada con estado {estado}", "EXITOSO",
        tabla_afectada="archivos", datos_nuevos={"id_archivo": id_archivo, **resumen},
    )
    return {"id_archivo": id_archivo, "estado": estado, **resumen}


if __name__ == "__main__":
    resultado = ejecutar_etl_peliculas(sys.argv[1] if len(sys.argv) > 1 else MOVIES_DAT)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    sys.exit(0 if resultado["estado"] != "FALLIDO" else 1)
