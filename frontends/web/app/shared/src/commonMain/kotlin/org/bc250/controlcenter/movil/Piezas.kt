package org.bc250.controlcenter.movil

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicText
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.bc250.controlcenter.componentes.Boton
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.Icono
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.estiloTexto
import org.bc250.controlcenter.componentes.marco
import org.bc250.controlcenter.componentes.pulsable
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.recursos.Res
import org.bc250.controlcenter.recursos.check_white
import org.bc250.controlcenter.recursos.chevron_right_gray
import org.bc250.controlcenter.recursos.edit_gray
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.LetrasActuales
import org.bc250.controlcenter.tema.grosor

val AnchoCompleto = Modifier.fillMaxWidth()

/** Los títulos y las cifras: una letra más estrecha y más firme que la del texto. */
@Composable
fun TextoTitulo(
    texto: String,
    tamano: Int,
    modifier: Modifier = Modifier,
    color: Color = ColoresActuales.current.texto,
    lineas: Int = Int.MAX_VALUE,
    peso: Int = 700,
) {
    val estilo = estiloTexto(tamano, peso, color).copy(fontFamily = LetrasActuales.current.cifras, lineHeight = (tamano * 1.22f).sp)
    BasicText(texto, modifier, style = estilo, maxLines = lineas, overflow = TextOverflow.Ellipsis)
}

/** Un nombre de grupo dentro de una tarjeta. */
@Composable
fun SubtituloMovil(texto: String) {
    Texto(texto, 13, Modifier.padding(start = 16.dp, top = 16.dp, bottom = 4.dp), peso = 700, color = ColoresActuales.current.apagado)
}

// -- grupos ------------------------------------------------------------------------------------------

/** El título pequeño de una sección y lo que lleva debajo. */
@Composable
fun SeccionMovil(titulo: String, color: Color = ColoresActuales.current.texto, contenido: @Composable ColumnScope.() -> Unit) {
    Column(Modifier.fillMaxWidth()) {
        TextoTitulo(titulo, 18, Modifier.padding(start = 2.dp, top = 10.dp, bottom = 10.dp), color)
        Column(Modifier.fillMaxWidth(), Arrangement.spacedBy(12.dp), content = contenido)
    }
}

/** Un grupo con un solo borde; sus filas se separan con una línea fina. */
@Composable
fun GrupoMovil(modifier: Modifier = Modifier, contenido: @Composable ColumnScope.() -> Unit) {
    val paleta = ColoresActuales.current
    val forma = RoundedCornerShape(12.dp)
    Column(
        modifier = modifier
            .fillMaxWidth()
            .clip(forma)
            .background(paleta.panel)
            .border(1.dp, paleta.bordeSuave, forma),
        content = contenido,
    )
}

/** La línea sobre una fila. En la primera queda debajo del borde del grupo y no se ve. */
@Composable
fun Modifier.lineaArriba(color: Color = ColoresActuales.current.bordeSuave): Modifier {
    return drawBehind {
        val grueso = 1.dp.toPx()
        drawLine(color, Offset(0f, grueso / 2), Offset(size.width, grueso / 2), grueso)
    }
}

/** Una fila cualquiera de un grupo. */
@Composable
fun FilaLibre(
    modifier: Modifier = Modifier,
    altoMinimo: Dp = 52.dp,
    alPulsar: (() -> Unit)? = null,
    activa: Boolean = true,
    contenido: @Composable RowScope.() -> Unit,
) {
    val conToque = if (alPulsar == null) Modifier else Modifier.pulsable(activa, alPulsar = alPulsar)
    Row(
        modifier = modifier
            .fillMaxWidth()
            .lineaArriba()
            .then(conToque)
            .heightIn(min = altoMinimo)
            .padding(horizontal = 16.dp, vertical = 9.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalAlignment = Alignment.CenterVertically,
        content = contenido,
    )
}

// -- filas ---------------------------------------------------------------------------------------------

/** El nombre de una fila y, debajo, su explicación. */
@Composable
fun RowScope.TextosFila(titulo: String, detalle: String = "", color: Color? = null, colorDetalle: Color? = null) {
    val paleta = ColoresActuales.current
    Column(Modifier.weight(1f)) {
        Texto(titulo, tamano = 15, peso = 500, color = color ?: paleta.texto)
        if (detalle.isNotEmpty()) {
            Texto(detalle, tamano = 13, color = colorDetalle ?: paleta.sutil)
        }
    }
}

/** Un dato: su nombre a la izquierda y su valor a la derecha. */
@Composable
fun FilaDato(nombre: String, valor: String, unidad: String = "", color: Color? = null, detalle: String = "") {
    val paleta = ColoresActuales.current
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .lineaArriba()
            .heightIn(min = 46.dp)
            .padding(horizontal = 16.dp, vertical = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Texto(nombre.ifEmpty { valor }, tamano = 14, color = paleta.apagado)
            if (detalle.isNotEmpty()) {
                Texto(detalle, tamano = 12, color = paleta.sutil)
            }
        }
        if (nombre.isEmpty()) {
            return@Row
        }
        ValorConUnidad(valor, unidad, color = color, modifier = Modifier.widthIn(max = 230.dp))
    }
}

