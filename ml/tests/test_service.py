"""HTTP-сервис поверх SQLite-моков: те же данные, что увидит бэкенд в compose."""
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from alfa_ml.config import load_config
from alfa_ml.decision.heuristic import MODEL_VERSION
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
    assert response.json() == {"status": "ok", "database": "ok", "asOf": AS_OF, "modelVersion": MODEL_VERSION}


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
    assert set(loans[0]) == {"loanId", "lender", "balance", "monthlyPayment", "remainingMonths", "endDate"}
    months = int(expected["remaining_months"].iloc[0])
    assert loans[0]["endDate"] == (pd.Timestamp(AS_OF) + pd.DateOffset(months=months)).date().isoformat()


def test_cors_closed_by_default(client, engine):
    headers = {"Origin": "http://localhost:8080"}
    assert "access-control-allow-origin" not in client.get("/health", headers=headers).headers
    opened = TestClient(create_app(Settings(cors_origins=("http://localhost:8080",)), engine))
    assert opened.get("/health", headers=headers).headers["access-control-allow-origin"] == "http://localhost:8080"


def test_openapi_lists_endpoints(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/health", "/score", "/companies/{inn}", "/companies/{inn}/loans"} <= set(paths)


def _request(app_row, **overrides):
    purpose = app_row["purpose"] if app_row["purpose"] in SCORING["purposes"] else "working_capital"
    body = {
        "applicationId": f"app-{app_row['application_id']}", "inn": app_row["inn"],
        "creditSum": int(app_row["requested_amount"]), "termMonths": int(app_row["term_months"]),
        "purpose": purpose, "refinanceLoanIds": list(app_row["refinance_loan_ids"]) if purpose == "refinancing" else [],
        "revenueLast12m": float(app_row["declared_revenue"]), "bkiConsent": True,
        "useAlfaAccount": False, "statements": None,
    }
    body.update(overrides)
    return body


@pytest.fixture(scope="module")
def scored(client, batch):
    """Ответы /score на заявки демо-среза (выручка из анкеты положительная, сумма в лимитах)."""
    apps = batch.applications.merge(batch.labels[["application_id", "heuristic_reason"]], on="application_id")
    apps = apps[(apps["declared_revenue"] > 0) & apps["requested_amount"].between(100_000, 30_000_000)]
    responses = []
    for _, row in apps.iloc[:150].iterrows():
        response = client.post("/score", json=_request(row))
        assert response.status_code == 200, response.text
        responses.append((row, response.json()))
    return responses


def test_score_decisions_follow_the_rules(scored):
    decisions = [body["decision"] for _, body in scored]
    assert {"APPROVED", "OFFER"} <= set(decisions)
    for row, body in scored:
        requested = int(row["requested_amount"])
        if row["heuristic_reason"]:
            assert body["decision"] == "REJECTED" and body["stopRules"] == [row["heuristic_reason"]]
            continue
        assert body["stopRules"] == []
        if body["decision"] == "APPROVED":
            assert body["approved"]["creditSum"] == requested and body["approved"]["termMonths"] == row["term_months"]
            assert body["pd"] < 0.05 and body["rate"] in (18.0, 20.0) and body["product"] == "no_collateral"
        elif body["decision"] == "OFFER":
            maxima = {t["termMonths"]: t["maxSum"] for t in body["maxByTerm"]}
            assert 1 <= len(body["offers"]) <= 2 and body["documentsRequired"]
            for offer in body["offers"]:
                assert 100_000 <= offer["creditSum"] <= min(requested, maxima[offer["termMonths"]])
        elif body["decision"] == "INFO":
            assert body["offers"] == [] and body["documentsRequired"] and body["product"] is None
        else:
            assert body["pd"] > 0.30 and body["product"] is None


def test_request_and_response_field_names_match_contract(client):
    """Имена полей — ровно как в согласованном с бэкендом контракте."""
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    assert set(schemas["ScoreRequest"]["properties"]) == {
        "applicationId", "inn", "creditSum", "termMonths", "purpose", "refinanceLoanIds", "revenueLast12m",
        "bkiConsent", "useAlfaAccount", "statements"}
    assert set(schemas["ScoreResponse"]["properties"]) == {
        "decision", "stage", "product", "pd", "rate", "approved", "offers", "maxByTerm", "limit", "termLimit",
        "documentsRequired", "clientMessage", "reasons", "stopRules", "modelVersion"}


def _app_row(batch, application_id):
    return batch.applications.set_index("application_id").loc[application_id].copy().rename(application_id)


def test_score_rfm_message_is_neutral(client, batch):
    listed = batch.labels.loc[batch.labels["heuristic_reason"] == "rfm_list", "application_id"]
    if not len(listed):
        pytest.skip("в срезе нет перечня")
    row = _app_row(batch, listed.iloc[0])
    row["application_id"] = listed.iloc[0]
    body = client.post("/score", json=_request(row)).json()
    assert body["decision"] == "REJECTED" and body["stopRules"] == ["rfm_list"]
    assert body["clientMessage"] == "К сожалению, сейчас мы не можем предоставить кредит."
    assert any("Росфинмониторинг" in reason for reason in body["reasons"])  # причина — только во внутреннем логе


def test_score_is_deterministic(client, scored):
    row, body = scored[0]
    assert client.post("/score", json=_request(row)).json() == body


@pytest.mark.parametrize(("override", "status"), [
    ({"bkiConsent": False}, 422),
    ({"termMonths": 7}, 422),
    ({"creditSum": 50_000}, 422),
    ({"purpose": "other"}, 422),
    ({"refinanceLoanIds": [1]}, 422),
    ({"purpose": "refinancing", "refinanceLoanIds": [999_999_999]}, 422),
    ({"useAlfaAccount": True}, 501),
    ({"inn": "7707083893"}, 404),
    ({"inn": "123"}, 422),
    ({"revenueLast12m": 0}, 422),
])
def test_score_validation(client, scored, override, status):
    row, _ = scored[0]
    assert client.post("/score", json=_request(row, **override)).status_code == status


def test_score_asks_revenue_when_unknown(client, batch):
    org = batch.companies[(batch.companies["legal_form"] == "ip") & ~batch.companies["is_alfa_client"]
                          & (batch.companies["status"] == "active")].iloc[0]
    row = _app_row(batch, org["application_id"])
    row["application_id"] = org["application_id"]
    response = client.post("/score", json=_request(row, revenueLast12m=None, creditSum=300_000))
    assert response.status_code == 422 and "revenueLast12m" in response.json()["detail"]
