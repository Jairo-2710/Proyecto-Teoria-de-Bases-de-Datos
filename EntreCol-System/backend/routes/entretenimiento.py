import logging
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request

from database import queries
from database.connection import Error, conexion, transaccion
from routes.auth import token_required
from services.audit_logger import registrar_auditoria

logger = logging.getLogger(__name__)

entretenimiento_bp = Blueprint("entretenimiento", __name__, url_prefix="/api/entretenimiento")

ERRNO_REFERENCIADO = 1451
ERRNO_REFERENCIA_INVALIDA = 1452
ERRNO_DUPLICADO = 1062
ERRNO_SENTENCIA_USUARIO = 1644
ERRNOS_CHECK = (3819,)
LIMITE_PAGINA_MAXIMO = 200
LIMITE_PAGINA_DEFECTO = 20
TIPOS_TOP5 = ("MEJOR", "PEOR")
PROCEDIMIENTOS = {
    "sp_peliculas_por_genero_fechas",
    "sp_top_n_libros",
    "sp_top5_libros_por_anio",
    "sp_peliculas_n_generos",
}

SQL_PELICULA = (
    "SELECT p.id_pelicula, p.titulo, p.anio_estreno, p.fecha_estreno, p.sinopsis, "
    "p.id_idioma, i.codigo_idioma AS idioma "
    "FROM peliculas p LEFT JOIN idiomas i ON i.id_idioma = p.id_idioma "
)

SQL_LIBRO = (
    "SELECT l.id_libro, l.titulo, l.id_autor, a.nombre_autor AS autor, l.id_editorial, "
    "e.nombre_editorial AS editorial, l.id_idioma, i.codigo_idioma AS idioma, l.isbn, l.isbn13, "
    "l.calificacion_promedio, l.numero_paginas, l.cantidad_calificaciones, l.numero_resenas, "
    "l.fecha_publicacion, l.anio_publicacion "
    "FROM libros l "
    "INNER JOIN autores a ON a.id_autor = l.id_autor "
    "LEFT JOIN editoriales e ON e.id_editorial = l.id_editorial "
    "LEFT JOIN idiomas i ON i.id_idioma = l.id_idioma "
)


def _error(mensaje, codigo):
    return jsonify({"error": mensaje}), codigo


def _cuerpo_json():
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        raise ValueError("El cuerpo de la petición debe ser un objeto JSON")
    return datos


def _traducir_error(exc, mensaje_referenciado):
    if isinstance(exc, ValueError):
        return str(exc), 400
    if isinstance(exc, LookupError):
        return str(exc.args[0]) if exc.args else "Recurso no encontrado", 404
    if isinstance(exc, Error):
        if exc.errno == ERRNO_DUPLICADO:
            return "Ya existe un registro con un valor único repetido", 409
        if exc.errno == ERRNO_REFERENCIADO:
            return mensaje_referenciado, 409
        if exc.errno == ERRNO_REFERENCIA_INVALIDA:
            return "Alguno de los identificadores enviados (idioma, género, autor o editorial) no existe", 400
        if exc.errno == ERRNO_SENTENCIA_USUARIO:
            return str(exc.msg), 400
        if exc.errno in ERRNOS_CHECK:
            return "Los datos enviados no cumplen las reglas de validación", 400
    return None, 500


def _fallo_escritura(exc, id_usuario, accion, tabla, mensaje_referenciado):
    mensaje, codigo = _traducir_error(exc, mensaje_referenciado)
    if codigo == 500:
        logger.exception("Error inesperado en %s sobre %s", accion, tabla)
        mensaje = "No fue posible completar la operación"
    registrar_auditoria(
        id_usuario,
        accion,
        f"Operación {accion} fallida sobre {tabla}: {exc}",
        "FALLIDO",
        tabla_afectada=tabla,
    )
    return _error(mensaje, codigo)


def _fallo_lectura(exc):
    mensaje, codigo = _traducir_error(exc, "El recurso está referenciado por otros registros")
    if codigo == 500:
        logger.exception("Error inesperado consultando entretenimiento")
        mensaje = "No fue posible completar la consulta"
    return _error(mensaje, codigo)


