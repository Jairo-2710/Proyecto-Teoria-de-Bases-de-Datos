USE entrecol_db;

DROP TRIGGER IF EXISTS trg_empleados_ai;
DROP TRIGGER IF EXISTS trg_empleados_au;
DROP TRIGGER IF EXISTS trg_empleados_ad;
DROP TRIGGER IF EXISTS trg_novedades_ai;
DROP TRIGGER IF EXISTS trg_novedades_au;
DROP TRIGGER IF EXISTS trg_novedades_ad;
DROP TRIGGER IF EXISTS trg_peliculas_ai;
DROP TRIGGER IF EXISTS trg_peliculas_au;
DROP TRIGGER IF EXISTS trg_peliculas_ad;
DROP TRIGGER IF EXISTS trg_libros_ai;
DROP TRIGGER IF EXISTS trg_libros_au;
DROP TRIGGER IF EXISTS trg_libros_ad;

DELIMITER //

CREATE TRIGGER trg_empleados_ai
AFTER INSERT ON empleados
FOR EACH ROW
BEGIN
    INSERT INTO auditoria (id_usuario, id_empleado, fecha, hora, accion, detalle, resultado, tabla_afectada, datos_anteriores, datos_nuevos)
    VALUES (
        (SELECT u.id_usuario FROM usuarios u WHERE u.id_usuario = @id_usuario_sesion),
        NEW.id_empleado,
        CURDATE(),
        CURTIME(),
        'INSERT',
        CONCAT('Se insertó el empleado con código ', NEW.codigo_personal),
        'EXITOSO',
        'empleados',
        NULL,
        JSON_OBJECT(
            'id_empleado', NEW.id_empleado,
            'id_persona', NEW.id_persona,
            'id_cargo', NEW.id_cargo,
            'codigo_personal', NEW.codigo_personal,
            'salario', NEW.salario,
            'fecha_ingreso', NEW.fecha_ingreso
        )
    );
END//

CREATE TRIGGER trg_empleados_au
AFTER UPDATE ON empleados
FOR EACH ROW
BEGIN
    INSERT INTO auditoria (id_usuario, id_empleado, fecha, hora, accion, detalle, resultado, tabla_afectada, datos_anteriores, datos_nuevos)
    VALUES (
        (SELECT u.id_usuario FROM usuarios u WHERE u.id_usuario = @id_usuario_sesion),
        NEW.id_empleado,
        CURDATE(),
        CURTIME(),
        'UPDATE',
        CONCAT('Se actualizó el empleado con código ', NEW.codigo_personal),
        'EXITOSO',
        'empleados',
        JSON_OBJECT(
            'id_empleado', OLD.id_empleado,
            'id_persona', OLD.id_persona,
            'id_cargo', OLD.id_cargo,
            'codigo_personal', OLD.codigo_personal,
            'salario', OLD.salario,
            'fecha_ingreso', OLD.fecha_ingreso
        ),
        JSON_OBJECT(
            'id_empleado', NEW.id_empleado,
            'id_persona', NEW.id_persona,
            'id_cargo', NEW.id_cargo,
            'codigo_personal', NEW.codigo_personal,
            'salario', NEW.salario,
            'fecha_ingreso', NEW.fecha_ingreso
        )
    );
END//

CREATE TRIGGER trg_empleados_ad
AFTER DELETE ON empleados
FOR EACH ROW
BEGIN
    INSERT INTO auditoria (id_usuario, id_empleado, fecha, hora, accion, detalle, resultado, tabla_afectada, datos_anteriores, datos_nuevos)
    VALUES (
        (SELECT u.id_usuario FROM usuarios u WHERE u.id_usuario = @id_usuario_sesion),
        NULL,
        CURDATE(),
        CURTIME(),
        'DELETE',
        CONCAT('Se eliminó el empleado con código ', OLD.codigo_personal),
        'EXITOSO',
        'empleados',
        JSON_OBJECT(
            'id_empleado', OLD.id_empleado,
            'id_persona', OLD.id_persona,
            'id_cargo', OLD.id_cargo,
            'codigo_personal', OLD.codigo_personal,
            'salario', OLD.salario,
            'fecha_ingreso', OLD.fecha_ingreso
        ),
        NULL
    );
END//

