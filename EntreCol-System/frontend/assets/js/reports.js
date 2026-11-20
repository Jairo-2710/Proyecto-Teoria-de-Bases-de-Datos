import {
  ApiError, apiDelete, apiFetchPdf, apiGet, apiPost, apiPut, apiUpload, getToken, getUser, goToLogin
} from './api.js';
import { chartImages, destroyChart, renderBars, renderPie, renderSimpleBar } from './charts.js';

if (!getToken()) {
  goToLogin();
}

const $ = (id) => document.getElementById(id);
const PAGE_SIZE = 20;
const MONEY = new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 });
const PERIODO = /^(0[1-9]|1[0-2])\/\d{4}$/;
const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

function esc(value) {
  return String(value === null || value === undefined ? '' : value).replace(/[&<>"']/g, (c) => ESCAPES[c]);
}

function money(value) {
  return value === null || value === undefined ? '—' : MONEY.format(value);
}

function dmy(iso) {
  if (!iso) return '';
  const part = String(iso).slice(0, 10).split('-');
  return part.length === 3 ? part.reverse().join('/') : String(iso);
}

function dmyKey(text) {
  const part = String(text || '').split('/');
  return part.length === 3 ? part[2] + part[1] + part[0] : '';
}

function periodoDe(iso) {
  if (!iso) return '';
  const part = String(iso).slice(0, 10).split('-');
  return part.length === 3 ? part[1] + '/' + part[0] : '';
}

function text(value) {
  return value === null || value === undefined ? '' : String(value);
}

function toast(message, type) {
  const box = document.createElement('div');
  box.className = 'toast ' + (type || '');
  box.textContent = message;
  $('toasts').appendChild(box);
  setTimeout(() => box.remove(), 4500);
}

function fail(error) {
  if (error instanceof ApiError && error.status === 401) return;
  toast(error.message || 'Error inesperado', 'error');
}

function loading(target) {
  target.innerHTML = '<div class="loading">Cargando...</div>';
}

function pillClass(value) {
  const v = String(value || '').toUpperCase();
  if (v.includes('FALL')) return 'bad';
  if (v.includes('ERR')) return 'warn';
  return 'ok';
}

function pill(value) {
  return '<span class="pill ' + pillClass(value) + '">' + esc(value) + '</span>';
}

function kpis(target, items) {
  target.innerHTML = items
    .map((i) => '<div class="kpi"><small>' + esc(i.etiqueta) + '</small><strong>' + esc(i.valor) + '</strong></div>')
    .join('');
}

function compare(a, b) {
  const empty = (v) => v === null || v === undefined || v === '';
  if (empty(a) && empty(b)) return 0;
  if (empty(a)) return 1;
  if (empty(b)) return -1;
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return String(a).localeCompare(String(b), 'es', { numeric: true, sensitivity: 'base' });
}

function renderTable(target, columns, rows, options = {}) {
  if (!rows || !rows.length) {
    target.innerHTML = '<div class="empty">' + esc(options.empty || 'Sin registros para los filtros aplicados') + '</div>';
    target.onclick = null;
    return;
  }
  const sort = { key: null, dir: 1 };
  const draw = () => {
    let data = rows;
    if (sort.key !== null) {
      const col = columns.find((c) => c.key === sort.key);
      const pick = (r) => (col.sortValue ? col.sortValue(r) : r[col.key]);
      data = rows.slice().sort((x, y) => sort.dir * compare(pick(x), pick(y)));
    }
    const head = columns
      .map((c) => {
        const sortable = c.sortable !== false && c.key;
        const arrow = sort.key === c.key ? '<span class="arrow">' + (sort.dir === 1 ? '▲' : '▼') + '</span>' : '';
        return '<th class="' + (sortable ? 'sortable ' : '') + (c.num ? 'num' : '') + '"' +
          (sortable ? ' data-k="' + esc(c.key) + '"' : '') + '>' + esc(c.label) + arrow + '</th>';
      })
      .join('');
    const body = data
      .map((r) => '<tr>' + columns.map((c) => {
        const content = c.html ? c.html(r) : esc(c.format ? c.format(r[c.key], r) : r[c.key]);
        return '<td class="' + (c.num ? 'num ' : '') + (c.wrap ? 'wrap' : '') + '">' + content + '</td>';
      }).join('') + '</tr>')
      .join('');
    target.innerHTML = '<div class="table-wrap"><table><thead><tr>' + head + '</tr></thead><tbody>' + body +
      '</tbody></table></div>';
  };
  target.onclick = (event) => {
    const th = event.target.closest('th[data-k]');
    if (!th) return;
    if (sort.key === th.dataset.k) sort.dir = -sort.dir;
    else {
      sort.key = th.dataset.k;
      sort.dir = 1;
    }
    draw();
  };
  draw();
}

function renderGroups(target, groups, titleOf, columns) {
  target.onclick = null;
  if (!groups || !groups.length) {
    target.innerHTML = '<div class="empty">Sin registros para los filtros aplicados</div>';
    return;
  }
  target.innerHTML = '';
  groups.forEach((group, index) => {
    const details = document.createElement('details');
    details.className = 'group';
    details.open = groups.length <= 4 || index === 0;
    const summary = document.createElement('summary');
    summary.innerHTML = '<span>' + esc(titleOf(group)) + '</span><span class="pill">' + esc(group.cantidad) + (group.cantidad === 1 ? ' empleado' : ' empleados') + '</span>';
    const holder = document.createElement('div');
    details.appendChild(summary);
    details.appendChild(holder);
    target.appendChild(details);
    renderTable(holder, columns, group.empleados);
  });
}

const colFecha = (key, label) => ({ key, label, sortValue: (r) => dmyKey(r[key]) });

const state = {
  nomina: null, info: { lista: [], seleccion: null }, salud: null, novedades: null,
  ent: { peliculas: null, top: null, mejores: null, peores: null, ngen: null, generos: null, anios: null, filtros: {} }
};

const loaded = {};

async function loadNomina() {
  const orden = $('nominaOrden').value;
  ['nominaGeneral', 'nominaDep', 'nominaDepCargo'].forEach((id) => loading($(id)));
  try {
    const data = await apiGet('/nomina/reportes/general', { orden });
    const lista = data.total_empleados.empleados;
    const cols = [
      { key: 'codigo_personal', label: 'Código' },
      { key: 'nombre_completo', label: 'Nombre' },
      { key: 'dependencia', label: 'Dependencia' },
      { key: 'cargo', label: 'Cargo' },
      colFecha('fecha_ingreso', 'Fecha ingreso'),
      { key: 'eps', label: 'EPS' },
      { key: 'pension', label: 'Pensión' }
    ];
    const colsSinDep = cols.filter((c) => c.key !== 'dependencia');
    const colsSinGrupo = cols.filter((c) => c.key !== 'dependencia' && c.key !== 'cargo');
    renderTable($('nominaGeneral'), cols, lista);
    renderGroups($('nominaDep'), data.por_dependencia.grupos, (g) => g.dependencia, colsSinDep);
    renderGroups($('nominaDepCargo'), data.por_dependencia_cargo.grupos, (g) => g.dependencia + ' — ' + g.cargo, colsSinGrupo);
    const torta = data.frecuencia_dependencia.grafico_torta;
    const barras = data.frecuencia_dependencia_cargo.grafico_barras;
    renderPie('chartNominaPie', torta.etiquetas, torta.valores, 'Empleados por dependencia');
    renderBars('chartNominaBars', barras.etiquetas, barras.series, 'Dependencia por cargo');
    const resumen = [
      { etiqueta: 'Total de empleados', valor: data.total_empleados.total },
      { etiqueta: 'Dependencias', valor: data.frecuencia_dependencia.frecuencias.length },
      { etiqueta: 'Combinaciones dependencia-cargo', valor: data.frecuencia_dependencia_cargo.frecuencias.length }
    ];
    kpis($('nominaKpi'), resumen);
    state.nomina = {
      titulo: 'Reporte de Nómina',
      subtitulo: 'Orden alfabético: ' + orden,
      kpis: resumen,
      encabezados: cols.map((c) => c.label),
      filas: lista.map((r) => cols.map((c) => text(r[c.key]))),
      charts: ['chartNominaPie', 'chartNominaBars']
    };
  } catch (e) {
    ['nominaGeneral', 'nominaDep', 'nominaDepCargo'].forEach((id) => { $(id).innerHTML = '<div class="empty">No fue posible cargar el reporte</div>'; });
    fail(e);
  }
}

function renderFicha(emp) {
  const item = (label, value, wide) => '<div class="ficha-item' + (wide ? ' wide' : '') + '"><small>' + esc(label) + '</small><strong>' + esc(value) + '</strong></div>';
  $('infoFicha').innerHTML = '<div class="ficha">' +
    item('Código', emp.codigo_personal) +
    item('Nombre', emp.nombre_completo) +
    item('Dependencia', emp.dependencia) +
    item('Cargo', emp.cargo) +
    item('Fecha de ingreso', emp.fecha_ingreso || '—') +
    item('EPS', emp.eps || 'Sin afiliación') +
    item('Aporte pensión', money(emp.aporte_pension) + (emp.pension ? ' · ' + emp.pension : '')) +
    item('Salario', money(emp.salario)) +
    '</div>';
  renderTable($('infoNovedades'), [
    { key: 'tipo_novedad', label: 'Tipo' },
    { key: 'periodo', label: 'Periodo' },
    colFecha('fecha_inicio', 'Inicio'),
    colFecha('fecha_fin', 'Fin'),
    { key: 'dias_reportados', label: 'Días', num: true },
    { key: 'detalle', label: 'Detalle', wrap: true }
  ], emp.novedades, { empty: 'El empleado no registra novedades' });
}

function selectEmpleado(emp) {
  state.info.seleccion = emp;
  renderFicha(emp);
}

async function loadInfo() {
  const busqueda = $('infoBusqueda').value.trim();
  loading($('infoLista'));
  try {
    const data = await apiGet('/nomina/reportes/info-personal', { busqueda, orden: 'ASC' });
    state.info.lista = data.empleados;
    state.info.seleccion = null;
    $('infoFicha').innerHTML = '<div class="empty">Seleccione un empleado de la lista de resultados</div>';
    $('infoNovedades').innerHTML = '<div class="empty">Seleccione un empleado para ver sus novedades</div>';
    renderTable($('infoLista'), [
      { key: 'codigo_personal', label: 'Código' },
      { key: 'nombre_completo', label: 'Nombre' },
      { key: 'dependencia', label: 'Dependencia' },
      { key: 'cargo', label: 'Cargo' },
      { key: 'cantidad_novedades', label: 'Novedades', num: true },
      { label: 'Ficha', sortable: false, html: (r) => '<button type="button" class="btn btn-sm btn-primary" data-ficha="' + esc(r.id_empleado) + '">Ver ficha</button>' }
    ], data.empleados, { empty: 'No se encontraron empleados con ese criterio' });
    const target = $('infoLista');
    const sorter = target.onclick;
    target.onclick = (event) => {
      const button = event.target.closest('button[data-ficha]');
      if (button) {
        const emp = state.info.lista.find((r) => String(r.id_empleado) === button.dataset.ficha);
        if (emp) selectEmpleado(emp);
        return;
      }
      if (sorter) sorter(event);
    };
    if (data.empleados.length === 1) selectEmpleado(data.empleados[0]);
  } catch (e) {
    $('infoLista').innerHTML = '<div class="empty">No fue posible realizar la búsqueda</div>';
    fail(e);
  }
}

function flattenGroups(groups, keys) {
  const rows = [];
  groups.forEach((g) => g.empleados.forEach((emp) => {
    const row = { ...emp };
    keys.forEach((k) => { row[k] = g[k]; });
    rows.push(row);
  }));
  return rows;
}

async function loadSalud() {
  const orden = $('saludOrden').value;
  loading($('saludCargoEps'));
  loading($('saludCargoPension'));
  try {
    const data = await apiGet('/nomina/reportes/salud-pension', { orden });
    renderPie('chartEpsPie', data.frecuencia_eps.grafico_torta.etiquetas, data.frecuencia_eps.grafico_torta.valores, 'Frecuencia EPS');
    renderPie('chartPensionPie', data.frecuencia_pension.grafico_torta.etiquetas, data.frecuencia_pension.grafico_torta.valores, 'Frecuencia Pensión');
    renderBars('chartEpsDep', data.eps_por_dependencia.grafico_barras.etiquetas, data.eps_por_dependencia.grafico_barras.series, 'EPS por dependencia');
    renderBars('chartPensionDep', data.pension_por_dependencia.grafico_barras.etiquetas, data.pension_por_dependencia.grafico_barras.series, 'Pensión por dependencia');
    const eps = flattenGroups(data.cargo_eps.grupos, ['cargo', 'eps']);
    const pen = flattenGroups(data.cargo_pension.grupos, ['cargo', 'pension']);
    const base = [
      { key: 'codigo_personal', label: 'Código' },
      { key: 'nombre_completo', label: 'Nombre' },
      { key: 'dependencia', label: 'Dependencia' },
      colFecha('fecha_ingreso', 'Fecha ingreso')
    ];
    renderTable($('saludCargoEps'), [{ key: 'cargo', label: 'Cargo' }, { key: 'eps', label: 'EPS' }, ...base], eps);
    renderTable($('saludCargoPension'), [{ key: 'cargo', label: 'Cargo' }, { key: 'pension', label: 'Pensión' }, ...base], pen);
    const pensionPorId = new Map(pen.map((r) => [r.id_empleado, r.pension]));
    state.salud = {
      titulo: 'Reporte de Salud y Pensión',
      subtitulo: 'Orden alfabético: ' + orden,
      kpis: [
        { etiqueta: 'Empleados', valor: eps.length },
        { etiqueta: 'EPS distintas', valor: data.frecuencia_eps.frecuencias.length },
        { etiqueta: 'Fondos de pensión', valor: data.frecuencia_pension.frecuencias.length }
      ],
      encabezados: ['Cargo', 'EPS', 'Pensión', 'Código', 'Nombre', 'Dependencia'],
      filas: eps.map((r) => [r.cargo, r.eps, text(pensionPorId.get(r.id_empleado)), r.codigo_personal, r.nombre_completo, r.dependencia]),
      charts: ['chartEpsPie', 'chartPensionPie', 'chartEpsDep', 'chartPensionDep']
    };
  } catch (e) {
    $('saludCargoEps').innerHTML = '<div class="empty">No fue posible cargar el reporte</div>';
    $('saludCargoPension').innerHTML = '<div class="empty">No fue posible cargar el reporte</div>';
    fail(e);
  }
}

async function loadNovedades() {
  const f1 = $('novF1').value.trim();
  const f2 = $('novF2').value.trim();
  if (!PERIODO.test(f1) || !PERIODO.test(f2)) {
    toast('F1 y F2 son obligatorios y deben tener formato MM/AAAA (ej. 01/2026)', 'error');
    return;
  }
  ['novEmpleados', 'novDepCargo', 'novDetalle'].forEach((id) => loading($(id)));
  try {
    const data = await apiGet('/nomina/reportes/novedades', { f1, f2 });
    const resumen = [
      { etiqueta: 'Periodo', valor: data.desde + ' – ' + data.hasta },
      { etiqueta: 'Total novedades', valor: data.total_novedades },
      { etiqueta: 'Empleados con novedades', valor: data.total_empleados }
    ];
    kpis($('novKpi'), resumen);
    renderTable($('novEmpleados'), [
      { key: 'codigo_personal', label: 'Código' },
      { key: 'nombre_completo', label: 'Nombre' },
      { key: 'dependencia', label: 'Dependencia' },
      { key: 'cargo', label: 'Cargo' },
      { key: 'cantidad_novedades', label: 'Novedades', num: true }
    ], data.empleados, { empty: 'No hay empleados con novedades en el rango' });
    renderTable($('novDepCargo'), [
      { key: 'dependencia', label: 'Dependencia' },
      { key: 'cargo', label: 'Cargo' },
      { key: 'cantidad_empleados', label: 'Empleados', num: true },
      { key: 'cantidad_novedades', label: 'Novedades', num: true }
    ], data.por_dependencia_cargo, { empty: 'No hay novedades en el rango' });
    const detalle = [
      { key: 'codigo_personal', label: 'Código' },
      { key: 'nombre_completo', label: 'Nombre' },
      { key: 'dependencia', label: 'Dependencia' },
      { key: 'cargo', label: 'Cargo' },
      { key: 'periodo', label: 'Periodo' },
      { key: 'tipo_novedad', label: 'Tipo' },
      colFecha('fecha_inicio', 'Inicio'),
      colFecha('fecha_fin', 'Fin'),
      { key: 'dias_reportados', label: 'Días', num: true }
    ];
    renderTable($('novDetalle'), detalle, data.novedades, { empty: 'No hay novedades en el rango' });
    state.novedades = {
      titulo: 'Reporte de Novedades',
      subtitulo: 'Periodo ' + f1 + ' a ' + f2,
      kpis: resumen,
      encabezados: detalle.map((c) => c.label),
      filas: data.novedades.map((r) => detalle.map((c) => text(r[c.key]))),
      charts: []
    };
  } catch (e) {
    ['novEmpleados', 'novDepCargo', 'novDetalle'].forEach((id) => { $(id).innerHTML = '<div class="empty">No fue posible cargar el reporte</div>'; });
    fail(e);
  }
}

const ent = state.ent;

function entOrden() {
  return $('entOrden').value;
}

function updateEntKpis() {
  const items = [];
  if (ent.peliculas) items.push({ etiqueta: 'Películas del género', valor: ent.peliculas.length });
  if (ent.top) items.push({ etiqueta: 'Libros Top N', valor: ent.top.length });
  if (ent.ngen) items.push({ etiqueta: 'Películas con N géneros', valor: ent.ngen.cantidad });
  if (ent.generos) items.push({ etiqueta: 'Géneros con películas', valor: ent.generos.length });
  if (ent.anios) items.push({ etiqueta: 'Años con libros', valor: ent.anios.length });
  kpis($('entKpi'), items);
}

async function loadEntPeliculas() {
  const id_genero = $('entGenero').value;
  const f1 = $('entF1').value;
  const f2 = $('entF2').value;
  if (!id_genero || !f1 || !f2) {
    toast('Seleccione un género y las fechas F1 y F2', 'error');
    return;
  }
  loading($('entPeliculas'));
  try {
    const data = await apiGet('/entretenimiento/reportes/peliculas-genero-fechas', { id_genero, f1, f2, orden: entOrden() });
    ent.peliculas = data.peliculas;
    ent.filtros.peliculas = $('entGenero').selectedOptions[0].textContent + ' ' + dmy(f1) + ' a ' + dmy(f2);
    renderTable($('entPeliculas'), [
      { key: 'titulo', label: 'Título' },
      { key: 'genero', label: 'Género' },
      { key: 'anio_estreno', label: 'Año', num: true },
      { key: 'fecha_estreno', label: 'Fecha estreno', format: (v) => dmy(v) || '—', sortValue: (r) => r.fecha_estreno || '' }
    ], data.peliculas, { empty: 'No hay películas para el género y rango de fechas' });
    updateEntKpis();
  } catch (e) {
    $('entPeliculas').innerHTML = '<div class="empty">No fue posible cargar las películas</div>';
    fail(e);
  }
}

const colsLibro = [
  { key: 'titulo', label: 'Título' },
  { key: 'autor', label: 'Autor' },
  { key: 'anio_publicacion', label: 'Año', num: true },
  { key: 'calificacion_promedio', label: 'Calificación', num: true },
  { key: 'cantidad_calificaciones', label: 'Calificaciones', num: true }
];

async function loadEntTop() {
  const n = $('entN').value;
  if (!n || Number(n) < 1) {
    toast('Ingrese un valor N mayor o igual a 1', 'error');
    return;
  }
  loading($('entTopLibros'));
  try {
    const data = await apiGet('/entretenimiento/reportes/top-n-libros', { n, orden: entOrden() });
    ent.top = data.libros;
    ent.filtros.top = 'N = ' + n;
    renderTable($('entTopLibros'), [colsLibro[0], colsLibro[1], { key: 'editorial', label: 'Editorial' }, ...colsLibro.slice(2)], data.libros, { empty: 'No hay libros registrados' });
    updateEntKpis();
  } catch (e) {
    $('entTopLibros').innerHTML = '<div class="empty">No fue posible cargar el Top N</div>';
    fail(e);
  }
}

async function loadEntTop5() {
  loading($('entMejores'));
  loading($('entPeores'));
  try {
    const data = await apiGet('/entretenimiento/reportes/top5-libros-anio', { orden: entOrden() });
    ent.mejores = data.mejores;
    ent.peores = data.peores;
    const cols = [
      { key: 'anio_publicacion', label: 'Año', num: true },
      { key: 'posicion', label: '#', num: true },
      { key: 'titulo', label: 'Título' },
      { key: 'autor', label: 'Autor' },
      { key: 'calificacion_promedio', label: 'Calificación', num: true }
    ];
    renderTable($('entMejores'), cols, data.mejores, { empty: 'Sin libros con año de publicación' });
    renderTable($('entPeores'), cols, data.peores, { empty: 'Sin libros con año de publicación' });
  } catch (e) {
    $('entMejores').innerHTML = '<div class="empty">No fue posible cargar el Top 5</div>';
    $('entPeores').innerHTML = '<div class="empty">No fue posible cargar el Top 5</div>';
    fail(e);
  }
}

async function loadEntNGeneros() {
  const n = $('entNGeneros').value;
  if (n === '' || Number(n) < 0) {
    toast('Ingrese un valor N mayor o igual a 0', 'error');
    return;
  }
  loading($('entNGenerosTabla'));
  try {
    const data = await apiGet('/entretenimiento/reportes/peliculas-n-generos', { n, orden: entOrden() });
    ent.ngen = { filas: data.peliculas, cantidad: data.cantidad_total };
    ent.filtros.ngen = 'N = ' + n;
    renderTable($('entNGenerosTabla'), [
      { key: 'titulo', label: 'Título' },
      { key: 'anio_estreno', label: 'Año', num: true },
      { key: 'cantidad_generos', label: 'Géneros', num: true },
      { key: 'generos', label: 'Lista de géneros', wrap: true }
    ], data.peliculas, { empty: 'No hay películas con exactamente ' + n + ' géneros' });
    updateEntKpis();
  } catch (e) {
    $('entNGenerosTabla').innerHTML = '<div class="empty">No fue posible cargar la consulta</div>';
    fail(e);
  }
}

async function loadEntGeneros() {
  try {
    const data = await apiGet('/entretenimiento/reportes/frecuencia-peliculas-genero');
    ent.generos = data.datos;
    renderSimpleBar('chartGeneros', data.grafico.etiquetas, data.grafico.valores, 'Películas', 'Películas por género');
    updateEntKpis();
  } catch (e) {
    fail(e);
  }
}

async function loadEntAnios() {
  const f1 = $('entAnio1').value;
  const f2 = $('entAnio2').value;
  try {
    const data = await apiGet('/entretenimiento/reportes/frecuencia-libros-anio', { f1, f2 });
    ent.anios = data.datos;
    ent.filtros.anios = (f1 || 'inicio') + ' a ' + (f2 || 'fin');
    renderSimpleBar('chartLibrosAnio', data.grafico.etiquetas, data.grafico.valores, 'Libros', 'Libros por año de publicación');
    updateEntKpis();
  } catch (e) {
    fail(e);
  }
}

async function loadEntAll() {
  await Promise.all([loadEntPeliculas(), loadEntTop(), loadEntTop5(), loadEntNGeneros(), loadEntGeneros(), loadEntAnios()]);
}

async function initEntretenimiento() {
  try {
    const cat = await apiGet('/entretenimiento/catalogos');
    $('entGenero').innerHTML = cat.generos.map((g) => '<option value="' + esc(g.id_genero) + '">' + esc(g.nombre_genero) + '</option>').join('');
  } catch (e) {
    fail(e);
  }
  await loadEntAll();
}

const crud = { entity: 'empleados', action: 'crear', cat: null, empleados: [], editing: null, page: 1, busqueda: '', rows: new Map() };

const opt = (items, value, label) => items.map((i) => ({ value: i[value], label: typeof label === 'function' ? label(i) : i[label] }));

const ENTITIES = {
  empleados: {
    nombre: 'Empleado',
    path: '/nomina/empleados',
    idKey: 'id_empleado',
    searchable: true,
    resumen: (r) => r.codigo_personal + ' — ' + r.nombre_completo,
    fields: () => [
      { name: 'codigo_personal', label: 'Código personal', type: 'text', required: true },
      { name: 'nombre_completo', label: 'Nombre completo', type: 'text', required: true },
      { name: 'numero_documento', label: 'Número de documento', type: 'text' },
      { name: 'fecha_nacimiento', label: 'Fecha de nacimiento', type: 'date' },
      { name: 'direccion_contacto', label: 'Dirección de contacto', type: 'text' },
      { name: 'id_cargo', label: 'Cargo', type: 'select', required: true, options: opt(crud.cat.cargos, 'id_cargo', (c) => c.nombre_dependencia + ' — ' + c.nombre_cargo) },
      { name: 'salario', label: 'Salario', type: 'number', required: true, step: '0.01', min: '0' },
      { name: 'fecha_ingreso', label: 'Fecha de ingreso', type: 'date', required: true },
      { name: 'id_eps', label: 'EPS', type: 'select', required: true, options: opt(crud.cat.eps, 'id_eps', 'nombre_eps') },
      { name: 'id_arl', label: 'ARL', type: 'select', required: true, options: opt(crud.cat.arl, 'id_arl', 'nombre_arl') },
      { name: 'id_fondo_pension', label: 'Fondo de pensión', type: 'select', required: true, options: opt(crud.cat.fondos_pension, 'id_fondo_pension', 'nombre_fondo_pension') },
      { name: 'fecha_afiliacion', label: 'Fecha de afiliación', type: 'date', createOnly: true }
    ],
    columns: [
      { key: 'id_empleado', label: 'ID', num: true },
      { key: 'codigo_personal', label: 'Código' },
      { key: 'nombre_completo', label: 'Nombre' },
      { key: 'dependencia', label: 'Dependencia' },
      { key: 'cargo', label: 'Cargo' },
      { key: 'salario', label: 'Salario', num: true, format: (v) => money(v) },
      { key: 'fecha_ingreso', label: 'Ingreso', format: (v) => dmy(v) },
      { key: 'eps', label: 'EPS' }
    ]
  },
  novedades: {
    nombre: 'Novedad',
    fem: true,
    path: '/nomina/novedades',
    idKey: 'id_novedad',
    searchable: false,
    resumen: (r) => '#' + r.id_novedad + ' ' + r.nombre_completo + ' (' + r.tipo_novedad + ')',
    fields: () => [
      { name: 'id_empleado', label: 'Empleado', type: 'select', required: true, options: opt(crud.empleados, 'id_empleado', (e) => e.codigo_personal + ' — ' + e.nombre_completo) },
      { name: 'periodo', label: 'Periodo (MM/AAAA)', type: 'text', required: true, placeholder: '01/2026', pattern: PERIODO },
      { name: 'id_tipo_novedad', label: 'Tipo de novedad', type: 'select', required: true, options: opt(crud.cat.tipos_novedad, 'id_tipo_novedad', 'nombre_tipo_novedad') },
      { name: 'fecha_inicio', label: 'Fecha de inicio', type: 'date' },
      { name: 'fecha_fin', label: 'Fecha de fin', type: 'date' },
      { name: 'dias_reportados', label: 'Días reportados', type: 'number', required: true, min: '0', max: '31', step: '1' },
      { name: 'detalle', label: 'Detalle', type: 'textarea', full: true }
    ],
    prefill: (r) => ({ ...r, periodo: periodoDe(r.periodo_fecha) }),
    columns: [
      { key: 'id_novedad', label: 'ID', num: true },
      { key: 'codigo_personal', label: 'Código' },
      { key: 'nombre_completo', label: 'Empleado' },
      { key: 'tipo_novedad', label: 'Tipo' },
      { key: 'periodo_fecha', label: 'Periodo', format: (v) => periodoDe(v) },
      { key: 'fecha_inicio', label: 'Inicio', format: (v) => dmy(v) },
      { key: 'fecha_fin', label: 'Fin', format: (v) => dmy(v) },
      { key: 'dias_reportados', label: 'Días', num: true },
      { key: 'detalle', label: 'Detalle', wrap: true }
    ]
  },
  peliculas: {
    nombre: 'Película',
    fem: true,
    path: '/entretenimiento/peliculas',
    idKey: 'id_pelicula',
    searchable: true,
    paginated: true,
    resumen: (r) => r.titulo,
    fields: () => [
      { name: 'titulo', label: 'Título', type: 'text', required: true, full: true },
      { name: 'fecha_estreno', label: 'Fecha de estreno', type: 'date' },
      { name: 'anio_estreno', label: 'Año de estreno', type: 'number', min: '1800', max: '2200', step: '1' },
      { name: 'id_idioma', label: 'Idioma', type: 'select', options: opt(crud.cat.idiomas, 'id_idioma', (i) => i.codigo_idioma + ' — ' + i.nombre_idioma) },
      { name: 'sinopsis', label: 'Sinopsis', type: 'textarea', full: true },
      { name: 'generos', label: 'Géneros (Ctrl/Cmd para varios)', type: 'multi', options: opt(crud.cat.generos, 'id_genero', 'nombre_genero'), full: true }
    ],
    prefill: (r) => ({ ...r, generos: (r.generos || []).map((g) => g.id_genero) }),
    columns: [
      { key: 'id_pelicula', label: 'ID', num: true },
      { key: 'titulo', label: 'Título' },
      { key: 'anio_estreno', label: 'Año', num: true },
      { key: 'fecha_estreno', label: 'Estreno', format: (v) => dmy(v) },
      { key: 'idioma', label: 'Idioma' },
      { key: 'generos', label: 'Géneros', wrap: true, format: (v) => (v || []).map((g) => g.nombre_genero).join(', '), sortable: false }
    ]
  },
  libros: {
    nombre: 'Libro',
    path: '/entretenimiento/libros',
    idKey: 'id_libro',
    searchable: true,
    paginated: true,
    resumen: (r) => r.titulo,
    fields: () => [
      { name: 'titulo', label: 'Título', type: 'text', required: true, full: true },
      { name: 'id_autor', label: 'Autor principal', type: 'select', required: true, options: opt(crud.cat.autores, 'id_autor', 'nombre_autor') },
      { name: 'id_editorial', label: 'Editorial', type: 'select', options: opt(crud.cat.editoriales, 'id_editorial', 'nombre_editorial') },
      { name: 'id_idioma', label: 'Idioma', type: 'select', options: opt(crud.cat.idiomas, 'id_idioma', (i) => i.codigo_idioma + ' — ' + i.nombre_idioma) },
      { name: 'isbn', label: 'ISBN', type: 'text' },
      { name: 'isbn13', label: 'ISBN-13', type: 'text' },
      { name: 'calificacion_promedio', label: 'Calificación promedio (0 a 5)', type: 'number', min: '0', max: '5', step: '0.01' },
      { name: 'numero_paginas', label: 'Número de páginas', type: 'number', min: '0', step: '1' },
      { name: 'cantidad_calificaciones', label: 'Cantidad de calificaciones', type: 'number', min: '0', step: '1' },
      { name: 'numero_resenas', label: 'Número de reseñas', type: 'number', min: '0', step: '1' },
      { name: 'fecha_publicacion', label: 'Fecha de publicación', type: 'date' },
      { name: 'coautores', label: 'Coautores (Ctrl/Cmd para varios)', type: 'multi', options: opt(crud.cat.autores, 'id_autor', 'nombre_autor'), full: true }
    ],
    prefill: (r) => ({
      ...r,
      coautores: (r.autores || []).map((a) => a.id_autor).filter((id) => id !== r.id_autor)
    }),
    columns: [
      { key: 'id_libro', label: 'ID', num: true },
      { key: 'titulo', label: 'Título' },
      { key: 'autor', label: 'Autor' },
      { key: 'editorial', label: 'Editorial' },
      { key: 'calificacion_promedio', label: 'Calificación', num: true },
      { key: 'anio_publicacion', label: 'Año', num: true },
      { key: 'isbn', label: 'ISBN' }
    ]
  }
};

async function ensureCrudCatalogs() {
  if (crud.cat) return;
  const [nomina, entretenimiento] = await Promise.all([apiGet('/nomina/catalogos'), apiGet('/entretenimiento/catalogos')]);
  crud.cat = { ...nomina, ...entretenimiento };
}

async function refreshEmpleadosCatalog() {
  const data = await apiGet('/nomina/empleados', { limite: 1000, orden: 'ASC' });
  crud.empleados = data.empleados;
}

function fieldHtml(field, value) {
  const id = 'crud_' + field.name;
  const attrs = (field.required ? ' required' : '') +
    (field.min !== undefined ? ' min="' + field.min + '"' : '') +
    (field.max !== undefined ? ' max="' + field.max + '"' : '') +
    (field.step !== undefined ? ' step="' + field.step + '"' : '') +
    (field.placeholder ? ' placeholder="' + esc(field.placeholder) + '"' : '');
  let control;
  if (field.type === 'select') {
    control = '<select id="' + id + '" name="' + field.name + '"' + (field.required ? ' required' : '') + '>' +
      '<option value="">' + (field.required ? 'Seleccione...' : '— Sin valor —') + '</option>' +
      field.options.map((o) => '<option value="' + esc(o.value) + '"' + (String(o.value) === String(value) ? ' selected' : '') + '>' + esc(o.label) + '</option>').join('') +
      '</select>';
  } else if (field.type === 'multi') {
    const chosen = (value || []).map(String);
    control = '<select id="' + id + '" name="' + field.name + '" multiple>' +
      field.options.map((o) => '<option value="' + esc(o.value) + '"' + (chosen.includes(String(o.value)) ? ' selected' : '') + '>' + esc(o.label) + '</option>').join('') +
      '</select>';
  } else if (field.type === 'textarea') {
    control = '<textarea id="' + id + '" name="' + field.name + '" maxlength="2000">' + esc(value) + '</textarea>';
  } else {
    const shown = field.type === 'date' ? text(value).slice(0, 10) : text(value);
    control = '<input id="' + id + '" name="' + field.name + '" type="' + field.type + '"' + attrs + ' value="' + esc(shown) + '">';
  }
  return '<label class="field' + (field.full ? ' full' : '') + '"><span>' + esc(field.label) + (field.required ? ' *' : '') + '</span>' + control + '</label>';
}

function collectForm(form, fields, editing) {
  const payload = {};
  for (const field of fields) {
    if (editing && field.createOnly) continue;
    const el = form.elements[field.name];
    let value;
    if (field.type === 'multi') {
      value = Array.from(el.selectedOptions).map((o) => Number(o.value));
    } else if (field.type === 'number') {
      value = el.value === '' ? null : Number(el.value);
    } else if (field.type === 'select') {
      value = el.value === '' ? null : Number(el.value);
    } else {
      const raw = el.value.trim();
      value = raw === '' ? null : raw;
    }
    const empty = value === null || (Array.isArray(value) && field.required && !value.length);
    if (field.required && empty) {
      el.focus();
      throw new Error('El campo "' + field.label + '" es obligatorio');
    }
    if (field.pattern && value !== null && !field.pattern.test(value)) {
      el.focus();
      throw new Error('El campo "' + field.label + '" no tiene el formato esperado');
    }
    if (value !== null || editing) payload[field.name] = value;
  }
  return payload;
}

function renderForm(box, entity, row) {
  const def = ENTITIES[entity];
  const fields = def.fields().filter((f) => !(row && f.createOnly));
  const source = row ? (def.prefill ? def.prefill(row) : row) : {};
  box.innerHTML = '<form id="crudForm" novalidate><div class="form-grid">' +
    fields.map((f) => fieldHtml(f, source[f.name])).join('') +
    '</div><div class="form-actions"><button type="submit" class="btn btn-primary">' + (row ? 'Guardar cambios' : 'Crear ' + def.nombre.toLowerCase()) + '</button>' +
    (row ? '<button type="button" class="btn btn-ghost" id="crudCancel">Cancelar edición</button>' : '<button type="reset" class="btn btn-ghost">Limpiar</button>') +
    '</div></form>';
  const form = $('crudForm');
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    let payload;
    try {
      payload = collectForm(form, fields, Boolean(row));
    } catch (e) {
      toast(e.message, 'error');
      return;
    }
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    try {
      if (row) {
        await apiPut(def.path + '/' + row[def.idKey], payload);
        toast(def.nombre + (def.fem ? ' actualizada' : ' actualizado') + ' correctamente', 'success');
        crud.editing = null;
        renderCrud();
      } else {
        await apiPost(def.path, payload);
        toast(def.nombre + (def.fem ? ' creada' : ' creado') + ' correctamente', 'success');
        form.reset();
        if (entity === 'empleados') await refreshEmpleadosCatalog();
      }
    } catch (e) {
      fail(e);
    } finally {
      button.disabled = false;
    }
  });
  const cancel = $('crudCancel');
  if (cancel) {
    cancel.addEventListener('click', () => {
      crud.editing = null;
      renderCrud();
    });
  }
}

