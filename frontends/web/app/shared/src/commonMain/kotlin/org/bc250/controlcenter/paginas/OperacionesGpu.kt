package org.bc250.controlcenter.paginas

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.entero
import org.bc250.controlcenter.datos.logico
import org.bc250.controlcenter.datos.objeto
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto

// Lo que la página de GPU pide al equipo, igual en una pantalla ancha que en un teléfono.

/** Un perfil de fábrica. */
class PerfilGpuOriginal(val nombre: String, val minimo: Int, val maximo: Int)

internal fun perfilGpuOriginal(clave: String): PerfilGpuOriginal {
    return when (clave) {
        "balanced" -> PerfilGpuOriginal("Balanced", 500, 1500)
        "gaming" -> PerfilGpuOriginal("Gaming", 1000, 1850)
        else -> PerfilGpuOriginal("Benchmark", 1000, 2000)
    }
}

/** Revisa un rango en el equipo y, si se acepta, lo aplica. */
internal suspend fun revisarRangoGpu(aplicacion: Aplicacion, minimo: Int, maximo: Int) {
    val revision = aplicacion.consultar("gpu.range", mapOf("min" to minimo.toString(), "max" to maximo.toString()))
    if (revision.isEmpty()) {
        aplicacion.avisar(t("Frequency range"), error = true)
        return
    }
    val parametros = mapOf("min" to JsonPrimitive(minimo), "max" to JsonPrimitive(maximo))
    val peligro = revision.logico("risk")
    aplicacion.preguntarYEjecutar("gpu.profile", revision.texto("title"), revision.texto("message"), parametros, peligro)
}

internal fun guardarArranqueGpu(aplicacion: Aplicacion, datos: JsonObject) {
    val rango = "${datos.entero("current_min")} – ${datos.entero("current_max")} MHz"
    val mensaje = t("Save active range for startup") + "\n" + rango
    aplicacion.preguntarYEjecutar("gpu.save_boot", t("Save for startup"), mensaje)
}

internal fun tituloServicioGpu(accion: String): String {
    return when (accion) {
        "reiniciar" -> t("Restart")
        "desactivar" -> t("Stop governor")
        else -> t("Start governor")
    }
}

/** ``accion`` es "activar", "reiniciar" o "desactivar". */
internal fun pedirServicioGpu(aplicacion: Aplicacion, datos: JsonObject, accion: String) {
    val titulo = tituloServicioGpu(accion)
    val plan = datos.objeto("service_plans").objeto(accion)
    val parametros = mapOf("action" to JsonPrimitive(accion))
    aplicacion.preguntarYEjecutar("gpu.service", titulo, plan.texto("message", titulo), parametros, plan.logico("risk"))
}

internal fun avisoDosGobernadores(): String {
    return t(
        "Only one GPU governor can be enabled at a time. Preparing another governor will ask before stopping the active one.",
    )
}

internal fun cambiarGobernador(aplicacion: Aplicacion, nuevo: String) {
    val parametros = mapOf("value" to JsonPrimitive(nuevo))
    val titulo = t("Switch GPU governor safely")
    aplicacion.preguntarYEjecutar("settings.governor", titulo, avisoDosGobernadores(), parametros, peligro = true)
}

internal fun pedirPuntosAltos(aplicacion: Aplicacion, habilitar: Boolean) {
    val titulo = t(if (habilitar) "Uncomment +2000 MHz points" else "Re-comment the +2000 MHz points")
    val parametros = mapOf("enable" to JsonPrimitive(habilitar))
    aplicacion.preguntarYEjecutar("gpu.high_points", titulo, avisoPuntosAltos(habilitar), parametros, peligro = true)
}

// -- compatibilidad de Cyan ----------------------------------------------------------------------------

/** Cómo lee y controla Cyan la GPU. */
internal data class AjusteCyan(
    val metodo: String,
    val uso: String,
    val temperatura: String,
    val metricas: Boolean,
    val frecuencias: Boolean,
)

internal fun leerAjusteCyan(datos: JsonObject): AjusteCyan {
    val actual = datos.objeto("cyan_telemetry")
    return AjusteCyan(
        metodo = actual.texto("set_method", "smu"),
        uso = actual.texto("method", "busy-flag"),
        temperatura = actual.texto("temp_read", "drm"),
        metricas = actual.logico("fix_metrics", true),
        frecuencias = actual.logico("fix_frequency"),
    )
}

internal fun aplicarCompatibilidad(aplicacion: Aplicacion, ajuste: AjusteCyan) {
    val aviso = t(
        "This validates and updates only gpu.set-method, gpu-usage.fix-metrics and gpu-usage.fix-freq. " +
            "If Cyan is active, its current D-Bus range is read first, the service restarts, and that range is restored.",
    ).replace("gpu.set-method", "gpu.set-method, gpu-usage.method")
    val parametros = mapOf(
        "set_method" to JsonPrimitive(ajuste.metodo),
        "usage_method" to JsonPrimitive(ajuste.uso),
        "metrics" to JsonPrimitive(ajuste.metricas),
        "frequencies" to JsonPrimitive(ajuste.frecuencias),
        "temp_read" to JsonPrimitive(ajuste.temperatura),
    )
    val mensaje = "${ajuste.metodo} · ${ajuste.uso} · ${ajuste.temperatura}\n$aviso"
    val titulo = t("Apply Cyan compatibility settings")
    aplicacion.preguntarYEjecutar("gpu.compat", titulo, mensaje, parametros, peligro = ajuste.metodo == "kernel")
}

internal fun avisoProcess(): String {
    return t(
        "The process reading goes through every open file of every program. With a game open, Cyan " +
            "stops answering: the range, the +2000 MHz points and the voltage lab stop working until the " +
            "game closes. busy-flag is the default.",
    )
}

internal fun avisoSinRespuesta(datos: JsonObject): String {
    if (datos.objeto("cyan_telemetry").texto("method") == "process") {
        return t(
            "Cyan is running but not answering. Its usage reading is set to process, which reads every open " +
                "file of every program; a Proton game keeps tens of thousands open. Choose busy-flag in Cyan " +
                "kernel compatibility and apply.",
        )
    }
    return t(
        "Cyan is running but not answering on D-Bus, so its range cannot be read or changed right now. " +
            "Restart the governor if it does not recover.",
    )
}

// -- voltajes --------------------------------------------------------------------------------------------

/**
 * Pide confirmar una curva: 1 a 3 suman voltaje, 0 vuelve a los de fábrica y -1 usa ``valores``.
 * Sin ``tabla`` se consulta antes. Dice si se pudo preguntar.
 */
internal suspend fun pedirVoltaje(aplicacion: Aplicacion, nivel: Int, valores: JsonObject, tabla: JsonObject): Boolean {
    val propuesta = if (tabla.isEmpty()) aplicacion.consultar("gpu.laboratorio", mapOf("level" to nivel.toString())) else tabla
    if (!propuesta.logico("available")) {
        aplicacion.avisar(propuesta.texto("error", t("Not connected")), error = true)
        return false
    }
    val accion = if (nivel == -1) "gpu.voltage_custom" else "gpu.voltage"
    val parametros = if (nivel == -1) mapOf("values" to valores) else mapOf("level" to JsonPrimitive(nivel))
    val confirmacion = propuesta.objeto("confirmation")
    val mayor = t("peak {value} mV", "value" to propuesta.entero("peak").toString())
    val mensaje = confirmacion.texto("message") + "\n" + mayor
    aplicacion.preguntarYEjecutar(accion, confirmacion.texto("title"), mensaje, parametros, peligro = true)
    return true
}