def _paginacion():
    pagina = queries._entero(request.args.get("page"), "page", 1, obligatorio=False) or 1
    limite = queries._entero(
        request.args.get("limit"), "limit", 1, LIMITE_PAGINA_MAXIMO, obligatorio=False
    ) or LIMITE_PAGINA_DEFECTO
    return pagina, limite, (pagina - 1) * limite


def _respuesta_paginada(datos, total, pagina, limite):
    return jsonify(
        {
            "datos": datos,
            "total": total,
            "page": pagina,
            "limit": limite,
            "paginas": (total + limite - 1) // limite if total else 0,
        }
    )


def _llamar_procedimiento(nombre, argumentos):
    if nombre not in PROCEDIMIENTOS:
        raise ValueError("Procedimiento no permitido")
    with conexion() as conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.callproc(nombre, argumentos)
            return [queries._normalizar_filas(r.fetchall()) for r in cursor.stored_results()]
        finally:
            cursor.close()


def _ids_lista(valor, campo):
    if valor is None:
        return []
    if not isinstance(valor, (list, tuple)):
        raise ValueError(f"El campo '{campo}' debe ser una lista de identificadores")
    vistos = []
    for elemento in valor:
        identificador = queries._entero(elemento, campo, 1)
        if identificador not in vistos:
            vistos.append(identificador)
    return vistos


def _consulta(sql, params=None):
    with transaccion() as cursor:
        cursor.execute(sql, params or ())
        return queries._normalizar_filas(cursor.fetchall())


def _adjuntar(cursor, filas, clave_id, sql, destino):
    if not filas:
        return filas
    ids = [f[clave_id] for f in filas]
    marcadores = ",".join(["%s"] * len(ids))
    cursor.execute(sql.format(marcadores=marcadores), ids)
    agrupado = {identificador: [] for identificador in ids}
    for fila in cursor.fetchall():
        agrupado[fila.pop(clave_id)].append(fila)
    for fila in filas:
        fila[destino] = agrupado[fila[clave_id]]
    return filas


def _adjuntar_generos(cursor, peliculas):
    return _adjuntar(
        cursor,
        peliculas,
        "id_pelicula",
        "SELECT pg.id_pelicula, g.id_genero, g.nombre_genero FROM pelicula_generos pg "
        "INNER JOIN generos g ON g.id_genero = pg.id_genero WHERE pg.id_pelicula IN ({marcadores}) "
        "ORDER BY g.nombre_genero ASC",
        "generos",
    )


def _adjuntar_autores(cursor, libros):
    return _adjuntar(
        cursor,
        libros,
        "id_libro",
        "SELECT la.id_libro, a.id_autor, a.nombre_autor, la.orden_autor FROM libro_autores la "
        "INNER JOIN autores a ON a.id_autor = la.id_autor WHERE la.id_libro IN ({marcadores}) "
        "ORDER BY la.orden_autor ASC, a.nombre_autor ASC",
        "autores",
    )


def _leer_pelicula(cursor, id_pelicula, bloquear=False):
    sufijo = " FOR UPDATE" if bloquear else ""
    cursor.execute(f"{SQL_PELICULA}WHERE p.id_pelicula = %s{sufijo}", (id_pelicula,))
    filas = queries._normalizar_filas(cursor.fetchall())
    if not filas:
        raise LookupError("No se encontró la película solicitada")
    return _adjuntar_generos(cursor, filas)[0]


def _leer_libro(cursor, id_libro, bloquear=False):
    sufijo = " FOR UPDATE OF l" if bloquear else ""
    cursor.execute(f"{SQL_LIBRO}WHERE l.id_libro = %s{sufijo}", (id_libro,))
    filas = queries._normalizar_filas(cursor.fetchall())
    if not filas:
        raise LookupError("No se encontró el libro solicitado")
    return _adjuntar_autores(cursor, filas)[0]


