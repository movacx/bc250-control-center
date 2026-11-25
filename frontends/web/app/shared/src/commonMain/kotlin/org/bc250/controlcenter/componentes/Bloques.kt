package org.bc250.controlcenter.componentes

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.bc250.controlcenter.datos.entero
import org.bc250.controlcenter.datos.logico
import org.bc250.controlcenter.datos.objeto
import org.bc250.controlcenter.datos.objetos
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto
import org.bc250.controlcenter.datos.textos
import org.bc250.controlcenter.recursos.Res
import org.bc250.controlcenter.recursos.chevron_right_gray
import org.bc250.controlcenter.recursos.copy_gray
import org.bc250.controlcenter.recursos.foto_i2c_header1_connected
import org.bc250.controlcenter.recursos.foto_i2c_header1_pins
import org.bc250.controlcenter.recursos.foto_tpms1_connected
import org.bc250.controlcenter.recursos.foto_tpms1_pins
import org.bc250.controlcenter.recursos.warning_orange
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas
import org.bc250.controlcenter.tema.mezclar
import org.jetbrains.compose.resources.DrawableResource
import org.jetbrains.compose.resources.painterResource

/** El gris de las explicaciones, un poco más claro que el apagado. */
@Composable
fun colorNota(): Color {
    val paleta = ColoresActuales.current
    return mezclar(paleta.apagado, paleta.texto, 0.30f)
}

/** Dibuja los bloques de una sección, uno debajo de otro. */
@Composable
fun Bloques(bloques: List<JsonObject>, ordenes: Ordenes, espacio: Dp = 0.dp) {
    Column(Modifier.fillMaxWidth(), Arrangement.spacedBy(espacio)) {
        for (bloque in bloques) {
            Bloque(bloque, ordenes)
        }
    }
}

@Composable
fun Bloque(bloque: JsonObject, ordenes: Ordenes) {
    when (bloque.texto("tipo")) {
        "grupo" -> GrupoBloques(bloque, ordenes)
        "fila" -> FilaAjuste(bloque, ordenes, ultima = true)
        "enlace" -> FilaEnlace(bloque, ordenes)
        "parrafo" -> Parrafo(bloque)
        "titulo" -> TituloBloque(bloque)
        "titulo_guia" -> TituloGuia(bloque)
        "puntos" -> Puntos(bloque)
        "comando" -> Comando(bloque, ordenes)
        "foto" -> Foto(bloque)
        "fotos" -> Fotos(bloque)
        "regla" -> LineaDivisoria(Modifier.padding(vertical = 8.dp))
        "advertencia" -> Advertencia(bloque)
        "recuadro" -> Recuadro(bloque)
        "botones" -> FilaBotones(bloque, ordenes)
        "tabla" -> TablaBloque(bloque)
        "cabecera" -> CabeceraTabla(bloque, ordenes)
        "pestanas" -> Pestanas(bloque, ordenes)
        "identidad" -> Identidad(bloque, ordenes)
        "temas" -> Temas(bloque, ordenes)
        "terminales" -> Terminales(bloque, ordenes)
        "fichas" -> FichasConBusqueda(bloque, ordenes)
        "tarjetas" -> TarjetasSoporte(bloque, ordenes)
        "enviados" -> ReportesEnviados(bloque, ordenes)
        "ficha_reporte" -> FichaReporte(bloque, ordenes)
        "errores" -> ErroresFrecuentes(bloque, ordenes)
        "hechos" -> Hechos(bloque)
        "distribucion" -> SelectorDistribucion(bloque, ordenes)
        "reporte" -> FormularioReporte(bloque, ordenes)
    }
}

// -- grupos y filas ------------------------------------------------------------------------------

@Composable
private fun GrupoBloques(grupo: JsonObject, ordenes: Ordenes) {
    val hijos = grupo.objetos("bloques")
    val titulo = grupo.texto("titulo")
    val sangria = grupo.logico("sangria")
    Column(Modifier.fillMaxWidth().padding(top = 30.dp)) {
        if (titulo.isNotEmpty()) {
            Texto(titulo, tamano = 14, peso = 600)
            Spacer(Modifier.height(4.dp))
        }
        if (sangria) {
            Column(Modifier.padding(horizontal = 16.dp, vertical = 10.dp), Arrangement.spacedBy(8.dp)) {
                ContenidoGrupo(hijos, ordenes)
            }
        } else {
            ContenidoGrupo(hijos, ordenes)
        }
    }
}

