package org.bc250.controlcenter.tema

import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import org.bc250.controlcenter.recursos.Res
import org.bc250.controlcenter.recursos.cifras_bold
import org.bc250.controlcenter.recursos.cifras_medium
import org.bc250.controlcenter.recursos.jetbrainsmono_bold
import org.bc250.controlcenter.recursos.jetbrainsmono_regular
import org.bc250.controlcenter.recursos.notosans_black
import org.bc250.controlcenter.recursos.notosans_bold
import org.bc250.controlcenter.recursos.notosans_medium
import org.bc250.controlcenter.recursos.notosans_regular
import org.jetbrains.compose.resources.Font

/** La letra de los textos, la de la consola y la estrecha de los títulos y las cifras del teléfono. */
class Letras(val normal: FontFamily, val consola: FontFamily, val cifras: FontFamily)

val LetrasActuales = staticCompositionLocalOf { Letras(FontFamily.SansSerif, FontFamily.Monospace, FontFamily.SansSerif) }

@Composable
fun cargarLetras(): Letras {
    val normal = FontFamily(
        Font(Res.font.notosans_regular, FontWeight.Normal),
        Font(Res.font.notosans_medium, FontWeight.Medium),
        Font(Res.font.notosans_bold, FontWeight.Bold),
        Font(Res.font.notosans_black, FontWeight.Black),
    )
    val consola = FontFamily(
        Font(Res.font.jetbrainsmono_regular, FontWeight.Normal),
        Font(Res.font.jetbrainsmono_bold, FontWeight.Bold),
    )
    val cifras = FontFamily(
        Font(Res.font.cifras_medium, FontWeight.Medium),
        Font(Res.font.cifras_bold, FontWeight.Bold),
    )
    return remember(normal, consola, cifras) { Letras(normal, consola, cifras) }
}

/** El grosor de Qt (400 a 900) llevado al archivo de letra que Qt elige para él. */
fun grosor(peso: Int): FontWeight {
    return when {
        peso <= 450 -> FontWeight.Normal
        peso <= 600 -> FontWeight.Medium
        peso <= 800 -> FontWeight.Bold
        else -> FontWeight.Black
    }
}

/** El alto de línea que Qt da a Noto Sans para cada tamaño. */
fun altoDeLinea(tamano: Int): Int {
    return when (tamano) {
        9 -> 13
        10 -> 14
        11 -> 15
        12 -> 17
        13 -> 18
        14 -> 20
        15 -> 21
        16 -> 22
        17 -> 23
        18 -> 25
        19 -> 26
        20 -> 27
        else -> (tamano * 1.362f + 0.5f).toInt()
    }
}