/** Una fila que abre algo: su valor actual y la flecha. */
@Composable
fun FilaAbrir(
    titulo: String,
    detalle: String = "",
    valor: String = "",
    unidad: String = "",
    colorTitulo: Color? = null,
    colorValor: Color? = null,
    activa: Boolean = true,
    alPulsar: () -> Unit,
) {
    FilaLibre(Modifier.alpha(if (activa) 1f else 0.6f), altoMinimo = 62.dp, alPulsar = alPulsar, activa = activa) {
        TextosFila(titulo, detalle, colorTitulo)
        if (valor.isNotEmpty()) {
            ValorConUnidad(valor, unidad, tamano = 15, color = colorValor, modifier = Modifier.widthIn(max = 190.dp))
        }
        Icono(Res.drawable.chevron_right_gray, 14.dp)
    }
}

@Composable
fun FilaInterruptor(
    titulo: String,
    encendido: Boolean,
    detalle: String = "",
    activa: Boolean = true,
    deRiesgo: Boolean = false,
    alCambiar: (Boolean) -> Unit,
) {
    FilaLibre {
        TextosFila(titulo, detalle)
        InterruptorMovil(encendido, activo = activa, deRiesgo = deRiesgo, alCambiar = alCambiar)
    }
}

/** Una opción entre varias, con su explicación. */
@Composable
fun FilaRadio(
    titulo: String,
    elegida: Boolean,
    detalle: String = "",
    etiqueta: String = "",
    activa: Boolean = true,
    alElegir: () -> Unit,
) {
    val alto = if (detalle.isEmpty()) 52.dp else 66.dp
    FilaLibre(Modifier.alpha(if (activa) 1f else 0.5f), altoMinimo = alto, alPulsar = alElegir, activa = activa) {
        RadioMovil(elegida)
        TextosFila(titulo, detalle)
        if (etiqueta.isNotEmpty()) {
            Pildora(etiqueta, viva = false)
        }
    }
}

