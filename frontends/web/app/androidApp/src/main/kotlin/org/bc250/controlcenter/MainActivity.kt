package org.bc250.controlcenter

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import org.bc250.controlcenter.datos.abridorDeDirecciones

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        abridorDeDirecciones = ::abrirEnElNavegador
        setContent {
            App()
        }
    }

    private fun abrirEnElNavegador(direccion: String) {
        startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(direccion)))
    }
}