async function loadCrudList(box) {
  const def = ENTITIES[crud.entity];
  loading(box);
  const params = def.paginated
    ? { page: crud.page, limit: PAGE_SIZE, busqueda: crud.busqueda }
    : { limite: PAGE_SIZE, offset: (crud.page - 1) * PAGE_SIZE, busqueda: def.searchable ? crud.busqueda : '' };
  try {
    const data = await apiGet(def.path, params);
    const rows = def.paginated ? data.datos : data[Object.keys(data).find((k) => Array.isArray(data[k]))];
    crud.rows = new Map(rows.map((r) => [String(r[def.idKey]), r]));
    const columns = def.columns.slice();
    if (crud.action !== 'listar') {
      const editar = crud.action === 'editar';
      columns.push({
        label: 'Acciones',
        sortable: false,
        html: (r) => '<div class="row-actions"><button type="button" class="btn btn-sm ' + (editar ? 'btn-primary' : 'btn-danger') +
          '" data-act="' + (editar ? 'edit' : 'delete') + '" data-id="' + esc(r[def.idKey]) + '">' + (editar ? 'Editar' : 'Eliminar') + '</button></div>'
      });
    }
    const hasMore = def.paginated ? data.page < data.paginas : rows.length === PAGE_SIZE;
    const info = def.paginated ? 'Página ' + data.page + ' de ' + Math.max(data.paginas, 1) + ' · ' + data.total + ' registros' : 'Página ' + crud.page;
    box.innerHTML = '<div id="crudTable"></div><div class="pager"><span>' + esc(info) + '</span>' +
      '<button type="button" class="btn btn-sm btn-ghost" id="crudPrev"' + (crud.page <= 1 ? ' disabled' : '') + '>Anterior</button>' +
      '<button type="button" class="btn btn-sm btn-ghost" id="crudNext"' + (hasMore ? '' : ' disabled') + '>Siguiente</button></div>';
    renderTable($('crudTable'), columns, rows, { empty: 'No hay registros' });
    const table = $('crudTable');
    const sorter = table.onclick;
    table.onclick = (event) => {
      const button = event.target.closest('button[data-act]');
      if (!button) {
        if (sorter) sorter(event);
        return;
      }
      const row = crud.rows.get(button.dataset.id);
      if (!row) return;
      if (button.dataset.act === 'edit') {
        crud.editing = row;
        crud.scroll = true;
        renderCrud();
      } else {
        removeRow(def, row);
      }
    };
    $('crudPrev').addEventListener('click', () => { crud.page -= 1; loadCrudList(box); });
    $('crudNext').addEventListener('click', () => { crud.page += 1; loadCrudList(box); });
  } catch (e) {
    box.innerHTML = '<div class="empty">No fue posible cargar el listado</div>';
    fail(e);
  }
}

