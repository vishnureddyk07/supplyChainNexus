from scripts.ml_baseline import DisruptionExample, evaluate, predict


def test_synthetic_baseline_reports_metrics_and_label():
    result = evaluate()

    assert result["dataset"] == "synthetic"
    assert result["samples"] == 8
    assert 0 <= result["accuracy"] <= 1
    assert result["recall"] > 0


def test_prediction_rejects_invalid_threshold():
    try:
        predict([DisruptionExample(0, 0, 0, 0)], threshold=1)
    except ValueError as error:
        assert "threshold" in str(error)
    else:
        raise AssertionError("invalid threshold should fail")
