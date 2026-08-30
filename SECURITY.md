# Security policy

BC250 Control Center can invoke privileged operations and can modify hardware frequency, voltage, compute-unit routing, fan PWM and system services. Security reports involving privilege boundaries, package/update provenance or unintended hardware writes should be treated as release-blocking until triaged.

## Reporting

Please report a suspected vulnerability privately to the project maintainer before publishing exploit details. Include the affected commit/version, distribution, exact action, expected/actual privilege boundary, and a minimal reproduction that avoids unnecessary hardware damage.

Do not include credentials, private diagnostic files or unrelated personal data. The built-in diagnostic report is written with user-only permissions; review its contents before sharing it.
