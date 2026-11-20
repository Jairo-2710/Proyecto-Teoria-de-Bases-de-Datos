USE entrecol_db;

DROP PROCEDURE IF EXISTS sp_top_n_libros;
DROP PROCEDURE IF EXISTS sp_top5_libros_por_anio;
DROP PROCEDURE IF EXISTS sp_novedades_rango;
DROP PROCEDURE IF EXISTS sp_peliculas_n_generos;
DROP PROCEDURE IF EXISTS sp_peliculas_por_genero_fechas;

DELIMITER //

CREATE PROCEDURE sp_top_n_libros(IN p_limit INT, IN p_orden VARCHAR(4))
BEGIN
    DECLARE v_orden VARCHAR(4) DEFAULT UPPER(TRIM(COALESCE(p_orden, 'ASC')));

    IF p_limit IS NULL OR p_limit <= 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El parámetro p_limit debe ser un entero mayor que cero';
    END IF;

    IF v_orden NOT IN ('ASC', 'DESC') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El parámetro p_orden debe ser ASC o DESC';
    END IF;

    SELECT
        t.id_libro,
        t.titulo,
        t.autor,
        t.editorial,
        t.calificacion_promedio,
        t.cantidad_calificaciones,
        t.anio_publicacion
    FROM (
        SELECT
            l.id_libro,
            l.titulo,
            a.nombre_autor AS autor,
            e.nombre_editorial AS editorial,
            l.calificacion_promedio,
            l.cantidad_calificaciones,
            l.anio_publicacion
        FROM libros l
        INNER JOIN autores a ON a.id_autor = l.id_autor
        LEFT JOIN editoriales e ON e.id_editorial = l.id_editorial
        ORDER BY l.calificacion_promedio DESC, l.cantidad_calificaciones DESC, l.id_libro ASC
        LIMIT p_limit
    ) t
    ORDER BY
        CASE WHEN v_orden = 'ASC' THEN t.titulo END ASC,
        CASE WHEN v_orden = 'DESC' THEN t.titulo END DESC;
END//

CREATE PROCEDURE sp_top5_libros_por_anio(IN p_tipo VARCHAR(10), IN p_orden VARCHAR(4))
BEGIN
    DECLARE v_tipo VARCHAR(10) DEFAULT UPPER(TRIM(COALESCE(p_tipo, 'MEJOR')));
    DECLARE v_orden VARCHAR(4) DEFAULT UPPER(TRIM(COALESCE(p_orden, 'ASC')));

    IF v_tipo NOT IN ('MEJOR', 'PEOR') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El parámetro p_tipo debe ser MEJOR o PEOR';
    END IF;

    IF v_orden NOT IN ('ASC', 'DESC') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El parámetro p_orden debe ser ASC o DESC';
    END IF;

    SELECT
        r.anio_publicacion,
        r.posicion,
        r.id_libro,
        r.titulo,
        r.autor,
        r.calificacion_promedio,
        r.cantidad_calificaciones
    FROM (
        SELECT
            l.anio_publicacion,
            l.id_libro,
            l.titulo,
            a.nombre_autor AS autor,
            l.calificacion_promedio,
            l.cantidad_calificaciones,
            ROW_NUMBER() OVER (
                PARTITION BY l.anio_publicacion
                ORDER BY
                    CASE WHEN v_tipo = 'MEJOR' THEN l.calificacion_promedio END DESC,
                    CASE WHEN v_tipo = 'PEOR' THEN l.calificacion_promedio END ASC,
                    l.cantidad_calificaciones DESC,
                    l.id_libro ASC
            ) AS posicion
        FROM libros l
        INNER JOIN autores a ON a.id_autor = l.id_autor
        WHERE l.anio_publicacion IS NOT NULL
          AND l.cantidad_calificaciones > 0
    ) r
    WHERE r.posicion <= 5
    ORDER BY
        r.anio_publicacion ASC,
        CASE WHEN v_orden = 'ASC' THEN r.titulo END ASC,
        CASE WHEN v_orden = 'DESC' THEN r.titulo END DESC;
END//

