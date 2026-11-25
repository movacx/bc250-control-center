package org.bc250.controlcenter.datos

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.first

/** Si la aplicación se está viendo. Escondida no pide nada: ni batería ni trabajo para el equipo. */
object PrimerPlano {
    val visible = MutableStateFlow(true)

    suspend fun esperar() {
        visible.first { seVe -> seVe }
    }
}

/** Avisa a [PrimerPlano] cuando la plataforma esconde o enseña la aplicación. */
expect fun vigilarPrimerPlano()
