import calendar
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from database.connection import conexion, consultar, consultar_uno, en_bloques, transaccion

ORDENES_PERMITIDOS = ("ASC", "DESC")
FORMATO_FECHA_REPORTE = "%d/%m/%Y"
PATRON_PERIODO = re.compile(r"^(0[1-9]|1[0-2])/(\d{4})$")
LIMITE_MAXIMO = 1000

FROM_EMPLEADOS = (
    "FROM empleados e "
    "INNER JOIN personas p ON p.id_persona = e.id_persona "
    "INNER JOIN cargos c ON c.id_cargo = e.id_cargo "
    "INNER JOIN dependencias d ON d.id_dependencia = c.id_dependencia "
    "LEFT JOIN afiliaciones_empleado af ON af.id_afiliacion_empleado = ("
    "SELECT a2.id_afiliacion_empleado FROM afiliaciones_empleado a2 "
    "WHERE a2.id_empleado = e.id_empleado "
    "ORDER BY (a2.fecha_fin IS NULL) DESC, a2.fecha_inicio DESC, a2.id_afiliacion_empleado DESC LIMIT 1) "
    "LEFT JOIN eps ep ON ep.id_eps = af.id_eps "
    "LEFT JOIN arl ar ON ar.id_arl = af.id_arl "
    "LEFT JOIN fondos_pension fp ON fp.id_fondo_pension = af.id_fondo_pension "
)

COLUMNAS_EMPLEADO = (
    "e.id_empleado, e.codigo_personal, p.id_persona, p.nombre_completo, p.numero_documento, "
    "p.fecha_nacimiento, p.direccion_contacto, d.id_dependencia, d.nombre_dependencia AS dependencia, "
    "c.id_cargo, c.nombre_cargo AS cargo, e.salario, e.fecha_ingreso, "
    "af.id_afiliacion_empleado, af.id_eps, ep.nombre_eps AS eps, af.id_arl, ar.nombre_arl AS arl, "
    "af.id_fondo_pension, fp.nombre_fondo_pension AS pension "
)

COLUMNAS_LISTADO = (
    "e.id_empleado, e.codigo_personal, p.nombre_completo, d.nombre_dependencia AS dependencia, "
    "c.nombre_cargo AS cargo, e.fecha_ingreso, "
    "COALESCE(ep.nombre_eps, 'Sin afiliación') AS eps, "
    "COALESCE(fp.nombre_fondo_pension, 'Sin afiliación') AS pension "
)

EXPR_EPS = "COALESCE(ep.nombre_eps, 'Sin afiliación')"
EXPR_PENSION = "COALESCE(fp.nombre_fondo_pension, 'Sin afiliación')"

SQL_APORTE_PENSION = (
    "(SELECT dn.valor_aporte_pension FROM detalle_nomina dn "
    "INNER JOIN afiliaciones_empleado a3 ON a3.id_afiliacion_empleado = dn.id_afiliacion_empleado "
    "WHERE a3.id_empleado = e.id_empleado "
    "ORDER BY dn.periodo_fecha DESC, dn.id_detalle_nomina DESC LIMIT 1)"
)

SQL_NOVEDAD = (
    "SELECT n.id_novedad, n.id_detalle_nomina, e.id_empleado, e.codigo_personal, p.nombre_completo, "
    "d.nombre_dependencia AS dependencia, c.nombre_cargo AS cargo, "
    "n.id_tipo_novedad, tn.nombre_tipo_novedad AS tipo_novedad, dn.periodo_fecha, "
    "n.fecha_inicio, n.fecha_fin, n.dias_reportados, n.detalle "
    "FROM novedades n "
    "INNER JOIN tipos_novedad tn ON tn.id_tipo_novedad = n.id_tipo_novedad "
    "INNER JOIN detalle_nomina dn ON dn.id_detalle_nomina = n.id_detalle_nomina "
    "INNER JOIN afiliaciones_empleado af ON af.id_afiliacion_empleado = dn.id_afiliacion_empleado "
    "INNER JOIN empleados e ON e.id_empleado = af.id_empleado "
    "INNER JOIN personas p ON p.id_persona = e.id_persona "
    "INNER JOIN cargos c ON c.id_cargo = e.id_cargo "
    "INNER JOIN dependencias d ON d.id_dependencia = c.id_dependencia "
)


def validar_orden(orden):
    if orden is None or str(orden).strip() == "":
        return "ASC"
    valor = str(orden).strip().upper()
    if valor not in ORDENES_PERMITIDOS:
        raise ValueError("El parámetro 'orden' debe ser ASC o DESC")
    return valor


