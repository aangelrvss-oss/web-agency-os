"""Network lock for the whole test package (AT1.4): any socket connection or DNS lookup raises and is counted."""
import socket

ATTEMPTS = []


class NetworkBlocked(RuntimeError):
    pass


def _blocked(name):
    def deny(*args, **kwargs):
        ATTEMPTS.append(name)
        raise NetworkBlocked(f"network access attempted during tests ({name})")
    return deny


socket.socket.connect = _blocked("connect")
socket.socket.connect_ex = _blocked("connect_ex")
socket.create_connection = _blocked("create_connection")
socket.getaddrinfo = _blocked("getaddrinfo")
socket.gethostbyname = _blocked("gethostbyname")
