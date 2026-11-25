package org.bc250.controlcenter.paginas

import androidx.compose.foundation.background
import androidx.compose.foundation.Image
import org.jetbrains.compose.resources.painterResource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.serialization.json.JsonObject
import org.bc250.controlcenter.componentes.*
import org.bc250.controlcenter.datos.*
import org.bc250.controlcenter.recursos.*
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas
import org.bc250.controlcenter.tema.MedidasPanelRendimiento as M

/** El panel nunca inicia una lectura privilegiada al abrirse. */
@Composable
fun PaginaPanel(aplicacion: Aplicacion) {
    var dialogo by remember { mutableStateOf("") }
    var novedades by remember { mutableStateOf(ObjetoVacio) }
    LaunchedEffect(Unit) {
        while (true) {
            novedades = aplicacion.consultar("panel.update")
            if (novedades.logico("available")) dialogo = "update"
            delay(900000)
        }
    }
    LaunchedEffect(Unit) {
        while (true) {
            aplicacion.leerPagina("dashboard")
            aplicacion.pausar(3000)
        }
    }
    val datos = JsonObject(aplicacion.lectura("dashboard") + ("update" to novedades))
    Box(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())
            .padding(start = M.margenHorizontal, top = M.margenSuperior, end = 26.dp, bottom = 24.dp),
            Arrangement.spacedBy(Medidas.espacio)) {
            CabeceraPanel(datos)
            if (datos.texto("error").isNotEmpty()) Leyenda(datos.texto("error"))
            if (datos.objetos("cards").isEmpty() || datos.logico("waiting")) Leyenda(t("Checking…"))
            InstrumentosPanel(aplicacion, datos) { dialogo = "telemetry" }
            MemoriaPanel(aplicacion, datos.objeto("gddr6"))
            AlimentacionPanel(aplicacion, datos) { dialogo = "vrm" }
            PreparacionPanel(aplicacion, datos) { nuevo -> dialogo = nuevo }
        }
        DialogosPanel(aplicacion, datos, dialogo) { dialogo = "" }
    }
}

@Composable
private fun CabeceraPanel(datos: JsonObject) {
    val paleta = ColoresActuales.current
    Row(Modifier.fillMaxWidth().heightIn(min = M.cabeceraPanel).marco(paleta.panel, paleta.bordeSuave, 8.dp)
        .padding(horizontal = 21.dp, vertical = 15.dp),
        Arrangement.spacedBy(14.dp), Alignment.CenterVertically) {
        val dibujo = if (paleta.esClaro) Res.drawable.bc250_board_light else Res.drawable.bc250_board_dark
        Image(painterResource(dibujo), "AMD BC-250", Modifier.size(64.dp, 44.dp))
        Column(Modifier.weight(1f), Arrangement.spacedBy(3.dp)) {
            Texto(datos.texto("title", "AMD BC-250"), tamano = 17, peso = 800)
            Texto(datos.texto("specification"), 12, peso = 600, color = paleta.apagado)
        }
    }
}

@Composable
private fun InstrumentosPanel(aplicacion: Aplicacion, datos: JsonObject, alTelemetria: () -> Unit) {
    val tarjetas = datos.objetos("cards")
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        if (maxWidth >= M.anchoColumnas) {
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(Medidas.espacio)) {
                for (tarjeta in tarjetas) {
                    val ancho = if (tarjeta.texto("key") == "gpu") 628f else 482f
                    InstrumentoPanel(aplicacion, tarjeta, datos,
                        Modifier.weight(ancho).heightIn(min = M.altoInstrumento), alTelemetria)
                }
            }
        } else {
            Column(verticalArrangement = Arrangement.spacedBy(Medidas.espacio)) {
                for (tarjeta in tarjetas) InstrumentoPanel(aplicacion, tarjeta, datos, Modifier.fillMaxWidth(), alTelemetria)
            }
        }
    }
}

