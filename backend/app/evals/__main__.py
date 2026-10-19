"""Eval'leri çalıştırır:  cd backend && uv run python -m app.evals

Seçenekler: --suite S, --case ID (ikisi de tekrarlanabilir), --no-judge (yalnızca kurallar).

Bir takımın başarı oranı eşiğinin altına düşerse çıkış kodu 1 olur (birleştirme engellenir,
CLAUDE.md §13). Sahte (mock) LLM ile skorlar anlamsızdır; o durumda eşik uygulanmaz.
Gerçek modelle çalışır, yani para harcar: ~senaryo sayısı x 2 çağrı.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from app.core.config import get_settings
from app.evals.runner import JUDGE_FEATURE, PERSONA_FEATURE, EvalRunner
from app.evals.scenarios import EvalConfigError, load_eval_set
from app.providers.registry import build_registry

_DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "evals"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m app.evals")
    parser.add_argument("--root", type=Path, default=_DEFAULT_ROOT)
    parser.add_argument("--suite", action="append", help="yalnızca bu takım (tekrarlanabilir)")
    parser.add_argument("--case", action="append", help="yalnızca bu senaryo (tekrarlanabilir)")
    parser.add_argument("--no-judge", action="store_true", help="yalnızca kural kontrolleri")
    parser.add_argument("--concurrency", type=int, default=4)
    return parser.parse_args(argv)


async def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    # Windows konsolu varsayılan olarak cp1254/cp437; Türkçe karakterler bozulmasın.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        eval_set = load_eval_set(args.root)
    except EvalConfigError as exc:
        print(f"eval config error: {exc}", file=sys.stderr)
        return 2

    registry = build_registry(get_settings())
    persona_provider, persona_cfg = registry.llm(PERSONA_FEATURE)
    mock = persona_provider.name == "mock"
    print(f"persona model: {persona_provider.name}/{persona_cfg.model}")
    if not args.no_judge:
        judge_provider, judge_cfg = registry.llm(JUDGE_FEATURE)
        print(f"judge model:   {judge_provider.name}/{judge_cfg.model}")

    runner = EvalRunner(
        eval_set, registry, use_judge=not args.no_judge, concurrency=args.concurrency
    )
    results = await runner.run(suites=args.suite, case_ids=args.case)
    if not results:
        print("no scenarios matched", file=sys.stderr)
        return 2

    for r in sorted(results, key=lambda r: (r.suite, r.scenario_id)):
        mark = "PASS" if r.passed else "FAIL"
        print(f"[{mark}] {r.suite}/{r.scenario_id}: {r.reason}")
        if not r.passed:
            # Senaryolar sentetik; cevabı göstermek hatayı anlamanın en hızlı yolu.
            print("       reply: " + r.reply.replace("\n", " ")[:400])

    print()
    all_ok = True
    for s in runner.score(results):
        verdict = "ok" if s.ok else "BELOW THRESHOLD"
        rate = f"{s.passed}/{s.total} = {s.rate:.0%}"
        print(f"{s.suite}: {rate} (threshold {s.threshold:.0%}) {verdict}")
        all_ok &= s.ok

    if mock:
        print("\nmock LLM: scores are meaningless, threshold not enforced")
        return 0
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
