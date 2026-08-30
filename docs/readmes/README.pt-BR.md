# BC250 Control Center

[English](../../README.md) · [Español](README.es.md) · [Русский](README.ru.md) · [Українська](README.uk.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Polski](README.pl.md) · [中文](README.zh-CN.md) · [日本語](README.ja.md)

Central de controle Linux para AMD BC-250: monitoramento, GPU, CPU, Unidades de Computação e ventoinhas em um aplicativo de desktop.

## Capturas de tela

[<img src="../../assets/screenshots/dashboard-overview.png" alt="Painel do BC250 Control Center" width="100%">](https://movacx.github.io/bc250-control-center/gallery/#dashboard)

## Instalação

```bash
# Pelo código-fonte
git clone https://github.com/movacx/bc250-control-center.git
cd bc250-control-center/scripts
./install-local.sh

# Arch, CachyOS e Manjaro
yay -S bc250-control-center-git
```

Para remover uma instalação local, execute `./uninstall-local.sh` na mesma pasta.

Os pacotes estão no [último lançamento](https://github.com/movacx/bc250-control-center/releases). Fedora, Nobara e Bazzite usam o mesmo RPM `noarch`:

```bash
sudo dnf install ./bc250-control-center-*.rpm        # Fedora / Nobara
sudo rpm-ostree install ./bc250-control-center-*.rpm # Bazzite / Fedora Atomic
systemctl reboot                                      # após rpm-ostree
sudo apt install ./bc250-control-center_*.deb         # Ubuntu / Debian
```

## Primeiro uso

1. Abra `bc250-control-center`.
2. No Dashboard, escolha **Prepare dependencies**.
3. Confira o estado do módulo antes de aplicar qualquer alteração.

## Recursos

- Métricas ao vivo de CPU, GPU, memória, armazenamento, rede, temperatura e ventoinhas.
- Governor de GPU, ajuste de CPU e desbloqueio experimental de núcleos.
- Controle de 24–40 Compute Units, PWM e curvas de ventoinha.
- Diagnósticos, histórico, exportação CSV, escala de interface e navegação por controle.

## Decky Quick Access opcional

No SteamOS/Game Mode, instale o painel pela seção **Decky** no fim do Dashboard. O aplicativo instala o Decky Loader quando necessário, ou instala/repara apenas o BC250 Quick Access. Veja o [README do Decky](../../integrations/decky/bc250-quick-access/README.md).

## Segurança

Overclock, mudanças de Compute Units e controle de ventoinhas podem causar travamentos, desligamentos, perda de dados ou danos ao hardware. Aplique uma alteração por vez, mantenha uma forma de recuperação e não trate verificações de software como validação de hardware.

## Créditos

O projeto integra trabalho da comunidade por fluxos explícitos e revisados. Consulte os [avisos de terceiros](../THIRD_PARTY_NOTICES.md) para licenças, revisão e limites de integração.

## Idiomas

A interface oferece 30 idiomas, pode seguir o sistema ou ser alterada em Settings; inclui inglês, espanhol, português, russo, ucraniano, alemão, francês, polonês, chinês, japonês, coreano e mais.

## Estrutura do projeto

```text
src/bc250cc/   lógica da aplicação e do sistema
frontends/     adaptadores Desktop Qt, CLI e Quick Access
privileged/    helpers protegidos e política Polkit
packaging/     metadados e configuração por distribuição
scripts/       inicializadores e instalador local
```

Licença [MIT](../../LICENSE).