@Composable
private fun InstrumentoPanel(aplicacion: Aplicacion, tarjeta: JsonObject, datos: JsonObject, modifier: Modifier, alTelemetria: () -> Unit) {
    val paleta = ColoresActuales.current
    val clave = tarjeta.texto("key")
    Column(modifier.marco(paleta.panel, paleta.bordeSuave, 8.dp).padding(start = 19.dp, top = 16.dp, end = 19.dp, bottom = 16.dp)) {
        Row(Modifier.fillMaxWidth().height(44.dp), verticalAlignment = Alignment.CenterVertically) {
            Texto(tarjeta.texto("title").uppercase(), tamano = 13, peso = 800, modifier = Modifier.weight(1f))
            Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(end = 4.dp)) {
                Texto(tarjeta.texto("value", "--"), tamano = 32, peso = 800)
                Texto(tarjeta.texto("unit"), tamano = 12, peso = 700,
                    color = paleta.apagado, modifier = Modifier.padding(bottom = 4.dp))
            }
        }
        Spacer(Modifier.height(7.dp))
        Box(Modifier.fillMaxWidth().height(2.dp).background(paleta.acento))
        val grupos = tarjeta.objetos("groups")
        if (clave == "gpu") {
            BoxWithConstraints(Modifier.fillMaxWidth()) {
                if (maxWidth >= 480.dp) {
                    Row(horizontalArrangement = Arrangement.spacedBy(22.dp)) {
                        for (columna in 0..1) {
                            Column(Modifier.weight(1f)) {
                                for (grupo in grupos) {
                                    if (grupo.entero("column") == columna) GrupoPanel(grupo)
                                }
                            }
                        }
                    }
                } else {
                    Column { for (grupo in grupos) GrupoPanel(grupo) }
                }
            }
        } else {
            for (grupo in grupos) GrupoPanel(grupo)
        }
        if (clave == "cpu") NucleosPanel(datos)
        val telemetria = datos.objeto("telemetry")
        if (clave == "gpu" && telemetria.logico("visible")) {
            Boton(telemetria.texto("label"), {
                repararTelemetriaPanel(aplicacion, telemetria, alTelemetria)
            }, activo = !telemetria.logico("pending") && aplicacion.puedeControlar && aplicacion.trabajo.terminado,
                alto = 30.dp, tamano = 11)
        }
        Spacer(Modifier.weight(1f))
        Spacer(Modifier.height(10.dp))
        val acciones = when (clave) {
            "cpu" -> listOf("Configure CPU" to "cpu")
            "gpu" -> listOf("Configure Governor" to "gpu", "Configure CUs" to "cu")
            else -> listOf("Fan Control" to "fans", "Automatic curve" to "fans")
        }
        Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp)) {
            for ((titulo, destino) in acciones) {
                val esPrincipal = titulo == acciones.first().first
                BotonPanel(t(titulo), esPrincipal, Modifier.weight(1f)) { aplicacion.irA(destino) }
            }
        }
    }
}

@Composable
private fun GrupoPanel(grupo: JsonObject) {
    var abierto by remember(grupo.texto("title")) { mutableStateOf(!grupo.logico("collapsed")) }
    val plegable = grupo.logico("collapsed")
    Column(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth().height(M.altoGrupo).padding(top = 5.dp).pulsable(plegable) { abierto = !abierto },
            verticalAlignment = Alignment.CenterVertically) {
            if (plegable) {
                val flecha = if (abierto) Res.drawable.chevron_down_gray else Res.drawable.chevron_right_gray
                Icono(flecha, 11.dp)
                Spacer(Modifier.width(4.dp))
            }
            Texto(t(grupo.texto("title")).uppercase(), tamano = 10, peso = 800,
                color = ColoresActuales.current.apagado)
        }
        if (abierto) {
            val filas = grupo.objetos("rows")
            for ((indice, fila) in filas.withIndex()) {
                if (indice > 0) {
                    LineaDivisoria()
                }
                LecturaPanel(fila)
            }
        }
    }
}

