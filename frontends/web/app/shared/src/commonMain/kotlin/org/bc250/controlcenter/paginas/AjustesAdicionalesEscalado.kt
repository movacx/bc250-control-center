package org.bc250.controlcenter.paginas

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.bc250.controlcenter.componentes.Boton
import org.bc250.controlcenter.componentes.CampoTexto
import org.bc250.controlcenter.componentes.Casilla
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.Desplegable
import org.bc250.controlcenter.componentes.Dialogo
import org.bc250.controlcenter.componentes.Eleccion
import org.bc250.controlcenter.componentes.LineaDivisoria
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.marco
import org.bc250.controlcenter.datos.logico
import org.bc250.controlcenter.datos.numero
import org.bc250.controlcenter.datos.objeto
import org.bc250.controlcenter.datos.objetos
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas

/** Escalado: una tarjeta por herramienta y, debajo, los juegos donde está puesta. */
@Composable
internal fun EscaladoExtras(estado: EstadoExtras, datos: JsonObject, paneles: List<JsonObject>) {
    val herramientas = paneles.firstOrNull()?.objetos("rows") ?: emptyList()
    var ajustesHelix by remember { mutableStateOf(false) }
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        if (maxWidth >= 900.dp) {
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(14.dp)) {
                for (fila in herramientas) {
                    TarjetaHerramienta(estado, fila, datos, Modifier.weight(1f)) { ajustesHelix = true }
                }
            }
        } else {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                for (fila in herramientas) {
                    TarjetaHerramienta(estado, fila, datos, Modifier.fillMaxWidth()) { ajustesHelix = true }
                }
            }
        }
    }
    for (panel in paneles.drop(1)) {
        PanelExtras(estado, "upscaling", panel)
    }
    if (ajustesHelix) {
        DialogoHelix(estado, datos.objetos("helixsr_settings")) { ajustesHelix = false }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun TarjetaHerramienta(estado: EstadoExtras, fila: JsonObject, datos: JsonObject, modifier: Modifier, alAjustes: () -> Unit) {
    val paleta = ColoresActuales.current
    val libre = estado.aplicacion.puedeControlar && estado.aplicacion.trabajo.terminado
    val esHelix = fila.texto("title").startsWith("HelixSR")
    Column(modifier.marco(paleta.panelAlterno, paleta.bordeSuave, Medidas.radioBoton).padding(1.dp)) {
        Column(Modifier.fillMaxWidth().background(paleta.panel).padding(14.dp), Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp), Alignment.CenterVertically) {
                Texto(fila.texto("title"), 14, Modifier.weight(1f), peso = 650)
                for (enlace in fila.objetos("links")) {
                    Boton(enlace.texto("label"), { estado.aplicacion.abrirEnlace(enlace.texto("url")) }, alto = 30.dp, tamano = 12)
                }
            }
            Texto(fila.texto("detail"), tamano = 12, color = paleta.apagado)
        }
        LineaDivisoria()
        Column(Modifier.fillMaxWidth().padding(14.dp), Arrangement.spacedBy(10.dp)) {
            Texto(t("Status"), tamano = 12, color = paleta.apagado)
            Texto(fila.texto("value"), tamano = 14, peso = 700, color = colorExtras(fila.texto("tone")))
            if (fila.texto("blocked").isNotEmpty()) {
                Texto(fila.texto("blocked"), tamano = 12, color = paleta.apagado)
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                for ((indice, operacion) in fila.objetos("actions").withIndex()) {
                    BotonHerramienta(estado, fila, operacion, esPrimera = indice == 0, libre = libre)
                }
                if (esHelix && datos.objetos("helixsr_settings").isNotEmpty()) {
                    Boton(t("Settings"), alAjustes, activo = libre, alto = 31.dp, tamano = 12)
                }
            }
        }
    }
}

@Composable
private fun BotonHerramienta(estado: EstadoExtras, fila: JsonObject, operacion: JsonObject, esPrimera: Boolean, libre: Boolean) {
    val clase = when {
        operacion.logico("danger") -> ClaseBoton.PELIGRO
        esPrimera -> ClaseBoton.PRINCIPAL
        else -> ClaseBoton.NORMAL
    }
    Boton(
        texto = operacion.texto("label"),
        alPulsar = { estado.abrir("upscaling", fila, operacion) },
        clase = clase,
        activo = libre && operacion.logico("enabled", defecto = true),
        alto = 31.dp,
        tamano = 12,
        peso = 650,
    )
}

/** Los ajustes de HelixSR: cada uno con el control que le corresponde. */
@Composable
private fun DialogoHelix(estado: EstadoExtras, ajustes: List<JsonObject>, alCerrar: () -> Unit) {
    val cambios = remember { mutableStateMapOf<String, JsonElement>() }
    fun guardar() {
        guardarHelix(estado, cambios.toMap())
        alCerrar()
    }
    Dialogo(alCerrar, ancho = 720.dp) {
        Texto(t("HelixSR settings"), tamano = 17, peso = 800)
        for (ajuste in ajustes) {
            val clave = ajuste.texto("id")
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(14.dp), Alignment.CenterVertically) {
                Texto(ajuste.texto("label"), 13, Modifier.weight(1f))
                ControlHelix(ajuste, cambios[clave]) { valor -> cambios[clave] = valor }
            }
        }
        Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp, Alignment.End)) {
            Boton(t("Cancel"), alCerrar)
            Boton(t("Save"), ::guardar, clase = ClaseBoton.PRINCIPAL, activo = cambios.isNotEmpty())
        }
    }
}

@Composable
private fun ControlHelix(ajuste: JsonObject, cambiado: JsonElement?, alCambiar: (JsonElement) -> Unit) {
    val actual = cambiado ?: ajuste["value"]
    val elecciones = ajuste["choices"] as? JsonArray ?: JsonArray(emptyList())
    when {
        ajuste.texto("kind") == "bool" -> {
            val marcado = actual is JsonPrimitive && actual.content == "true"
            Casilla(marcado, { nuevo -> alCambiar(JsonPrimitive(nuevo)) })
        }
        elecciones.isNotEmpty() -> {
            val opciones = elecciones.map { eleccion -> Eleccion(eleccion.toString(), (eleccion as JsonPrimitive).content) }
            Desplegable(
                opciones = opciones,
                elegida = actual.toString(),
                alElegir = { elegido -> elecciones.firstOrNull { eleccion -> eleccion.toString() == elegido }?.let(alCambiar) },
                modifier = Modifier.width(220.dp),
            )
        }
        else -> CampoNumeroHelix(ajuste, actual, alCambiar)
    }
}

@Composable
private fun CampoNumeroHelix(ajuste: JsonObject, actual: JsonElement?, alCambiar: (JsonElement) -> Unit) {
    var escrito by remember { mutableStateOf((actual as? JsonPrimitive)?.content ?: "") }
    fun escribir(nuevo: String) {
        escrito = nuevo
        val numero = nuevo.replace(',', '.').toDoubleOrNull() ?: return
        val menor = ajuste.numero("min") ?: 0.0
        val mayor = ajuste.numero("max") ?: 1.0
        if (numero in menor..mayor) {
            alCambiar(JsonPrimitive(numero))
        }
    }
    CampoTexto(escrito, ::escribir, Modifier.width(120.dp), alto = 36.dp)
}

internal fun guardarHelix(estado: EstadoExtras, cambios: Map<String, JsonElement>) {
    val parametros = mapOf<String, JsonElement>("values" to JsonObject(cambios))
    estado.aplicacion.preguntarYEjecutar("extras.helixsr_settings", t("HelixSR settings"), parametros = parametros)
}
