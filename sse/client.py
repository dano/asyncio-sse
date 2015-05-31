# Based on the sseclient library by btubbs: http://bits.btubbs.com/sseclient
import re
import sys
import asyncio
import aiohttp
import warnings

__all__ = ['SSEClient', 'Event']

_PY35 = sys.version_info >= (3, 5)

class SSEClient(object):
    @classmethod
    @asyncio.coroutine
    def create(cls, url, last_id=None, retry=3000, 
                 encoding='utf-8', on_message=None, **kwargs):
        s = cls()
        s.url = url
        s.last_id = last_id
        s.retry = retry
        s.encoding = encoding
        s._connected = False
        s.on_message = on_message
        s.buf = ''

        # Any extra kwargs will be fed into the aiohttp.request call later.
        s.request_kwargs = kwargs

        if 'headers' not in s.request_kwargs:
            s.request_kwargs['headers'] = {}

        # The SSE spec requires making requests with Cache-Control: nocache
        s.request_kwargs['headers']['Cache-Control'] = 'no-cache'

        # The 'Accept' header is not required, but explicit > implicit
        s.request_kwargs['headers']['Accept'] = 'text/event-stream'

        yield from s.connect()

    @asyncio.coroutine
    def connect(self):
        if self.last_id:
            self.request_kwargs['headers']['Last-Event-ID'] = self.last_id
        self._resp = yield from aiohttp.request('get', self.url, 
                                                **self.request_kwargs)
        self._connected = True
        if self.on_message:
            asyncio.async(self._do_receive_loop())

    @asyncio.coroutine
    def _do_receive_loop(self):
        while self._connected:
            try:
                msg = yield from self.receive()
                if asyncio.iscoroutinefunction(self.on_message):
                    yield from self.on_message(msg)
                else:
                    self.on_message(msg)
            except aiohttp.errors.ServerDisconnectedError:
                if not self._connected:
                    pass
                else:
                    raise

    @asyncio.coroutine
    def receive(self):
        multibyte = False
        while '\n\n' not in self.buf:
            if not multibyte:
                # Only reset nextchar if we're not processing a
                # multibyte unicode character.
                nextchar = b''
            multibyte = False
            nextchar += yield from self._resp.content.read(1)
            if not nextchar:
                yield from asyncio.sleep(self.retry / 1000.0)
                yield from self.connect()
                # The SSE spec only supports resuming from a whole message, so
                # if we have half a message we should throw it out.
                head, sep, tail = self.buf.rpartition('\n\n')
                self.buf = head + sep
                continue
            try:
                nextchar = nextchar.decode(self.encoding)
            except UnicodeDecodeError:
                # We hit a multibyte unicode character. To handle it,
                # we'll pull the next byte, append it to nextchar,
                # and try again.
                multibyte = True
                continue
            self.buf += nextchar
        head, sep, tail = self.buf.partition('\n\n')
        self.buf = tail
        msg = Event.parse(head)

        # Set retry and id if provided by the event
        if msg.retry:
            self.retry = msg.retry
        if msg.id:
            self.last_id = msg.id

        return msg

    def close(self):
        if self._connected:
            self._resp.close()
            self._connected = False

    if _PY35:
        @asyncio.coroutine
        def __aenter__(self):
            yield from self.connect()
            return self

        @asyncio.coroutine
        def __aexit__(self, *args):
            self.close()

        @asyncio.coroutine
        def __aiter__(self):
            return self

        @asyncio.coroutine
        def __anext__(self):
            data = yield from self.receive()
            if data:
                return data
            else:
                raise StopAsyncIteration


class Event(object):
    sse_line_pattern = re.compile('(?P<name>[^:]*):?( ?(?P<value>.*))?')
    DEFAULT_MSG = "message" # The SSE spec defines this.

    def __init__(self, data='', event=DEFAULT_MSG, id=None, retry=None):
        self.data = data
        self.event = event
        self.id = id
        self.retry = retry

    def dump(self):
        lines = []
        if self.id:
            lines.append('id: {}'.format(self.id))

        # Only include an event line if it's not the default already.
        if self.event != Event.DEFAULT_MSG:
            lines.append('event: {}'.format(self.event))

        if self.retry:
            lines.append('retry: {}'.format(self.retry))

        lines.extend('data: {}'.format(d) for d in self.data.split('\n'))
        return '{}\n\n'.format('\n'.join(lines))

    @classmethod
    def parse(cls, raw):
        """
        Given a possibly-multiline string representing an SSE message, parse it
        and return a Event object.
        """
        msg = cls()
        for line in raw.split('\n'):
            m = cls.sse_line_pattern.match(line)
            if m is None:
                # Malformed line.  Discard but warn.
                warnings.warn('Invalid SSE line: "{}"'.format(line), 
                              SyntaxWarning)
                continue

            name = m.groupdict()['name']
            value = m.groupdict()['value']
            if name == '':
                # line began with a ":", so is a comment.  Ignore
                continue
            elif name == 'data':
                # If we already have some data, then join to it with a newline.
                # Else this is it.
                if msg.data:
                    msg.data = '{}\n{}'.format(msg.data, value)
                else:
                    msg.data = value
            elif name == 'event':
                msg.event = value
            elif name == 'id':
                msg.id = value
            elif name == 'retry':
                msg.retry = int(value)

        return msg

    def __str__(self):
        return """{{
 Event: {event}
 Data: {data}
 id: {id}
}}""".format(**self.__dict__)


