package org.bc250.controlcenter.componentes

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.bc250.controlcenter.datos.logico
import org.bc250.controlcenter.datos.objeto
import org.bc250.controlcenter.datos.objetos
import org.bc250.controlcenter.datos.texto
import org.bc250.controlcenter.datos.textos
import org.bc250.controlcenter.recursos.Res
import org.bc250.controlcenter.recursos.check_green
import org.bc250.controlcenter.recursos.copy_gray
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas
import org.bc250.controlcenter.tema.leerColor

/** Cuántas piezas van por fila según el ancho disponible. */
@Composable
private fun Cuadricula(cantidad: Int, columnas: Int, anchoMinimo: Int, separacion: Int, pieza: @Composable (Int) -> Unit) {
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val caben = (maxWidth.value / anchoMinimo).toInt().coerceIn(1, columnas)
        Column(verticalArrangement = Arrangement.spacedBy(separacion.dp)) {
            for (inicio in 0 until cantidad step caben) {
                Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(separacion.dp)) {
                    for (columna in 0 until caben) {
                        Box(Modifier.weight(1f)) {
                            if (inicio + columna < cantidad) {
                                pieza(inicio + columna)
                            }
                        }
                    }
                }
            }
        }
    }
}

// -- apariencia --------------------------------------------------------------------------------------

