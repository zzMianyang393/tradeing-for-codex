from ten_u_event_trend_contract_v1 import EventTrendConfig
from ten_u_event_trend_data_v1 import HOUR_MS
from ten_u_event_trend_formation_v1 import FourHourBar, HourBar
from ten_u_event_trend_postmortem_v1 import _summarize


def test_summary_reports_directional_sign_without_threshold_search():
    result = _summarize([0.1, -0.2, 0.3])
    assert result["events"] == 3
    assert result["positive_direction_fraction"] == 2 / 3
    assert result["median_directional_return_fraction"] == 0.1


def test_postmortem_contract_has_fixed_horizons_independent_of_results():
    # The contract and test deliberately contain no parameter-selection helper.
    config = EventTrendConfig()
    assert config.maximum_holding_hours == 48