CREATE TRIGGER trg_novedades_ai
AFTER INSERT ON novedades
FOR EACH ROW
BEGIN
    INSERT INTO auditoria (id_usuario, id_empleado, fecha, hora, accion, detalle, resultado, tabla_afectada, datos_anteriores, datos_nuevos)
    VALUES (
        (SELECT u.id_usuario FROM usuarios u WHERE u.id_usuario = @id_usuario_sesion),
        (SELECT a.id_empleado FROM detalle_nomina d INNER JOIN afiliaciones_empleado a ON a.id_afiliacion_empleado = d.id_afiliacion_empleado WHERE d.id_detalle_nomina = NEW.id_detalle_nomina),
        CURDATE(),
        CURTIME(),
        'INSERT',
        CONCAT('Se insertó la novedad ', NEW.id_novedad),
        'EXITOSO',
        'novedades',
        NULL,
        JSON_OBJECT(
            'id_novedad', NEW.id_novedad,
            'id_tipo_novedad', NEW.id_tipo_novedad,
            'id_detalle_nomina', NEW.id_detalle_nomina,
            'fecha_inicio', NEW.fecha_inicio,
            'fecha_fin', NEW.fecha_fin,
            'dias_reportados', NEW.dias_reportados,
            'detalle', NEW.detalle
        )
    );
END//

CREATE TRIGGER trg_novedades_au
AFTER UPDATE ON novedades
FOR EACH ROW
BEGIN
    INSERT INTO auditoria (id_usuario, id_empleado, fecha, hora, accion, detalle, resultado, tabla_afectada, datos_anteriores, datos_nuevos)
    VALUES (
        (SELECT u.id_usuario FROM usuarios u WHERE u.id_usuario = @id_usuario_sesion),
        (SELECT a.id_empleado FROM detalle_nomina d INNER JOIN afiliaciones_empleado a ON a.id_afiliacion_empleado = d.id_afiliacion_empleado WHERE d.id_detalle_nomina = NEW.id_detalle_nomina),
        CURDATE(),
        CURTIME(),
        'UPDATE',
        CONCAT('Se actualizó la novedad ', NEW.id_novedad),
        'EXITOSO',
        'novedades',
        JSON_OBJECT(
            'id_novedad', OLD.id_novedad,
            'id_tipo_novedad', OLD.id_tipo_novedad,
            'id_detalle_nomina', OLD.id_detalle_nomina,
            'fecha_inicio', OLD.fecha_inicio,
            'fecha_fin', OLD.fecha_fin,
            'dias_reportados', OLD.dias_reportados,
            'detalle', OLD.detalle
        ),
        JSON_OBJECT(
            'id_novedad', NEW.id_novedad,
            'id_tipo_novedad', NEW.id_tipo_novedad,
            'id_detalle_nomina', NEW.id_detalle_nomina,
            'fecha_inicio', NEW.fecha_inicio,
            'fecha_fin', NEW.fecha_fin,
            'dias_reportados', NEW.dias_reportados,
            'detalle', NEW.detalle
        )
    );
END//

CREATE TRIGGER trg_novedades_ad
AFTER DELETE ON novedades
FOR EACH ROW
BEGIN
    INSERT INTO auditoria (id_usuario, id_empleado, fecha, hora, accion, detalle, resultado, tabla_afectada, datos_anteriores, datos_nuevos)
    VALUES (
        (SELECT u.id_usuario FROM usuarios u WHERE u.id_usuario = @id_usuario_sesion),
        (SELECT a.id_empleado FROM detalle_nomina d INNER JOIN afiliaciones_empleado a ON a.id_afiliacion_empleado = d.id_afiliacion_empleado WHERE d.id_detalle_nomina = OLD.id_detalle_nomina),
        CURDATE(),
        CURTIME(),
        'DELETE',
        CONCAT('Se eliminó la novedad ', OLD.id_novedad),
        'EXITOSO',
        'novedades',
        JSON_OBJECT(
            'id_novedad', OLD.id_novedad,
            'id_tipo_novedad', OLD.id_tipo_novedad,
            'id_detalle_nomina', OLD.id_detalle_nomina,
            'fecha_inicio', OLD.fecha_inicio,
            'fecha_fin', OLD.fecha_fin,
            'dias_reportados', OLD.dias_reportados,
            'detalle', OLD.detalle
        ),
        NULL
    );
