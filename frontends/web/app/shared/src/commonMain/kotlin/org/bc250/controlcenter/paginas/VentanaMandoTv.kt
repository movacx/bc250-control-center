package org.bc250.controlcenter.paginas

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.hoverable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsHoveredAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.bc250.controlcenter.componentes.Boton
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.Dialogo
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.marco
import org.bc250.controlcenter.componentes.pulsable
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.ObjetoVacio
import org.bc250.controlcenter.datos.logico
import org.bc250.controlcenter.datos.objetos
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/** Lo que sabe el mando mientras está abierto. */
private class EstadoMando(val aplicacion: Aplicacion, private val tareas: CoroutineScope) {
    var datos by mutableStateOf(ObjetoVacio)
    var mensaje by mutableStateOf("")
    var ocupado by mutableStateOf(false)
    var enAjustes by mutableStateOf(false)

    suspend fun leer() {
        ocupado = true
        datos = aplicacion.consultar("tv.status")
        if (datos.texto("notice").isNotEmpty()) {
            mensaje = datos.texto("notice")
        }
        ocupado = false
    }

    fun comprobar() {
        tareas.launch { leer() }
    }

    fun enviar(boton: String) {
        ocupado = true
        mensaje = t("Sending...")
        tareas.launch {
            val pedido = JsonObject(mapOf("button" to JsonPrimitive(boton)))
            val respuesta = aplicacion.pulsarAhora("tv.press", pedido)
            mensaje = respuesta.texto("text")
            ocupado = false
            if (respuesta.logico("sent")) {
                leer()
            }
        }
    }
}

/** El mando de la TV y del receptor; el engranaje lo cambia por sus ajustes. */
@Composable
internal fun VentanaMandoTv(aplicacion: Aplicacion, alCerrar: () -> Unit) {
    val tareas = rememberCoroutineScope()
    val estado = remember { EstadoMando(aplicacion, tareas) }
    LaunchedEffect(Unit) {
        estado.leer()
    }
    Dialogo(alCerrar, ancho = 420.dp) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Texto(t(if (estado.enAjustes) "Settings" else "TV control"), 17, Modifier.weight(1f), peso = 780)
            if (estado.enAjustes) {
                BotonDibujado("back", t("Back"), 34.dp, 34.dp, CircleShape) { estado.enAjustes = false }
            } else {
                BotonDibujado("gear", t("Settings"), 34.dp, 34.dp, CircleShape) { estado.enAjustes = true }
            }
        }
        if (estado.enAjustes) {
            AjustesMando(estado, alCerrar)
        } else {
            CuerpoMando(estado)
            Texto(estado.mensaje, 12, Modifier.fillMaxWidth(), color = ColoresActuales.current.apagado, alineado = TextAlign.Center)
        }
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            if (estado.enAjustes) {
                Boton(t("Check"), estado::comprobar, activo = !estado.ocupado)
            }
            Spacer(Modifier.weight(1f))
            Boton(t("Close"), alCerrar, clase = ClaseBoton.PRINCIPAL)
        }
    }
}

// -- el mando -----------------------------------------------------------------------------------------

