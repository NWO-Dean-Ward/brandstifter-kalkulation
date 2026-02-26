"""
Test: qwen2.5-coder:14b als primaeres lokales LLM.
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.llm_router import LLMRouter, LLMTask, LLMModell


async def main():
    router = LLMRouter()
    await router.init()

    print("=== LLM-Router: qwen2.5-coder:14b Test ===\n")
    print(f"Verfuegbare Modelle: {router._verfuegbare_modelle}")

    # 1. Routing-Test: Welches Modell fuer welchen Task?
    print("\n--- Task-Routing ---")
    for task in LLMTask:
        modell = router._route_task(task)
        print(f"  {task.value:25s} -> {modell.value}")

    # 2. Materialpreis-Schaetzung via qwen2.5-coder:14b
    print("\n--- Materialpreis-Schaetzung (qwen2.5-coder:14b) ---")
    result = await router.schaetze_materialpreis("Multiplex Birke 18mm", "m2")
    print(f"  Multiplex Birke 18mm: {result}")

    # 3. JSON-Qualitaetstest: Kann qwen sauberes JSON liefern?
    print("\n--- JSON-Qualitaetstest ---")
    result = await router.generate(
        prompt=(
            'Gib mir die Kosten fuer 3 Schreinerei-Materialien als JSON-Array.\n'
            'Format: [{"name": "...", "preis_eur": 0.0, "einheit": "m2"}]\n'
            'Nur JSON, keine Erklaerung.'
        ),
        modell=LLMModell.QWEN_CODER,
        temperature=0.1,
        max_tokens=300,
    )
    response = result.get("response", "").strip()
    print(f"  Modell: {result['modell']}")
    print(f"  Tokens: {result['tokens']}")
    print(f"  Dauer: {result['duration_ms']:.0f}ms")
    print(f"  Antwort:\n    {response[:500]}")

    # JSON validieren
    import json
    try:
        start = response.find("[")
        end = response.rfind("]") + 1
        if start >= 0 and end > start:
            parsed = json.loads(response[start:end])
            print(f"\n  >>> JSON VALIDE: {len(parsed)} Eintraege <<<")
            for item in parsed:
                print(f"      {item}")
        else:
            print("\n  >>> KEIN JSON-ARRAY GEFUNDEN <<<")
    except json.JSONDecodeError as e:
        print(f"\n  >>> JSON UNGUELTIG: {e} <<<")

    # 4. Freitext-Interpretation
    print("\n--- Freitext-Interpretation ---")
    positionen = await router.interpretiere_freitext(
        "Kueche komplett: 8 Unterschraenke Eiche furniert, "
        "4 Haengeschraenke Glas, Arbeitsplatte Granit 3m"
    )
    print(f"  Erkannte Positionen: {len(positionen)}")
    for pos in positionen:
        print(f"    {pos.get('pos_nr', '?')}: {pos.get('kurztext', '?')} "
              f"({pos.get('menge', '?')} {pos.get('einheit', '?')})")

    # 5. Vergleich: qwen vs gpt-oss
    print("\n--- Vergleich: qwen vs gpt-oss (gleicher Prompt) ---")
    test_prompt = (
        'Schaetze den Preis fuer "Spanplatte Melamin weiss 19mm" pro m2 in Deutschland.\n'
        'Antworte NUR mit JSON: {"preis": <zahl>, "einheit": "m2"}'
    )

    for modell in [LLMModell.QWEN_CODER, LLMModell.GPT_OSS]:
        r = await router.generate(prompt=test_prompt, modell=modell, temperature=0.1, max_tokens=100)
        print(f"  {modell.value:25s}: {r.get('response', '').strip()[:200]}  "
              f"({r['tokens']} tokens, {r['duration_ms']:.0f}ms)")

    print("\n=== TEST ABGESCHLOSSEN ===")


if __name__ == "__main__":
    asyncio.run(main())
