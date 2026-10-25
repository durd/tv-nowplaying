#!/usr/bin/env python3
"""ADB over TCP to the TV, without the adb binary.

Usage:
    tv.py <shell command>      run one shell command, print its output
    tv.py --install <apk>      push the APK and install it (pm install -r)
    tv.py --find               list the Philips TVs found on the network

The TV is TV_HOST (host or host:port, ADB port 5555 by default), else tv.host in local.properties, else
the Philips TV found over mDNS (_philipstv_s_rpc._tcp, the service the Philips TV integration uses too).

Uses this project's own key, tools/adbkey/adbkey (made on first use, gitignored). The first connection
makes the TV ask "Allow USB debugging?"; choose "Always allow".
"""
import base64
import hashlib
import os
import sys
import time

from adb_shell.adb_device import AdbDeviceTcp
from adb_shell.auth.keygen import keygen
from adb_shell.auth.sign_pythonrsa import PythonRSASigner

KEYDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adbkey")
KEY = os.path.join(KEYDIR, "adbkey")
PROPERTIES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "local.properties")
PHILIPS = "_philipstv_s_rpc._tcp.local."
REMOTE_APK = "/data/local/tmp/nowplaying.apk"
# Raw bytes per shell command. Pushing over shell commands, not ADB sync: some TV adbd builds
# corrupt larger sync transfers, and the md5 check below catches a bad copy either way.
CHUNK = 48 * 1024


def signer():
    os.makedirs(KEYDIR, mode=0o700, exist_ok=True)
    if not os.path.exists(KEY):
        keygen(KEY)
    # An ADB credential: anyone who can read it gets a shell on the TV. keygen leaves it world-readable.
    os.chmod(KEY, 0o600)
    with open(KEY) as f:
        priv = f.read()
    with open(KEY + ".pub") as f:
        pub = f.read()
    return PythonRSASigner(pub, priv)


def find_tvs(wait=3.0):
    """(name, IPv4 address) of each Philips TV answering on mDNS."""
    from zeroconf import IPVersion, ServiceBrowser, Zeroconf

    names = []

    class Listener:
        def add_service(self, zc, type_, name):
            names.append(name)

        def update_service(self, zc, type_, name):
            pass

        def remove_service(self, zc, type_, name):
            pass

    zc = Zeroconf()
    try:
        ServiceBrowser(zc, PHILIPS, Listener())
        time.sleep(wait)
        found = []
        for name in names:
            info = zc.get_service_info(PHILIPS, name, timeout=3000)
            addresses = info.parsed_addresses(IPVersion.V4Only) if info else []
            if addresses:
                found.append((name.removesuffix("." + PHILIPS), addresses[0]))
        return found
    finally:
        zc.close()


def target():
    if os.environ.get("TV_HOST"):
        return os.environ["TV_HOST"]
    if os.path.exists(PROPERTIES):
        with open(PROPERTIES) as f:
            for line in f:
                if line.startswith("tv.host="):
                    return line.split("=", 1)[1].strip()
    tvs = find_tvs()
    if len(tvs) != 1:
        sys.exit(f"found {len(tvs)} Philips TVs over mDNS; set TV_HOST or tv.host in local.properties")
    return tvs[0][1]


def connect():
    host, _, port = target().partition(":")
    dev = AdbDeviceTcp(host, int(port or 5555), default_transport_timeout_s=60.0)
    # Long auth timeout: the first connection waits for someone to accept the prompt on the TV.
    dev.connect(rsa_keys=[signer()], auth_timeout_s=90.0)
    return dev


def install(dev, apk):
    with open(apk, "rb") as f:
        data = f.read()
    tmp = REMOTE_APK + ".b64"
    dev.shell(f"rm -f {tmp} {REMOTE_APK}")
    for i in range(0, len(data), CHUNK):
        dev.shell(f"echo -n {base64.b64encode(data[i:i + CHUNK]).decode()} >> {tmp}")
    remote_md5 = dev.shell(f"base64 -d {tmp} > {REMOTE_APK} && rm -f {tmp} && md5sum {REMOTE_APK}").split()[:1]
    if remote_md5 != [hashlib.md5(data).hexdigest()]:
        dev.shell(f"rm -f {tmp} {REMOTE_APK}")
        sys.exit("APK copy on the TV does not match; nothing installed")
    out = dev.shell(f"pm install -r {REMOTE_APK}; rm -f {REMOTE_APK}")
    print(out.strip())
    if "Success" not in out:
        sys.exit(1)


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        sys.exit(__doc__)
    if args == ["--find"]:
        for name, address in find_tvs():
            print(f"{address}  {name}")
        return
    dev = connect()
    try:
        if args[0] == "--install" and len(args) == 2:
            install(dev, args[1])
        else:
            print(dev.shell(" ".join(args), read_timeout_s=120.0), end="")
    finally:
        dev.close()


if __name__ == "__main__":
    main()
