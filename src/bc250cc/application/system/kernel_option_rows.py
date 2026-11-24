"""The kernel boot options' names, buttons and questions, for every frontend."""

from __future__ import annotations

from bc250cc.infrastructure.system_setup import (
    CH7218_QUIRK_OPTION,
    CH7218_VRR_OPTION,
    CU_UNLOCK_OPTION,
    HDMI21_OFF_OPTION,
    HIDE_BOOT_MESSAGES_OPTION,
    MEMORY_SENSOR_OPTION,
    PCON_FORCE_DSC_OPTION,
    RELINK_AT_BOOT_OPTION,
    RELINK_OFF_OPTION,
    SCHED_POLICY_OPTION,
)

#: The two boot options, in the order the panel shows them.
ROWS = (
    ("mitigations=off", "CPU security mitigations", "Disable mitigations", "Restore mitigations"),
    ("nosmt", "Simultaneous multithreading (SMT)", "Disable SMT", "Restore SMT"),
    (CU_UNLOCK_OPTION, "Compute Units unlock (kernel)", "Unlock all 40 CUs", "Restore CU lock"),
    (HIDE_BOOT_MESSAGES_OPTION, "Boot messages (hides the RDSEED warning)", "Hide boot messages", "Show boot messages"),
    (SCHED_POLICY_OPTION, "GPU scheduler policy (non-HWS)", "Use non-HWS scheduling", "Restore default scheduling"),
    (HDMI21_OFF_OPTION, "HDMI 2.1 and DSC negotiation", "Turn HDMI 2.1 off", "Turn HDMI 2.1 on"),
    (RELINK_OFF_OPTION, "Picture recovery after a mode change", "Turn recovery off", "Turn recovery on"),
    # Opt-in fixes of MastaG's kernel, each for one symptom; off by default there.
    (CH7218_QUIRK_OPTION, "4K120 black screen fix (UGREEN / CH7218 adapter)", "Turn the CH7218 fix on", "Turn the CH7218 fix off"),
    (CH7218_VRR_OPTION, "VRR on CH7218 firmware 07.00.69", "Force VRR on the adapter", "Stop forcing VRR"),
    (PCON_FORCE_DSC_OPTION, "Force DSC on a VMM7100 adapter (experimental)", "Force DSC", "Stop forcing DSC"),
    (RELINK_AT_BOOT_OPTION, "Picture recovery at boot (experimental)", "Recover at boot", "Stop recovering at boot"),
    # Off on purpose: the driver patches the SMU firmware and shares its mailbox.
    (MEMORY_SENSOR_OPTION, "GDDR6 temperature from the kernel (bc250_memory)", "Load at boot", "Stop loading at boot"),
)
#: Options only the BC-250 kernel has a parameter for: offered where the
#: kernel reports it (or where one is already staged, to take it back).
PARAMETER_OPTIONS = frozenset({
    HDMI21_OFF_OPTION, RELINK_OFF_OPTION,
    CH7218_QUIRK_OPTION, CH7218_VRR_OPTION, PCON_FORCE_DSC_OPTION, RELINK_AT_BOOT_OPTION,
    MEMORY_SENSOR_OPTION,
})
#: Options that give something up, and so are drawn as a warning. Unlocking
#: compute units gives nothing up: it is the BC-250 kernel's own method.
#: Hiding boot messages risks nothing for the board; it is explained in its
#: confirmation, not painted red.
NEUTRAL = frozenset({
    CU_UNLOCK_OPTION, HIDE_BOOT_MESSAGES_OPTION, SCHED_POLICY_OPTION, HDMI21_OFF_OPTION, RELINK_OFF_OPTION,
    CH7218_QUIRK_OPTION, CH7218_VRR_OPTION, PCON_FORCE_DSC_OPTION, RELINK_AT_BOOT_OPTION,
})

