from typing import get_type_hints, NewType
from os.path import join as join_path
from os import environ as env
import json


JsonDict = NewType('JsonDict', dict)


class AppConfigError(Exception):
    pass


class AppConfig:
    BASE_DIR: str = ''
    DOWNLOAD_DIR: str = 'downloads'
    AUDIO_DOWNLOAD_DIR: str = '%%DOWNLOAD_DIR'
    DOWNLOAD_DIRS_INDEXABLE: bool = False
    CUSTOM_DIRS: bool = True
    CREATE_CUSTOM_DIRS: bool = True
    DELETE_FILE_ON_TRASHCAN: bool = True
    STATE_DIR: str = '.'
    URL_PREFIX: str = ''
    OUTPUT_TEMPLATE: str = '%(title)s.%(ext)s'
    OUTPUT_TEMPLATE_CHAPTER: str = '%(title)s - %(section_number)s %(section_title)s.%(ext)s'
    YTDL_OPTIONS: JsonDict = '{}'
    HOST: str = '0.0.0.0'
    PORT: int = 8081


    def __init__(self):
        for field in self.__annotations__:
            if not field.isupper():
                continue

            default_value = getattr(self, field, None)
            if default_value is None and env.get(field) is None:
                raise AppConfigError('Field "{}" is required'.format(field))
            
            self.parse_envvar(field, default_value)
        
        # parse referencial variables
        for field in self.__annotations__:
            value = getattr(self, field)
            if isinstance(value, str) and value.startswith('%%'):
                setattr(self, field, getattr(self, value[2:]))
        
        if not self.URL_PREFIX.endswith('/'):
            self.URL_PREFIX += '/'

    def parse_envvar(self, field: str, default_value):
        try:
            var_type = get_type_hints(AppConfig)[field]
            val = env.get(field, default_value)
            if var_type == bool:
                value = val if type(val) == bool else val.lower() in ['true', 'yes', 'on', '1']
            elif var_type == JsonDict:
                value = json.loads(val)
                assert isinstance(value, dict)
            else:
                value = var_type(env.get(field, default_value))

            self.__setattr__(field, value)
        except ValueError:
            raise AppConfigError('Unable to cast value "{}" to type "{}" for "{}" field'.format(
                env[field],
                var_type,
                field
            )
        )
    
    def basedir_path(self, path):
        return join_path(self.BASE_DIR, path)
    
    def statedir_path(self, path):
        return join_path(self.STATE_DIR, path)

    def urlpath(self, path):
        return join_path(self.URL_PREFIX, path)
    
    def __repr__(self):
        return str(self.__dict__)

Config = AppConfig()
