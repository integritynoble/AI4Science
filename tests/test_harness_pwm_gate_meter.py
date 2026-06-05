from ai4science.harness import repl


def test_turn_cost_from_usage(monkeypatch):
    from ai4science.harness.events import Usage
    monkeypatch.setattr(repl.routing, "_select_source",
                        lambda backend: ("src", "pid", "0xWALLET", 1.0))
    monkeypatch.setattr(repl.pricing, "price_call",
                        lambda model, usage, price_multiplier=1.0: {"pwm": 0.02, "usd": 0.1})
    pwm, wallet = repl._turn_cost_for("openai", "gpt-5.5",
                                      Usage(input=10, output=5, total=15))
    assert pwm == 0.02 and wallet == "0xWALLET"
