# BC250 Control Center

[English](../../README.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Русский](README.ru.md) · [Українська](README.uk.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Polski](README.pl.md) · [中文](README.zh-CN.md)

AMD BC-250 向け Linux コントロールセンターです。監視、GPU 制御、CPU チューニング、Compute Units、ファン制御を一つのデスクトップアプリにまとめています。

## スクリーンショット

[<img src="../../assets/screenshots/dashboard-overview.png" alt="BC250 Control Center ダッシュボード" width="100%">](https://movacx.github.io/bc250-control-center/gallery/#dashboard)

## インストール

```bash
# ソースから
git clone https://github.com/movacx/bc250-control-center.git
cd bc250-control-center/scripts
./install-local.sh

# Arch、CachyOS、Manjaro
yay -S bc250-control-center-git
```

ローカルインストールを削除するには、同じフォルダーで `./uninstall-local.sh` を実行してください。

パッケージは[最新リリース](https://github.com/movacx/bc250-control-center/releases)から入手できます。Fedora、Nobara、Bazzite は同じ `noarch` RPM を使用します。

```bash
sudo dnf install ./bc250-control-center-*.rpm        # Fedora / Nobara
sudo rpm-ostree install ./bc250-control-center-*.rpm # Bazzite / Fedora Atomic
systemctl reboot                                      # rpm-ostree の後に再起動
sudo apt install ./bc250-control-center_*.deb         # Ubuntu / Debian
```

## 初回起動

1. `bc250-control-center` を開きます。
2. Dashboard で **Prepare dependencies** を選びます。
3. 変更を適用する前にモジュールの状態を確認します。

## 機能

- CPU、GPU、メモリ、ストレージ、ネットワーク、温度、ファンのライブ監視。
- GPU governor、CPU チューニング、実験的なコアアンロック。
- 24–40 Compute Units、PWM、ファンカーブの制御。
- 診断、履歴、CSV エクスポート、UI スケーリング、コントローラーナビゲーション。

## オプションの Decky Quick Access

SteamOS/Game Mode では、Dashboard 下部の **Decky** セクションからパネルを導入します。必要に応じてアプリが Decky Loader を導入し、すでにある場合は BC250 Quick Access のみをインストールまたは修復します。[Decky README](../../integrations/decky/bc250-quick-access/README.md)を参照してください。

## 安全性

オーバークロック、Compute Units の変更、ファン制御は、フリーズ、シャットダウン、データ損失、ハードウェア損傷を引き起こす可能性があります。一度に一つの変更だけを適用し、復旧手段を確保してください。ソフトウェアの確認をハードウェア検証として扱わないでください。

## クレジット

このプロジェクトは、明示的に確認された手順を通じてコミュニティの成果を統合しています。[第三者通知](../THIRD_PARTY_NOTICES.md)にライセンス、確認状況、統合範囲を記載しています。

## 言語

デスクトップ UI は 30 言語に対応し、システム言語に従うか Settings で変更できます。英語、スペイン語、ポルトガル語、ロシア語、ウクライナ語、ドイツ語、フランス語、ポーランド語、中国語、日本語、韓国語などを含みます。

## プロジェクト構成

```text
src/bc250cc/   アプリケーションとシステムのロジック
frontends/     Desktop Qt、CLI、Quick Access のアダプター
privileged/    保護された helper と Polkit ポリシー
packaging/     パッケージメタデータとディストリビューション設定
scripts/       ランチャーとローカルインストーラー
```

[MIT ライセンス](../../LICENSE)。
