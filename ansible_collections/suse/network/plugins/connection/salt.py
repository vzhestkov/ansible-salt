# -*- coding: utf-8 -*-
# Copyright (c) 2025, Victor Zhestkov <vzhestkov@gmail.com>

DOCUMENTATION = """
    name: salt
    author:
      - Victor Zhestkov (@vzhestkov)
    short_description: Salt connection plugin
    description:
        - This plugin leverages the ZeroMQ transport of the local salt-master
          to communicate with managed hosts derived from the suse.network.salt inventory plugin.
          No configuration is required, the plugin utilizes the existing local salt-master config.
    requirements:
        - salt
"""

EXAMPLES = """
plugin: suse.network.salt
"""


import base64
import os
import tempfile

from ansible import errors
from ansible.plugins.connection import ConnectionBase
from shutil import copyfileobj, move as move_file

HAS_SALT = False
try:
    import salt.client
    import salt.config
    import salt.syspaths
    import salt.utils.gzip_util

    HAS_SALT = True
except ImportError:
    pass


class Connection(ConnectionBase):
    """
    Salt Minion Connection using connection established to Salt Master
    """

    has_pipelining = True
    transport = "suse.network.salt"

    def __init__(self, play_context, new_stdin, *args, **kwargs):
        if not HAS_SALT:
            raise errors.AnsibleError("Salt is not available")
        super(Connection, self).__init__(play_context, new_stdin, *args, **kwargs)
        salt_conf_path = os.path.join(salt.syspaths.CONFIG_DIR, "master")
        self.salt_opts = salt.config.client_config(salt_conf_path)
        self.salt_cache_dir = self.salt_opts["cachedir"]
        _connector_opts = self.salt_opts.get("ansible_connector", {})
        self.salt_file_root = _connector_opts.get(
            "file_root", self.salt_opts.get("file_roots", {}).get("base", [None])[0]
        )
        self.salt_temp_dir = _connector_opts.get("temp_dir", "")
        self.salt_compress_files = _connector_opts.get("compress", False)
        self.salt_pull_chunk_size = _connector_opts.get("chunk_size", 100000)
        self.salt_file_recv = self.salt_opts.get("file_recv", False)
        if self.salt_file_root is None:
            raise errors.AnsibleError(
                "Not possible to find `file_root` for ansible temp files in Salt config"
            )
        self.host = self._play_context.remote_addr

    def _connect(self):
        if not HAS_SALT:
            raise errors.AnsibleError("Salt is not available")

        self.salt_client = salt.client.LocalClient(mopts=self.salt_opts)
        self._connected = True
        return self

    def exec_command(self, cmd, in_data=None, sudoable=False):
        """
        Run a command on the minion
        """
        super(Connection, self).exec_command(cmd, in_data=in_data, sudoable=sudoable)

        self._display.vvv(f"  EXEC: {cmd} | {in_data}", host=self.host)

        kwarg = None
        if in_data is not None:
            kwarg = {"stdin": in_data}

        ret = self.salt_client.cmd(self.host, "cmd.run_all", [cmd], kwarg=kwarg)
        if self.host not in ret:
            raise errors.AnsibleError(
                f"Minion {self.host} didn't respond! Check if it's online"
            )

        ret = ret.get(self.host)

        self._display.vvv(f"RETURN: {ret}", host=self.host)

        if not isinstance(ret, dict) or (
            "retcode" not in ret and "stdout" not in ret and "stderr" not in ret
        ):
            raise errors.AnsibleError(
                f"Minion {self.host} didn't respond! Check if it's online"
            )

        return ret["retcode"], ret["stdout"], ret["stderr"]

    def _pull_file(self, src, dst):
        with open(src, "rb") as src_file, tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=".ansible-",
            suffix=".tmp",
            dir=os.path.join(self.salt_file_root, self.salt_temp_dir),
            delete_on_close=False,
            delete=True,
        ) as tmp_file:
            copyfileobj(src_file, tmp_file)
            tmp_file.flush()
            kwarg = None
            if self.salt_compress_files:
                kwarg = {"gzip": True}
                salt.utils.gzip_util.compress_file(tmp_file)
            else:
                tmp_file.close()
            salt_source_file = os.path.join(
                "salt://", self.salt_temp_dir, os.path.basename(tmp_file.name)
            )
            ret = self.salt_client.cmd(
                self.host,
                "cp.get_file",
                [
                    salt_source_file,
                    dst,
                ],
                kwarg=kwarg,
            )
            if ret.get(self.host) == dst:
                return True
            return False

    def put_file(self, in_path, out_path):
        """
        Transfer a file from local to minion
        """

        super(Connection, self).put_file(in_path, out_path)

        self._display.vvv(f"PUT_FILE: {in_path} TO {out_path}", host=self.host)
        self._pull_file(in_path, out_path)

    def fetch_file(self, in_path, out_path):
        """
        Fetch a file from minion to local
        """

        super(Connection, self).fetch_file(in_path, out_path)

        self._display.vvv(f"FETCH_FILE: {in_path} TO {out_path}", host=self.host)

        minion_cache_file_dir = os.path.join(
            self.salt_cache_dir, "minions", self.host, "files"
        )

        if not os.path.isdir(minion_cache_file_dir):
            os.makedirs(minion_cache_file_dir)

        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=".ansible-",
            suffix=".tmp",
            dir=minion_cache_file_dir,
            delete_on_close=False,
            delete=True,
        ) as tmp_file, open(out_path, "wb") as dst_file:
            tmp_file_name = os.path.basename(tmp_file.name)
            pull_file = not self.salt_file_recv
            if self.salt_file_recv:
                tmp_file.close()
                ret = self.salt_client.cmd(
                    self.host,
                    "cp.push",
                    [in_path],
                    kwarg={"upload_path": tmp_file_name},
                )
                self._display.vvv(f"FETCH_FILE: cp.push RETURN: {ret}", host=self.host)
                if ret.get(self.host) is True:
                    tmp_file = open(os.path.realpath(tmp_file.name), "rb")
                    copyfileobj(tmp_file, dst_file)
                    tmp_file.close()
                else:
                    pull_file = True
            if pull_file:
                ret = self.salt_client.cmd(
                    self.host, "hashutil.base64_encodefile", [in_path]
                )
                ret = ret.get(self.host)
                if ret.startswith("VALUE_TRIMMED"):
                    ret = self.salt_client.cmd(self.host, "file.stats", [in_path])
                    file_stats = ret.get(self.host)
                    self._display.vvv(
                        f"FETCH_FILE: file.stats RETURN: {file_stats}", host=self.host
                    )
                    self._fetch_chunked(
                        file_stats["target"], file_stats["size"], dst_file, tmp_file
                    )
                else:
                    self._display.vvv(
                        f"FETCH_FILE: hashutil.base64_encodefile RETURN SIZE: {len(ret)}",
                        host=self.host,
                    )
                    try:
                        dst_file.write(base64.b64decode(ret))
                    except Exception as exc:  # pylint: disable=broad-except
                        self._display.vvv(
                            f"FETCH_FILE: hashutil.base64_encodefile EXCEPTION: {exc}",
                            host=self.host,
                        )
                        raise errors.AnsibleError(
                            f"Exception while getting file '{in_path}' from {self.host}: {exc}"
                        )

    def _fetch_chunked(self, src_file_path, file_size, dst_file, tmp_file):
        self._display.vvv(
            f"FETCH_CHUNKED: {src_file_path} size: {file_size}", host=self.host
        )
        ret = self.salt_client.cmd(
            self.host, "temp.file", [], kwarg={"prefix": ".ansible-", "suffix": ".tmp"}
        )
        remote_temp_file = ret.get(self.host)
        self._display.vvv(f"FETCH_CHUNKED: temp.file RETURN: {ret}", host=self.host)
        ret = self.salt_client.cmd(
            self.host,
            "cmd.run_all",
            [
                (
                    f"gzip -c -k {src_file_path} | base64 - > {remote_temp_file}"
                    if self.salt_compress_files
                    else f"base64 {src_file_path} > {remote_temp_file}"
                )
            ],
        )
        ret = ret.get(self.host)
        self._display.vvv(
            f"FETCH_CHUNKED: ({'compress & ' if self.salt_compress_files else ''}base64) RETURN: {ret}",
            host=self.host,
        )
        ret = self.salt_client.cmd(self.host, "file.stats", [remote_temp_file])
        temp_file_stats = ret.get(self.host)
        self._display.vvv(
            f"FETCH_CHUNKED: file.stats RETURN: {temp_file_stats}", host=self.host
        )
        temp_file_size = temp_file_stats["size"]
        fetched = 0
        idx = 0
        while fetched < temp_file_size:
            to_request = (
                self.salt_pull_chunk_size
                if (temp_file_size - fetched) > self.salt_pull_chunk_size
                else temp_file_size - fetched
            )
            ret = self.salt_client.cmd(
                self.host,
                "cmd.run_all",
                [
                    f"dd status=none if={remote_temp_file} count=1 "
                    f"bs={self.salt_pull_chunk_size} skip={idx}"
                ],
            )
            content = ret.get(self.host).get("stdout")
            tmp_file.write(content.encode("utf-8"))
            idx += 1
            fetched += to_request
        tmp_file.flush()
        tmp_file.close()
        local_tmp_file_name = os.path.realpath(tmp_file.name)
        self._display.vvv(
            f"FETCH_CHUNKED: TMP FILE RECEIVED: {local_tmp_file_name}", host=self.host
        )
        tmp_file = open(local_tmp_file_name, "rb")
        base64.decode(tmp_file, dst_file)
        dst_file.flush()
        if self.salt_compress_files:
            real_dst_file_path = os.path.realpath(dst_file.name)
            dst_file.close()
            tmp_file.close()
            dst_file = salt.utils.gzip_util.open(real_dst_file_path)
            tmp_file = open(local_tmp_file_name, "wb")
            copyfileobj(dst_file, tmp_file)
            tmp_file.flush()
            tmp_file.close()
            move_file(local_tmp_file_name, real_dst_file_path)

    def close(self):
        """
        Terminate the connection
        """
        self._connected = False
        self.salt_client.destroy()
        self.salt_client = None
        self.salt_opts = None
