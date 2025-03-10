import json
import os

import pytest

from jina import __version__
from jina.hubble import HubExecutor
from jina.hubble.hubio import HubIO
from jina.orchestrate.deployments.config.helper import (
    get_base_executor_version,
    get_image_name,
    to_compatible_name,
)


@pytest.mark.parametrize('is_master', (True, False))
def test_version(is_master, requests_mock):
    if is_master:
        count = 0
    else:
        # current version is published already
        count = 3
    requests_mock.get(
        'https://registry.hub.docker.com/v2/repositories/jinaai/jina/tags',
        text=json.dumps(
            {
                'count': count,
                'next': 'abc',
                'previous': 'def',
                'results': [{'a': 'b', 'c': 'd'}],
            }
        ),
    )
    v = get_base_executor_version()
    if is_master:
        assert v == 'master'
    else:
        assert v == __version__


def test_to_compatible_name():
    assert to_compatible_name('executor/hey-ha_HO') == 'executor-hey-ha-ho'


def test_get_image_name(mocker, monkeypatch):
    mock = mocker.Mock()

    def _mock_fetch(
        name,
        tag,
        image_required=True,
        rebuild_image=True,
        *,
        secret=None,
        force=False,
    ):
        mock(name=name, rebuild_image=rebuild_image)

        return (
            HubExecutor(
                uuid='hello',
                name=name,
                tag='v0',
                image_name=f'jinahub/{name}',
                md5sum=None,
                visibility=True,
                archive_url=None,
            ),
            False,
        )

    monkeypatch.setattr(HubIO, 'fetch_meta', _mock_fetch)

    uses = 'jinahub://DummyExecutor'

    image_name = get_image_name(uses)

    assert image_name == 'jinahub/DummyExecutor'

    _, mock_kwargs = mock.call_args_list[0]
    assert mock_kwargs['rebuild_image'] is True  # default value must be True

    os.environ['JINA_HUB_NO_IMAGE_REBUILD'] = '1'

    get_image_name(uses)

    del os.environ['JINA_HUB_NO_IMAGE_REBUILD']

    _, mock_kwargs = mock.call_args_list[1]
    assert mock_kwargs['rebuild_image'] is False  # env var is set, so it must be False