@Composable
fun Temas(bloque: JsonObject, ordenes: Ordenes) {
    val opciones = bloque.objetos("opciones")
    val elegido = bloque.texto("valor")
    Box(Modifier.padding(top = 8.dp, bottom = 10.dp)) {
        Cuadricula(opciones.size, columnas = 4, anchoMinimo = 140, separacion = 10) { indice ->
            val valor = opciones[indice].texto("valor")
            Column(
                modifier = Modifier.fillMaxWidth().pulsable { ordenes.guardar("theme", JsonPrimitive(valor)) },
                verticalArrangement = Arrangement.spacedBy(6.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                MiniaturaTema(valor, bloque.texto("acento"), valor == elegido)
                Texto(opciones[indice].texto("nombre"), tamano = 12, peso = 650)
            }
        }
    }
}

/** Una ventana en pequeño con los colores de ese tema. */
@Composable
private fun MiniaturaTema(tema: String, acento: String, elegida: Boolean) {
    val paleta = ColoresActuales.current
    val paletas = LocalPaletas.current
    val mostrado = if (tema == "system") (if (paleta.esClaro) "light" else "dark") else tema
    fun color(nombre: String): Color {
        return paletas.color(mostrado, acento, nombre)
    }
    val borde = if (elegida) paleta.acento else paleta.bordeSuave
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(104.dp)
            .background(paleta.panelElevado, RoundedCornerShape(7.dp))
            .border(if (elegida) 2.dp else 1.dp, borde, RoundedCornerShape(7.dp))
            .padding(8.dp),
    ) {
        Row(Modifier.fillMaxWidth().fillMaxHeight().background(color("window"), RoundedCornerShape(4.dp)).padding(6.dp)) {
            Column(Modifier.width(28.dp), Arrangement.spacedBy(5.dp)) {
                Box(Modifier.size(26.dp, 8.dp).background(color("panel_alt"), RoundedCornerShape(2.dp)))
                Box(Modifier.size(26.dp, 8.dp).background(color("blue"), RoundedCornerShape(2.dp)))
                Box(Modifier.size(26.dp, 8.dp).background(color("panel_alt"), RoundedCornerShape(2.dp)))
            }
            Spacer(Modifier.width(6.dp))
            Column(Modifier.weight(1f), Arrangement.spacedBy(6.dp)) {
                Box(Modifier.fillMaxWidth(0.7f).height(6.dp).background(color("muted"), RoundedCornerShape(2.dp)))
                Row(Modifier.fillMaxWidth().weight(1f), Arrangement.spacedBy(5.dp)) {
                    repeat(2) {
                        val marco = Modifier.weight(1f).fillMaxHeight().marco(color("panel"), color("border"), 3.dp)
                        Column(marco.padding(6.dp)) {
                            Box(Modifier.fillMaxWidth().height(4.dp).background(color("text"), RoundedCornerShape(1.dp)))
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun Terminales(bloque: JsonObject, ordenes: Ordenes) {
    val elegida = bloque.texto("valor")
    Column(Modifier.padding(top = 10.dp, bottom = 12.dp), Arrangement.spacedBy(12.dp)) {
        for (grupo in bloque.objetos("grupos")) {
            Texto(grupo.texto("nombre"), 13, Modifier.padding(top = 6.dp), peso = 600, color = colorNota())
            val tarjetas = grupo.objetos("tarjetas")
            Cuadricula(tarjetas.size, columnas = 3, anchoMinimo = 200, separacion = 12) { indice ->
                TarjetaTerminal(tarjetas[indice], elegida) { valor -> ordenes.guardar("console_theme", JsonPrimitive(valor)) }
            }
        }
    }
}

/** Una terminal de muestra con los colores de su tema. */
@Composable
private fun TarjetaTerminal(tarjeta: JsonObject, elegida: String, alElegir: (String) -> Unit) {
    val valor = tarjeta.texto("valor")
    val colores = tarjeta.textos("colores").map(::leerColor)
    fun ansi(numero: Int): Color {
        return colores.getOrElse(numero) { leerColor(tarjeta.texto("texto")) }
    }
    val borde = if (valor == elegida) ColoresActuales.current.acento else leerColor(tarjeta.texto("borde"))
    val textoNormal = leerColor(tarjeta.texto("texto"))
    Column(Modifier.pulsable { alElegir(valor) }, Arrangement.spacedBy(6.dp)) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .background(leerColor(tarjeta.texto("fondo")), RoundedCornerShape(6.dp))
                .border(if (valor == elegida) 2.dp else 1.dp, borde, RoundedCornerShape(6.dp))
                .padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(3.dp),
        ) {
            TextoMono("bash", tamano = 10, color = leerColor(tarjeta.texto("apagado")))
            Spacer(Modifier.height(6.dp))
            TextoMono("$ pacman -S mesa", tamano = 12, color = textoNormal)
            TextoMono("info resolving deps", tamano = 12, color = ansi(4))
            TextoMono("ok mesa installed", tamano = 12, color = ansi(2))
            TextoMono("! reboot required", tamano = 12, color = ansi(3))
            TextoMono("x 1 conflict", tamano = 12, color = ansi(1))
        }
        Texto(tarjeta.texto("nombre"), 12, Modifier.fillMaxWidth(), peso = 650, alineado = TextAlign.Center)
    }
}

// -- fichas y búsquedas -----------------------------------------------------------------------------------

@Composable
fun FichasConBusqueda(bloque: JsonObject, ordenes: Ordenes) {
    var busqueda by remember { mutableStateOf("") }
    val fichas = bloque.objetos("fichas").filter { ficha -> contiene(ficha, busqueda) }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        CampoTexto(busqueda, { nueva -> busqueda = nueva }, Modifier.fillMaxWidth(), ayuda = bloque.texto("buscar"))
        for (ficha in fichas) {
            Ficha(ficha, ordenes)
        }
        if (fichas.isEmpty()) {
            Texto(bloque.texto("vacio"), tamano = 13, color = colorNota())
        }
    }
}

private fun contiene(ficha: JsonObject, busqueda: String): Boolean {
    val buscado = busqueda.trim().lowercase()
    val contenido = (ficha.texto("titulo") + " " + ficha.texto("detalle")).lowercase()
    return contenido.contains(buscado)
}

/** Un renglón numerado con su botón: un repositorio o una guía. */
@Composable
private fun Ficha(ficha: JsonObject, ordenes: Ordenes) {
    val paleta = ColoresActuales.current
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .marco(paleta.panelElevado, paleta.bordeSuave, 6.dp)
            .padding(horizontal = 18.dp, vertical = 14.dp),
        horizontalArrangement = Arrangement.spacedBy(16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Texto(ficha.texto("numero"), 11, Modifier.width(25.dp), peso = 700, color = paleta.apagado)
        Column(Modifier.weight(1f), Arrangement.spacedBy(5.dp)) {
            Texto(ficha.texto("titulo"), tamano = 14, peso = 650)
            Texto(ficha.texto("detalle"), tamano = 12, color = paleta.apagado)
        }
        if (ficha.texto("marca").isNotEmpty()) {
            Texto(ficha.texto("marca"), tamano = 11, color = paleta.naranja)
        }
        BotonOrden(ficha.objeto("boton"), ordenes)
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ErroresFrecuentes(bloque: JsonObject, ordenes: Ordenes) {
    var busqueda by remember { mutableStateOf(bloque.texto("consulta")) }
    var modulo by remember { mutableStateOf(bloque.texto("modulo")) }
    LaunchedEffect(busqueda, modulo) {
        if (busqueda != bloque.texto("consulta") || modulo != bloque.texto("modulo")) {
            delay(250)
            ordenes.ir("support_errors", mapOf("query" to busqueda, "module" to modulo))
        }
    }
    Column(Modifier.padding(top = 10.dp), Arrangement.spacedBy(10.dp)) {
        Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(12.dp)) {
            CampoTexto(busqueda, { nueva -> busqueda = nueva }, Modifier.weight(3f), ayuda = bloque.texto("buscar"))
            val modulos = bloque.objetos("modulos").map { opcion -> Eleccion(opcion.texto("valor"), opcion.texto("nombre")) }
            Desplegable(modulos, modulo, { valor -> modulo = valor }, Modifier.weight(2f).widthIn(max = 240.dp))
        }
        for (ficha in bloque.objetos("fichas")) {
            Ficha(ficha, ordenes)
        }
        if (bloque.objetos("fichas").isEmpty()) {
            Texto(bloque.texto("vacio"), tamano = 13, color = colorNota())
            Texto(bloque.texto("ayuda"), tamano = 12, color = ColoresActuales.current.apagado)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                for (sugerencia in bloque.objetos("sugerencias")) {
                    Boton(sugerencia.texto("texto"), {
                        busqueda = sugerencia.texto("buscar")
                        modulo = sugerencia.texto("modulo")
                    })
                }
                Boton(bloque.texto("reportar"), { ordenes.ir("support_report", mapOf("query" to busqueda)) })
            }
        }
    }
}

@Composable
fun SelectorDistribucion(bloque: JsonObject, ordenes: Ordenes) {
    Row(Modifier.padding(vertical = 8.dp), Arrangement.spacedBy(12.dp), Alignment.CenterVertically) {
        Texto(bloque.texto("nombre"), tamano = 13, peso = 600)
        Desplegable(
            opciones = leerOpciones(bloque),
            elegida = bloque.texto("valor"),
            alElegir = { valor -> ordenes.ir("", mapOf("distro" to valor)) },
            modifier = Modifier.widthIn(max = 340.dp),
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun Hechos(bloque: JsonObject) {
    val paleta = ColoresActuales.current
    FlowRow(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 6.dp)
            .marco(paleta.panelElevado, paleta.bordeSuave, 5.dp)
            .padding(horizontal = 14.dp, vertical = 10.dp),
        horizontalArrangement = Arrangement.spacedBy(28.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        for (hecho in bloque.objetos("hechos")) {
            Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Texto(hecho.texto("nombre"), tamano = 11, peso = 650, color = paleta.apagado)
                Texto(hecho.texto("valor"), tamano = 13, peso = 600)
            }
        }
    }
}

// -- soporte ------------------------------------------------------------------------------------------------

@Composable
fun TarjetasSoporte(bloque: JsonObject, ordenes: Ordenes) {
    val tarjetas = bloque.objetos("tarjetas")
    Box(Modifier.padding(top = 14.dp, bottom = 22.dp)) {
        Cuadricula(tarjetas.size, columnas = 3, anchoMinimo = 220, separacion = 12) { indice ->
            TarjetaSoporte(tarjetas[indice], ordenes)
        }
    }
}

@Composable
private fun TarjetaSoporte(tarjeta: JsonObject, ordenes: Ordenes) {
    val paleta = ColoresActuales.current
    val borde = if (tarjeta.logico("principal")) paleta.acento else paleta.bordeSuave
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .height(118.dp)
            .marco(paleta.panelElevado, borde, 6.dp)
            .pulsable { ordenes.cumplir(tarjeta.objeto("orden")) }
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Texto(tarjeta.texto("titulo"), tamano = 14, peso = 700)
        Texto(tarjeta.texto("detalle"), 12, Modifier.weight(1f), color = colorNota())
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            Texto(tarjeta.texto("ir"), tamano = 12, peso = 650, color = paleta.acento)
            FlechaPlegar(abierto = false, tamano = 10.dp)
        }
    }
}

@Composable
fun ReportesEnviados(bloque: JsonObject, ordenes: Ordenes) {
    val paleta = ColoresActuales.current
    var soloSemana by remember { mutableStateOf(false) }
    val filas = bloque.objetos("filas").filter { fila -> !soloSemana || fila.logico("semana") }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp), Alignment.CenterVertically) {
            Texto(bloque.texto("titulo"), 14, Modifier.weight(1f), peso = 600)
            Pastilla(bloque.texto("todos"), !soloSemana) { soloSemana = false }
            Pastilla(bloque.texto("semana"), soloSemana) { soloSemana = true }
        }
        Column(Modifier.fillMaxWidth().marco(paleta.panelElevado, paleta.bordeSuave, 5.dp).padding(1.dp)) {
            val columnas = bloque.textos("columnas")
            Row(
                modifier = Modifier.fillMaxWidth().height(34.dp).background(paleta.ventana).padding(horizontal = 16.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Texto(columnas.getOrElse(0) { "" }, 11, Modifier.width(132.dp), peso = 650, color = paleta.apagado)
                Texto(columnas.getOrElse(1) { "" }, 11, Modifier.weight(1f), peso = 650, color = paleta.apagado)
                Texto(columnas.getOrElse(2) { "" }, 11, Modifier.width(80.dp), peso = 650, color = paleta.apagado)
                Texto(columnas.getOrElse(3) { "" }, 11, Modifier.width(130.dp), peso = 650, color = paleta.apagado)
                Spacer(Modifier.width(150.dp))
            }
            if (filas.isEmpty()) {
                Texto(bloque.texto("vacio"), 12, Modifier.padding(horizontal = 16.dp, vertical = 14.dp), color = colorNota())
            }
            for (fila in filas) {
                LineaDivisoria()
                FilaEnviado(fila, bloque, ordenes)
            }
        }
    }
}

@Composable
private fun FilaEnviado(fila: JsonObject, bloque: JsonObject, ordenes: Ordenes) {
    val paleta = ColoresActuales.current
    val identificador = fila.texto("id")
    Row(
        modifier = Modifier.fillMaxWidth().height(52.dp).padding(horizontal = 16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.width(132.dp)) {
            TextoMono(identificador, tamano = 12, color = paleta.acento)
        }
        Column(Modifier.weight(1f), Arrangement.spacedBy(1.dp)) {
            Texto(fila.texto("titulo"), tamano = 13, peso = 720, lineas = 1)
            Texto(fila.texto("detalle"), tamano = 12, color = colorNota(), lineas = 1)
        }
        Texto(fila.texto("version"), 13, Modifier.width(80.dp))
        Texto(fila.texto("cuando"), 13, Modifier.width(130.dp))
        Row(Modifier.width(150.dp), Arrangement.spacedBy(6.dp, Alignment.End)) {
            Boton(bloque.texto("ver"), { ordenes.ir("support_detail", mapOf("id" to identificador)) }, alto = 28.dp, tamano = 11)
            Boton(bloque.texto("copiar"), { ordenes.copiar(identificador) }, alto = 28.dp, tamano = 11, icono = Res.drawable.copy_gray)
        }
    }
}

@Composable
private fun Pastilla(texto: String, elegida: Boolean, alPulsar: () -> Unit) {
    val paleta = ColoresActuales.current
    val borde = if (elegida) paleta.bordeFuerte else paleta.bordeSuave
    val color = if (elegida) paleta.texto else paleta.apagado
    Box(
        modifier = Modifier.marco(paleta.control, borde, 6.dp).pulsable(alPulsar = alPulsar).padding(horizontal = 12.dp, vertical = 5.dp),
    ) {
        Texto(texto, tamano = 12, color = color)
    }
}

@Composable
fun FichaReporte(bloque: JsonObject, ordenes: Ordenes) {
    val paleta = ColoresActuales.current
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 14.dp)
            .marco(paleta.panelElevado, paleta.bordeSuave, 5.dp)
            .padding(18.dp),
        verticalArrangement = Arrangement.spacedBy(9.dp),
    ) {
        for (dato in bloque.objetos("datos")) {
            Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                Texto(dato.texto("nombre"), 12, Modifier.width(110.dp), color = colorNota())
                Texto(dato.texto("valor"), 13, Modifier.weight(1f), peso = 600)
            }
        }
        LineaDivisoria(Modifier.padding(vertical = 6.dp))
        Texto(bloque.texto("encabezado"), tamano = 11, peso = 650, color = paleta.apagado)
        val adjuntos = bloque.textos("adjuntos")
        for (adjunto in adjuntos) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                Icono(Res.drawable.check_green, tamano = 13.dp)
                Texto(adjunto, tamano = 13)
            }
        }
        if (adjuntos.isEmpty()) {
            Texto(bloque.texto("vacio"), tamano = 12, color = colorNota())
        }
        BotonOrden(bloque.objeto("boton"), ordenes)
    }
}
