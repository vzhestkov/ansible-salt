# -*- coding: utf-8 -*-
# Copyright (c) 2025, Victor Zhestkov <vzhestkov@gmail.com>

DOCUMENTATION = """
    name: salt
    author:
      - Victor Zhestkov (@vzhestkov)
    short_description: Salt inventory plugin
    description:
        - Retrieves inventory data from the local salt-master, encompassing all accepted minions.
          Additionally, it is capable of parsing configured nodegroups to establish the inventory grouping structure.
          No configuration is required, the plugin utilizes the existing local salt-master config.
    requirements:
        - salt
"""

EXAMPLES = """
plugin: suse.network.salt
"""


import os

import salt.config
import salt.syspaths

from ansible.plugins.inventory import BaseInventoryPlugin


class InventoryModule(BaseInventoryPlugin):

    NAME = "suse.network.salt"

    def verify_file(self, path):
        return path.endswith("@salt")

    def parse(self, inventory, loader, path, cache=True):

        # call base method to ensure properties are available for use with other helper methods
        super(InventoryModule, self).parse(inventory, loader, path, cache)

        self.inventory.set_variable(
            "all",
            "ansible_interpreter_python_fallback",
            ["/usr/lib/venv-salt-minion/bin/python", "/usr/bin/python3"],
        )

        client_conf_path = os.path.join(salt.syspaths.CONFIG_DIR, "master")
        opts = salt.config.client_config(client_conf_path)

        nodegroups = opts.get("nodegroups", {}).copy()
        nodegroups[None] = None

        ck_minions = salt.utils.minions.CkMinions(opts)

        for nodegroup, nodegroup_rules in nodegroups.items():
            if nodegroup is not None:
                self.inventory.add_group(nodegroup)
                tgts = salt.utils.minions.nodegroup_comp(nodegroup, nodegroups)
            else:
                tgts = ["*"]
            for tgt in tgts:
                minions = ck_minions.check_minions(tgt, "compound").get("minions", [])
                for minion in minions:
                    self.inventory.add_host(minion, group=nodegroup)
