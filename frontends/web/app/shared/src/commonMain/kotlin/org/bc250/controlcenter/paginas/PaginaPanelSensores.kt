package org.bc250.controlcenter.paginas

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.runtime.Composable
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
internal fun MemoriaPanel(aplicacion: Aplicacion, datos: JsonObject) {
    val paleta = ColoresActuales.current
    val muestra = datos.objeto("sample")
    val chips = muestra.objetos("chips")
    val activo = datos.logico("active")
    val externo = datos.logico("kernel_driver") || datos.objeto("external").texto("state") == "active"
    val listo = datos.logico("repository_ready") || activo || datos.logico("kernel_driver")
    val libre = aplicacion.puedeControlar && aplicacion.trabajo.terminado
    Column(Modifier.fillMaxWidth().marco(paleta.panel, paleta.borde, 8.dp).padding(13.dp, 10.dp),
        Arrangement.spacedBy(6.dp)) {
        BoxWithConstraints(Modifier.fillMaxWidth()) {
            val estrecho = maxWidth < M.anchoMovil
            @Composable fun valor() {
                val temperatura = muestra.numero("average_c")
                val texto = if (temperatura != null && chips.isNotEmpty()) "$temperatura °C"
                    else t(if (activo) "Waiting for sample" else "Off")
                Texto(texto, tamano = 14, peso = 700)
            }
            @Composable fun accion() {
                if (!externo) {
                    if (!listo) {
                        Boton(t("Prepare readings"), {
                            aplicacion.preguntarYEjecutar("gddr6.prepare", t("Prepare readings"))
                        }, activo = libre, alto = 34.dp, tamano = 12)
                    } else if (activo) {
                        Boton(t("Stop"), { aplicacion.interrumpirTrabajo() }, alto = 34.dp, tamano = 12,
                            activo = aplicacion.puedeControlar && !aplicacion.trabajo.terminado && aplicacion.trabajo.titulo == t("GDDR6 memory temperature"))
                    } else {
                        Boton(t("Monitor live"), {
                            aplicacion.preguntarYEjecutar("gddr6.monitor", t("GDDR6 memory temperature"),
                                datos.texto("blocker").ifEmpty { t("Monitor live") }, peligro = true)
                        }, activo = libre && datos.logico("can_monitor"), alto = 34.dp, tamano = 12)
                    }
                }
            }
            if (estrecho) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Texto(t("GDDR6 memory temperature").uppercase(), tamano = 10, peso = 800, color = ColoresActuales.current.apagado)
                    valor()
                    accion()
                }
            } else {
                Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(10.dp), Alignment.CenterVertically) {
                    Texto(t("GDDR6 memory temperature").uppercase(), tamano = 10, peso = 800, color = ColoresActuales.current.apagado)
                    valor()
                    Spacer(Modifier.weight(1f))
                    accion()
                }
            }
        }
        if (muestra.numero("hotspot_c") != null) {
            Leyenda(t("Hotspot {value}", "value" to "${muestra.numero("hotspot_c")} °C"))
        }
        if (externo) {
            Leyenda(t(if (datos.logico("kernel_driver")) "Read by the kernel driver (bc250_memory)" else "Read by BC250-Telemetry"))
        }
        if (datos.texto("blocker").isNotEmpty()) Texto(datos.texto("blocker"), tamano = 11, color = ColoresActuales.current.apagado)
        if (muestra.texto("error").isNotEmpty()) Leyenda(muestra.texto("error"))
        if (chips.isNotEmpty()) {
            Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), Arrangement.spacedBy(8.dp)) {
                for (chip in chips) {
                    val indice = chip.entero("chip", chip.entero("index"))
                    val temperatura = chip.numero("temperature_c")
                    Column(Modifier.width(100.dp)) {
                        Texto(t("Chip {chip}", "chip" to indice.toString()), tamano = 11, peso = 700)
                        Texto(if (temperatura == null) "--" else "$temperatura °C", tamano = 13)
                        BarraUso(temperatura?.div(110.0)?.times(100), Modifier.fillMaxWidth())
                    }
                }
            }
        }
    }
}

@Composable
internal fun AlimentacionPanel(aplicacion: Aplicacion, datos: JsonObject, alAyuda: () -> Unit) {
    val paleta = ColoresActuales.current
    val presente = datos.logico("vrm_present")
    Column(Modifier.fillMaxWidth().marco(paleta.panel, paleta.borde, 8.dp).padding(18.dp, 14.dp)) {
        Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp), Alignment.CenterVertically) {
            Texto(t("Power delivery").uppercase(), tamano = 13, peso = 800, modifier = Modifier.weight(1f))
            if (!presente) {
                Boton(t("How to enable"), alAyuda, alto = 34.dp, tamano = 12)
                if (datos.logico("vrm_repair")) {
                    Boton(t("Repair sensor"), {
                        aplicacion.preguntarYEjecutar("panel.repair_vrm", t("Repair sensor"))
                    }, activo = aplicacion.puedeControlar && aplicacion.trabajo.terminado, alto = 34.dp, tamano = 12)
                }
            }
        }
        if (presente) {
            BoxWithConstraints(Modifier.fillMaxWidth()) {
                val columnas = if (maxWidth >= M.anchoColumnas) 4 else if (maxWidth >= M.anchoMovil) 2 else 1
                val filas = datos.objetos("rails")
                Column {
                    for (inicio in filas.indices step columnas) {
                        Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(Medidas.espacio)) {
                            for (columna in 0 until columnas) {
                                val fila = filas.getOrNull(inicio + columna)
                                Column(Modifier.weight(1f)) { if (fila != null) LecturaPanel(fila) }
                            }
                        }
                    }
                }
            }
        }
    }
}