CREATE PROCEDURE sp_novedades_rango(IN p_fecha_inicio DATE, IN p_fecha_fin DATE)
BEGIN
    DECLARE v_inicio DATE;
    DECLARE v_fin DATE;

    IF p_fecha_inicio IS NULL OR p_fecha_fin IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Las fechas de inicio y fin son obligatorias';
    END IF;

    IF p_fecha_inicio > p_fecha_fin THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La fecha de inicio no puede ser mayor que la fecha fin';
    END IF;

    SET v_inicio = DATE_FORMAT(p_fecha_inicio, '%Y-%m-01');
    SET v_fin = LAST_DAY(p_fecha_fin);

    SELECT
        e.codigo_personal,
        p.nombre_completo,
        dp.nombre_dependencia AS dependencia,
        c.nombre_cargo AS cargo,
        DATE_FORMAT(dn.periodo_fecha, '%m/%Y') AS periodo,
        tn.nombre_tipo_novedad AS tipo_novedad,
        n.fecha_inicio,
        n.fecha_fin,
        n.dias_reportados,
        n.detalle
    FROM novedades n
    INNER JOIN tipos_novedad tn ON tn.id_tipo_novedad = n.id_tipo_novedad
    INNER JOIN detalle_nomina dn ON dn.id_detalle_nomina = n.id_detalle_nomina
    INNER JOIN dependencias dp ON dp.id_dependencia = dn.id_dependencia
    INNER JOIN afiliaciones_empleado af ON af.id_afiliacion_empleado = dn.id_afiliacion_empleado
    INNER JOIN empleados e ON e.id_empleado = af.id_empleado
    INNER JOIN personas p ON p.id_persona = e.id_persona
    INNER JOIN cargos c ON c.id_cargo = e.id_cargo
    WHERE dn.periodo_fecha BETWEEN v_inicio AND v_fin
    ORDER BY dn.periodo_fecha ASC, p.nombre_completo ASC, tn.nombre_tipo_novedad ASC;

    SELECT
        dp.nombre_dependencia AS dependencia,
        c.nombre_cargo AS cargo,
        COUNT(DISTINCT e.id_empleado) AS cantidad_empleados,
        COUNT(n.id_novedad) AS cantidad_novedades
    FROM novedades n
    INNER JOIN detalle_nomina dn ON dn.id_detalle_nomina = n.id_detalle_nomina
    INNER JOIN dependencias dp ON dp.id_dependencia = dn.id_dependencia
    INNER JOIN afiliaciones_empleado af ON af.id_afiliacion_empleado = dn.id_afiliacion_empleado
    INNER JOIN empleados e ON e.id_empleado = af.id_empleado
    INNER JOIN cargos c ON c.id_cargo = e.id_cargo
    WHERE dn.periodo_fecha BETWEEN v_inicio AND v_fin
    GROUP BY dp.nombre_dependencia, c.nombre_cargo
    ORDER BY dp.nombre_dependencia ASC, c.nombre_cargo ASC;
END//

CREATE PROCEDURE sp_peliculas_n_generos(IN p_num_generos INT, IN p_orden VARCHAR(4))
BEGIN
    DECLARE v_orden VARCHAR(4) DEFAULT UPPER(TRIM(COALESCE(p_orden, 'ASC')));

    IF p_num_generos IS NULL OR p_num_generos < 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El parámetro p_num_generos debe ser un entero mayor o igual a cero';
    END IF;

    IF v_orden NOT IN ('ASC', 'DESC') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El parámetro p_orden debe ser ASC o DESC';
    END IF;

    SELECT
        p.id_pelicula,
        p.titulo,
        p.anio_estreno,
        COUNT(pg.id_genero) AS cantidad_generos,
        GROUP_CONCAT(g.nombre_genero ORDER BY g.nombre_genero ASC SEPARATOR ', ') AS generos
    FROM peliculas p
    LEFT JOIN pelicula_generos pg ON pg.id_pelicula = p.id_pelicula
    LEFT JOIN generos g ON g.id_genero = pg.id_genero
    GROUP BY p.id_pelicula, p.titulo, p.anio_estreno
    HAVING COUNT(pg.id_genero) = p_num_generos
    ORDER BY
        CASE WHEN v_orden = 'ASC' THEN p.titulo END ASC,
        CASE WHEN v_orden = 'DESC' THEN p.titulo END DESC;

    SELECT COUNT(*) AS cantidad_peliculas
    FROM (
        SELECT p.id_pelicula
        FROM peliculas p
        LEFT JOIN pelicula_generos pg ON pg.id_pelicula = p.id_pelicula
        GROUP BY p.id_pelicula
        HAVING COUNT(pg.id_genero) = p_num_generos
    ) x;
END//

CREATE PROCEDURE sp_peliculas_por_genero_fechas(IN p_id_genero INT, IN p_fecha_inicio DATE, IN p_fecha_fin DATE, IN p_orden VARCHAR(4))
BEGIN
    DECLARE v_orden VARCHAR(4) DEFAULT UPPER(TRIM(COALESCE(p_orden, 'ASC')));

    IF p_id_genero IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El parámetro p_id_genero es obligatorio';
    END IF;

    IF p_fecha_inicio IS NULL OR p_fecha_fin IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Las fechas de inicio y fin son obligatorias';
    END IF;

    IF p_fecha_inicio > p_fecha_fin THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La fecha de inicio no puede ser mayor que la fecha fin';
    END IF;

    IF v_orden NOT IN ('ASC', 'DESC') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El parámetro p_orden debe ser ASC o DESC';
    END IF;

    SELECT
        p.id_pelicula,
        p.titulo,
        g.nombre_genero AS genero,
        p.anio_estreno,
        p.fecha_estreno
    FROM peliculas p
    INNER JOIN pelicula_generos pg ON pg.id_pelicula = p.id_pelicula
    INNER JOIN generos g ON g.id_genero = pg.id_genero
    WHERE pg.id_genero = p_id_genero
      AND (
            (p.fecha_estreno IS NOT NULL AND p.fecha_estreno BETWEEN p_fecha_inicio AND p_fecha_fin)
         OR (p.fecha_estreno IS NULL AND p.anio_estreno BETWEEN YEAR(p_fecha_inicio) AND YEAR(p_fecha_fin))
      )
    ORDER BY
        CASE WHEN v_orden = 'ASC' THEN p.titulo END ASC,
        CASE WHEN v_orden = 'DESC' THEN p.titulo END DESC;
END//

DELIMITER ;
