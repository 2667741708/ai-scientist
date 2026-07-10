from open_coscientist.models import Hypothesis
from open_coscientist.nodes.ranking import (
    _comparison_mode,
    build_tournament_pairings,
    calculate_elo_update,
    hypothesis_identifier,
)


def _pair_key(pair: tuple[Hypothesis, Hypothesis]) -> tuple[str, str]:
    return tuple(sorted([hypothesis_identifier(pair[0]), hypothesis_identifier(pair[1])]))


def test_elo_update_moves_winner_up_and_loser_down() -> None:
    winner, loser = calculate_elo_update(1200, 1200)

    assert winner == 1212
    assert loser == 1188


def test_pairings_cover_all_hypotheses_and_do_not_repeat_small_pool() -> None:
    hypotheses = [
        Hypothesis(text="alpha retrieval audit", score=9),
        Hypothesis(text="beta contradiction benchmark", score=8),
        Hypothesis(text="gamma evidence attribution", score=7),
    ]

    pairings = build_tournament_pairings(hypotheses, seed_string="goal_0")

    assert len(pairings) == 3
    assert len({_pair_key(pair) for pair in pairings}) == 3
    covered = {id(hypothesis) for pair in pairings for hypothesis in pair}
    assert covered == {id(hypothesis) for hypothesis in hypotheses}


def test_pairings_prioritize_same_proximity_cluster() -> None:
    hypotheses = [
        Hypothesis(text="top ranked unrelated mechanism", score=10),
        Hypothesis(text="clustered retrieval contradiction audit one", score=8),
        Hypothesis(text="clustered retrieval contradiction audit two", score=7),
        Hypothesis(text="distant experiment planning idea", score=6),
    ]
    hypotheses[1].similarity_cluster_id = "cluster-a"
    hypotheses[2].similarity_cluster_id = "cluster-a"

    first_pair = build_tournament_pairings(hypotheses, seed_string="goal_0")[0]

    assert _pair_key(first_pair) == _pair_key((hypotheses[1], hypotheses[2]))


def test_top_ranked_pair_uses_debate_mode() -> None:
    hypotheses = [
        Hypothesis(text="best hypothesis", score=10),
        Hypothesis(text="second hypothesis", score=9),
        Hypothesis(text="third hypothesis", score=8),
    ]
    index_by_object = {id(hypothesis): index for index, hypothesis in enumerate(hypotheses)}

    assert _comparison_mode(hypotheses[0], hypotheses[1], index_by_object, len(hypotheses)) == (
        "debate",
        3,
    )
    assert _comparison_mode(hypotheses[0], hypotheses[2], index_by_object, len(hypotheses)) == (
        "single_turn",
        0,
    )
