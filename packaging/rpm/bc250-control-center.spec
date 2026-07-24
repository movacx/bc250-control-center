Name:           bc250-control-center
Version:        0.1.0
Release:        64%{?dist}
Summary:        Linux gaming task manager and safe AMD BC-250 control panel

%{!?_userunitdir:%global _userunitdir /usr/lib/systemd/user}

License:        MIT
URL:            https://github.com/movacx/bc250-control-center
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

Requires:       python3
Requires:       python3-pyqt6
Requires:       python3-psutil
Recommends:     lm_sensors
Recommends:     stress
Recommends:     git
Recommends:     pciutils
Recommends:     libdrm
Recommends:     vulkan-tools
Recommends:     cyan-skillfish-governor-smu
Recommends:     umr
Recommends:     libnotify
Recommends:     polkit
Recommends:     kmod
Recommends:     systemd
Recommends:     make
Recommends:     gcc
Recommends:     elfutils-libelf-devel

%description
BC250 Control Center is a PyQt6 task manager and conservative AMD BC-250
control panel. It can prepare local BC250 tools, monitor sensors, manage the
cyan-skillfish GPU governor, run temporary CPU OC through bc250_smu_oc, and
work with BC250 40CU live-manager workflows.

%prep
%autosetup -n %{name}-%{version}

%build
# Pure Python/PyQt6 application. Nothing to build.

%install
install -dm755 %{buildroot}%{_datadir}/bc250-control-center
cp -a mvc %{buildroot}%{_datadir}/bc250-control-center/

install -Dm755 scripts/bc250-control-center %{buildroot}%{_bindir}/bc250-control-center
install -Dm755 scripts/bc250-control-centerd %{buildroot}%{_bindir}/bc250-control-centerd
install -Dm755 mvc/Resources/privileged/bc250-fan-pwm-helper %{buildroot}/usr/libexec/bc250-control-center/bc250-fan-pwm-helper
install -Dm644 packaging/common/polkit/io.github.fabianbeita.bc250-control-center.policy %{buildroot}%{_datadir}/polkit-1/actions/io.github.fabianbeita.bc250-control-center.policy

for size in 32 48 64 128 256 512 1024; do
  install -Dm644 mvc/Resources/icons/bc250-control-center-${size}.png %{buildroot}%{_datadir}/icons/hicolor/${size}x${size}/apps/bc250-control-center.png
done
install -Dm644 packaging/common/desktop/io.github.fabianbeita.bc250-control-center.desktop %{buildroot}%{_datadir}/applications/io.github.fabianbeita.bc250-control-center.desktop
install -Dm644 packaging/common/metainfo/io.github.fabianbeita.bc250-control-center.metainfo.xml %{buildroot}%{_datadir}/metainfo/io.github.fabianbeita.bc250-control-center.metainfo.xml
install -Dm644 packaging/common/systemd-user/bc250-control-centerd.service %{buildroot}%{_userunitdir}/bc250-control-centerd.service

install -Dm644 README.md %{buildroot}%{_docdir}/bc250-control-center/README.md
if [ -d docs ]; then
  for doc in docs/*.md; do
    [ -f "$doc" ] || continue
    install -Dm644 "$doc" %{buildroot}%{_docdir}/bc250-control-center/$(basename "$doc")
  done
fi
install -Dm644 LICENSE %{buildroot}%{_licensedir}/%{name}/LICENSE

%post
# Limpia el icono SVG viejo de builds anteriores para que GNOME/KDE usen el PNG nuevo.
rm -f %{_datadir}/icons/hicolor/scalable/apps/bc250-control-center.svg
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -t -f %{_datadir}/icons/hicolor || true
fi

%postun
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -t -f %{_datadir}/icons/hicolor || true
fi

%posttrans
rm -f %{_datadir}/icons/hicolor/scalable/apps/bc250-control-center.svg
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -t -f %{_datadir}/icons/hicolor || true
fi

%files
%license %{_licensedir}/%{name}/LICENSE
%doc %{_docdir}/bc250-control-center/*.md
%{_bindir}/bc250-control-center
%{_bindir}/bc250-control-centerd
/usr/libexec/bc250-control-center/bc250-fan-pwm-helper
%{_datadir}/polkit-1/actions/io.github.fabianbeita.bc250-control-center.policy
%{_datadir}/bc250-control-center/
%{_datadir}/applications/io.github.fabianbeita.bc250-control-center.desktop
%{_datadir}/metainfo/io.github.fabianbeita.bc250-control-center.metainfo.xml
%{_datadir}/icons/hicolor/*/apps/bc250-control-center.png
%{_userunitdir}/bc250-control-centerd.service

%changelog
* Thu Jul 23 2026 Fabian Beita <fabianbeita@users.noreply.github.com> - 0.1.0-64
- Fix Fedora PWM dependency preparation by treating kernel-headers as a generic userspace header package.
- Require only kernel-devel to match the running kernel and provide a clear recovery path when it is unavailable.
- Prevent an unavailable versioned kernel-headers argument from aborting the full DNF transaction.

