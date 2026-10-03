#!/usr/bin/env bash

ensure_arch_build_toolchain() {
  if have git && have makepkg && have fakeroot; then
    return 0
  fi
  bold "Installing Arch/AUR build toolchain"
  as_root pacman -S --needed --noconfirm base-devel git fakeroot debugedit
  verify_command git
  verify_command makepkg
  verify_command fakeroot
}

ensure_aur_helper() {
  AUR_HELPER=""
  # AUR helpers still require makepkg/fakeroot to build packages. Verify this
  # before accepting an already-installed yay/paru binary.
  ensure_arch_build_toolchain
  if have yay; then
    AUR_HELPER="$(command -v yay)"
    info "AUR helper found: $AUR_HELPER"
    return 0
  fi
  if have paru; then
    AUR_HELPER="$(command -v paru)"
    info "AUR helper found: $AUR_HELPER"
    return 0
  fi

  # Manjaro and some Arch derivatives publish yay in an official repository.
  if pacman -Si yay >/dev/null 2>&1; then
    bold "Installing yay from distribution repository"
    as_root pacman -S --needed --noconfirm yay
    hash -r
    verify_command yay
    AUR_HELPER="$(command -v yay)"
    return 0
  fi

  require_user_build
  export_parallel_build_env
  bold "Building yay from the official AUR package"
  local yay_dir="${XDG_CACHE_HOME:-$HOME/.cache}/bc250-control-center/aur/yay"
  clone_or_update https://aur.archlinux.org/yay.git "$yay_dir"
  (
    cd "$yay_dir"
    run makepkg --cleanbuild --clean --force --syncdeps --install --needed --noconfirm
  )
  hash -r
  verify_command yay
  AUR_HELPER="$(command -v yay)"
}

install_aur_package_direct() {
  local package="$1" rebuild="${2:-}"
  ensure_arch_build_toolchain
  require_user_build
  export_parallel_build_env
  local package_dir="${XDG_CACHE_HOME:-$HOME/.cache}/bc250-control-center/aur/$package"
  clone_or_update "https://aur.archlinux.org/${package}.git" "$package_dir"
  (
    cd "$package_dir"
    # --needed skips a package whose version is already installed, which is
    # exactly the case of one that must be built again against new libraries.
    if [[ "$rebuild" == "rebuild" ]]; then
      run makepkg --cleanbuild --clean --force --syncdeps --install --noconfirm
    else
      run makepkg --cleanbuild --clean --force --syncdeps --install --needed --noconfirm
    fi
  )
}

# install_aur_package <package> [rebuild]
# "rebuild" builds it again even though the same version is installed: for a
# package that still exists but no longer starts because a library it was
# linked against was replaced.
install_aur_package() {
  local package="$1" rebuild="${2:-}"
  ensure_aur_helper
  if [[ -n "$AUR_HELPER" && -x "$AUR_HELPER" ]]; then
    bold "Installing AUR package: $package"
    export_parallel_build_env
    local -a helper_args=(-S --needed --noconfirm)
    if [[ "$rebuild" == "rebuild" ]]; then
      # paru and yay both take --rebuild: always build the target.
      helper_args=(-S --rebuild --noconfirm)
    fi
    # --answerclean/--answerdiff are yay options. Passing them to paru makes a
    # valid CachyOS installation fail before package resolution starts.
    if [[ "$(basename "$AUR_HELPER")" == "yay" ]]; then
      helper_args+=(--answerclean None --answerdiff None)
    fi
    if run "$AUR_HELPER" "${helper_args[@]}" "$package"; then
      return 0
    fi
    warn "$AUR_HELPER failed; falling back to a clean makepkg build for $package"
  fi
  install_aur_package_direct "$package" "$rebuild"
}
