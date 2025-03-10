from typing import TYPE_CHECKING, Dict, List, Optional, Union

from docarray import DocumentArray

from jina.logging.logger import JinaLogger
from jina.serve.networking import GrpcConnectionPool
from jina.serve.runtimes.gateway.graph.topology_graph import TopologyGraph
from jina.serve.runtimes.gateway.request_handling import RequestHandler
from jina.serve.stream import RequestStreamer

__all__ = ['GatewayStreamer']

if TYPE_CHECKING:
    from prometheus_client import CollectorRegistry


class GatewayStreamer:
    """
    Wrapper object to be used in a Custom Gateway. Naming to be defined
    """

    def __init__(
        self,
        graph_representation: Dict,
        executor_addresses: Dict[str, Union[str, List[str]]],
        graph_conditions: Dict = {},
        deployments_disable_reduce: List[str] = [],
        timeout_send: Optional[float] = None,
        retries: int = 0,
        compression: Optional[str] = None,
        runtime_name: str = 'custom gateway',
        prefetch: int = 0,
        logger: Optional['JinaLogger'] = None,
        metrics_registry: Optional['CollectorRegistry'] = None,
    ):
        """
        :param graph_representation: A dictionary describing the topology of the Deployments. 2 special nodes are expected, the name `start-gateway` and `end-gateway` to
            determine the nodes that receive the very first request and the ones whose response needs to be sent back to the client. All the nodes with no outgoing nodes
            will be considered to be floating, and they will be "flagged" so that the user can ignore their tasks and not await them.
        :param executor_addresses: dictionary JSON with the input addresses of each Deployment. Each Executor can have one single address or a list of addrresses for each Executor
        :param graph_conditions: Dictionary stating which filtering conditions each Executor in the graph requires to receive Documents.
        :param deployments_disable_reduce: list of Executor disabling the built-in merging mechanism.
        :param timeout_send: Timeout to be considered when sending requests to Executors
        :param retries: Number of retries to try to make successfull sendings to Executors
        :param compression: The compression mechanism used when sending requests from the Head to the WorkerRuntimes. For more details, check https://grpc.github.io/grpc/python/grpc.html#compression.
        :param runtime_name: Name to be used for monitoring.
        :param prefetch: How many Requests are processed from the Client at the same time.
        :param logger: Optional logger that can be used for logging
        :param metrics_registry: optional metrics registry for prometheus used if we need to expose metrics
        """
        topology_graph = self._create_topology_graph(
            graph_representation,
            graph_conditions,
            deployments_disable_reduce,
            timeout_send,
            retries,
        )
        self.runtime_name = runtime_name

        self._connection_pool = self._create_connection_pool(
            executor_addresses, compression, metrics_registry, logger
        )
        request_handler = RequestHandler(metrics_registry, runtime_name)

        self._streamer = RequestStreamer(
            request_handler=request_handler.handle_request(
                graph=topology_graph, connection_pool=self._connection_pool
            ),
            result_handler=request_handler.handle_result(),
            prefetch=prefetch,
            logger=logger,
        )
        self._streamer.Call = self._streamer.stream

    def _create_topology_graph(
        self,
        graph_description,
        graph_conditions,
        deployments_disable_reduce,
        timeout_send,
        retries,
    ):
        # check if it should be in K8s, maybe ConnectionPoolFactory to be created
        return TopologyGraph(
            graph_representation=graph_description,
            graph_conditions=graph_conditions,
            deployments_disable_reduce=deployments_disable_reduce,
            timeout_send=timeout_send,
            retries=retries,
        )

    def _create_connection_pool(
        self, deployments_addresses, compression, metrics_registry, logger
    ):
        # add the connections needed
        connection_pool = GrpcConnectionPool(
            runtime_name=self.runtime_name,
            logger=logger,
            compression=compression,
            metrics_registry=metrics_registry,
        )
        for deployment_name, addresses in deployments_addresses.items():
            for address in addresses:
                connection_pool.add_connection(
                    deployment=deployment_name, address=address, head=True
                )

        return connection_pool

    def stream(self, *args, **kwargs):
        """
        stream requests from client iterator and stream responses back.

        :param args: positional arguments to be passed to inner RequestStreamer
        :param kwargs: keyword arguments to be passed to inner RequestStreamer
        :return: An iterator over the responses from the Executors
        """
        return self._streamer.stream(*args, **kwargs)

    async def stream_docs(
        self,
        docs: DocumentArray,
        request_size: int,
        return_results: bool = False,
        exec_endpoint: Optional[str] = None,
        target_executor: Optional[str] = None,
        parameters: Optional[Dict] = None,
    ):
        """
        stream documents and stream responses back.

        :param docs: The Documents to be sent to all the Executors
        :param request_size: The amount of Documents to be put inside a single request.
        :param return_results: If set to True, the generator will yield Responses and not `DocumentArrays`
        :param exec_endpoint: The executor endpoint to which to send the Documents
        :param target_executor: A regex expression indicating the Executors that should receive the Request
        :param parameters: Parameters to be attached to the Requests
        :yield: Yields DocumentArrays or Responses from the Executors
        """
        from jina.types.request.data import DataRequest

        def _req_generator():
            for docs_batch in docs.batch(batch_size=request_size, shuffle=False):
                req = DataRequest()
                req.data.docs = docs_batch
                if exec_endpoint:
                    req.header.exec_endpoint = exec_endpoint
                if target_executor:
                    req.header.target_executor = target_executor
                if parameters:
                    req.parameters = parameters
                yield req

        async for resp in self._streamer.stream(_req_generator()):
            if return_results:
                yield resp
            else:
                yield resp.docs

    async def close(self):
        """
        Gratefully closes the object making sure all the floating requests are taken care and the connections are closed gracefully
        """
        await self._streamer.wait_floating_requests_end()
        await self._connection_pool.close()

    Call = stream
