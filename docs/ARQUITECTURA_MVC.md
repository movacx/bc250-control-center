# Arquitectura — BC250 Control Center

La aplicación separa la interfaz, los casos de uso y los adaptadores del
sistema para que ninguna vista escriba hardware ni construya comandos
privilegiados por sí sola.

```text
Desktop / CLI / Quick Access
            ↓
        application
            ↓
 domain · infrastructure · platform
            ↓
 helpers tipados · sistema · D-Bus · sysfs · herramientas externas
```

## Capas activas

- `frontends/`: interfaz PyQt6, CLI y Quick Access. Recoge la intención del
  usuario y presenta resultados, sin ser una frontera de seguridad.
- `src/bc250cc/application/`: casos de uso y coordinación.
- `src/bc250cc/domain/`: modelos, límites y políticas puras.
- `src/bc250cc/infrastructure/`: persistencia, procesos, D-Bus, sysfs y
  adaptadores de herramientas externas.
- `src/bc250cc/platform/`: selección de distribución, paquetes e init.
- `privileged/`: helpers root-owned con acciones tipadas y política Polkit.
- `packaging/` y `scripts/`: artefactos de instalación y flujos explícitos.

`ApplicationContainer` compone las dependencias. Las acciones lentas o con
privilegios salen del hilo de interfaz y regresan como resultados tipados; los
frontends comparten la misma lógica de aplicación en lugar de implementar sus
propias reglas de hardware.

## Límites que no se deben romper

1. La UI no escribe hardware ni ejecuta comandos root arbitrarios.
2. Un helper privilegiado acepta acciones finitas, valida sus argumentos y no
   ejecuta código que el usuario pueda sustituir.
3. `ResourceTools` es espacio de usuario; no es una raíz de confianza para
   Python o shell con privilegios.
4. Los cambios de CPU, GPU, CU, PWM, kernel, ACPI, UEFI o servicios requieren
   validación en su propia frontera, además de cualquier confirmación de UI.
5. Telemetría rápida no debe iniciar red, Git, gestores de paquetes ni cambios
   de systemd.

Los detalles de procedencia, revisión y límites de las herramientas externas
están en [Third-party notices](THIRD_PARTY_NOTICES.md).
