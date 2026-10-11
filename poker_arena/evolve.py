"""進化系統：用基因演算法讓參數化機器人一代代變強。

    python -m poker_arena.evolve --generations 6 --population 8 --seed 1
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, dataclass

from poker_arena.bots import BaseBot, chen_score, pot_odds
from poker_arena.cards import pretty
from poker_arena.engine import ActionType, Decision, GameView, Street, play_match


@dataclass(frozen=True)
class Genome:
    play_threshold: float = 6.0  # 翻牌前 Chen 分數高於此才入池
    raise_threshold: float = 10.0  # 翻牌前 Chen 分數高於此就加注
    value_equity: float = 0.6  # 翻牌後勝率高於此就下注/加注
    bet_size: float = 0.7  # 下注大小（底池比例）
    bluff_rate: float = 0.1  # 翻牌後詐唬機率
    call_margin: float = 0.0  # 跟注需要的勝率 = 賠率門檻 + call_margin

    def mutate(self, rng: random.Random, strength: float = 1.0) -> Genome:
        def jitter(value: float, scale: float, low: float, high: float) -> float:
            return round(min(high, max(low, value + rng.gauss(0, scale * strength))), 3)

        return Genome(
            play_threshold=jitter(self.play_threshold, 1.5, -1, 20),
            raise_threshold=jitter(self.raise_threshold, 1.5, -1, 20),
            value_equity=jitter(self.value_equity, 0.05, 0.3, 0.95),
            bet_size=jitter(self.bet_size, 0.15, 0.2, 2.0),
            bluff_rate=jitter(self.bluff_rate, 0.05, 0.0, 0.6),
            call_margin=jitter(self.call_margin, 0.04, -0.2, 0.3),
        )

    @staticmethod
    def crossover(a: Genome, b: Genome, rng: random.Random) -> Genome:
        da, db = asdict(a), asdict(b)
        return Genome(**{k: (da[k] if rng.random() < 0.5 else db[k]) for k in da})

    @staticmethod
    def random(rng: random.Random) -> Genome:
        return Genome(
            play_threshold=round(rng.uniform(0, 12), 3),
            raise_threshold=round(rng.uniform(4, 16), 3),
            value_equity=round(rng.uniform(0.4, 0.8), 3),
            bet_size=round(rng.uniform(0.3, 1.5), 3),
            bluff_rate=round(rng.uniform(0, 0.4), 3),
            call_margin=round(rng.uniform(-0.1, 0.15), 3),
        )


class EvolvedBot(BaseBot):
    """依基因決策的機器人，內心話會說出自己的門檻。"""

    style = "進化體"

    def __init__(self, genome: Genome, name: str = "進化體", seed: int | None = None, iterations: int = 150) -> None:
        super().__init__(name=name, seed=seed, iterations=iterations)
        self.genome = genome

    def decide(self, view: GameView) -> Decision:
        g = self.genome
        if view.street is Street.PREFLOP:
            score = chen_score(view.hole_cards)
            hand = pretty(view.hole_cards)
            if score >= g.raise_threshold:
                return Decision(
                    ActionType.RAISE, self.raise_to(view, g.bet_size),
                    f"{hand} 有 {score:.0f} 分，超過我的加注基因 {g.raise_threshold:.1f}，加注！",
                )
            if score >= g.play_threshold and view.to_call <= view.stack * 0.15:
                return Decision(ActionType.CALL, thought=f"{hand} {score:.0f} 分，達到入池門檻 {g.play_threshold:.1f}，跟。")
            return self.check_or_fold(f"{hand} 只有 {score:.0f} 分，基因說不玩。")

        eq = self.equity(view)
        odds = pot_odds(view)
        if eq >= g.value_equity:
            return Decision(
                ActionType.RAISE, self.raise_to(view, g.bet_size),
                f"勝率 {eq:.0%} ≥ 價值門檻 {g.value_equity:.0%}，下注 {g.bet_size:.0%} 底池。",
            )
        if self.rng.random() < g.bluff_rate:
            return Decision(
                ActionType.RAISE, self.raise_to(view, g.bet_size),
                f"勝率只有 {eq:.0%}，但我的基因有 {g.bluff_rate:.0%} 詐唬率。詐唬！",
            )
        if view.to_call == 0:
            return Decision(ActionType.CHECK, thought=f"勝率 {eq:.0%}，過牌。")
        if eq >= odds + g.call_margin:
            return Decision(ActionType.CALL, thought=f"勝率 {eq:.0%} ≥ 門檻 {odds + g.call_margin:.0%}，跟。")
        return Decision(ActionType.FOLD, thought=f"勝率 {eq:.0%} < 門檻 {odds + g.call_margin:.0%}，棄牌。")


@dataclass
class GenerationReport:
    generation: int
    best_fitness: float
    mean_fitness: float
    best_genome: Genome


def evaluate(
    population: list[Genome],
    rng: random.Random,
    tables_per_genome: int = 2,
    hands_per_match: int = 30,
    iterations: int = 40,
) -> list[float]:
    """每個基因打數場 4 人桌（隨機分桌），適應度 = 平均每場淨贏籌碼。"""
    totals = [0.0] * len(population)
    games = [0] * len(population)
    stack = 500
    for _ in range(tables_per_genome):
        order = list(range(len(population)))
        rng.shuffle(order)
        # 不滿 4 人的最後一桌從其他人補位（補位者的成績不計）
        for start in range(0, len(order), 4):
            table = order[start:start + 4]
            counted = len(table)
            while len(table) < 4:
                table.append(rng.choice(order))
            bots = [
                EvolvedBot(population[g], name=f"G{g}", seed=rng.randrange(2**32), iterations=iterations)
                for g in table
            ]
            result = play_match(bots, starting_stack=stack, max_hands=hands_per_match, seed=rng.randrange(2**32))
            for k in range(counted):
                totals[table[k]] += result.final_stacks[k] - stack
                games[table[k]] += 1
    return [t / max(n, 1) for t, n in zip(totals, games)]


def evolve(
    generations: int = 5,
    population_size: int = 8,
    seed: int | None = None,
    elite: int = 2,
    tables_per_genome: int = 2,
    hands_per_match: int = 30,
    iterations: int = 40,
) -> tuple[Genome, list[GenerationReport]]:
    """回傳最後一代的冠軍基因與每代的紀錄。"""
    if population_size < max(elite, 2):
        raise ValueError("population too small")
    rng = random.Random(seed)
    population = [Genome()] + [Genome.random(rng) for _ in range(population_size - 1)]
    reports: list[GenerationReport] = []
    best = population[0]
    for gen in range(generations):
        fitness = evaluate(population, rng, tables_per_genome, hands_per_match, iterations)
        ranked = sorted(zip(fitness, range(len(population))), key=lambda x: -x[0])
        best = population[ranked[0][1]]
        reports.append(GenerationReport(gen, ranked[0][0], sum(fitness) / len(fitness), best))
        parents = [population[i] for _, i in ranked[: max(elite, population_size // 2)]]
        children = [population[i] for _, i in ranked[:elite]]
        while len(children) < population_size:
            a, b = rng.sample(parents, 2) if len(parents) > 1 else (parents[0], parents[0])
            children.append(Genome.crossover(a, b, rng).mutate(rng))
        population = children
    return best, reports


def main(argv: list[str] | None = None) -> None:
    from poker_arena.bots import default_lineup

    parser = argparse.ArgumentParser(description="進化出更強的撲克機器人")
    parser.add_argument("--generations", type=int, default=6)
    parser.add_argument("--population", type=int, default=8)
    parser.add_argument("--hands", type=int, default=30, help="每場比賽手數")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--save", help="把冠軍基因存成 JSON")
    args = parser.parse_args(argv)

    champion, reports = evolve(args.generations, args.population, args.seed, hands_per_match=args.hands)
    for r in reports:
        print(f"第 {r.generation + 1} 代：最佳 {r.best_fitness:+.0f}，平均 {r.mean_fitness:+.0f}")
    print("冠軍基因：", asdict(champion))

    # 冠軍挑戰三位經典機器人
    classics = default_lineup(seed=args.seed, iterations=60)[:3]
    challenger = EvolvedBot(champion, name="進化冠軍", seed=args.seed, iterations=60)
    result = play_match([challenger, *classics], max_hands=60, seed=args.seed)
    print("冠軍挑戰賽（60 手）：")
    for name, s in sorted(zip(result.names, result.final_stacks), key=lambda x: -x[1]):
        print(f"  {name}：{s}")
    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(asdict(champion), f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
