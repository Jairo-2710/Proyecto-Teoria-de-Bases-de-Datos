import base64
import binascii
import io
import re
from datetime import datetime

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from fpdf.fonts import FontFace

TITULO_CORPORATIVO = "EntreCOL+ | ColPlus-Solutions"
COLOR_PRIMARIO = (20, 61, 107)
COLOR_SECUNDARIO = (232, 238, 246)
COLOR_TEXTO = (33, 37, 41)
COLOR_BORDE = (190, 200, 212)
COLOR_ZEBRA = (246, 248, 251)
MAX_IMAGENES = 12
MAX_CARACTERES_CELDA = 1500
PATRON_DATA_URL = re.compile(r"^data:image/[a-zA-Z0-9.+-]+;base64,", re.IGNORECASE)


def _texto(valor):
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    texto = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(valor))
    texto = texto.replace("\t", " ").replace("\r", " ")
    if len(texto) > MAX_CARACTERES_CELDA:
        texto = texto[:MAX_CARACTERES_CELDA] + "..."
    return texto.encode("latin-1", "replace").decode("latin-1")


def _decodificar_imagen(cadena):
    if not isinstance(cadena, str) or not cadena.strip():
        return None
    contenido = PATRON_DATA_URL.sub("", cadena.strip())
    try:
        crudo = base64.b64decode(contenido, validate=False)
    except (binascii.Error, ValueError):
        return None
    if not crudo:
        return None
    return io.BytesIO(crudo)


class ReportePDF(FPDF):
    def __init__(self, titulo):
        super().__init__(orientation="L", unit="mm", format="A4")
        self.titulo_reporte = _texto(titulo)
        self.set_auto_page_break(auto=True, margin=16)
        self.set_margins(12, 12, 12)
        self.alias_nb_pages()

    def header(self):
        self.set_fill_color(*COLOR_PRIMARIO)
        self.rect(0, 0, self.w, 14, style="F")
        self.set_xy(12, 3.5)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(255, 255, 255)
        self.cell(0, 7, TITULO_CORPORATIVO, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*COLOR_TEXTO)
        self.set_y(18)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(110, 118, 128)
        self.cell(0, 6, f"{TITULO_CORPORATIVO}  |  {self.titulo_reporte}", align="L")
        self.set_x(12)
        self.cell(0, 6, f"Pagina {self.page_no()} de {{nb}}", align="R")
        self.set_text_color(*COLOR_TEXTO)


