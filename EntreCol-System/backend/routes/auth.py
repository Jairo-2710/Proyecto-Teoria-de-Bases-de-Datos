import base64
import hashlib
import hmac
import random
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps

import bcrypt
import jwt
from flask import Blueprint, g, jsonify, request

from config import (
    CAPTCHA_EXPIRACION_SEGUNDOS,
    CAPTCHA_LONGITUD,
    JWT_ALGORITHM,
    JWT_EXPIRACION_HORAS,
    ADMIN_ROL,
    ROL_POR_DEFECTO,
    SECRET_KEY,
)
from database.connection import Error, consultar_uno, transaccion
from services.audit_logger import registrar_auditoria

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

ALFABETO_CAPTCHA = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PATRON_USUARIO = re.compile(r"^[A-Za-z0-9_.-]{3,50}$")
_azar = random.SystemRandom()
_captchas_usados = {}
_captchas_lock = threading.Lock()
HASH_FICTICIO = bcrypt.hashpw(b"contrasena-ficticia", bcrypt.gensalt(rounds=12))


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verificar_password(password, hash_almacenado):
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hash_almacenado.encode("utf-8"))
    except (ValueError, AttributeError):
        return False


def generar_token(usuario):
    ahora = datetime.now(timezone.utc)
    payload = {
        "id_usuario": usuario["id_usuario"],
        "username": usuario["username"],
        "rol": usuario["nombre_rol"],
        "iat": ahora,
        "exp": ahora + timedelta(hours=JWT_EXPIRACION_HORAS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def decodificar_token(token):
    return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])


def _token_de_cabecera():
    cabecera = request.headers.get("Authorization", "")
    partes = cabecera.split()
    if len(partes) == 2 and partes[0].lower() == "bearer":
        return partes[1]
    return None


def token_required(funcion):
    @wraps(funcion)
    def envoltura(*args, **kwargs):
        token = _token_de_cabecera()
        if not token:
            return jsonify({"error": "Token de autenticación requerido"}), 401
        try:
            payload = decodificar_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "El token ha expirado"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Token inválido"}), 401
        g.usuario = payload
        kwargs["id_usuario"] = payload["id_usuario"]
        return funcion(*args, **kwargs)

    return envoltura


def _firma_captcha(jti, codigo):
    mensaje = f"{jti}:{codigo.upper()}".encode("utf-8")
    return hmac.new(SECRET_KEY.encode("utf-8"), mensaje, hashlib.sha256).hexdigest()


def _generar_svg(codigo):
    ancho, alto = 180, 60
    partes = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{ancho}" height="{alto}" '
        f'viewBox="0 0 {ancho} {alto}">',
        f'<rect width="{ancho}" height="{alto}" fill="rgb(240,243,247)"/>',
    ]
    for _ in range(7):
        x1, y1 = _azar.randint(0, ancho), _azar.randint(0, alto)
        x2, y2 = _azar.randint(0, ancho), _azar.randint(0, alto)
        color = f"rgb({_azar.randint(90,200)},{_azar.randint(90,200)},{_azar.randint(90,200)})"
        partes.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1.5"/>'
        )
    paso = ancho / (len(codigo) + 1)
    for indice, caracter in enumerate(codigo):
        x = paso * (indice + 1)
        y = _azar.randint(36, 44)
        giro = _azar.randint(-25, 25)
        color = f"rgb({_azar.randint(10,90)},{_azar.randint(10,90)},{_azar.randint(10,90)})"
        tamano = _azar.randint(28, 34)
        partes.append(
            f'<text x="{x:.1f}" y="{y}" font-family="Verdana,Arial,sans-serif" '
            f'font-size="{tamano}" font-weight="bold" fill="{color}" text-anchor="middle" '
            f'transform="rotate({giro} {x:.1f} {y})">{caracter}</text>'
        )
    for _ in range(40):
        cx, cy = _azar.randint(0, ancho), _azar.randint(0, alto)
        partes.append(f'<circle cx="{cx}" cy="{cy}" r="1" fill="rgb(120,120,120)"/>')
    partes.append("</svg>")
    return "".join(partes)


def crear_captcha():
    codigo = "".join(_azar.choice(ALFABETO_CAPTCHA) for _ in range(CAPTCHA_LONGITUD))
    jti = uuid.uuid4().hex
    ahora = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "tipo": "captcha",
            "jti": jti,
            "firma": _firma_captcha(jti, codigo),
            "iat": ahora,
            "exp": ahora + timedelta(seconds=CAPTCHA_EXPIRACION_SEGUNDOS),
        },
        SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )
    svg = _generar_svg(codigo)
    imagen = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return token, f"data:image/svg+xml;base64,{imagen}"


def validar_captcha(token, respuesta):
    if not token or not respuesta:
        return False
    try:
        payload = decodificar_token(token)
    except jwt.InvalidTokenError:
        return False
    if payload.get("tipo") != "captcha":
        return False
    jti = payload["jti"]
    ahora = time.time()
    with _captchas_lock:
        for clave in [k for k, v in _captchas_usados.items() if v < ahora]:
            del _captchas_usados[clave]
        if jti in _captchas_usados:
            return False
        _captchas_usados[jti] = payload["exp"]
    return hmac.compare_digest(payload["firma"], _firma_captcha(jti, str(respuesta).strip()))


def _buscar_usuario(username):
    return consultar_uno(
        "SELECT u.id_usuario, u.username, u.password, u.activo, r.nombre_rol "
        "FROM usuarios u INNER JOIN roles_acceso r ON r.id_rol_acceso = u.id_rol_acceso "
        "WHERE u.username = %s",
        (username,),
    )