def _valor_json(valor, formato_fecha):
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, datetime):
        return valor.isoformat(sep=" ")
    if isinstance(valor, date):
        return valor.strftime(formato_fecha) if formato_fecha else valor.isoformat()
    return valor


def _normalizar(fila, formato_fecha=None):
    if fila is None:
        return None
    return {clave: _valor_json(valor, formato_fecha) for clave, valor in fila.items()}


def _normalizar_filas(filas, formato_fecha=None):
    return [_normalizar(fila, formato_fecha) for fila in filas]


def _consultar(sql, params=None, formato_fecha=None):
    return _normalizar_filas(consultar(sql, params), formato_fecha)


def _texto(valor, campo, maximo, obligatorio=True):
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        if obligatorio:
            raise ValueError(f"El campo '{campo}' es obligatorio")
        return None
    if isinstance(valor, (dict, list, bool)):
        raise ValueError(f"El campo '{campo}' debe ser texto")
    texto = re.sub(r"\s+", " ", str(valor)).strip()
    if len(texto) > maximo:
        raise ValueError(f"El campo '{campo}' no puede superar {maximo} caracteres")
    return texto


def _entero(valor, campo, minimo=None, maximo=None, obligatorio=True):
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        if obligatorio:
            raise ValueError(f"El campo '{campo}' es obligatorio")
        return None
    if isinstance(valor, bool):
        raise ValueError(f"El campo '{campo}' debe ser un número entero")
    try:
        numero = int(str(valor).strip())
    except (TypeError, ValueError):
        raise ValueError(f"El campo '{campo}' debe ser un número entero")
    if minimo is not None and numero < minimo:
        raise ValueError(f"El campo '{campo}' debe ser mayor o igual a {minimo}")
    if maximo is not None and numero > maximo:
        raise ValueError(f"El campo '{campo}' debe ser menor o igual a {maximo}")
    return numero


def _fecha(valor, campo, obligatorio=True):
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        if obligatorio:
            raise ValueError(f"El campo '{campo}' es obligatorio")
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    for formato in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    raise ValueError(f"El campo '{campo}' debe tener formato AAAA-MM-DD o DD/MM/AAAA")


def _dinero(valor, campo):
    if valor is None or isinstance(valor, bool) or (isinstance(valor, str) and not valor.strip()):
        raise ValueError(f"El campo '{campo}' es obligatorio")
    try:
        numero = Decimal(str(valor).strip())
    except InvalidOperation:
        raise ValueError(f"El campo '{campo}' debe ser numérico")
    if not numero.is_finite() or numero < 0 or numero > Decimal("999999999999.99"):
        raise ValueError(f"El campo '{campo}' debe estar entre 0 y 999999999999.99")
    return numero.quantize(Decimal("0.01"))


def parsear_periodo(texto, campo):
    coincidencia = PATRON_PERIODO.match(str(texto or "").strip())
    if not coincidencia:
        raise ValueError(f"El parámetro '{campo}' es obligatorio y debe tener formato MM/AAAA")
    return int(coincidencia.group(2)), int(coincidencia.group(1))


def rango_desde_periodos(f1, f2):
    anio1, mes1 = parsear_periodo(f1, "f1")
    anio2, mes2 = parsear_periodo(f2, "f2")
    inicio = date(anio1, mes1, 1)
    fin = date(anio2, mes2, calendar.monthrange(anio2, mes2)[1])
    if inicio > fin:
        raise ValueError("El periodo f1 no puede ser posterior al periodo f2")
    return inicio, fin


def _paginacion(limite, desplazamiento):
    tope = _entero(limite, "limite", 1, LIMITE_MAXIMO, obligatorio=False) or 500
    salto = _entero(desplazamiento, "offset", 0, obligatorio=False) or 0
    return tope, salto


def _patron_busqueda(texto):
    escapado = str(texto).strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escapado}%"


def _agrupar(filas, claves):
    grupos = []
    indice = {}
    for fila in filas:
        clave = tuple(fila[k] for k in claves)
        if clave not in indice:
            grupo = {k: fila[k] for k in claves}
            grupo["cantidad"] = 0
            grupo["empleados"] = []
            indice[clave] = grupo
            grupos.append(grupo)
        grupo = indice[clave]
        grupo["empleados"].append({k: v for k, v in fila.items() if k not in claves})
        grupo["cantidad"] += 1
    return grupos