#: What is asked before one is added: (title, text, button, tone). Restoring needs no question.
CONFIRMATIONS = {
    CU_UNLOCK_OPTION: ("Unlock all 40 compute units with the kernel", (
        "The BC-250 kernel unlocks the compute units by itself when amdgpu starts, so umr "
        "and the CU live manager are not needed. Turn off the live manager's boot service "
        "so only one of them sets the CUs. A board with a damaged CU pair cannot run all "
        "40. The change applies after reboot and can be restored from Control Center."
    ), "Unlock 40 CUs", "orange"),
    "mitigations=off": ("Disable CPU security mitigations", (
        "This disables optional kernel protections against multiple CPU vulnerabilities. "
        "It may improve performance in some workloads. The change applies after reboot "
        "and can be restored from Control Center."
    ), "Disable mitigations", "red"),
    HIDE_BOOT_MESSAGES_OPTION: ("Hide the kernel's boot messages", (
        "The BC-250's CPU makes the kernel print a warning about its random-number "
        "instructions (RDSEED) at every boot. This hides it by silencing all kernel messages "
        "on screen while the system starts, errors included, so a boot problem will show "
        "nothing there. It fixes nothing: the messages stay in dmesg and the system log. "
        "The change applies after reboot and can be restored from Control Center."
    ), "Hide boot messages", "orange"),
    SCHED_POLICY_OPTION: ("Use the non-HWS GPU scheduler", (
        "Some systems and games run smoother with the software GPU scheduler "
        "(amdgpu.sched_policy=2), others slower, so measure yours. ROCm and KFD work needs it. "
        "The change applies after reboot and can be restored from Control Center."
    ), "Use non-HWS scheduling", "orange"),
    HDMI21_OFF_OPTION: ("Turn HDMI 2.1 negotiation off", (
        "This removes 4K120 at 4:4:4 through a DisplayPort to HDMI 2.1 adapter. Only do it if "
        "that negotiation gives you a black screen or flicker. The change applies after "
        "reboot and can be restored from Control Center."
    ), "Turn HDMI 2.1 off", "orange"),
    RELINK_OFF_OPTION: ("Turn picture recovery off", (
        "The kernel re-detects the display when the picture stays off after a mode change. "
        "Turning this off leaves a lost picture as it is. The change applies after reboot "
        "and can be restored from Control Center."
    ), "Turn recovery off", "orange"),
    CH7218_QUIRK_OPTION: ("Turn the CH7218 adapter fix on", (
        "Only for a DisplayPort to HDMI 2.1 adapter with a Chrontel CH7218 chip (UGREEN and "
        "others) where 4K60 works but 4K90 or 4K120 gives a black screen. It makes the driver "
        "treat the adapter as the HDMI 2.1 converter it is. Many CH7218 adapters work without "
        "it and nothing tells them apart, so leave it off unless you have that symptom. It "
        "needs HDMI 2.1 negotiation on. The change applies after reboot and can be restored "
        "from Control Center."
    ), "Turn the CH7218 fix on", "orange"),
    CH7218_VRR_OPTION: ("Force VRR on the CH7218 adapter", (
        "UGREEN's 07.00.69 firmware for the CH7218 adapter no longer tells the driver that it "
        "supports VRR, so none is offered although the TV has it. This makes the driver assume "
        "it does. It was tested on one setup: if the picture misbehaves with VRR on, turn it "
        "off again. It needs HDMI 2.1 negotiation on. The change applies after reboot and can "
        "be restored from Control Center."
    ), "Force VRR on the adapter", "orange"),
    PCON_FORCE_DSC_OPTION: ("Force DSC on the adapter", (
        "Experimental. For a DisplayPort to HDMI 2.1 adapter that reports no DSC decoder, such "
        "as the Cable Matters 102101 (VMM7100), and so gives 4K120 in 4:2:2 instead of RGB. "
        "The driver then drives it as if it had DSC. Either 4K120 comes out in full colour, or "
        "the screen stays black at 4K120 and you turn it off again. The change applies after "
        "reboot and can be restored from Control Center."
    ), "Force DSC", "orange"),
    RELINK_AT_BOOT_OPTION: ("Recover the picture at boot", (
        "Experimental. Re-detects the display once on the first screen of each boot, for an "
        "adapter that was already stuck before the machine started. Each re-detect costs a real "
        "mode change, so leave it off unless you have that symptom. The change applies after "
        "reboot and can be restored from Control Center."
    ), "Recover at boot", "orange"),
    MEMORY_SENSOR_OPTION: ("Load the GDDR6 memory driver at boot", (
        "The kernel's bc250_memory driver then publishes the temperature of the eight GDDR6 "
        "chips all the time, without pressing Monitor live. To read it, the driver patches the "
        "SMU firmware in memory, and it asks the SMU for readings through the same single "
        "mailbox that Cyan and CPU overclocking use. It does not make the board more stable: "
        "it adds one more user to that mailbox, and if two of them collide the board can "
        "freeze until it is switched off at the plug. Leave it off unless you need the "
        "temperature all the time. The change applies after reboot; to undo the patch, "
        "switch the board off completely."
    ), "Load at boot", "orange"),
    "nosmt": ("Disable simultaneous multithreading", (
        "The CPU runs one thread per core: 6 or 8 threads instead of 12 or 16. Some games "
        "run smoother, others slower; measure yours. The change applies after reboot and "
        "can be restored from Control Center."
    ), "Disable SMT", "orange"),
}
