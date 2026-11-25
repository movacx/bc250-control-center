package org.bc250.controlcenter.componentes

import androidx.compose.runtime.staticCompositionLocalOf
import org.bc250.controlcenter.tema.Paletas

/** Las paletas disponibles, para las miniaturas de tema y los puntos de acento. */
val LocalPaletas = staticCompositionLocalOf { Paletas() }