def _dataset_torta(filas, etiqueta):
    total = sum(f["cantidad"] for f in filas)
    return {
        "etiquetas": [f[etiqueta] for f in filas],
        "valores": [f["cantidad"] for f in filas],
        "porcentajes": [round(f["cantidad"] * 100 / total, 2) if total else 0 for f in filas],
        "total": total,
    }


def _dataset_barras(filas, eje, serie):
    ejes = sorted({f[eje] for f in filas})
    series = sorted({f[serie] for f in filas})
    valores = {(f[eje], f[serie]): f["cantidad"] for f in filas}
    return {
        "etiquetas": ejes,
        "series": [
            {"nombre": s, "valores": [valores.get((e, s), 0) for e in ejes]}
            for s in series
        ],
    }


def listar_dependencias():
    return _consultar(
        "SELECT id_dependencia, nombre_dependencia FROM dependencias ORDER BY nombre_dependencia ASC"
    )


def listar_cargos(id_dependencia=None):
    sql = (
        "SELECT c.id_cargo, c.id_dependencia, d.nombre_dependencia, c.nombre_cargo "
        "FROM cargos c INNER JOIN dependencias d ON d.id_dependencia = c.id_dependencia "
    )
    params = []
    if id_dependencia is not None:
        sql += "WHERE c.id_dependencia = %s "
        params.append(_entero(id_dependencia, "id_dependencia", 1))
    sql += "ORDER BY d.nombre_dependencia ASC, c.nombre_cargo ASC"
    return _consultar(sql, params)


def listar_eps():
    return _consultar("SELECT id_eps, nombre_eps FROM eps ORDER BY nombre_eps ASC")


def listar_arl():
    return _consultar("SELECT id_arl, nombre_arl FROM arl ORDER BY nombre_arl ASC")


def listar_fondos_pension():
    return _consultar(
        "SELECT id_fondo_pension, nombre_fondo_pension FROM fondos_pension ORDER BY nombre_fondo_pension ASC"
    )


def listar_tipos_novedad():
    return _consultar(
        "SELECT id_tipo_novedad, nombre_tipo_novedad FROM tipos_novedad ORDER BY nombre_tipo_novedad ASC"
    )


def listar_nominas():
    return _consultar(
        "SELECT id_nomina, id_archivo, descripcion, fecha_liquidacion, estado "
        "FROM nominas ORDER BY fecha_liquidacion DESC, id_nomina DESC"
    )


def obtener_catalogos():
    return {
        "dependencias": listar_dependencias(),
        "cargos": listar_cargos(),
        "eps": listar_eps(),
        "arl": listar_arl(),
        "fondos_pension": listar_fondos_pension(),
        "tipos_novedad": listar_tipos_novedad(),
        "nominas": listar_nominas(),
    }


def _leer_empleado(cursor, id_empleado, bloquear=False):
    sufijo = " FOR UPDATE" if bloquear else ""
    cursor.execute(
        f"SELECT {COLUMNAS_EMPLEADO} {FROM_EMPLEADOS} WHERE e.id_empleado = %s{sufijo}",
        (id_empleado,),
    )
    return _normalizar(cursor.fetchone())


def obtener_empleado(id_empleado):
    fila = consultar_uno(
        f"SELECT {COLUMNAS_EMPLEADO} {FROM_EMPLEADOS} WHERE e.id_empleado = %s", (id_empleado,)
    )
    return _normalizar(fila)


def listar_empleados(busqueda=None, id_dependencia=None, id_cargo=None, orden="ASC", limite=None, desplazamiento=None):
    orden = validar_orden(orden)
    tope, salto = _paginacion(limite, desplazamiento)
    condiciones = []
    params = []
    if busqueda is not None and str(busqueda).strip():
        patron = _patron_busqueda(busqueda)
        condiciones.append("(p.nombre_completo LIKE %s OR e.codigo_personal LIKE %s OR p.numero_documento LIKE %s)")
        params.extend([patron, patron, patron])
    if id_dependencia is not None:
        condiciones.append("d.id_dependencia = %s")
        params.append(_entero(id_dependencia, "id_dependencia", 1))
    if id_cargo is not None:
        condiciones.append("c.id_cargo = %s")
        params.append(_entero(id_cargo, "id_cargo", 1))
    where = f"WHERE {' AND '.join(condiciones)} " if condiciones else ""
    params.extend([tope, salto])
    return _consultar(
        f"SELECT {COLUMNAS_EMPLEADO} {FROM_EMPLEADOS} {where}"
        f"ORDER BY p.nombre_completo {orden}, e.id_empleado ASC LIMIT %s OFFSET %s",
        params,
    )