@Composable
private fun ContenidoGrupo(hijos: List<JsonObject>, ordenes: Ordenes) {
    for ((indice, hijo) in hijos.withIndex()) {
        if (hijo.texto("tipo") == "fila") {
            val ultima = hijos.drop(indice + 1).none { it.texto("tipo") == "fila" }
            FilaAjuste(hijo, ordenes, ultima)
        } else {
            Bloque(hijo, ordenes)
        }
    }
}

/** Una fila de ajuste: qué es a la izquierda y su control a la derecha. */
@Composable
private fun FilaAjuste(fila: JsonObject, ordenes: Ordenes, ultima: Boolean) {
    val control = fila.objeto("control")
    Column(Modifier.fillMaxWidth()) {
        BoxWithConstraints(Modifier.fillMaxWidth().padding(vertical = 12.dp)) {
            if (maxWidth < 520.dp && controlAncho(control)) {
                Column(verticalArrangement = Arrangement.spacedBy(9.dp)) {
                    TextoFila(fila, Modifier.fillMaxWidth())
                    ControlFila(control, ordenes)
                }
            } else {
                Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(18.dp), Alignment.CenterVertically) {
                    TextoFila(fila, Modifier.weight(1f))
                    ControlFila(control, ordenes)
                }
            }
        }
        if (!ultima) {
            LineaDivisoria(color = ColoresActuales.current.borde)
        }
    }
}

private fun controlAncho(control: JsonObject): Boolean {
    return control.texto("tipo") !in listOf("interruptor", "tecla")
}

@Composable
private fun TextoFila(fila: JsonObject, modifier: Modifier) {
    Column(modifier, Arrangement.spacedBy(2.dp)) {
        Texto(fila.texto("titulo"), tamano = 13, peso = 650)
        val detalle = fila.texto("detalle")
        if (detalle.isNotEmpty()) {
            Texto(detalle, tamano = 12, color = colorNota())
        }
    }
}

@Composable
private fun ControlFila(control: JsonObject, ordenes: Ordenes) {
    when (control.texto("tipo")) {
        "lista" -> ListaAjuste(control, ordenes)
        "interruptor" -> InterruptorAjuste(control, ordenes)
        "segmentos" -> Segmentos(control, ordenes)
        "botones" -> FilaBotones(control, ordenes)
        "acentos" -> Acentos(control, ordenes)
        "tecla" -> Tecla(control.texto("texto"))
        "ruta" -> Ruta(control, ordenes)
        "texto" -> {
            val modificador = Modifier.widthIn(max = 275.dp)
            Texto(control.texto("texto"), 12, modificador, peso = 700, alineado = TextAlign.Start)
        }
    }
}

@Composable
private fun ListaAjuste(control: JsonObject, ordenes: Ordenes) {
    val opciones = leerOpciones(control)
    val orden = control.objeto("orden")
    fun elegir(valor: String) {
        val ajuste = control.texto("ajuste")
        if (orden.isNotEmpty()) {
            ordenes.cumplir(ordenConValor(orden, valor))
        } else if (ajuste.isNotEmpty()) {
            ordenes.cumplir(ordenDeAjuste(ajuste, valor))
        } else {
            ordenes.guardar(control.texto("clave"), valorDePreferencia(control.texto("clave"), valor))
        }
    }
    val ancho = control.entero("ancho", 275)
    Desplegable(opciones, control.texto("valor"), ::elegir, Modifier.widthIn(max = ancho.dp).fillMaxWidth())
}

fun leerOpciones(control: JsonObject): List<Eleccion> {
    return control.objetos("opciones").map { opcion -> Eleccion(opcion.texto("valor"), opcion.texto("nombre")) }
}

/** La escala se guarda como número; las demás preferencias, como texto. */
private fun valorDePreferencia(clave: String, valor: String): JsonPrimitive {
    return if (clave == "scale") JsonPrimitive(valor.toInt()) else JsonPrimitive(valor)
}

private fun ordenConValor(orden: JsonObject, valor: String): JsonObject {
    val parametros = JsonObject(orden.objeto("parametros") + ("value" to JsonPrimitive(valor)))
    return JsonObject(orden + ("parametros" to parametros))
}

