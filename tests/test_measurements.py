"""Structural integrity of MEASUREMENT_GROUPS and the _ABBREV_MAP index."""

import app


def _all_entries():
    for group_name, entries in app.MEASUREMENT_GROUPS:
        for entry in entries:
            yield group_name, entry


def test_groups_is_list_of_pairs():
    assert isinstance(app.MEASUREMENT_GROUPS, list)
    for group_name, entries in app.MEASUREMENT_GROUPS:
        assert isinstance(group_name, str) and group_name
        assert isinstance(entries, list) and entries


def test_every_entry_is_seven_tuple():
    for _, entry in _all_entries():
        assert len(entry) == 7, f"bad arity: {entry}"
        label, abbrev, measurement, field, source, convert, unit = entry
        assert isinstance(label, str) and label
        assert isinstance(abbrev, str) and abbrev
        assert isinstance(measurement, str) and measurement
        assert isinstance(field, str) and field
        assert source is None or isinstance(source, str)
        assert callable(convert)
        assert isinstance(unit, str) and unit


def test_abbrevs_unique_across_groups():
    seen = {}
    for _, entry in _all_entries():
        abbrev = entry[1]
        assert abbrev not in seen, f"duplicate abbrev {abbrev}"
        seen[abbrev] = True


def test_abbrevs_uppercase_alnum():
    # Abbrevs are alphanumeric and start uppercase, optionally with a
    # lowercase trailing disambiguator (e.g. "COGt" = Course Over Ground,
    # true; "MFITT" = trial variant of MFIT).
    for _, entry in _all_entries():
        abbrev = entry[1]
        assert abbrev.isalnum(), f"weird abbrev {abbrev!r}"
        assert abbrev[0].isupper(), f"weird abbrev {abbrev!r}"


def test_measurement_field_unique():
    seen = set()
    for _, entry in _all_entries():
        key = (entry[2], entry[3])
        assert key not in seen, f"duplicate (measurement, field): {key}"
        seen.add(key)


def test_abbrev_map_covers_all_entries():
    assert set(app._ABBREV_MAP) == {e[1] for _, e in _all_entries()}


def test_abbrev_map_payload():
    """_ABBREV_MAP values must be (measurement, field, source, convert)."""
    for _abbrev, (measurement, field, source, convert) in app._ABBREV_MAP.items():
        assert isinstance(measurement, str)
        assert isinstance(field, str)
        assert source is None or isinstance(source, str)
        assert callable(convert)


def test_lat_lon_use_passthrough():
    lat = app._ABBREV_MAP["LAT"]
    lon = app._ABBREV_MAP["LON"]
    assert lat[3] is app._passthrough
    assert lon[3] is app._passthrough
    assert lat[0] == "navigation.position" and lat[1] == "lat"
    assert lon[0] == "navigation.position" and lon[1] == "lon"


def test_position_source_is_n2k():
    assert app._ABBREV_MAP["LAT"][2] == "n2k-can0.10"


def test_interval_options_and_keys_agree():
    assert app._INTERVAL_KEYS == frozenset(k for k, _ in app.INTERVAL_OPTIONS)
    assert "10s" in app._INTERVAL_KEYS


def test_version_exposed_to_templates():
    assert app.app.jinja_env.globals["VERSION"] == app.__version__
