# BC250 Control Center

[English](../../README.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Русский](README.ru.md) · [Українська](README.uk.md) · [Deutsch](README.de.md) · [Polski](README.pl.md) · [中文](README.zh-CN.md) · [日本語](README.ja.md)

Centre de contrôle pour l’AMD BC-250 sous Linux. Surveillance, contrôle du GPU, réglage du CPU, Compute Units, ventilateurs et mise à jour du BIOS réunis dans une seule application de bureau, avec des limites claires et des vérifications avant chaque changement matériel.

## Captures d’écran

[<img src="../../assets/screenshots/dashboard-overview.png" alt="Tableau de bord de BC250 Control Center" width="100%">](https://movacx.github.io/bc250-control-center/gallery/#dashboard)

[Voir toutes les captures →](https://movacx.github.io/bc250-control-center/gallery/#dashboard)

## Installation

### Arch, CachyOS et SteamOS (AUR)

```bash
yay -S bc250-control-center-git
```

### Paquets de chaque version

Téléchargez le paquet de votre système depuis la [dernière version](https://github.com/movacx/bc250-control-center/releases/latest) :

| Système | Fichier |
|---|---|
| Arch / CachyOS / Manjaro | `bc250-control-center-<version>-any.pkg.tar.zst` |
| Fedora / Nobara / Bazzite | `bc250-control-center-<version>.noarch.rpm` |
| Ubuntu / Debian | `bc250-control-center_<version>_all.deb` |

```bash
# Arch / CachyOS / Manjaro
sudo pacman -U ./bc250-control-center-*-any.pkg.tar.zst

# Fedora / Nobara
sudo dnf install ./bc250-control-center-*.rpm

# Bazzite / Fedora Atomic: le même RPM, puis redémarrez sur le nouveau déploiement
sudo rpm-ostree install ./bc250-control-center-*.rpm
systemctl reboot

# Ubuntu / Debian
sudo apt install ./bc250-control-center_*.deb
```

Sous Debian et Ubuntu, utilisez `apt install` et non `dpkg -i` : APT télécharge ainsi aussi les dépendances. Si `dpkg -i` a laissé le paquet à moitié installé, `sudo apt --fix-broken install` le répare.

### Mises à jour

Inutile de revenir sur cette page. Quand une nouvelle version sort, le tableau de bord le signale, montre ce qui a changé et l’installe avec le gestionnaire de paquets de votre système, après avoir vérifié son SHA-256.

Sous SteamOS, la mise à jour désactive la protection en lecture seule, installe puis la réactive. Une mise à jour de SteamOS supprime tout ce qui a été installé dans le système, y compris cette application : ouvrez **Reinstall BC250 Control Center** depuis le menu du mode Bureau, puis préparez à nouveau les dépendances. SteamOS demande le mot de passe de `deck` ; si vous n'en avez jamais défini, exécutez d'abord `passwd` dans Konsole.

**Vous venez de la 1.19 ?** Son outil de mise à jour ne sait pas installer de paquets. Mettez à jour une fois à la main avec le paquet de la [dernière version](https://github.com/movacx/bc250-control-center/releases/latest) ; ensuite l'application se met à jour seule. Sous Bazzite, remplacez la 1.19 en une étape puis redémarrez ; si vous aviez utilisé install-local.sh, retirez d'abord cette copie :

```bash
# Bazzite / Fedora Atomic
sudo rpm-ostree uninstall bc250-control-center --install ./bc250-control-center-*.noarch.rpm
systemctl reboot

# install-local.sh
bash scripts/uninstall-local.sh
```

## Premier démarrage

1. Ouvrez **BC250 Control Center**.
2. L’écran d’accueil demande la langue, l’apparence et la barre latérale, et propose d’installer les outils dont la carte a besoin. Tout se change ensuite dans les **Paramètres**.
3. Si vous le souhaitez, suivez la visite guidée : elle parcourt chaque module et explique ce que chacun modifie sur la carte.

Avant tout changement, consultez l’état du module : il indique ce qui est prêt, ce qui manque et pourquoi.

## Fonctionnalités

**Tableau de bord et surveillance**
- Tableau de bord avec processeur, graphismes et refroidissement, cœurs en direct, température de chaque puce GDDR6, rails d’alimentation (avec le mod I2C) et BIOS installé.
- Module Performances avec graphiques CPU, GPU, VRAM, RAM, disque et réseau, et une vue Capteurs avec minimum, moyenne et maximum.

**Matériel**
- **GPU :** plages sûres du governor pour Cyan et Oberon, laboratoire de tension et points au-delà de 2000 MHz.
- **CPU / SMU :** réglage temporaire et persistant, test de stabilité et déverrouillage expérimental des cœurs cachés.
- **Compute Units :** de 24 à 40 CU, avec l’état en direct et l’état au démarrage séparés.
- **Ventilateurs :** contrôle PWM manuel, courbes par température, profils conservés au redémarrage et export vers un fichier ou vers Decky.
- **Mémoire :** taille de la VRAM, ZRAM, ZSWAP et fichier d’échange.
- **Firmware (BIOS) :** prépare une clé USB de mise à jour avec P3.00 Chipset Menu, MeiMeiDXE v3, P5.00, P3.00 ou P2.00, chaque fichier vérifié.

**Système**
- Préparation des dépendances adaptée à chaque distribution, avec un terminal intégré qui montre chaque commande.
- Correctifs de compatibilité : GFX1013 et async compute, FSR4 par jeu, télémétrie et ACPI.
- Dolby Digital 5.1 en HDMI pour les amplis et barres de son, et contrôle du téléviseur en HDMI-CEC avec le cecd de Valve.
- Pilotes Wi-Fi, Bluetooth et imprimantes depuis les dépôts officiels de votre distribution.
- Diagnostics, historique et export des mesures en CSV.

**Interface**
- Thèmes Clair, Sombre et Bleu nuit, styles Standard et Sobre, 10 couleurs d’accentuation et échelle de 70 % à 150 %.
- 30 langues et navigation à la manette.

## Decky Quick Access (optionnel)

Un panneau pour le menu d’accès rapide de SteamOS et le mode Jeu de Steam. Il apporte les réglages du quotidien (GPU, CU, CPU, ventilateurs et VRAM) sans quitter le jeu ; la configuration avancée reste dans l’application de bureau.

- **Profils par jeu :** attribuez à chaque jeu un profil GPU et ventilateurs. Il s’applique à l’ouverture du jeu et tout revient comme avant à sa fermeture.
- **Async compute en direct :** indique si le jeu utilise le calcul asynchrone, et dans quelle mesure.
- **Préréglages de ventilateurs :** avec les noms et vitesses exportés depuis le bureau.

Pour l’installer, ouvrez le **Tableau de bord**, descendez jusqu’à la section **Decky** et choisissez l’action proposée. Si Decky Loader manque, l’application l’installe ; s’il est déjà là, elle installe ou répare seulement BC250 Quick Access. La préparation normale des dépendances n’installe jamais Decky d’elle-même.

Plus de détails dans le [README de Decky](../../integrations/decky/bc250-quick-access/README.md).

## Sécurité

L’overclocking, les changements de Compute Units, le contrôle des ventilateurs et la mise à jour du BIOS peuvent figer ou éteindre le système, faire perdre des données ou endommager le matériel. Appliquez un changement à la fois, gardez toujours un moyen de revenir en arrière et ne prenez pas les vérifications de l’application pour une garantie matérielle.

## Outils externes et crédits

BC250 Control Center s’appuie sur le travail de la communauté et ne revendique aucun de ces projets. Chaque outil n’est utilisé qu’à travers des flux explicites et vérifiés.

**GPU**
- [cyan-skillfish-governor](https://github.com/filippor/cyan-skillfish-governor/tree/smu): governor du GPU.
- [Oberon Governor](https://gitlab.com/mothenjoyer69/oberon-governor): governor alternatif pris en charge.
- [bc250-gfx1013-fix](https://github.com/DryhoppedIPA/bc250-gfx1013-fix) et [bc250-steamos](https://github.com/keyboardspecialist/bc250-steamos): noyau et Mesa/RADV pour GFX1013.
- [linux-cachyos-bc250](https://github.com/MastaG/linux-cachyos-bc250): noyau et Mesa/RADV appariés pour Arch/CachyOS.
- [bc250-async-compute-bazzite](https://github.com/tri3gubki-ops/bc250-async-compute-bazzite): async compute sur Bazzite 44.
- [bc250-fsr4](https://github.com/dmorazasanchez/bc250-fsr4) et [bc250-fsr4-fork](https://github.com/daniel-h-0/bc250-fsr4-fork) (OptiScaler Client): FSR4 par jeu.
- [HelixSR](https://github.com/lonewolf0622/HelixSR): reconstruction DLSS Model E pour les jeux FSR 3.1, par jeu.

**CPU et Compute Units**
- [bc250_smu_oc](https://github.com/bc250-collective/bc250_smu_oc): détection et réglage du CPU via le SMU.
- [bc250-core-unlock](https://github.com/rw-r-r-0644/bc250-core-unlock) et [bc250-efi-core-unlock](https://github.com/Hexxeh/bc250-efi-core-unlock): déverrouillage des cœurs.
- [bc250-cu-live-manager](https://github.com/WinnieLV/bc250-cu-live-manager), [SteamOS](https://github.com/F5GO/bc250-cu-live-manager-SteamOS) et [bc250-40cu-unlock](https://github.com/duggasco/bc250-40cu-unlock): Compute Units.
- [bc250-acpi-fix](https://github.com/e-tho/bc250-acpi-fix): états de performance du CPU via ACPI.

**Capteurs, mémoire et ventilateurs**
- [BC250-Telemetry](https://github.com/onlinermm/BC250-Telemetry): télémétrie des régulateurs de tension (VRM).
- [bc250-memory-temperature](https://github.com/pan-Rijovich/bc250-memory-temperature): température de la mémoire GDDR6.
- [bc250_memcfg](https://github.com/fanoush/bc250_memcfg): taille de la VRAM via la CMOS.
- [nct6687d](https://github.com/Fred78290/nct6687d): capteurs NCT et PWM des ventilateurs.
- [linux-cec](https://gitlab.steamos.cloud/holo/linux-cec): cecd, le démon HDMI-CEC de Valve.

**Firmware**
- [bc250-bios](https://gitlab.com/TuxThePenguin0/bc250-bios): BIOS P3.00 d’origine et Chipset Menu.
- [AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script](https://github.com/Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script): UEFI Shell et MeiMeiDXE v3.
- [BC-250](https://github.com/kenavru/BC-250): copie du kit de mise à jour ASRock (P2.00 et P5.00).
- [bc250-custom-bios-logo](https://github.com/tmghd272/bc250-custom-bios-logo): logo de démarrage personnalisé.

Les licences, l’état de vérification et le périmètre exact de chaque intégration figurent dans les [mentions tierces](../THIRD_PARTY_NOTICES.md).

## Structure du projet

```text
bc250-control-center/
├── src/bc250cc/          Le cœur, sans interface graphique
│   ├── domain/           Règles et limites de chaque module (GPU, CPU, CU, ventilateurs, firmware…)
│   ├── application/      Cas d’usage qui combinent ces règles
│   ├── infrastructure/   Accès au système : capteurs, services, paquets, GitHub
│   ├── platform/         Différences entre distributions et systèmes d’init
│   └── shared/           Version, chemins et contrats partagés par tous les processus
├── frontends/
│   ├── desktop/          Application de bureau Qt
│   │   ├── pages/        Un fichier par module (tableau de bord, GPU, CPU, ventilateurs, firmware…)
│   │   ├── components/   Éléments d’interface réutilisables
│   │   ├── onboarding/   Écran d’accueil et visite guidée
│   │   ├── console/      Terminal intégré
│   │   ├── theme/        Thèmes, styles, couleurs et icônes
│   │   └── i18n/         Traductions en 30 langues
│   └── cli.py            Mode ligne de commande
├── integrations/decky/   Plugin Decky Quick Access pour le mode Jeu
├── privileged/           Ce qui s’exécute en root, isolé et vérifié
│   ├── helpers/          Un assistant par tâche privilégiée
│   ├── lib/              Code partagé par ces assistants
│   └── policies/         Autorisations Polkit
├── packaging/            Paquets .pkg.tar.zst, .rpm et .deb, et le PKGBUILD de l’AUR
├── scripts/              Lanceurs, installateur local et utilitaires système
├── assets/               Icônes, captures et galerie web
├── docs/                 Documentation, mentions tierces et traductions de ce README
└── tests/                Plus de 4000 tests automatisés
```

Sous [licence MIT](../../LICENSE).
