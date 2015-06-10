SSE
===

Simple asyncio/aiohttp wrapper for Server-Sent Events.

Usage
-----

Sending events:

```python
import asyncio
import sse


class Handler(sse.Handler):
    @asyncio.coroutine
    def handle_request(self):
        yield from asyncio.sleep(2)
        self.send('foo')
        yield from asyncio.sleep(2)
        self.send('bar', event='wakeup')

start_server = sse.serve(Handler, 'localhost', 8888)
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
```

Validating incoming requests:

```python
class Handler(sse.Handler):
    def validate_sse(self):
        super().validate_sse()
        # use self.request / self.payload
        if not self.request.path.startswith('/live'):
            raise sse.SseException()
```

Sending JSON data:

```python
class Handler(sse.Handler):
    @asyncio.coroutine
    def handle_request(self):
        self.send({'foo': 'bar'})
```

Sending IDs / event names / retry information:

```python
class Handler(sse.Handler):
    @asyncio.coroutine
    def handle_request(self):
        self.send('some data', id=12345, event='something', retry=10000)
```

SSE Client:
```python
@asyncio.coroutine
def connect_to_sse_server(server_url):
    client = yield from SSEClient.create(server_url)
    while True:
        event = yield from client.receive()
        print(event)
        print(event.event)
        print(event.data)
    client.close()

@asyncio.coroutine
def connect_to_sse_server_cb(server_url):
    def cb(event):
        print(event)
        print(event.event)
        print(event.data)
    client = yield from SSEClient.create(server_url, on_message=cb)

async def connect_to_sse_server_py35(server_url):
    """ This one only works on Python 3.5+ """
    client = await SSEClient.create(server_url)
    async for event in client:
        print(event)
        print(event.event)
        print(event.data)
```
