"""Self-tests for spectral_match.py. Run after any change to this file."""
from spectral_match import SpectralCalibrationChart, normalize_vector

def test_normalization_brightness_invariance():
    raw_bright = {"F1":500,"F2":600,"F3":700,"F4":800,"F5":900,"F6":1000,"F7":1100,"F8":1200,"CLEAR":5000,"NIR":300}
    raw_dim = {k: v*0.5 for k, v in raw_bright.items()}
    n1, n2 = normalize_vector(raw_bright), normalize_vector(raw_dim)
    assert max(abs(a-b) for a,b in zip(n1,n2)) < 1e-6

def test_exact_match():
    chart = SpectralCalibrationChart.from_pairs([
        (10, {"F1":400,"F2":420,"F3":440,"F4":460,"F5":480,"F6":500,"F7":520,"F8":540,"CLEAR":4000,"NIR":200}),
        (20, {"F1":420,"F2":440,"F3":460,"F4":480,"F5":500,"F6":520,"F7":540,"F8":560,"CLEAR":4000,"NIR":210}),
        (30, {"F1":440,"F2":460,"F3":480,"F4":500,"F5":520,"F6":540,"F7":560,"F8":580,"CLEAR":4000,"NIR":220}),
    ], name="test_urea")
    for pt in chart.points:
        r = chart.match(pt.raw_channels)
        assert r.distance < 1e-6 and abs(r.value - pt.value) < 0.01

def test_out_of_range():
    chart = SpectralCalibrationChart.from_pairs([
        (10, {"F1":400,"F2":420,"F3":440,"F4":460,"F5":480,"F6":500,"F7":520,"F8":540,"CLEAR":4000,"NIR":200}),
        (30, {"F1":440,"F2":460,"F3":480,"F4":500,"F5":520,"F6":540,"F7":560,"F8":580,"CLEAR":4000,"NIR":220}),
    ], name="test_urea")
    r = chart.match({"F1":9000,"F2":10,"F3":9000,"F4":10,"F5":9000,"F6":10,"F7":9000,"F8":10,"CLEAR":4000,"NIR":9000})
    assert not r.in_range

if __name__ == "__main__":
    test_normalization_brightness_invariance()
    test_exact_match()
    test_out_of_range()
    print("All tests passed.")