/** Un número que sube y baja con dos botones grandes. */
@Composable
fun FilaPaso(
    nombre: String,
    valor: Int,
    unidad: String,
    minimo: Int,
    maximo: Int,
    paso: Int = 1,
    detalle: String = "",
    color: Color? = null,
    fuerte: Boolean = false,
    activa: Boolean = true,
    alCambiar: (Int) -> Unit,
) {
    val paleta = ColoresActuales.current
    FilaLibre(altoMinimo = 60.dp) {
        Column(Modifier.weight(1f)) {
            Texto(nombre, tamano = 15, peso = if (fuerte) 700 else 500)
            if (detalle.isNotEmpty()) {
                Texto(detalle, tamano = 12, color = paleta.sutil)
            }
        }
        Row(
            modifier = Modifier.height(44.dp).marco(paleta.panelAlterno, Color.Transparent, 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            BotonPaso("−", activa && valor > minimo) { alCambiar((valor - paso).coerceAtLeast(minimo)) }
            ValorConUnidad(valor.toString(), unidad, color = color, centrado = true, modifier = Modifier.widthIn(min = 58.dp))
            BotonPaso("+", activa && valor < maximo) { alCambiar((valor + paso).coerceAtMost(maximo)) }
        }
    }
}

@Composable
private fun BotonPaso(signo: String, activo: Boolean, alPulsar: () -> Unit) {
    val paleta = ColoresActuales.current
    Box(Modifier.size(44.dp).pulsable(activo, alPulsar = alPulsar), Alignment.Center) {
        Texto(signo, tamano = 20, color = if (activo) paleta.texto else paleta.textoInactivo)
    }
}

// -- valores ---------------------------------------------------------------------------------------------

/** Un valor en negrita con su unidad más pequeña. */
@Composable
fun ValorConUnidad(
    valor: String,
    unidad: String = "",
    modifier: Modifier = Modifier,
    tamano: Int = 14,
    color: Color? = null,
    centrado: Boolean = false,
    alineado: TextAlign = if (centrado) TextAlign.Center else TextAlign.End,
) {
    val paleta = ColoresActuales.current
    val normal = LetrasActuales.current.normal
    val texto = buildAnnotatedString {
        append(valor)
        if (unidad.isNotEmpty()) {
            withStyle(SpanStyle(fontSize = (if (tamano > 20) 14 else 12).sp, fontWeight = grosor(500), fontFamily = normal, color = paleta.apagado)) {
                append(" $unidad")
            }
        }
    }
    BasicText(text = texto, modifier = modifier, style = estiloValor(valor, tamano, color, alineado))
}

/** Las cifras van en su letra y más grandes; una palabra es un texto más y lo que no se pudo leer, se apaga. */
@Composable
private fun estiloValor(valor: String, tamano: Int, color: Color?, alineado: TextAlign): TextStyle {
    val paleta = ColoresActuales.current
    if (valor.any { letra -> letra.isDigit() }) {
        val estilo = estiloTexto(tamano + 2, if (tamano < 20) 600 else 700, color ?: paleta.texto, alineado)
        return estilo.copy(fontFamily = LetrasActuales.current.cifras, lineHeight = ((tamano + 2) * 1.22f).sp)
    }
    val sinDato = valor == "—" || valor == "--" || valor == t("Not detected")
    return estiloTexto(tamano, if (sinDato) 400 else 500, color ?: if (sinDato) paleta.sutil else paleta.texto, alineado)
}

/** Una lectura de la franja de arriba. */
class LecturaFranja(val nombre: String, val valor: String, val unidad: String = "", val color: Color? = null, val larga: Boolean = false)

/** Tres lecturas grandes, una al lado de otra. */
@Composable
fun FranjaLecturas(vararg lecturas: LecturaFranja) {
    val paleta = ColoresActuales.current
    GrupoMovil {
        Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min)) {
            for ((indice, lectura) in lecturas.withIndex()) {
                if (indice > 0) {
                    Box(Modifier.width(1.dp).fillMaxHeight().background(paleta.bordeSuave))
                }
                Column(Modifier.weight(1f).heightIn(min = 82.dp).padding(horizontal = 16.dp, vertical = 14.dp)) {
                    Texto(lectura.nombre, tamano = 13, color = paleta.apagado, lineas = 1)
                    val tamano = if (lectura.larga) 17 else 26
                    ValorConUnidad(lectura.valor, lectura.unidad, tamano = tamano, color = lectura.color, alineado = TextAlign.Start)
                }
            }
        }
    }
}

/** Una etiqueta corta de estado. */
@Composable
fun Pildora(texto: String, viva: Boolean = true) {
    val paleta = ColoresActuales.current
    val fondo = if (viva) paleta.acentoSuave else paleta.bordeSuave
    val color = if (viva) paleta.acento else paleta.apagado
    Box(Modifier.background(fondo, RoundedCornerShape(5.dp)).padding(horizontal = 9.dp, vertical = 4.dp)) {
        Texto(texto, tamano = 12, peso = 700, color = color, lineas = 1)
    }
}

/** Una explicación suelta debajo de un grupo. */
@Composable
fun NotaMovil(texto: String, color: Color = ColoresActuales.current.sutil, tamano: Int = 13) {
    Texto(texto, tamano = tamano, color = color, modifier = Modifier.padding(horizontal = 2.dp))
}

// -- controles ---------------------------------------------------------------------------------------------

@Composable
fun RadioMovil(elegida: Boolean) {
    val paleta = ColoresActuales.current
    val color = if (elegida) paleta.acento else paleta.bordeFuerte
    Box(Modifier.size(20.dp).border(if (elegida) 6.dp else 2.dp, color, CircleShape))
}

@Composable
fun InterruptorMovil(
    encendido: Boolean,
    modifier: Modifier = Modifier,
    activo: Boolean = true,
    deRiesgo: Boolean = false,
    alCambiar: (Boolean) -> Unit,
) {
    val paleta = ColoresActuales.current
    val vivo = if (deRiesgo) paleta.peligroSolido else paleta.acento
    val fondo by animateColorAsState(if (encendido) vivo else paleta.bordeFuerte)
    val lugar by animateDpAsState(if (encendido) 23.dp else 3.dp)
    Box(
        modifier = modifier
            .alpha(if (activo) 1f else 0.4f)
            .size(48.dp, 28.dp)
            .background(fondo, RoundedCornerShape(14.dp))
            .pulsable(activo) { alCambiar(!encendido) },
        contentAlignment = Alignment.CenterStart,
    ) {
        Box(Modifier.offset(x = lugar).size(22.dp).background(Color.White, CircleShape))
    }
}

