# BC250 Control Center

[English](../../README.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Русский](README.ru.md) · [Українська](README.uk.md) · [Deutsch](README.de.md) · [Polski](README.pl.md) · [中文](README.zh-CN.md) · [日本語](README.ja.md)

Centre de contrôle Linux pour l’AMD BC-250 : surveillance, GPU, CPU, unités de calcul et ventilateurs dans une application de bureau.

## Captures d’écran

[<img src="../../assets/screenshots/dashboard-overview.png" alt="Tableau de bord BC250 Control Center" width="100%">](https://movacx.github.io/bc250-control-center/gallery/#dashboard)

## Installation

```bash
# Depuis les sources
git clone https://github.com/movacx/bc250-control-center.git
cd bc250-control-center/scripts
./install-local.sh

# Arch, CachyOS et Manjaro
yay -S bc250-control-center-git
```

Pour supprimer une installation locale, exécutez `./uninstall-local.sh` depuis le même dossier.

Les paquets sont disponibles dans la [dernière version](https://github.com/movacx/bc250-control-center/releases). Fedora, Nobara et Bazzite utilisent le même RPM `noarch` :

```bash
sudo dnf install ./bc250-control-center-*.rpm        # Fedora / Nobara
sudo rpm-ostree install ./bc250-control-center-*.rpm # Bazzite / Fedora Atomic
systemctl reboot                                      # après rpm-ostree
sudo apt install ./bc250-control-center_*.deb         # Ubuntu / Debian
```

## Premier démarrage

1. Ouvrez `bc250-control-center`.
2. Dans Dashboard, choisissez **Prepare dependencies**.
3. Vérifiez l’état du module avant d’appliquer une modification.

## Fonctionnalités

- Mesures en direct du CPU, GPU, mémoire, stockage, réseau, températures et ventilateurs.
- Governor GPU, réglage CPU et déverrouillage expérimental des cœurs.
- Contrôle de 24 à 40 Compute Units, PWM et courbes de ventilation.
- Diagnostics, historique, export CSV, échelle de l’interface et navigation à la manette.

## Decky Quick Access optionnel

Sous SteamOS/Game Mode, installez le panneau depuis la section **Decky** en bas du Dashboard. L’application installe Decky Loader si nécessaire, ou installe/répare seulement BC250 Quick Access. Voir le [README Decky](../../integrations/decky/bc250-quick-access/README.md).

## Sécurité

L’overclocking, les changements de Compute Units et le contrôle des ventilateurs peuvent causer gels, arrêts, pertes de données ou dommages matériels. Appliquez un changement à la fois, gardez une méthode de récupération et ne considérez pas les vérifications logicielles comme une validation matérielle.

## Crédits

Le projet intègre le travail de la communauté via des flux explicites et vérifiés. Consultez les [avis tiers](../THIRD_PARTY_NOTICES.md) pour les licences, l’état de vérification et les limites d’intégration.

## Langues

L’interface de bureau prend en charge 30 langues, peut suivre la langue du système ou être modifiée dans Settings : anglais, espagnol, portugais, russe, ukrainien, allemand, français, polonais, chinois, japonais, coréen et plus encore.

## Structure du projet

```text
src/bc250cc/   logique d’application et système
frontends/     adaptateurs Desktop Qt, CLI et Quick Access
privileged/    helpers protégés et politique Polkit
packaging/     métadonnées et installation par distribution
scripts/       lanceurs et installateur local
```

Licence [MIT](../../LICENSE).