private fun ordenDeAjuste(nombre: String, valor: String): JsonObject {
    return JsonObject(
        mapOf(
            "orden" to JsonPrimitive("ajuste"),
            "nombre" to JsonPrimitive(nombre),
            "parametros" to JsonObject(mapOf("value" to JsonPrimitive(valor))),
        ),
    )
}

/** La lista desplegable de la Configuración: 36 de alto, con su valor a la izquierda. */
@Composable
fun Desplegable(
    opciones: List<Eleccion>,
    elegida: String,
    alElegir: (String) -> Unit,
    modifier: Modifier = Modifier,
    vacio: String = "",
) {
    val paleta = ColoresActuales.current
    var abierta by remember { mutableStateOf(false) }
    val actual = opciones.firstOrNull { it.valor == elegida }
    Box(modifier) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(36.dp)
                .marco(paleta.panelElevado, paleta.bordeFuerte, Medidas.radioChico)
                .pulsable { abierta = true }
                .padding(horizontal = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            val color = if (actual == null) paleta.sutil else paleta.texto
            Texto(actual?.nombre ?: vacio, 13, Modifier.weight(1f), peso = 600, color = color, lineas = 1)
        }
        if (abierta) {
            MenuOpciones(opciones, elegida, alCerrar = { abierta = false }) { valor ->
                abierta = false
                alElegir(valor)
            }
        }
    }
}

@Composable
private fun InterruptorAjuste(control: JsonObject, ordenes: Ordenes) {
    val activo = control.logico("activo")
    val aviso = control.objeto("aviso")
    fun cambiar(nuevo: Boolean) {
        val clave = control.texto("clave")
        if (nuevo && aviso.isNotEmpty()) {
            ordenes.preguntarYGuardar(aviso.texto("titulo"), aviso.texto("mensaje"), clave)
        } else {
            ordenes.guardar(clave, JsonPrimitive(nuevo))
        }
    }
    Interruptor(activo, ::cambiar)
}

@Composable
private fun Segmentos(control: JsonObject, ordenes: Ordenes) {
    val elegida = control.texto("valor")
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        for (opcion in control.objetos("opciones")) {
            val valor = opcion.texto("valor")
            val clase = if (valor == elegida) ClaseBoton.PRINCIPAL else ClaseBoton.NORMAL
            Boton(
                texto = opcion.texto("nombre"),
                alPulsar = { ordenes.guardar(control.texto("clave"), JsonPrimitive(valor)) },
                clase = clase,
                alto = 31.dp,
                tamano = 12,
                peso = 650,
            )
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun FilaBotones(control: JsonObject, ordenes: Ordenes) {
    val estado = control.texto("estado")
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
        itemVerticalAlignment = Alignment.CenterVertically,
    ) {
        if (estado.isNotEmpty()) {
            Texto(estado, tamano = 12, color = colorNota())
        }
        for (boton in control.objetos("botones")) {
            BotonOrden(boton, ordenes)
        }
    }
}

/** Un botón descrito por el servidor. */
@Composable
fun BotonOrden(boton: JsonObject, ordenes: Ordenes) {
    val orden = boton.objeto("orden")
    val paleta = ColoresActuales.current
    if (boton.texto("clase") == "enlace") {
        val modificador = Modifier.pulsable { ordenes.cumplir(orden) }
        Texto(boton.texto("texto"), 12, modificador, peso = 680, color = paleta.acento)
        return
    }
    val principal = boton.texto("clase") == "principal"
    Boton(
        texto = boton.texto("texto"),
        alPulsar = { ordenes.cumplir(orden) },
        clase = if (principal) ClaseBoton.PRINCIPAL else ClaseBoton.NORMAL,
        activo = boton.logico("activo", defecto = true),
        alto = if (principal) 36.dp else 34.dp,
        tamano = 12,
        peso = if (principal) 730 else 680,
    )
}

@Composable
private fun Acentos(control: JsonObject, ordenes: Ordenes) {
    val elegido = control.texto("valor")
    val paletas = LocalPaletas.current
    Row(Modifier.fillMaxWidthSiCabe(), Arrangement.spacedBy(4.dp)) {
        for (opcion in control.objetos("opciones")) {
            val nombre = opcion.texto("valor")
            val color = paletas.acento(nombre)
            val borde = if (nombre == elegido) color else Color.Transparent
            Box(
                modifier = Modifier
                    .size(34.dp)
                    .border(2.dp, borde, CircleShape)
                    .pulsable { ordenes.guardar("accent", JsonPrimitive(nombre)) },
                contentAlignment = Alignment.Center,
            ) {
                Box(Modifier.size(24.dp).background(color, CircleShape))
            }
        }
    }
}

private fun Modifier.fillMaxWidthSiCabe(): Modifier {
    return this.widthIn(max = 380.dp)
}

@Composable
private fun Tecla(texto: String) {
    val paleta = ColoresActuales.current
    Box(
        modifier = Modifier.marco(paleta.panelElevado, paleta.borde, Medidas.radioChico).padding(horizontal = 10.dp, vertical = 5.dp),
    ) {
        Texto(texto, tamano = 11, peso = 700, color = paleta.apagado)
    }
}

@Composable
private fun Ruta(control: JsonObject, ordenes: Ordenes) {
    val paleta = ColoresActuales.current
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(
            modifier = Modifier
                .widthIn(max = 400.dp)
                .width(400.dp)
                .height(32.dp)
                .marco(paleta.panelElevado, paleta.bordeSuave, Medidas.radioChico)
                .padding(horizontal = 12.dp),
            contentAlignment = Alignment.CenterStart,
        ) {
            SelectionContainer {
                TextoMono(control.texto("texto"), tamano = 11)
            }
        }
        Boton(control.texto("boton"), { ordenes.cumplir(control.objeto("orden")) }, alto = 28.dp, tamano = 11, peso = 650)
    }
}