/** Varias opciones cortas, una al lado de otra. */
@Composable
fun SegmentadoMovil(opciones: List<Pair<String, String>>, elegida: String, activo: Boolean = true, alElegir: (String) -> Unit) {
    val paleta = ColoresActuales.current
    val forma = RoundedCornerShape(9.dp)
    Row(Modifier.fillMaxWidth().clip(forma).background(paleta.panelAlterno).padding(3.dp)) {
        for ((valor, nombre) in opciones) {
            val esta = valor == elegida
            Box(
                modifier = Modifier
                    .weight(1f)
                    .height(42.dp)
                    .background(if (esta) paleta.texto else Color.Transparent, RoundedCornerShape(7.dp))
                    .pulsable(activo) { alElegir(valor) },
                contentAlignment = Alignment.Center,
            ) {
                val color = if (esta) paleta.ventana else paleta.apagado
                Texto(nombre, tamano = 14, peso = 700, color = color, lineas = 1)
            }
        }
    }
}

@Composable
fun BotonMovil(
    texto: String,
    modifier: Modifier = Modifier,
    clase: ClaseBoton = ClaseBoton.NORMAL,
    activo: Boolean = true,
    alPulsar: () -> Unit,
) {
    Boton(texto, alPulsar, modifier, clase, activo, alto = 50.dp, tamano = 15, peso = 700, radio = 10.dp)
}

/** Dos o tres acciones en una sola tira dividida. */
@Composable
fun TiraAcciones(vararg acciones: AccionTira) {
    val paleta = ColoresActuales.current
    Row(Modifier.fillMaxWidth().lineaArriba().height(50.dp)) {
        for ((indice, accion) in acciones.withIndex()) {
            if (indice > 0) {
                Box(Modifier.width(1.dp).fillMaxHeight().background(paleta.bordeSuave))
            }
            Box(Modifier.weight(1f).fillMaxHeight().pulsable(accion.activa, alPulsar = accion.alPulsar), Alignment.Center) {
                val color = if (accion.activa) paleta.texto else paleta.textoInactivo
                Texto(accion.nombre, tamano = 14, peso = 500, color = color, lineas = 1)
            }
        }
    }
}

class AccionTira(val nombre: String, val activa: Boolean = true, val alPulsar: () -> Unit)

/** Un enlace pequeño en color de acento. */
@Composable
fun EnlaceMovil(texto: String, activo: Boolean = true, alPulsar: () -> Unit) {
    val paleta = ColoresActuales.current
    Box(Modifier.height(44.dp).pulsable(activo, alPulsar = alPulsar).padding(horizontal = 6.dp), Alignment.Center) {
        Texto(texto, tamano = 14, peso = 700, color = if (activo) paleta.acento else paleta.textoInactivo)
    }
}

/** Opciones cortas que se deslizan a lo ancho. */
@Composable
fun FilaOpciones(opciones: List<Pair<String, String>>, elegidas: Set<String>, alElegir: (String) -> Unit) {
    val paleta = ColoresActuales.current
    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), Arrangement.spacedBy(6.dp)) {
        for ((valor, nombre) in opciones) {
            val esta = valor in elegidas
            val fondo = if (esta) paleta.texto else paleta.panelAlterno
            Box(
                modifier = Modifier.height(40.dp).marco(fondo, fondo, 8.dp).pulsable { alElegir(valor) }.padding(horizontal = 14.dp),
                contentAlignment = Alignment.Center,
            ) {
                Texto(nombre, tamano = 14, peso = if (esta) 700 else 500, color = if (esta) paleta.ventana else paleta.apagado, lineas = 1)
            }
        }
    }
}

/** La casilla de una lista en la que se marcan varias cosas. */
@Composable
fun CasillaMovil(marcada: Boolean, activa: Boolean = true) {
    val paleta = ColoresActuales.current
    val fondo = if (marcada) paleta.acento else paleta.panelAlterno
    val borde = if (marcada) paleta.acento else paleta.bordeFuerte
    Box(Modifier.alpha(if (activa) 1f else 0.5f).size(22.dp).marco(fondo, borde, 4.dp), Alignment.Center) {
        if (marcada) {
            Icono(Res.drawable.check_white, 14.dp, paleta.sobreAcento)
        }
    }
}

