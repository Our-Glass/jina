import json
import os
from typing import Dict, Tuple, Union

import pytest

from jina.helper import Namespace
from jina.hubble import HubExecutor
from jina.hubble.hubio import HubIO
from jina.orchestrate.deployments.config.k8s import K8sDeploymentConfig
from jina.parsers import set_deployment_parser, set_gateway_parser
from jina.serve.networking import GrpcConnectionPool


def namespace_equal(
    n1: Union[Namespace, Dict], n2: Union[Namespace, Dict], skip_attr: Tuple = ()
) -> bool:
    """
    Checks that two `Namespace` object have equal public attributes.
    It skips attributes that start with a underscore and additional `skip_attr`.
    """
    if n1 is None and n2 is None:
        return True
    for attr in filter(lambda x: x not in skip_attr and not x.startswith('_'), dir(n1)):
        if not getattr(n1, attr) == getattr(n2, attr):
            return False
    return True


@pytest.mark.parametrize('shards', [1, 5])
@pytest.mark.parametrize('uses_before', [None, 'jinahub+docker://HubBeforeExecutor'])
@pytest.mark.parametrize('uses_after', [None, 'docker://docker_after_image:latest'])
@pytest.mark.parametrize('uses_with', ['{"paramkey": "paramvalue"}', None])
@pytest.mark.parametrize('uses_metas', ['{"workspace": "workspacevalue"}', None])
def test_parse_args(
    shards: int,
    uses_with,
    uses_metas,
    uses_before,
    uses_after,
):
    args_list = ['--shards', str(shards), '--name', 'executor']
    if uses_before is not None:
        args_list.extend(['--uses-before', uses_before])

    if uses_after is not None:
        args_list.extend(['--uses-after', uses_after])

    if uses_with is not None:
        args_list.extend(['--uses-with', uses_with])

    if uses_metas is not None:
        args_list.extend(['--uses-metas', uses_metas])
    args = set_deployment_parser().parse_args(args_list)
    deployment_config = K8sDeploymentConfig(args, 'default-namespace')

    if shards > 1:
        assert namespace_equal(
            deployment_config.deployment_args['head_deployment'],
            args,
            skip_attr=(
                'runtime_cls',
                'pod_role',
                'port',
                'k8s_namespace',
                'name',
                'uses',
                'connection_list',
                'uses_with',
                'uses_metas',
                'uses_before_address',
                'uses_after_address',
                'port_monitoring',
            ),
        )
        assert (
            deployment_config.deployment_args['head_deployment'].k8s_namespace
            == 'default-namespace'
        )
        assert (
            deployment_config.deployment_args['head_deployment'].name == 'executor/head'
        )
        assert (
            deployment_config.deployment_args['head_deployment'].runtime_cls
            == 'HeadRuntime'
        )
        assert deployment_config.deployment_args['head_deployment'].uses is None
        assert (
            deployment_config.deployment_args['head_deployment'].uses_before
            == uses_before
        )
        assert (
            deployment_config.deployment_args['head_deployment'].uses_after
            == uses_after
        )
        assert deployment_config.deployment_args['head_deployment'].uses_metas is None
        assert deployment_config.deployment_args['head_deployment'].uses_with is None
        if uses_before is None:
            assert (
                deployment_config.deployment_args['head_deployment'].uses_before_address
                is None
            )
        else:
            assert (
                deployment_config.deployment_args['head_deployment'].uses_before_address
                == '127.0.0.1:8081'
            )
        if uses_after is None:
            assert (
                deployment_config.deployment_args['head_deployment'].uses_after_address
                is None
            )
        else:
            assert (
                deployment_config.deployment_args['head_deployment'].uses_after_address
                == '127.0.0.1:8082'
            )
        candidate_connection_list = {
            str(i): f'executor-{i}.default-namespace.svc:8080' for i in range(shards)
        }
        assert deployment_config.deployment_args[
            'head_deployment'
        ].connection_list == json.dumps(candidate_connection_list)

    for i, depl_arg in enumerate(deployment_config.deployment_args['deployments']):
        import copy

        assert (
            depl_arg.name == f'executor-{i}'
            if len(deployment_config.deployment_args['deployments']) > 1
            else 'executor'
        )
        assert depl_arg.port_monitoring == GrpcConnectionPool.K8S_PORT_MONITORING
        cargs = copy.deepcopy(args)
        cargs.shard_id = i
        assert namespace_equal(
            depl_arg,
            cargs,
            skip_attr=(
                'runtime_cls',
                'pod_role',
                'port',
                'k8s_namespace',
                'uses_before',  # the uses_before and after is head business
                'uses_after',
                'name',
                'port_monitoring',
            ),
        )


