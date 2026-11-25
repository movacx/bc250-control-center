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
            delay(3000)
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
    Row(Modifier.fillMaxWidth().heightIn(min = M.cabeceraPanel).marco(paleta.panel, paleta.borde, 8.dp)
        .padding(horizontal = 20.dp, vertical = 15.dp),
        Arrangement.spacedBy(14.dp), Alignment.CenterVertically) {
        val dibujo = if (paleta.esClaro) Res.drawable.bc250_board_light else Res.drawable.bc250_board_dark
        Image(painterResource(dibujo), "AMD BC-250", Modifier.size(64.dp, 44.dp))
        Column(Modifier.weight(1f), Arrangement.spacedBy(3.dp)) {
            Texto(datos.texto("title", "AMD BC-250"), tamano = 17, peso = 800)
            Leyenda(datos.texto("specification"))
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
    Column(modifier.marco(paleta.panel, paleta.bordeSuave, 8.dp).padding(horizontal = M.margenInstrumento, vertical = 15.dp)) {
        Row(Modifier.fillMaxWidth().height(44.dp), verticalAlignment = Alignment.CenterVertically) {
            Texto(tarjeta.texto("title").uppercase(), tamano = 13, peso = 800, modifier = Modifier.weight(1f))
            Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                Texto(tarjeta.texto("value", "--"), tamano = 32, peso = 800)
                Texto(tarjeta.texto("unit"), tamano = 12, peso = 700,
                    color = paleta.apagado, modifier = Modifier.padding(bottom = 5.dp))
            }
        }
        LineaDivisoria(Modifier.padding(top = 7.dp))
        val grupos = tarjeta.objetos("groups")
        if (clave == "gpu") {
            BoxWithConstraints(Modifier.fillMaxWidth()) {
                if (maxWidth >= 480.dp) {
                    Row(horizontalArrangement = Arrangement.spacedBy(18.dp)) {
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
                if (telemetria.logico("available")) {
                    aplicacion.preguntarYEjecutar("panel.repair_telemetry", telemetria.texto("label"))
                } else alTelemetria()
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
                Boton(t(titulo), { aplicacion.irA(destino) }, Modifier.weight(1f), alto = 34.dp, tamano = 12)
            }
        }
    }
}

@Composable
private fun GrupoPanel(grupo: JsonObject) {
    var abierto by remember(grupo.texto("title")) { mutableStateOf(!grupo.logico("collapsed")) }
    val plegable = grupo.logico("collapsed")
    Column(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth().height(M.altoGrupo).pulsable(plegable) { abierto = !abierto },
            verticalAlignment = Alignment.CenterVertically) {
            val flecha = if (plegable) (if (abierto) "▾ " else "▸ ") else ""
            Texto(flecha + t(grupo.texto("title")).uppercase(), tamano = 10, peso = 800,
                color = ColoresActuales.current.apagado)
        }
        if (abierto) {
            for (fila in grupo.objetos("rows")) LecturaPanel(fila)
        }
    }
}

@Composable
internal fun LecturaPanel(fila: JsonObject) {
    val paleta = ColoresActuales.current
    Column(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth().heightIn(min = M.altoLectura), Arrangement.spacedBy(8.dp), Alignment.CenterVertically) {
            Texto(t(fila.texto("label")), tamano = 12, color = paleta.apagado, modifier = Modifier.weight(1f))
            Column(horizontalAlignment = Alignment.End) {
                val color = when (fila.texto("tone")) {
                    "danger" -> paleta.rojo
                    "warning" -> paleta.naranja
                    else -> paleta.texto
                }
                Texto(t(fila.texto("value", "Not detected")), tamano = 14, peso = 700, color = color)
                if (fila.texto("detail").isNotEmpty()) Leyenda(t(fila.texto("detail")))
            }
            if (fila.texto("unit").isNotEmpty()) {
                Texto(fila.texto("unit"), tamano = 11, peso = 600, color = paleta.apagado,
                    modifier = Modifier.width(M.anchoUnidad))
            }
        }
        LineaDivisoria()
    }
}

@Composable
private fun NucleosPanel(datos: JsonObject) {
    Row(Modifier.fillMaxWidth().heightIn(min = 32.dp), verticalAlignment = Alignment.CenterVertically) {
        Texto(t("Live core monitor").uppercase(), tamano = 10, peso = 800,
            color = ColoresActuales.current.apagado, modifier = Modifier.weight(1f))
        Texto(datos.texto("topology"), tamano = 12, peso = 700)
    }
    val nucleos = datos.objetos("cores")
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val columnas = if (maxWidth < 400.dp) 1 else 2
        val filas = 8 / columnas
        Column {
            for (indice in 0 until filas) {
                Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(18.dp)) {
                    for (columna in 0 until columnas) {
                        val nucleo = nucleos.getOrNull(indice + columna * filas) ?: ObjetoVacio
                        Row(Modifier.weight(1f).height(M.altoNucleo), Arrangement.spacedBy(8.dp), Alignment.CenterVertically) {
                            Texto(nucleo.texto("label"), tamano = 12, peso = 800)
                            Texto(nucleo.texto("value"), tamano = 12, peso = 750, modifier = Modifier.weight(1f))
                            BarraUso(nucleo.numero("usage"), Modifier.width(35.dp))
                            Texto(nucleo.texto("detail"), tamano = 11)
                        }
                    }
                }
            }
        }
    }
}