/** Texto con la letra de consola, en una línea. */
@Composable
fun TextoMono(texto: String, tamano: Int, color: Color = ColoresActuales.current.apagado, lineas: Int = 1) {
    androidx.compose.foundation.text.BasicText(
        text = texto,
        style = estiloTexto(tamano, 700, color, deConsola = true),
        maxLines = lineas,
        overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
    )
}

@Composable
private fun FilaEnlace(bloque: JsonObject, ordenes: Ordenes) {
    Column(Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.height(44.dp).pulsable { ordenes.cumplir(bloque.objeto("orden")) },
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Texto(bloque.texto("texto"), tamano = 13, peso = 620)
            Icono(Res.drawable.chevron_right_gray, tamano = 11.dp)
        }
        if (!bloque.logico("ultimo")) {
            LineaDivisoria()
        }
    }
}

// -- textos ----------------------------------------------------------------------------------------

@Composable
private fun Parrafo(bloque: JsonObject) {
    val paleta = ColoresActuales.current
    val texto = bloque.texto("texto")
    SelectionContainer {
        when (bloque.texto("clase")) {
            "pista" -> Texto(texto, 10, Modifier.padding(vertical = 4.dp), color = paleta.sutil)
            "entrada" -> Texto(texto, 13, Modifier.padding(top = 6.dp))
            "apunte" -> Texto(texto, 12, Modifier.padding(start = 2.dp))
            "descripcion" -> Texto(texto, 12, Modifier.padding(top = 8.dp, bottom = 12.dp), color = colorNota())
            "guia" -> Texto(texto, 13, Modifier.padding(vertical = 3.dp))
            "guia_entrada" -> Texto(texto, 13, Modifier.padding(vertical = 6.dp), color = colorNota())
            "guia_dato" -> Texto(texto, 12, Modifier.padding(vertical = 3.dp), color = paleta.apagado)
            "aviso" -> Texto(texto, 12, Modifier.padding(vertical = 4.dp), color = colorNota())
            "vacio" -> Texto(texto, 12, Modifier.padding(vertical = 14.dp), color = paleta.apagado)
            else -> Texto(texto, 13)
        }
    }
}

@Composable
private fun TituloBloque(bloque: JsonObject) {
    val paleta = ColoresActuales.current
    val numero = bloque.entero("numero")
    Row(Modifier.padding(top = 12.dp, bottom = 6.dp), Arrangement.spacedBy(9.dp), Alignment.CenterVertically) {
        if (numero > 0) {
            Box(Modifier.size(22.dp).background(paleta.acentoSuave, CircleShape), Alignment.Center) {
                Texto(numero.toString(), tamano = 11, peso = 800, color = paleta.acento)
            }
        }
        Texto(bloque.texto("texto"), tamano = 14, peso = 650)
    }
}

