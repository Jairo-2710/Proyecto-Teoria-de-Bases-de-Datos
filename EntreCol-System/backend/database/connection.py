import re
import threading
import unicodedata
from contextlib import contextmanager

import mysql.connector
from mysql.connector import pooling

from config import CHUNK_SIZE, DB_CONFIG, DB_POOL_NAME, DB_POOL_SIZE

_pool = None
_pool_lock = threading.Lock()


def _obtener_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = pooling.MySQLConnectionPool(
                    pool_name=DB_POOL_NAME,
                    pool_size=DB_POOL_SIZE,
                    pool_reset_session=True,
                    **DB_CONFIG,
                )
    return _pool


def obtener_conexion():
    return _obtener_pool().get_connection()


@contextmanager
def conexion():
    conn = obtener_conexion()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaccion(id_usuario_sesion=None):
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True, buffered=True)
    try:
        if id_usuario_sesion is not None:
            cursor.execute("SET @id_usuario_sesion = %s", (id_usuario_sesion,))
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def consultar(sql, params=None):
    with conexion() as conn:
        cursor = conn.cursor(dictionary=True, buffered=True)
        try:
            cursor.execute(sql, params or ())
            return cursor.fetchall()
        finally:
            cursor.close()


def consultar_uno(sql, params=None):
    filas = consultar(sql, params)
    return filas[0] if filas else None


def ejecutar(sql, params=None):
    with transaccion() as cursor:
        cursor.execute(sql, params or ())
        return cursor.lastrowid


def normalizar_clave(texto):
    if texto is None:
        return ""
    descompuesto = unicodedata.normalize("NFKD", str(texto))
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_acentos).strip().casefold()


def en_bloques(elementos, tamano=CHUNK_SIZE):
    elementos = list(elementos)
    for inicio in range(0, len(elementos), tamano):
        yield elementos[inicio : inicio + tamano]


def resolver_catalogo(
    cursor, tabla, columna_id, columna_nombre, nombres, longitud_maxima=None
):
    limpios = {}
    for nombre in nombres:
        if nombre is None:
            continue
        texto = re.sub(r"\s+", " ", str(nombre)).strip()
        if longitud_maxima:
            texto = texto[:longitud_maxima]
        if texto:
            limpios.setdefault(normalizar_clave(texto), texto)
    mapa = {}
    for bloque in en_bloques(limpios.values()):
        cursor.executemany(
            f"INSERT IGNORE INTO {tabla} ({columna_nombre}) VALUES (%s)",
            [(n,) for n in bloque],
        )
        marcadores = ",".join(["%s"] * len(bloque))
        cursor.execute(
            f"SELECT {columna_id} AS id, {columna_nombre} AS nombre FROM {tabla} "
            f"WHERE {columna_nombre} IN ({marcadores})",
            bloque,
        )
        for fila in cursor.fetchall():
            mapa[normalizar_clave(fila["nombre"])] = fila["id"]
        for nombre in bloque:
            clave = normalizar_clave(nombre)
            if clave not in mapa:
                cursor.execute(
                    f"SELECT {columna_id} AS id FROM {tabla} WHERE {columna_nombre} = %s",
                    (nombre,),
                )
                fila = cursor.fetchone()
                if fila:
                    mapa[clave] = fila["id"]
    return mapa


def resolver_usuario_etl(id_usuario=None):
    if id_usuario is not None:
        fila = consultar_uno(
            "SELECT id_usuario FROM usuarios WHERE id_usuario = %s", (id_usuario,)
        )
        if fila:
            return fila["id_usuario"]
    fila = consultar_uno(
        "SELECT id_usuario FROM usuarios WHERE activo = 1 "
        "ORDER BY (username = 'admin') DESC, id_usuario ASC LIMIT 1"
    )
    if not fila:
        raise RuntimeError(
            "No existe ningún usuario activo para asociar el archivo cargado"
        )
    return fila["id_usuario"]


def registrar_archivo(nombre_archivo, tipo, id_usuario=None):
    propietario = resolver_usuario_etl(id_usuario)
    with transaccion() as cursor:
        cursor.execute(
            "INSERT INTO archivos (id_usuario, nombre_archivo, fecha, hora, tipo, estado) "
            "VALUES (%s, %s, CURDATE(), CURTIME(), %s, 'PROCESANDO')",
            (propietario, str(nombre_archivo)[:255], tipo),
        )
        return cursor.lastrowid


def cerrar_archivo(id_archivo, estado):
    with transaccion() as cursor:
        cursor.execute(
            "UPDATE archivos SET estado = %s WHERE id_archivo = %s",
            (estado, id_archivo),
        )


def guardar_errores(id_archivo, errores):
    if not errores:
        return
    filas = [
        (id_archivo, fila, str(motivo)[:500], None if crudo is None else str(crudo))
        for fila, motivo, crudo in errores
    ]
    with transaccion() as cursor:
        for bloque in en_bloques(filas):
            cursor.executemany(
                "INSERT INTO errores_carga (id_archivo, numero_fila, motivo, dato_crudo) "
                "VALUES (%s, %s, %s, %s)",
                bloque,
            )


Error = mysql.connector.Error
