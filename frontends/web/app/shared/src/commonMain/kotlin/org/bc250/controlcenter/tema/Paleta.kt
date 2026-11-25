package org.bc250.controlcenter.tema

import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

/**
 * Los colores de un tema. Son los mismos nombres y valores que usa el escritorio:
 * el servidor los envía y aquí solo se leen.
 */
class Paleta(private val colores: Map<String, String>, val esClaro: Boolean) {

    /** La misma paleta con otros colores de consola. */
    fun conTerminal(consola: Map<String, String>): Paleta {
        return if (consola.isEmpty()) this else Paleta(colores + consola, esClaro)
    }

    /** El color con ese nombre; si falta, uno muy visible para notarlo. */
    fun color(nombre: String): Color {
        val texto = colores[nombre]
        if (texto == null) {
            return Color.Magenta
        }
        return leerColor(texto)
    }

    val ventana: Color get() = color("window")
    val panel: Color get() = color("panel")
    val panelAlterno: Color get() = color("panel_alt")
    val panelElevado: Color get() = color("panel_raised")
    val control: Color get() = color("control")
    val controlEncima: Color get() = color("control_hover")
    val borde: Color get() = color("border")
    val bordeSuave: Color get() = color("border_soft")
    val bordeFuerte: Color get() = color("border_strong")
    val texto: Color get() = color("text")
    val apagado: Color get() = color("muted")
    val sutil: Color get() = color("subtle")
    val fondoInactivo: Color get() = color("disabled_bg")
    val textoInactivo: Color get() = color("disabled_text")
    val acento: Color get() = color("blue")
    val acentoSuave: Color get() = color("blue_soft")
    val acentoBorde: Color get() = color("blue_border")
    val acentoEncima: Color get() = color("blue_hover")
    val sobreAcento: Color get() = color("on_blue")
    val rojo: Color get() = color("red")
    val rojoSuave: Color get() = color("red_soft")
    val rojoBorde: Color get() = color("red_border")
    val verde: Color get() = color("green")
    val naranja: Color get() = color("orange")
    val pista: Color get() = color("progress_track")

    /** El relleno de un grupo dentro de una tarjeta. */
    val grupo: Color get() = panelElevado

    /** Los colores sólidos de las acciones, oscurecidos para que el texto blanco se lea. */
    val peligroSolido: Color get() = mezclar(rojo, Color.Black, 0.25f)
    val exitoSolido: Color get() = mezclar(verde, Color.Black, 0.32f)

    /** El fondo de la opción elegida dentro de un grupo. */
    val elegido: Color get() = if (esClaro) acentoSuave else mezclar(grupo, acento, 0.14f)

    /** La línea de un panel de riesgo. */
    val bordeRiesgo: Color get() = if (esClaro) rojoBorde else mezclar(borde, rojo, 0.55f)
}

/** Mezcla dos colores; con 0 queda el primero y con 1 el segundo. */
fun mezclar(base: Color, encima: Color, cantidad: Float): Color {
    val resto = 1f - cantidad
    return Color(
        red = base.red * resto + encima.red * cantidad,
        green = base.green * resto + encima.green * cantidad,
        blue = base.blue * resto + encima.blue * cantidad,
    )
}

/** Un color escrito como #RRGGBB. */
fun leerColor(texto: String): Color {
    val numero = texto.removePrefix("#").toLongOrNull(16)
    if (numero == null) {
        return Color.Magenta
    }
    return Color(0xFF000000 or numero)
}

/** Los colores de respaldo mientras el servidor responde: los del tema oscuro verde. */
val PaletaInicial = Paleta(
    mapOf(
        "window" to "#0F0F0F", "panel" to "#171717", "panel_alt" to "#1F1F1F", "panel_raised" to "#242424",
        "control" to "#242424", "control_hover" to "#2C2C2C", "border" to "#343434", "border_soft" to "#292929",
        "border_strong" to "#4A4A4A", "text" to "#F2F2F2", "muted" to "#B9B9B9", "subtle" to "#9D9D9D",
        "disabled_bg" to "#292929", "disabled_text" to "#707070", "blue" to "#69B486", "blue_soft" to "#1A2B21",
        "blue_border" to "#395946", "blue_hover" to "#78BC92", "on_blue" to "#FFFFFF", "red" to "#F0827B",
        "red_soft" to "#352625", "red_border" to "#724441", "green" to "#80C198", "orange" to "#E3A673",
        "progress_track" to "#2A2A2A", "focus" to "#86A8DA", "console_bg" to "#0A0A0A",
        "console_text" to "#E6E6E6", "console_border" to "#333333", "scrollbar" to "#424242",
        "scrollbar_hover" to "#5A5A5A", "scrim" to "#000000",
    ),
    esClaro = false,
)

val ColoresActuales = staticCompositionLocalOf { PaletaInicial }
