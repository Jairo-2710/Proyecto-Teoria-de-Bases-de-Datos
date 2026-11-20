import json
import logging

from database.connection import transaccion

logger = logging.getLogger(__name__)


def _a_json(valor):
    if valor is None:
        return None
    if isinstance(valor, str):
        try:
            json.loads(valor)
            return valor
        except ValueError:
            return json.dumps({"valor": valor}, ensure_ascii=False)
    return json.dumps(valor, ensure_ascii=False, default=str)


def registrar_auditoria(
    id_usuario,
    accion,
    detalle,
    resultado,
    tabla_afectada=None,
    datos_anteriores=None,
    datos_nuevos=None,
    id_empleado=None,
):
    try:
        with transaccion() as cursor:
            cursor.execute(
                "INSERT INTO auditoria (id_usuario, id_empleado, fecha, hora, accion, detalle, "
                "resultado, tabla_afectada, datos_anteriores, datos_nuevos) "
                "VALUES (%s, %s, CURDATE(), CURTIME(), %s, %s, %s, %s, %s, %s)",
                (
                    id_usuario,
                    id_empleado,
                    str(accion)[:100],
                    None if detalle is None else str(detalle)[:1000],
                    str(resultado)[:50],
                    tabla_afectada,
                    _a_json(datos_anteriores),
                    _a_json(datos_nuevos),
                ),
            )
            return cursor.lastrowid
    except Exception:
        logger.exception("No fue posible registrar la auditoría de la acción %s", accion)
        return None
