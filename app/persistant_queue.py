from collections import OrderedDict
from download import Download
import shelve
import os


class PersistentQueue:
    def __init__(self, path: str):
        self.path = path
        self.dict = OrderedDict()

        pdir = os.path.dirname(path)
        if not os.path.exists(pdir):
            os.makedirs(pdir, exist_ok=True)

        self.load_or_create()

    def load_or_create(self):
        try:
            with shelve.open(self.path, 'r') as shelf:
                items = sorted(shelf.items(), key=lambda it: it[1][1].timestamp)
            for k, (dl_request, dl_info) in items:
                self.dict[k] = Download(dl_request, dl_info)
        except:
            with shelve.open(self.path, 'c'):
                pass

    def exists(self, key: str) -> bool:
        return key in self.dict

    def get(self, key) -> Download:
        return self.dict[key]

    def items(self) -> list[tuple[str, Download]]:
        return list(self.dict.items())

    def put(self, value: Download):
        key = value.dl_info.url
        self.dict[key] = value
        with shelve.open(self.path, 'w') as shelf:
            shelf[key] = (value.dl_request, value.dl_info)

    def delete(self, key):
        del self.dict[key]
        with shelve.open(self.path, 'w') as shelf:
            shelf.pop(key)

    def next(self) -> tuple[str, Download]:
        k, v = next(iter(self.dict.items()))
        return k, v

    def empty(self):
        return not bool(self.dict)
