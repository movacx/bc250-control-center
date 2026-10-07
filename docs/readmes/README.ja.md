# BC250 Control Center

[English](../../README.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Русский](README.ru.md) · [Українська](README.uk.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Polski](README.pl.md) · [中文](README.zh-CN.md)

Linux 向け AMD BC-250 コントロールセンター。監視、GPU 制御、CPU チューニング、Compute Units、ファン、BIOS 更新を 1 つのデスクトップアプリにまとめ、ハードウェアを変更する前には明確な制限と検証を行います。

## スクリーンショット

[<img src="../../assets/screenshots/dashboard-overview.png" alt="BC250 Control Center ダッシュボード" width="100%">](https://movacx.github.io/bc250-control-center/gallery/#dashboard)

[すべてのスクリーンショットを見る →](https://movacx.github.io/bc250-control-center/gallery/#dashboard)

## インストール

### Arch、CachyOS、SteamOS（AUR）

```bash
yay -S bc250-control-center-git
```

### リリースパッケージ

[最新リリース](https://github.com/movacx/bc250-control-center/releases/latest)からお使いのシステム用のパッケージをダウンロードします:

| システム | ファイル |
|---|---|
| Arch / CachyOS / Manjaro | `bc250-control-center-<バージョン>-any.pkg.tar.zst` |
| Fedora / Nobara / Bazzite | `bc250-control-center-<バージョン>.noarch.rpm` |
| Ubuntu / Debian | `bc250-control-center_<バージョン>_all.deb` |

```bash
# Arch / CachyOS / Manjaro
sudo pacman -U ./bc250-control-center-*-any.pkg.tar.zst

# Fedora / Nobara
sudo dnf install ./bc250-control-center-*.rpm

# Bazzite / Fedora Atomic: 同じ RPM をインストールし、新しいデプロイメントで再起動
sudo rpm-ostree install ./bc250-control-center-*.rpm
systemctl reboot

# Ubuntu / Debian
sudo apt install ./bc250-control-center_*.deb
```

Debian と Ubuntu では `dpkg -i` ではなく `apt install` を使ってください。APT が依存関係もダウンロードします。`dpkg -i` でパッケージが中途半端になった場合は `sudo apt --fix-broken install` で修復できます。

### アップデート

このページに戻る必要はありません。新しいバージョンが出るとダッシュボードが知らせ、変更内容を表示し、SHA-256 を確認したうえでシステムのパッケージマネージャーでインストールします。

SteamOS では、アップデートが読み取り専用の保護を解除してインストールし、再び有効にします。SteamOS のアップデートはシステムにインストールされたものをすべて削除し、このアプリも例外ではありません。デスクトップモードのメニューから **Reinstall BC250 Control Center** を開き、依存関係をもう一度準備してください。SteamOS は `deck` のパスワードを求めます。設定したことがない場合は、先に Konsole で `passwd` を実行してください。

**1.19 から移行しますか?** 1.19 の内蔵アップデーターはパッケージをインストールできません。[最新リリース](https://github.com/movacx/bc250-control-center/releases/latest)のパッケージで一度だけ手動で更新すれば、以降はアプリが自動で更新します。Bazzite では 1.19 を一度の操作で置き換えて再起動し、install-local.sh でインストールした場合は先にそのコピーを削除してください:

```bash
# Bazzite / Fedora Atomic
sudo rpm-ostree uninstall bc250-control-center --install ./bc250-control-center-*.noarch.rpm
systemctl reboot

# install-local.sh
bash scripts/uninstall-local.sh
```

## 初回起動

1. **BC250 Control Center** を開きます。
2. ようこそ画面で言語、外観、サイドバーを選び、ボードに必要なツールのインストールを案内します。すべて後から**設定**で変更できます。
3. 必要ならガイドツアーを進めてください。各モジュールを回り、それぞれがボードの何を変えるかを説明します。

変更を適用する前に、モジュールの状態を確認してください。準備ができているもの、足りないもの、その理由が表示されます。

## 機能

**ダッシュボードと監視**
- プロセッサー、グラフィックス、冷却、リアルタイムのコア、各 GDDR6 チップの温度、電源レール（I2C 改造時）、インストール済み BIOS を表示するダッシュボード。
- CPU、GPU、VRAM、RAM、ディスク、ネットワークのグラフと、最小・平均・最大を示すセンサービューを備えたパフォーマンスモジュール。

**ハードウェア**
- **GPU:** Cyan と Oberon の安全なガバナー範囲、電圧ラボ、2000 MHz を超えるポイント。
- **CPU / SMU:** 一時的および永続的なチューニング、安定性テスト、実験的な隠しコアのアンロック。
- **Compute Units:** 24〜40 CU。現在の状態と起動時の状態を分けて表示。
- **ファン:** 手動 PWM 制御、温度カーブ、再起動後も保持されるプロファイル、ファイルや Decky へのエクスポート。
- **メモリ:** VRAM サイズ、ZRAM、ZSWAP、スワップファイル。
- **ファームウェア（BIOS）:** P3.00 Chipset Menu、MeiMeiDXE v3、P5.00、P3.00、P2.00 の更新用 USB を作成し、各ファイルを検証。

**システム**
- ディストリビューションごとに合わせた依存関係の準備。内蔵ターミナルですべてのコマンドを表示。
- 互換性の修正: GFX1013 と async compute、ゲームごとの FSR4、テレメトリ、ACPI。
- ディストリビューション公式リポジトリからの Wi-Fi、Bluetooth、プリンタードライバー。
- 診断、履歴、CSV へのメトリクスのエクスポート。

**インターフェース**
- ライト、ダーク、ナイトブルーのテーマ、標準とフォーマルのスタイル、10 色のアクセント、70 %〜150 % のスケール。
- 30 言語とコントローラー操作。

## Decky Quick Access（オプション）

SteamOS のクイックアクセスメニューと Steam のゲームモード向けのパネルです。日常的な操作（GPU、CU、CPU、ファン、VRAM）をゲームを離れずに使えます。高度な設定はデスクトップアプリに残ります。

- **ゲームごとのプロファイル:** 各ゲームに GPU とファンのプロファイルを割り当てます。ゲーム起動時に適用され、終了すると元の状態に戻ります。
- **リアルタイムの async compute:** ゲームが非同期コンピュートを使っているか、どの程度かを表示します。
- **ファンのプリセット:** デスクトップからエクスポートした名前と回転数で使えます。

インストールするには、**ダッシュボード**を開いて **Decky** セクションまでスクロールし、表示された操作を選びます。Decky Loader がなければアプリがインストールし、すでにあれば BC250 Quick Access だけをインストールまたは修復します。通常の依存関係の準備で Decky が自動的にインストールされることはありません。

詳しくは [Decky の README](../../integrations/decky/bc250-quick-access/README.md) をご覧ください。

## 安全性

オーバークロック、Compute Units の変更、ファン制御、BIOS の更新は、システムのフリーズやシャットダウン、データの損失、ハードウェアの損傷を引き起こすことがあります。変更は 1 つずつ行い、常に元に戻す手段を用意し、アプリのチェックをハードウェアの保証とみなさないでください。

## 外部ツールとクレジット

BC250 Control Center はコミュニティの成果の上に成り立っており、これらのプロジェクトを自分のものとは主張しません。各ツールは明示的でレビュー済みの手順でのみ使用されます。

**GPU**
- [cyan-skillfish-governor](https://github.com/filippor/cyan-skillfish-governor/tree/smu): GPU ガバナー。
- [Oberon Governor](https://gitlab.com/mothenjoyer69/oberon-governor): サポートされている代替ガバナー。
- [bc250-gfx1013-fix](https://github.com/DryhoppedIPA/bc250-gfx1013-fix) と [bc250-steamos](https://github.com/keyboardspecialist/bc250-steamos): GFX1013 向けのカーネルと Mesa/RADV。
- [linux-cachyos-bc250](https://github.com/MastaG/linux-cachyos-bc250): Arch/CachyOS 向けに対応付けたカーネルと Mesa/RADV。
- [bc250-async-compute-bazzite](https://github.com/tri3gubki-ops/bc250-async-compute-bazzite): Bazzite 44 での async compute。
- [bc250-fsr4](https://github.com/dmorazasanchez/bc250-fsr4) と [bc250-fsr4-fork](https://github.com/daniel-h-0/bc250-fsr4-fork) (OptiScaler Client): ゲームごとの FSR4。
- [HelixSR](https://github.com/lonewolf0622/HelixSR): FSR 3.1 ゲーム向けの DLSS Model E 再構成 (ゲームごと)。

**CPU と Compute Units**
- [bc250_smu_oc](https://github.com/bc250-collective/bc250_smu_oc): SMU による CPU の検出とチューニング。
- [bc250-core-unlock](https://github.com/rw-r-r-0644/bc250-core-unlock) と [bc250-efi-core-unlock](https://github.com/Hexxeh/bc250-efi-core-unlock): コアのアンロック。
- [bc250-cu-live-manager](https://github.com/WinnieLV/bc250-cu-live-manager), [SteamOS](https://github.com/F5GO/bc250-cu-live-manager-SteamOS) と [bc250-40cu-unlock](https://github.com/duggasco/bc250-40cu-unlock): Compute Units。
- [bc250-acpi-fix](https://github.com/e-tho/bc250-acpi-fix): ACPI による CPU のパフォーマンスステート。

**センサー、メモリ、ファン**
- [BC250-Telemetry](https://github.com/onlinermm/BC250-Telemetry): 電圧レギュレーター（VRM）のテレメトリ。
- [bc250-memory-temperature](https://github.com/pan-Rijovich/bc250-memory-temperature): GDDR6 メモリの温度。
- [bc250_memcfg](https://github.com/fanoush/bc250_memcfg): CMOS による VRAM サイズ。
- [nct6687d](https://github.com/Fred78290/nct6687d): NCT センサーとファン PWM。

**ファームウェア**
- [bc250-bios](https://gitlab.com/TuxThePenguin0/bc250-bios): 純正 P3.00 と Chipset Menu の BIOS。
- [AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script](https://github.com/Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script): UEFI Shell と MeiMeiDXE v3。
- [BC-250](https://github.com/kenavru/BC-250): ASRock 更新キットのミラー（P2.00 と P5.00）。
- [bc250-custom-bios-logo](https://github.com/tmghd272/bc250-custom-bios-logo): カスタム起動ロゴ。

ライセンス、レビュー状況、各統合の正確な範囲は[サードパーティ通知](../THIRD_PARTY_NOTICES.md)に記載しています。

## プロジェクト構成

```text
bc250-control-center/
├── src/bc250cc/          コア部分（GUI なし）
│   ├── domain/           各モジュールのルールと制限（GPU、CPU、CU、ファン、ファームウェアなど）
│   ├── application/      それらのルールを組み合わせるユースケース
│   ├── infrastructure/   システムへのアクセス: センサー、サービス、パッケージ、GitHub
│   ├── platform/         ディストリビューションと init システムの違い
│   └── shared/           全プロセスで共有するバージョン、パス、契約
├── frontends/
│   ├── desktop/          Qt デスクトップアプリ
│   │   ├── pages/        モジュールごとに 1 ファイル（ダッシュボード、GPU、CPU、ファン、ファームウェアなど）
│   │   ├── components/   再利用可能な UI 部品
│   │   ├── onboarding/   ようこそ画面とガイドツアー
│   │   ├── console/      内蔵ターミナル
│   │   ├── theme/        テーマ、スタイル、色、アイコン
│   │   └── i18n/         30 言語の翻訳
│   └── cli.py            コマンドラインモード
├── integrations/decky/   ゲームモード用の Decky Quick Access プラグイン
├── privileged/           root で動く部分（分離・レビュー済み）
│   ├── helpers/          特権タスクごとのヘルパー
│   ├── lib/              ヘルパー間で共有するコード
│   └── policies/         Polkit の権限
├── packaging/            .pkg.tar.zst、.rpm、.deb パッケージと AUR の PKGBUILD
├── scripts/              ランチャー、ローカルインストーラー、システムユーティリティ
├── assets/               アイコン、スクリーンショット、Web ギャラリー
├── docs/                 ドキュメント、サードパーティ通知、この README の翻訳
└── tests/                4000 以上の自動テスト
```

[MIT ライセンス](../../LICENSE)で提供しています。