/** La flecha al final de una fila que además se puede marcar: abre sus detalles. */
@Composable
fun FlechaDetalle(alPulsar: () -> Unit) {
    Box(Modifier.size(32.dp, 44.dp).pulsable(alPulsar = alPulsar), Alignment.CenterEnd) {
        Icono(Res.drawable.chevron_right_gray, 14.dp)
    }
}

/** El título grande de una tarjeta de lecturas, con su raya de acento. */
@Composable
fun TituloLectura(titulo: String, valor: String, unidad: String) {
    val paleta = ColoresActuales.current
    Row(Modifier.fillMaxWidth().padding(start = 16.dp, top = 14.dp, end = 16.dp, bottom = 10.dp), Arrangement.spacedBy(6.dp)) {
        TextoTitulo(titulo, 20, Modifier.weight(1f).alignByBaseline())
        TextoTitulo(valor, 46, Modifier.alignByBaseline())
        Texto(unidad, 14, Modifier.alignByBaseline(), peso = 500, color = paleta.apagado)
    }
    Box(Modifier.fillMaxWidth().height(2.dp).background(paleta.acento))
}

// -- perfiles ------------------------------------------------------------------------------------------------

/** Un perfil: se elige tocándolo y se cambia con el lápiz. */
@Composable
fun TarjetaPerfilMovil(
    nombre: String,
    valor: String,
    detalle: String,
    elegido: Boolean,
    activo: Boolean = true,
    alEditar: (() -> Unit)? = null,
    adorno: @Composable () -> Unit = {},
    alElegir: () -> Unit,
) {
    val paleta = ColoresActuales.current
    val forma = RoundedCornerShape(12.dp)
    val borde = if (elegido) paleta.acento else paleta.bordeSuave
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .alpha(if (activo) 1f else 0.5f)
            .heightIn(min = 76.dp)
            .clip(forma)
            .background(if (elegido) paleta.panelElevado else paleta.panel)
            .border(if (elegido) 2.dp else 1.dp, borde, forma)
            .pulsable(activo, alPulsar = alElegir)
            .padding(start = 16.dp),
        horizontalArrangement = Arrangement.spacedBy(14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        RadioMovil(elegido)
        Column(Modifier.weight(1f).padding(vertical = 11.dp)) {
            Texto(nombre, tamano = 14, peso = 500, color = if (elegido) paleta.texto else paleta.apagado)
            Row {
                if (valor.isNotEmpty()) {
                    TextoTitulo(valor, 21, Modifier.alignByBaseline().padding(end = 10.dp), lineas = 1)
                }
                if (detalle.isNotEmpty()) {
                    Texto(detalle, tamano = 13, color = paleta.sutil, modifier = Modifier.alignByBaseline())
                }
            }
        }
        adorno()
        if (alEditar == null) {
            Box(Modifier.width(0.dp))
        } else {
            Box(Modifier.size(44.dp).pulsable(activo, alPulsar = alEditar), Alignment.Center) {
                Icono(Res.drawable.edit_gray, 16.dp, paleta.apagado)
            }
        }
    }
}

// -- ventanas inferiores -----------------------------------------------------------------------------------------

@Composable
fun TituloHoja(texto: String, enlace: String = "", alPulsar: () -> Unit = {}) {
    Row(Modifier.fillMaxWidth(), Arrangement.SpaceBetween, Alignment.CenterVertically) {
        TextoTitulo(texto, 22, Modifier.weight(1f))
        if (enlace.isNotEmpty()) {
            EnlaceMovil(enlace, alPulsar = alPulsar)
        }
    }
}

@Composable
fun TextoHoja(texto: String) {
    Texto(texto, tamano = 14, color = ColoresActuales.current.apagado)
}

/** El botón que cierra una ventana inferior. */
@Composable
fun CerrarHoja(texto: String = t("Close"), clase: ClaseBoton = ClaseBoton.NORMAL) {
    val movil = movil()
    BotonMovil(texto, Modifier.fillMaxWidth(), clase) { movil.cerrarHoja() }
}

/** Dos botones al pie de una ventana inferior o de una página. */
@Composable
fun ParejaBotones(contenido: @Composable RowScope.() -> Unit) {
    Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp), content = contenido)
}

/** Elegir una opción de una lista en una ventana inferior. */
fun EstadoMovil.abrirLista(titulo: String, opciones: List<Pair<String, String>>, elegida: String, alElegir: (String) -> Unit) {
    abrirHoja {
        TituloHoja(titulo)
        GrupoMovil {
            for ((valor, nombre) in opciones) {
                FilaRadio(nombre, valor == elegida) {
                    cerrarHoja()
                    alElegir(valor)
                }
            }
        }
    }
}
