import pytest

from cadenza import policies
from cadenza.context import DATA_DIR, parse_now

EXPECTED_TITLES = [
    ("1", "Sobre a Empório da Música"),
    ("1.1", "Missão"),
    ("1.2", "Dados da Empresa"),
    ("2", "Horário de Funcionamento"),
    ("3", "Formas de Pagamento"),
    ("3.1", "Regras de Parcelamento"),
    ("4", "Política de Trocas e Devoluções"),
    ("4.1", "Direito de Arrependimento (Compras Online)"),
    ("4.2", "Trocas por Defeito"),
    ("4.3", "Trocas por Preferência"),
    ("4.4", "Itens Não Elegíveis para Troca"),
    ("5", "Política de Frete e Entregas"),
    ("5.1", "Entregas na Região Metropolitana de Campo Grande"),
    ("5.2", "Entregas para Outras Cidades"),
    ("5.3", "Código de Rastreamento"),
    ("6", "Promoções e Descontos"),
    ("6.1", "Tipos de Promoção"),
    ("6.2", "Regras de Promoções"),
    ("7", "Atendimento via WhatsApp"),
    ("7.1", "Diretrizes de Atendimento"),
    ("7.2", "Fluxo de Atendimento Padrão"),
    ("7.3", "Situações Especiais"),
    ("8", "Garantia"),
    ("8.1", "Garantia Legal"),
    ("8.2", "Garantia do Fabricante"),
    ("8.3", "O que Não Cobre a Garantia"),
    ("9", "Privacidade e Proteção de Dados"),
    ("10", "Disposições Finais"),
]


@pytest.fixture(scope="module")
def sections():
    return policies.load_manual(DATA_DIR / "store_policies.pdf")


def test_manual_has_ten_sections_and_the_28_expected_titles(sections):
    assert [(s.number, s.title) for s in sections] == EXPECTED_TITLES
    assert len([s for s in sections if "." not in s.number]) == 10


def test_indented_numbered_steps_stay_inside_their_section(sections):
    flow = next(s for s in sections if s.number == "7.2")
    assert any(line.startswith("1. Saudação") for line in flow.lines)


def test_cover_headers_and_footers_are_removed(sections):
    full = "\n".join(s.text for s in sections)
    assert "Página" not in full
    assert "Manual de Políticas e Procedimentos" not in full
    assert "Última atualização" not in sections[-1].text


def test_layout_spacing_is_collapsed(sections):
    hours = policies.topic_text(sections, "horario")
    assert "Segunda a Sexta-feira 09:00 às 18:00" in hours


def test_conflicting_contacts_are_replaced_by_the_official_ones(sections):
    full = "\n".join(s.text for s in sections)
    assert "3321-4500" not in full
    assert "empóriodamusica" not in full
    assert policies.OFFICIAL_WHATSAPP in policies.topic_text(sections, "sobre_a_loja")
    assert policies.OFFICIAL_EMAIL in policies.topic_text(sections, "sobre_a_loja")


def test_topic_includes_its_subsections(sections):
    returns = policies.topic_text(sections, "trocas_devolucoes")
    assert "4.1 Direito de Arrependimento" in returns
    assert "4.4 Itens Não Elegíveis" in returns
    assert "5. " not in returns


def test_every_topic_maps_to_non_empty_text(sections):
    for topic in policies.TOPIC_SECTIONS:
        assert policies.topic_text(sections, topic)


def test_installment_conflict_comes_with_a_resolution_note():
    assert "3.1" in policies.TOPIC_NOTES["pagamento"]
    assert set(policies.TOPIC_NOTES) <= set(policies.TOPIC_SECTIONS)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        ("2026-11-03T10:00", "2026-11-03T10:00"),  # Tuesday, open
        ("2026-11-03T02:36", "2026-11-03T09:00"),  # Tuesday, before opening
        ("2026-11-06T18:00", "2026-11-07T09:00"),  # Friday at closing time
        ("2026-11-07T14:00", "2026-11-09T09:00"),  # Saturday afternoon
        ("2026-11-08T11:00", "2026-11-09T09:00"),  # Sunday
    ],
)
def test_next_opening_follows_the_manual_hours(now, expected):
    assert policies.next_opening(parse_now(now)) == parse_now(expected)
