import json
import re
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from config import (
    ADMIN_PASSWORD,
    ADMIN_ROL,
    ADMIN_USERNAME,
    BASE_DIR,
    CORS_ORIGINS,
    MAX_UPLOAD_MB,
    SECRET_KEY,
    UPLOAD_DIR,
)
from database.connection import consultar, consultar_uno, transaccion
from etl.load_libros import ejecutar_etl_libros
from etl.load_nomina import ejecutar_etl_nomina
from etl.load_peliculas import ejecutar_etl_peliculas
from routes.auth import auth_bp, hash_password, token_required
from routes.entretenimiento import entretenimiento_bp
from routes.nomina import nomina_bp
from services.audit_logger import registrar_auditoria
from services.pdf_generator import generar_pdf_reporte

FRONTEND_DIR = (BASE_DIR.parent / "frontend").resolve()
LIMITE_HISTORIAL = 100
MAX_FILAS_PDF = 20000

ETL_POR_EXTENSION = {
    ".xlsx": ("NOMINA", ejecutar_etl_nomina),
    ".dat": ("PELICULAS", ejecutar_etl_peliculas),
    ".json": ("LIBROS", ejecutar_etl_libros),
}


def asegurar_admin_por_defecto():
    if consultar_uno("SELECT id_usuario FROM usuarios WHERE username = %s", (ADMIN_USERNAME,)):
        return False
    with transaccion() as cursor:
        cursor.execute("INSERT IGNORE INTO roles_acceso (nombre_rol) VALUES (%s)", (ADMIN_ROL,))
        cursor.execute("SELECT id_rol_acceso FROM roles_acceso WHERE nombre_rol = %s", (ADMIN_ROL,))
        id_rol = cursor.fetchone()["id_rol_acceso"]
        cursor.execute(
            "INSERT INTO usuarios (id_persona, id_rol_acceso, username, password, activo) "
            "VALUES (NULL, %s, %s, %s, 1)",
            (id_rol, ADMIN_USERNAME, hash_password(ADMIN_PASSWORD)),
        )
        nuevo_id = cursor.lastrowid
    registrar_auditoria(
        nuevo_id, "CREACION_ADMIN_POR_DEFECTO", f"Se creó el usuario '{ADMIN_USERNAME}' al iniciar el servidor",
        "EXITOSO", tabla_afectada="usuarios",
    )
    return True


