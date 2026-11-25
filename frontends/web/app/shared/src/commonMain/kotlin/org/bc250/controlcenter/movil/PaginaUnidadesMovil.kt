package org.bc250.controlcenter.movil

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.LineaDivisoria
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.TextoMono
import org.bc250.controlcenter.componentes.marco
import org.bc250.controlcenter.componentes.pulsable
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.ObjetoVacio
import org.bc250.controlcenter.datos.entero
import org.bc250.controlcenter.datos.logico
import org.bc250.controlcenter.datos.objeto
import org.bc250.controlcenter.datos.objetos
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto
import org.bc250.controlcenter.paginas.EleccionUnidades
import org.bc250.controlcenter.paginas.mascarasCu
import org.bc250.controlcenter.paginas.recordarEleccionUnidades
import org.bc250.controlcenter.tema.ColoresActuales

private const val WGP_POR_FILA = 5
private const val CU_POR_FILA = 10
private const val CU_POR_MOTOR = 20
private const val UNIDADES = 0

private val CambioDeCelda = tween<Color>(140)

@Composable
fun PaginaUnidadesMovil(aplicacion: Aplicacion) {
    val eleccion = recordarEleccionUnidades(aplicacion)
    val movil = movil()
    PaginaMovil("cu", listOf(t("Units"), t("Persistence"))) {
        EstadoLecturaMovil(eleccion.datos)
        if (eleccion.datos.texto("notice").isNotEmpty()) {
            NotaMovil(eleccion.datos.texto("notice"), ColoresActuales.current.naranja, tamano = 13)
        }
        if (movil.pestana("cu") == UNIDADES) {
            if (eleccion.datos.isNotEmpty()) {
                TablaMovil(aplicacion, eleccion)
            }
            LeyendaMovil(eleccion)
            LecturasMovil(eleccion.datos)
        } else {
            PersistenciaUnidades(aplicacion, eleccion)
        }
    }
}

// -- tabla ---------------------------------------------------------------------------------------------

@Composable
private fun TablaMovil(aplicacion: Aplicacion, eleccion: EleccionUnidades) {
    GrupoMovil {
        Column(Modifier.padding(horizontal = 14.dp, vertical = 16.dp), Arrangement.spacedBy(26.dp)) {
            MotorSombreado(eleccion, motor = 0)
            MotorSombreado(eleccion, motor = 1)
            PieDeTabla(aplicacion, eleccion)
        }
    }
}