* Thu Jul 23 2026 Fabian Beita <fabianbeita@users.noreply.github.com> - 0.1.0-63
- Prepare Bazzite user-space repositories before the transactional reboot so one dependency-button press is sufficient.
- Consolidate Bazzite package layering into one rpm-ostree deployment and detect already pending packages.
- Store nct6687 per kernel under /var, preserve the SELinux module label, and avoid depmod writes to immutable /usr.
- Add a persistent Bazzite service that rebuilds nct6687 after compatible kernel updates and records Secure Boot/SELinux diagnostics.

* Thu Jul 23 2026 Fabian Beita <fabianbeita@users.noreply.github.com> - 0.1.0-62
- Isolate Arch, Manjaro, CachyOS, Debian, Ubuntu, Fedora, Bazzite and SteamOS preparation strategies.
- Fix Manjaro AUR bootstrap by installing and verifying base-devel, fakeroot and Yay before the governor.
- Add truthful failure and reboot-required states for governor, UMR and nct6687 preparation.
- Harden PWM helper creation and Debian package permissions.

* Sat Jul 18 2026 Fabian Beita <fabianbeita@users.noreply.github.com> - 0.1.0-61
- Fix fan PWM preparation dialog translations.

* Sat Jul 18 2026 Fabian Beita <fabianbeita@users.noreply.github.com> - 0.1.0-60
- Add Ubuntu and Debian dependency preparation.
- Add Debian/Ubuntu fan PWM driver setup and package build support.

* Thu Jul 16 2026 Fabian Beita <fabianbeita@users.noreply.github.com> - 0.1.0-59
- Add persistent global GUI zoom from 70% to 150% with Ctrl+Plus, Ctrl+Minus and Ctrl+0.

* Thu Jul 16 2026 Fabian Beita <fabianbeita@users.noreply.github.com> - 0.1.0-58
- Preserve the BC250 monitor layout with its own horizontal scrollbar on narrow windows.

* Thu Jul 16 2026 Fabian Beita <fabianbeita@users.noreply.github.com> - 0.1.0-57
- Allow horizontal scrolling in narrow BC250 GPU, CPU and 40CU panels.

* Thu Jul 16 2026 Fabian Beita <fabianbeita@users.noreply.github.com> - 0.1.0-56
- Label the custom nct6687 module as modules_object_t so SELinux permits systemd to load it.
- Recover automatically from an incomplete nct6687d source directory on Bazzite.

* Thu Jul 16 2026 Fabian Beita <fabianbeita@users.noreply.github.com> - 0.1.0-55
- Load the Bazzite fallback nct6687 module after multi-user.target as documented for BC-250.
- Prefer the kernel-matched module under /var for custom -ogc kernels and preserve loader errors in the journal.
- Keep the visible terminal workflow for Prepare fan PWM.

* Thu Jul 16 2026 Fabian Beita <fabianbeita@users.noreply.github.com> - 0.1.0-52
- Fix Bazzite fan PWM startup loader when nct6687 is already loaded or uses fallback module.

* Thu Jul 16 2026 Fabian Beita <fabianbeita@users.noreply.github.com> - 0.1.0-51
- Add fan PWM control packaging metadata and persistent nct6687 boot loader support.
- Keep hardware helper tools as weak dependencies so Fedora/Bazzite installs are not blocked.

* Fri Jul 10 2026 Fabian Beita <fabianbeita@users.noreply.github.com> - 0.1.0-6
- Move history handling to a dedicated JSONL repository style layer.
- Auto-compact app history after 26 records, keeping the last 6 entries.

* Fri Jul 10 2026 Fabian Beita <fabianbeita@users.noreply.github.com> - 0.1.0-5
- Add full translation audit coverage and new languages: German, French, Japanese, Arabic and Hindi.
- Redesign the 40CU panel around live dispatch dashboard, service/custom profile workflow and discreet paths.
- Add custom CPU OC enable checkbox and GNOME process protection.
- Move local runtime files into Data and ResourceTools style directories with legacy migration.

* Fri Jul 10 2026 Fabian Beita <fabianbeita@users.noreply.github.com> - 0.1.0-4
- Expand terminal launcher support for CachyOS/GNOME, Fedora, Bazzite and mixed desktops.
- Add xdg-terminal-exec, TERMINAL environment detection and more terminal fallbacks.

* Fri Jul 10 2026 Fabian Beita <fabianbeita@users.noreply.github.com> - 0.1.0-3
- Clean stale hicolor scalable SVG during RPM transactions so desktops pick the new PNG icon.
- Refresh hicolor icon cache after install, erase and upgrade.

* Fri Jul 10 2026 Fabian Beita <fabianbeita@users.noreply.github.com> - 0.1.0-2
- Fix Fedora dependency name to python3-pyqt6.
- Move hardware helper tools to Recommends to avoid Bazzite filtered packages blocking install.
- Package PNG icon sizes only to avoid stale SVG being preferred by GNOME.
- Add Ptyxis terminal support for Bazzite/GNOME operations.

* Fri Jul 10 2026 Fabian Beita <fabianbeita@users.noreply.github.com> - 0.1.0-1
- Initial RPM package for Fedora, Nobara and Bazzite testing.
