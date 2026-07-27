Name:           bc250-control-center
Version:        1.17.22
Release:        3%{?dist}
Summary:        Linux gaming task manager and safe AMD BC-250 control panel

%{!?_userunitdir:%global _userunitdir /usr/lib/systemd/user}

License:        MIT
URL:            https://github.com/movacx/bc250-control-center
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

Requires:       python3
Requires:       python3-pyqt6
Requires:       qt6-qtsvg
Requires:       python3-psutil
Recommends:     python3-evdev
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
install -Dm644 packaging/common/polkit/io.github.movacx.bc250-control-center.policy %{buildroot}%{_datadir}/polkit-1/actions/io.github.movacx.bc250-control-center.policy

for size in 32 48 64 128 256 512 1024; do
  install -Dm644 mvc/Resources/icons/bc250-control-center-${size}.png %{buildroot}%{_datadir}/icons/hicolor/${size}x${size}/apps/bc250-control-center.png
done
install -Dm644 packaging/common/desktop/io.github.movacx.bc250-control-center.desktop %{buildroot}%{_datadir}/applications/io.github.movacx.bc250-control-center.desktop
install -Dm644 packaging/common/metainfo/io.github.movacx.bc250-control-center.metainfo.xml %{buildroot}%{_datadir}/metainfo/io.github.movacx.bc250-control-center.metainfo.xml
install -Dm644 packaging/common/systemd-user/bc250-control-centerd.service %{buildroot}%{_userunitdir}/bc250-control-centerd.service

install -Dm644 README.md %{buildroot}%{_docdir}/bc250-control-center/README.md
install -Dm644 docs/ARQUITECTURA_MVC.md %{buildroot}%{_docdir}/bc250-control-center/ARQUITECTURA_MVC.md
install -Dm644 docs/THIRD_PARTY_NOTICES.md %{buildroot}%{_docdir}/bc250-control-center/THIRD_PARTY_NOTICES.md
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
%{_datadir}/polkit-1/actions/io.github.movacx.bc250-control-center.policy
%{_datadir}/bc250-control-center/
%{_datadir}/applications/io.github.movacx.bc250-control-center.desktop
%{_datadir}/metainfo/io.github.movacx.bc250-control-center.metainfo.xml
%{_datadir}/icons/hicolor/*/apps/bc250-control-center.png
%{_userunitdir}/bc250-control-centerd.service

%changelog
* Mon Jul 27 2026 Movacx <movacx@users.noreply.github.com> - 1.17.22-3
- Resolve the SteamOS Cyan Skillfish UMR selector for the F5GO 40CU backend.

* Mon Jul 27 2026 Movacx <movacx@users.noreply.github.com> - 1.17.22-2
- Require Qt SVG support so interface icons render on Linux Mint, Ubuntu and Fedora-family desktops.

* Sun Jul 26 2026 Movacx <movacx@users.noreply.github.com> - 1.17.22-1
- Improve controller compatibility, focus navigation, and on-screen numeric input.
- Keep voltage profile presets locked unless Custom mode is selected.
- Prepare refreshed distribution packages for Fedora, Bazzite, and Debian.

* Sun Jul 26 2026 Movacx <movacx@users.noreply.github.com> - 1.17.21-1
- Ship the definitive restructured PyQt6 interface with responsive pages and optional gamepad navigation.
- Add exact WGP mask verification for graphical Compute Units changes.
- Refresh packaging metadata and document the six supported languages.