@auth_bp.get("/captcha")
def captcha():
    token, imagen = crear_captcha()
    return jsonify(
        {
            "captcha_token": token,
            "imagen": imagen,
            "expira_en": CAPTCHA_EXPIRACION_SEGUNDOS,
        }
    )


@auth_bp.post("/login")
def login():
    datos = request.get_json(silent=True) or {}
    username = str(datos.get("username") or "").strip()
    password = str(datos.get("password") or "")
    captcha_token = datos.get("captcha_token")
    captcha_respuesta = datos.get("captcha_respuesta")

    if not username or not password:
        return jsonify({"error": "Usuario y contraseña son obligatorios"}), 400

    usuario = _buscar_usuario(username)
    id_usuario = usuario["id_usuario"] if usuario else None

    if not validar_captcha(captcha_token, captcha_respuesta):
        registrar_auditoria(
            id_usuario,
            "LOGIN_FALLIDO",
            f"CAPTCHA inválido o expirado para el usuario '{username}'",
            "FALLIDO",
            tabla_afectada="usuarios",
        )
        return jsonify({"error": "CAPTCHA inválido o expirado"}), 400

    hash_a_comparar = usuario["password"] if usuario else HASH_FICTICIO.decode("utf-8")
    password_valida = verificar_password(password, hash_a_comparar)

    if not usuario or not password_valida or not usuario["activo"]:
        if not usuario:
            motivo = f"Usuario inexistente '{username}'"
        elif not usuario["activo"]:
            motivo = f"Usuario inactivo '{username}'"
        else:
            motivo = f"Contraseña incorrecta para el usuario '{username}'"
        registrar_auditoria(id_usuario, "LOGIN_FALLIDO", motivo, "FALLIDO", tabla_afectada="usuarios")
        return jsonify({"error": "Credenciales inválidas"}), 401

    token = generar_token(usuario)
    registrar_auditoria(
        usuario["id_usuario"],
        "LOGIN_EXITOSO",
        f"Inicio de sesión del usuario '{usuario['username']}'",
        "EXITOSO",
        tabla_afectada="usuarios",
    )
    return jsonify(
        {
            "token": token,
            "expira_en_horas": JWT_EXPIRACION_HORAS,
            "usuario": {
                "id_usuario": usuario["id_usuario"],
                "username": usuario["username"],
                "rol": usuario["nombre_rol"],
            },
        }
    )


@auth_bp.post("/register")
def register():
    datos = request.get_json(silent=True) or {}
    username = str(datos.get("username") or "").strip()
    password = str(datos.get("password") or "")
    rol = str(datos.get("rol") or ROL_POR_DEFECTO).strip()

    if not PATRON_USUARIO.match(username):
        return jsonify({"error": "El usuario debe tener entre 3 y 50 caracteres (letras, números, . _ -)"}), 400
    if len(password) < 8 or len(password.encode("utf-8")) > 72:
        return jsonify({"error": "La contraseña debe tener entre 8 y 72 caracteres"}), 400

    actor = None
    token = _token_de_cabecera()
    if token:
        try:
            actor = decodificar_token(token)
        except jwt.InvalidTokenError:
            return jsonify({"error": "Token inválido"}), 401

    if rol == ADMIN_ROL and (not actor or actor.get("rol") != ADMIN_ROL):
        registrar_auditoria(
            actor["id_usuario"] if actor else None,
            "REGISTRO_USUARIO",
            f"Intento no autorizado de crear el usuario administrador '{username}'",
            "FALLIDO",
            tabla_afectada="usuarios",
        )
        return jsonify({"error": "Solo un administrador puede crear usuarios administradores"}), 403

    rol_fila = consultar_uno("SELECT id_rol_acceso FROM roles_acceso WHERE nombre_rol = %s", (rol,))
    if not rol_fila:
        return jsonify({"error": f"El rol '{rol}' no existe"}), 400

    if _buscar_usuario(username):
        registrar_auditoria(
            actor["id_usuario"] if actor else None,
            "REGISTRO_USUARIO",
            f"El usuario '{username}' ya existe",
            "FALLIDO",
            tabla_afectada="usuarios",
        )
        return jsonify({"error": "El nombre de usuario ya está en uso"}), 409

    try:
        with transaccion() as cursor:
            cursor.execute(
                "INSERT INTO usuarios (id_persona, id_rol_acceso, username, password, activo) "
                "VALUES (NULL, %s, %s, %s, 1)",
                (rol_fila["id_rol_acceso"], username, hash_password(password)),
            )
            nuevo_id = cursor.lastrowid
    except Error as exc:
        registrar_auditoria(
            actor["id_usuario"] if actor else None,
            "REGISTRO_USUARIO",
            f"Error al crear el usuario '{username}': {exc}",
            "FALLIDO",
            tabla_afectada="usuarios",
        )
        return jsonify({"error": "No fue posible registrar el usuario"}), 500

    registrar_auditoria(
        actor["id_usuario"] if actor else nuevo_id,
        "REGISTRO_USUARIO",
        f"Se registró el usuario '{username}' con rol '{rol}'",
        "EXITOSO",
        tabla_afectada="usuarios",
        datos_nuevos={"id_usuario": nuevo_id, "username": username, "rol": rol},
    )
    return jsonify({"id_usuario": nuevo_id, "username": username, "rol": rol}), 201
