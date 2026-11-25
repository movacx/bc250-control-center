package org.bc250.controlcenter.paginas

import androidx.compose.foundation.background
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.serialization.json.JsonObject
import org.bc250.controlcenter.componentes.*
import org.bc250.controlcenter.datos.*
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas
import org.bc250.controlcenter.tema.MedidasPanelRendimiento as M

@Composable
internal fun SensoresRendimiento(
    aplicacion: Aplicacion, datos: JsonObject,
    buscar: String, alBuscar: (String) -> Unit, tipos: Set<Int>, alTipo: (Int) -> Unit,
    ocultar: Boolean, alOcultar: (Boolean) -> Unit,
    distribucion: String, alDistribucion: (String) -> Unit,
    ventana: Int, alVentana: (Int) -> Unit, alMarcar: (String) -> Unit,
) {
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val movil = maxWidth < M.anchoMovil
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (movil) {
                CampoTexto(buscar, alBuscar, Modifier.fillMaxWidth(), ayuda = t("Filter by name"), alto = M.altoFiltro)
                ControlesSensores(aplicacion, ocultar, alOcultar, apilado = true)
            } else {
                Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(10.dp), Alignment.CenterVertically) {
                    CampoTexto(buscar, alBuscar, Modifier.weight(1f), ayuda = t("Filter by name"), alto = M.altoFiltro)
                    ControlesSensores(aplicacion, ocultar, alOcultar)
                }
            }
            Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), Arrangement.spacedBy(6.dp)) {
                for (opcion in datos.objetos("kinds")) {
                    val indice = opcion.entero("index")
                    Boton(opcion.texto("title"), { alTipo(indice) },
                        clase = if (indice in tipos || (indice == 0 && tipos.isEmpty())) ClaseBoton.PRINCIPAL else ClaseBoton.COMPACTO,
                        alto = M.altoTipo, tamano = 11)
                }
            }
            if (distribucion == "split" && !movil) {
                Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(10.dp)) {
                    ListaSensores(datos, alMarcar, Modifier.weight(3f))
                    TrazasSensores(datos, ventana, Modifier.weight(2f))
                }
            } else {
                if (distribucion != "graphs") ListaSensores(datos, alMarcar, Modifier.fillMaxWidth())
                if (distribucion != "list") TrazasSensores(datos, ventana, Modifier.fillMaxWidth())
            }
            if (movil) {
                Leyenda(datos.texto("count"))
                Leyenda(datos.texto("footer"))
            } else {
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Leyenda(datos.texto("count"))
                    Leyenda("·")
                    Leyenda(datos.texto("footer"))
                }
            }
        }
    }
}