@Composable
private fun TituloGuia(bloque: JsonObject) {
    Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(12.dp), Alignment.CenterVertically) {
        Texto(bloque.texto("texto"), 21, Modifier.weight(1f), peso = 700)
        Texto(bloque.texto("marca"), tamano = 12, color = ColoresActuales.current.apagado)
    }
}

@Composable
private fun Puntos(bloque: JsonObject) {
    Column(Modifier.padding(vertical = 4.dp), Arrangement.spacedBy(6.dp)) {
        for (texto in bloque.textos("textos")) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Texto("•", tamano = 13)
                Texto(texto, tamano = 13, modifier = Modifier.weight(1f))
            }
        }
    }
}

/** Una orden de terminal con su botón de copiar. */
@Composable
private fun Comando(bloque: JsonObject, ordenes: Ordenes) {
    val paleta = ColoresActuales.current
    val texto = bloque.texto("texto")
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 5.dp)
            .marco(paleta.color("console_bg"), paleta.color("console_border"), Medidas.radioPanel)
            .padding(horizontal = 12.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.weight(1f)) {
            SelectionContainer {
                TextoMono(texto, tamano = 12, color = paleta.color("console_text"), lineas = 20)
            }
        }
        Boton(t("Copy"), { ordenes.copiar(texto) }, alto = 28.dp, tamano = 11, icono = Res.drawable.copy_gray)
    }
}

private fun dibujoDeFoto(archivo: String): DrawableResource? {
    return when (archivo) {
        "i2c-header1-pins.jpg" -> Res.drawable.foto_i2c_header1_pins
        "i2c-header1-connected.jpg" -> Res.drawable.foto_i2c_header1_connected
        "tpms1-pins.jpg" -> Res.drawable.foto_tpms1_pins
        "tpms1-connected.jpg" -> Res.drawable.foto_tpms1_connected
        else -> null
    }
}

@Composable
private fun Foto(bloque: JsonObject) {
    val dibujo = dibujoDeFoto(bloque.texto("archivo"))
    if (dibujo != null) {
        Image(
            painter = painterResource(dibujo),
            contentDescription = bloque.texto("texto"),
            contentScale = ContentScale.FillWidth,
            modifier = Modifier.padding(vertical = 8.dp).widthIn(max = bloque.entero("ancho", 560).dp).fillMaxWidth(),
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Fotos(bloque: JsonObject) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        for (foto in bloque.objetos("fotos")) {
            Column(Modifier.widthIn(max = foto.entero("ancho", 275).dp)) {
                Foto(foto)
                Texto(foto.texto("texto"), tamano = 11, color = ColoresActuales.current.apagado)
            }
        }
    }
}

@Composable
private fun Advertencia(bloque: JsonObject) {
    Row(Modifier.padding(vertical = 8.dp), Arrangement.spacedBy(8.dp)) {
        Icono(Res.drawable.warning_orange, tamano = 16.dp)
        Texto(bloque.texto("texto"), 13, Modifier.weight(1f), color = ColoresActuales.current.naranja)
    }
}

@Composable
private fun Recuadro(bloque: JsonObject) {
    val paleta = ColoresActuales.current
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 8.dp)
            .marco(paleta.panelAlterno, paleta.bordeSuave, Medidas.radioPanel)
            .padding(horizontal = 14.dp, vertical = 10.dp),
    ) {
        Texto(bloque.texto("texto"), tamano = 12, color = colorNota())
    }
}

// -- identidad, pestañas y tablas --------------------------------------------------------------------

@Composable
private fun Identidad(bloque: JsonObject, ordenes: Ordenes) {
    Row(Modifier.fillMaxWidth().padding(top = 12.dp), Arrangement.spacedBy(16.dp), Alignment.Top) {
        Box(Modifier.size(52.dp), Alignment.Center) {
            Logotipo(48.dp)
        }
        Column(Modifier.weight(1f), Arrangement.spacedBy(3.dp)) {
            Texto(bloque.texto("nombre"), tamano = 18, peso = 800)
            Texto(bloque.texto("detalle"), tamano = 12, peso = 600, color = ColoresActuales.current.apagado)
        }
        BotonOrden(bloque.objeto("boton"), ordenes)
    }
}

