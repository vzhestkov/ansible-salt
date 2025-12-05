# Ansible to Salt integration

This is a PoC project made during [Hack Week 25](https://hackweek.opensuse.org/25/projects).

[Ansible to Salt integration](https://hackweek.opensuse.org/25/projects/ansible-to-salt-integration)

The projects consists of 2 Ansible plugins:
- [Inventory plugin](#inventory-plugin)
- [Connection plugin](#connection-plugin)

## Inventory plugin

Retrieves inventory data from the local salt-master, encompassing all accepted minions.
Additionally, it is capable of parsing configured nodegroups to establish the inventory grouping structure.

No configuration is required, the plugin utilizes the existing local salt-master config.

Name: `suse.network.salt`

## Connection plugin

This plugin leverages the `ZeroMQ` transport of the local `salt-master`
to communicate with managed hosts derived from the `suse.network.salt` inventory plugin.

No configuration is required, the plugin utilizes the existing local salt-master config.

Name: `suse.network.salt`

## Deployment

The plugins are not packaged yet, so the only way to install them now is to place the content of
[`ansible_collections`](ansible_collections/) to `/usr/lib/python3.13/site-packages/ansible_collections/`
on [`openSUSE Leap 16`](https://get.opensuse.org/leap/16.0/) system used with `salt-master` and `ansible` installed on it.

> [!IMPORTANT]
> PoC was tested on `openSUSE Leap 16` with the version of `salt` packages which was not yet released at the moment of testing (2025-12-01).
> Original `salt` packages from `openSUSE Leap 16` may not function the right way due to the missing fixes for `Python 3.13`.

## Configuration

Ansible requires just very siple configuration in [`/etc/ansible/ansible.cfg`](config-examples/etc/ansible/ansible.cfg)
just to make easier to use the plugins and avoid specifying them as extra parameters with each `ansible` call.

Example:
```
[defaults]
interpreter_python = auto_silent
inventory = @salt
transport = suse.network.salt

[inventory]
enable_plugins = suse.network.salt

[connection]
enable_plugins = suse.network.salt
```

Configuration of `salt-master` should be extended to use [Connection plugin](#connection-plugin):

Example of [`/etc/salt/master.d/ansible-connector.conf`](config-examples/etc/salt/master.d/ansible-connector.conf):
```
ansible_connector:
  file_root: /srv/salt
  temp_dir: .actmp
  compress: True
  chunk_size: 100000

# Setting `file_recv` to `True` could significantly improve the speed
# of getting the file from the remote clients, but could have security implication.
#file_recv: True
```

`ansible_connector` parameters description:
`file_root` is used for temporary files which should be pulled by the minions

`temp_dir` is the name of the directory used by `suse.network.salt` connection plugin
    to store the temporary files for the minions. The names of these files are random.
    The files are exposed only for short intervals of time, and deleted
    as soon asretrived by the targeted minion.
    The directory must have the permission allowing `salt` user to create files there.

`compress` is used to enforce using `gzip` compression on transferring the files.
    This parameter affects transferring files in both directions.
    It's recommended to set it to `True` in case if mostly text files are transferred.
    In case of getting large binary files with Ansible it's better to set `False`.

`chunk_size` (default: 100000) could be used to adjust the size of the chunk,
    which is used on transferring large files from the client to the server,
    but only in case of `file_recv` is set to `False` (default for salt-master).

Ansible groups can be populated using `nodegroups` specified in the `salt-master` config.

Example of [`/etc/salt/master.d/nodegroups.conf`](config-examples/etc/salt/master.d/nodegroups.conf):
```
nodegroups:
  suse: 'test-sl* test-lp*'
  alma: 'test-alma*'
  ubuntu: 'test-u*'
  outdated:
    - test-alma9.example.org
    - test-u2004.example.org
  fresh:
    - test-lp16.example.org
    - test-alma10.example.org
    - test-u2404.example.org
```

> [!IMPORTANT]
> Compount matcher is used inside the `nodegroups`.
> Some of the matchers could be very heavy to expand, especially the ones,
> which require getting data from the minion (Grains, Subnet/IP...)

## Usage

> [!NOTE]
> This is fully functional PoC, most of the features of Ansible should work
> For testing purposts `salt` or `root` users was used on the server with `salt-master` and `ansible` installed.

> [!IMPORTANT]
> PoC was tested on `openSUSE Leap 16` with the version of `salt` packages which was not yet released at the moment of testing (2025-12-01).
> Original `salt` packages from `openSUSE Leap 16` may not function the right way due to the missing fixes for `Python 3.13`.

This PoC can also make Ansible using Python interpreter from the Salt Bundle (venv-salt-minion) on the client side.

The minions should be onboarded to the `salt-master` and `salt-key` should return something like this:
```
Accepted Keys:
test-alma10.example.org
test-alma9.example.org
test-lp16.example.org
test-u2004.example.org
test-u2404.example.org
Denied Keys:
Unaccepted Keys:
test-deb13.example.org
test-sl16.example.org
Rejected Keys:
```

The example of calling `ansible-inventory --graph`:
```
@all:
  |--@ungrouped:
  |--@suse:
  |  |--test-lp16.example.org
  |--@alma:
  |  |--test-alma10.example.org
  |  |--test-alma9.example.org
  |--@ubuntu:
  |  |--test-u2004.example.org
  |  |--test-u2404.example.org
  |--@outdated:
  |  |--test-u2004.example.org
  |  |--test-alma9.example.org
  |--@fresh:
  |  |--test-alma10.example.org
  |  |--test-u2404.example.org
  |  |--test-lp16.example.org
```

The clients are assigned to the certain groups accoring to `nodegroups` specified in the `salt-master`'s config.

On accepting the keys of the minions listed in `Unaccepted Keys` section, we would get these minions populated to the inventory:
```
> salt-key -A
The following keys are going to be accepted:
Unaccepted Keys:
test-deb13.example.org
test-sl16.example.org
Proceed? [n/Y] y
Key for minion test-deb13.example.org accepted.
Key for minion test-sl16.example.org accepted.

> ansible-inventory --graph
@all:
  |--@ungrouped:
  |  |--test-deb13.example.org
  |--@suse:
  |  |--test-sl16.example.org
  |  |--test-lp16.example.org
  |--@alma:
  |  |--test-alma10.example.org
  |  |--test-alma9.example.org
  |--@ubuntu:
  |  |--test-u2004.example.org
  |  |--test-u2404.example.org
  |--@outdated:
  |  |--test-alma9.example.org
  |  |--test-u2004.example.org
  |--@fresh:
  |  |--test-lp16.example.org
  |  |--test-alma10.example.org
  |  |--test-u2404.example.org
```

Once the minions are onboarded they can be reached with `salt` and `ansible`
using the same transport of `salt-minion` to `salt-master` connection.

`salt` calls example:
```
> salt \* test.ping
test-sl16.example.org:
    True
test-alma9.example.org:
    True
test-deb13.example.org:
    True
test-u2004.example.org:
    True
test-alma10.example.org:
    True
test-lp16.example.org:
    True
test-u2404.example.org:
    True

> salt \* cmd.run 'uname -a'
test-u2004.example.org:
    Linux test-u2004.example.org 5.4.0-216-generic #236-Ubuntu SMP Fri Apr 11 19:53:21 UTC 2025 x86_64 x86_64 x86_64 GNU/Linux
test-sl16.example.org:
    Linux test-sl16.example.org 6.12.0-160000.6-default #1 SMP PREEMPT_DYNAMIC Fri Oct 17 10:54:40 UTC 2025 (724dacd) x86_64 x86_64 x86_64 GNU/Linux
test-alma9.example.org:
    Linux test-alma9.example.org 5.14.0-611.5.1.el9_7.x86_64 #1 SMP PREEMPT_DYNAMIC Tue Nov 11 08:09:09 EST 2025 x86_64 x86_64 x86_64 GNU/Linux
test-u2404.example.org:
    Linux test-u2404.example.org 6.8.0-88-generic #89-Ubuntu SMP PREEMPT_DYNAMIC Sat Oct 11 01:02:46 UTC 2025 x86_64 x86_64 x86_64 GNU/Linux
test-alma10.example.org:
    Linux test-alma10.example.org 6.12.0-124.8.1.el10_1.x86_64 #1 SMP PREEMPT_DYNAMIC Tue Nov 11 11:41:04 EST 2025 x86_64 GNU/Linux
test-deb13.example.org:
    Linux test-deb13.example.org 6.12.57+deb13-amd64 #1 SMP PREEMPT_DYNAMIC Debian 6.12.57-1 (2025-11-05) x86_64 GNU/Linux
test-lp16.example.org:
    Linux test-lp16.example.org 6.12.0-160000.5-default #1 SMP PREEMPT_DYNAMIC Wed Sep 10 15:26:25 UTC 2025 (3545bbd) x86_64 x86_64 x86_64 GNU/Linux
```

`ansible` call example:
```
> ansible -m ping all
test-deb13.example.org | SUCCESS => {
    "ansible_facts": {
        "discovered_interpreter_python": "/usr/lib/venv-salt-minion/bin/python"
    },
    "changed": false,
    "ping": "pong"
}
test-sl16.example.org | SUCCESS => {
    "ansible_facts": {
        "discovered_interpreter_python": "/usr/lib/venv-salt-minion/bin/python"
    },
    "changed": false,
    "ping": "pong"
}
test-alma9.example.org | SUCCESS => {
    "ansible_facts": {
        "discovered_interpreter_python": "/usr/lib/venv-salt-minion/bin/python"
    },
    "changed": false,
    "ping": "pong"
}
test-alma10.example.org | SUCCESS => {
    "ansible_facts": {
        "discovered_interpreter_python": "/usr/lib/venv-salt-minion/bin/python"
    },
    "changed": false,
    "ping": "pong"
}
test-u2004.example.org | SUCCESS => {
    "ansible_facts": {
        "discovered_interpreter_python": "/usr/lib/venv-salt-minion/bin/python"
    },
    "changed": false,
    "ping": "pong"
}
test-lp16.example.org | SUCCESS => {
    "ansible_facts": {
        "discovered_interpreter_python": "/usr/lib/venv-salt-minion/bin/python"
    },
    "changed": false,
    "ping": "pong"
}
test-u2404.example.org | SUCCESS => {
    "ansible_facts": {
        "discovered_interpreter_python": "/usr/lib/venv-salt-minion/bin/python"
    },
    "changed": false,
    "ping": "pong"
}

> ansible -m command -a 'uname -a' all
test-sl16.example.org | CHANGED | rc=0 >>
Linux test-sl16.example.org 6.12.0-160000.6-default #1 SMP PREEMPT_DYNAMIC Fri Oct 17 10:54:40 UTC 2025 (724dacd) x86_64 x86_64 x86_64 GNU/Linux
test-alma10.example.org | CHANGED | rc=0 >>
Linux test-alma10.example.org 6.12.0-124.8.1.el10_1.x86_64 #1 SMP PREEMPT_DYNAMIC Tue Nov 11 11:41:04 EST 2025 x86_64 GNU/Linux
test-deb13.example.org | CHANGED | rc=0 >>
Linux test-deb13.example.org 6.12.57+deb13-amd64 #1 SMP PREEMPT_DYNAMIC Debian 6.12.57-1 (2025-11-05) x86_64 GNU/Linux
test-alma9.example.org | CHANGED | rc=0 >>
Linux test-alma9.example.org 5.14.0-611.5.1.el9_7.x86_64 #1 SMP PREEMPT_DYNAMIC Tue Nov 11 08:09:09 EST 2025 x86_64 x86_64 x86_64 GNU/Linux
test-u2004.example.org | CHANGED | rc=0 >>
Linux test-u2004.example.org 5.4.0-216-generic #236-Ubuntu SMP Fri Apr 11 19:53:21 UTC 2025 x86_64 x86_64 x86_64 GNU/Linux
test-u2404.example.org | CHANGED | rc=0 >>
Linux test-u2404.example.org 6.8.0-88-generic #89-Ubuntu SMP PREEMPT_DYNAMIC Sat Oct 11 01:02:46 UTC 2025 x86_64 x86_64 x86_64 GNU/Linux
test-lp16.example.org | CHANGED | rc=0 >>
Linux test-lp16.example.org 6.12.0-160000.5-default #1 SMP PREEMPT_DYNAMIC Wed Sep 10 15:26:25 UTC 2025 (3545bbd) x86_64 x86_64 x86_64 GNU/Linux
```

It's also possible to run playbooks through the clients:
Example of the playbook `os_info_fresh.yml`:
```
---
- hosts: fresh
  become: no
  vars:
    output_file: fresh.csv
  tasks:
    - block:
        # For permisison setup.
        - name: get current user
          command: whoami
          register: whoami
          run_once: yes

        - name: clean file
          copy:
            dest: "{{ output_file }}"
            content: 'hostname,distribution,version,release'
            owner: "{{ whoami.stdout }}"
          run_once: yes

        - name: fill os information
          lineinfile:
            path: "{{ output_file }}"
            line: "{{ ansible_hostname }},\
              {{ ansible_distribution }},\
              {{ ansible_distribution_version }},\
              {{ ansible_distribution_release }}"
          # Tries to prevent concurrent writes.
          throttle: 1
      delegate_to: localhost
```

The example of output on running the playbook:
```
> ansible-playbook os_info_fresh.yml 

PLAY [fresh] *******************************************************************************************************

TASK [Gathering Facts] *********************************************************************************************
ok: [test-u2404.example.org]
ok: [test-alma10.example.org]
ok: [test-lp16.example.org]

TASK [get current user] ********************************************************************************************
changed: [test-alma10.example.org -> localhost]

TASK [clean file] **************************************************************************************************
changed: [test-alma10.example.org -> localhost]

TASK [fill os information] *****************************************************************************************
changed: [test-alma10.example.org -> localhost]
changed: [test-u2404.example.org -> localhost]
changed: [test-lp16.example.org -> localhost]

PLAY RECAP *********************************************************************************************************
test-alma10.example.org    : ok=4    changed=3    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
test-lp16.example.org      : ok=2    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
test-u2404.example.org     : ok=2    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

And the content of the resulting `fresh.csv`:
```
test-alma10,AlmaLinux,10.1,Heliotrope Lion
test-u2404,Ubuntu,24.04,noble
test-lp16,openSUSE Leap,16.0,0
```
