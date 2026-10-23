# BC250 Control Center

[English](../../README.md) · [Español](README.es.md) · [Русский](README.ru.md) · [Українська](README.uk.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Polski](README.pl.md) · [中文](README.zh-CN.md) · [日本語](README.ja.md)

<a href="https://ko-fi.com/movacx"><img src="https://img.shields.io/badge/Ko--fi-Doar-ff5e5b?style=for-the-badge&logo=kofi&logoColor=white" alt="Doar · Ko-fi"></a>

Aplicativo de desktop para configurar, ajustar e monitorar a AMD BC-250 no Linux.

Cobre o governador da GPU, o ajuste da CPU, as Unidades de Computação (CU), os ventiladores, a memória, a atualização da BIOS, o upscaling e a preparação do sistema para as distribuições compatíveis. Cada mudança no hardware é verificada contra seus limites e confirmada antes de ser aplicada. Um plugin opcional do Decky leva os controles do dia a dia para o Modo Jogo da Steam.

<p align="center">
  <a href="https://movacx.github.io/bc250-control-center/gallery/#dashboard"><img src="../../assets/screenshots/dashboard-overview.png" alt="Painel do BC250 Control Center" width="100%"></a>
</p>

Mais capturas de tela na [galeria](https://movacx.github.io/bc250-control-center/gallery/).

## Recursos

- Painel com CPU, GPU, refrigeração, carga por núcleo, temperatura da GDDR6 por chip, BIOS instalada e trilhos de energia (os trilhos exigem a modificação de hardware I2C; o aplicativo inclui um guia com fotos)
- Gráficos de desempenho de CPU, GPU, VRAM, RAM, disco e rede, com visualização de sensores e exportação para CSV
- Gerenciamento do governador da GPU (Cyan, com Oberon como alternativa), faixas de frequência seguras e um laboratório de tensão
- Ajuste da CPU pela SMU, teste de estabilidade e desbloqueio opcional de núcleos
- Unidades de Computação: de 24 a 40 CUs, com o estado ativo e o de inicialização informados separadamente
- Controle dos ventiladores: PWM manual, curvas por temperatura, perfis persistentes ou entrega ao CoolerControl, fancontrol ou fan2go
- Memória: tamanho da VRAM, ZRAM, ZSWAP e swap
- Criação de pendrive para atualizar a BIOS (P3.00 Chipset Menu, MeiMeiDXE v3, P5.00, P3.00, P2.00), com todos os arquivos verificados
- Upscaling por jogo: FSR4 INT8 pelo OptiScaler Client e HelixSR, com backup e restauração dos arquivos do jogo
- Preparação do sistema por distribuição, executada em um terminal integrado
- Correções de compatibilidade para GFX1013, async compute, ACPI e Mesa; Dolby Digital 5.1 por HDMI; controle da TV por HDMI-CEC
- Relatórios de problemas dentro do aplicativo, com códigos de erro, códigos de origem e o erro bruto anexado
- 30 idiomas, temas claro e escuro, escala da interface e navegação por controle

## Distribuições compatíveis

- Arch Linux, CachyOS, Manjaro
- Fedora, Nobara
- Bazzite e outras variantes atômicas do Fedora
- SteamOS (beta)
- Ubuntu, Linux Mint, Debian 13

É necessário Python 3.11 ou mais recente. Outras distribuições, incluindo sistemas com OpenRC, são detectadas e tratadas sempre que possível, mas não são testadas em todas as versões.

## Instalação

### AUR

Para Arch Linux, CachyOS e SteamOS:

```bash
yay -S bc250-control-center-git
```

### Pacotes das versões

Baixe o pacote da sua distribuição na [versão mais recente](https://github.com/movacx/bc250-control-center/releases/latest).

Arch Linux, CachyOS, Manjaro:

```bash
sudo pacman -U ./bc250-control-center-*-any.pkg.tar.zst
```

Fedora, Nobara:

```bash
sudo dnf install ./bc250-control-center-*.rpm
```

Bazzite e Fedora Atomic (é preciso reiniciar):

```bash
sudo rpm-ostree install ./bc250-control-center-*.rpm
systemctl reboot
```

Ubuntu, Linux Mint, Debian:

```bash
sudo apt install ./bc250-control-center_*.deb
```

Use `apt install` em vez de `dpkg -i` para que as dependências sejam instaladas. Se um pacote ficou pela metade com `dpkg -i`, execute `sudo apt --fix-broken install`.

### SteamOS

O SteamOS mantém a partição do sistema somente leitura, então o pacote só pode ser instalado com essa proteção desativada. Abra o Konsole no Modo Desktop e execute:

```bash
sudo steamos-readonly disable
sudo pacman-key --init
sudo pacman-key --populate archlinux holo
sudo pacman -Syy
sudo pacman -U ./bc250-control-center-*-any.pkg.tar.zst
sudo steamos-readonly enable
```

As linhas `pacman-key` e `pacman -Syy` atualizam o chaveiro e os bancos de dados de pacotes, que uma atualização do SteamOS redefine. Se você ainda não definiu uma senha para o usuário `deck`, execute `passwd` antes. Depois de uma atualização do SteamOS, **Reinstall BC250 Control Center** no menu do Modo Desktop faz esses passos por você.

### A partir do código-fonte

```bash
git clone https://github.com/movacx/bc250-control-center.git
cd bc250-control-center
./run.sh                          # executa a partir do repositório
bash scripts/install-local.sh     # ou instala para o usuário atual
```

## Atualizações

O aplicativo verifica novas versões, mostra o changelog, confere a soma de verificação do pacote e instala a atualização com o gerenciador de pacotes do sistema.

**SteamOS:** uma atualização do sistema do SteamOS remove os pacotes instalados no sistema, incluindo este. Depois de uma atualização do sistema, execute **Reinstall BC250 Control Center** no menu do Modo Desktop e depois rode Prepare BC250 system novamente. O SteamOS pede a senha do usuário `deck`; se você ainda não tiver uma, crie com `passwd`.

**Atualizando a partir da 1.19:** o atualizador da 1.19 não consegue instalar pacotes. Instale a versão atual uma vez manualmente; as seguintes se atualizam sozinhas.

```bash
# Bazzite / Fedora Atomic: substituir um pacote 1.19 instalado em camadas
sudo rpm-ostree uninstall bc250-control-center --install ./bc250-control-center-*.noarch.rpm
systemctl reboot

# Uma cópia instalada com install-local.sh: remova e depois instale o pacote
bash scripts/uninstall-local.sh
```

## Primeiros passos

1. Abra o BC250 Control Center. A tela de primeira execução define idioma e aparência e oferece instalar os componentes necessários.
2. Opcionalmente, faça o tour guiado, que explica o que cada módulo altera na placa.
3. No Painel, execute **Prepare BC250 system**. Ele mostra o que será instalado para a sua distribuição e roda no terminal integrado.
4. Leia a linha de status de um módulo antes de aplicar alterações; ela informa o que está pronto e o que falta.

## Plugin Decky

O BC250 Quick Access é um painel opcional para o menu de acesso rápido do Modo Jogo da Steam. Oferece controles de GPU, Unidades de Computação, CPU, ventiladores e VRAM, perfis de GPU e ventiladores por jogo e leituras ao vivo de async compute. A configuração avançada continua no aplicativo de desktop.

Instale-o pela seção **Decky** do Painel. O Decky Loader também é instalado se estiver faltando; nada mais no aplicativo instala o Decky. Veja o [README do plugin](../../integrations/decky/bc250-quick-access/README.md) para mais detalhes.

## Relatando problemas

As janelas de erro mostram um código de diagnóstico (por exemplo, `BC250-UPSCALE-001`), um código de origem que identifica a função onde o erro ocorreu (por exemplo, `GPU-0142`) e o erro bruto com o seu traceback.

Use **Relatar este problema** na janela de erro ou **Configurações › Diagnóstico › Enviar um relatório**. O formulário abre dentro do aplicativo com os códigos, o erro bruto, as especificações do sistema e os erros recentes já preenchidos. Você pode revisar tudo antes de enviar; os caminhos da pasta pessoal são substituídos por `~`. Se o formulário não puder ser enviado, ele abre no navegador com as suas respostas mantidas. O formulário também está [na web](https://docs.google.com/forms/d/e/1FAIpQLSe3M1stf3bpCoorb4hCWFX9YC_TZ_Gv6WHWQDRe1AV5rJT6rA/viewform).

O relatório também anexa um diagnóstico de hardware, coletado sem root em todas as distribuições: kernel e cabeçalhos, módulos de sensores carregados e suas mensagens do kernel (NCT6687, amdgpu), leituras de hwmon e `sensors`, linhas de GPU e de falhas do log do kernel, como terminou o boot anterior (desligamento limpo ou reset abrupto), serviços, pacotes e o final do último log de fluxo de trabalho. Quando o log do kernel está fechado para o seu usuário, o desktop pede a senha uma vez pelo polkit. Relatórios grandes demais para o formulário são reduzidos automaticamente, começando pelas partes menos importantes; **Abrir no navegador** continua copiando o texto completo.

### Black box (travamentos e resets)

Um travamento total não deixa nada no log do kernel. A black box registra quatro vezes por segundo o clock e a carga da GPU, as temperaturas, a tensão da GFX, a potência, a velocidade do ventilador, o clock da CPU e a memória livre, gravando cada linha no disco. Assim, o próximo relatório mostra os últimos segundos da placa antes de um travamento ou reset. Não precisa de root e o arquivo tem tamanho limitado (512 KB, depois é rotacionado).

```bash
# Modo Desktop: deixe o terminal aberto enquanto joga; pare com Ctrl+C
bc250-control-center-cli black-box

# Modo Jogo (SteamOS): inicie em segundo plano antes de trocar de modo
systemd-run --user --unit=bc250-black-box bc250-control-center-cli black-box
systemctl --user stop bc250-black-box
```

O log fica em `~/.local/state/bc250-control-center/black-box/`. `bc250-control-center-cli diagnose` mostra o mesmo diagnóstico de hardware que o relatório envia.

Problemas no GitHub também são bem-vindos. Inclua sua distribuição, a versão do kernel e a saída do terminal.

## Segurança

Overclock, desbloqueio de Unidades de Computação, mudança do controle dos ventiladores e gravação de uma BIOS podem deixar o sistema instável, causar perda de dados ou danificar a placa. Mude uma coisa de cada vez e mantenha uma forma de reverter. As verificações do aplicativo pegam erros comuns, mas não são uma garantia.

## Créditos

Este projeto se apoia no trabalho da comunidade BC-250. Os projetos abaixo pertencem aos seus autores; o aplicativo os integra por meio de fluxos revisados e fixados em uma versão específica. Licenças e o alcance de cada integração estão nos [avisos de terceiros](../THIRD_PARTY_NOTICES.md).

**GPU**
- [cyan-skillfish-governor](https://github.com/filippor/cyan-skillfish-governor/tree/smu): governador da GPU
- [Oberon Governor](https://gitlab.com/mothenjoyer69/oberon-governor): governador alternativo
- [bc250-gfx1013-fix](https://github.com/DryhoppedIPA/bc250-gfx1013-fix) e [bc250-steamos](https://github.com/keyboardspecialist/bc250-steamos): kernel e Mesa/RADV para GFX1013
- [linux-cachyos-bc250](https://github.com/MastaG/linux-cachyos-bc250): kernel e Mesa/RADV para Arch e CachyOS
- [bc250-async-compute-bazzite](https://github.com/tri3gubki-ops/bc250-async-compute-bazzite): async compute no Bazzite 44, com patches de RADV também compilados para Arch, CachyOS e Fedora com kernel 7.2 ou mais recente

**Upscaling**
- [bc250-fsr4](https://github.com/dmorazasanchez/bc250-fsr4) e [bc250-fsr4-fork](https://github.com/daniel-h-0/bc250-fsr4-fork): OptiScaler Client, FSR4 por jogo
- [HelixSR](https://github.com/lonewolf0622/HelixSR): reconstrução DLSS Model E em jogos com FSR 3.1

**CPU e Unidades de Computação**
- [bc250_smu_oc](https://github.com/bc250-collective/bc250_smu_oc): detecção e ajuste da CPU pela SMU
- [bc250-core-unlock](https://github.com/rw-r-r-0644/bc250-core-unlock) e [bc250-efi-core-unlock](https://github.com/Hexxeh/bc250-efi-core-unlock): desbloqueio de núcleos
- [bc250-acpi-fix](https://github.com/e-tho/bc250-acpi-fix): estados de desempenho da CPU pelo ACPI
- [bc250-cu-live-manager](https://github.com/WinnieLV/bc250-cu-live-manager), [bc250-cu-live-manager-SteamOS](https://github.com/F5GO/bc250-cu-live-manager-SteamOS) e [bc250-40cu-unlock](https://github.com/duggasco/bc250-40cu-unlock): Unidades de Computação

**Sensores, memória e ventiladores**
- [BC250-Telemetry](https://github.com/onlinermm/BC250-Telemetry): telemetria dos reguladores de tensão (VRM) e as fotos do guia I2C
- [bc250-memory-temperature](https://github.com/pan-Rijovich/bc250-memory-temperature): temperatura da GDDR6
- [bc250_memcfg](https://github.com/fanoush/bc250_memcfg): tamanho da VRAM pelo CMOS
- [nct6687d](https://github.com/Fred78290/nct6687d): sensores NCT e PWM dos ventiladores
- [linux-cec](https://gitlab.steamos.cloud/holo/linux-cec): cecd, o daemon HDMI-CEC da Valve

**Firmware**
- [bc250-bios](https://gitlab.com/TuxThePenguin0/bc250-bios): BIOS P3.00 original e Chipset Menu
- [AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script](https://github.com/Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script): UEFI Shell e MeiMeiDXE v3
- [BC-250](https://github.com/kenavru/BC-250): espelho do kit de atualização da ASRock (P2.00 e P5.00)
- [bc250-custom-bios-logo](https://github.com/tmghd272/bc250-custom-bios-logo): logotipo de boot personalizado

**Projetos relacionados** (o aplicativo não os usa; licenças conforme o GitHub)
- [bc250-vrm-dkms](https://github.com/Hexxeh/bc250-vrm-dkms) e [bc250-memory-dkms](https://github.com/Hexxeh/bc250-memory-dkms) (GPL-2.0): temperaturas do VRM e da memória como módulos do kernel
- [bc250-bazzite-suite](https://github.com/RobertoTorino/bc250-bazzite-suite) (GPL-3.0): suíte de configuração para o Bazzite
- [bc250-vcn-research](https://github.com/Shalasere/bc250-vcn-research) e [amdgpu-wddm](https://github.com/D-Ogi/amdgpu-wddm): pesquisa sobre codificação de vídeo VCN e um driver aberto para Windows (sem licença declarada; apenas linkados)

## Estrutura do projeto

```text
bc250-control-center/
├── src/bc250cc/              O núcleo, sem interface gráfica
│   ├── domain/               Regras e limites de cada módulo (GPU, CPU, CU, ventiladores, firmware…)
│   ├── application/          Casos de uso que combinam essas regras
│   ├── infrastructure/       Acesso ao sistema: sensores, serviços, pacotes, GitHub
│   ├── platform/             Diferenças entre distribuições e sistemas de boot
│   └── shared/               Versão, caminhos e contratos compartilhados por todos os processos
├── frontends/
│   ├── desktop/              Aplicativo de desktop em Qt
│   │   ├── pages/            Um arquivo por módulo (painel, GPU, CPU, ventiladores, firmware…)
│   │   ├── components/       Peças reutilizáveis da interface
│   │   ├── onboarding/       Tela de boas-vindas e tour guiado
│   │   ├── console/          Terminal integrado
│   │   ├── theme/            Temas, estilos, cores e ícones
│   │   └── i18n/             Traduções para 30 idiomas
│   └── cli.py                Modo de linha de comando
├── integrations/decky/       Plugin Decky Quick Access para o Modo Jogo
├── privileged/               O que roda como root, isolado e revisado
│   ├── helpers/              Um auxiliar por tarefa privilegiada
│   ├── lib/                  Código compartilhado por esses auxiliares
│   └── policies/             Permissões do Polkit
├── packaging/                Pacotes .pkg.tar.zst, .rpm e .deb, e o PKGBUILD do AUR
├── scripts/                  Inicializadores, instalador local e utilitários de sistema
├── assets/                   Ícones, capturas de tela e galeria web
├── docs/                     Documentação, avisos de terceiros e traduções deste README
└── tests/                    Mais de 5000 testes automáticos, com os-release de 37 distribuições reais
```

## Contribuindo

A contribuição mais útil é um relatório de erro, principalmente com a sua distribuição, a versão do kernel e o que o terminal mostrou. Se você usa uma distribuição que não aparece acima, conte como foi, para o bem ou para o mal.

Licença [MIT](../../LICENSE).
