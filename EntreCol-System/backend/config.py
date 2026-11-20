import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "entrecol_db"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "charset": "utf8mb4",
    "collation": "utf8mb4_unicode_ci",
    "autocommit": False,
}

DB_POOL_NAME = "entrecol_pool"
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))

SECRET_KEY = os.getenv("SECRET_KEY", "entrecol-dev-secret-key-cambiar-en-produccion-2026")
JWT_ALGORITHM = "HS256"
JWT_EXPIRACION_HORAS = int(os.getenv("JWT_EXPIRACION_HORAS", "8"))
CAPTCHA_EXPIRACION_SEGUNDOS = int(os.getenv("CAPTCHA_EXPIRACION_SEGUNDOS", "300"))
CAPTCHA_LONGITUD = 5

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")

DATA_SOURCES_DIR = Path(os.getenv("DATA_SOURCES_DIR", BASE_DIR.parent / "data_sources"))
UPLOAD_DIR = DATA_SOURCES_DIR / "uploads"
NOMINA_XLSX = DATA_SOURCES_DIR / "Nomina.xlsx"
MOVIES_DAT = DATA_SOURCES_DIR / "movies.dat"
BOOKS_JSON = DATA_SOURCES_DIR / "Books.json"

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "200"))
CHUNK_SIZE = 1000

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "Admin123*"
ADMIN_ROL = "Administrador"
ROL_POR_DEFECTO = "Analista"

DATA_SOURCES_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
