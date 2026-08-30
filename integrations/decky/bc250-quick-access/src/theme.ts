export const tokens = {
  colors: {
    // Mirrors the Desktop application's dark palette (frontends/desktop/theme).
    // Orange is the one brand accent, reused exactly as the desktop uses it
    // for selection and primary actions. Amber is a second, deliberately
    // different hue reserved only for "pending change" / "needs attention" —
    // never for a selected/current state — so the two meanings never look
    // the same on the same screen.
    window: "#0F0F0F",
    panel: "#171717",
    panel_alt: "#1F1F1F",
    panel_raised: "#242424",
    control: "#242424",
    control_hover: "#2C2C2C",
    control_pressed: "#333333",
    border: "#343434",
    border_soft: "#292929",
    border_strong: "#4A4A4A",
    text: "#F2F2F2",
    muted: "#B4B4B4",
    subtle: "#8E8E8E",
    disabled_bg: "#292929",
    disabled_text: "#707070",
    // Controller focus ring only, same as the desktop theme.
    focus: "#6E9FFF",
    focus_soft: "rgba(110, 159, 255, 0.18)",
    // Brand accent (selection / primary action). Mirrors DARK_COLORS.orange.
    selection: "#38291D",
    action: "#38291D",
    action_hover: "#F0A45D",
    action_soft: "#38291D",
    // Pending / needs-attention. Deliberately not orange — see note above.
    // selection_border is now used exclusively for the CU grid's pending
    // indicator (see index.tsx CuEditor), so it shares this value.
    amber: "#E0A83E",
    amber_soft: "#3A2E12",
    selection_border: "#E0A83E",
    scrollbar: "#424242",
    scrollbar_hover: "#5A5A5A",
    progress_track: "#2A2A2A",
    chart_surface: "#151515",
    chart_grid: "#2D2D2D",
    chart_axis: "#4A4A4A",
    neutral_soft: "#242424",
    neutral_border: "#363636",
    icon_border: "#353535",
    on_accent: "#ffffff",
    console_bg: "#0A0A0A",
    console_text: "#E6E6E6",
    console_border: "#333333",
    blue: "#5B8DEF",
    blue_soft: "#1D2A3D",
    purple: "#B39DFF",
    purple_soft: "#2B2440",
    orange: "#F0A45D",
    orange_soft: "#38291D",
    orange_border: "#AD7643",
    cyan: "#56C7D4",
    cyan_soft: "#183137",
    green: "#5CBF78",
    green_soft: "#1B3224",
    red: "#FF6B64",
    red_soft: "#3A2020",
    blue_border: "#4268A9",
    purple_border: "#6F5BA8",
    cyan_border: "#3B7D86",
    green_border: "#3D784C",
    red_border: "#884947",
  },
  spacing: {
    micro: 2,
    tight: 4,
    compact: 6,
    regular: 8,
    section: 12,
  },
  radii: {
    compact: 4,
    control: 4,
    card: 4,
  },
  typography: {
    // QAM is viewed from farther away than the desktop window. Keep the
    // compact table legible before using bold or colour as decoration.
    micro: ".58em",
    caption: ".62em",
    body: ".68em",
    label: ".74em",
    value: ".88em",
  },
} as const;
