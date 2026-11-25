package org.bc250.controlcenter.movil

import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.unit.dp

/** Por debajo de este ancho se usa el diseño de teléfono. */
val AnchoMovil = 600.dp

/** Lo que una ventana inferior muestra. */
typealias ContenidoHoja = @Composable ColumnScope.() -> Unit

/** Lo que el teléfono recuerda mientras está abierto: pestañas, menú, detalle y ventana inferior. */
class EstadoMovil {
    var menuAbierto by mutableStateOf(false)

    /** El título de la pantalla de detalle; vacío cuando se ve la página. */
    var detalle by mutableStateOf("")
        private set

    var hoja by mutableStateOf<ContenidoHoja?>(null)
        private set

    private val pestanas = mutableStateMapOf<String, Int>()

    fun pestana(pagina: String): Int {
        return pestanas[pagina] ?: 0
    }

    fun elegirPestana(pagina: String, indice: Int) {
        pestanas[pagina] = indice
    }

    fun abrirDetalle(titulo: String) {
        detalle = titulo
    }

    fun cerrarDetalle() {
        detalle = ""
    }

    fun abrirHoja(contenido: ContenidoHoja) {
        hoja = contenido
    }

    fun cerrarHoja() {
        hoja = null
    }

    /** Vuelve un paso; dice si había algo que cerrar. */
    fun volver(): Boolean {
        when {
            hoja != null -> cerrarHoja()
            menuAbierto -> menuAbierto = false
            detalle.isNotEmpty() -> cerrarDetalle()
            else -> return false
        }
        return true
    }

    fun alCambiarDePagina() {
        menuAbierto = false
        cerrarDetalle()
        cerrarHoja()
    }
}

/** El estado del teléfono, o nada en una pantalla ancha. */
val LocalMovil = staticCompositionLocalOf<EstadoMovil?> { null }

/** El estado del teléfono desde una página que solo existe en él. */
@Composable
fun movil(): EstadoMovil {
    return checkNotNull(LocalMovil.current)
}

/** Si la pantalla es de teléfono; las ventanas sueltas suben entonces desde abajo. */
val LocalTelefono = staticCompositionLocalOf { false }