def crear_app():
    app = Flask(__name__, static_folder=None)
    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
    app.json.ensure_ascii = False
    CORS(app, resources={r"/api/*": {"origins": CORS_ORIGINS}})
    app.register_blueprint(auth_bp)
    app.register_blueprint(nomina_bp)
    app.register_blueprint(entretenimiento_bp)

    @app.errorhandler(RequestEntityTooLarge)
    def archivo_muy_grande(_):
        return jsonify({"error": f"El archivo supera el límite de {MAX_UPLOAD_MB} MB"}), 413

    @app.get("/api/health")
    def health():
        return jsonify({"estado": "ok"})

    @app.post("/api/etl/upload")
    @token_required
    def etl_upload(id_usuario):
        archivo = request.files.get("archivo") or request.files.get("file")
        if archivo is None or not archivo.filename:
            return jsonify({"error": "Debe adjuntar un archivo en el campo 'archivo'"}), 400

        nombre_original = archivo.filename
        extension = Path(nombre_original).suffix.lower()
        if extension not in ETL_POR_EXTENSION:
            registrar_auditoria(
                id_usuario, "ETL_UPLOAD", f"Extensión no permitida: {nombre_original}", "FALLIDO",
                tabla_afectada="archivos",
            )
            return jsonify({"error": "Solo se permiten archivos .xlsx, .dat o .json"}), 400

        tipo, funcion_etl = ETL_POR_EXTENSION[extension]
        nombre_seguro = re.sub(r"[^A-Za-z0-9_.-]", "_", secure_filename(nombre_original)) or f"archivo{extension}"
        marca = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = UPLOAD_DIR / f"{marca}_{nombre_seguro}"
        archivo.save(destino)

        try:
            resultado = funcion_etl(str(destino), id_usuario=id_usuario)
        except Exception as exc:
            registrar_auditoria(
                id_usuario, "ETL_UPLOAD", f"Error procesando {nombre_original}: {exc}", "FALLIDO",
                tabla_afectada="archivos",
            )
            return jsonify({"error": f"No fue posible procesar el archivo: {exc}"}), 500

        codigo = 200 if resultado.get("estado") != "FALLIDO" else 422
        return jsonify({"tipo": tipo, "archivo": nombre_original, "resultado": resultado}), codigo

    @app.post("/api/reportes/pdf")
    @token_required
    def reportes_pdf(id_usuario):
        datos = request.get_json(silent=True)
        if not isinstance(datos, dict):
            return jsonify({"error": "El cuerpo de la petición debe ser un objeto JSON"}), 400
        titulo = datos.get("titulo")
        encabezados = datos.get("encabezados")
        filas = datos.get("filas")
        if not isinstance(titulo, str) or not titulo.strip():
            return jsonify({"error": "El campo 'titulo' es obligatorio"}), 400
        if not isinstance(encabezados, list) or not encabezados:
            return jsonify({"error": "El campo 'encabezados' debe ser una lista no vacía"}), 400
        if filas is None:
            filas = []
        if not isinstance(filas, list):
            return jsonify({"error": "El campo 'filas' debe ser una lista"}), 400
        if len(filas) > MAX_FILAS_PDF:
            return jsonify({"error": f"El reporte no puede superar {MAX_FILAS_PDF} filas"}), 413
        imagenes = datos.get("imagenes_base64")
        if imagenes is not None and not isinstance(imagenes, (list, str)):
            return jsonify({"error": "El campo 'imagenes_base64' debe ser una lista de cadenas"}), 400
        try:
            pdf = generar_pdf_reporte(
                titulo,
                datos.get("subtitulo"),
                datos.get("resumen_kpis"),
                encabezados,
                filas,
                imagenes,
            )
        except Exception as exc:
            registrar_auditoria(
                id_usuario, "EXPORTAR_PDF", f"Error generando el PDF '{titulo[:200]}': {exc}", "FALLIDO",
            )
            return jsonify({"error": "No fue posible generar el PDF"}), 500
        registrar_auditoria(
            id_usuario, "EXPORTAR_PDF", f"Se exportó el reporte '{titulo[:200]}' con {len(filas)} filas", "EXITOSO",
            datos_nuevos={"titulo": titulo, "subtitulo": datos.get("subtitulo"), "filas": len(filas)},
        )
        nombre = re.sub(r"[^A-Za-z0-9_-]+", "_", titulo).strip("_")[:60] or "reporte"
        return send_file(
            pdf,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"{nombre}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        )

    @app.get("/api/auditoria")
    @token_required
    def listar_auditoria(id_usuario):
        filas = consultar(
            "SELECT a.id_auditoria, a.id_usuario, u.username, a.id_empleado, "
            "DATE_FORMAT(a.fecha, '%Y-%m-%d') AS fecha, TIME_FORMAT(a.hora, '%H:%i:%s') AS hora, "
            "a.accion, a.detalle, a.resultado, a.tabla_afectada, a.datos_anteriores, a.datos_nuevos "
            "FROM auditoria a LEFT JOIN usuarios u ON u.id_usuario = a.id_usuario "
            f"ORDER BY a.id_auditoria DESC LIMIT {LIMITE_HISTORIAL}",
        )
        for fila in filas:
            for clave in ("datos_anteriores", "datos_nuevos"):
                valor = fila[clave]
                if isinstance(valor, (bytes, str)):
                    try:
                        fila[clave] = json.loads(valor)
                    except ValueError:
                        pass
        return jsonify({"total": len(filas), "auditoria": filas})

    @app.get("/api/archivos")
    @token_required
    def listar_archivos(id_usuario):
        filas = consultar(
            "SELECT a.id_archivo, a.id_usuario, u.username, a.nombre_archivo, "
            "DATE_FORMAT(a.fecha, '%Y-%m-%d') AS fecha, TIME_FORMAT(a.hora, '%H:%i:%s') AS hora, "
            "a.tipo, a.estado, "
            "(SELECT COUNT(*) FROM errores_carga ec WHERE ec.id_archivo = a.id_archivo) AS cantidad_errores "
            "FROM archivos a LEFT JOIN usuarios u ON u.id_usuario = a.id_usuario "
            f"ORDER BY a.id_archivo DESC LIMIT {LIMITE_HISTORIAL}",
        )
        return jsonify({"total": len(filas), "archivos": filas})

    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def frontend(path):
        if path == "api" or path.startswith("api/"):
            return jsonify({"error": "Recurso no encontrado"}), 404
        if not FRONTEND_DIR.is_dir():
            return jsonify({"error": "El frontend no está disponible"}), 404
        solicitado = (FRONTEND_DIR / path).resolve() if path else FRONTEND_DIR
        if path and solicitado.is_file() and FRONTEND_DIR in solicitado.parents:
            return send_from_directory(FRONTEND_DIR, path)
        if path and Path(path).suffix:
            return jsonify({"error": "Recurso no encontrado"}), 404
        indice = FRONTEND_DIR / "index.html"
        if indice.is_file():
            return send_from_directory(FRONTEND_DIR, "index.html")
        return jsonify({"error": "El frontend no está disponible"}), 404

    asegurar_admin_por_defecto()
    return app


app = crear_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
