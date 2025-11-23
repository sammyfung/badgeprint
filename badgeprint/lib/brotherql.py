import socket
import ipaddress
import concurrent.futures
import netifaces
from typing import Dict, Tuple
import re

class BrotherQLPrinter:
    DEFAULT_PORT = 9100

    def get_local_subnet(self) -> str:
        """Get the local subnet based on the default network interface."""
        interfaces = netifaces.interfaces()
        for interface in interfaces:
            #if interface == 'lo':  # Skip loopback
            if not re.search('en0', interface):
                continue
            addrs = netifaces.ifaddresses(interface)
            if netifaces.AF_INET in addrs:
                for addr in addrs[netifaces.AF_INET]:
                    ip = addr['addr']
                    mask = addr['netmask']
                    network = ipaddress.IPv4Network(f"{ip}/{mask}", strict=False)
                    return str(network)
        return "192.168.1.0/24"  # Fallback subnet

    def scan_port(self, ip: str, port: int = DEFAULT_PORT, timeout: float = 1.0) -> Tuple[str, str]:
        """Scan a single IP for the specified port and return its status."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                result = sock.connect_ex((ip, port))
                return ip, "open" if result == 0 else "closed"
        except socket.error:
            return ip, "closed"

    def scan_printers(self) -> Dict[str, str]:
        """Scan port 9100 on all IPs in the local subnet."""
        subnet = self.get_local_subnet()
        network = ipaddress.IPv4Network(subnet, strict=False)
        results = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            future_to_ip = {executor.submit(self.scan_port, str(ip)): ip for ip in network}
            for future in concurrent.futures.as_completed(future_to_ip):
                ip, status = future.result()
                if status == 'open':
                    results.append(f"tcp://{ip}:{self.DEFAULT_PORT}")

        return results