function confirmDialog(title, message) {
  return new Promise((resolve) => {
    $('confirmTitle').textContent = title;
    $('confirmText').textContent = message;
    const modal = $('confirmModal');
    modal.classList.remove('hidden');
    const done = (value) => {
      modal.classList.add('hidden');
      $('confirmYes').onclick = null;
      $('confirmNo').onclick = null;
      resolve(value);
    };
    $('confirmYes').onclick = () => done(true);
    $('confirmNo').onclick = () => done(false);
  });
}

async function removeRow(def, row) {
  const accepted = await confirmDialog('Eliminar ' + def.nombre.toLowerCase(), '¿Confirma eliminar "' + def.resumen(row) + '"? Esta acción no se puede deshacer.');
  if (!accepted) return;
  try {
    await apiDelete(def.path + '/' + row[def.idKey]);
    toast(def.nombre + (def.fem ? ' eliminada' : ' eliminado') + ' correctamente', 'success');
    if (crud.entity === 'empleados') await refreshEmpleadosCatalog();
    loadCrudList($('crudListBox'));
  } catch (e) {
    fail(e);
  }
}

async function renderCrud() {
  const panel = $('crudPanel');
  const def = ENTITIES[crud.entity];
  loading(panel);
  try {
    await ensureCrudCatalogs();
    if (crud.entity === 'novedades' || crud.entity === 'empleados') await refreshEmpleadosCatalog();
  } catch (e) {
    panel.innerHTML = '<div class="empty">No fue posible cargar los catálogos</div>';
    fail(e);
    return;
  }
  const titles = { crear: 'Crear', listar: 'Listar', editar: 'Editar', eliminar: 'Eliminar' };
  panel.innerHTML = '<h3>' + titles[crud.action] + ' — ' + esc(def.nombre) + '</h3>' +
    '<div id="crudFormBox"></div><div id="crudToolsBox"></div><div id="crudListBox"></div>';
  if (crud.action === 'crear') {
    renderForm($('crudFormBox'), crud.entity, null);
    return;
  }
  if (crud.action === 'editar' && crud.editing) {
    $('crudFormBox').innerHTML = '';
    const box = document.createElement('div');
    box.className = 'card';
    box.style.background = 'var(--bg-2)';
    box.innerHTML = '<h4>Editando: ' + esc(def.resumen(crud.editing)) + '</h4><div id="crudEditForm"></div>';
    $('crudFormBox').appendChild(box);
    renderForm($('crudEditForm'), crud.entity, crud.editing);
    if (crud.scroll) {
      crud.scroll = false;
      $('crudFormBox').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }
  if (def.searchable) {
    $('crudToolsBox').innerHTML = '<div class="crud-bar"><label class="inline-field grow"><span>Buscar</span><input type="search" id="crudSearch" value="' + esc(crud.busqueda) + '" placeholder="Texto de búsqueda"></label>' +
      '<button type="button" class="btn btn-primary" id="crudSearchBtn">Buscar</button></div>';
    const run = () => {
      crud.busqueda = $('crudSearch').value.trim();
      crud.page = 1;
      loadCrudList($('crudListBox'));
    };
    $('crudSearchBtn').addEventListener('click', run);
    $('crudSearch').addEventListener('keydown', (event) => {
      if (event.key === 'Enter') run();
    });
  }
  loadCrudList($('crudListBox'));
}

function selectCrudTab(group, attr, value) {
  document.querySelectorAll('#' + group + ' .tab').forEach((t) => t.classList.toggle('active', t.dataset[attr] === value));
}

function setCrud(entity, action) {
  if (entity !== undefined) {
    if (entity !== crud.entity) crud.busqueda = '';
    crud.entity = entity;
  }
  if (action !== undefined) crud.action = action;
  crud.editing = null;
  crud.page = 1;
  selectCrudTab('crudEntities', 'entity', crud.entity);
  selectCrudTab('crudActions', 'action', crud.action);
  renderCrud();
}

function renderEtlResult(payload, ok) {
  const resultado = payload.resultado || {};
  const parts = Object.entries(resultado).map(([key, value]) => {
    const label = key.replace(/_/g, ' ');
    const shown = key === 'estado' ? pill(value) : esc(typeof value === 'object' ? JSON.stringify(value) : value);
    return '<div class="kpi"><small>' + esc(label) + '</small><strong style="font-size:18px">' + shown + '</strong></div>';
  });
  $('etlResult').innerHTML = '<div class="alert ' + (ok ? 'alert-success' : 'alert-error') + '" style="margin-top:16px">' +
    esc(ok ? 'Archivo procesado: ' + payload.archivo + ' (' + payload.tipo + ')' : 'El procesamiento falló: ' + (resultado.error || payload.archivo)) +
    '</div><div class="etl-summary">' + parts.join('') + '</div>';
}

async function loadEtlHistory() {
  const box = $('etlHistory');
  loading(box);
  try {
    const data = await apiGet('/archivos');
    renderTable(box, archivoColumns(), data.archivos, { empty: 'Aún no hay cargas registradas' });
  } catch (e) {
    box.innerHTML = '<div class="empty">No fue posible cargar el historial</div>';
    fail(e);
  }
}

function archivoColumns() {
  return [
    { key: 'id_archivo', label: 'ID', num: true },
    { key: 'nombre_archivo', label: 'Archivo' },
    { key: 'tipo', label: 'Tipo' },
    { key: 'estado', label: 'Estado', html: (r) => pill(r.estado) },
    { key: 'cantidad_errores', label: 'Errores', num: true },
    { key: 'username', label: 'Usuario' },
    { key: 'fecha', label: 'Fecha', format: (v) => dmy(v) },
    { key: 'hora', label: 'Hora' }
  ];
}

async function submitEtl(event) {
  event.preventDefault();
  const input = $('etlFile');
  const file = input.files[0];
  if (!file) {
    toast('Seleccione un archivo .xlsx, .dat o .json', 'error');
    return;
  }
  if (!/\.(xlsx|dat|json)$/i.test(file.name)) {
    toast('Formato no permitido. Use .xlsx, .dat o .json', 'error');
    return;
  }
  const button = $('etlSubmit');
  button.disabled = true;
  button.textContent = 'Procesando...';
  $('etlResult').innerHTML = '<div class="loading">Procesando archivo, esto puede tardar unos segundos...</div>';
  try {
    const data = await apiUpload('/etl/upload', file);
    renderEtlResult(data, true);
    toast('Carga finalizada', 'success');
    input.value = '';
  } catch (e) {
    if (e instanceof ApiError && e.data && e.data.resultado) renderEtlResult(e.data, false);
    else $('etlResult').innerHTML = '<div class="alert alert-error" style="margin-top:16px">' + esc(e.message) + '</div>';
    fail(e);
  } finally {
    button.disabled = false;
    button.textContent = 'Procesar archivo';
    loadEtlHistory();
  }
}

let auditTimer = null;

async function loadAudit() {
  if (document.querySelector('#auditTable details[open]')) return;
  try {
    const [audit, files] = await Promise.all([apiGet('/auditoria'), apiGet('/archivos')]);
    renderTable($('auditTable'), [
      { key: 'id_auditoria', label: 'ID', num: true },
      { key: 'fecha', label: 'Fecha', format: (v) => dmy(v), sortValue: (r) => r.fecha + ' ' + r.hora },
      { key: 'hora', label: 'Hora' },
      { key: 'username', label: 'Usuario', format: (v) => v || '—' },
      { key: 'accion', label: 'Acción' },
      { key: 'tabla_afectada', label: 'Tabla', format: (v) => v || '—' },
      { key: 'resultado', label: 'Resultado', html: (r) => pill(r.resultado) },
      { key: 'detalle', label: 'Detalle', wrap: true, format: (v) => (v && v.length > 160 ? v.slice(0, 160) + '…' : v) },
      {
        label: 'Datos',
        sortable: false,
        html: (r) => {
          if (!r.datos_anteriores && !r.datos_nuevos) return '—';
          const json = JSON.stringify({ anteriores: r.datos_anteriores, nuevos: r.datos_nuevos }, null, 2);
          return '<details><summary>Ver</summary><pre class="json">' + esc(json) + '</pre></details>';
        }
      }
    ], audit.auditoria, { empty: 'Sin registros de auditoría' });
    renderTable($('archivosTable'), archivoColumns(), files.archivos, { empty: 'Sin archivos cargados' });
    $('auditStamp').textContent = 'Actualizado ' + new Date().toLocaleTimeString('es-CO');
  } catch (e) {
    fail(e);
  }
}

function startAudit() {
  stopAudit();
  loadAudit();
  auditTimer = setInterval(() => {
    if ($('auditAuto').checked) loadAudit();
  }, 10000);
}

function stopAudit() {
  if (auditTimer) clearInterval(auditTimer);
  auditTimer = null;
}

let pdfUrl = null;
let pdfName = 'reporte.pdf';

function closePdf() {
  $('pdfModal').classList.add('hidden');
  $('pdfViewer').src = 'about:blank';
  if (pdfUrl) URL.revokeObjectURL(pdfUrl);
  pdfUrl = null;
}

function entPdf() {
  const filas = [];
  const libro = (seccion, r) => filas.push([seccion, r.titulo, r.autor, text(r.anio_publicacion), text(r.calificacion_promedio)]);
  if (ent.peliculas) ent.peliculas.forEach((r) => filas.push(['Películas por género', r.titulo, r.genero, text(r.anio_estreno), r.fecha_estreno ? dmy(r.fecha_estreno) : '']));
  if (ent.top) ent.top.forEach((r) => libro('Top N libros', r));
  if (ent.mejores) ent.mejores.forEach((r) => libro('Top 5 mejor rating por año', r));
  if (ent.peores) ent.peores.forEach((r) => libro('Top 5 peor rating por año', r));
  if (ent.ngen) ent.ngen.filas.forEach((r) => filas.push(['Películas con N géneros', r.titulo, r.generos, text(r.anio_estreno), text(r.cantidad_generos)]));
  const subtitulo = ['Orden: ' + entOrden()]
    .concat(Object.entries({ peliculas: 'Género', top: 'Top', ngen: 'N géneros', anios: 'Años libros' })
      .filter(([k]) => ent.filtros[k])
      .map(([k, label]) => label + ' ' + ent.filtros[k]))
    .join(' | ');
  const resumen = [];
  if (ent.peliculas) resumen.push({ etiqueta: 'Películas del género', valor: ent.peliculas.length });
  if (ent.top) resumen.push({ etiqueta: 'Libros Top N', valor: ent.top.length });
  if (ent.ngen) resumen.push({ etiqueta: 'Películas con N géneros', valor: ent.ngen.cantidad });
  return {
    titulo: 'Reporte Base-Entretenimiento',
    subtitulo,
    kpis: resumen,
    encabezados: ['Sección', 'Título', 'Autor / Género', 'Año', 'Calificación / Detalle'],
    filas,
    charts: ['chartGeneros', 'chartLibrosAnio']
  };
}

function infoPdf() {
  const emp = state.info.seleccion;
  if (!emp) return null;
  return {
    titulo: 'Información Personal - ' + emp.nombre_completo,
    subtitulo: 'Código ' + emp.codigo_personal,
    kpis: [
      { etiqueta: 'Código', valor: emp.codigo_personal },
      { etiqueta: 'Nombre', valor: emp.nombre_completo },
      { etiqueta: 'Dependencia', valor: emp.dependencia },
      { etiqueta: 'Cargo', valor: emp.cargo },
      { etiqueta: 'Fecha de ingreso', valor: emp.fecha_ingreso || '' },
      { etiqueta: 'EPS', valor: emp.eps || 'Sin afiliación' },
      { etiqueta: 'Aporte pensión', valor: money(emp.aporte_pension) },
      { etiqueta: 'Salario', valor: money(emp.salario) }
    ],
    encabezados: ['Tipo', 'Periodo', 'Inicio', 'Fin', 'Días', 'Detalle'],
    filas: emp.novedades.map((n) => [n.tipo_novedad, n.periodo, n.fecha_inicio, n.fecha_fin, text(n.dias_reportados), n.detalle]),
    charts: []
  };
}

const PDF_SOURCES = {
  nomina: () => state.nomina,
  info: infoPdf,
  salud: () => state.salud,
  novedades: () => state.novedades,
  entretenimiento: entPdf
};

const PDF_EMPTY = {
  nomina: 'Consulte primero el reporte de nómina',
  info: 'Seleccione un empleado para generar su ficha en PDF',
  salud: 'Consulte primero el reporte de salud y pensión',
  novedades: 'Consulte primero el rango de novedades (F1 y F2)',
  entretenimiento: 'Consulte primero el reporte de entretenimiento'
};

async function openPdf(key) {
  const spec = PDF_SOURCES[key]();
  if (!spec) {
    toast(PDF_EMPTY[key], 'error');
    return;
  }
  const modal = $('pdfModal');
  $('pdfTitle').textContent = 'Vista previa — ' + spec.titulo;
  $('pdfLoading').classList.remove('hidden');
  $('pdfViewer').src = 'about:blank';
  modal.classList.remove('hidden');
  const payload = {
    titulo: spec.titulo,
    subtitulo: spec.subtitulo,
    resumen_kpis: spec.kpis,
    encabezados: spec.encabezados,
    filas: spec.filas,
    imagenes_base64: chartImages(spec.charts)
  };
  try {
    const { blob, filename } = await apiFetchPdf(payload);
    if (pdfUrl) URL.revokeObjectURL(pdfUrl);
    pdfUrl = URL.createObjectURL(blob);
    pdfName = filename;
    const viewer = $('pdfViewer');
    viewer.onload = () => $('pdfLoading').classList.add('hidden');
    viewer.src = pdfUrl;
    setTimeout(() => $('pdfLoading').classList.add('hidden'), 2500);
  } catch (e) {
    closePdf();
    fail(e);
  }
}

function printPdf() {
  const viewer = $('pdfViewer');
  if (!pdfUrl) return;
  try {
    viewer.contentWindow.focus();
    viewer.contentWindow.print();
  } catch (e) {
    toast('No fue posible abrir el diálogo de impresión. Use Descargar.', 'error');
  }
}

function downloadPdf() {
  if (!pdfUrl) return;
  const link = document.createElement('a');
  link.href = pdfUrl;
  link.download = pdfName;
  document.body.appendChild(link);
  link.click();
  link.remove();
}

const VIEWS = {
  nomina: { title: 'Reporte Nómina', init: loadNomina },
  info: { title: 'Reporte Información Personal', init: loadInfo },
  salud: { title: 'Reporte Salud y Pensión', init: loadSalud },
  novedades: { title: 'Reporte Novedades', init: null },
  entretenimiento: { title: 'Reporte Base-Entretenimiento', init: initEntretenimiento },
  crud: { title: 'Gestión CRUD', init: () => setCrud(crud.entity, crud.action) },
  etl: { title: 'Carga Masiva ETL', init: loadEtlHistory, always: true },
  auditoria: { title: 'Auditoría y Trazabilidad', init: startAudit, always: true }
};

function showView(name) {
  const view = VIEWS[name];
  if (!view) return;
  if (name !== 'auditoria') stopAudit();
  document.querySelectorAll('.view').forEach((v) => v.classList.toggle('active', v.id === 'view-' + name));
  document.querySelectorAll('.nav-item').forEach((n) => n.classList.toggle('active', n.dataset.view === name));
  $('viewTitle').textContent = view.title;
  closeMenu();
  if (view.init && (view.always || !loaded[name])) {
    loaded[name] = true;
    view.init();
  }
}

function openMenu() {
  $('sidebar').classList.add('open');
  $('sidebarBackdrop').classList.add('show');
}

function closeMenu() {
  $('sidebar').classList.remove('open');
  $('sidebarBackdrop').classList.remove('show');
}

function bind() {
  const user = getUser() || {};
  $('userName').textContent = user.username || 'usuario';
  $('userRole').textContent = user.rol || '';
  $('userAvatar').textContent = (user.username || 'U').charAt(0);
  $('logoutBtn').addEventListener('click', goToLogin);
  $('menuBtn').addEventListener('click', openMenu);
  $('sidebarBackdrop').addEventListener('click', closeMenu);
  $('nav').addEventListener('click', (event) => {
    const item = event.target.closest('.nav-item');
    if (item) showView(item.dataset.view);
  });

  $('nominaLoad').addEventListener('click', loadNomina);
  $('nominaOrden').addEventListener('change', loadNomina);
  $('nominaPdf').addEventListener('click', () => openPdf('nomina'));

  $('infoBuscar').addEventListener('click', loadInfo);
  $('infoBusqueda').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') loadInfo();
  });
  $('infoPdf').addEventListener('click', () => openPdf('info'));

  $('saludLoad').addEventListener('click', loadSalud);
  $('saludOrden').addEventListener('change', loadSalud);
  $('saludPdf').addEventListener('click', () => openPdf('salud'));

  $('novForm').addEventListener('submit', (event) => {
    event.preventDefault();
    loadNovedades();
  });
  $('novPdf').addEventListener('click', () => openPdf('novedades'));

  $('entOrden').addEventListener('change', () => {
    loadEntPeliculas();
    loadEntTop();
    loadEntTop5();
    loadEntNGeneros();
  });
  $('entLoadAll').addEventListener('click', loadEntAll);
  $('entFormPeliculas').addEventListener('submit', (event) => { event.preventDefault(); loadEntPeliculas(); });
  $('entFormTop').addEventListener('submit', (event) => { event.preventDefault(); loadEntTop(); });
  $('entFormGeneros').addEventListener('submit', (event) => { event.preventDefault(); loadEntNGeneros(); });
  $('entFormAnios').addEventListener('submit', (event) => { event.preventDefault(); loadEntAnios(); });
  $('entPdf').addEventListener('click', () => openPdf('entretenimiento'));

  $('crudEntities').addEventListener('click', (event) => {
    const tab = event.target.closest('.tab');
    if (tab) setCrud(tab.dataset.entity, undefined);
  });
  $('crudActions').addEventListener('click', (event) => {
    const tab = event.target.closest('.tab');
    if (tab) setCrud(undefined, tab.dataset.action);
  });

  $('etlForm').addEventListener('submit', submitEtl);
  $('auditRefresh').addEventListener('click', loadAudit);

  $('pdfPrint').addEventListener('click', printPdf);
  $('pdfDownload').addEventListener('click', downloadPdf);
  $('pdfClose').addEventListener('click', closePdf);
  $('pdfModal').addEventListener('click', (event) => {
    if (event.target === $('pdfModal')) closePdf();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !$('pdfModal').classList.contains('hidden')) closePdf();
  });
}

bind();
showView('nomina');
