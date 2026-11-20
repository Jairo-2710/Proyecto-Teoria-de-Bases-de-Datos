import logging

from flask import Blueprint, jsonify, request

from database import queries
from database.connection import Error
from routes.auth import token_required
from services.audit_logger import registrar_auditoria

logger = logging.getLogger(__name__)

nomina_bp = Blueprint("nomina", __name__, url_prefix="/api/nomina")

ERRNO_DUPLICADO = 1062
ERRNO_REFERENCIADO = 1451
ERRNO_REFERENCIA_INVALIDA = 1452
ERRNO_SENTENCIA_USUARIO = 1644
ERRNOS_CHECK = (3819,)


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
            return "Ya existe un registro con un valor único repetido (código personal o documento)", 409
        if exc.errno == ERRNO_REFERENCIADO:
            return mensaje_referenciado, 409
        if exc.errno == ERRNO_REFERENCIA_INVALIDA:
            return "Alguno de los identificadores enviados no existe (cargo, EPS, ARL, fondo o tipo de novedad)", 400
        if exc.errno == ERRNO_SENTENCIA_USUARIO or exc.errno in ERRNOS_CHECK:
            return "Los datos enviados no cumplen las reglas de validación", 400
    return None, 500


def _fallo_escritura(exc, id_usuario, accion, tabla, mensaje_referenciado, id_empleado=None):
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
        id_empleado=None if isinstance(exc, LookupError) else id_empleado,
    )
    return _error(mensaje, codigo)


def _fallo_lectura(exc):
    mensaje, codigo = _traducir_error(exc, "El recurso está referenciado por otros registros")
    if codigo == 500:
        logger.exception("Error inesperado consultando nómina")
        mensaje = "No fue posible completar la consulta"
    return _error(mensaje, codigo)


@nomina_bp.get("/catalogos")
@token_required
def catalogos(id_usuario):
    try:
        return jsonify(queries.obtener_catalogos())
    except Exception as exc:
        return _fallo_lectura(exc)


@nomina_bp.get("/empleados")
@token_required
def listar_empleados(id_usuario):
    try:
        filas = queries.listar_empleados(
            busqueda=request.args.get("busqueda"),
            id_dependencia=request.args.get("id_dependencia"),
            id_cargo=request.args.get("id_cargo"),
            orden=request.args.get("orden"),
            limite=request.args.get("limite"),
            desplazamiento=request.args.get("offset"),
        )
        return jsonify({"total": len(filas), "empleados": filas})
    except Exception as exc:
        return _fallo_lectura(exc)


@nomina_bp.post("/empleados")
@token_required
def crear_empleado(id_usuario):
    try:
        id_empleado, nuevo = queries.crear_empleado(id_usuario, _cuerpo_json())
    except Exception as exc:
        return _fallo_escritura(exc, id_usuario, "INSERT", "empleados", "")
    registrar_auditoria(
        id_usuario,
        "INSERT",
        f"Se creó el empleado con código {nuevo['codigo_personal']} desde la API de nómina",
        "EXITOSO",
        tabla_afectada="empleados",
        datos_nuevos=nuevo,
        id_empleado=id_empleado,
    )
    return jsonify(nuevo), 201


@nomina_bp.put("/empleados/<int:id_empleado>")
@token_required
def actualizar_empleado(id_usuario, id_empleado):
    try:
        anterior, nuevo = queries.actualizar_empleado(id_usuario, id_empleado, _cuerpo_json())
    except Exception as exc:
        return _fallo_escritura(exc, id_usuario, "UPDATE", "empleados", "", id_empleado)
    registrar_auditoria(
        id_usuario,
        "UPDATE",
        f"Se actualizó el empleado {nuevo['codigo_personal']} desde la API de nómina",
        "EXITOSO",
        tabla_afectada="empleados",
        datos_anteriores=anterior,
        datos_nuevos=nuevo,
        id_empleado=id_empleado,
    )
    return jsonify(nuevo)


@nomina_bp.delete("/empleados/<int:id_empleado>")
@token_required
def eliminar_empleado(id_usuario, id_empleado):
    try:
        anterior = queries.eliminar_empleado(id_usuario, id_empleado)
    except Exception as exc:
        return _fallo_escritura(
            exc,
            id_usuario,
            "DELETE",
            "empleados",
            "No se puede eliminar el empleado porque tiene liquidaciones de nómina asociadas",
            id_empleado,
        )
    registrar_auditoria(
        id_usuario,
        "DELETE",
        f"Se eliminó el empleado {anterior['codigo_personal']} desde la API de nómina",
        "EXITOSO",
        tabla_afectada="empleados",
        datos_anteriores=anterior,
    )
    return jsonify({"mensaje": "Empleado eliminado", "id_empleado": id_empleado})