@Composable
private fun MotorSombreado(eleccion: EleccionUnidades, motor: Int) {
    val filas = listOf(motor * 2, motor * 2 + 1)
    val activas = filas.sumOf { fila -> eleccion.mascaras[fila].countOneBits() * 2 }
    Column(verticalArrangement = Arrangement.spacedBy(11.dp)) {
        TituloConCuenta("SE$motor", 17, "$activas / $CU_POR_MOTOR CU")
        LineaDivisoria(color = ColoresActuales.current.borde)
        Column(verticalArrangement = Arrangement.spacedBy(20.dp)) {
            for (fila in filas) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    val activasFila = eleccion.mascaras[fila].countOneBits() * 2
                    TituloConCuenta("SH${fila % 2}", 14, "$activasFila / $CU_POR_FILA CU")
                    Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(7.dp)) {
                        for (wgp in 0 until WGP_POR_FILA) {
                            CasillaWgp(eleccion, fila, wgp, Modifier.weight(1f))
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun TituloConCuenta(titulo: String, tamano: Int, cuenta: String) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        TextoTitulo(titulo, tamano + 3, Modifier.weight(1f))
        Texto(cuenta, tamano = 14, color = ColoresActuales.current.apagado)
    }
}

private class ColoresWgp(val fondo: Color, val borde: Color, val texto: Color)

@Composable
private fun coloresWgp(token: String, porAplicar: Boolean): ColoresWgp {
    val paleta = ColoresActuales.current
    return when {
        porAplicar -> ColoresWgp(paleta.color("orange_soft"), paleta.naranja, paleta.naranja)
        token == "D+" -> ColoresWgp(paleta.color("green_soft"), paleta.color("green_border"), paleta.verde)
        token == "S+" -> ColoresWgp(paleta.color("cyan_soft"), paleta.color("cyan_border"), paleta.color("cyan"))
        token == "D!" -> ColoresWgp(paleta.rojoSuave, paleta.rojoBorde, paleta.rojo)
        else -> ColoresWgp(paleta.panelAlterno, paleta.borde, paleta.textoInactivo)
    }
}

@Composable
private fun CasillaWgp(eleccion: EleccionUnidades, fila: Int, wgp: Int, modifier: Modifier) {
    val celda = eleccion.seleccion.objetos("rows").getOrNull(fila)?.objetos("cells")?.getOrNull(wgp) ?: ObjetoVacio
    val token = celda.texto("token", "--")
    val porAplicar = (eleccion.mascaras[fila] xor eleccion.vivas[fila]) and (1 shl wgp) != 0
    val destino = coloresWgp(token, porAplicar)
    val fondo by animateColorAsState(destino.fondo, CambioDeCelda)
    val borde by animateColorAsState(destino.borde, CambioDeCelda)
    val letra by animateColorAsState(destino.texto, CambioDeCelda)
    Column(
        modifier = modifier
            .height(78.dp)
            .drawBehind {
                val radio = CornerRadius(9.dp.toPx())
                drawRoundRect(fondo, cornerRadius = radio)
                drawRoundRect(borde, cornerRadius = radio, style = Stroke(1.dp.toPx()))
            }
            .pulsable(eleccion.editable) { eleccion.alternar(fila, wgp) },
        verticalArrangement = Arrangement.spacedBy(4.dp, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Texto("WGP $wgp", tamano = 11, peso = 500, color = ColoresActuales.current.apagado, lineas = 1)
        TextoTitulo(token, 22, color = letra)
        Texto("${wgp * 2}–${wgp * 2 + 1}", tamano = 11, color = letra)
    }
}

@Composable
private fun PieDeTabla(aplicacion: Aplicacion, eleccion: EleccionUnidades) {
    val paleta = ColoresActuales.current
    val seleccion = eleccion.seleccion
    val pendientes = seleccion.entero("pending")
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        LineaDivisoria()
        if (pendientes > 0) {
            Texto(textoPendiente(eleccion), tamano = 14, peso = 500, color = paleta.naranja)
        }
        if (!seleccion.logico("balanced", true)) {
            Texto(seleccion.texto("balance_detail"), tamano = 13, color = paleta.apagado)
        }
        if (!seleccion.logico("balanced", true)) {
            BotonMovil(t("Balance shader engines"), Modifier.fillMaxWidth(), activo = eleccion.libre && !eleccion.delKernel) {
                eleccion.elegir(mascarasCu(seleccion, "balanced_masks"))
            }
        }
        ParejaBotones {
            BotonMovil(t("Reset selection"), Modifier.weight(1f), activo = eleccion.permite("discard")) { eleccion.restablecer() }
            BotonMovil(t("Review and apply"), Modifier.weight(1f), ClaseBoton.PRINCIPAL, eleccion.permite("apply_live")) {
                eleccion.operarTabla(guardar = false)
            }
        }
        BotonMovil(t("Unlock / Sync"), Modifier.fillMaxWidth(), activo = eleccion.libre) {
            aplicacion.preguntarYEjecutar("cu.sync", t("Unlock / Sync"))
        }
        PrepararHerramientas(aplicacion, eleccion)
    }
}

private fun textoPendiente(eleccion: EleccionUnidades): String {
    val pendientes = eleccion.seleccion.entero("pending")
    return when {
        !eleccion.datos.objeto("presentation").logico("verified") -> t("Authorize a live refresh before applying WGP changes.")
        !eleccion.estado.logico("privileged_backend_ready") ->
            t("CU write actions are locked until a verified root-owned backend is installed.")
        pendientes > 0 -> t("{pairs} differ from the last authorized live table.", "pairs" to pendientes.toString())
        else -> t("No pending WGP changes.")
    }
}

@Composable
private fun PrepararHerramientas(aplicacion: Aplicacion, eleccion: EleccionUnidades) {
    if (eleccion.estado.logico("privileged_backend_ready") || eleccion.delKernel || eleccion.datos.isEmpty()) {
        return
    }
    NotaMovil(eleccion.estado.texto("privileged_backend_reason"), ColoresActuales.current.naranja)
    BotonMovil(t("Prepare Compute Units tools"), Modifier.fillMaxWidth(), activo = eleccion.libre) {
        aplicacion.preguntarYEjecutar(
            "cu.prepare",
            t("Prepare Compute Units tools"),
            t(
                "The existing distribution-specific dependency workflow will prepare UMR and bc250-cu-live-manager. " +
                    "Package installation may open a visible terminal and request administrator authentication.",
            ),
        )
    }
}

@Composable
private fun LeyendaMovil(eleccion: EleccionUnidades) {
    val paleta = ColoresActuales.current
    val leyenda = listOf(
        "D+ " + t("Driver + routed") to paleta.verde,
        "S+ " + t("Live unlock") to paleta.color("cyan"),
        "D! " + t("Driver blocked") to paleta.rojo,
        "-- " + t("Not routed") to paleta.sutil,
    )
    val presentes = eleccion.seleccion.objetos("rows").flatMap { fila -> fila.objetos("cells") }.map { celda -> celda.texto("token") }.toSet()
    for (pareja in leyenda.filter { (texto, _) -> texto.take(2) in presentes }.chunked(2)) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 2.dp)) {
            for ((texto, color) in pareja) {
                Texto(texto, tamano = 13, color = color, modifier = Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun LecturasMovil(datos: JsonObject) {
    SeccionMovil(t("Readings")) {
        GrupoMovil {
            for (lectura in datos.objetos("telemetry")) {
                FilaDato(lectura.texto("label"), lectura.texto("value"))
            }
        }
    }
}

// -- persistencia ----------------------------------------------------------------------------------------

@Composable
private fun PersistenciaUnidades(aplicacion: Aplicacion, eleccion: EleccionUnidades) {
    val movil = movil()
    val paleta = ColoresActuales.current
    val lecturas = eleccion.datos.objetos("telemetry")
    GrupoMovil {
        for (lectura in lecturas.take(2)) {
            FilaDato(lectura.texto("label"), lectura.texto("value"))
        }
        FilaDato(t("In use now"), "${eleccion.vivas.sumOf { mascara -> mascara.countOneBits() * 2 }} / 40", "CU")
    }
    SeccionMovil(t("Boot persistence")) {
        GrupoMovil {
            FilaAbrir(t("Save selection"), activa = eleccion.permite("save_boot")) { eleccion.operarTabla(guardar = true) }
            FilaAbrir(t("Install service"), activa = eleccion.permite("install_service")) {
                eleccion.operarServicio("install_service", "Install service")
            }
            FilaAbrir(t("Apply saved"), activa = eleccion.permite("apply_saved")) {
                eleccion.operarServicio("apply_saved", "Apply saved boot layout now")
            }
        }
        GrupoMovil {
            FilaAbrir(t("Raw status")) { aplicacion.ejecutar("cu.raw", t("Compute Units raw status")) }
            FilaAbrir(t("Registers")) { movil.abrirHoja { HojaRegistros(eleccion.seleccion) } }
            FilaAbrir(t("Validate CUs")) { movil.abrirHoja { HojaGuia(eleccion.datos.objeto("guide")) } }
        }
        GrupoMovil {
            FilaAbrir(t("Restore factory"), activa = eleccion.permite("restore_factory")) {
                eleccion.operarServicio("factory_repair", "Restore factory", peligro = true)
            }
            FilaAbrir(t("Remove service"), colorTitulo = paleta.rojo, activa = eleccion.permite("remove_service")) {
                eleccion.operarServicio("remove_service", "Remove service", peligro = true)
            }
        }
    }
}

@Composable
private fun HojaRegistros(seleccion: JsonObject) {
    val columnas = listOf("name" to "Shader row", "live" to "Live SPI", "target" to "Target SPI", "driver" to "Driver map", "cc" to "CC harvest")
    val paleta = ColoresActuales.current
    TituloHoja(t("Register diagnostics"))
    TextoHoja(t("Read-only register values and the pending SPI target."))
    GrupoMovil {
        Column(Modifier.horizontalScroll(rememberScrollState()).background(paleta.panel)) {
            FilaRegistro(columnas.map { (_, titulo) -> t(titulo) }, titulo = true)
            for (fila in seleccion.objetos("rows")) {
                FilaRegistro(columnas.map { (clave, _) -> fila.texto(clave) }, titulo = false)
            }
        }
    }
    CerrarHoja()
}

@Composable
private fun FilaRegistro(celdas: List<String>, titulo: Boolean) {
    Row(Modifier.padding(horizontal = 14.dp, vertical = 9.dp)) {
        for (celda in celdas) {
            Box(Modifier.width(104.dp)) {
                if (titulo) {
                    Texto(celda, tamano = 12, peso = 700, color = ColoresActuales.current.apagado)
                } else {
                    TextoMono(celda, tamano = 12, color = ColoresActuales.current.texto)
                }
            }
        }
    }
}

@Composable
private fun HojaGuia(guia: JsonObject) {
    TituloHoja(guia.texto("title"))
    TextoHoja(guia.texto("message"))
    NotaMovil(guia.texto("detail"))
    CerrarHoja()
}