@pytest.mark.parametrize('shards', [1, 5])
def test_parse_args_custom_executor(shards: int):
    uses_before = 'custom-executor-before'
    uses_after = 'custom-executor-after'
    args = set_deployment_parser().parse_args(
        [
            '--shards',
            str(shards),
            '--uses-before',
            uses_before,
            '--uses-after',
            uses_after,
            '--name',
            'executor',
        ]
    )
    deployment_config = K8sDeploymentConfig(args, 'default-namespace')

    if shards > 1:
        assert (
            deployment_config.deployment_args['head_deployment'].runtime_cls
            == 'HeadRuntime'
        )
        assert (
            deployment_config.deployment_args['head_deployment'].uses_before
            == uses_before
        )
        assert deployment_config.deployment_args['head_deployment'].uses is None
        assert (
            deployment_config.deployment_args['head_deployment'].uses_after
            == uses_after
        )
        assert (
            deployment_config.deployment_args['head_deployment'].uses_before_address
            == f'127.0.0.1:{GrpcConnectionPool.K8S_PORT_USES_BEFORE}'
        )
        assert (
            deployment_config.deployment_args['head_deployment'].uses_after_address
            == f'127.0.0.1:{GrpcConnectionPool.K8S_PORT_USES_AFTER}'
        )

    for i, depl_arg in enumerate(deployment_config.deployment_args['deployments']):
        import copy

        assert (
            depl_arg.name == f'executor-{i}'
            if len(deployment_config.deployment_args['deployments']) > 1
            else 'executor'
        )
        cargs = copy.deepcopy(args)
        cargs.shard_id = i
        assert namespace_equal(
            depl_arg,
            cargs,
            skip_attr=(
                'uses_before',
                'uses_after',
                'port',
                'k8s_namespace',
                'name',
                'port_monitoring',
            ),
        )


@pytest.mark.parametrize(
    ['name', 'shards'],
    [
        (
            'gateway',
            '1',
        ),
        (
            'test-deployment',
            '1',
        ),
        (
            'test-deployment',
            '2',
        ),
    ],
)
@pytest.mark.parametrize('gpus', ['0', '1'])
def test_deployments(name: str, shards: str, gpus):
    args = set_deployment_parser().parse_args(
        ['--name', name, '--shards', shards, '--gpus', gpus]
    )
    deployment_config = K8sDeploymentConfig(args, 'ns')

    if name != 'gateway' and int(shards) > int(1):
        head_deployment = deployment_config.head_deployment
        assert head_deployment.deployment_args.gpus is None

    actual_deployments = deployment_config.worker_deployments

    assert len(actual_deployments) == int(shards)
    for i, deploy in enumerate(actual_deployments):
        assert deploy.deployment_args.gpus == gpus
        if int(shards) > 1:
            assert deploy.name == f'{name}-{i}'
        else:
            assert deploy.name == name
        assert deploy.jina_deployment_name == name
        assert deploy.shard_id == i


def assert_config_map_config(
    config_map: Dict, base_name: str, expected_config_map_data: Dict
):
    assert config_map['kind'] == 'ConfigMap'
    assert config_map['metadata'] == {
        'name': f'{base_name}-configmap',
        'namespace': 'default-namespace',
    }
    assert config_map['data'] == expected_config_map_data