def _campos_empleado(datos, parcial):
    persona = {}
    empleado = {}
    afiliacion = {}

    def presente(campo):
        return campo in datos if parcial else True

    if presente("nombre_completo"):
        persona["nombre_completo"] = _texto(datos.get("nombre_completo"), "nombre_completo", 150)
    if presente("numero_documento"):
        persona["numero_documento"] = _texto(datos.get("numero_documento"), "numero_documento", 30, False)
    if presente("fecha_nacimiento"):
        persona["fecha_nacimiento"] = _fecha(datos.get("fecha_nacimiento"), "fecha_nacimiento", False)
    if presente("direccion_contacto"):
        persona["direccion_contacto"] = _texto(datos.get("direccion_contacto"), "direccion_contacto", 200, False)
    if presente("id_cargo"):
        empleado["id_cargo"] = _entero(datos.get("id_cargo"), "id_cargo", 1)
    if presente("codigo_personal"):
        empleado["codigo_personal"] = _texto(datos.get("codigo_personal"), "codigo_personal", 30)
    if presente("salario"):
        empleado["salario"] = _dinero(datos.get("salario"), "salario")
    if presente("fecha_ingreso"):
        empleado["fecha_ingreso"] = _fecha(datos.get("fecha_ingreso"), "fecha_ingreso")
    if presente("id_eps"):
        afiliacion["id_eps"] = _entero(datos.get("id_eps"), "id_eps", 1)
    if presente("id_arl"):
        afiliacion["id_arl"] = _entero(datos.get("id_arl"), "id_arl", 1)
    if presente("id_fondo_pension"):
        afiliacion["id_fondo_pension"] = _entero(datos.get("id_fondo_pension"), "id_fondo_pension", 1)
    return persona, empleado, afiliacion


def _actualizar_tabla(cursor, tabla, columna_id, valor_id, cambios):
    if not cambios:
        return
    asignaciones = ", ".join(f"{columna} = %s" for columna in cambios)
    cursor.execute(
        f"UPDATE {tabla} SET {asignaciones} WHERE {columna_id} = %s",
        list(cambios.values()) + [valor_id],
    )


def crear_empleado(id_usuario, datos):
    persona, empleado, afiliacion = _campos_empleado(datos, parcial=False)
    fecha_afiliacion = _fecha(datos.get("fecha_afiliacion"), "fecha_afiliacion", False) or empleado["fecha_ingreso"]
    with transaccion(id_usuario) as cursor:
        cursor.execute(
            "INSERT INTO personas (nombre_completo, numero_documento, fecha_nacimiento, direccion_contacto) "
            "VALUES (%s, %s, %s, %s)",
            (
                persona["nombre_completo"],
                persona["numero_documento"],
                persona["fecha_nacimiento"],
                persona["direccion_contacto"],
            ),
        )
        id_persona = cursor.lastrowid
        cursor.execute(
            "INSERT INTO empleados (id_persona, id_cargo, codigo_personal, salario, fecha_ingreso) "
            "VALUES (%s, %s, %s, %s, %s)",
            (
                id_persona,
                empleado["id_cargo"],
                empleado["codigo_personal"],
                empleado["salario"],
                empleado["fecha_ingreso"],
            ),
        )
        id_empleado = cursor.lastrowid
        cursor.execute(
            "INSERT INTO afiliaciones_empleado (id_empleado, id_eps, id_arl, id_fondo_pension, fecha_inicio) "
            "VALUES (%s, %s, %s, %s, %s)",
            (
                id_empleado,
                afiliacion["id_eps"],
                afiliacion["id_arl"],
                afiliacion["id_fondo_pension"],
                fecha_afiliacion,
            ),
        )
        return id_empleado, _leer_empleado(cursor, id_empleado)


