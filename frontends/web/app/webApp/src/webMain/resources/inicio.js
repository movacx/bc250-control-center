// Deja instalar la web en el teléfono. Sin conexión solo explica qué pasa: nunca guarda datos del equipo.
if ("serviceWorker" in navigator && window.isSecureContext) {
    navigator.serviceWorker.register("/sw.js");
}
