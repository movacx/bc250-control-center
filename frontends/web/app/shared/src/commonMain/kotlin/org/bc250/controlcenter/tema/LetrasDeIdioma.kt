package org.bc250.controlcenter.tema

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.platform.LocalFontFamilyResolver
import androidx.compose.ui.text.font.FontFamily
import org.bc250.controlcenter.recursos.Res
import org.bc250.controlcenter.recursos.letra_ja
import org.bc250.controlcenter.recursos.letra_ko
import org.bc250.controlcenter.recursos.letra_nombres
import org.bc250.controlcenter.recursos.letra_th
import org.bc250.controlcenter.recursos.letra_zh_cn
import org.bc250.controlcenter.recursos.letra_zh_tw
import org.jetbrains.compose.resources.Font
import org.jetbrains.compose.resources.FontResource

/** Los alfabetos que Noto Sans no trae: el del idioma elegido y los nombres del selector. */
@Composable
fun CargarLetrasDeIdioma(idioma: String, alCargar: () -> Unit) {
    CargarLetra(Res.font.letra_th, alCargar)
    CargarLetra(Res.font.letra_nombres, alCargar)
    when (idioma) {
        "ja" -> CargarLetra(Res.font.letra_ja, alCargar)
        "ko" -> CargarLetra(Res.font.letra_ko, alCargar)
        "zh-CN" -> CargarLetra(Res.font.letra_zh_cn, alCargar)
        "zh-TW" -> CargarLetra(Res.font.letra_zh_tw, alCargar)
    }
}

/** Queda como letra de repuesto para los caracteres que falten. */
@Composable
private fun CargarLetra(recurso: FontResource, alCargar: () -> Unit) {
    val letra = Font(recurso)
    val letras = LocalFontFamilyResolver.current
    LaunchedEffect(letra) {
        letras.preload(FontFamily(letra))
        alCargar()
    }
}
