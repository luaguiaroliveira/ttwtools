

def test_fichas_dos_modelos():
    from ttwtools import models
    fichas = models.list_models("pt")["models"]
    ids = {m["id"] for m in fichas}
    assert {"en_core_web_sm", "pt_core_news_sm", "stanza:pt"} <= ids
    for m in fichas:
        assert m["license"] and m["source_url"].startswith("https://") and m["trained_on"]
        assert m["name"] and m["purpose"] and m["about"] and not m["about"].startswith("model.")
        assert m["available"] == (m["reason"] is None)
