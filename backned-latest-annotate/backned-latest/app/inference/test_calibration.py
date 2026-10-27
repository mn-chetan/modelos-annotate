from app.inference.calibration import apply_temperature, fit_temperature


def test_temperature_one_is_identity():
    assert apply_temperature(0.2, 1.0) == 0.2


def test_fit_improves_overconfident_scores():
    result = fit_temperature([0.99, 0.95, 0.90, 0.80], [0, 0, 1, 1])
    assert result.improved
    assert result.calibrated_nll < result.baseline_nll
