#!/usr/bin/env python3
"""Build the SteamOS CU backend compatibility copy used by BC250 Control Center.

SteamOS currently exposes the BC-250 PCI device (1002:13fe) to UMR as an
unknown dynamically discovered ASIC named ``amd13fe``.  Passing
``cyan_skillfish.gfx1010`` as the register namespace does not bind that static
ASIC model; UMR therefore cannot find the BC-250-only WGP register definitions.

Keep the F5GO checkout pristine and generate a SteamOS-only runtime copy that:

* binds every UMR read/write to the static ``cyan_skillfish`` model;
* keeps the selected debugfs DRI instance attached to that model;
* forces the static .asic database instead of incomplete IP discovery; and
* validates the SPI WGP register with its real SE/SH bank syntax.

No non-SteamOS backend is modified by this generator.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import stat
import sys

MARKER = "BC250_CONTROL_CENTER_FAST_SELECTOR=5"


DEFAULT_ASIC_REPLACEMENT = 'ASIC="${UMR_ASIC:-cyan_skillfish.gfx1010}"'


def _replace_default_asic(source: str) -> str:
    """Use the GC namespace declared by cyan_skillfish.asic.

    Current UMR databases define the BC-250 graphics IP as ``gfx1010``.  The
    physical ASIC is commonly described as gfx1013, but that name is not a
    register block in the database.  Using gfx1013 makes UMR retry and fail
    before the old code eventually reaches the correct gfx1010 fallback.
    """
    pattern = re.compile(r'^ASIC="\$\{UMR_ASIC:-cyan_skillfish\.gfx10(?:10|13)\}"$', re.MULTILINE)
    match = pattern.search(source)
    if not match:
        raise RuntimeError("The F5GO default ASIC selector was not found; refusing unverified output.")
    return source[:match.start()] + DEFAULT_ASIC_REPLACEMENT + source[match.end():]

DATABASE_VALIDATOR_REPLACEMENT = r'''umr_database_looks_valid() {
  local path="$1" model header common soc15 family blocks vgpr apu extra regfile
  [ -n "$path" ] || return 1
  [ -d "$path" ] || return 1

  # The original F5GO check accepted pci.did by itself. That allowed a partial
  # database with an empty cyan_skillfish.asic to survive forever, after which
  # UMR reports: "Invalid ASIC header line []".
  model="$path/cyan_skillfish.asic"
  [ -s "$model" ] || return 1
  header="$(awk 'NF { print; exit }' "$model" 2>/dev/null)"
  read -r common soc15 family blocks vgpr apu extra <<<"$header"
  [ "$common" = "cyan_skillfish" ] || return 1
  [ -n "$soc15" ] && [ -n "$family" ] && [ -n "$blocks" ] && [ -n "$vgpr" ] && [ -n "$apu" ] || return 1
  [ -z "${extra:-}" ] || return 1
  [[ "$family" =~ ^[0-9]+$ ]] || return 1
  [[ "$blocks" =~ ^[0-9]+$ ]] || return 1
  [[ "$vgpr" =~ ^[0-9]+$ ]] || return 1
  [[ "$apu" =~ ^[01]$ ]] || return 1
  [ "$blocks" -gt 0 ] || return 1
  [ -s "$path/$soc15" ] || return 1

  regfile="$(awk 'NR > 1 && NF == 4 && ($1 ~ /^gfx/ || $2 == "GC") { print $4; exit }' "$model" 2>/dev/null)"
  [ -n "$regfile" ] || return 1
  [ -s "$path/$regfile" ] || return 1
  grep -q 'mmCC_GC_SHADER_ARRAY_CONFIG' "$path/$regfile" || return 1
  grep -q 'mmSPI_PG_ENABLE_STATIC_WGP_MASK' "$path/$regfile" || return 1
  grep -q 'mmRLC_PG_ALWAYS_ON_WGP_MASK' "$path/$regfile" || return 1
}
'''


ENSURE_DATABASE_REPLACEMENT = r'''ensure_umr_database() {
  is_steamos || return 0
  if [ -n "$UMR_DATABASE_PATH" ] && umr_database_looks_valid "$UMR_DATABASE_PATH"; then
    return 0
  fi
  die "CU_UMR_DATABASE_INVALID: the SteamOS user-scoped UMR database is missing or malformed at ${UMR_DATABASE_PATH:-unset}. Run Prepare dependencies from Desktop Mode; register actions never download a database implicitly."
}
'''

MODEL_ARGUMENTS_REPLACEMENT = r'''# BC250_CONTROL_CENTER_FAST_SELECTOR=5
init_umr_instance_args() {
  local help model
  UMR_INSTANCE_ARGS=()
  model="${ASIC%%.*}"
  [ -n "$model" ] || die "could not derive the UMR ASIC model from UMR_ASIC='$ASIC'"

  # A BC-250 can be reported by UMR as the unknown dynamically-discovered
  # model 'amd13fe'.  The register path ($ASIC.$REG_*) does not change the
  # model already bound by UMR.  Bind the real static cyan_skillfish model to
  # the concrete DRI instance for every subsequent read and write.
  help="$("$UMR" --help 2>&1 || true)"
  # force_asic_file is passed unconditionally.  Some distro builds omit the
  # -O option list from --help even though the option is implemented; a real
  # unsupported-option error is more reliable than rejecting such builds here.
  if printf '%s\n' "$help" | grep -q -- '--gpu'; then
    if [ -n "$UMR_INSTANCE" ]; then
      UMR_INSTANCE_ARGS=(-O force_asic_file --gpu "$model@$UMR_INSTANCE")
    else
      # Let UMR choose the first device matching the explicitly forced model.
      UMR_INSTANCE_ARGS=(-O force_asic_file -f "$model")
    fi
  else
    # Compatibility path for older UMR releases without the compound --gpu
    # selector.  Model forcing still precedes the legacy instance selector.
    UMR_INSTANCE_ARGS=(-O force_asic_file -f "$model")
    if [ -n "$UMR_INSTANCE" ]; then
      UMR_INSTANCE_ARGS+=(-i "$UMR_INSTANCE")
    fi
  fi
}

umr_cmd_string() {
  local arg
  printf '%q' "$UMR"
  for arg in "${UMR_INSTANCE_ARGS[@]}"; do
    printf ' %q' "$arg"
  done
}
'''

SELECT_ASIC_REPLACEMENT = r'''select_asic() {
  local out value probe
  local last_out=""

  # mmSPI_PG_ENABLE_STATIC_WGP_MASK is banked per SE/SH.  The central UMR
  # argument array above also forces the static cyan_skillfish model; without
  # that binding UMR sees only the generic 'amd13fe' model and the register
  # path is absent regardless of the bank arguments.
  for probe in bank-mask bank legacy; do
    case "$probe" in
      bank-mask)
        out="$("$UMR" "${UMR_INSTANCE_ARGS[@]}" -r "$ASIC.$REG_SPI" -b 0 0 0xffffffff 2>&1 || true)"
        ;;
      bank)
        out="$("$UMR" "${UMR_INSTANCE_ARGS[@]}" -r "$ASIC.$REG_SPI" -b 0 0 2>&1 || true)"
        ;;
      legacy)
        out="$("$UMR" "${UMR_INSTANCE_ARGS[@]}" -r "$ASIC.$REG_SPI" 2>&1 || true)"
        ;;
    esac
    last_out="$out"
    value="$(printf '%s\n' "$out" | parse_hex)"
    if [ -n "$value" ] && ! umr_output_failed "$out"; then
      return 0
    fi
  done

  printf '%s\n' "$last_out" >&2
  die "failed to bind/read $ASIC.$REG_SPI with the static cyan_skillfish model. Verify UMR supports --gpu/-f plus -O force_asic_file, the DRI instance, and UMR_DATABASE_PATH."
}
'''


def _replace_database_validator(source: str) -> str:
    pattern = re.compile(
        r"(?ms)^umr_database_looks_valid\(\) \{.*?^\}\n"
        r"(?=\n(?:download_umr_database|ensure_umr_database)\(\) \{)"
    )
    match = pattern.search(source)
    if not match:
        raise RuntimeError(
            "The F5GO umr_database_looks_valid() function was not found in the expected form; "
            "refusing to generate an unverified backend."
        )
    current = match.group(0)
    if "Invalid ASIC header line" in current and "mmSPI_PG_ENABLE_STATIC_WGP_MASK" in current:
        return source
    return source[:match.start()] + DATABASE_VALIDATOR_REPLACEMENT.rstrip("\n") + source[match.end():]


def _replace_ensure_database(source: str) -> str:
    pattern = re.compile(
        r"(?ms)^ensure_umr_database\(\) \{.*?^\}\n"
        r"(?=\nneed_umr\(\) \{)"
    )
    match = pattern.search(source)
    if not match:
        raise RuntimeError(
            "The F5GO ensure_umr_database() function was not found; refusing unverified output."
        )
    return source[:match.start()] + ENSURE_DATABASE_REPLACEMENT.rstrip("\n") + source[match.end():]


def _replace_model_argument_functions(source: str) -> str:
    pattern = re.compile(
        r"(?ms)^init_umr_instance_args\(\) \{.*?^\}\n\n"
        r"^umr_cmd_string\(\) \{.*?^\}\n"
    )
    match = pattern.search(source)
    if not match:
        raise RuntimeError(
            "The F5GO init_umr_instance_args()/umr_cmd_string() functions were not found "
            "in the expected form; refusing to generate an unverified backend."
        )
    current = match.group(0)
    if "force_asic_file" in current and ("--gpu" in current or " -f " in current):
        return source[:match.start()] + f"# {MARKER}\n" + current + source[match.end():]
    return source[:match.start()] + MODEL_ARGUMENTS_REPLACEMENT.rstrip("\n") + "\n" + source[match.end():]


def _replace_selector_probe(source: str) -> str:
    pattern = re.compile(r"(?ms)^select_asic\(\) \{.*?^\}\n(?=\nreg_candidates\(\) \{)")
    match = pattern.search(source)
    if not match:
        raise RuntimeError(
            "The F5GO select_asic() function was not found in the expected form; "
            "refusing to generate an unverified backend."
        )
    current = match.group(0)
    # Preserve an upstream selector only when it is both bank-aware and checks
    # UMR output failures.  The model binding itself is handled centrally by
    # init_umr_instance_args(), so every later read/write receives it too.
    if "-b 0 0" in current and "umr_output_failed" in current:
        return source
    return source[:match.start()] + SELECT_ASIC_REPLACEMENT.rstrip("\n") + source[match.end():]


def patch_text(source: str) -> str:
    if MARKER in source:
        return source
    patched = _replace_default_asic(source)
    patched = _replace_database_validator(patched)
    patched = _replace_ensure_database(patched)
    patched = _replace_model_argument_functions(patched)
    patched = _replace_selector_probe(patched)
    if MARKER not in patched:
        raise RuntimeError("SteamOS CU backend marker was not emitted; refusing incomplete output.")
    return patched


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    destination = args.destination.expanduser().resolve()
    if source == destination:
        raise RuntimeError("Source and destination must differ; the upstream checkout must stay pristine.")
    text = source.read_text(encoding="utf-8")
    patched = patch_text(text)

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(patched, encoding="utf-8")
    mode = source.stat().st_mode
    os.chmod(temporary, (mode & 0o777) | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    temporary.replace(destination)
    print(f"Prepared SteamOS CU compatibility backend: {destination}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