def _campos_pelicula(datos, actual=None):
    base = actual or {}

    def valor(clave):
        return datos[clave] if clave in datos else base.get(clave)

    titulo = queries._texto(valor("titulo"), "titulo", 500)
    id_idioma = queries._entero(valor("id_idioma"), "id_idioma", 1, obligatorio=False)
    fecha = queries._fecha(valor("fecha_estreno"), "fecha_estreno", obligatorio=False)
    anio = queries._entero(valor("anio_estreno"), "anio_estreno", 1800, 2200, obligatorio=False)
    if fecha is not None and ("anio_estreno" not in datos or anio is None):
        anio = fecha.year
    if fecha is not None and anio is not None and fecha.year != anio:
        raise ValueError("El año de estreno no coincide con la fecha de estreno")
    sinopsis = queries._texto(valor("sinopsis"), "sinopsis", 2000, obligatorio=False)
    return {
        "titulo": titulo,
        "id_idioma": id_idioma,
        "anio_estreno": anio,
        "fecha_estreno": fecha,
        "sinopsis": sinopsis,
    }


def _calificacion(valor):
    if valor is None or isinstance(valor, bool) or (isinstance(valor, str) and not valor.strip()):
        return Decimal("0.00")
    try:
        numero = Decimal(str(valor).strip())
    except InvalidOperation:
        raise ValueError("El campo 'calificacion_promedio' debe ser numérico")
    if not numero.is_finite() or numero < 0 or numero > 5:
        raise ValueError("El campo 'calificacion_promedio' debe estar entre 0 y 5")
    return numero.quantize(Decimal("0.01"))


def _campos_libro(datos, actual=None):
    base = actual or {}

    def valor(clave):
        return datos[clave] if clave in datos else base.get(clave)

    def entero_cero(clave):
        return queries._entero(valor(clave), clave, 0, 2147483647, obligatorio=False) or 0

    return {
        "titulo": queries._texto(valor("titulo"), "titulo", 500),
        "id_autor": queries._entero(valor("id_autor"), "id_autor", 1),
        "id_editorial": queries._entero(valor("id_editorial"), "id_editorial", 1, obligatorio=False),
        "id_idioma": queries._entero(valor("id_idioma"), "id_idioma", 1, obligatorio=False),
        "isbn": queries._texto(valor("isbn"), "isbn", 20, obligatorio=False),
        "isbn13": queries._texto(valor("isbn13"), "isbn13", 20, obligatorio=False),
        "calificacion_promedio": _calificacion(valor("calificacion_promedio")),
        "numero_paginas": entero_cero("numero_paginas"),
        "cantidad_calificaciones": entero_cero("cantidad_calificaciones"),
        "numero_resenas": entero_cero("numero_resenas"),
        "fecha_publicacion": queries._fecha(valor("fecha_publicacion"), "fecha_publicacion", obligatorio=False),
    }


def _sincronizar_generos(cursor, id_pelicula, generos):
    cursor.execute("DELETE FROM pelicula_generos WHERE id_pelicula = %s", (id_pelicula,))
    if generos:
        cursor.executemany(
            "INSERT INTO pelicula_generos (id_pelicula, id_genero) VALUES (%s, %s)",
            [(id_pelicula, g) for g in generos],
        )


def _sincronizar_autores(cursor, id_libro, id_autor, coautores):
    ordenados = [id_autor] + [a for a in coautores if a != id_autor]
    if len(ordenados) > 255:
        raise ValueError("El libro no puede tener más de 255 autores")
    cursor.execute("DELETE FROM libro_autores WHERE id_libro = %s", (id_libro,))
    cursor.executemany(
        "INSERT INTO libro_autores (id_libro, id_autor, orden_autor) VALUES (%s, %s, %s)",
        [(id_libro, autor, orden) for orden, autor in enumerate(ordenados, start=1)],
    )


def _coautores_de(datos, actual):
    if "coautores" in datos:
        return _ids_lista(datos["coautores"], "coautores")
    principal = actual["id_autor"] if actual else None
    return [a["id_autor"] for a in (actual or {}).get("autores", []) if a["id_autor"] != principal]


def _filtro_busqueda(columnas):
    busqueda = request.args.get("busqueda")
    if busqueda is None or not busqueda.strip():
        return "", []
    patron = queries._patron_busqueda(busqueda)
    condicion = " OR ".join(f"{c} LIKE %s" for c in columnas)
    return f"WHERE ({condicion}) ", [patron] * len(columnas)


