@file:OptIn(kotlin.js.ExperimentalWasmJsInterop::class)

package org.bc250.controlcenter.datos

private fun escucharEnElNavegador(alPulsar: (String) -> Unit): Unit = js(
    """{
        const nombres = {0: 'aceptar', 1: 'volver', 4: 'anterior', 5: 'siguiente',
                         12: 'arriba', 13: 'abajo', 14: 'izquierda', 15: 'derecha'};
        const antes = {};
        const repetir = {};
        function mirar() {
            const ahora = Date.now();
            const mandos = navigator.getGamepads ? navigator.getGamepads() : [];
            const activos = {};
            for (const mando of mandos) {
                if (!mando) { continue; }
                for (const numero in nombres) {
                    if (mando.buttons[numero] && mando.buttons[numero].pressed) { activos[nombres[numero]] = true; }
                }
                if (mando.axes[0] < -0.6) { activos['izquierda'] = true; }
                if (mando.axes[0] > 0.6) { activos['derecha'] = true; }
                if (mando.axes[1] < -0.6) { activos['arriba'] = true; }
                if (mando.axes[1] > 0.6) { activos['abajo'] = true; }
            }
            for (const nombre of Object.values(nombres)) {
                const seRepite = nombre !== 'aceptar' && nombre !== 'volver';
                if (activos[nombre] && !antes[nombre]) {
                    repetir[nombre] = ahora + 420;
                    alPulsar(nombre);
                } else if (activos[nombre] && seRepite && ahora > repetir[nombre]) {
                    repetir[nombre] = ahora + 140;
                    alPulsar(nombre);
                }
                antes[nombre] = activos[nombre];
            }
            if (document.hasFocus()) { requestAnimationFrame(mirar); } else { setTimeout(mirar, 500); }
        }
        if (!window.bc250Mando) {
            window.bc250Mando = true;
            mirar();
        }
    }""",
)

private fun pulsarEnElNavegador(): Unit = js(
    """{
        function buscar(raiz) {
            const lienzo = raiz.querySelector('canvas');
            if (lienzo) { return lienzo; }
            for (const pieza of raiz.querySelectorAll('*')) {
                const dentro = pieza.shadowRoot ? buscar(pieza.shadowRoot) : null;
                if (dentro) { return dentro; }
            }
            return null;
        }
        const lienzo = buscar(document);
        if (lienzo) {
            for (const clase of ['keydown', 'keyup']) {
                lienzo.dispatchEvent(new KeyboardEvent(clase, {key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true, cancelable: true}));
            }
        }
    }""",
)

actual fun escucharMando(alPulsar: (String) -> Unit) {
    escucharEnElNavegador(alPulsar)
}

actual fun pulsarEnfocado() {
    pulsarEnElNavegador()
}
