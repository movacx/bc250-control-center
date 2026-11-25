package org.bc250.controlcenter.paginas

import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.*
import org.bc250.controlcenter.componentes.*
import org.bc250.controlcenter.datos.*
import org.bc250.controlcenter.recursos.Res
import org.bc250.controlcenter.recursos.chevron_down_gray
import org.bc250.controlcenter.recursos.chevron_right_gray
import org.bc250.controlcenter.tema.*

internal fun mascarasCu(datos: JsonObject, clave: String): List<Int> {
    val valores = datos.lista(clave).map { (it as? JsonPrimitive)?.content?.toIntOrNull() ?: 0 }
    return if (valores.size == 4) valores else listOf(0, 0, 0, 0)
}

@Composable
fun PaginaUnidades(aplicacion: Aplicacion) {
    val tareas = rememberCoroutineScope()
    val datos = aplicacion.lectura("cu")
    val estado = datos.objeto("cu")
    val paleta = ColoresActuales.current
    var valores by remember { mutableStateOf(listOf(0, 0, 0, 0)) }
    var editado by remember { mutableStateOf(false) }
    var seleccion by remember { mutableStateOf(ObjetoVacio) }
    var consultando by remember { mutableStateOf(false) }
    var registros by remember { mutableStateOf(false) }
    var guia by remember { mutableStateOf(false) }
    var trabajoAnterior by remember { mutableStateOf(aplicacion.trabajo.id) }
    val libre = aplicacion.puedeControlar && aplicacion.trabajo.terminado && datos.isNotEmpty() && datos.texto("error").isEmpty()
    val kernel = estado.logico("kernel_managed")
    val disponibilidad = seleccion.objeto("availability")

    LaunchedEffect(aplicacion) {
        while (true) {
            aplicacion.leerPagina("cu")
            delay(3000)
        }
    }
    LaunchedEffect(estado, aplicacion.trabajo.id, aplicacion.trabajo.terminado) {
        if (aplicacion.trabajo.id != trabajoAnterior && aplicacion.trabajo.terminado) {
            editado = false
            trabajoAnterior = aplicacion.trabajo.id
        }
        if (!editado || kernel) {
            valores = mascarasCu(estado, "masks")
            seleccion = datos.objeto("selection")
        }
    }
    LaunchedEffect(valores, estado) {
        consultando = true
        delay(100)
        val resultado = aplicacion.consultar("cu.selection", mapOf("masks" to JsonArray(valores.map { JsonPrimitive(it) }).toString()))
        if (resultado.isNotEmpty()) seleccion = resultado
        consultando = false
    }
    fun elegir(nuevos: List<Int>) {
        valores = nuevos
        editado = true
        consultando = true
    }
    fun alternar(fila: Int, wgp: Int) {
        elegir(valores.mapIndexed { indice, valor -> if (indice == fila) valor xor (1 shl wgp) else valor })
    }
    fun restablecer() {
        editado = false
        valores = mascarasCu(estado, "masks")
        seleccion = datos.objeto("selection")
    }
    fun operar(accion: String, titulo: String, parametros: Map<String, JsonElement> = emptyMap(), peligro: Boolean = false) {
        val clave = if (accion == "cu.apply") "apply" else if (accion == "cu.save") "save"
            else (parametros["name"] as? JsonPrimitive)?.content ?: ""
        val texto = datos.objeto("confirmations").objeto(clave)
        aplicacion.preguntarYEjecutar(accion, texto.texto("title", t(titulo)),
            texto.texto("message") + "\n" + seleccion.texto("summary"), parametros, peligro)
    }
    fun operarTabla(guardar: Boolean) {
        operar(if (guardar) "cu.save" else "cu.apply", if (guardar) "Save selection" else "Apply now",
            mapOf("masks" to JsonArray(valores.map { JsonPrimitive(it) })), peligro = true)
    }
    fun accionServicio(nombre: String, titulo: String, peligro: Boolean = false) {
        operar("cu.action", titulo, mapOf("name" to JsonPrimitive(nombre)), peligro)
    }

    Box(Modifier.fillMaxSize()) {
        PaginaDesplazable(margen = PaddingValues(start = 18.dp, top = 8.dp, end = 18.dp, bottom = 24.dp), espacio = MedidasGpuCu.espacio) {
            EstadoLecturaGpuCu(aplicacion, datos.texto("error"), datos.isEmpty()) {
                tareas.launch { aplicacion.leerPagina("cu") }
            }
            if (datos.texto("notice").isNotEmpty()) SubPanel { Texto(datos.texto("notice"), color = paleta.naranja, tamano = 13) }
            TarjetaPagina(Modifier.fillMaxWidth(), espacio = 12.dp) {
                LeyendaUnidades()
                TablaUnidades(seleccion.objetos("rows"), libre && !kernel, ::alternar)
                if (registros) {
                    RegistrosUnidades(seleccion.objetos("rows"))
                    Boton(t("Apply saved"), { accionServicio("apply_saved", "Apply saved boot layout now") },
                        activo = libre && disponibilidad.logico("apply_saved") && !consultando)
                    Boton(t("Validate CUs"), { guia = true })
                }
            }
            RejillaGpuCu(2, 2, umbral = 1080.dp, separacion = 14.dp) { indice, modificador ->
                if (indice == 0) {
                    TarjetaPagina(modificador, espacio = 12.dp) {
                        SubPanel(margen = PaddingValues(13.dp, 10.dp), espacio = 8.dp, fondo = paleta.panelAlterno, borde = paleta.bordeSuave) {
                            val verificado = datos.objeto("presentation").logico("verified")
                            Column(verticalArrangement = Arrangement.spacedBy(1.dp)) {
                                Texto(if (verificado) t("Target: {count} / 40 CUs", "count" to seleccion.entero("target").toString()) else t("Target: Not verified"),
                                    tamano = 13, peso = 830)
                                val detalle = when {
                                    !verificado -> t("Authorize a live refresh before applying WGP changes.")
                                    !estado.logico("privileged_backend_ready") -> t("CU write actions are locked until a verified root-owned backend is installed.")
                                    seleccion.entero("pending") > 0 -> t("{pairs} differ from the last authorized live table.", "pairs" to seleccion.entero("pending").toString())
                                    else -> t("No pending WGP changes.")
                                }
                                Texto(detalle, tamano = 10, color = paleta.apagado)
                                Texto(seleccion.texto("balance_detail"), tamano = 10, color = paleta.apagado)
                            }
                            if (!seleccion.logico("balanced", true)) {
                                Boton(t("Balance shader engines"), {
                                    elegir(mascarasCu(seleccion, "balanced_masks"))
                                }, activo = libre && !kernel && !consultando)
                            }
                            RejillaGpuCu(3, 3, umbral = 550.dp) { boton, caja ->
                                when (boton) {
                                    0 -> Boton(t("Unlock / Sync"), {
                                        aplicacion.preguntarYEjecutar("cu.sync", t("Unlock / Sync"))
                                    }, caja, activo = libre)
                                    1 -> Boton(t("Reset selection"), ::restablecer, caja,
                                        activo = libre && disponibilidad.logico("discard") && !consultando)
                                    else -> Boton(t("Apply now"), { operarTabla(false) }, caja, ClaseBoton.PRINCIPAL,
                                        activo = libre && disponibilidad.logico("apply_live") && !consultando)
                                }
                            }
                        }
                        SubPanel(margen = PaddingValues(12.dp, 10.dp), espacio = 7.dp, fondo = paleta.panelAlterno, borde = paleta.bordeSuave) {
                            Texto(t("Boot persistence"), tamano = 11, peso = 700, color = paleta.apagado)
                            Texto(t("Select the WGP pairs above, then use the buttons below in order — Apply now, Save selection, Install service — to make the change survive a reboot."),
                                tamano = 10, color = paleta.sutil)
                            RejillaGpuCu(6, 3, umbral = 550.dp, separacion = 8.dp) { boton, caja ->
                                when (boton) {
                                    0 -> Boton(t("Save selection"), { operarTabla(true) }, caja, alto = 39.dp,
                                        activo = libre && disponibilidad.logico("save_boot") && !consultando)
                                    1 -> Boton(t("Install service"), { accionServicio("install_service", "Install service") }, caja, alto = 39.dp,
                                        activo = libre && disponibilidad.logico("install_service") && !consultando)
                                    2 -> Boton(t("Remove service"), { accionServicio("remove_service", "Remove service", true) }, caja, clase = ClaseBoton.PELIGRO_SUAVE, alto = 39.dp,
                                        activo = libre && disponibilidad.logico("remove_service") && !consultando)
                                    3 -> Boton(t("Restore factory"), { accionServicio("factory_repair", "Restore factory", true) }, caja, alto = 39.dp,
                                        activo = libre && disponibilidad.logico("restore_factory") && !consultando)
                                    4 -> Boton(t("Raw status"), { aplicacion.ejecutar("cu.raw", t("Compute Units raw status")) }, caja, alto = 39.dp)
                                    else -> Boton(t(if (registros) "Hide registers" else "Show registers"), { registros = !registros }, caja, alto = 39.dp, icono = if (registros) Res.drawable.chevron_down_gray else Res.drawable.chevron_right_gray)
                                }
                            }
                        }
                        Texto(t("Live routing is temporary until the current table is saved and the boot service is installed. One WGP always represents two CUs; individual CUs cannot be toggled separately."),
                            tamano = 10, color = paleta.sutil)
                        if (!estado.logico("privileged_backend_ready") && !kernel) {
                            Texto(estado.texto("privileged_backend_reason"), tamano = 12, color = paleta.naranja)
                            Boton(t("Prepare Compute Units tools"), {
                                aplicacion.preguntarYEjecutar("cu.prepare", t("Prepare Compute Units tools"),
                                    t("The existing distribution-specific dependency workflow will prepare UMR and bc250-cu-live-manager. Package installation may open a visible terminal and request administrator authentication."))
                            }, activo = libre)
                        }
                    }
                } else {
                    TarjetaPagina(modificador, margen = PaddingValues(20.dp, 18.dp)) {
                        SubPanel(margen = PaddingValues(8.dp), espacio = 8.dp, fondo = paleta.panel, borde = paleta.borde) {
                            val lecturas = datos.objetos("telemetry")
                            RejillaGpuCu(lecturas.size, 2, umbral = 450.dp) { numero, caja ->
                                val lectura = lecturas[numero]
                                SubPanel(caja.heightIn(min = 76.dp), margen = PaddingValues(14.dp, 10.dp), espacio = 1.dp,
                                    fondo = paleta.panelAlterno, borde = paleta.bordeSuave) {
                                    Texto(lectura.texto("label"), tamano = 10, peso = 700, color = paleta.apagado)
                                    Texto(lectura.texto("value"), tamano = 16, peso = 800)
                                    Texto(lectura.texto("detail"), tamano = 10, color = paleta.sutil)
                                }
                            }
                        }
                    }
                }
            }
        }
        if (guia) Dialogo({ guia = false }, ancho = 820.dp) {
            val contenido = datos.objeto("guide")
            Texto(contenido.texto("title"), tamano = 18, peso = 800)
            Texto(contenido.texto("message"), tamano = 13)
            Texto(contenido.texto("detail"), tamano = 12, color = paleta.apagado)
            Boton(t("Close"), { guia = false })
        }
    }
}
