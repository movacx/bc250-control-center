package org.bc250.controlcenter

import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts.PickVisualMedia
import androidx.activity.result.contract.ActivityResultContracts.RequestPermission
import org.bc250.controlcenter.datos.BarraDelSistema
import org.bc250.controlcenter.datos.BotonAtras
import org.bc250.controlcenter.datos.abridorDeDirecciones
import org.bc250.controlcenter.datos.abridorDeGaleria
import org.bc250.controlcenter.datos.prepararAlmacen
import org.bc250.controlcenter.datos.recibirImagen

private const val PERMISO_DE_RED = "android.permission.ACCESS_LOCAL_NETWORK"
private const val ANDROID_CON_PERMISO_DE_RED = 37

class MainActivity : ComponentActivity() {

    private val galeria = registerForActivityResult(PickVisualMedia()) { direccion ->
        if (direccion != null) {
            recibirImagen(this, direccion)
        }
    }

    private val permisoDeRed = registerForActivityResult(RequestPermission()) {
        dibujar()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        ponerBarras(claro = false)
        BarraDelSistema.alCambiarTema = ::ponerBarras
        prepararAlmacen(applicationContext)
        abridorDeDirecciones = ::abrirEnElNavegador
        abridorDeGaleria = { galeria.launch(PickVisualMediaRequest(PickVisualMedia.ImageOnly)) }
        onBackPressedDispatcher.addCallback(this, atras)
        if (faltaPermisoDeRed()) {
            permisoDeRed.launch(PERMISO_DE_RED)
        } else {
            dibujar()
        }
    }

    private fun dibujar() {
        setContent {
            App()
        }
    }

    private fun faltaPermisoDeRed(): Boolean {
        val loExige = Build.VERSION.SDK_INT >= ANDROID_CON_PERMISO_DE_RED
        return loExige && checkSelfPermission(PERMISO_DE_RED) != PackageManager.PERMISSION_GRANTED
    }

    /** Las barras del sistema son transparentes; sus iconos contrastan con el tema de la aplicación. */
    private fun ponerBarras(claro: Boolean) {
        val barra = if (claro) SystemBarStyle.light(Color.TRANSPARENT, Color.TRANSPARENT) else SystemBarStyle.dark(Color.TRANSPARENT)
        enableEdgeToEdge(barra, barra)
    }

    /** Atrás cierra primero lo que esté abierto; si no hay nada, la aplicación queda en segundo plano. */
    private val atras = object : OnBackPressedCallback(true) {
        override fun handleOnBackPressed() {
            if (!BotonAtras.atender()) {
                moveTaskToBack(true)
            }
        }
    }

    private fun abrirEnElNavegador(direccion: String) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(direccion)))
        } catch (error: ActivityNotFoundException) {
            // Sin navegador no hay nada que abrir.
        }
    }
}