def actualizar_empleado(id_usuario, id_empleado, datos):
    persona, empleado, afiliacion = _campos_empleado(datos, parcial=True)
    if not (persona or empleado or afiliacion):
        raise ValueError("No se enviaron campos para actualizar")
    with transaccion(id_usuario) as cursor:
        anterior = _leer_empleado(cursor, id_empleado, bloquear=True)
        if anterior is None:
            raise LookupError("El empleado no existe")
        _actualizar_tabla(cursor, "personas", "id_persona", anterior["id_persona"], persona)
        _actualizar_tabla(cursor, "empleados", "id_empleado", id_empleado, empleado)
        if afiliacion:
            if anterior["id_afiliacion_empleado"] is not None:
                _actualizar_tabla(
                    cursor,
                    "afiliaciones_empleado",
                    "id_afiliacion_empleado",
                    anterior["id_afiliacion_empleado"],
                    afiliacion,
                )
            else:
                completa = {
                    "id_eps": afiliacion.get("id_eps"),
                    "id_arl": afiliacion.get("id_arl"),
                    "id_fondo_pension": afiliacion.get("id_fondo_pension"),
                }
                if any(v is None for v in completa.values()):
                    raise ValueError("El empleado no tiene afiliación: envíe id_eps, id_arl e id_fondo_pension")
                cursor.execute(
                    "INSERT INTO afiliaciones_empleado (id_empleado, id_eps, id_arl, id_fondo_pension, fecha_inicio) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (
                        id_empleado,
                        completa["id_eps"],
                        completa["id_arl"],
                        completa["id_fondo_pension"],
                        _fecha(anterior["fecha_ingreso"], "fecha_ingreso"),
                    ),
                )
        return anterior, _leer_empleado(cursor, id_empleado)


def eliminar_empleado(id_usuario, id_empleado):
    with transaccion(id_usuario) as cursor:
        anterior = _leer_empleado(cursor, id_empleado, bloquear=True)
        if anterior is None:
            raise LookupError("El empleado no existe")
        cursor.execute("DELETE FROM empleados WHERE id_empleado = %s", (id_empleado,))
        cursor.execute(
            "SELECT 1 AS usada FROM usuarios WHERE id_persona = %s LIMIT 1", (anterior["id_persona"],)
        )
        if cursor.fetchone() is None:
            cursor.execute("DELETE FROM personas WHERE id_persona = %s", (anterior["id_persona"],))
        return anterior


def listar_novedades(id_empleado=None, id_tipo_novedad=None, f1=None, f2=None, limite=None, desplazamiento=None):
    tope, salto = _paginacion(limite, desplazamiento)
    condiciones = []
    params = []
    if id_empleado is not None:
        condiciones.append("e.id_empleado = %s")
        params.append(_entero(id_empleado, "id_empleado", 1))
    if id_tipo_novedad is not None:
        condiciones.append("n.id_tipo_novedad = %s")
        params.append(_entero(id_tipo_novedad, "id_tipo_novedad", 1))
    if f1 or f2:
        inicio, fin = rango_desde_periodos(f1, f2)
        condiciones.append("dn.periodo_fecha BETWEEN %s AND %s")
        params.extend([inicio, fin])
    where = f"WHERE {' AND '.join(condiciones)} " if condiciones else ""
    params.extend([tope, salto])
    return _consultar(
        f"{SQL_NOVEDAD}{where}ORDER BY dn.periodo_fecha DESC, p.nombre_completo ASC, n.id_novedad ASC "
        "LIMIT %s OFFSET %s",
        params,
    )


def obtener_novedad(id_novedad):
    return _normalizar(consultar_uno(f"{SQL_NOVEDAD}WHERE n.id_novedad = %s", (id_novedad,)))


def _leer_novedad(cursor, id_novedad, bloquear=False):
    sufijo = " FOR UPDATE" if bloquear else ""
    cursor.execute(f"{SQL_NOVEDAD}WHERE n.id_novedad = %s{sufijo}", (id_novedad,))
    return _normalizar(cursor.fetchone())


def _resolver_detalle(cursor, datos):
    id_detalle = _entero(datos.get("id_detalle_nomina"), "id_detalle_nomina", 1, obligatorio=False)
    if id_detalle is not None:
        cursor.execute("SELECT id_detalle_nomina FROM detalle_nomina WHERE id_detalle_nomina = %s", (id_detalle,))
        if cursor.fetchone() is None:
            raise LookupError("El detalle de nómina indicado no existe")
        return id_detalle
    id_empleado = _entero(datos.get("id_empleado"), "id_empleado", 1)
    anio, mes = parsear_periodo(datos.get("periodo"), "periodo")
    cursor.execute(
        "SELECT dn.id_detalle_nomina FROM detalle_nomina dn "
        "INNER JOIN afiliaciones_empleado af ON af.id_afiliacion_empleado = dn.id_afiliacion_empleado "
        "WHERE af.id_empleado = %s AND dn.periodo_fecha = %s",
        (id_empleado, date(anio, mes, 1)),
    )
    fila = cursor.fetchone()
    if fila is None:
        raise LookupError("El empleado no tiene liquidación de nómina en el periodo indicado")
    return fila["id_detalle_nomina"]