@Composable
private fun CuerpoMando(estado: EstadoMando) {
    val paleta = ColoresActuales.current
    Box(Modifier.fillMaxWidth(), Alignment.Center) {
        Column(
            modifier = Modifier
                .width(250.dp)
                .marco(paleta.panelElevado, paleta.bordeFuerte, 40.dp)
                .padding(horizontal = 26.dp)
                .padding(top = 12.dp, bottom = 26.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Box(Modifier.size(44.dp, 6.dp).background(paleta.borde, RoundedCornerShape(3.dp)))
            Spacer(Modifier.height(4.dp))
            PantallaMando(estado.datos)
            RotuloMando("TV")
            Row(horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                Tecla(estado, "tv-on", "power", "Turn the TV on", 50.dp, 50.dp, CircleShape, paleta.verde)
                Tecla(estado, "tv-off", "power", "Turn the TV off", 50.dp, 50.dp, CircleShape, paleta.rojo)
            }
            Tecla(estado, "switch", "input", "Use this input", 112.dp, 36.dp, RoundedCornerShape(18.dp))
            Spacer(Modifier.height(8.dp))
            RotuloMando("Receiver")
            Row(horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                Tecla(estado, "amp-on", "power", "Wake the receiver", 46.dp, 46.dp, RoundedCornerShape(13.dp), paleta.verde)
                Tecla(estado, "amp-off", "power", "Receiver standby", 46.dp, 46.dp, RoundedCornerShape(13.dp), paleta.rojo)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(22.dp), verticalAlignment = Alignment.CenterVertically) {
                Column {
                    val arriba = RoundedCornerShape(topStart = 27.dp, topEnd = 27.dp)
                    val abajo = RoundedCornerShape(bottomStart = 27.dp, bottomEnd = 27.dp)
                    Tecla(estado, "volume-up", "plus", "Volume up", 54.dp, 62.dp, arriba)
                    Tecla(estado, "volume-down", "minus", "Volume down", 54.dp, 62.dp, abajo)
                }
                Tecla(estado, "mute", "mute", "Mute", 46.dp, 46.dp, CircleShape)
            }
        }
    }
}

@Composable
private fun RotuloMando(texto: String) {
    Texto(t(texto), tamano = 12, peso = 700, color = ColoresActuales.current.apagado)
}

@Composable
private fun PantallaMando(datos: JsonObject) {
    val paleta = ColoresActuales.current
    Column(Modifier.fillMaxWidth().marco(paleta.panelAlterno, paleta.bordeSuave, Medidas.radioPanel).padding(12.dp, 6.dp)) {
        LineaPantalla("TV", datos.texto("tv"))
        LineaPantalla("Receiver", datos.texto("receiver"))
    }
}

@Composable
private fun LineaPantalla(nombre: String, valor: String) {
    Row(Modifier.fillMaxWidth()) {
        Texto(t(nombre), 11, Modifier.weight(1f), color = ColoresActuales.current.sutil)
        Texto(valor.ifEmpty { "--" }, tamano = 12, peso = 650)
    }
}

@Composable
private fun Tecla(
    estado: EstadoMando,
    orden: String,
    dibujo: String,
    nombre: String,
    ancho: Dp,
    alto: Dp,
    forma: Shape,
    color: Color? = null,
) {
    val activo = estado.datos.logico("ready") && !estado.ocupado && estado.aplicacion.puedeControlar
    BotonDibujado(dibujo, t(nombre), ancho, alto, forma, color, activo) { estado.enviar(orden) }
}

@Composable
private fun BotonDibujado(
    dibujo: String,
    nombre: String,
    ancho: Dp,
    alto: Dp,
    forma: Shape,
    color: Color? = null,
    activo: Boolean = true,
    alPulsar: () -> Unit,
) {
    val paleta = ColoresActuales.current
    val interaccion = remember { MutableInteractionSource() }
    val encima by interaccion.collectIsHoveredAsState()
    var fondo = paleta.control
    var borde = paleta.bordeFuerte
    var tinta = color ?: paleta.texto
    if (!activo) {
        fondo = paleta.fondoInactivo
        borde = paleta.bordeSuave
        tinta = paleta.textoInactivo
    } else if (encima) {
        fondo = paleta.controlEncima
    }
    Box(
        modifier = Modifier
            .size(ancho, alto)
            .clip(forma)
            .background(fondo)
            .border(1.dp, borde, forma)
            .hoverable(interaccion)
            .semantics { contentDescription = nombre }
            .pulsable(activo, interaccion, alPulsar),
        contentAlignment = Alignment.Center,
    ) {
        Canvas(Modifier.fillMaxSize()) {
            dibujarSimbolo(dibujo, tinta)
        }
    }
}

/** Los símbolos del mando, en la misma cuadrícula de 24 que usa el escritorio. */
private fun DrawScope.dibujarSimbolo(nombre: String, color: Color) {
    val unidad = minOf(size.width, size.height) * 0.48f / 24f
    val grosor = maxOf(1.6f * density, unidad * 2f)
    val centro = Offset(size.width / 2, size.height / 2)

    fun punto(x: Float, y: Float): Offset {
        return Offset(centro.x + x * unidad, centro.y + y * unidad)
    }

    fun linea(x1: Float, y1: Float, x2: Float, y2: Float) {
        drawLine(color, punto(x1, y1), punto(x2, y2), grosor, StrokeCap.Round)
    }

    val trazo = Stroke(grosor, cap = StrokeCap.Round, join = StrokeJoin.Round)
    when (nombre) {
        "power" -> {
            val lado = 17f * unidad
            drawArc(color, -60f, 300f, false, punto(-8.5f, -7.5f), Size(lado, lado), style = trazo)
            linea(0f, -10f, 0f, -1f)
        }
        "input" -> {
            linea(-2f, -9f, 9f, -9f)
            linea(9f, -9f, 9f, 9f)
            linea(9f, 9f, -2f, 9f)
            linea(-10f, 0f, 3f, 0f)
            linea(-1f, -4f, 3f, 0f)
            linea(-1f, 4f, 3f, 0f)
        }
        "plus" -> {
            linea(-7f, 0f, 7f, 0f)
            linea(0f, -7f, 0f, 7f)
        }
        "minus" -> linea(-7f, 0f, 7f, 0f)
        "mute" -> {
            val altavoz = contorno(listOf(-10f to -4f, -5f to -4f, 1f to -9f, 1f to 9f, -5f to 4f, -10f to 4f), ::punto)
            drawPath(altavoz, color)
            linea(5f, -4f, 11f, 4f)
            linea(11f, -4f, 5f, 4f)
        }
        "gear" -> {
            drawPath(contorno(dientes(), ::punto), color, style = trazo)
            drawCircle(color, 3 * unidad, centro, style = trazo)
        }
        "back" -> {
            linea(7f, 0f, -7f, 0f)
            linea(-1f, -6f, -7f, 0f)
            linea(-1f, 6f, -7f, 0f)
        }
    }
}

private fun contorno(puntos: List<Pair<Float, Float>>, aPantalla: (Float, Float) -> Offset): Path {
    val camino = Path()
    for ((indice, punto) in puntos.withIndex()) {
        val destino = aPantalla(punto.first, punto.second)
        if (indice == 0) {
            camino.moveTo(destino.x, destino.y)
        } else {
            camino.lineTo(destino.x, destino.y)
        }
    }
    camino.close()
    return camino
}

private fun dientes(): List<Pair<Float, Float>> {
    val puntos = mutableListOf<Pair<Float, Float>>()
    val perfil = listOf(-13 to 7.2f, -9 to 10.2f, 9 to 10.2f, 13 to 7.2f)
    for (diente in 0 until 8) {
        for ((giro, radio) in perfil) {
            val angulo = ((45 * diente + giro) * PI / 180).toFloat()
            puntos.add(radio * cos(angulo) to radio * sin(angulo))
        }
    }
    return puntos
}

// -- los ajustes del mando ------------------------------------------------------------------------------

@Composable
private fun AjustesMando(estado: EstadoMando, alCerrar: () -> Unit) {
    val paleta = ColoresActuales.current
    Texto(estado.datos.texto("through"), tamano = 12, color = paleta.apagado)
    Row(Modifier.fillMaxWidth().marco(paleta.panelAlterno, paleta.bordeSuave, Medidas.radioPanel).padding(12.dp, 8.dp)) {
        LecturaMando("TV", estado.datos.texto("tv"), Modifier.weight(1f))
        LecturaMando("Receiver", estado.datos.texto("receiver"), Modifier.weight(1f))
        LecturaMando("This computer", estado.datos.texto("address"), Modifier.weight(1f))
    }
    Texto(t("Automatic"), tamano = 13, peso = 700)
    for (fila in estado.datos.objetos("automation")) {
        FilaAutomatica(estado, fila, alCerrar)
    }
}

@Composable
private fun LecturaMando(nombre: String, valor: String, modifier: Modifier) {
    Column(modifier) {
        Texto(t(nombre), tamano = 11, color = ColoresActuales.current.sutil)
        Texto(valor.ifEmpty { "--" }, tamano = 12, peso = 650)
    }
}

@Composable
private fun FilaAutomatica(estado: EstadoMando, fila: JsonObject, alCerrar: () -> Unit) {
    val paleta = ColoresActuales.current
    val instalada = fila.logico("installed")
    val nombreBoton = t(if (instalada) "Remove" else "Install")
    fun cambiar() {
        alCerrar()
        val parametros = mapOf("key" to JsonPrimitive(fila.texto("key")), "enable" to JsonPrimitive(!instalada))
        estado.aplicacion.preguntarYEjecutar("tv.automation", fila.texto("title"), fila.texto("detail"), parametros, instalada)
    }
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .marco(paleta.panelAlterno, paleta.bordeSuave, Medidas.radioPanel)
            .padding(start = 12.dp, top = 6.dp, end = 10.dp, bottom = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f), Arrangement.spacedBy(1.dp)) {
            Texto(fila.texto("title"), tamano = 12, peso = 650)
            Texto(fila.texto("detail"), tamano = 11, color = paleta.apagado)
            if (fila.texto("note").isNotEmpty()) {
                Texto(fila.texto("note"), tamano = 11, color = paleta.naranja)
            }
        }
        val activo = estado.aplicacion.puedeControlar && estado.aplicacion.trabajo.terminado && !fila.logico("foreign")
        Boton(nombreBoton, ::cambiar, Modifier.width(88.dp), activo = activo, alto = 32.dp, tamano = 12)
    }
}
