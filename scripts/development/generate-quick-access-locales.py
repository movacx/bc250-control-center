#!/usr/bin/env python3
"""Generate and validate the seven complete Quick Access catalogs."""
from __future__ import annotations

import ast
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from frontends.desktop.i18n.locale_catalog import load_locale_catalog  # noqa: E402

generator_path = ROOT / "scripts" / "development" / "generate-complete-locales.py"
spec = importlib.util.spec_from_file_location("bc250_complete_locale_generator", generator_path)
if spec is None or spec.loader is None:
    raise RuntimeError("could not load the complete locale generator")
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)

SOURCE = ROOT / "integrations" / "decky" / "bc250-quick-access" / "src" / "index.tsx"
OUTPUT = ROOT / "integrations" / "decky" / "bc250-quick-access" / "locales"
LOCALES = ("en", "es", "es-419", "pt", "ru", "pl", "de", "uk")

EXTRA_ENGLISH = {
    "profileRecovery": "Recovery",
    "profileBalanced": "Balanced",
    "profileGaming": "Gaming",
    "profileBenchmark": "Benchmark",
    "advanced": "advanced",
    "gpuBusyGuidance": "Wait for the GPU to return to 1000 MHz, then retry.",
    "oberonBusy": "Wait for the GPU to return to 1000 MHz",
    "cuGuidance": "Refresh and review CU diagnostics if it repeats.",
    "fanGuidance": "Return the channel to Automatic and retry.",
    "cpuGuidance": "Review the validated profile in Desktop Mode.",
    "retryGuidance": "Wait a few seconds and retry.",
    "safeCuMinimum": "Quick Access keeps a safe 24 CU minimum.",
    "topologyUnavailable": "WGP topology unavailable.",
    "liveRoutingUnchanged": "Live routing will not change.",
    "runAutomaticFirst": "Run automatic scale first",
    "stressMissing": "The stress dependency required by bc250-detect is missing.",
    "cpuHelperUnavailable": "The protected CPU helper is unavailable.",
    "serviceRemovedBootProfile": "The service is removed; the detected profile remains available during this boot.",
    "manualApplyWarning": "It will be applied temporarily at the detector-validated frequency. Monitor temperature and stability before installing the service.",
    "automaticApplyWarning": "bc250-detect will test the CPU under load, derive the scale, and apply only the result it finds. Monitor temperatures and stability.",
    "installExactProfile": "Only the exact profile applied and verified during this boot will be installed.",
    "estimated": "estimated",
    "snapshotWarning": "The shared CU snapshot could not be updated. Refresh before making another CU change.",
    "gpuOperationFailed": "The GPU operation failed.",
    "cuOperationFailed": "The CU operation failed.",
    "fanOperationFailed": "The fan operation failed.",
    "cpuOperationFailed": "The CPU operation failed.",
    "likelyCause": "Likely cause",
    "diagnosticCode": "Diagnostic code",
    "protocolFailed": "Quick Access and its helper are different versions.",
    "protocolCause": "Only part of BC250 Control Center was updated, or Decky kept an older plugin process running.",
    "protocolAction": "Repair Quick Access in Desktop Mode, then restart Decky Loader.",
    "helperFailed": "The protected BC250 helper is missing or unsafe.",
    "helperCause": "The helper is absent, has incorrect root ownership, or can be modified by another user.",
    "helperAction": "Reinstall BC250 Control Center from Desktop Mode and repair Quick Access.",
    "busyFailed": "Another BC250 operation is still running.",
    "busyCause": "A previous press, Desktop workflow, or external toolkit still holds the hardware lock.",
    "busyAction": "Wait for the current operation to finish, refresh, and retry once.",
    "timeoutFailed": "The operation exceeded its safety time limit.",
    "timeoutCause": "A helper, service, hardware read-back, or external toolkit stopped responding.",
    "timeoutAction": "Check Desktop Mode for a running process or service error before retrying.",
    "gpuDbusFailed": "The GPU governor controls are not ready.",
    "gpuDbusCause": "Cyan is stopped, still starting, misconfigured, or conflicting with Oberon.",
    "gpuDbusAction": "In Desktop Mode, keep one governor active and wait for D-Bus to show Connected.",
    "gpuBusyCause": "The GPU is not at the idle state required for this Oberon change.",
    "gpuRangeFailed": "The selected GPU range is not supported now.",
    "gpuRangeCause": "The requested point is outside the safe table reported by the active governor.",
    "gpuRangeAction": "Refresh and choose one of the GPU profiles or safe points currently displayed.",
    "gpuCause": "The active governor or live hardware state did not verify the requested change.",
    "gpuAction": "Refresh GPU status and verify the active governor in Desktop Mode.",
    "cuBackendFailed": "The Compute Units backend is not ready.",
    "cuBackendCause": "UMR, its GPU database, or the live manager does not match the running stack.",
    "cuBackendAction": "Prepare UMR in Desktop Mode, then sync the live CU map again.",
    "cuCause": "The requested WGP map and the live AMDGPU topology did not agree.",
    "fanCause": "The NCT driver, hwmon route, PWM channel, or write read-back is unavailable.",
    "cpuVerifyFailed": "The CPU result could not be verified.",
    "cpuVerifyCause": "The same-boot detector evidence is missing or does not match the requested frequency and scale.",
    "cpuVerifyAction": "Run automatic detection for this exact frequency in the current boot before saving it.",
    "cpuCause": "The detector, stress dependency, SMU helper, or selected profile did not complete safely.",
    "unknownCause": "Quick Access received a failure that does not match a known component yet.",
}

