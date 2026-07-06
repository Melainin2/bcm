"""Tests du préprocessing : acronymes DBA + correction de fautes de frappe."""

from rag import preprocess


def test_typo_correction_postgresql():
    a = preprocess.analyze_query("how does postgressql vaccum work")
    corrected = a.corrected.lower()
    assert "postgresql" in corrected
    assert "vacuum" in corrected
    pairs = {(f.lower(), t.lower()) for f, t in a.corrections}
    assert ("postgressql", "postgresql") in pairs


def test_typo_correction_oracle():
    a = preprocess.analyze_query("what is an orcale tablspace")
    assert "oracle" in a.corrected.lower()
    assert "tablespace" in a.corrected.lower()


def test_acronym_expansion_awr():
    a = preprocess.analyze_query("explain the AWR report")
    assert "Automatic Workload Repository" in a.expanded
    assert any(sig == "AWR" for sig, _ in a.acronyms)


def test_acronym_expansion_multiple():
    a = preprocess.analyze_query("difference between SGA and PGA")
    forms = a.expanded
    assert "System Global Area" in forms
    assert "Program Global Area" in forms


def test_did_you_mean_suggestion():
    a = preprocess.analyze_query("show me the ARW data")
    sugg = {(f.upper(), t.upper()) for f, t in a.suggestions}
    assert ("ARW", "AWR") in sugg


def test_wal_and_mvcc_known():
    a = preprocess.analyze_query("how do WAL and MVCC interact")
    assert "Write-Ahead Log" in a.expanded
    assert "Multiversion Concurrency Control" in a.expanded


def test_as_dict_shape():
    d = preprocess.analyze_query("orcale AWR").as_dict()
    assert set(d.keys()) == {"corrections", "acronyms", "suggestions"}
    assert isinstance(d["corrections"], list)


def test_clean_query_unchanged_meaningfully():
    a = preprocess.analyze_query("What is a tablespace")
    assert "tablespace" in a.corrected.lower()
    assert not a.corrections  # rien à corriger
