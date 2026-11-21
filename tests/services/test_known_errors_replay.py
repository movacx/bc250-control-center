"""Error windows from real reports open the entry that explains them.

Each message below is the decisive part of what an owner's error window
showed (October-November 2026 reports), with names and paths removed. The
window offers ``for_message``'s answer; when it is a single entry it opens
that guide directly. Before this replay only 37% of the reported windows
reached the right guide alone: loose rules (any sudo prompt, any compiler
error, any systemd failure) answered next to the rule that named the cause,
and a generic code printed in the text dragged in every entry sharing it.
"""

from __future__ import annotations

import pytest

from bc250cc.shared import known_errors as handbook

WORKFLOW_FOOTER = (
    "\nThe workflow did not finish successfully.\n"
    "Diagnostic code: BC250-WORKFLOW-001\n"
)

REPLAYS = [
    # A sudo prompt sits in almost every workflow; the cause is elsewhere.
    ("STEAM-07", "[sudo] password for deck:\n[ERROR] SteamOS write verification needs interactive sudo "
                 "authorization.\n[ERROR] Run this installer from a terminal, or authorize its Polkit prompt, "
                 "then retry." + WORKFLOW_FOOTER),
    ("STEAM-01", "[sudo] password for deck:\nERROR: the reviewed SteamOS kernel backend supports kernel bases "
                 "6.16, 6.18, 7.2; running: 7.3.1-valve2-1-neptune" + WORKFLOW_FOOTER),
    ("GOV-13", "[sudo] password for user:\nERROR: Cyan fix-freq is missing or invalid in config.toml" + WORKFLOW_FOOTER),
    # Build failures are not authorization failures.
    ("STEAM-03", "make[1]: *** [valve-kernel/Makefile:1601: tools/bpf/resolve_btfids] Error 2\n"
                 "make: *** [Makefile:248: __sub-make] Error 2" + WORKFLOW_FOOTER),
    ("GOV-11", "fatal error: features.h: No such file or directory\n"
               "make[2]: *** [_deps/yaml-cpp-build/CMakeFiles/yaml-cpp.dir/build.make:93: graphbuilder.cpp.o] Error 1"),
    # The same words in other languages.
    ("PKG-01", "błąd: nie udało się zablokować bazy danych: Plik istnieje"),
    ("PKG-01", "E: Could not get lock /var/lib/dpkg/lock-frontend. It is held by process 1602 (apt-get)"),
    ("PKG-01", "error: failed to synchronize all databases (unable to lock database)"),
    ("PKG-01", "ERROR: A package manager is still running (pacman), so pacman is busy."),
    ("PKG-11", "erro: base de dados já registrada"),
    ("INST-05", "error: Updating deployment: Przekroczono czas oczekiwania"),
    ("AUTH-01", "sudo: délai d'attente dépassé durant la lecture du mot de passe\n"
                "sudo: il est nécessaire de saisir un mot de passe"),
    # One specific cause next to the consequence every run prints.
    ("UPS-08", "wine client error:0: recvmsg: Connection reset by peer\n[helixsr-setup] error: the setup "
               "stopped (exit 1)\nThe network was not built. HelixSR is installed."),
    ("UPS-02", "[helixsr-setup] error: unknown option: --vulkan (see --help)\nDownload it now? [y/N]\n"
               "The network was not built."),
    ("UPS-01", "Checking the reviewed SHA-256... ERROR: HelixSR-3.3.0.zip as published now is not the archive "
               "Control Center checked."),
    ("INST-01", "error: Packages not found: coolercontrol\nThat layered package is no longer available."),
    ("INST-04", "Another rpm-ostree transaction (usually an automatic system update) is running; waiting for it "
                "to finish...\nerror: Transaction in progress: upgrade"),
    ("INST-08", "[sudo] password for user: usage: bc250-system-setup-helper [-h] [--policy {preserve,restore}] "
                "[--ttm {-1,0,8,10,12}]"),
    ("GOV-07", "cyan-skillfish-governor-smu[1559]: Error: Message(\"Cyan Skillfish GPU not found at expected PCI "
               "bus location\")\nsystemd[1]: cyan-skillfish-governor-smu.service: Main process exited, "
               "status=1/FAILURE"),
    ("GOV-07", "[ERROR] AMD BC-250 (PCI 1002:13fe) was not found" + WORKFLOW_FOOTER),
    ("GOV-09", "Error: Io(Custom { kind: Other, error: \"mount --bind /dev/shm/patched_gpu_metrics "
               "/sys/bus/pci/devices/0000:01:00.0/gpu_metrics failed: exit status: 32\" })"),
    ("GOV-03", "ERROR: The governor TOML does not contain any safe-point above 2000 MHz."),
    ("GOV-10", "RuntimeError: The Cyan governor must be active before changing its voltage curve."),
    ("GOV-08", "{\"ok\": false, \"error\": \"The BC-250's render node was not found.\"}\n"
               "ERROR: the built driver did not start or lacks H.264/HEVC. Nothing was installed."),
    ("FAN-01", "bc250-load-nct6687: insmod: ERROR: could not insert module nct6687.ko: No such device\n"
               "systemd[1]: Failed to start nct6687-load.service - Load nct6687 for BC250 fan PWM on Bazzite."),
    ("STOR-01", "What happened: /var has only 83 MB free and this needs about 100 MB."),
    ("MEM-02", "ERROR: Insufficient disk space: a 16 GiB swapfile must still leave 23 GiB free on /var/lib"),
    ("CU-01", "could not install umr automatically; install it with apt/pacman/paru/rpm-ostree/dnf first"),
    ("INST-03", "W: GPG error: http://dl.google.com/linux/earth/deb stable InRelease: The following signatures "
                "couldn't be verified because the public key is not available: NO_PUBKEY 32EE5355A6BC6E42"),
    ("GFX-01", "ERROR: Release v0.2.4 supports Bazzite 44 only." + WORKFLOW_FOOTER),
]


@pytest.mark.parametrize(("expected", "message"), REPLAYS, ids=[f"{e}-{i}" for i, (e, _m) in enumerate(REPLAYS)])
def test_a_reported_window_opens_its_own_entry(expected, message):
    found = [entry["id"] for entry in handbook.for_message(message)]
    assert found == [expected]


def test_a_generic_code_in_the_text_proposes_nothing():
    # Every workflow prints its diagnostic code; it says nothing about the cause.
    assert handbook.for_message("Something unrecognised happened." + WORKFLOW_FOOTER) == ()


def test_a_specific_code_in_the_text_still_finds_its_entries():
    assert {entry["id"] for entry in handbook.for_message("BC250-UMR-001")} == {"CU-01", "CU-02"}


@pytest.mark.parametrize(("pattern", "length"), [
    (r"authorization.*(?:cancel|fail|dismiss)", 17),
    (r"\[sudo\] password for", 19),
    (r"unexpected core mask 0x[0-9a-fA-F]{2}, expected 0x77", 38),
    (r"(?:a|b)?xyz", 3),
])
def test_specificity_counts_only_what_a_rule_insists_on(pattern, length):
    assert handbook._literal_length(pattern) == length
