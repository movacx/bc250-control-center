package org.bc250.controlcenter.tema

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalFontFamilyResolver
import androidx.compose.ui.text.font.FontFamily
import kotlinx.coroutines.delay
import org.bc250.controlcenter.recursos.Res
import org.bc250.controlcenter.recursos.letra_ja
import org.bc250.controlcenter.recursos.letra_ko
import org.bc250.controlcenter.recursos.letra_nombres
import org.bc250.controlcenter.recursos.letra_th
import org.bc250.controlcenter.recursos.letra_zh_cn
import org.bc250.controlcenter.recursos.letra_zh_tw
import org.jetbrains.compose.resources.Font
import org.jetbrains.compose.resources.FontResource

/** Si la red falla no se espera más: los signos que falten se verán como cuadros. */
private const val ESPERA_MAXIMA = 6000L

private fun letraDe(idioma: String): FontResource? {
    return when (idioma) {
        "ja" -> Res.font.letra_ja
        "ko" -> Res.font.letra_ko
        "zh-CN" -> Res.font.letra_zh_cn
        "zh-TW" -> Res.font.letra_zh_tw
        "th" -> Res.font.letra_th
        else -> null
    }
}

/**
 * Los alfabetos que Noto Sans no trae. Contesta si ya se puede dibujar en este idioma: un signo
 * dibujado antes de que llegue su letra se quedaría como un cuadro para siempre.
 */
@Composable
fun letrasListas(idioma: String): Boolean {
    cargarLetra(Res.font.letra_nombres)
    val propia = letraDe(idioma) ?: return true
    return key(idioma) { cargarLetra(propia) }
}

/** Deja la letra como repuesto de los signos que falten. */
@Composable
private fun cargarLetra(recurso: FontResource): Boolean {
    val letra = Font(recurso)
    val provisional = remember { letra }
    val letras = LocalFontFamilyResolver.current
    var lista by remember { mutableStateOf(false) }
    LaunchedEffect(letra) {
        if (letra !== provisional) {
            letras.preload(FontFamily(letra))
            lista = true
        } else {
            delay(ESPERA_MAXIMA)
            lista = true
        }
    }
    return lista
}
