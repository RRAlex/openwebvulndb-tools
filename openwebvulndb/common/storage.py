import re
from json.decoder import JSONDecodeError
from os.path import join, dirname
from os import makedirs, scandir, walk
from contextlib import contextmanager

from .schemas import MetaSchema, VulnerabilityListSchema, VersionListSchema
from .serialize import serialize
from .config import DEFAULT_PATH
from .logs import logger


class Storage:

    def __init__(self, base_path=DEFAULT_PATH):
        self.base_path = base_path
        self.known = set()

    def write_meta(self, meta):
        self._write(MetaSchema(), meta, 'META.json')

    def read_meta(self, key):
        return self._read(MetaSchema(), key, 'META.json')

    def list_meta(self, *args):
        for key, path, dirs, files in self.walk(*args):
            if "META.json" in files:
                yield self.read_meta(key)

    def write_vulnerabilities(self, vlist):
        self._write(VulnerabilityListSchema(), vlist, 'vuln-%s.json' % vlist.producer.lower())

    def read_vulnerabilities(self, key, producer):
        return self._read(VulnerabilityListSchema(), key, 'vuln-%s.json' % producer.lower())

    def list_vulnerabilities(self, key):
        name_format = re.compile(r'^vuln-(\w+)\.json$')

        for entry in scandir(self._path(key)):
            parts = name_format.match(entry.name)
            if parts and not entry.is_dir():
                yield self.read_vulnerabilities(key, parts.group(1))

    def write_versions(self, vlist):
        self._write(VersionListSchema(), vlist, "versions.json")

    def read_versions(self, key):
        return self._read(VersionListSchema(), key, 'versions.json')

    def list_directories(self, path):
        try:
            return {entry.name for entry in scandir(self._path(path)) if entry.is_dir()}
        except FileNotFoundError:
            return set()

    def append(self, relative, content):
        path = dirname(relative)
        self._prepare_path(path)
        with self._open('a+', relative) as fp:
            fp.write(content.strip("\n") + "\n")

    def read_lines(self, relative):
        try:
            with self._open('r', relative) as fp:
                for line in fp.readlines():
                    yield line.strip("\n")
        except FileNotFoundError:
            pass

    def walk(self, *args):
        base_len = len(self.base_path)

        for path, dirs, files in walk(self._path(*args)):
            key = path[base_len + 1:]
            yield key, path, dirs, files

    def _write(self, schema, item, *args):
        data, errors = serialize(schema, item)
        self._prepare_path(item.key)
        with self._open('w', item.key, *args) as fp:
            fp.write(data)

    def _read(self, schema, *args):
        try:
            with self._open('r', *args) as fp:
                data, errors = schema.loads(fp.read())
                if errors:
                    raise Exception(*args, errors)
                return data
        except JSONDecodeError:
            logger.critical("JSON Decode error in %s", args)

    @contextmanager
    def _open(self, mode, *args):
        with open(self._path(*args), mode) as fp:
            yield fp

    def _prepare_path(self, relative):
        if relative not in self.known:
            makedirs(self._path(relative), mode=0o755, exist_ok=True)
            self.known.add(relative)

    def _path(self, *args):
        return join(self.base_path, *args)