@entretenimiento_bp.get("/catalogos")
@token_required
def catalogos(id_usuario):
    try:
        return jsonify(
            {
                "generos": _consulta("SELECT id_genero, nombre_genero FROM generos ORDER BY nombre_genero ASC"),
                "idiomas": _consulta(
                    "SELECT id_idioma, codigo_idioma, nombre_idioma FROM idiomas ORDER BY codigo_idioma ASC"
                ),
                "autores": _consulta("SELECT id_autor, nombre_autor FROM autores ORDER BY nombre_autor ASC"),
                "editoriales": _consulta(
                    "SELECT id_editorial, nombre_editorial FROM editoriales ORDER BY nombre_editorial ASC"
                ),
            }
        )
    except Exception as exc:
        return _fallo_lectura(exc)


@entretenimiento_bp.get("/peliculas")
@token_required
def listar_peliculas(id_usuario):
    try:
        pagina, limite, salto = _paginacion()
        busqueda = request.args.get("busqueda")
        where, params = "", []
        if busqueda is not None and busqueda.strip():
            patron = queries._patron_busqueda(busqueda)
            where = (
                "WHERE (p.titulo LIKE %s OR EXISTS (SELECT 1 FROM pelicula_generos pg "
                "INNER JOIN generos g ON g.id_genero = pg.id_genero "
                "WHERE pg.id_pelicula = p.id_pelicula AND g.nombre_genero LIKE %s)) "
            )
            params = [patron, patron]
        with transaccion() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM peliculas p {where}", params)
            total = cursor.fetchone()["total"]
            cursor.execute(
                f"{SQL_PELICULA}{where}ORDER BY p.titulo ASC, p.id_pelicula ASC LIMIT %s OFFSET %s",
                params + [limite, salto],
            )
            filas = _adjuntar_generos(cursor, queries._normalizar_filas(cursor.fetchall()))
        return _respuesta_paginada(filas, total, pagina, limite)
    except Exception as exc:
        return _fallo_lectura(exc)


@entretenimiento_bp.post("/peliculas")
@token_required
def crear_pelicula(id_usuario):
    try:
        datos = _cuerpo_json()
        campos = _campos_pelicula(datos)
        generos = _ids_lista(datos.get("generos"), "generos")
        with transaccion(id_usuario) as cursor:
            cursor.execute(
                "INSERT INTO peliculas (id_idioma, titulo, anio_estreno, fecha_estreno, sinopsis) "
                "VALUES (%s, %s, %s, %s, %s)",
                (
                    campos["id_idioma"],
                    campos["titulo"],
                    campos["anio_estreno"],
                    campos["fecha_estreno"],
                    campos["sinopsis"],
                ),
            )
            id_pelicula = cursor.lastrowid
            _sincronizar_generos(cursor, id_pelicula, generos)
            nueva = _leer_pelicula(cursor, id_pelicula)
    except Exception as exc:
        return _fallo_escritura(exc, id_usuario, "INSERT", "peliculas", "")
    registrar_auditoria(
        id_usuario,
        "INSERT",
        f"Se creó la película {id_pelicula} desde la API de entretenimiento",
        "EXITOSO",
        tabla_afectada="peliculas",
        datos_nuevos=nueva,
    )
    return jsonify(nueva), 201


