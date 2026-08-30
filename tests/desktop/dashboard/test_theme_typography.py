from frontends.desktop.theme import scale_stylesheet


def test_readability_pass_increases_small_fonts_without_changing_spacing():
    source = "QLabel { font-size: 9px; margin: 9px; padding: 8px; }"

    result = scale_stylesheet(source, 100)

    assert "font-size: 10px" in result
    assert "margin: 9px" in result
    assert "padding: 8px" in result


def test_user_scale_remains_proportional_after_readability_bonus():
    result = scale_stylesheet("QLabel { font-size: 10px; margin: 10px; }", 120)

    assert "font-size: 13px" in result
    assert "margin: 12px" in result
