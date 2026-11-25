package org.bc250.controlcenter.datos

import android.content.Context
import android.content.SharedPreferences

/** Lo prepara la actividad antes de dibujar nada. */
private var preferencias: SharedPreferences? = null

fun prepararAlmacen(contexto: Context) {
    preferencias = contexto.getSharedPreferences("bc250", Context.MODE_PRIVATE)
}

actual val pideDireccion: Boolean = true

actual fun leerGuardado(clave: String): String {
    return preferencias?.getString(clave, "") ?: ""
}

actual fun guardarDato(clave: String, valor: String) {
    preferencias?.edit()?.putString(clave, valor)?.apply()
}