@entretenimiento_bp.put("/peliculas/<int:id_pelicula>")
@token_required
def actualizar_pelicula(id_usuario, id_pelicula):
    try:
        datos = _cuerpo_json()
        with transaccion(id_usuario) as cursor:
            anterior = _leer_pelicula(cursor, id_pelicula, bloquear=True)
            campos = _campos_pelicula(datos, anterior)
            generos = (
                _ids_lista(datos["generos"], "generos")
                if "generos" in datos
                else [g["id_genero"] for g in anterior["generos"]]
            )
            cursor.execute(
                "UPDATE peliculas SET id_idioma = %s, titulo = %s, anio_estreno = %s, "
                "fecha_estreno = %s, sinopsis = %s WHERE id_pelicula = %s",
                (
                    campos["id_idioma"],
                    campos["titulo"],
                    campos["anio_estreno"],
                    campos["fecha_estreno"],
                    campos["sinopsis"],
                    id_pelicula,
                ),
            )
            _sincronizar_generos(cursor, id_pelicula, generos)
            nueva = _leer_pelicula(cursor, id_pelicula)
    except Exception as exc:
        return _fallo_escritura(exc, id_usuario, "UPDATE", "peliculas", "")
    registrar_auditoria(
        id_usuario,
        "UPDATE",
        f"Se actualizó la película {id_pelicula} desde la API de entretenimiento",
        "EXITOSO",
        tabla_afectada="peliculas",
        datos_anteriores=anterior,
        datos_nuevos=nueva,
    )
    return jsonify(nueva)


@entretenimiento_bp.delete("/peliculas/<int:id_pelicula>")
@token_required
def eliminar_pelicula(id_usuario, id_pelicula):
    try:
        with transaccion(id_usuario) as cursor:
            anterior = _leer_pelicula(cursor, id_pelicula, bloquear=True)
            cursor.execute("DELETE FROM peliculas WHERE id_pelicula = %s", (id_pelicula,))
    except Exception as exc:
        return _fallo_escritura(
            exc, id_usuario, "DELETE", "peliculas", "No se puede eliminar la película porque tiene registros asociados"
        )
    registrar_auditoria(
        id_usuario,
        "DELETE",
        f"Se eliminó la película {id_pelicula} desde la API de entretenimiento",
        "EXITOSO",
        tabla_afectada="peliculas",
        datos_anteriores=anterior,
    )
    return jsonify({"mensaje": "Película eliminada", "id_pelicula": id_pelicula})


@entretenimiento_bp.get("/libros")
@token_required
def listar_libros(id_usuario):
    try:
        pagina, limite, salto = _paginacion()
        where, params = _filtro_busqueda(
            ["l.titulo", "a.nombre_autor", "e.nombre_editorial", "l.isbn", "l.isbn13"]
        )
        base = (
            "FROM libros l INNER JOIN autores a ON a.id_autor = l.id_autor "
            "LEFT JOIN editoriales e ON e.id_editorial = l.id_editorial "
        )
        with transaccion() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total {base}{where}", params)
            total = cursor.fetchone()["total"]
            cursor.execute(
                f"{SQL_LIBRO}{where}ORDER BY l.titulo ASC, l.id_libro ASC LIMIT %s OFFSET %s",
                params + [limite, salto],
            )
            filas = _adjuntar_autores(cursor, queries._normalizar_filas(cursor.fetchall()))
        return _respuesta_paginada(filas, total, pagina, limite)
    except Exception as exc:
        return _fallo_lectura(exc)


def _insertar_libro(cursor, campos):
    cursor.execute(
        "INSERT INTO libros (id_idioma, id_autor, id_editorial, titulo, isbn, isbn13, calificacion_promedio, "
        "numero_paginas, cantidad_calificaciones, numero_resenas, fecha_publicacion) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            campos["id_idioma"],
            campos["id_autor"],
            campos["id_editorial"],
            campos["titulo"],
            campos["isbn"],
            campos["isbn13"],
            campos["calificacion_promedio"],
            campos["numero_paginas"],
            campos["cantidad_calificaciones"],
            campos["numero_resenas"],
            campos["fecha_publicacion"],
        ),
    )
    return cursor.lastrowid


@entretenimiento_bp.post("/libros")
@token_required
def crear_libro(id_usuario):
    try:
        datos = _cuerpo_json()
        campos = _campos_libro(datos)
        coautores = _coautores_de(datos, None)
        with transaccion(id_usuario) as cursor:
            id_libro = _insertar_libro(cursor, campos)
            _sincronizar_autores(cursor, id_libro, campos["id_autor"], coautores)
            nuevo = _leer_libro(cursor, id_libro)
    except Exception as exc:
        return _fallo_escritura(exc, id_usuario, "INSERT", "libros", "")
    registrar_auditoria(
        id_usuario,
        "INSERT",
        f"Se creó el libro {id_libro} desde la API de entretenimiento",
        "EXITOSO",
        tabla_afectada="libros",
        datos_nuevos=nuevo,
    )
    return jsonify(nuevo), 201


