"""Агрегаты по реестру и БКИ. Общий код для обучения и скоринга."""
import pandas as pd

DPD_LABELS = ["0", "1-29", "30-89", "90+"]
TRACK_RISK_ORDER = {"ok": 0, "first": 1, "problem": 2}


def owner_mask(persons: pd.DataFrame, share_threshold: float) -> pd.Series:
    """Чьи история и опыт учитываются: ИП, директор ООО и участники с долей больше порога."""
    return persons["is_director"] | (persons["share"] > share_threshold)


def _relevant_subjects(bki_subjects: pd.DataFrame, persons: pd.DataFrame, share_threshold: float) -> pd.DataFrame:
    owners = persons.loc[owner_mask(persons, share_threshold), ["application_id", "inn"]]
    owners = owners.rename(columns={"inn": "subject_inn"}).assign(is_owner=True)
    merged = bki_subjects.merge(owners, on=["application_id", "subject_inn"], how="left")
    return merged[merged["is_borrower"] | merged["is_owner"].notna()]


def max_dpd(bki_subjects, persons, application_ids, share_threshold: float) -> pd.Series:
    """Худшая просрочка за 24 месяца по заёмщику и собственникам; NaN — истории нет ни у кого."""
    subjects = _relevant_subjects(bki_subjects, persons, share_threshold)
    subjects = subjects[subjects["has_history"]]
    return subjects.groupby("application_id")["max_dpd_24m"].max().reindex(pd.Index(application_ids))


def dpd_category(days: pd.Series) -> pd.Series:
    """Интервал просрочки; отсутствие истории — отдельная категория, а не «0»."""
    category = pd.cut(days, bins=[-1, 0, 29, 89, float("inf")], labels=DPD_LABELS).astype(object)
    return category.where(days.notna(), "no_history").astype(str)


def borrower_inquiries(bki_subjects, application_ids) -> pd.Series:
    """Запросы кредитной истории другими кредиторами за 90 дней: по ИП или по компании."""
    borrowers = bki_subjects[bki_subjects["is_borrower"]].set_index("application_id")
    return borrowers["inquiries_90d"].reindex(pd.Index(application_ids)).fillna(0)


def kept_loans(bki_loans: pd.DataFrame, applications: pd.DataFrame) -> pd.DataFrame:
    """Кредиты заёмщика без тех, которые гасятся рефинансированием."""
    refinanced = applications[["application_id", "refinance_loan_ids"]].explode("refinance_loan_ids").dropna()
    refinanced = refinanced.rename(columns={"refinance_loan_ids": "loan_id"}).astype({"loan_id": "int64"})
    merged = bki_loans.merge(refinanced, on=["application_id", "loan_id"], how="left", indicator=True)
    return merged[merged["_merge"] == "left_only"].drop(columns="_merge")


def business_debt(loans: pd.DataFrame, application_ids) -> pd.Series:
    """Остаток бизнес-кредитов. Личные кредиты ИП сюда не входят: они учитываются через платежи."""
    business = loans[loans["is_business"]]
    return business.groupby("application_id")["balance"].sum().reindex(pd.Index(application_ids)).fillna(0.0)


def existing_payments(loans: pd.DataFrame, application_ids) -> pd.Series:
    """Ежемесячные платежи по всем кредитам заёмщика: у ИП вместе с личными."""
    return loans.groupby("application_id")["monthly_payment"].sum().reindex(pd.Index(application_ids)).fillna(0.0)


def worst_track_record(persons: pd.DataFrame, application_ids, share_threshold: float) -> pd.Series:
    """Худший опыт собственников: problem хуже first, first хуже ok."""
    owners = persons[owner_mask(persons, share_threshold)]
    worst = owners["track_record"].map(TRACK_RISK_ORDER).groupby(owners["application_id"]).max()
    by_order = {order: name for name, order in TRACK_RISK_ORDER.items()}
    return worst.map(by_order).reindex(pd.Index(application_ids))