def _campos_novedad(datos, parcial):
    campos = {}

    def presente(campo):
        return campo in datos if parcial else True

    if presente("id_tipo_novedad"):
        campos["id_tipo_novedad"] = _entero(datos.get("id_tipo_novedad"), "id_tipo_novedad", 1)
    if presente("fecha_inicio"):
        campos["fecha_inicio"] = _fecha(datos.get("fecha_inicio"), "fecha_inicio", False)
    if presente("fecha_fin"):
        campos["fecha_fin"] = _fecha(datos.get("fecha_fin"), "fecha_fin", False)
    if presente("dias_reportados"):
        campos["dias_reportados"] = _entero(datos.get("dias_reportados"), "dias_reportados", 0, 31)
    if presente("detalle"):
        campos["detalle"] = _texto(datos.get("detalle"), "detalle", 1000, False)
    return campos


def _validar_fechas_novedad(inicio, fin):
    if inicio is not None and fin is not None and fin < inicio:
        raise ValueError("La fecha_fin no puede ser anterior a la fecha_inicio")


def crear_novedad(id_usuario, datos):
    campos = _campos_novedad(datos, parcial=False)
    _validar_fechas_novedad(campos["fecha_inicio"], campos["fecha_fin"])
    with transaccion(id_usuario) as cursor:
        id_detalle = _resolver_detalle(cursor, datos)
        cursor.execute(
            "INSERT INTO novedades (id_tipo_novedad, id_detalle_nomina, fecha_inicio, fecha_fin, "
            "dias_reportados, detalle) VALUES (%s, %s, %s, %s, %s, %s)",
            (
                campos["id_tipo_novedad"],
                id_detalle,
                campos["fecha_inicio"],
                campos["fecha_fin"],
                campos["dias_reportados"],
                campos["detalle"],
            ),
        )
        id_novedad = cursor.lastrowid
        return id_novedad, _leer_novedad(cursor, id_novedad)


def actualizar_novedad(id_usuario, id_novedad, datos):
    campos = _campos_novedad(datos, parcial=True)
    cambia_detalle = "id_detalle_nomina" in datos or "periodo" in datos or "id_empleado" in datos
    if not campos and not cambia_detalle:
        raise ValueError("No se enviaron campos para actualizar")
    with transaccion(id_usuario) as cursor:
        anterior = _leer_novedad(cursor, id_novedad, bloquear=True)
        if anterior is None:
            raise LookupError("La novedad no existe")
        if cambia_detalle:
            base = {
                "id_empleado": datos.get("id_empleado", anterior["id_empleado"]),
                "periodo": datos.get("periodo"),
                "id_detalle_nomina": datos.get("id_detalle_nomina"),
            }
            if base["id_detalle_nomina"] is None and base["periodo"] is None:
                base["periodo"] = _fecha(anterior["periodo_fecha"], "periodo").strftime("%m/%Y")
            campos["id_detalle_nomina"] = _resolver_detalle(cursor, base)
        inicio = campos["fecha_inicio"] if "fecha_inicio" in campos else _fecha(anterior["fecha_inicio"], "fecha_inicio", False)
        fin = campos["fecha_fin"] if "fecha_fin" in campos else _fecha(anterior["fecha_fin"], "fecha_fin", False)
        _validar_fechas_novedad(inicio, fin)
        _actualizar_tabla(cursor, "novedades", "id_novedad", id_novedad, campos)
        return anterior, _leer_novedad(cursor, id_novedad)


def eliminar_novedad(id_usuario, id_novedad):
    with transaccion(id_usuario) as cursor:
        anterior = _leer_novedad(cursor, id_novedad, bloquear=True)
        if anterior is None:
            raise LookupError("La novedad no existe")
        cursor.execute("DELETE FROM novedades WHERE id_novedad = %s", (id_novedad,))
        return anterior


def _listado_empleados(orden_sql):
    return _consultar(
        f"SELECT {COLUMNAS_LISTADO} {FROM_EMPLEADOS} {orden_sql}",
        formato_fecha=FORMATO_FECHA_REPORTE,
    )


def reporte_empleados_total(orden="ASC"):
    orden = validar_orden(orden)
    filas = _listado_empleados(f"ORDER BY p.nombre_completo {orden}, e.id_empleado ASC")
    return {"total": len(filas), "empleados": filas}


def reporte_empleados_por_dependencia(orden="ASC"):
    orden = validar_orden(orden)
    filas = _listado_empleados(
        f"ORDER BY d.nombre_dependencia ASC, p.nombre_completo {orden}, e.id_empleado ASC"
    )
    return {"total": len(filas), "grupos": _agrupar(filas, ["dependencia"])}