@entretenimiento_bp.put("/libros/<int:id_libro>")
@token_required
def actualizar_libro(id_usuario, id_libro):
    try:
        datos = _cuerpo_json()
        with transaccion(id_usuario) as cursor:
            anterior = _leer_libro(cursor, id_libro, bloquear=True)
            campos = _campos_libro(datos, anterior)
            coautores = _coautores_de(datos, anterior)
            cursor.execute(
                "UPDATE libros SET id_idioma = %s, id_autor = %s, id_editorial = %s, titulo = %s, isbn = %s, "
                "isbn13 = %s, calificacion_promedio = %s, numero_paginas = %s, cantidad_calificaciones = %s, "
                "numero_resenas = %s, fecha_publicacion = %s WHERE id_libro = %s",
                (
                    campos["id_idioma"],
                    campos["id_autor"],
                    campos["id_editorial"],
                    campos["titulo"],
                    campos["isbn"],
                    campos["isbn13"],
                    campos["calificacion_promedio"],
                    campos["numero_paginas"],
                    campos["cantidad_calificaciones"],
                    campos["numero_resenas"],
                    campos["fecha_publicacion"],
                    id_libro,
                ),
            )
            _sincronizar_autores(cursor, id_libro, campos["id_autor"], coautores)
            nuevo = _leer_libro(cursor, id_libro)
    except Exception as exc:
        return _fallo_escritura(exc, id_usuario, "UPDATE", "libros", "")
    registrar_auditoria(
        id_usuario,
        "UPDATE",
        f"Se actualizó el libro {id_libro} desde la API de entretenimiento",
        "EXITOSO",
        tabla_afectada="libros",
        datos_anteriores=anterior,
        datos_nuevos=nuevo,
    )
    return jsonify(nuevo)


@entretenimiento_bp.delete("/libros/<int:id_libro>")
@token_required
def eliminar_libro(id_usuario, id_libro):
    try:
        with transaccion(id_usuario) as cursor:
            anterior = _leer_libro(cursor, id_libro, bloquear=True)
            cursor.execute("DELETE FROM libros WHERE id_libro = %s", (id_libro,))
    except Exception as exc:
        return _fallo_escritura(
            exc, id_usuario, "DELETE", "libros", "No se puede eliminar el libro porque tiene registros asociados"
        )
    registrar_auditoria(
        id_usuario,
        "DELETE",
        f"Se eliminó el libro {id_libro} desde la API de entretenimiento",
        "EXITOSO",
        tabla_afectada="libros",
        datos_anteriores=anterior,
    )
    return jsonify({"mensaje": "Libro eliminado", "id_libro": id_libro})


@entretenimiento_bp.get("/reportes/peliculas-genero-fechas")
@token_required
def reporte_peliculas_genero_fechas(id_usuario):
    try:
        orden = queries.validar_orden(request.args.get("orden"))
        id_genero = queries._entero(request.args.get("id_genero"), "id_genero", 1)
        f1 = queries._fecha(request.args.get("f1"), "f1")
        f2 = queries._fecha(request.args.get("f2"), "f2")
        conjuntos = _llamar_procedimiento("sp_peliculas_por_genero_fechas", (id_genero, f1, f2, orden))
        filas = conjuntos[0] if conjuntos else []
        return jsonify(
            {
                "parametros": {"id_genero": id_genero, "f1": f1.isoformat(), "f2": f2.isoformat(), "orden": orden},
                "total": len(filas),
                "peliculas": filas,
            }
        )
    except Exception as exc:
        return _fallo_lectura(exc)


@entretenimiento_bp.get("/reportes/top-n-libros")
@token_required
def reporte_top_n_libros(id_usuario):
    try:
        orden = queries.validar_orden(request.args.get("orden"))
        n = queries._entero(request.args.get("n") or 10, "n", 1, 1000)
        conjuntos = _llamar_procedimiento("sp_top_n_libros", (n, orden))
        filas = conjuntos[0] if conjuntos else []
        return jsonify({"parametros": {"n": n, "orden": orden}, "total": len(filas), "libros": filas})
    except Exception as exc:
        return _fallo_lectura(exc)


