import random

from poker_arena.cards import parse_cards
from poker_arena.engine import ActionType, GameView, Street
from poker_arena.evolve import EvolvedBot, Genome, evolve


def test_mutation_stays_in_bounds() -> None:
    rng = random.Random(0)
    g = Genome()
    for _ in range(200):
        g = g.mutate(rng, strength=3.0)
        assert 0.3 <= g.value_equity <= 0.95
        assert 0.0 <= g.bluff_rate <= 0.6
        assert 0.2 <= g.bet_size <= 2.0


def test_crossover_takes_genes_from_parents() -> None:
    rng = random.Random(1)
    a, b = Genome(bet_size=0.5), Genome(bet_size=1.5, bluff_rate=0.4)
    child = Genome.crossover(a, b, rng)
    assert child.bet_size in (0.5, 1.5) and child.bluff_rate in (0.1, 0.4)


def test_evolved_bot_follows_genome() -> None:
    view = GameView(
        seat=0, hole_cards=tuple(parse_cards("As Ah")), board=(), street=Street.PREFLOP, pot=15,
        stack=1000, to_call=5, current_bet=10, min_raise_to=20, max_raise_to=1000, big_blind=10,
        num_active=2, stacks=(1000, 1000), history=(),
    )
    tight = EvolvedBot(Genome(play_threshold=25, raise_threshold=25), seed=0)
    loose = EvolvedBot(Genome(raise_threshold=5), seed=0)
    assert tight.decide(view).action is ActionType.FOLD
    d = loose.decide(view)
    assert d.action is ActionType.RAISE and "基因" in d.thought


def test_evolve_is_reproducible() -> None:
    kwargs = dict(generations=2, population_size=4, seed=7, tables_per_genome=1, hands_per_match=6, iterations=15)
    best1, reports1 = evolve(**kwargs)
    best2, reports2 = evolve(**kwargs)
    assert best1 == best2
    assert len(reports1) == 2
    assert [r.best_fitness for r in reports1] == [r.best_fitness for r in reports2]
