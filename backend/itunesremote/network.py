"""Discover interface addresses without sending packets or resolving external names."""

from __future__ import annotations

import fcntl
import ipaddress
import socket
import struct
import sys


def lan_addresses() -> list[str]:
    # SIOCGIFADDR uses the BSD ifreq layout on macOS and the Linux layout elsewhere.
    request = 0xC0206921 if sys.platform == "darwin" else 0x8915
    addresses = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            for _, name in socket.if_nameindex():
                try:
                    result = fcntl.ioctl(probe.fileno(), request, struct.pack("256s", name.encode()[:15]))
                except OSError:
                    # Interfaces without an IPv4 address are normal, including disconnected Wi-Fi.
                    continue
                address = ipaddress.IPv4Address(result[20:24])
                if (
                    address.is_private
                    and not address.is_loopback
                    and not address.is_unspecified
                    and not address.is_reserved
                ):
                    addresses.add(address)
    except OSError:
        # Local access must remain available when interface discovery is unavailable.
        return []
    return [str(address) for address in sorted(addresses)]
