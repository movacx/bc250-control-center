Name:           bc250-control-center
Version:        0.1.0
Release:        50%{?dist}
Summary:        Linux gaming task manager and safe AMD BC-250 control panel

%{!?_userunitdir:%global _userunitdir /usr/lib/systemd/user}

License:        MIT
URL:            https://github.com/movacx/bc250-control-center
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

Requires:       python3
Requires:       python3-pyqt6
Requires:       python3-psutil
Requires:       lm_sensors
Requires:       stress
Recommends:     git
Recommends:     pciutils
Recommends:     libdrm
Recommends:     vulkan-tools
Recommends:     cyan-skillfish-governor-smu
Recommends:     umr
Recommends:     libnotify
Recommends:     polkit

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
%{_datadir}/bc250-control-center/
%{_datadir}/applications/io.github.fabianbeita.bc250-control-center.desktop
%{_datadir}/metainfo/io.github.fabianbeita.bc250-control-center.metainfo.xml
%{_datadir}/icons/hicolor/*/apps/bc250-control-center.png
%{_userunitdir}/bc250-control-centerd.service

%changelog
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
