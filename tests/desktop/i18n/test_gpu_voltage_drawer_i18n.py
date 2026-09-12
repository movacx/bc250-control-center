from frontends.desktop.i18n import tr
from frontends.desktop.i18n.locale_catalog import COMPLETE_LOCALES, load_locale_catalog

GPU_VOLTAGE_WORKFLOW_SOURCES = (
    "GPU voltage curve",
    "Choose a safe preset or drag the active points",
    "Close GPU voltage curve",
    "V/F curve",
    "proposed",
    "1 point changed",
    "{count} points changed",
    "peak {value} mV",
    "max {value} mV",
    "Curve boost",
    "Gentle",
    "Moderate",
    "Custom\nEdit active points",
    "Selected",
    "Configured",
    "Not set",
    "Governor default",
    "No baseline",
    "Oberon compatibility mode",
    "Oberon uses two YAML endpoints. They are shown below for reference; curve editing is unavailable for this governor.",
    "Restore governor defaults",
    "Adjust the safe points currently active in the governor configuration.",
    "+{added} mV is added only to the high-frequency curve from {start} MHz. Lower-frequency values return to governor defaults.",
    "Open voltage laboratory",
    "Open the compact voltage curve laboratory without leaving GPU control.",
    "Save active range for startup",
    "Write the live Cyan range to [frequency-range] for the next startup.",
    "Active range unavailable",
    "Refresh GPU status before saving a startup range.",
    "This writes the currently active Cyan D-Bus range to the managed TOML. Cyan will use it at the next startup. The running GPU range and governor service will not be changed.",
    "TOML section",
    "No restart",
    "Save startup range",
    "Saved {minimum}-{maximum} MHz for Cyan startup.",
    "Could not save the startup range",
)


def test_gpu_voltage_workflow_is_materialized_in_all_thirty_locales():
    assert len(COMPLETE_LOCALES) == 30
    for language in COMPLETE_LOCALES:
        catalog = load_locale_catalog(language)
        for source in GPU_VOLTAGE_WORKFLOW_SOURCES:
            assert source in catalog, (language, source)
            assert catalog[source].strip(), (language, source)
            assert tr(source, language) == catalog[source]


def test_gpu_voltage_workflow_has_no_non_english_fallbacks():
    for language in COMPLETE_LOCALES:
        if language == "en":
            continue
        catalog = load_locale_catalog(language)
        for source in GPU_VOLTAGE_WORKFLOW_SOURCES:
            assert catalog[source] != source, (language, source)