@Composable
private fun Pestanas(bloque: JsonObject, ordenes: Ordenes) {
    val paleta = ColoresActuales.current
    val pestanas = bloque.objetos("pestanas")
    var abierta by remember { mutableStateOf("") }
    val actual = pestanas.firstOrNull { it.texto("clave") == abierta } ?: pestanas.firstOrNull() ?: return
    Column(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth().padding(top = 6.dp), Arrangement.spacedBy(2.dp)) {
            for (pestana in pestanas) {
                val elegida = pestana === actual
                val color = if (elegida) paleta.texto else paleta.apagado
                val linea = if (elegida) paleta.acento else Color.Transparent
                Column(
                    modifier = Modifier.pulsable { abierta = pestana.texto("clave") },
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Texto(pestana.texto("nombre"), 13, Modifier.padding(horizontal = 14.dp, vertical = 8.dp), peso = 650, color = color)
                    Box(Modifier.width(60.dp).height(2.dp).background(linea))
                }
            }
        }
        LineaDivisoria()
        Spacer(Modifier.height(10.dp))
        Bloques(actual.objetos("bloques"), ordenes)
    }
}

@Composable
private fun CabeceraTabla(bloque: JsonObject, ordenes: Ordenes) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(top = 18.dp, bottom = 10.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Texto(bloque.texto("texto"), tamano = 14, peso = 600)
        Texto(bloque.texto("cuenta"), tamano = 12, color = colorNota())
        Spacer(Modifier.weight(1f))
        val interruptor = bloque.objeto("interruptor")
        if (interruptor.isNotEmpty()) {
            Texto(interruptor.texto("texto"), tamano = 12, color = colorNota())
            Interruptor(interruptor.logico("activo"), { nuevo -> ordenes.guardar(interruptor.texto("clave"), JsonPrimitive(nuevo)) })
        }
        for (boton in bloque.objetos("botones")) {
            BotonOrden(boton, ordenes)
        }
    }
}

/** Una tabla: las columnas con peso 0 toman un ancho fijo y las demás se reparten el resto. */
@Composable
private fun TablaBloque(bloque: JsonObject) {
    val paleta = ColoresActuales.current
    val columnas = bloque.textos("columnas")
    val pesos = bloque.textos("pesos").map { it.toInt() }
    val filas = bloque.objetos("filas")
    var elegida by remember { mutableStateOf(-1) }
    Column(Modifier.fillMaxWidth().marco(paleta.panel, paleta.borde, Medidas.radioBoton).padding(1.dp)) {
        FilaTabla(columnas, pesos, paleta.panelAlterno, encabezado = true) {}
        for ((indice, fila) in filas.withIndex()) {
            val fondo = when {
                indice == elegida -> paleta.acentoSuave
                indice % 2 == 1 -> paleta.panelAlterno
                else -> paleta.panel
            }
            FilaTabla(fila.textos("celdas"), pesos, fondo, encabezado = false) { elegida = indice }
        }
    }
    if (bloque.logico("con_detalle")) {
        val detalle = filas.getOrNull(elegida)?.texto("detalle") ?: bloque.texto("pista")
        Spacer(Modifier.height(10.dp))
        TextoConsola(detalle, Modifier.fillMaxWidth().heightIn(min = 150.dp))
    }
}

@Composable
private fun FilaTabla(celdas: List<String>, pesos: List<Int>, fondo: Color, encabezado: Boolean, alPulsar: () -> Unit) {
    val paleta = ColoresActuales.current
    Row(
        modifier = Modifier.fillMaxWidth().heightIn(min = 32.dp).background(fondo).pulsable(!encabezado, alPulsar = alPulsar),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        for ((indice, celda) in celdas.withIndex()) {
            val peso = pesos.getOrElse(indice) { 1 }
            val ancho = if (peso == 0) Modifier.width(128.dp) else Modifier.weight(peso.toFloat())
            val modificador = ancho.padding(horizontal = 10.dp, vertical = 7.dp)
            val color = if (encabezado) paleta.apagado else paleta.texto
            Texto(celda, 11, modificador, peso = if (encabezado) 700 else 400, color = color)
        }
    }
}