EXTRA_SPANISH = {
    "profileRecovery": "Recuperación", "profileBalanced": "Equilibrado",
    "profileGaming": "Juegos", "profileBenchmark": "Benchmark", "advanced": "avanzado",
    "gpuBusyGuidance": "Espera a que la GPU vuelva a 1000 MHz y reintenta.",
    "oberonBusy": "Espera a que la GPU vuelva a 1000 MHz",
    "cuGuidance": "Actualiza el estado y revisa Diagnóstico CU si se repite.",
    "fanGuidance": "Devuelve el canal a Automático y vuelve a intentarlo.",
    "cpuGuidance": "Revisa el perfil validado en Modo Escritorio.",
    "retryGuidance": "Espera unos segundos y vuelve a intentarlo.",
    "safeCuMinimum": "Quick Access mantiene un mínimo seguro de 24 CU.",
    "topologyUnavailable": "Topología WGP no disponible.",
    "liveRoutingUnchanged": "El ruteo vivo no cambiará.",
    "runAutomaticFirst": "Ejecuta primero la escala automática",
    "stressMissing": "Falta la dependencia stress para ejecutar bc250-detect.",
    "cpuHelperUnavailable": "El helper CPU protegido no está disponible.",
    "serviceRemovedBootProfile": "Se elimina el servicio; el perfil detectado se conserva durante este arranque.",
    "manualApplyWarning": "Se aplicará temporalmente sobre la frecuencia validada por el detector. Supervisa temperatura y estabilidad antes de instalar el servicio.",
    "automaticApplyWarning": "bc250-detect probará la CPU bajo carga, derivará la escala y aplicará únicamente el resultado encontrado. Supervisa temperaturas y estabilidad.",
    "installExactProfile": "Se instalará exactamente el perfil aplicado y verificado en este arranque.",
    "estimated": "estimados",
    "snapshotWarning": "No se pudo actualizar la instantánea CU compartida. Actualiza antes de realizar otro cambio CU.",
    "gpuOperationFailed": "Falló la operación de GPU.", "cuOperationFailed": "Falló la operación de CU.",
    "fanOperationFailed": "Falló la operación del ventilador.", "cpuOperationFailed": "Falló la operación de CPU.",
    "likelyCause": "Causa probable", "diagnosticCode": "Código de diagnóstico",
    "protocolFailed": "Quick Access y su helper tienen versiones diferentes.",
    "protocolCause": "Solo se actualizó una parte de BC250 Control Center o Decky mantuvo un proceso antiguo del plugin.",
    "protocolAction": "Repara Quick Access en Modo Escritorio y reinicia Decky Loader.",
    "helperFailed": "El helper protegido de BC250 falta o no es seguro.",
    "helperCause": "El helper no existe, no pertenece a root o puede ser modificado por otro usuario.",
    "helperAction": "Reinstala BC250 Control Center desde Modo Escritorio y repara Quick Access.",
    "busyFailed": "Todavía hay otra operación de BC250 en ejecución.",
    "busyCause": "Una acción anterior, un flujo de Escritorio o un toolkit externo mantiene ocupado el hardware.",
    "busyAction": "Espera a que termine la operación, actualiza y vuelve a intentarlo una vez.",
    "timeoutFailed": "La operación superó su límite de tiempo seguro.",
    "timeoutCause": "Un helper, servicio, lectura del hardware o toolkit externo dejó de responder.",
    "timeoutAction": "Revisa en Modo Escritorio si sigue un proceso activo o existe un error de servicio.",
    "gpuDbusFailed": "Los controles del governor de GPU todavía no están listos.",
    "gpuDbusCause": "Cyan está detenido, iniciando, mal configurado o en conflicto con Oberon.",
    "gpuDbusAction": "En Modo Escritorio deja un solo governor activo y espera a que D-Bus indique Conectado.",
    "gpuBusyCause": "La GPU no está en el estado de reposo requerido para este cambio de Oberon.",
    "gpuRangeFailed": "El rango de GPU seleccionado no es compatible ahora.",
    "gpuRangeCause": "El punto solicitado queda fuera de la tabla segura informada por el governor activo.",
    "gpuRangeAction": "Actualiza y elige uno de los perfiles o puntos seguros de GPU mostrados.",
    "gpuCause": "El governor activo o el estado vivo del hardware no verificó el cambio solicitado.",
    "gpuAction": "Actualiza el estado de GPU y verifica el governor activo en Modo Escritorio.",
    "cuBackendFailed": "El backend de Unidades de Cómputo no está listo.",
    "cuBackendCause": "UMR, su base de datos GPU o el live manager no coinciden con el stack en ejecución.",
    "cuBackendAction": "Prepara UMR en Modo Escritorio y vuelve a sincronizar el mapa CU vivo.",
    "cuCause": "El mapa WGP solicitado y la topología AMDGPU en vivo no coincidieron.",
    "fanCause": "El driver NCT, la ruta hwmon, el canal PWM o la verificación de escritura no están disponibles.",
    "cpuVerifyFailed": "No se pudo verificar el resultado de CPU.",
    "cpuVerifyCause": "Falta la evidencia del detector de este arranque o no coincide con la frecuencia y escala solicitadas.",
    "cpuVerifyAction": "Ejecuta la detección automática para esta frecuencia exacta durante el arranque actual antes de guardarla.",
    "cpuCause": "El detector, la dependencia stress, el helper SMU o el perfil elegido no terminaron de forma segura.",
    "unknownCause": "Quick Access recibió un fallo que todavía no coincide con un componente conocido.",
}


