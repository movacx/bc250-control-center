package org.bc250.controlcenter.paginas

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.*
import org.bc250.controlcenter.componentes.*
import org.bc250.controlcenter.datos.*
import org.bc250.controlcenter.tema.ColoresActuales

/** La previsualización usa los mismos planes de voltaje del escritorio en el servidor. */
@Composable
internal fun LaboratorioGpu(aplicacion: Aplicacion, datos: JsonObject, libre: Boolean,
    valores: Map<String, JsonElement>, alCambiarValores: (Map<String, JsonElement>) -> Unit, alCerrar: () -> Unit) {
    val tareas = rememberCoroutineScope()
    val lab = datos.objeto("voltage_lab")
    val oberon = lab.logico("is_oberon")
    val paleta = ColoresActuales.current
    var nivel by remember { mutableStateOf(if (valores.isNotEmpty()) -1 else datos.entero("opening_level", -1)) }
    var tabla by remember { mutableStateOf(ObjetoVacio) }
    var cargando by remember { mutableStateOf(true) }
    LaunchedEffect(nivel, valores, lab) {
        cargando = true
        delay(150)
        val parametros = mutableMapOf("level" to nivel.toString())
        if (valores.isNotEmpty()) parametros["values"] = JsonObject(valores).toString()
        tabla = aplicacion.consultar("gpu.laboratorio", parametros)
        cargando = false
    }
    fun aplicar(curva: Int) {
        val actuales = mutableMapOf<String, JsonElement>()
        for (fila in tabla.objetos("rows")) {
            if (fila.logico("custom_available")) {
                val frecuencia = fila.entero("frequency").toString()
                actuales[frecuencia] = valores[frecuencia] ?: JsonPrimitive(fila.entero("editor_value"))
            }
        }
        tareas.launch {
            if (pedirVoltaje(aplicacion, curva, JsonObject(actuales), if (curva == nivel) tabla else ObjetoVacio)) {
                alCerrar()
            }
        }
    }
    Dialogo(alCerrar, ancho = 880.dp) {
        Texto(t("GPU voltage curve"), tamano = 20, peso = 800)
        Texto(t("Choose a safe boost or edit the active points"), color = paleta.apagado, tamano = 13)
        if (oberon) {
            SubPanel {
                Texto(t("Oberon compatibility mode"), peso = 700, tamano = 13)
                Texto(t("Oberon uses two YAML endpoints. They are shown below for reference; curve editing is unavailable for this governor."), tamano = 13)
            }
        } else {
            TituloGpuCu(t("Curve boost"))
            val niveles = listOf(1, 2, 3, -1)
            RejillaGpuCu(4, 4) { indice, modificador ->
                val valor = niveles[indice]
                val nombre = when (valor) {
                    1 -> "+10 mV · " + t("Gentle")
                    2 -> "+20 mV · " + t("Moderate")
                    3 -> "+30 mV · " + t("High")
                    else -> t("Custom\nEdit active points")
                }
                Boton(nombre, { nivel = valor }, modificador,
                    clase = if (valor == nivel) ClaseBoton.PRINCIPAL else ClaseBoton.NORMAL, activo = libre)
            }
        }
        Texto(if (cargando) t("Loading") else tabla.texto("detail"), tamano = 12, color = paleta.apagado)
        if (tabla.isEmpty() && !cargando) Texto(t("Not connected"), color = paleta.rojo, tamano = 13)
        Column(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState())) {
            Row(Modifier.width(650.dp), Arrangement.spacedBy(10.dp)) {
                for (nombre in listOf("Frequency", "Current", if (oberon) "Configured" else "Selected", "Δ")) {
                    Texto(t(nombre), tamano = 12, peso = 700, modifier = Modifier.weight(1f))
                }
            }
            for (fila in tabla.objetos("rows")) {
                val frecuencia = fila.entero("frequency")
                Row(Modifier.width(650.dp).padding(vertical = 5.dp), Arrangement.spacedBy(10.dp)) {
                    Texto("$frecuencia MHz", modifier = Modifier.weight(1f), tamano = 13)
                    Texto(if (fila.entero("current") > 0) "${fila.entero("current")} mV" else t("Not set"), modifier = Modifier.weight(1f), tamano = 13)
                    if (nivel == -1 && fila.logico("custom_available") && !oberon) {
                        val elegido = (valores[frecuencia.toString()] as? JsonPrimitive)?.content?.toIntOrNull() ?: fila.entero("editor_value")
                        CampoNumero(elegido, { valor ->
                            alCambiarValores(valores + (frecuencia.toString() to JsonPrimitive(valor)))
                        }, datos.entero("minimum_mv", 600), datos.entero("maximum_mv", 1210), Modifier.weight(1f), sufijo = "mV", activo = libre)
                    } else Texto("${fila.entero("proposed")} mV", modifier = Modifier.weight(1f), tamano = 13)
                    Texto(if (oberon) t("Read only") else "${fila.entero("added")} mV", modifier = Modifier.weight(1f), tamano = 13)
                }
                LineaDivisoria()
            }
        }
        if (tabla.texto("error").isNotEmpty()) Texto(tabla.texto("error"), color = paleta.rojo, tamano = 13)
        Texto(t("{count} points changed", "count" to tabla.entero("changed").toString()) + " · " +
            t("peak {value} mV", "value" to tabla.entero("peak").toString()), tamano = 12)
        if (!oberon) {
            Boton(t("Restore governor defaults"), { aplicar(0) }, activo = libre && !cargando)
            Boton(t("Review and apply"), { aplicar(nivel) }, clase = ClaseBoton.PRINCIPAL,
                activo = libre && !cargando && tabla.logico("available"))
        }
        Boton(t("Close"), alCerrar)
    }
}
