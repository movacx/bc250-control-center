package org.bc250.controlcenter.paginas

import androidx.compose.runtime.Composable
import org.bc250.controlcenter.componentes.PaginaPendiente
import org.bc250.controlcenter.datos.Aplicacion

@Composable
fun PaginaConfiguracion(aplicacion: Aplicacion) {
    PaginaPendiente(aplicacion.pagina)
}
