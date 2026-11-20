"""The wake model's file and fit (MIS-0008 R24): weights and a report, never a pickle."""
import numpy as np
import pytest

from macf.voice.wake.model import FORMAT, WakeModel, fit_logistic


def test_a_model_round_trips_with_its_report(tmp_path):
    model = WakeModel(weights=np.arange(4.0), bias=-0.5, threshold=0.7, phrase="yo tom",
                      report={"misses": 1, "false_alarms_per_hour": 0.0})
    model.save(tmp_path / "wake.npz")
    back = WakeModel.load(tmp_path / "wake.npz")
    assert (back.phrase, back.threshold, back.report["misses"]) == ("yo tom", 0.7, 1)
    assert np.allclose(back.predict_proba(np.eye(4)), model.predict_proba(np.eye(4)))


def test_a_pickled_model_is_refused_not_unpickled(tmp_path):
    """A file holding a Python object can't be loaded: unpickling it could run anything."""
    path = tmp_path / "wake.npz"
    np.savez(path, weights=np.zeros(3), meta=np.array([{"format": FORMAT}], dtype=object))
    with pytest.raises(ValueError, match="pickled|allow_pickle"):
        WakeModel.load(path)


def test_a_file_of_another_format_is_refused_by_name(tmp_path):
    path = tmp_path / "wake.npz"
    np.savez(path, weights=np.zeros(3), meta=np.array('{"format": "something-else/9"}'))
    with pytest.raises(ValueError, match="something-else/9"):
        WakeModel.load(path)


def test_the_fit_separates_two_clusters_and_weights_its_classes():
    """A plain check that the logistic regression learns: two shifted clusters, few positives."""
    rng = np.random.default_rng(3)
    pos = rng.normal(1.5, 1.0, size=(30, 8))
    neg = rng.normal(-1.5, 1.0, size=(600, 8))
    w, b = fit_logistic(np.vstack([pos, neg]), np.r_[np.ones(30), np.zeros(600)], l2=1.0)
    model = WakeModel(weights=w, bias=b, threshold=0.5, phrase="x")
    p_pos = model.predict_proba(rng.normal(1.5, 1.0, size=(200, 8)))[:, 1]
    p_neg = model.predict_proba(rng.normal(-1.5, 1.0, size=(200, 8)))[:, 1]
    assert (p_pos > 0.5).mean() > 0.9 and (p_neg > 0.5).mean() < 0.1
