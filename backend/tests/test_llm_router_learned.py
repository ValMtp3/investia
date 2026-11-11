"""Tests TDD du routeur appris (étape 12h) — store fake en mémoire, zéro DB."""

from investia.llm.router import LearnedRouter, Neighbor


class FakeStore:
    def __init__(self, neighbors=None):
        self._neighbors = list(neighbors or [])
        self.recorded: list[tuple[str, str, bool]] = []

    async def neighbors(self, question: str, k: int = 7) -> list[Neighbor]:
        return self._neighbors[:k]

    async def record(self, question: str, model: str, success: bool) -> None:
        self.recorded.append((question, model, success))


def n(similarity: float, model: str, success: bool) -> Neighbor:
    return Neighbor(similarity=similarity, model=model, success=success)


async def test_knn_choisit_le_modele_qui_a_reussi():
    store = FakeStore([n(0.9, "small", True)] * 6)
    router = LearnedRouter(store)
    model, source = await router.choose("question test")
    assert model == "small"
    assert source == "learned"


async def test_fallback_regles_si_moins_de_5_feedbacks():
    store = FakeStore([n(0.9, "small", True)] * 4)
    router = LearnedRouter(store)
    model, source = await router.choose("analyse approfondie de la stratégie")
    assert source == "rules"
    assert model == "large"  # règle D44 : mot-clé « analyse » -> large


async def test_fallback_regles_si_ecart_trop_faible():
    store = FakeStore([n(0.9, "small", True), n(0.9, "large", True)] * 3)
    router = LearnedRouter(store)
    _model, source = await router.choose("question neutre sans mot-clé")
    assert source == "rules"


async def test_ponderation_par_similarite():
    # small est le plus proche mais a échoué ; large est plus lointain mais a réussi
    # -> large gagne : la similarité pondère, ce n'est pas un vote brut
    store = FakeStore([n(0.95, "small", False)] * 3 + [n(0.5, "large", True)] * 3)
    router = LearnedRouter(store)
    model, source = await router.choose("q")
    assert model == "large"
    assert source == "learned"


async def test_scores_ex_aequo_tombent_sur_les_regles():
    # que des échecs côté small -> score small = 0.0 = score large (absent) -> écart 0
    store = FakeStore([n(0.9, "small", False)] * 6)
    router = LearnedRouter(store)
    _model, source = await router.choose("q")
    assert source == "rules"


async def test_record_delegue_au_store():
    store = FakeStore()
    router = LearnedRouter(store)
    await router.record("q", "small", True)
    assert store.recorded == [("q", "small", True)]


async def test_k_parametre_limite_les_voisins():
    store = FakeStore([n(0.9, "small", True)] * 10)
    router = LearnedRouter(store, k=7)
    model, source = await router.choose("q")
    assert len(store._neighbors[:7]) == 7
    assert (model, source) == ("small", "learned")
