from dl_formats import get_format, get_opts, AUDIO_FORMATS
from serializers import JsonSerializer
from socketio import AsyncServer
from config import Config
import multiprocessing
import asyncio
import os.path
import yt_dlp
import time
import re


class DownloadRequest:
    def __init__(self,
                 url: str,
                 quality: str,
                 format: str,
                 folder: str,
                 custom_name_prefix: str):

        self.url = url
        self.quality = quality
        self.format = format
        self.folder = folder
        self.custom_name_prefix = custom_name_prefix
        # TODO: is this reliable?
        self.is_audio = quality == 'audio' or format in AUDIO_FORMATS

    def apply_prefix(self, s: str) -> str:
        if len(self.custom_name_prefix) > 0:
            return f'{self.custom_name_prefix}.{s}'
        return s
    
    def __str__(self):
        return str(vars(self))


class DownloadInfo:
    def __init__(self,
                 id: str,
                 title: str,
                 url: str, 
                 download_dir: str,
                 output_template: str,
                 output_template_chapter: str):
        self.id = id
        self.title = title
        self.url = url
        self.download_dir = download_dir
        self.output_template = output_template
        self.output_template_chapter = output_template_chapter
        self.filename = None
        self.status = None
        self.msg = None
        self.percent = None
        self.speed = None
        self.eta = None
        self.timestamp = time.time_ns()


class Download:
    manager = multiprocessing.Manager()

    def __init__(self, dl_request: DownloadRequest, dl_info: DownloadInfo):
        self.format = get_format(dl_request.format, dl_request.quality)
        self.ytdl_opts = get_opts(dl_request.format, dl_request.quality, Config.YTDL_OPTIONS)
        self.dl_request = dl_request
        self.dl_info = dl_info
        self.canceled = False
        self.tmpfilename = None
        self.proc = None
        self.loop = None
        self.notifier = None
        self.status_queue = Download.manager.Queue()

    def notify_progress(self):
        pass
    
    def _download(self):
        try:
            def put_status(st: dict):
                self.status_queue.put({k: v for k, v in st.items() if k in (
                    'tmpfilename',
                    'filename',
                    'status',
                    'msg',
                    'total_bytes',
                    'total_bytes_estimate',
                    'downloaded_bytes',
                    'speed',
                    'eta',
                )})

            def put_status_postprocessor(d):
                if d['postprocessor'] == 'MoveFiles' and d['status'] == 'finished':
                    if '__finaldir' in d['info_dict']:
                        filename = os.path.join(
                            d['info_dict']['__finaldir'], os.path.basename(d['info_dict']['filepath']))
                    else:
                        filename = d['info_dict']['filepath']
                    self.status_queue.put(
                        {'status': 'finished', 'filename': filename})
            ret = yt_dlp.YoutubeDL(params={
                'quiet': True,
                'no_color': True,
                # 'skip_download': True,
                'paths': {"home": self.dl_info.download_dir},
                'outtmpl': {"default": self.dl_info.output_template, "chapter": self.dl_info.output_template_chapter},
                'format': self.format,
                'socket_timeout': 30,
                'progress_hooks': [put_status],
                'postprocessor_hooks': [put_status_postprocessor],
                **self.ytdl_opts,
            }).download([self.dl_info.url])
            self.status_queue.put(
                {'status': 'finished' if ret == 0 else 'error'})
        except yt_dlp.utils.YoutubeDLError as exc:
            self.status_queue.put({'status': 'error', 'msg': str(exc)})

    async def start(self, notifier: 'Notifier'):
        self.proc = multiprocessing.Process(target=self._download)
        self.proc.start()
        self.loop = asyncio.get_running_loop()
        self.notifier = notifier
        self.dl_info.status = 'preparing'
        await self.notifier.updated(self.dl_info)
        asyncio.create_task(self.update_status())
        return await self.loop.run_in_executor(None, self.proc.join)

    def cancel(self):
        if self.running():
            self.proc.kill()
        self.canceled = True

    def close(self):
        if self.started():
            self.proc.close()
            self.status_queue.put(None)

    def running(self):
        try:
            return self.proc is not None and self.proc.is_alive()
        except ValueError:
            return False

    def started(self):
        return self.proc is not None

    async def update_status(self):
        while True:
            status = await self.loop.run_in_executor(None, self.status_queue.get)
            if status is None:
                return
            self.tmpfilename = status.get('tmpfilename')
            if 'filename' in status:
                self.dl_info.filename = os.path.relpath(
                    status.get('filename'), self.dl_info.download_dir)

                # Set correct file extension for thumbnails
                if self.dl_request.format == 'thumbnail':
                    self.dl_info.filename = re.sub(
                        r'\.webm$', '.jpg', self.dl_info.filename)
            self.dl_info.status = status['status']
            self.dl_info.msg = status.get('msg')
            if 'downloaded_bytes' in status:
                total = status.get('total_bytes') or status.get(
                    'total_bytes_estimate')
                if total:
                    self.dl_info.percent = round(
                        status['downloaded_bytes'] / total * 100)
            self.dl_info.speed = status.get('speed')
            self.dl_info.eta = status.get('eta')
            await self.notifier.updated(self.dl_info)

    def __str__(self):
        return str(vars(self))


class Notifier:
    def __init__(self, sio: AsyncServer, serializer: JsonSerializer):
        self.sio = sio
        self.serializer = serializer

    async def added(self, dl: Download):
        await self.sio.emit('added', self.serializer.encode(dl.dl_info))

    async def updated(self, dl_info: DownloadInfo):
        await self.sio.emit('updated', self.serializer.encode(dl_info))

    async def completed(self, dl_info: DownloadInfo):
        await self.sio.emit('completed', self.serializer.encode(dl_info))

    async def canceled(self, id: str):
        await self.sio.emit('canceled', self.serializer.encode(id))

    async def cleared(self, id: str):
        await self.sio.emit('cleared', self.serializer.encode(id))