def reporte_empleados_por_dependencia_cargo(orden="ASC"):
    orden = validar_orden(orden)
    filas = _listado_empleados(
        f"ORDER BY d.nombre_dependencia ASC, c.nombre_cargo ASC, p.nombre_completo {orden}, e.id_empleado ASC",
    )
    return {"total": len(filas), "grupos": _agrupar(filas, ["dependencia", "cargo"])}


def frecuencia_por_dependencia():
    filas = _consultar(
        "SELECT d.nombre_dependencia AS dependencia, COUNT(*) AS cantidad "
        f"{FROM_EMPLEADOS} GROUP BY d.id_dependencia, d.nombre_dependencia "
        "ORDER BY d.nombre_dependencia ASC"
    )
    return {"frecuencias": filas, "grafico_torta": _dataset_torta(filas, "dependencia")}


def frecuencia_por_dependencia_cargo():
    filas = _consultar(
        "SELECT d.nombre_dependencia AS dependencia, c.nombre_cargo AS cargo, COUNT(*) AS cantidad "
        f"{FROM_EMPLEADOS} GROUP BY d.id_dependencia, d.nombre_dependencia, c.id_cargo, c.nombre_cargo "
        "ORDER BY d.nombre_dependencia ASC, c.nombre_cargo ASC"
    )
    return {"frecuencias": filas, "grafico_barras": _dataset_barras(filas, "dependencia", "cargo")}


def reporte_nomina_general(orden="ASC"):
    orden = validar_orden(orden)
    return {
        "orden": orden,
        "total_empleados": reporte_empleados_total(orden),
        "por_dependencia": reporte_empleados_por_dependencia(orden),
        "por_dependencia_cargo": reporte_empleados_por_dependencia_cargo(orden),
        "frecuencia_dependencia": frecuencia_por_dependencia(),
        "frecuencia_dependencia_cargo": frecuencia_por_dependencia_cargo(),
    }


def _consultar_info_personal(condicion, params, orden):
    filas = _consultar(
        f"SELECT e.id_empleado, e.codigo_personal, p.nombre_completo, d.nombre_dependencia AS dependencia, "
        f"c.nombre_cargo AS cargo, e.fecha_ingreso, ep.nombre_eps AS eps, fp.nombre_fondo_pension AS pension, "
        f"{SQL_APORTE_PENSION} AS aporte_pension, e.salario "
        f"{FROM_EMPLEADOS} {condicion} ORDER BY p.nombre_completo {orden}, e.id_empleado ASC",
        params,
        FORMATO_FECHA_REPORTE,
    )
    novedades = {fila["id_empleado"]: [] for fila in filas}
    for bloque in en_bloques(list(novedades)):
        marcadores = ",".join(["%s"] * len(bloque))
        detalle = consultar(
            f"{SQL_NOVEDAD}WHERE e.id_empleado IN ({marcadores}) "
            "ORDER BY dn.periodo_fecha ASC, n.fecha_inicio ASC, n.id_novedad ASC",
            bloque,
        )
        for fila in detalle:
            periodo = fila["periodo_fecha"].strftime("%m/%Y") if fila["periodo_fecha"] else None
            novedades[fila["id_empleado"]].append(
                {
                    "id_novedad": fila["id_novedad"],
                    "tipo_novedad": fila["tipo_novedad"],
                    "periodo": periodo,
                    "fecha_inicio": _valor_json(fila["fecha_inicio"], FORMATO_FECHA_REPORTE),
                    "fecha_fin": _valor_json(fila["fecha_fin"], FORMATO_FECHA_REPORTE),
                    "dias_reportados": fila["dias_reportados"],
                    "detalle": fila["detalle"],
                }
            )
    for fila in filas:
        fila["novedades"] = novedades[fila["id_empleado"]]
        fila["cantidad_novedades"] = len(fila["novedades"])
    return filas


def reporte_info_personal(id_empleado=None, codigo_personal=None, busqueda=None, orden="ASC"):
    orden = validar_orden(orden)
    condiciones = []
    params = []
    if id_empleado is not None:
        condiciones.append("e.id_empleado = %s")
        params.append(_entero(id_empleado, "id_empleado", 1))
    if codigo_personal is not None and str(codigo_personal).strip():
        condiciones.append("e.codigo_personal = %s")
        params.append(str(codigo_personal).strip())
    if busqueda is not None and str(busqueda).strip():
        patron = _patron_busqueda(busqueda)
        condiciones.append("(p.nombre_completo LIKE %s OR e.codigo_personal LIKE %s OR p.numero_documento LIKE %s)")
        params.extend([patron, patron, patron])
    where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
    return _consultar_info_personal(where, params, orden)