END//

CREATE TRIGGER trg_peliculas_ai
AFTER INSERT ON peliculas
FOR EACH ROW
BEGIN
    INSERT INTO auditoria (id_usuario, id_empleado, fecha, hora, accion, detalle, resultado, tabla_afectada, datos_anteriores, datos_nuevos)
    VALUES (
        (SELECT u.id_usuario FROM usuarios u WHERE u.id_usuario = @id_usuario_sesion),
        NULL,
        CURDATE(),
        CURTIME(),
        'INSERT',
        CONCAT('Se insertó la película ', NEW.id_pelicula, ': ', LEFT(NEW.titulo, 200)),
        'EXITOSO',
        'peliculas',
        NULL,
        JSON_OBJECT(
            'id_pelicula', NEW.id_pelicula,
            'id_idioma', NEW.id_idioma,
            'titulo', NEW.titulo,
            'anio_estreno', NEW.anio_estreno,
            'fecha_estreno', NEW.fecha_estreno,
            'sinopsis', NEW.sinopsis
        )
    );
END//

CREATE TRIGGER trg_peliculas_au
AFTER UPDATE ON peliculas
FOR EACH ROW
BEGIN
    INSERT INTO auditoria (id_usuario, id_empleado, fecha, hora, accion, detalle, resultado, tabla_afectada, datos_anteriores, datos_nuevos)
    VALUES (
        (SELECT u.id_usuario FROM usuarios u WHERE u.id_usuario = @id_usuario_sesion),
        NULL,
        CURDATE(),
        CURTIME(),
        'UPDATE',
        CONCAT('Se actualizó la película ', NEW.id_pelicula, ': ', LEFT(NEW.titulo, 200)),
        'EXITOSO',
        'peliculas',
        JSON_OBJECT(
            'id_pelicula', OLD.id_pelicula,
            'id_idioma', OLD.id_idioma,
            'titulo', OLD.titulo,
            'anio_estreno', OLD.anio_estreno,
            'fecha_estreno', OLD.fecha_estreno,
            'sinopsis', OLD.sinopsis
        ),
        JSON_OBJECT(
            'id_pelicula', NEW.id_pelicula,
            'id_idioma', NEW.id_idioma,
            'titulo', NEW.titulo,
            'anio_estreno', NEW.anio_estreno,
            'fecha_estreno', NEW.fecha_estreno,
            'sinopsis', NEW.sinopsis
        )
    );
END//

CREATE TRIGGER trg_peliculas_ad
AFTER DELETE ON peliculas
FOR EACH ROW
BEGIN
    INSERT INTO auditoria (id_usuario, id_empleado, fecha, hora, accion, detalle, resultado, tabla_afectada, datos_anteriores, datos_nuevos)
    VALUES (
        (SELECT u.id_usuario FROM usuarios u WHERE u.id_usuario = @id_usuario_sesion),
        NULL,
        CURDATE(),
        CURTIME(),
        'DELETE',
        CONCAT('Se eliminó la película ', OLD.id_pelicula, ': ', LEFT(OLD.titulo, 200)),
        'EXITOSO',
        'peliculas',
        JSON_OBJECT(
            'id_pelicula', OLD.id_pelicula,
            'id_idioma', OLD.id_idioma,
            'titulo', OLD.titulo,
            'anio_estreno', OLD.anio_estreno,
            'fecha_estreno', OLD.fecha_estreno,
            'sinopsis', OLD.sinopsis
        ),
        NULL
    );
END//

