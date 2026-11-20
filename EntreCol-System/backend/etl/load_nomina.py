import calendar
import json
import re
import sys
from collections import Counter
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config import NOMINA_XLSX
from database.connection import (
    Error,
    cerrar_archivo,
    guardar_errores,
    normalizar_clave,
    registrar_archivo,
    resolver_catalogo,
    transaccion,
)
from services.audit_logger import registrar_auditoria

TASA_APORTE_PENSION = Decimal("0.04")

COL_CODIGO = "CÓDIGO"
COL_NOMBRE = "NOMBRE DEL EMPLEADO"
COL_DEPENDENCIA = "DEPENDENCIA"
COL_CARGO = "CARGO"
COL_FECHA_INGRESO = "FECHA INGRESO"
COL_EPS = "EPS"
COL_ARL = "ARL"
COL_PENSION = "PENSIÓN"
COL_SUELDO = "SUELDO"

COL_NOV_INCAPACIDAD = "NOVEDAD INCAPACIDAD"
COL_NOV_VACACIONES = "NOVEDAD VACACIONES"
COL_DIAS_TRABAJADOS = "NUMERO DIAS TRABAJADOS EN EL MES"
COL_DIAS_INCAPACIDAD = "NUMERO DIAS INCAPACIDADES EN EL MES"
COL_DIAS_VACACIONES = "NUMERO DE DIAS VACACIONES"
COL_INICIO_VACACIONES = "FECHA DE INICIO DE VACACIONES"
COL_FIN_VACACIONES = "FECHA TERMINACION DE VACACIONES"
COL_INICIO_INCAPACIDAD = "FECHA INICIO INCAPACIDAD"
COL_FIN_INCAPACIDAD = "FECHA TERMINACIÓN INCAPACIDAD"
COL_BONIFICACION = "BONIFICACIÓN"
COL_TRANSPORTE = "TRANSPORTE"

COLUMNAS_EMPLEADOS = [
    COL_CODIGO, COL_NOMBRE, COL_DEPENDENCIA, COL_CARGO, COL_FECHA_INGRESO,
    COL_EPS, COL_ARL, COL_PENSION, COL_SUELDO,
]
COLUMNAS_MENSUALES = [
    COL_CODIGO, COL_NOV_INCAPACIDAD, COL_NOV_VACACIONES, COL_DIAS_TRABAJADOS,
    COL_DIAS_INCAPACIDAD, COL_DIAS_VACACIONES, COL_INICIO_VACACIONES,
    COL_FIN_VACACIONES, COL_INICIO_INCAPACIDAD, COL_FIN_INCAPACIDAD,
    COL_BONIFICACION, COL_TRANSPORTE,
]

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def _vacio(valor):
    if valor is None:
        return True
    try:
        if pd.isna(valor):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(valor, str) and not valor.strip()


def _texto(valor):
    if _vacio(valor):
        return None
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return re.sub(r"\s+", " ", str(valor)).strip()


def _entero(valor, por_defecto=None):
    if _vacio(valor):
        return por_defecto
    try:
        return int(Decimal(str(valor).strip().replace(",", ".")))
    except (InvalidOperation, ValueError):
        raise ValueError(f"valor no numérico: {valor!r}")


def _decimal(valor, por_defecto=None):
    if _vacio(valor):
        return por_defecto
    try:
        return Decimal(str(valor).strip().replace(",", "."))
    except InvalidOperation:
        raise ValueError(f"valor no numérico: {valor!r}")


