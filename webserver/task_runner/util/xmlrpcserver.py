import asyncio
import concurrent.futures
import functools
import threading
import select
import signal
import sys
import traceback
import selectors

# poll/select have the advantage of not requiring any extra file descriptor,
# contrarily to epoll/kqueue (also, they require a single syscall).
if hasattr(selectors, 'PollSelector'):
    _ServerSelector = selectors.PollSelector
else:
    _ServerSelector = selectors.SelectSelector

from xmlrpc.server import SimpleXMLRPCServer, SimpleXMLRPCRequestHandler
from xmlrpc.client import Fault, dumps, loads


def resolve_dotted_attribute(obj, attr, allow_dotted_names=True):
    """resolve_dotted_attribute(a, 'b.c.d') => a.b.c.d

    Resolves a dotted attribute name to an object.  Raises
    an AttributeError if any attribute in the chain starts with a '_'.

    If the optional allow_dotted_names argument is false, dots are not
    supported and this function operates similar to getattr(obj, attr).
    """

    if allow_dotted_names:
        attrs = attr.split('.')
    else:
        attrs = [attr]

    for i in attrs:
        if i.startswith('_'):
            raise AttributeError(
                'attempt to access private attribute "%s"' % i
                )
        else:
            obj = getattr(obj,i)
    return obj

class MatchAllXMLRPCRequestHandler(SimpleXMLRPCRequestHandler):
    rpc_paths = None

class StoppableXMLRPCServer(SimpleXMLRPCServer):
    allow_reuse_address = True

    def __init__(self, host, port):
        SimpleXMLRPCServer.__init__(self, (host, port),
                                    requestHandler=MatchAllXMLRPCRequestHandler,
                                    logRequests=False,
                                    bind_and_activate=False)
        self._activated = False
        self._stopper_thread = None
        # self._threads = []
        self.__is_shut_down = threading.Event()
        self.__shutdown_request = False

    def activate(self):
        if not self._activated:
            self.server_bind()
            self.server_activate()
            self._activated = True
        return self.server_address[1]

    def serve_forever(self, poll_interval=0.5):
        """Handle one request at a time until shutdown.

        Polls for shutdown every poll_interval seconds. Ignores
        self.timeout. If you need to do periodic tasks, do them in
        another thread.
        """
        self.__is_shut_down.clear()
        try:
            # XXX: Consider using another file descriptor or connecting to the
            # socket to wake this up instead of polling. Polling reduces our
            # responsiveness to a shutdown request and wastes cpu at all other
            # times.
            with _ServerSelector() as selector:
                selector.register(self, selectors.EVENT_READ)

                while not self.__shutdown_request:
                    ready = selector.select(poll_interval)
                    # bpo-35017: shutdown() called during select(), exit immediately.
                    if self.__shutdown_request:
                        break
                    if ready:
                        handler_thread = threading.Thread(target=self._handle_request_noblock())
                        handler_thread.daemon = True
                        handler_thread.start()
                        # self._threads.append(handler_thread)

                    self.service_actions()
        finally:
            self.__shutdown_request = False
            self.__is_shut_down.set()

    def serve(self):
        self.activate()
        try:
            self.serve_forever()
        except select.error:
            # Signals seem to cause this error with Python 2.6.
            if sys.version_info[:2] > (2, 6):
                raise
        self.server_close()
        if self._stopper_thread:
            self._stopper_thread.join()
            self._stopper_thread = None

    def shutdown(self):
        """Stops the serve_forever loop.

        Blocks until the loop has finished. This must be called while
        serve_forever() is running in another thread, or it will
        deadlock.
        """
        self.__shutdown_request = True
        self.__is_shut_down.wait()

    def stop(self):
        self._stopper_thread = threading.Thread(target=self.shutdown)
        self._stopper_thread.daemon = True
        self._stopper_thread.start()

    # copy from xmlrpc.server.SimpleXMLRPCDispatcher to inject the path to the _dispatcher
    def _marshaled_dispatch(self, data, dispatch_method = None, path = None):
        """Dispatches an XML-RPC method from marshalled (XML) data.

        XML-RPC methods are dispatched from the marshalled (XML) data
        using the _dispatch method and the result is returned as
        marshalled data. For backwards compatibility, a dispatch
        function can be provided as an argument (see comment in
        SimpleXMLRPCRequestHandler.do_POST) but overriding the
        existing method through subclassing is the preferred means
        of changing method dispatch behavior.
        """

        try:
            params, method = loads(data, use_builtin_types=self.use_builtin_types)

            # generate response
            if dispatch_method is not None:
                response = dispatch_method(method, params, path)
            else:
                response = self._dispatch(method, params, path)
            # wrap response in a singleton tuple
            response = (response,)
            response = dumps(response, methodresponse=1,
                             allow_none=self.allow_none, encoding=self.encoding)
        except Fault as fault:
            response = dumps(fault, allow_none=self.allow_none,
                             encoding=self.encoding)
        except:
            # report exception back to server
            exc_type, exc_value, exc_tb = sys.exc_info()
            # print('>>>>>>')
            # print(exc_type, exc_value)
            # traceback.print_tb(exc_tb)
            # print('<<<<<<<')
            try:
                response = dumps(
                    Fault(1, "%s:%s" % (exc_type, exc_value)),
                    encoding=self.encoding, allow_none=self.allow_none,
                    )
            finally:
                # Break reference cycle
                exc_type = exc_value = exc_tb = None

        return response.encode(self.encoding, 'xmlcharrefreplace')


    def _dispatch(self, method, params, path):
        """Dispatches the XML-RPC method.

        XML-RPC calls are forwarded to a registered function that
        matches the called XML-RPC method name. If no such function
        exists then the call is forwarded to the registered instance,
        if available.

        If the registered instance has a _dispatch method then that
        method will be called with the name of the XML-RPC method and
        its parameters as a tuple
        e.g. instance._dispatch('add',(2,3))

        If the registered instance does not have a _dispatch method
        then the instance will be searched to find a matching method
        and, if found, will be called.

        Methods beginning with an '_' are considered private and will
        not be called.
        """

        try:
            # call the matching registered function
            func = self.funcs[method]
        except KeyError:
            pass
        else:
            if func is not None:
                return func(path, *params)
            raise Exception('method "%s" is not supported' % method)

        if self.instance is not None:
            if hasattr(self.instance, '_dispatch'):
                # call the `_dispatch` method on the instance
                return self.instance._dispatch(method, params)

            # call the instance's method directly
            try:
                func = resolve_dotted_attribute(
                    self.instance,
                    method,
                    self.allow_dotted_names
                )
            except AttributeError:
                pass
            else:
                if func is not None:
                    return func(*params)

        raise Exception('method "%s" is not supported' % method)