CREATE TRIGGER trg_libros_ai
AFTER INSERT ON libros
FOR EACH ROW
BEGIN
    INSERT INTO auditoria (id_usuario, id_empleado, fecha, hora, accion, detalle, resultado, tabla_afectada, datos_anteriores, datos_nuevos)
    VALUES (
        (SELECT u.id_usuario FROM usuarios u WHERE u.id_usuario = @id_usuario_sesion),
        NULL,
        CURDATE(),
        CURTIME(),
        'INSERT',
        CONCAT('Se insertó el libro ', NEW.id_libro, ': ', LEFT(NEW.titulo, 200)),
        'EXITOSO',
        'libros',
        NULL,
        JSON_OBJECT(
            'id_libro', NEW.id_libro,
            'id_idioma', NEW.id_idioma,
            'id_autor', NEW.id_autor,
            'id_editorial', NEW.id_editorial,
            'titulo', NEW.titulo,
            'isbn', NEW.isbn,
            'isbn13', NEW.isbn13,
            'calificacion_promedio', NEW.calificacion_promedio,
            'numero_paginas', NEW.numero_paginas,
            'cantidad_calificaciones', NEW.cantidad_calificaciones,
            'numero_resenas', NEW.numero_resenas,
            'fecha_publicacion', NEW.fecha_publicacion,
            'anio_publicacion', NEW.anio_publicacion
        )
    );
END//

CREATE TRIGGER trg_libros_au
AFTER UPDATE ON libros
FOR EACH ROW
BEGIN
    INSERT INTO auditoria (id_usuario, id_empleado, fecha, hora, accion, detalle, resultado, tabla_afectada, datos_anteriores, datos_nuevos)
    VALUES (
        (SELECT u.id_usuario FROM usuarios u WHERE u.id_usuario = @id_usuario_sesion),
        NULL,
        CURDATE(),
        CURTIME(),
        'UPDATE',
        CONCAT('Se actualizó el libro ', NEW.id_libro, ': ', LEFT(NEW.titulo, 200)),
        'EXITOSO',
        'libros',
        JSON_OBJECT(
            'id_libro', OLD.id_libro,
            'id_idioma', OLD.id_idioma,
            'id_autor', OLD.id_autor,
            'id_editorial', OLD.id_editorial,
            'titulo', OLD.titulo,
            'isbn', OLD.isbn,
            'isbn13', OLD.isbn13,
            'calificacion_promedio', OLD.calificacion_promedio,
            'numero_paginas', OLD.numero_paginas,
            'cantidad_calificaciones', OLD.cantidad_calificaciones,
            'numero_resenas', OLD.numero_resenas,
            'fecha_publicacion', OLD.fecha_publicacion,
            'anio_publicacion', OLD.anio_publicacion
        ),
        JSON_OBJECT(
            'id_libro', NEW.id_libro,
            'id_idioma', NEW.id_idioma,
            'id_autor', NEW.id_autor,
            'id_editorial', NEW.id_editorial,
            'titulo', NEW.titulo,
            'isbn', NEW.isbn,
            'isbn13', NEW.isbn13,
            'calificacion_promedio', NEW.calificacion_promedio,
            'numero_paginas', NEW.numero_paginas,
            'cantidad_calificaciones', NEW.cantidad_calificaciones,
            'numero_resenas', NEW.numero_resenas,
            'fecha_publicacion', NEW.fecha_publicacion,
            'anio_publicacion', NEW.anio_publicacion
        )
    );
END//

CREATE TRIGGER trg_libros_ad
AFTER DELETE ON libros
FOR EACH ROW
BEGIN
    INSERT INTO auditoria (id_usuario, id_empleado, fecha, hora, accion, detalle, resultado, tabla_afectada, datos_anteriores, datos_nuevos)
    VALUES (
        (SELECT u.id_usuario FROM usuarios u WHERE u.id_usuario = @id_usuario_sesion),
        NULL,
        CURDATE(),
        CURTIME(),
        'DELETE',
        CONCAT('Se eliminó el libro ', OLD.id_libro, ': ', LEFT(OLD.titulo, 200)),
        'EXITOSO',
        'libros',
        JSON_OBJECT(
            'id_libro', OLD.id_libro,
            'id_idioma', OLD.id_idioma,
            'id_autor', OLD.id_autor,
            'id_editorial', OLD.id_editorial,
            'titulo', OLD.titulo,
            'isbn', OLD.isbn,
            'isbn13', OLD.isbn13,
            'calificacion_promedio', OLD.calificacion_promedio,
            'numero_paginas', OLD.numero_paginas,
            'cantidad_calificaciones', OLD.cantidad_calificaciones,
            'numero_resenas', OLD.numero_resenas,
            'fecha_publicacion', OLD.fecha_publicacion,
            'anio_publicacion', OLD.anio_publicacion
        ),
        NULL
    );
END//

DELIMITER ;