@Composable
private fun ControlesSensores(aplicacion: Aplicacion, ocultar: Boolean, alOcultar: (Boolean) -> Unit, apilado: Boolean = false) {
    @Composable fun casilla() {
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
            Casilla(ocultar, alOcultar)
            Texto(t("Hide unused channels"), tamano = 13)
        }
    }
    @Composable fun reiniciar() {
        Boton(t("Reset min/max"), {
            aplicacion.guardar("performance.reset", emptyMap(), "performance")
        }, alto = M.altoFiltro, tamano = 12, activo = aplicacion.puedeControlar)
    }
    if (apilado) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            casilla()
            reiniciar()
        }
    } else {
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
            casilla()
            reiniciar()
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun ListaSensores(datos: JsonObject, alMarcar: (String) -> Unit, modifier: Modifier) {
    val paleta = ColoresActuales.current
    val plegados = remember { mutableStateMapOf<String, Boolean>() }
    BoxWithConstraints(modifier.marco(paleta.panel, paleta.bordeSuave, 8.dp).height(M.altoListaSensores)) {
        val ancho = maxOf(maxWidth, M.anchoTabla)
        val etiqueta = ancho - M.anchoValorSensor * 4
        Column(Modifier.horizontalScroll(rememberScrollState())) {
            Column(Modifier.width(ancho)) {
                Row(Modifier.fillMaxWidth().height(M.altoCabeceraSensor).background(paleta.panelAlterno),
                    verticalAlignment = Alignment.CenterVertically) {
                    Texto(t("Sensor"), tamano = 11, peso = 820, modifier = Modifier.width(etiqueta).padding(start = 10.dp))
                    for (titulo in listOf("Value", "Min", "Avg", "Max")) {
                        Texto(t(titulo), tamano = 10, peso = 820, modifier = Modifier.width(M.anchoValorSensor))
                    }
                }
                Column(Modifier.fillMaxWidth().weight(1f).verticalScroll(rememberScrollState())) {
                    var grupo = ""
                    var alternar = false
                    for (fila in datos.objetos("rows")) {
                        if (fila.containsKey("group")) {
                            grupo = fila.texto("group")
                            val nombre = grupo
                            val plegado = plegados[nombre] ?: false
                            Row(Modifier.fillMaxWidth().height(M.altoFilaSensor).background(paleta.panelAlterno)
                                .pulsable { plegados[nombre] = !plegado }.padding(start = 8.dp),
                                verticalAlignment = Alignment.CenterVertically) {
                                Texto((if (plegado) "▸ " else "▾ ") + nombre, tamano = 11, peso = 780)
                            }
                        } else if (plegados[grupo] != true) {
                            val fondo = if (alternar) paleta.panelAlterno else paleta.panel
                            alternar = !alternar
                            Row(Modifier.fillMaxWidth().height(M.altoFilaSensor).background(fondo)
                                .combinedClickable(onClick = { alMarcar(fila.texto("key")) },
                                    onDoubleClick = { alMarcar(fila.texto("key")) }), verticalAlignment = Alignment.CenterVertically) {
                                Row(Modifier.width(etiqueta).padding(start = 22.dp),
                                    Arrangement.spacedBy(8.dp), Alignment.CenterVertically) {
                                    Casilla(fila.logico("ticked"), { alMarcar(fila.texto("key")) })
                                    Texto(fila.texto("label"), tamano = 11, lineas = 1)
                                }
                                for (clave in listOf("value", "min", "avg", "max")) {
                                    Texto(fila.texto(clave), tamano = 11, modifier = Modifier.width(M.anchoValorSensor))
                                }
                            }
                        }
                    }
                    if (datos.objetos("rows").isEmpty()) Leyenda(datos.texto("count"), Modifier.padding(12.dp))
                }
            }
        }
    }
}

@Composable
private fun TrazasSensores(datos: JsonObject, ventana: Int, modifier: Modifier) {
    val paleta = ColoresActuales.current
    Column(modifier.height(M.altoListaSensores).verticalScroll(rememberScrollState()), Arrangement.spacedBy(8.dp)) {
        val trazas = datos.objetos("traces")
        if (trazas.isEmpty() && datos.objetos("missing_traces").isEmpty()) {
            Leyenda(t("Tick a sensor in the list to draw its last two minutes here."), Modifier.padding(24.dp))
        }
        for (traza in trazas) {
            Column(Modifier.fillMaxWidth().marco(paleta.panelAlterno, paleta.bordeSuave, 8.dp).padding(10.dp)) {
                Row(Modifier.fillMaxWidth()) {
                    Texto(traza.texto("label"), tamano = 11, peso = 760, modifier = Modifier.weight(1f))
                    Texto(traza.texto("value"), tamano = 12, peso = 790)
                }
                if (!traza.logico("fresh")) Leyenda(t("Waiting for sample"))
                GraficaPanelRendimiento(traza.objeto("chart"), ventana, alto = 78.dp)
                Leyenda("${t("Min")} ${traza.texto("min")} · ${t("Avg")} ${traza.texto("avg")} · ${t("Max")} ${traza.texto("max")}")
            }
        }
        for (traza in datos.objetos("missing_traces")) {
            SubPanel {
                Texto(traza.texto("label"), tamano = 11, peso = 760)
                Leyenda(t("Waiting for first sample"))
            }
        }
    }
}