@nomina_bp.get("/novedades")
@token_required
def listar_novedades(id_usuario):
    try:
        filas = queries.listar_novedades(
            id_empleado=request.args.get("id_empleado"),
            id_tipo_novedad=request.args.get("id_tipo_novedad"),
            f1=request.args.get("f1"),
            f2=request.args.get("f2"),
            limite=request.args.get("limite"),
            desplazamiento=request.args.get("offset"),
        )
        return jsonify({"total": len(filas), "novedades": filas})
    except Exception as exc:
        return _fallo_lectura(exc)


@nomina_bp.post("/novedades")
@token_required
def crear_novedad(id_usuario):
    try:
        id_novedad, nueva = queries.crear_novedad(id_usuario, _cuerpo_json())
    except Exception as exc:
        return _fallo_escritura(exc, id_usuario, "INSERT", "novedades", "")
    registrar_auditoria(
        id_usuario,
        "INSERT",
        f"Se creó la novedad {id_novedad} del empleado {nueva['codigo_personal']} desde la API de nómina",
        "EXITOSO",
        tabla_afectada="novedades",
        datos_nuevos=nueva,
        id_empleado=nueva["id_empleado"],
    )
    return jsonify(nueva), 201


@nomina_bp.put("/novedades/<int:id_novedad>")
@token_required
def actualizar_novedad(id_usuario, id_novedad):
    try:
        anterior, nueva = queries.actualizar_novedad(id_usuario, id_novedad, _cuerpo_json())
    except Exception as exc:
        return _fallo_escritura(exc, id_usuario, "UPDATE", "novedades", "")
    registrar_auditoria(
        id_usuario,
        "UPDATE",
        f"Se actualizó la novedad {id_novedad} desde la API de nómina",
        "EXITOSO",
        tabla_afectada="novedades",
        datos_anteriores=anterior,
        datos_nuevos=nueva,
        id_empleado=nueva["id_empleado"],
    )
    return jsonify(nueva)


@nomina_bp.delete("/novedades/<int:id_novedad>")
@token_required
def eliminar_novedad(id_usuario, id_novedad):
    try:
        anterior = queries.eliminar_novedad(id_usuario, id_novedad)
    except Exception as exc:
        return _fallo_escritura(exc, id_usuario, "DELETE", "novedades", "")
    registrar_auditoria(
        id_usuario,
        "DELETE",
        f"Se eliminó la novedad {id_novedad} desde la API de nómina",
        "EXITOSO",
        tabla_afectada="novedades",
        datos_anteriores=anterior,
        id_empleado=anterior["id_empleado"],
    )
    return jsonify({"mensaje": "Novedad eliminada", "id_novedad": id_novedad})


@nomina_bp.get("/reportes/general")
@token_required
def reporte_general(id_usuario):
    try:
        orden = queries.validar_orden(request.args.get("orden"))
        return jsonify(queries.reporte_nomina_general(orden))
    except Exception as exc:
        return _fallo_lectura(exc)


@nomina_bp.get("/reportes/info-personal")
@token_required
def reporte_info_personal(id_usuario):
    id_empleado = request.args.get("id_empleado")
    codigo_personal = request.args.get("codigo_personal")
    try:
        filas = queries.reporte_info_personal(
            id_empleado=id_empleado,
            codigo_personal=codigo_personal,
            busqueda=request.args.get("busqueda"),
            orden=request.args.get("orden"),
        )
        if (id_empleado or codigo_personal) and not filas:
            raise LookupError("No se encontró el empleado solicitado")
        if id_empleado or codigo_personal:
            return jsonify({"empleado": filas[0]})
        return jsonify({"total": len(filas), "empleados": filas})
    except Exception as exc:
        return _fallo_lectura(exc)


@nomina_bp.get("/reportes/salud-pension")
@token_required
def reporte_salud_pension(id_usuario):
    try:
        orden = queries.validar_orden(request.args.get("orden"))
        return jsonify(queries.reporte_salud_pension(orden))
    except Exception as exc:
        return _fallo_lectura(exc)


@nomina_bp.get("/reportes/novedades")
@token_required
def reporte_novedades(id_usuario):
    try:
        return jsonify(
            queries.reporte_novedades_rango(request.args.get("f1"), request.args.get("f2"))
        )
    except Exception as exc:
        return _fallo_lectura(exc)