def _frecuencia_simple(expresion, alias):
    return _consultar(
        f"SELECT {expresion} AS {alias}, COUNT(*) AS cantidad "
        f"{FROM_EMPLEADOS} GROUP BY {expresion} ORDER BY {alias} ASC"
    )


def _frecuencia_por_dependencia(expresion, alias):
    return _consultar(
        f"SELECT d.nombre_dependencia AS dependencia, {expresion} AS {alias}, COUNT(*) AS cantidad "
        f"{FROM_EMPLEADOS} GROUP BY d.id_dependencia, d.nombre_dependencia, {expresion} "
        f"ORDER BY d.nombre_dependencia ASC, {alias} ASC"
    )


def frecuencia_eps():
    filas = _frecuencia_simple(EXPR_EPS, "eps")
    return {"frecuencias": filas, "grafico_torta": _dataset_torta(filas, "eps")}


def frecuencia_pension():
    filas = _frecuencia_simple(EXPR_PENSION, "pension")
    return {"frecuencias": filas, "grafico_torta": _dataset_torta(filas, "pension")}


def frecuencia_eps_por_dependencia():
    filas = _frecuencia_por_dependencia(EXPR_EPS, "eps")
    return {"frecuencias": filas, "grafico_barras": _dataset_barras(filas, "dependencia", "eps")}


def frecuencia_pension_por_dependencia():
    filas = _frecuencia_por_dependencia(EXPR_PENSION, "pension")
    return {"frecuencias": filas, "grafico_barras": _dataset_barras(filas, "dependencia", "pension")}


def empleados_por_cargo_eps(orden="ASC"):
    orden = validar_orden(orden)
    filas = _listado_empleados(
        f"ORDER BY c.nombre_cargo ASC, {EXPR_EPS} ASC, p.nombre_completo {orden}, e.id_empleado ASC",
    )
    for fila in filas:
        fila.pop("pension", None)
    return {"total": len(filas), "grupos": _agrupar(filas, ["cargo", "eps"])}


def empleados_por_cargo_pension(orden="ASC"):
    orden = validar_orden(orden)
    filas = _listado_empleados(
        f"ORDER BY c.nombre_cargo ASC, {EXPR_PENSION} ASC, p.nombre_completo {orden}, e.id_empleado ASC",
    )
    for fila in filas:
        fila.pop("eps", None)
    return {"total": len(filas), "grupos": _agrupar(filas, ["cargo", "pension"])}


def reporte_salud_pension(orden="ASC"):
    orden = validar_orden(orden)
    return {
        "orden": orden,
        "frecuencia_eps": frecuencia_eps(),
        "frecuencia_pension": frecuencia_pension(),
        "eps_por_dependencia": frecuencia_eps_por_dependencia(),
        "pension_por_dependencia": frecuencia_pension_por_dependencia(),
        "cargo_eps": empleados_por_cargo_eps(orden),
        "cargo_pension": empleados_por_cargo_pension(orden),
    }


def reporte_novedades_rango(f1, f2):
    inicio, fin = rango_desde_periodos(f1, f2)
    with conexion() as conn:
        cursor = conn.cursor(dictionary=True, buffered=True)
        try:
            cursor.callproc("sp_novedades_rango", (inicio, fin))
            resultados = [resultado.fetchall() for resultado in cursor.stored_results()]
        finally:
            cursor.close()
    novedades = _normalizar_filas(resultados[0] if resultados else [], FORMATO_FECHA_REPORTE)
    por_dependencia_cargo = _normalizar_filas(resultados[1] if len(resultados) > 1 else [])
    empleados = {}
    for fila in novedades:
        clave = fila["codigo_personal"]
        if clave not in empleados:
            empleados[clave] = {
                "codigo_personal": fila["codigo_personal"],
                "nombre_completo": fila["nombre_completo"],
                "dependencia": fila["dependencia"],
                "cargo": fila["cargo"],
                "cantidad_novedades": 0,
            }
        empleados[clave]["cantidad_novedades"] += 1
    return {
        "desde": inicio.strftime(FORMATO_FECHA_REPORTE),
        "hasta": fin.strftime(FORMATO_FECHA_REPORTE),
        "total_novedades": len(novedades),
        "total_empleados": len(empleados),
        "empleados": sorted(empleados.values(), key=lambda e: (e["nombre_completo"], e["codigo_personal"])),
        "novedades": novedades,
        "por_dependencia_cargo": por_dependencia_cargo,
    }