@pytest.mark.parametrize('deployments_addresses', [None, {'1': 'address.svc'}])
@pytest.mark.parametrize('custom_gateway', ['jinaai/jina:custom-gateway', None])
def test_k8s_yaml_gateway(deployments_addresses, custom_gateway):
    if custom_gateway:
        os.environ['JINA_GATEWAY_IMAGE'] = custom_gateway
    elif 'JINA_GATEWAY_IMAGE' in os.environ:
        del os.environ['JINA_GATEWAY_IMAGE']
    args = set_gateway_parser().parse_args(
        ['--env', 'ENV_VAR:ENV_VALUE', '--port', '32465']
    )  # envs are
    # ignored for gateway
    deployment_config = K8sDeploymentConfig(
        args, 'default-namespace', deployments_addresses
    )
    yaml_configs = deployment_config.to_kubernetes_yaml()
    assert len(yaml_configs) == 1
    name, configs = yaml_configs[0]
    assert name == 'gateway'
    assert len(configs) == 3  # 3 configs per yaml (configmap, service and deployment)
    config_map = configs[0]
    assert_config_map_config(
        config_map,
        'gateway',
        {
            'ENV_VAR': 'ENV_VALUE',
            'JINA_LOG_LEVEL': 'INFO',
            'pythonunbuffered': '1',
            'worker_class': 'uvicorn.workers.UvicornH11Worker',
        },
    )

    service = configs[1]
    assert service['kind'] == 'Service'
    assert service['metadata'] == {
        'name': 'gateway',
        'namespace': 'default-namespace',
        'labels': {'app': 'gateway'},
    }
    spec_service = service['spec']
    assert spec_service['type'] == 'ClusterIP'
    assert len(spec_service['ports']) == 1
    port = spec_service['ports'][0]
    assert port['name'] == 'port'
    assert port['protocol'] == 'TCP'
    assert port['port'] == 32465
    assert port['targetPort'] == 32465
    assert spec_service['selector'] == {'app': 'gateway'}

    deployment = configs[2]
    assert deployment['kind'] == 'Deployment'
    assert deployment['metadata'] == {
        'name': 'gateway',
        'namespace': 'default-namespace',
    }
    spec_deployment = deployment['spec']
    assert spec_deployment['replicas'] == 1  # no gateway replication for now
    assert spec_deployment['strategy'] == {
        'type': 'RollingUpdate',
        'rollingUpdate': {'maxSurge': 1, 'maxUnavailable': 0},
    }
    assert spec_deployment['selector'] == {'matchLabels': {'app': 'gateway'}}
    template = spec_deployment['template']
    assert template['metadata'] == {
        'labels': {
            'app': 'gateway',
            'jina_deployment_name': 'gateway',
            'shard_id': '',
            'pod_type': 'GATEWAY',
            'ns': 'default-namespace',
        },
        'annotations': {'linkerd.io/inject': 'enabled'},
    }
    spec = template['spec']
    containers = spec['containers']
    assert len(containers) == 1
    container = containers[0]
    assert container['name'] == 'gateway'
    assert (
        container['image'] == custom_gateway
        if custom_gateway
        else f'jinaai/jina:{deployment_config.worker_deployments[0].version}-py38-standard'
    )
    assert container['imagePullPolicy'] == 'IfNotPresent'
    assert container['command'] == ['jina']
    args = container['args']
    assert args[0] == 'gateway'
    assert '--k8s-namespace' in args
    assert args[args.index('--k8s-namespace') + 1] == 'default-namespace'
    assert '--port' in args
    assert args[args.index('--port') + 1] == '32465'
    assert '--env' not in args
    assert '--pod-role' in args
    assert args[args.index('--pod-role') + 1] == 'GATEWAY'
    if deployments_addresses is not None:
        assert '--deployments-addresses' in args
        assert args[args.index('--deployments-addresses') + 1] == json.dumps(
            deployments_addresses
        )


def assert_port_config(port_dict: Dict, name: str, port: int):
    assert port_dict['name'] == name
    assert port_dict['protocol'] == 'TCP'
    assert port_dict['port'] == port
    assert port_dict['targetPort'] == port


