from download import Download, DownloadInfo, DownloadRequest, Notifier
from persistant_queue import PersistentQueue
from config import Config
import asyncio
import logging
import yt_dlp
import os


log = logging.getLogger('ytdl')


class DownloadQueue:
    def __init__(self, notifier: Notifier):
        self.notifier = notifier
        self.queue = PersistentQueue(Config.statedir_path('queue'))
        self.done = PersistentQueue(Config.statedir_path('completed'))

    async def initialize(self):
        self.event = asyncio.Event()
        asyncio.create_task(self.__download())

    def __extract_info(self, url):
        return yt_dlp.YoutubeDL(params={
            'quiet': True,
            'no_color': True,
            'extract_flat': True,
            **Config.YTDL_OPTIONS,
        }).extract_info(url, download=False)

    async def __add_playlist_entry(self, entry, dl_request: DownloadRequest, already: set):
        entries = entry['entries']
        log.info(f'playlist detected with {len(entries)} entries')
        playlist_index_digits = len(str(len(entries)))
        results = []
        for idx, etr in enumerate(entries, start=1):
            etr["playlist"] = entry["id"]
            etr["playlist_index"] = '{{0:0{0:d}d}}'.format(
                playlist_index_digits).format(idx)
            for property in ("id", "title", "uploader", "uploader_id"):
                if property in entry:
                    etr[f"playlist_{property}"] = entry[property]
            # TODO: loop await?
            results.append(await self.__add_entry(etr, dl_request, already))
        if any(res['status'] == 'error' for res in results):
            messages = (res['msg'] for res in results
                        if res['status'] == 'error' and 'msg' in res)
            raise Exception(*messages)

    def handle_custom_folder(self, base_dir: str, folder: str) -> str:
        if not Config.CUSTOM_DIRS:
            raise Exception(
                'A folder for the download was specified but CUSTOM_DIRS is not true in the configuration.')
        download_dir = os.path.realpath(os.path.join(base_dir, folder))
        real_base_dir = os.path.realpath(base_dir)
        if not download_dir.startswith(real_base_dir):
            raise Exception(
                f'Folder "{folder}" must resolve inside the base download directory "{real_base_dir}"')
        if not os.path.isdir(download_dir):
            if not Config.CREATE_CUSTOM_DIRS:
                raise Exception(
                    f'Folder "{folder}" for download does not exist inside base directory "{real_base_dir}", and CREATE_CUSTOM_DIRS is not true in the configuration.')
            os.makedirs(download_dir, exist_ok=True)
        return download_dir

    async def __add_video_entry(self, entry, dl_request: DownloadRequest):
        # Keep consistent with frontend
        if dl_request.is_audio:
            base_dir = Config.AUDIO_DOWNLOAD_DIR
        else:
            base_dir = Config.DOWNLOAD_DIR

        if dl_request.folder:
            download_dir = self.handle_custom_folder(base_dir, dl_request.folder)
        else:
            download_dir = base_dir

        id = dl_request.apply_prefix(entry['id'])
        title = dl_request.apply_prefix(entry['title'])
        url = entry.get('webpage_url') or entry['url']
        
        output = dl_request.apply_prefix(Config.OUTPUT_TEMPLATE)
        for property, value in entry.items():
            if property.startswith("playlist"):
                output = output.replace(f"%({property})s", str(value))
        output_chapter = Config.OUTPUT_TEMPLATE_CHAPTER

        dl_info = DownloadInfo(id, title, url, download_dir, output, output_chapter)
        dl = Download(dl_request, dl_info)
        self.queue.put(dl)
        self.event.set()
        await self.notifier.added(dl)

    async def __add_entry(self, entry, dl_request: DownloadRequest, already: set):
        etype = entry.get('_type') or 'video'
        if etype == 'playlist':
            self.__add_playlist_entry(entry, dl_request, already)
        elif etype == 'video' or etype.startswith('url') and 'id' in entry and 'title' in entry:
            if not self.queue.exists(entry['id']):
                await self.__add_video_entry(entry, dl_request)
        elif etype.startswith('url'):
            dl_request.url = entry['url']
            await self.add(dl_request, already)
        else:
            raise Exception(f'Unsupported resource "{etype}"')

    async def add(self, dl_request: DownloadRequest, already=None):
        log.info(f'adding {dl_request}')

        url = dl_request.url

        if already is None:
            already = set()
        elif url in already:
            log.info('recursion detected, skipping')
            return {'status': 'ok'}

        already.add(url)

        try:
            entry = await asyncio.get_running_loop().run_in_executor(None, self.__extract_info, url)
        except yt_dlp.utils.YoutubeDLError as exc:
            return {'status': 'error', 'msg': str(exc)}

        try:
            await self.__add_entry(entry, dl_request, already)
            return {'status': 'ok'}
        except Exception as e:
            return {'status': 'error', 'msg': '\n\n'.join(e.args)}

    async def cancel(self, ids):
        for id in ids:
            if not self.queue.exists(id):
                log.warn(f'requested cancel for non-existent download {id}')
                continue
            if self.queue.get(id).started():
                self.queue.get(id).cancel()
            else:
                self.queue.delete(id)
                await self.notifier.canceled(id)
        return {'status': 'ok'}

    async def clear(self, ids):
        for id in ids:
            if not self.done.exists(id):
                log.warn(f'requested delete for non-existent download {id}')
                continue
            if Config.DELETE_FILE_ON_TRASHCAN:
                dl = self.done.get(id)
                os.remove(os.path.join(dl.dl_info.download_dir, dl.dl_info.filename))
            self.done.delete(id)
            await self.notifier.cleared(id)
        return {'status': 'ok'}

    def get(self):
        return (
            [(k, v.dl_info) for k, v in self.queue.items()],
            [(k, v.dl_info) for k, v in self.done.items()]
        )

    async def __download(self):
        while True:
            while self.queue.empty():
                log.info('waiting for item to download')
                await self.event.wait()
                self.event.clear()
            id, entry = self.queue.next()
            log.info(f'downloading {entry.dl_info.title}')
            await entry.start(self.notifier)
            if entry.dl_info.status != 'finished':
                if entry.tmpfilename and os.path.isfile(entry.tmpfilename):
                    try:
                        os.remove(entry.tmpfilename)
                    except:
                        pass
                entry.dl_info.status = 'error'
            entry.close()
            if self.queue.exists(id):
                self.queue.delete(id)
                if entry.canceled:
                    await self.notifier.canceled(id)
                else:
                    self.done.put(entry)
                    await self.notifier.completed(entry.dl_info)