@entretenimiento_bp.get("/reportes/top5-libros-anio")
@token_required
def reporte_top5_libros_anio(id_usuario):
    try:
        orden = queries.validar_orden(request.args.get("orden"))
        resultado = {}
        for tipo in TIPOS_TOP5:
            conjuntos = _llamar_procedimiento("sp_top5_libros_por_anio", (tipo, orden))
            resultado[tipo] = conjuntos[0] if conjuntos else []
        return jsonify(
            {
                "parametros": {"orden": orden},
                "mejores": resultado["MEJOR"],
                "peores": resultado["PEOR"],
                "total_mejores": len(resultado["MEJOR"]),
                "total_peores": len(resultado["PEOR"]),
            }
        )
    except Exception as exc:
        return _fallo_lectura(exc)


@entretenimiento_bp.get("/reportes/peliculas-n-generos")
@token_required
def reporte_peliculas_n_generos(id_usuario):
    try:
        orden = queries.validar_orden(request.args.get("orden"))
        n = queries._entero(request.args.get("n") or 3, "n", 0, 1000)
        conjuntos = _llamar_procedimiento("sp_peliculas_n_generos", (n, orden))
        filas = conjuntos[0] if conjuntos else []
        cantidad = conjuntos[1][0]["cantidad_peliculas"] if len(conjuntos) > 1 and conjuntos[1] else len(filas)
        return jsonify(
            {"parametros": {"n": n, "orden": orden}, "cantidad_total": cantidad, "peliculas": filas}
        )
    except Exception as exc:
        return _fallo_lectura(exc)


@entretenimiento_bp.get("/reportes/frecuencia-peliculas-genero")
@token_required
def reporte_frecuencia_peliculas_genero(id_usuario):
    try:
        filas = _consulta(
            "SELECT g.id_genero, g.nombre_genero AS genero, COUNT(pg.id_pelicula) AS cantidad "
            "FROM generos g INNER JOIN pelicula_generos pg ON pg.id_genero = g.id_genero "
            "GROUP BY g.id_genero, g.nombre_genero ORDER BY cantidad DESC, g.nombre_genero ASC"
        )
        return jsonify({"total": sum(f["cantidad"] for f in filas), "datos": filas, "grafico": _grafico(filas, "genero")})
    except Exception as exc:
        return _fallo_lectura(exc)


@entretenimiento_bp.get("/reportes/frecuencia-libros-anio")
@token_required
def reporte_frecuencia_libros_anio(id_usuario):
    try:
        f1 = queries._entero(request.args.get("f1"), "f1", 1, 9999, obligatorio=False)
        f2 = queries._entero(request.args.get("f2"), "f2", 1, 9999, obligatorio=False)
        if f1 is not None and f2 is not None and f1 > f2:
            raise ValueError("El año f1 no puede ser mayor que el año f2")
        condiciones = ["anio_publicacion IS NOT NULL"]
        params = []
        if f1 is not None:
            condiciones.append("anio_publicacion >= %s")
            params.append(f1)
        if f2 is not None:
            condiciones.append("anio_publicacion <= %s")
            params.append(f2)
        filas = _consulta(
            "SELECT anio_publicacion AS anio, COUNT(*) AS cantidad FROM libros "
            f"WHERE {' AND '.join(condiciones)} GROUP BY anio_publicacion ORDER BY anio_publicacion ASC",
            params,
        )
        return jsonify(
            {
                "parametros": {"f1": f1, "f2": f2},
                "total": sum(f["cantidad"] for f in filas),
                "datos": filas,
                "grafico": _grafico(filas, "anio"),
            }
        )
    except Exception as exc:
        return _fallo_lectura(exc)


def _grafico(filas, etiqueta):
    return {"etiquetas": [f[etiqueta] for f in filas], "valores": [f["cantidad"] for f in filas]}
