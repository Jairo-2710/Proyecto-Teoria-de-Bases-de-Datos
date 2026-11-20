CREATE DATABASE IF NOT EXISTS entrecol_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE entrecol_db;

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS dependencias (
    id_dependencia INT UNSIGNED NOT NULL AUTO_INCREMENT,
    nombre_dependencia VARCHAR(100) NOT NULL,
    CONSTRAINT pk_dependencias PRIMARY KEY (id_dependencia),
    CONSTRAINT uq_dependencias_nombre UNIQUE (nombre_dependencia)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS cargos (
    id_cargo INT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_dependencia INT UNSIGNED NOT NULL,
    nombre_cargo VARCHAR(100) NOT NULL,
    CONSTRAINT pk_cargos PRIMARY KEY (id_cargo),
    CONSTRAINT uq_cargos_dependencia_nombre UNIQUE (id_dependencia, nombre_cargo),
    CONSTRAINT fk_cargos_dependencias FOREIGN KEY (id_dependencia)
        REFERENCES dependencias (id_dependencia) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS eps (
    id_eps INT UNSIGNED NOT NULL AUTO_INCREMENT,
    nombre_eps VARCHAR(100) NOT NULL,
    CONSTRAINT pk_eps PRIMARY KEY (id_eps),
    CONSTRAINT uq_eps_nombre UNIQUE (nombre_eps)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS arl (
    id_arl INT UNSIGNED NOT NULL AUTO_INCREMENT,
    nombre_arl VARCHAR(100) NOT NULL,
    CONSTRAINT pk_arl PRIMARY KEY (id_arl),
    CONSTRAINT uq_arl_nombre UNIQUE (nombre_arl)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS fondos_pension (
    id_fondo_pension INT UNSIGNED NOT NULL AUTO_INCREMENT,
    nombre_fondo_pension VARCHAR(100) NOT NULL,
    CONSTRAINT pk_fondos_pension PRIMARY KEY (id_fondo_pension),
    CONSTRAINT uq_fondos_pension_nombre UNIQUE (nombre_fondo_pension)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS tipos_novedad (
    id_tipo_novedad INT UNSIGNED NOT NULL AUTO_INCREMENT,
    nombre_tipo_novedad VARCHAR(100) NOT NULL,
    CONSTRAINT pk_tipos_novedad PRIMARY KEY (id_tipo_novedad),
    CONSTRAINT uq_tipos_novedad_nombre UNIQUE (nombre_tipo_novedad)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS generos (
    id_genero INT UNSIGNED NOT NULL AUTO_INCREMENT,
    nombre_genero VARCHAR(80) NOT NULL,
    CONSTRAINT pk_generos PRIMARY KEY (id_genero),
    CONSTRAINT uq_generos_nombre UNIQUE (nombre_genero)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS idiomas (
    id_idioma INT UNSIGNED NOT NULL AUTO_INCREMENT,
    codigo_idioma VARCHAR(10) NOT NULL,
    nombre_idioma VARCHAR(50) NULL,
    CONSTRAINT pk_idiomas PRIMARY KEY (id_idioma),
    CONSTRAINT uq_idiomas_codigo UNIQUE (codigo_idioma)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS autores (
    id_autor INT UNSIGNED NOT NULL AUTO_INCREMENT,
    nombre_autor VARCHAR(150) NOT NULL,
    CONSTRAINT pk_autores PRIMARY KEY (id_autor),
    CONSTRAINT uq_autores_nombre UNIQUE (nombre_autor)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS editoriales (
    id_editorial INT UNSIGNED NOT NULL AUTO_INCREMENT,
    nombre_editorial VARCHAR(150) NOT NULL,
    CONSTRAINT pk_editoriales PRIMARY KEY (id_editorial),
    CONSTRAINT uq_editoriales_nombre UNIQUE (nombre_editorial)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS artistas (
    id_artista INT UNSIGNED NOT NULL AUTO_INCREMENT,
    nombre_artista VARCHAR(150) NOT NULL,
    CONSTRAINT pk_artistas PRIMARY KEY (id_artista),
    CONSTRAINT uq_artistas_nombre UNIQUE (nombre_artista)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS roles_acceso (
    id_rol_acceso INT UNSIGNED NOT NULL AUTO_INCREMENT,
    nombre_rol VARCHAR(50) NOT NULL,
    CONSTRAINT pk_roles_acceso PRIMARY KEY (id_rol_acceso),
    CONSTRAINT uq_roles_acceso_nombre UNIQUE (nombre_rol)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS personas (
    id_persona INT UNSIGNED NOT NULL AUTO_INCREMENT,
    nombre_completo VARCHAR(150) NOT NULL,
    numero_documento VARCHAR(30) NULL,
    fecha_nacimiento DATE NULL,
    direccion_contacto VARCHAR(200) NULL,
    CONSTRAINT pk_personas PRIMARY KEY (id_persona),
    CONSTRAINT uq_personas_documento UNIQUE (numero_documento),
    INDEX idx_personas_nombre (nombre_completo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS empleados (
    id_empleado INT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_persona INT UNSIGNED NOT NULL,
    id_cargo INT UNSIGNED NOT NULL,
    codigo_personal VARCHAR(30) NOT NULL,
    salario DECIMAL(14,2) NOT NULL,
    fecha_ingreso DATE NOT NULL,
    CONSTRAINT pk_empleados PRIMARY KEY (id_empleado),
    CONSTRAINT uq_empleados_persona UNIQUE (id_persona),
    CONSTRAINT uq_empleados_codigo_personal UNIQUE (codigo_personal),
    CONSTRAINT ck_empleados_salario CHECK (salario >= 0),
    CONSTRAINT fk_empleados_personas FOREIGN KEY (id_persona)
        REFERENCES personas (id_persona) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_empleados_cargos FOREIGN KEY (id_cargo)
        REFERENCES cargos (id_cargo) ON UPDATE CASCADE ON DELETE RESTRICT,
    INDEX idx_empleados_fecha_ingreso (fecha_ingreso)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS afiliaciones_empleado (
    id_afiliacion_empleado INT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_empleado INT UNSIGNED NOT NULL,
    id_eps INT UNSIGNED NOT NULL,
    id_arl INT UNSIGNED NOT NULL,
    id_fondo_pension INT UNSIGNED NOT NULL,
    fecha_inicio DATE NOT NULL,
    fecha_fin DATE NULL,
    CONSTRAINT pk_afiliaciones_empleado PRIMARY KEY (id_afiliacion_empleado),
    CONSTRAINT uq_afiliaciones_empleado_inicio UNIQUE (id_empleado, fecha_inicio),
    CONSTRAINT ck_afiliaciones_fechas CHECK (fecha_fin IS NULL OR fecha_fin >= fecha_inicio),
    CONSTRAINT fk_afiliaciones_empleados FOREIGN KEY (id_empleado)
        REFERENCES empleados (id_empleado) ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_afiliaciones_eps FOREIGN KEY (id_eps)
        REFERENCES eps (id_eps) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_afiliaciones_arl FOREIGN KEY (id_arl)
        REFERENCES arl (id_arl) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_afiliaciones_fondos_pension FOREIGN KEY (id_fondo_pension)
        REFERENCES fondos_pension (id_fondo_pension) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS usuarios (
    id_usuario INT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_persona INT UNSIGNED NULL,
    id_rol_acceso INT UNSIGNED NOT NULL,
    username VARCHAR(50) NOT NULL,
    password VARCHAR(255) NOT NULL,
    activo TINYINT NOT NULL DEFAULT 1,
    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_usuarios PRIMARY KEY (id_usuario),
    CONSTRAINT uq_usuarios_username UNIQUE (username),
    CONSTRAINT fk_usuarios_personas FOREIGN KEY (id_persona)
        REFERENCES personas (id_persona) ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_usuarios_roles_acceso FOREIGN KEY (id_rol_acceso)
        REFERENCES roles_acceso (id_rol_acceso) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS archivos (
    id_archivo INT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_usuario INT UNSIGNED NOT NULL,
    nombre_archivo VARCHAR(255) NOT NULL,
    fecha DATE NOT NULL,
    hora TIME NOT NULL,
    tipo VARCHAR(50) NOT NULL,
    estado VARCHAR(30) NOT NULL DEFAULT 'PENDIENTE',
    CONSTRAINT pk_archivos PRIMARY KEY (id_archivo),
    CONSTRAINT fk_archivos_usuarios FOREIGN KEY (id_usuario)
        REFERENCES usuarios (id_usuario) ON UPDATE CASCADE ON DELETE RESTRICT,
    INDEX idx_archivos_fecha (fecha)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS errores_carga (
    id_error_carga INT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_archivo INT UNSIGNED NOT NULL,
    numero_fila INT UNSIGNED NULL,
    motivo VARCHAR(500) NOT NULL,
    dato_crudo TEXT NULL,
    CONSTRAINT pk_errores_carga PRIMARY KEY (id_error_carga),
    CONSTRAINT fk_errores_carga_archivos FOREIGN KEY (id_archivo)
        REFERENCES archivos (id_archivo) ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS revisiones_archivo (
    id_revision_archivo INT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_archivo INT UNSIGNED NOT NULL,
    id_usuario INT UNSIGNED NOT NULL,
    comentario VARCHAR(1000) NULL,
    estado_revision VARCHAR(20) NOT NULL,
    fecha_hora DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_revisiones_archivo PRIMARY KEY (id_revision_archivo),
    CONSTRAINT fk_revisiones_archivo_archivos FOREIGN KEY (id_archivo)
        REFERENCES archivos (id_archivo) ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_revisiones_archivo_usuarios FOREIGN KEY (id_usuario)
        REFERENCES usuarios (id_usuario) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS nominas (
    id_nomina INT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_archivo INT UNSIGNED NULL,
    descripcion VARCHAR(200) NULL,
    fecha_liquidacion DATE NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'ABIERTA',
    CONSTRAINT pk_nominas PRIMARY KEY (id_nomina),
    CONSTRAINT fk_nominas_archivos FOREIGN KEY (id_archivo)
        REFERENCES archivos (id_archivo) ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS detalle_nomina (
    id_detalle_nomina INT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_nomina INT UNSIGNED NOT NULL,
    id_afiliacion_empleado INT UNSIGNED NOT NULL,
    id_dependencia INT UNSIGNED NOT NULL,
    periodo_fecha DATE NOT NULL,
    dias_trabajados TINYINT UNSIGNED NOT NULL DEFAULT 30,
    valor_bonificacion DECIMAL(14,2) NOT NULL DEFAULT 0,
    valor_transporte DECIMAL(14,2) NOT NULL DEFAULT 0,
    valor_aporte_pension DECIMAL(14,2) NOT NULL DEFAULT 0,
    CONSTRAINT pk_detalle_nomina PRIMARY KEY (id_detalle_nomina),
    CONSTRAINT uq_detalle_nomina_afiliacion_periodo UNIQUE (id_afiliacion_empleado, periodo_fecha),
    CONSTRAINT ck_detalle_nomina_dias CHECK (dias_trabajados BETWEEN 0 AND 31),
    CONSTRAINT fk_detalle_nomina_nominas FOREIGN KEY (id_nomina)
        REFERENCES nominas (id_nomina) ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_detalle_nomina_afiliaciones FOREIGN KEY (id_afiliacion_empleado)
        REFERENCES afiliaciones_empleado (id_afiliacion_empleado) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_detalle_nomina_dependencias FOREIGN KEY (id_dependencia)
        REFERENCES dependencias (id_dependencia) ON UPDATE CASCADE ON DELETE RESTRICT,
    INDEX idx_detalle_nomina_periodo_fecha (periodo_fecha)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS novedades (
    id_novedad INT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_tipo_novedad INT UNSIGNED NOT NULL,
    id_detalle_nomina INT UNSIGNED NOT NULL,
    fecha_inicio DATE NULL,
    fecha_fin DATE NULL,
    dias_reportados TINYINT UNSIGNED NOT NULL DEFAULT 0,
    detalle VARCHAR(1000) NULL,
    CONSTRAINT pk_novedades PRIMARY KEY (id_novedad),
    CONSTRAINT ck_novedades_fechas CHECK (fecha_fin IS NULL OR fecha_inicio IS NULL OR fecha_fin >= fecha_inicio),
    CONSTRAINT ck_novedades_dias CHECK (dias_reportados BETWEEN 0 AND 31),
    CONSTRAINT fk_novedades_tipos_novedad FOREIGN KEY (id_tipo_novedad)
        REFERENCES tipos_novedad (id_tipo_novedad) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_novedades_detalle_nomina FOREIGN KEY (id_detalle_nomina)
        REFERENCES detalle_nomina (id_detalle_nomina) ON UPDATE CASCADE ON DELETE CASCADE,
    INDEX idx_novedades_fecha_inicio (fecha_inicio)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS revisiones_nomina (
    id_revision_nomina INT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_detalle_nomina INT UNSIGNED NOT NULL,
    id_usuario INT UNSIGNED NOT NULL,
    comentario VARCHAR(1000) NULL,
    estado_revision VARCHAR(20) NOT NULL,
    fecha_hora DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_revisiones_nomina PRIMARY KEY (id_revision_nomina),
    CONSTRAINT fk_revisiones_nomina_detalle FOREIGN KEY (id_detalle_nomina)
        REFERENCES detalle_nomina (id_detalle_nomina) ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_revisiones_nomina_usuarios FOREIGN KEY (id_usuario)
        REFERENCES usuarios (id_usuario) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS peliculas (
    id_pelicula INT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_idioma INT UNSIGNED NULL,
    titulo VARCHAR(500) NOT NULL,
    anio_estreno SMALLINT UNSIGNED NULL,
    fecha_estreno DATE NULL,
    sinopsis VARCHAR(2000) NULL,
    CONSTRAINT pk_peliculas PRIMARY KEY (id_pelicula),
    CONSTRAINT fk_peliculas_idiomas FOREIGN KEY (id_idioma)
        REFERENCES idiomas (id_idioma) ON UPDATE CASCADE ON DELETE SET NULL,
    INDEX idx_peliculas_anio_estreno (anio_estreno),
    INDEX idx_peliculas_fecha_estreno (fecha_estreno),
    INDEX idx_peliculas_titulo (titulo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS pelicula_generos (
    id_pelicula INT UNSIGNED NOT NULL,
    id_genero INT UNSIGNED NOT NULL,
    CONSTRAINT pk_pelicula_generos PRIMARY KEY (id_pelicula, id_genero),
    CONSTRAINT fk_pelicula_generos_peliculas FOREIGN KEY (id_pelicula)
        REFERENCES peliculas (id_pelicula) ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_pelicula_generos_generos FOREIGN KEY (id_genero)
        REFERENCES generos (id_genero) ON UPDATE CASCADE ON DELETE RESTRICT,
    INDEX idx_pelicula_generos_genero (id_genero)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS pelicula_participantes (
    id_pelicula INT UNSIGNED NOT NULL,
    id_artista INT UNSIGNED NOT NULL,
    tipo_rol VARCHAR(30) NOT NULL,
    CONSTRAINT pk_pelicula_participantes PRIMARY KEY (id_pelicula, id_artista, tipo_rol),
    CONSTRAINT fk_pelicula_participantes_peliculas FOREIGN KEY (id_pelicula)
        REFERENCES peliculas (id_pelicula) ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_pelicula_participantes_artistas FOREIGN KEY (id_artista)
        REFERENCES artistas (id_artista) ON UPDATE CASCADE ON DELETE RESTRICT,
    INDEX idx_pelicula_participantes_artista (id_artista)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS libros (
    id_libro INT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_idioma INT UNSIGNED NULL,
    id_autor INT UNSIGNED NOT NULL,
    id_editorial INT UNSIGNED NULL,
    titulo VARCHAR(500) NOT NULL,
    isbn VARCHAR(20) NULL,
    isbn13 VARCHAR(20) NULL,
    calificacion_promedio DECIMAL(4,2) NOT NULL DEFAULT 0,
    numero_paginas INT UNSIGNED NOT NULL DEFAULT 0,
    cantidad_calificaciones INT UNSIGNED NOT NULL DEFAULT 0,
    numero_resenas INT UNSIGNED NOT NULL DEFAULT 0,
    fecha_publicacion DATE NULL,
    anio_publicacion INT GENERATED ALWAYS AS (YEAR(fecha_publicacion)) STORED,
    CONSTRAINT pk_libros PRIMARY KEY (id_libro),
    CONSTRAINT ck_libros_calificacion CHECK (calificacion_promedio BETWEEN 0 AND 5),
    CONSTRAINT fk_libros_idiomas FOREIGN KEY (id_idioma)
        REFERENCES idiomas (id_idioma) ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_libros_autores FOREIGN KEY (id_autor)
        REFERENCES autores (id_autor) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_libros_editoriales FOREIGN KEY (id_editorial)
        REFERENCES editoriales (id_editorial) ON UPDATE CASCADE ON DELETE SET NULL,
    INDEX idx_libros_calificacion_promedio (calificacion_promedio),
    INDEX idx_libros_anio_publicacion (anio_publicacion),
    INDEX idx_libros_anio_calificacion (anio_publicacion, calificacion_promedio),
    INDEX idx_libros_isbn13 (isbn13),
    INDEX idx_libros_titulo (titulo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS libro_autores (
    id_libro INT UNSIGNED NOT NULL,
    id_autor INT UNSIGNED NOT NULL,
    orden_autor TINYINT UNSIGNED NOT NULL DEFAULT 1,
    CONSTRAINT pk_libro_autores PRIMARY KEY (id_libro, id_autor),
    CONSTRAINT fk_libro_autores_libros FOREIGN KEY (id_libro)
        REFERENCES libros (id_libro) ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_libro_autores_autores FOREIGN KEY (id_autor)
        REFERENCES autores (id_autor) ON UPDATE CASCADE ON DELETE RESTRICT,
    INDEX idx_libro_autores_autor (id_autor)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS auditoria (
    id_auditoria BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_usuario INT UNSIGNED NULL,
    id_empleado INT UNSIGNED NULL,
    fecha DATE NOT NULL,
    hora TIME NOT NULL,
    accion VARCHAR(100) NOT NULL,
    detalle VARCHAR(1000) NULL,
    resultado VARCHAR(50) NOT NULL,
    tabla_afectada VARCHAR(60) NULL,
    datos_anteriores JSON NULL,
    datos_nuevos JSON NULL,
    CONSTRAINT pk_auditoria PRIMARY KEY (id_auditoria),
    CONSTRAINT fk_auditoria_usuarios FOREIGN KEY (id_usuario)
        REFERENCES usuarios (id_usuario) ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_auditoria_empleados FOREIGN KEY (id_empleado)
        REFERENCES empleados (id_empleado) ON UPDATE CASCADE ON DELETE SET NULL,
    INDEX idx_auditoria_fecha_hora (fecha, hora),
    INDEX idx_auditoria_tabla_accion (tabla_afectada, accion)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO roles_acceso (nombre_rol) VALUES
    ('Administrador'),
    ('Analista');

INSERT IGNORE INTO tipos_novedad (nombre_tipo_novedad) VALUES
    ('INCAPACIDAD'),
    ('VACACIONES');

INSERT IGNORE INTO usuarios (id_persona, id_rol_acceso, username, password, activo)
SELECT NULL, r.id_rol_acceso, 'admin', '$2b$12$bOMGHhnLnGj/mPCMkf53feilQiYku0OETMurBjRwoerwYUR4PDp3u', 1
FROM roles_acceso r
WHERE r.nombre_rol = 'Administrador';