class SignalHandler(object):

    def __init__(self, handler):
        self._handler = lambda signum, frame: handler()
        self._original = {}

    def __enter__(self):
        for name in 'SIGINT', 'SIGTERM', 'SIGHUP':
            if hasattr(signal, name):
                try:
                    orig = signal.signal(getattr(signal, name), self._handler)
                except ValueError:  # Not in main thread
                    return
                self._original[name] = orig

    def __exit__(self, *exc_info):
        while self._original:
            name, handler = self._original.popitem()
            signal.signal(getattr(signal, name), handler)

class XMLRPCServer(threading.Thread):
    def __init__(self, rpc_proxy, host='0.0.0.0', port=8270):
        super().__init__()
        self.server = StoppableXMLRPCServer(host, port)
        self.rpc_proxy = rpc_proxy
        self.name = 'XMLRPCServer'

    @property
    def rpc_loop(self):
        return self.rpc_proxy['loop']

    def run(self):
        self.server.register_function(self.get_keyword_names)
        self.server.register_function(self.run_keyword)
        self.server.register_function(self.get_keyword_arguments)
        self.server.register_function(self.get_keyword_documentation)
        # self.server.register_function(self.stop_remote_server)

        self.server.activate()
        with SignalHandler(self.server.stop):
            self.server.serve()

    def get_keyword_names(self, path):
        if path not in self.rpc_proxy:
            # print(f'endpoint {path} not found in the proxy')
            return []
        fut = asyncio.run_coroutine_threadsafe(self.rpc_proxy[path].request.get_keyword_names(), self.rpc_loop)
        return fut.result()

    def run_keyword(self, path, name, args, kwargs=None):
        if path not in self.rpc_proxy:
            return None
        # if name == 'stop_remote_server':
        #     return KeywordRunner(self.stop_remote_server).run_keyword(args, kwargs)
        fut = asyncio.run_coroutine_threadsafe(self.rpc_proxy[path].request.run_keyword(name, args, kwargs), self.rpc_loop)
        return fut.result()

    def get_keyword_arguments(self, path, name):
        if path not in self.rpc_proxy:
            return None
        if name == 'stop_remote_server':
            return []
        fut = asyncio.run_coroutine_threadsafe(self.rpc_proxy[path].request.get_keyword_arguments(name), self.rpc_loop)
        return fut.result()

    def get_keyword_documentation(self, path, name):
        if path not in self.rpc_proxy:
            return None
        if name == 'stop_remote_server':
            return ('Stop the remote server unless stopping is disabled.\n\n'
                    'Return ``True/False`` depending was server stopped or not.')
        fut = asyncio.run_coroutine_threadsafe(self.rpc_proxy[path].request.get_keyword_documentation(name), self.rpc_loop)
        return fut.result()

    def get_keyword_tags(self, path, name):
        if path not in self.rpc_proxy:
            return None
        if name == 'stop_remote_server':
            return []
        fut = asyncio.run_coroutine_threadsafe(self.rpc_proxy[path].request.get_keyword_tags(name), self.rpc_loop)
        return fut.result()