def _fecha(valor):
    if _vacio(valor):
        return None
    if isinstance(valor, pd.Timestamp):
        return valor.date()
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    texto = str(valor).strip()
    for formato in ("%Y%m%d", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    raise ValueError(f"fecha inválida: {valor!r}")


def _crudo(fila):
    salida = {}
    for clave, valor in fila.items():
        if _vacio(valor):
            salida[str(clave)] = None
        elif isinstance(valor, (pd.Timestamp, datetime, date)):
            salida[str(clave)] = valor.isoformat()
        else:
            salida[str(clave)] = str(valor)
    return json.dumps(salida, ensure_ascii=False)


def _renombrar_columnas(df, esperadas):
    equivalencias = {normalizar_clave(c): c for c in esperadas}
    renombres = {}
    for columna in df.columns:
        destino = equivalencias.get(normalizar_clave(columna))
        if destino:
            renombres[columna] = destino
    df = df.rename(columns=renombres)
    faltantes = [c for c in esperadas if c not in df.columns]
    return df, faltantes


def _inferir_periodo(nombre_hoja, df):
    texto = normalizar_clave(nombre_hoja)
    coincidencia = re.search(r"(20\d{2})[-_/ .]?(0?[1-9]|1[0-2])\b", texto)
    if coincidencia:
        return date(int(coincidencia.group(1)), int(coincidencia.group(2)), 1)
    coincidencia = re.search(r"\b(0?[1-9]|1[0-2])[-_/ .](20\d{2})\b", texto)
    if coincidencia:
        return date(int(coincidencia.group(2)), int(coincidencia.group(1)), 1)
    for nombre_mes, numero in MESES.items():
        coincidencia = re.search(rf"{nombre_mes}\D*(20\d{{2}})", texto)
        if coincidencia:
            return date(int(coincidencia.group(1)), numero, 1)
    meses = []
    for columna in (COL_INICIO_INCAPACIDAD, COL_FIN_INCAPACIDAD, COL_INICIO_VACACIONES, COL_FIN_VACACIONES):
        if columna in df.columns:
            for valor in df[columna]:
                try:
                    fecha = _fecha(valor)
                except ValueError:
                    fecha = None
                if fecha:
                    meses.append((fecha.year, fecha.month))
    if meses:
        conteo = Counter(meses)
        mejor = max(conteo.values())
        anio, mes = min(m for m, c in conteo.items() if c == mejor)
        return date(anio, mes, 1)
    hoy = date.today()
    return date(hoy.year, hoy.month, 1)


def _ultimo_dia(periodo):
    return date(periodo.year, periodo.month, calendar.monthrange(periodo.year, periodo.month)[1])


def _cargar_empleados(cursor, df, errores, resumen):
    df, faltantes = _renombrar_columnas(df, COLUMNAS_EMPLEADOS)
    if faltantes:
        raise ValueError(f"La primera hoja no contiene las columnas: {', '.join(faltantes)}")

    filas_validas = []
    for indice, fila in df.iterrows():
        numero_fila = int(indice) + 2
        if all(_vacio(v) for v in fila.values):
            continue
        try:
            codigo = _texto(fila[COL_CODIGO])
            nombre = _texto(fila[COL_NOMBRE])
            dependencia = _texto(fila[COL_DEPENDENCIA])
            cargo = _texto(fila[COL_CARGO])
            eps = _texto(fila[COL_EPS])
            arl = _texto(fila[COL_ARL])
            pension = _texto(fila[COL_PENSION])
            ingreso = _fecha(fila[COL_FECHA_INGRESO])
            sueldo = _decimal(fila[COL_SUELDO])
            obligatorios = {
                "CÓDIGO": codigo, "NOMBRE DEL EMPLEADO": nombre, "DEPENDENCIA": dependencia,
                "CARGO": cargo, "EPS": eps, "ARL": arl, "PENSIÓN": pension,
                "FECHA INGRESO": ingreso, "SUELDO": sueldo,
            }
            vacios = [k for k, v in obligatorios.items() if v is None]
            if vacios:
                raise ValueError(f"campos obligatorios vacíos: {', '.join(vacios)}")
            if sueldo < 0:
                raise ValueError("el sueldo no puede ser negativo")
            if len(codigo) > 30:
                raise ValueError("el código excede 30 caracteres")
        except ValueError as exc:
            errores.append((numero_fila, str(exc), _crudo(fila)))
            continue
        filas_validas.append((numero_fila, fila, codigo, nombre, dependencia, cargo, eps, arl, pension, ingreso, sueldo))

    mapa_dep = resolver_catalogo(cursor, "dependencias", "id_dependencia", "nombre_dependencia", [f[4] for f in filas_validas], 100)
    mapa_eps = resolver_catalogo(cursor, "eps", "id_eps", "nombre_eps", [f[6] for f in filas_validas], 100)
    mapa_arl = resolver_catalogo(cursor, "arl", "id_arl", "nombre_arl", [f[7] for f in filas_validas], 100)
    mapa_pen = resolver_catalogo(cursor, "fondos_pension", "id_fondo_pension", "nombre_fondo_pension", [f[8] for f in filas_validas], 100)
    resolver_catalogo(cursor, "tipos_novedad", "id_tipo_novedad", "nombre_tipo_novedad", ["INCAPACIDAD", "VACACIONES"], 100)

    for numero_fila, fila, codigo, nombre, dependencia, cargo, eps, arl, pension, ingreso, sueldo in filas_validas:
        cursor.execute("SAVEPOINT fila_empleado")
        try:
            id_dep = mapa_dep[normalizar_clave(dependencia)]
            cursor.execute(
                "INSERT IGNORE INTO cargos (id_dependencia, nombre_cargo) VALUES (%s, %s)",
                (id_dep, cargo[:100]),
            )
            cursor.execute(
                "SELECT id_cargo FROM cargos WHERE id_dependencia = %s AND nombre_cargo = %s",
                (id_dep, cargo[:100]),
            )
            id_cargo = cursor.fetchone()["id_cargo"]

            cursor.execute("SELECT id_persona FROM empleados WHERE codigo_personal = %s", (codigo,))
            existente = cursor.fetchone()
            if existente:
                id_persona = existente["id_persona"]
                cursor.execute(
                    "UPDATE personas SET nombre_completo = %s WHERE id_persona = %s",
                    (nombre[:150], id_persona),
                )
            else:
                cursor.execute("INSERT INTO personas (nombre_completo) VALUES (%s)", (nombre[:150],))
                id_persona = cursor.lastrowid
                resumen["personas"] += 1

            cursor.execute(
                "INSERT INTO empleados (id_persona, id_cargo, codigo_personal, salario, fecha_ingreso) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE id_cargo = VALUES(id_cargo), salario = VALUES(salario), "
                "fecha_ingreso = VALUES(fecha_ingreso)",
                (id_persona, id_cargo, codigo, sueldo, ingreso),
            )
            cursor.execute("SELECT id_empleado FROM empleados WHERE codigo_personal = %s", (codigo,))
            id_empleado = cursor.fetchone()["id_empleado"]

            cursor.execute(
                "INSERT INTO afiliaciones_empleado "
                "(id_empleado, id_eps, id_arl, id_fondo_pension, fecha_inicio, fecha_fin) "
                "VALUES (%s, %s, %s, %s, %s, NULL) "
                "ON DUPLICATE KEY UPDATE id_eps = VALUES(id_eps), id_arl = VALUES(id_arl), "
                "id_fondo_pension = VALUES(id_fondo_pension)",
                (id_empleado, mapa_eps[normalizar_clave(eps)], mapa_arl[normalizar_clave(arl)], mapa_pen[normalizar_clave(pension)], ingreso),
            )
            resumen["empleados"] += 1
        except (Error, KeyError) as exc:
            cursor.execute("ROLLBACK TO SAVEPOINT fila_empleado")
            errores.append((numero_fila, f"Error al guardar el empleado: {exc}", _crudo(fila)))
        else:
            cursor.execute("RELEASE SAVEPOINT fila_empleado")


def _datos_empleado(cursor, codigo):
    cursor.execute(
        "SELECT a.id_afiliacion_empleado, c.id_dependencia "
        "FROM empleados e "
        "INNER JOIN cargos c ON c.id_cargo = e.id_cargo "
        "INNER JOIN afiliaciones_empleado a ON a.id_empleado = e.id_empleado "
        "WHERE e.codigo_personal = %s "
        "ORDER BY a.fecha_inicio DESC LIMIT 1",
        (codigo,),
    )
    return cursor.fetchone()


def _id_tipo_novedad(cursor, nombre):
    cursor.execute("SELECT id_tipo_novedad FROM tipos_novedad WHERE nombre_tipo_novedad = %s", (nombre,))
    return cursor.fetchone()["id_tipo_novedad"]


def _guardar_novedad(cursor, id_tipo, id_detalle, inicio, fin, dias, detalle, resumen):
    cursor.execute(
        "SELECT id_novedad FROM novedades WHERE id_detalle_nomina = %s AND id_tipo_novedad = %s "
        "AND fecha_inicio <=> %s",
        (id_detalle, id_tipo, inicio),
    )
    existente = cursor.fetchone()
    if existente:
        cursor.execute(
            "UPDATE novedades SET fecha_fin = %s, dias_reportados = %s, detalle = %s WHERE id_novedad = %s",
            (fin, dias, detalle, existente["id_novedad"]),
        )
    else:
        cursor.execute(
            "INSERT INTO novedades (id_tipo_novedad, id_detalle_nomina, fecha_inicio, fecha_fin, dias_reportados, detalle) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (id_tipo, id_detalle, inicio, fin, dias, detalle),
        )
        resumen["novedades"] += 1


def _cargar_hoja_mensual(cursor, id_archivo, nombre_hoja, df, errores, resumen):
    df, faltantes = _renombrar_columnas(df, COLUMNAS_MENSUALES)
    if faltantes:
        errores.append((None, f"La hoja '{nombre_hoja}' no contiene las columnas: {', '.join(faltantes)}", None))
        return

    periodo = _inferir_periodo(nombre_hoja, df)
    descripcion = f"Nómina {nombre_hoja} {periodo.strftime('%Y-%m')}"[:200]
    liquidacion = _ultimo_dia(periodo)

    cursor.execute(
        "SELECT id_nomina FROM nominas WHERE descripcion = %s AND fecha_liquidacion = %s",
        (descripcion, liquidacion),
    )
    existente = cursor.fetchone()
    if existente:
        id_nomina = existente["id_nomina"]
        cursor.execute("UPDATE nominas SET id_archivo = %s WHERE id_nomina = %s", (id_archivo, id_nomina))
    else:
        cursor.execute(
            "INSERT INTO nominas (id_archivo, descripcion, fecha_liquidacion, estado) VALUES (%s, %s, %s, 'ABIERTA')",
            (id_archivo, descripcion, liquidacion),
        )
        id_nomina = cursor.lastrowid
        resumen["nominas"] += 1

    id_incapacidad = _id_tipo_novedad(cursor, "INCAPACIDAD")
    id_vacaciones = _id_tipo_novedad(cursor, "VACACIONES")

    for indice, fila in df.iterrows():
        numero_fila = int(indice) + 2
        if all(_vacio(v) for v in fila.values):
            continue
        cursor.execute("SAVEPOINT fila_nomina")
        try:
            codigo = _texto(fila[COL_CODIGO])
            if not codigo:
                raise ValueError("CÓDIGO vacío")
            empleado = _datos_empleado(cursor, codigo)
            if not empleado:
                raise ValueError(f"No existe empleado con código {codigo} en la primera hoja")

            dias_trabajados = _entero(fila[COL_DIAS_TRABAJADOS], 30)
            dias_incapacidad = _entero(fila[COL_DIAS_INCAPACIDAD], 0)
            dias_vacaciones = _entero(fila[COL_DIAS_VACACIONES], 0)
            bonificacion = _decimal(fila[COL_BONIFICACION], Decimal("0"))
            transporte = _decimal(fila[COL_TRANSPORTE], Decimal("0"))
            for etiqueta, valor in (
                ("días trabajados", dias_trabajados),
                ("días de incapacidad", dias_incapacidad),
                ("días de vacaciones", dias_vacaciones),
            ):
                if not 0 <= valor <= 31:
                    raise ValueError(f"{etiqueta} fuera de rango (0-31): {valor}")
            if bonificacion < 0 or transporte < 0:
                raise ValueError("bonificación o transporte negativos")

            ini_inc = _fecha(fila[COL_INICIO_INCAPACIDAD])
            fin_inc = _fecha(fila[COL_FIN_INCAPACIDAD])
            ini_vac = _fecha(fila[COL_INICIO_VACACIONES])
            fin_vac = _fecha(fila[COL_FIN_VACACIONES])
            if ini_inc and fin_inc and fin_inc < ini_inc:
                raise ValueError("la fecha de terminación de la incapacidad es anterior al inicio")
            if ini_vac and fin_vac and fin_vac < ini_vac:
                raise ValueError("la fecha de terminación de las vacaciones es anterior al inicio")

            cursor.execute(
                "SELECT e.salario FROM empleados e WHERE e.codigo_personal = %s", (codigo,)
            )
            salario = cursor.fetchone()["salario"]
            aporte = (Decimal(salario) * TASA_APORTE_PENSION).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            cursor.execute(
                "INSERT INTO detalle_nomina (id_nomina, id_afiliacion_empleado, id_dependencia, periodo_fecha, "
                "dias_trabajados, valor_bonificacion, valor_transporte, valor_aporte_pension) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE id_nomina = VALUES(id_nomina), id_dependencia = VALUES(id_dependencia), "
                "dias_trabajados = VALUES(dias_trabajados), valor_bonificacion = VALUES(valor_bonificacion), "
                "valor_transporte = VALUES(valor_transporte), valor_aporte_pension = VALUES(valor_aporte_pension)",
                (
                    id_nomina, empleado["id_afiliacion_empleado"], empleado["id_dependencia"], periodo,
                    dias_trabajados, bonificacion, transporte, aporte,
                ),
            )
            cursor.execute(
                "SELECT id_detalle_nomina FROM detalle_nomina WHERE id_afiliacion_empleado = %s AND periodo_fecha = %s",
                (empleado["id_afiliacion_empleado"], periodo),
            )
            id_detalle = cursor.fetchone()["id_detalle_nomina"]
            resumen["detalles"] += 1

            marca_inc = bool(_texto(fila[COL_NOV_INCAPACIDAD])) or dias_incapacidad > 0 or ini_inc is not None
            if marca_inc:
                _guardar_novedad(
                    cursor, id_incapacidad, id_detalle, ini_inc, fin_inc, dias_incapacidad,
                    f"Incapacidad de {dias_incapacidad} días reportada en {nombre_hoja}", resumen,
                )
            marca_vac = bool(_texto(fila[COL_NOV_VACACIONES])) or dias_vacaciones > 0 or ini_vac is not None
            if marca_vac:
                _guardar_novedad(
                    cursor, id_vacaciones, id_detalle, ini_vac, fin_vac, dias_vacaciones,
                    f"Vacaciones de {dias_vacaciones} días reportadas en {nombre_hoja}", resumen,
                )
        except (ValueError, Error) as exc:
            cursor.execute("ROLLBACK TO SAVEPOINT fila_nomina")
            errores.append((numero_fila, f"[{nombre_hoja}] {exc}", _crudo(fila)))
        else:
            cursor.execute("RELEASE SAVEPOINT fila_nomina")


def ejecutar_etl_nomina(ruta_archivo=None, id_usuario=None):
    ruta = Path(ruta_archivo or NOMINA_XLSX)
    if not ruta.is_file():
        raise FileNotFoundError(f"No se encontró el archivo {ruta}")

    hojas = pd.read_excel(ruta, sheet_name=None, dtype=object)
    if not hojas:
        raise ValueError("El archivo no contiene hojas")

    id_archivo = registrar_archivo(ruta.name, "NOMINA", id_usuario)
    errores = []
    resumen = {"personas": 0, "empleados": 0, "nominas": 0, "detalles": 0, "novedades": 0}

    try:
        nombres = list(hojas.keys())
        with transaccion(id_usuario) as cursor:
            _cargar_empleados(cursor, hojas[nombres[0]], errores, resumen)
            for nombre_hoja in nombres[1:]:
                _cargar_hoja_mensual(cursor, id_archivo, nombre_hoja, hojas[nombre_hoja], errores, resumen)
    except Exception as exc:
        errores.append((None, f"Fallo general de la carga: {exc}", None))
        guardar_errores(id_archivo, errores)
        cerrar_archivo(id_archivo, "FALLIDO")
        registrar_auditoria(
            id_usuario, "ETL_NOMINA", f"Falló la carga de {ruta.name}: {exc}", "FALLIDO",
            tabla_afectada="archivos", datos_nuevos={"id_archivo": id_archivo},
        )
        return {"id_archivo": id_archivo, "estado": "FALLIDO", "error": str(exc), "errores": len(errores), **resumen}

    guardar_errores(id_archivo, errores)
    estado = "CON_ERRORES" if errores else "PROCESADO"
    cerrar_archivo(id_archivo, estado)
    registrar_auditoria(
        id_usuario, "ETL_NOMINA", f"Carga de {ruta.name} finalizada con estado {estado}", "EXITOSO",
        tabla_afectada="archivos", datos_nuevos={"id_archivo": id_archivo, "errores": len(errores), **resumen},
    )
    return {"id_archivo": id_archivo, "estado": estado, "errores": len(errores), **resumen}


if __name__ == "__main__":
    resultado = ejecutar_etl_nomina(sys.argv[1] if len(sys.argv) > 1 else NOMINA_XLSX)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    sys.exit(0 if resultado["estado"] != "FALLIDO" else 1)
