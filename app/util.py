from glob import glob


def get_subdirs_recursive(path: str):
    return glob('**', root_dir=path, recursive=True)
