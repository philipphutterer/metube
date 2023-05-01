#!/usr/bin/env python3
# pylint: disable=no-member,method-hidden

from download import DownloadRequest, Notifier
from util import get_subdirs_recursive
from serializers import JsonSerializer
from ytdl import DownloadQueue
from config import Config
from aiohttp import web
import socketio
import logging


log = logging.getLogger('main')

serializer = JsonSerializer()

app = web.Application()
sio = socketio.AsyncServer(cors_allowed_origins='*')
sio.attach(app, socketio_path=Config.urlpath('socket.io'))
routes = web.RouteTableDef()


dqueue = DownloadQueue(Notifier(sio, serializer))
app.on_startup.append(lambda app: dqueue.initialize())

@routes.post(Config.urlpath('add'))
async def add(request):
    post = await request.json()
    url = post.get('url')
    quality = post.get('quality')
    if not url or not quality:
        raise web.HTTPBadRequest()
    format = post.get('format')
    folder = post.get('folder')
    custom_name_prefix = post.get('customNamePrefix')
    if custom_name_prefix is None:
        custom_name_prefix = ''
    status = await dqueue.add(DownloadRequest(url, quality, format, folder, custom_name_prefix))
    return web.Response(text=serializer.encode(status))

@routes.post(Config.urlpath('delete'))
async def delete(request):
    post = await request.json()
    ids = post.get('ids')
    where = post.get('where')
    if not ids or where not in ['queue', 'done']:
        raise web.HTTPBadRequest()
    status = await (dqueue.cancel(ids) if where == 'queue' else dqueue.clear(ids))
    return web.Response(text=serializer.encode(status))

@sio.event
async def connect(sid, environ):
    await sio.emit('all', serializer.encode(dqueue.get()), to=sid)
    await sio.emit('configuration', serializer.encode(Config), to=sid)
    if Config.CUSTOM_DIRS:
        download_dir = get_subdirs_recursive(Config.DOWNLOAD_DIR)
        audio_download_dir = get_subdirs_recursive(Config.AUDIO_DOWNLOAD_DIR)
        custom_dirs = dict(download_dir=download_dir, audio_download_dir=audio_download_dir)
        await sio.emit('custom_dirs', serializer.encode(custom_dirs), to=sid)

@routes.get(Config.URL_PREFIX)
def index(request):
    return web.FileResponse(Config.basedir_path('ui/dist/metube/index.html'))

if Config.URL_PREFIX != '/':
    @routes.get('/')
    def index_redirect_root(request):
        return web.HTTPFound(Config.URL_PREFIX)

    @routes.get(Config.URL_PREFIX[:-1])
    def index_redirect_dir(request):
        return web.HTTPFound(Config.URL_PREFIX)

routes.static(Config.urlpath('favicon/'), Config.basedir_path('favicon'))
routes.static(Config.urlpath('download/'), Config.DOWNLOAD_DIR, show_index=Config.DOWNLOAD_DIRS_INDEXABLE)
routes.static(Config.urlpath('audio_download/'), Config.AUDIO_DOWNLOAD_DIR, show_index=Config.DOWNLOAD_DIRS_INDEXABLE)
routes.static(Config.URL_PREFIX, Config.basedir_path('ui/dist/metube'))
try:
    app.add_routes(routes)
except ValueError as e:
    if 'ui/dist/metube' in str(e):
        raise RuntimeError('Could not find the frontend UI static assets. Please run `node_modules/.bin/ng build` inside the ui folder') from e
    raise e

@routes.options(Config.urlpath('add'))
async def add_cors(request):
    return web.Response(text=serializer.encode({"status": "ok"}))


async def on_prepare(request, response):
    if 'Origin' in request.headers:
        response.headers['Access-Control-Allow-Origin'] = request.headers['Origin']
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'

app.on_response_prepare.append(on_prepare)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    web.run_app(app, host=Config.HOST, port=Config.PORT, reuse_port=True)