def _bloque_titulo(pdf, titulo, subtitulo):
    ancho = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.set_font("Helvetica", "B", 17)
    pdf.set_text_color(*COLOR_PRIMARIO)
    pdf.multi_cell(ancho, 8, _texto(titulo) or "Reporte", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if subtitulo:
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*COLOR_TEXTO)
        pdf.multi_cell(ancho, 5.5, "Filtros aplicados: " + _texto(subtitulo), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(110, 118, 128)
    marca = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    pdf.cell(ancho, 5.5, f"Generado el {marca}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)
    pdf.set_text_color(*COLOR_TEXTO)


def _normalizar_kpis(resumen_kpis):
    if isinstance(resumen_kpis, dict):
        return [(_texto(k), _texto(v)) for k, v in resumen_kpis.items()]
    if isinstance(resumen_kpis, (list, tuple)):
        elementos = []
        for item in resumen_kpis:
            if isinstance(item, dict):
                etiqueta = item.get("etiqueta", item.get("label", item.get("nombre", "")))
                valor = item.get("valor", item.get("value", ""))
                elementos.append((_texto(etiqueta), _texto(valor)))
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                elementos.append((_texto(item[0]), _texto(item[1])))
            else:
                elementos.append(("", _texto(item)))
        return elementos
    return []


def _bloque_kpis(pdf, resumen_kpis):
    kpis = _normalizar_kpis(resumen_kpis)
    if not kpis:
        return
    ancho_total = pdf.w - pdf.l_margin - pdf.r_margin
    por_fila = min(4, len(kpis))
    separacion = 4
    ancho = (ancho_total - separacion * (por_fila - 1)) / por_fila
    alto = 17
    for inicio in range(0, len(kpis), por_fila):
        if pdf.get_y() + alto > pdf.page_break_trigger:
            pdf.add_page()
        y = pdf.get_y()
        for posicion, (etiqueta, valor) in enumerate(kpis[inicio:inicio + por_fila]):
            x = pdf.l_margin + posicion * (ancho + separacion)
            pdf.set_fill_color(*COLOR_SECUNDARIO)
            pdf.set_draw_color(*COLOR_BORDE)
            pdf.rect(x, y, ancho, alto, style="DF")
            pdf.set_xy(x + 2, y + 1.5)
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(90, 98, 108)
            pdf.cell(ancho - 4, 4.5, etiqueta[:60], new_x=XPos.LEFT, new_y=YPos.NEXT)
            pdf.set_x(x + 2)
            pdf.set_font("Helvetica", "B", 13)
            pdf.set_text_color(*COLOR_PRIMARIO)
            pdf.cell(ancho - 4, 8, valor[:40])
        pdf.set_y(y + alto + 3)
    pdf.set_text_color(*COLOR_TEXTO)
    pdf.ln(1)


def _bloque_imagenes(pdf, imagenes_base64):
    if not imagenes_base64:
        return
    if isinstance(imagenes_base64, str):
        imagenes_base64 = [imagenes_base64]
    if isinstance(imagenes_base64, dict):
        imagenes_base64 = list(imagenes_base64.values())
    ancho_total = pdf.w - pdf.l_margin - pdf.r_margin
    for cadena in list(imagenes_base64)[:MAX_IMAGENES]:
        flujo = _decodificar_imagen(cadena)
        if flujo is None:
            continue
        try:
            info = pdf.preload_image(flujo)[2]
        except Exception:
            continue
        ancho_px, alto_px = info["w"], info["h"]
        if not ancho_px or not alto_px:
            continue
        ancho = min(ancho_total * 0.75, ancho_px * 0.2646)
        alto = ancho * alto_px / ancho_px
        maximo = pdf.h - pdf.t_margin - 30
        if alto > maximo:
            alto = maximo
            ancho = alto * ancho_px / alto_px
        if pdf.get_y() + alto > pdf.page_break_trigger:
            pdf.add_page()
        x = pdf.l_margin + (ancho_total - ancho) / 2
        flujo.seek(0)
        try:
            pdf.image(flujo, x=x, y=pdf.get_y(), w=ancho, h=alto)
        except Exception:
            continue
        pdf.set_y(pdf.get_y() + alto + 4)


def _anchos_columnas(pdf, encabezados, filas):
    ancho_total = pdf.w - pdf.l_margin - pdf.r_margin
    cantidad = len(encabezados)
    pesos = []
    for indice, encabezado in enumerate(encabezados):
        mayor = len(_texto(encabezado))
        for fila in filas[:200]:
            if indice < len(fila):
                mayor = max(mayor, min(len(_texto(fila[indice])), 60))
        pesos.append(max(6, min(mayor, 60)))
    total = sum(pesos)
    minimo = min(14, ancho_total / cantidad)
    anchos = [max(minimo, ancho_total * p / total) for p in pesos]
    exceso = sum(anchos) - ancho_total
    if exceso > 0:
        factor = ancho_total / sum(anchos)
        anchos = [a * factor for a in anchos]
    return anchos


def _bloque_tabla(pdf, encabezados, filas):
    if not encabezados:
        return
    filas = [list(f) if isinstance(f, (list, tuple)) else list(f.values()) if isinstance(f, dict) else [f] for f in (filas or [])]
    anchos = _anchos_columnas(pdf, encabezados, filas)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*COLOR_PRIMARIO)
    pdf.cell(0, 7, f"Detalle ({len(filas)} registros)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*COLOR_TEXTO)
    pdf.set_draw_color(*COLOR_BORDE)
    pdf.set_font("Helvetica", "", 8)
    estilo_cabecera = FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=COLOR_PRIMARIO)
    with pdf.table(
        col_widths=anchos,
        text_align="LEFT",
        line_height=4.6,
        padding=1.2,
        width=sum(anchos),
        headings_style=estilo_cabecera,
        repeat_headings=1,
        borders_layout="SINGLE_TOP_LINE",
        v_align="TOP",
        cell_fill_color=COLOR_ZEBRA,
        cell_fill_mode="ROWS",
    ) as tabla:
        encabezado = tabla.row()
        for texto in encabezados:
            encabezado.cell(_texto(texto))
        for fila in filas:
            registro = tabla.row()
            for indice in range(len(encabezados)):
                registro.cell(_texto(fila[indice] if indice < len(fila) else ""))
    if not filas:
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(0, 8, "Sin registros para los filtros aplicados", new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def generar_pdf_reporte(titulo, subtitulo, resumen_kpis, encabezados, filas, imagenes_base64=None):
    encabezados = [e for e in (encabezados or [])]
    pdf = ReportePDF(titulo)
    pdf.set_title(_texto(titulo) or "Reporte")
    pdf.set_author(TITULO_CORPORATIVO)
    pdf.add_page()
    _bloque_titulo(pdf, titulo, subtitulo)
    _bloque_kpis(pdf, resumen_kpis)
    _bloque_imagenes(pdf, imagenes_base64)
    _bloque_tabla(pdf, encabezados, filas)
    salida = io.BytesIO(bytes(pdf.output()))
    salida.seek(0)
    return salida
