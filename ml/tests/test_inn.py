import numpy as np
import pytest

from alfa_ml.inn import is_valid_inn
from alfa_ml.synth.ids import InnFactory


@pytest.mark.parametrize("inn", ["7707083893", "500100732259"])
def test_known_valid_inns(inn):
    assert is_valid_inn(inn)


@pytest.mark.parametrize("inn", ["7707083894", "500100732258", "123", "77070838931", "77070A3893", ""])
def test_invalid_inns(inn):
    assert not is_valid_inn(inn)


def test_factory_issues_unique_valid_inns():
    factory = InnFactory(np.random.default_rng(0))
    companies = factory.companies(3000)
    persons = factory.persons(3000)
    more = factory.companies(3000)
    assert all(len(x) == 10 for x in companies) and all(len(x) == 12 for x in persons)
    assert all(is_valid_inn(x) for x in [*companies, *persons, *more])
    assert len(set(companies) | set(more)) == 6000