/** El botón al pie de una tarjeta; el principal va en color de acento. */
@Composable
internal fun BotonPanel(texto: String, principal: Boolean, modifier: Modifier = Modifier, alPulsar: () -> Unit) {
    val clase = if (principal) ClaseBoton.ACENTO else ClaseBoton.NORMAL
    Boton(texto, alPulsar, modifier, clase, alto = 34.dp, tamano = 12)
}

@Composable
internal fun LecturaPanel(fila: JsonObject) {
    val paleta = ColoresActuales.current
    val detalle = fila.texto("detail")
    val unidad = fila.texto("unit")
    val alto = if (detalle.isEmpty()) M.altoLectura else M.altoLecturaDoble
    Row(Modifier.fillMaxWidth().heightIn(min = alto), Arrangement.spacedBy(8.dp), Alignment.CenterVertically) {
        Texto(t(fila.texto("label")), 12, Modifier.weight(1f), peso = 500, color = paleta.apagado)
        Column(horizontalAlignment = Alignment.End) {
            val color = when (fila.texto("tone")) {
                "danger" -> paleta.rojo
                "warning" -> paleta.naranja
                else -> paleta.texto
            }
            Texto(t(fila.texto("value", "Not detected")), tamano = 14, peso = 700, color = color)
            if (detalle.isNotEmpty()) {
                Texto(t(detalle), tamano = 10, color = paleta.apagado)
            }
        }
        // Sin unidad queda el mismo hueco a la derecha que en el escritorio.
        val anchoUnidad = if (unidad.isEmpty()) 0.dp else M.anchoUnidad
        Texto(unidad, 11, Modifier.width(anchoUnidad), peso = 600, color = paleta.apagado)
    }
}

@Composable
private fun NucleosPanel(datos: JsonObject) {
    val paleta = ColoresActuales.current
    Spacer(Modifier.height(16.dp))
    Row(Modifier.fillMaxWidth().padding(top = 9.dp, bottom = 4.dp).height(20.dp), verticalAlignment = Alignment.CenterVertically) {
        Texto(t("Live core monitor").uppercase(), 10, Modifier.weight(1f), peso = 800, color = paleta.apagado)
        Texto(datos.texto("topology"), tamano = 14, peso = 700)
    }
    val nucleos = datos.objetos("cores")
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        if (maxWidth < 320.dp) {
            ColumnaNucleosPanel(nucleos, Modifier.fillMaxWidth())
        } else {
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(18.dp)) {
                ColumnaNucleosPanel(nucleos.take(4), Modifier.weight(1f))
                ColumnaNucleosPanel(nucleos.drop(4), Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun ColumnaNucleosPanel(nucleos: List<JsonObject>, modifier: Modifier) {
    Column(modifier) {
        for ((indice, nucleo) in nucleos.withIndex()) {
            if (indice > 0) {
                LineaDivisoria()
            }
            FilaNucleoPanel(nucleo)
        }
    }
}

@Composable
private fun FilaNucleoPanel(nucleo: JsonObject) {
    val paleta = ColoresActuales.current
    val oculto = nucleo.texto("detail").isEmpty()
    val colorNombre = if (oculto) paleta.sutil else paleta.apagado
    val colorValor = if (oculto) paleta.sutil else paleta.texto
    Row(Modifier.fillMaxWidth().height(M.altoNucleo), verticalAlignment = Alignment.CenterVertically) {
        Texto(nucleo.texto("label"), 12, Modifier.width(36.dp), peso = 800, color = colorNombre)
        Texto(nucleo.texto("value"), 13, Modifier.width(84.dp), peso = 750, color = colorValor, lineas = 1)
        BarraUso(nucleo.numero("usage"), Modifier.weight(1f))
        Texto(nucleo.texto("detail"), 12, Modifier.width(50.dp), peso = 700, color = paleta.apagado, alineado = TextAlign.End)
    }
}

internal fun repararTelemetriaPanel(aplicacion: Aplicacion, telemetria: JsonObject, alTelemetria: () -> Unit) {
    if (telemetria.logico("available")) {
        aplicacion.preguntarYEjecutar("panel.repair_telemetry", telemetria.texto("label"))
    } else alTelemetria()
}
