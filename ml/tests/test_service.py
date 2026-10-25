"""HTTP-сервис поверх SQLite-моков: те же данные, что увидит бэкенд в compose."""
import numpy as np
import pytest
from fastapi.testclient import TestClient

from alfa_ml.config import load_config
from alfa_ml.features.build import okved_group, revenue_source
from alfa_ml.service.app import create_app
from alfa_ml.service.settings import Settings
from alfa_ml.sources.export import export_database, sqlite_engine
from alfa_ml.synth.datasets import Context, Segment, build_sample
from alfa_ml.synth.ids import IdCounter, InnFactory

AS_OF = "2026-11-01"
SCORING = load_config("scoring")


@pytest.fixture(scope="module")
def batch():
    gen = load_config("generator")
    ctx = Context(gen, SCORING, InnFactory(np.random.default_rng(5)), IdCounter(), IdCounter())
    return build_sample([Segment(300, gen)], (AS_OF, AS_OF), ctx, np.random.SeedSequence(5))[0]


@pytest.fixture(scope="module")
def engine(batch, tmp_path_factory):
    engine = sqlite_engine(tmp_path_factory.mktemp("mocks") / "mocks.sqlite")
    export_database(batch, engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def client(engine):
    return TestClient(create_app(Settings(), engine))


def test_health_reports_snapshot_date(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "asOf": AS_OF, "modelVersion": None}


def test_health_degraded_without_database(tmp_path):
    broken = sqlite_engine(tmp_path / "missing" / "mocks.sqlite")
    response = TestClient(create_app(Settings(), broken)).get("/health")
    assert response.status_code == 503
    assert response.json()["database"] == "error"


def test_company_card_ooo(client, batch):
    org = batch.companies[batch.companies["legal_form"] == "ooo"].iloc[0]
    card = client.get(f"/companies/{org['inn']}").json()
    persons = batch.persons[batch.persons["application_id"] == org["application_id"]]
    director = persons[persons["is_director"]].iloc[0]
    assert card["inn"] == org["inn"] and card["ogrn"] == org["ogrn"] and card["legalForm"] == "ooo"
    assert card["name"] == org["name"] and card["registrationDate"] == org["registration_date"].date().isoformat()
    assert card["director"] == {"inn": director["inn"], "name": director["name"], "share": None}
    assert {p["inn"] for p in card["participants"]} == set(persons.loc[persons["share"] > 0, "inn"])
    assert sum(p["share"] for p in card["participants"]) == pytest.approx(1.0, abs=1e-3)
    assert card["okvedGroup"] == okved_group(org[["okved_code"]], SCORING["okved_groups"]).iloc[0]


def test_company_card_ip(client, batch):
    org = batch.companies[batch.companies["legal_form"] == "ip"].iloc[0]
    card = client.get(f"/companies/{org['inn']}").json()
    assert card["legalForm"] == "ip" and len(card["ogrn"]) == 15
    assert card["director"]["inn"] == org["inn"]  # у ИП человек и организация — один ИНН
    assert card["participants"] == []


def test_revenue_known_matches_model_rule(client, batch):
    """Карточка говорит «спрашивать выручку» ровно тогда, когда модель взяла бы её из анкеты."""
    months = batch.monthly.groupby("application_id").size()
    for _, org in batch.companies.iloc[:80].iterrows():
        alfa_months = months.get(org["application_id"], 0) if org["is_alfa_client"] else 0
        expected = revenue_source([org["is_alfa_client"]], [alfa_months], [org["fns_revenue"]],
                                  SCORING["features"]["revenue_min_months"])[0]
        card = client.get(f"/companies/{org['inn']}").json()
        assert card["revenueKnown"] == (expected != "declared"), org["inn"]
        assert card["revenueSource"] == (None if expected == "declared" else expected)


def test_status_flags(client, batch):
    inactive = batch.companies[batch.companies["status"] != "active"]
    if len(inactive):
        card = client.get(f"/companies/{inactive.iloc[0]['inn']}").json()
        assert card["isActive"] is False and card["status"] == inactive.iloc[0]["status"]


@pytest.mark.parametrize(("inn", "status"), [("7707083893", 404), ("7707083894", 422), ("123", 422)])
def test_unknown_or_invalid_inn(client, inn, status):
    assert client.get(f"/companies/{inn}").status_code == status
    assert client.get(f"/companies/{inn}/loans").status_code == status


def test_loans_are_business_loans_by_balance(client, batch):
    business = batch.bki_loans[batch.bki_loans["is_business"]]
    app_id = business["application_id"].value_counts().index[0]
    inn = batch.companies.set_index("application_id").loc[app_id, "inn"]
    loans = client.get(f"/companies/{inn}/loans").json()["loans"]
    expected = business[business["application_id"] == app_id].sort_values("balance", ascending=False)
    assert [l["loanId"] for l in loans] == expected["loan_id"].tolist()
    assert loans[0]["balance"] == pytest.approx(expected["balance"].iloc[0])


def test_cors_closed_by_default(client, engine):
    headers = {"Origin": "http://localhost:8080"}
    assert "access-control-allow-origin" not in client.get("/health", headers=headers).headers
    opened = TestClient(create_app(Settings(cors_origins=("http://localhost:8080",)), engine))
    assert opened.get("/health", headers=headers).headers["access-control-allow-origin"] == "http://localhost:8080"


def test_openapi_lists_endpoints(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/health", "/companies/{inn}", "/companies/{inn}/loans"} <= set(paths)