def existing_text_objects() -> tuple[dict[str, str], dict[str, str]]:
    source = SOURCE.read_text(encoding="utf-8")
    if "const text = isSpanish" not in source:
        return (
            json.loads((OUTPUT / "en.json").read_text(encoding="utf-8")),
            json.loads((OUTPUT / "es.json").read_text(encoding="utf-8")),
        )
    start = source.index("const text = isSpanish")
    spanish_start = source.index("? {", start)
    english_start = source.index(": {", spanish_start)
    end = source.index("};", english_start)

    def parse(block: str) -> dict[str, str]:
        return {
            key: ast.literal_eval(f'"{value}"')
            for key, value in re.findall(r'(\w+):\s*"((?:[^"\\]|\\.)*)"', block)
        }

    return parse(source[english_start:end]), parse(source[spanish_start:english_start])


def translate_missing(language: str, pending: dict[str, str]) -> dict[str, str]:
    if not pending:
        return {}
    by_source = dict.fromkeys(pending.values())
    entries = []
    for ordinal, source in enumerate(by_source):
        protected, replacements = generator.protect(source, ordinal)
        entries.append((source, protected, replacements))
    translated: dict[str, str] = {}
    for index, batch in enumerate(generator.chunks(entries)):
        translated.update(generator.translate_chunk(language, index, batch))
    return {key: translated[source] for key, source in pending.items()}


def main() -> int:
    english, spanish = existing_text_objects()
    english.update(EXTRA_ENGLISH)
    spanish.update(EXTRA_SPANISH)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for language in LOCALES:
        catalog: dict[str, str] = {}
        pending: dict[str, str] = {}
        desktop = load_locale_catalog(language)
        for key, source in english.items():
            if language == "en":
                catalog[key] = source
            elif language in {"es", "es-419"} and key in spanish:
                catalog[key] = spanish[key]
            elif source in desktop and desktop[source] != source:
                catalog[key] = desktop[source]
            else:
                pending[key] = source
        catalog.update(translate_missing(language, pending))
        if set(catalog) != set(english) or any(not value.strip() for value in catalog.values()):
            raise ValueError(f"{language}: incomplete Quick Access catalog")
        for key, source in english.items():
            if not generator.protected_terms_preserved(source, catalog[key]):
                raise ValueError(f"{language}: changed technical name in {key}")
        (OUTPUT / f"{language}.json").write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"{language}: wrote {len(catalog)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
