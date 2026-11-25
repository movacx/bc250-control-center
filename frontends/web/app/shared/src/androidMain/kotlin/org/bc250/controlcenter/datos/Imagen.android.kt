package org.bc250.controlcenter.datos

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.net.Uri
import android.provider.OpenableColumns
import android.util.Base64
import java.io.ByteArrayOutputStream

private const val ANCHO_LOGO = 672
private const val ALTO_LOGO = 378
private const val MAXIMO_BYTES = 60_000
private const val CALIDAD_MAYOR = 85
private const val CALIDAD_MENOR = 25
private const val PASO_CALIDAD = 10

private class ImagenElegida(val nombre: String, val dibujo: Bitmap)

private var elegida: ImagenElegida? = null
private var alRecibir: (ImagenLogo) -> Unit = {}

/** Lo pone la actividad: abre la galería del teléfono. */
var abridorDeGaleria: () -> Unit = {}

actual val puedeElegirImagen: Boolean = true

actual fun elegirImagen(alElegir: (ImagenLogo) -> Unit) {
    alRecibir = alElegir
    abridorDeGaleria()
}

/** La actividad entrega aquí lo que se eligió en la galería. */
fun recibirImagen(contexto: Context, direccion: Uri) {
    val dibujo = contexto.contentResolver.openInputStream(direccion)?.use { entrada -> BitmapFactory.decodeStream(entrada) }
    if (dibujo != null) {
        val imagen = ImagenElegida(nombreDe(contexto, direccion), dibujo)
        elegida = imagen
        alRecibir(preparar(imagen, 100))
    }
}

actual fun reescalarImagen(porcentaje: Int, alTerminar: (ImagenLogo) -> Unit) {
    val imagen = elegida
    if (imagen != null) {
        alTerminar(preparar(imagen, porcentaje))
    }
}

private fun nombreDe(contexto: Context, direccion: Uri): String {
    val columnas = arrayOf(OpenableColumns.DISPLAY_NAME)
    contexto.contentResolver.query(direccion, columnas, null, null, null)?.use { filas ->
        if (filas.moveToFirst()) {
            return filas.getString(0) ?: "logo"
        }
    }
    return "logo"
}

/** La imagen centrada sobre negro, con la calidad más alta que quepa en 60 KB. */
private fun preparar(imagen: ImagenElegida, porcentaje: Int): ImagenLogo {
    val lienzo = Bitmap.createBitmap(ANCHO_LOGO, ALTO_LOGO, Bitmap.Config.ARGB_8888)
    val pincel = Canvas(lienzo)
    pincel.drawColor(Color.BLACK)
    val parte = porcentaje / 100f
    val escala = minOf(ANCHO_LOGO * parte / imagen.dibujo.width, ALTO_LOGO * parte / imagen.dibujo.height)
    val ancho = imagen.dibujo.width * escala
    val alto = imagen.dibujo.height * escala
    val izquierda = (ANCHO_LOGO - ancho) / 2
    val arriba = (ALTO_LOGO - alto) / 2
    pincel.drawBitmap(imagen.dibujo, null, RectF(izquierda, arriba, izquierda + ancho, arriba + alto), Paint(Paint.FILTER_BITMAP_FLAG))
    var calidad = CALIDAD_MAYOR
    var datos = comprimir(lienzo, calidad)
    while (datos.size > MAXIMO_BYTES && calidad > CALIDAD_MENOR) {
        calidad -= PASO_CALIDAD
        datos = comprimir(lienzo, calidad)
    }
    return ImagenLogo(imagen.nombre, imagen.dibujo.width, imagen.dibujo.height, Base64.encodeToString(datos, Base64.NO_WRAP))
}

private fun comprimir(lienzo: Bitmap, calidad: Int): ByteArray {
    val salida = ByteArrayOutputStream()
    lienzo.compress(Bitmap.CompressFormat.JPEG, calidad, salida)
    return salida.toByteArray()
}