@pytest.mark.parametrize('shards', [3, 1])
@pytest.mark.parametrize(
    'uses', ['jinahub+docker://HubExecutor', 'docker://docker_image:latest']
)
@pytest.mark.parametrize('uses_before', [None, 'jinahub+docker://HubBeforeExecutor'])
@pytest.mark.parametrize('uses_after', [None, 'jinahub+docker://HubAfterExecutor'])
@pytest.mark.parametrize('uses_with', ['{"paramkey": "paramvalue"}', None])
@pytest.mark.parametrize('uses_metas', ['{"workspace": "workspacevalue"}', None])
@pytest.mark.parametrize('polling', ['ANY', 'ALL'])
def test_k8s_yaml_regular_deployment(
    uses_before,
    uses_after,
    uses,
    shards,
    uses_with,
    uses_metas,
    polling,
    monkeypatch,
):
    def _mock_fetch(
        name,
        tag,
        image_required=True,
        rebuild_image=True,
        *,
        secret=None,
        force=False,
    ):
        return (
            HubExecutor(
                uuid='hello',
                name='alias_dummy',
                tag='v0',
                image_name=f'jinahub/{name}',
                md5sum=None,
                visibility=True,
                archive_url=None,
            ),
            False,
        )

    monkeypatch.setattr(HubIO, 'fetch_meta', _mock_fetch)
    args_list = [
        '--name',
        'executor',
        '--uses',
        uses,
        '--env',
        'ENV_VAR:ENV_VALUE',
        '--replicas',
        '3',
        '--shards',
        str(shards),
        '--polling',
        str(polling),
    ]
    if uses_before is not None:
        args_list.extend(['--uses-before', uses_before])

    if uses_after is not None:
        args_list.extend(['--uses-after', uses_after])

    if uses_with is not None:
        args_list.extend(['--uses-with', uses_with])

    if uses_metas is not None:
        args_list.extend(['--uses-metas', uses_metas])

    args = set_deployment_parser().parse_args(args_list)
    # ignored for gateway
    deployment_config = K8sDeploymentConfig(args, 'default-namespace')
    yaml_configs = deployment_config.to_kubernetes_yaml()
    assert len(yaml_configs) == shards + (1 if shards > 1 else 0)

    if shards > 1:
        head_name, head_configs = yaml_configs[0]
        assert head_name == 'executor-head'
        assert (
            len(head_configs) == 3
        )  # 3 configs per yaml (configmap, service and deployment)
        config_map = head_configs[0]
        assert_config_map_config(
            config_map,
            'executor-head',
            {
                'ENV_VAR': 'ENV_VALUE',
                'JINA_LOG_LEVEL': 'INFO',
                'pythonunbuffered': '1',
                'worker_class': 'uvicorn.workers.UvicornH11Worker',
            },
        )
        head_service = head_configs[1]
        assert head_service['kind'] == 'Service'
        assert head_service['metadata'] == {
            'name': 'executor-head',
            'namespace': 'default-namespace',
            'labels': {'app': 'executor-head'},
        }
        head_spec_service = head_service['spec']
        assert head_spec_service['type'] == 'ClusterIP'
        assert len(head_spec_service['ports']) == 1
        head_port = head_spec_service['ports'][0]
        assert_port_config(head_port, 'port', 8080)
        assert head_spec_service['selector'] == {'app': 'executor-head'}

        head_deployment = head_configs[2]
        assert head_deployment['kind'] == 'Deployment'
        assert head_deployment['metadata'] == {
            'name': 'executor-head',
            'namespace': 'default-namespace',
        }
        head_spec_deployment = head_deployment['spec']
        assert head_spec_deployment['replicas'] == 1  # no head replication for now
        assert head_spec_deployment['strategy'] == {
            'type': 'RollingUpdate',
            'rollingUpdate': {'maxSurge': 1, 'maxUnavailable': 0},
        }
        assert head_spec_deployment['selector'] == {
            'matchLabels': {'app': 'executor-head'}
        }
        head_template = head_spec_deployment['template']
        assert head_template['metadata'] == {
            'labels': {
                'app': 'executor-head',
                'jina_deployment_name': 'executor',
                'shard_id': '',
                'pod_type': 'HEAD',
                'ns': 'default-namespace',
            },
            'annotations': {'linkerd.io/inject': 'enabled'},
        }

        head_spec = head_template['spec']
        head_containers = head_spec['containers']
        assert len(head_containers) == 1 + (1 if uses_before is not None else 0) + (
            1 if uses_after is not None else 0
        )
        head_runtime_container = head_containers[0]
        assert head_runtime_container['name'] == 'executor'
        assert (
            head_runtime_container['image']
            == f'jinaai/jina:{deployment_config.head_deployment.version}-py38-standard'
        )
        assert head_runtime_container['imagePullPolicy'] == 'IfNotPresent'
        assert head_runtime_container['command'] == ['jina']
        head_runtime_container_args = head_runtime_container['args']

        assert head_runtime_container_args[0] == 'executor'
        assert '--native' in head_runtime_container_args
        assert '--runtime-cls' in head_runtime_container_args
        assert (
            head_runtime_container_args[
                head_runtime_container_args.index('--runtime-cls') + 1
            ]
            == 'HeadRuntime'
        )
        assert '--name' in head_runtime_container_args
        assert (
            head_runtime_container_args[head_runtime_container_args.index('--name') + 1]
            == 'executor/head'
        )
        assert '--k8s-namespace' in head_runtime_container_args
        assert (
            head_runtime_container_args[
                head_runtime_container_args.index('--k8s-namespace') + 1
            ]
            == 'default-namespace'
        )
        assert '--port' in head_runtime_container_args
        assert (
            head_runtime_container_args[head_runtime_container_args.index('--port') + 1]
            == '8080'
        )
        assert '--env' not in head_runtime_container_args
        assert '--pod-role' in head_runtime_container_args
        assert (
            head_runtime_container_args[
                head_runtime_container_args.index('--pod-role') + 1
            ]
            == 'HEAD'
        )
        assert '--connection-list' in head_runtime_container_args
        connection_list_string = head_runtime_container_args[
            head_runtime_container_args.index('--connection-list') + 1
        ]
        assert connection_list_string == json.dumps(
            {
                str(shard_id): f'executor-{shard_id}.default-namespace.svc:8080'
                for shard_id in range(shards)
            }
        )

        if polling == 'ANY':
            assert '--polling' not in head_runtime_container_args
        else:
            assert '--polling' in head_runtime_container_args
            assert (
                head_runtime_container_args[
                    head_runtime_container_args.index('--polling') + 1
                ]
                == 'ALL'
            )

        if uses_before is not None:
            uses_before_container = head_containers[1]
            assert uses_before_container['name'] == 'uses-before'
            assert uses_before_container['image'] == 'jinahub/HubBeforeExecutor'
            assert uses_before_container['imagePullPolicy'] == 'IfNotPresent'
            assert uses_before_container['command'] == ['jina']
            uses_before_runtime_container_args = uses_before_container['args']

            assert uses_before_runtime_container_args[0] == 'executor'
            assert '--native' in uses_before_runtime_container_args
            assert '--name' in uses_before_runtime_container_args
            assert (
                uses_before_runtime_container_args[
                    uses_before_runtime_container_args.index('--name') + 1
                ]
                == 'executor/uses-before'
            )
            assert '--k8s-namespace' in uses_before_runtime_container_args
            assert (
                uses_before_runtime_container_args[
                    uses_before_runtime_container_args.index('--k8s-namespace') + 1
                ]
                == 'default-namespace'
            )
            assert '--port' in uses_before_runtime_container_args
            assert (
                uses_before_runtime_container_args[
                    uses_before_runtime_container_args.index('--port') + 1
                ]
                == '8081'
            )
            assert '--env' not in uses_before_runtime_container_args
            assert '--connection-list' not in uses_before_runtime_container_args

        if uses_after is not None:
            uses_after_container = head_containers[-1]
            assert uses_after_container['name'] == 'uses-after'
            assert uses_after_container['image'] == 'jinahub/HubAfterExecutor'
            assert uses_after_container['imagePullPolicy'] == 'IfNotPresent'
            assert uses_after_container['command'] == ['jina']
            uses_after_runtime_container_args = uses_after_container['args']

            assert uses_after_runtime_container_args[0] == 'executor'
            assert '--native' in uses_after_runtime_container_args
            assert '--name' in uses_after_runtime_container_args
            assert (
                uses_after_runtime_container_args[
                    uses_after_runtime_container_args.index('--name') + 1
                ]
                == 'executor/uses-after'
            )
            assert '--k8s-namespace' in uses_after_runtime_container_args
            assert (
                uses_after_runtime_container_args[
                    uses_after_runtime_container_args.index('--k8s-namespace') + 1
                ]
                == 'default-namespace'
            )
            assert '--port' in uses_after_runtime_container_args
            assert (
                uses_after_runtime_container_args[
                    uses_after_runtime_container_args.index('--port') + 1
                ]
                == '8082'
            )
            assert '--env' not in uses_after_runtime_container_args
            assert '--connection-list' not in uses_after_runtime_container_args

    for i, (shard_name, shard_configs) in enumerate(yaml_configs[1:]):
        name = f'executor-{i}' if shards > 1 else 'executor'
        assert shard_name == name
        assert (
            len(shard_configs) == 3
        )  # 3 configs per yaml (configmap, service and deployment
        config_map = shard_configs[0]
        assert_config_map_config(
            config_map,
            name,
            {
                'ENV_VAR': 'ENV_VALUE',
                'JINA_LOG_LEVEL': 'INFO',
                'pythonunbuffered': '1',
                'worker_class': 'uvicorn.workers.UvicornH11Worker',
            },
        )
        shard_service = shard_configs[1]
        assert shard_service['kind'] == 'Service'
        assert shard_service['metadata'] == {
            'name': name,
            'namespace': 'default-namespace',
            'labels': {'app': name},
        }
        shard_spec_service = shard_service['spec']
        assert shard_spec_service['type'] == 'ClusterIP'
        assert len(shard_spec_service['ports']) == 1
        shard_port = shard_spec_service['ports'][0]
        assert_port_config(shard_port, 'port', 8080)
        assert shard_spec_service['selector'] == {'app': name}

        shard_deployment = shard_configs[2]
        assert shard_deployment['kind'] == 'Deployment'
        assert shard_deployment['metadata'] == {
            'name': name,
            'namespace': 'default-namespace',
        }
        shard_spec_deployment = shard_deployment['spec']
        assert shard_spec_deployment['replicas'] == 3  # no head replication for now
        assert shard_spec_deployment['strategy'] == {
            'type': 'RollingUpdate',
            'rollingUpdate': {'maxSurge': 1, 'maxUnavailable': 0},
        }
        assert shard_spec_deployment['selector'] == {'matchLabels': {'app': name}}
        shard_template = shard_spec_deployment['template']
        assert shard_template['metadata'] == {
            'labels': {
                'app': name,
                'jina_deployment_name': 'executor',
                'shard_id': str(i),
                'pod_type': 'WORKER',
                'ns': 'default-namespace',
            },
            'annotations': {'linkerd.io/inject': 'enabled'},
        }

        shard_spec = shard_template['spec']
        shard_containers = shard_spec['containers']
        assert len(shard_containers) == 1
        shard_container = shard_containers[0]
        assert shard_container['name'] == 'executor'
        assert shard_container['image'] in {
            'jinahub/HubExecutor',
            'docker_image:latest',
        }
        assert shard_container['imagePullPolicy'] == 'IfNotPresent'
        assert shard_container['command'] == ['jina']
        shard_container_runtime_container_args = shard_container['args']
        assert shard_container_runtime_container_args[0] == 'executor'
        assert '--native' in shard_container_runtime_container_args
        assert '--name' in shard_container_runtime_container_args
        assert (
            shard_container_runtime_container_args[
                shard_container_runtime_container_args.index('--name') + 1
            ]
            == name
        )
        assert '--k8s-namespace' in shard_container_runtime_container_args
        assert (
            shard_container_runtime_container_args[
                shard_container_runtime_container_args.index('--k8s-namespace') + 1
            ]
            == 'default-namespace'
        )
        assert '--port' in shard_container_runtime_container_args
        assert (
            shard_container_runtime_container_args[
                shard_container_runtime_container_args.index('--port') + 1
            ]
            == '8080'
        )
        assert '--env' not in shard_container_runtime_container_args
        assert '--connection-list' not in shard_container_runtime_container_args

        if uses_with is not None:
            assert '--uses-with' in shard_container_runtime_container_args
            assert (
                shard_container_runtime_container_args[
                    shard_container_runtime_container_args.index('--uses-with') + 1
                ]
                == uses_with
            )
        else:
            assert '--uses-with' not in shard_container_runtime_container_args

        expected_uses_metas = {}
        if uses_metas is not None:
            expected_uses_metas = json.loads(uses_metas)
        assert '--uses-metas' in shard_container_runtime_container_args
        assert shard_container_runtime_container_args[
            shard_container_runtime_container_args.index('--uses-metas') + 1
        ] == json.dumps(expected_uses_metas)
