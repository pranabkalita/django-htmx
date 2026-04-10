from ipaddress import ip_address

from django.conf import settings


def _parse_ip(value):
    try:
        return str(ip_address((value or '').strip()))
    except ValueError:
        return None


def get_client_ip(request):
    remote_addr = _parse_ip(request.META.get('REMOTE_ADDR'))
    if not remote_addr:
        return None

    trusted_proxies = set(getattr(settings, 'TRUSTED_PROXY_IPS', []))
    if remote_addr not in trusted_proxies:
        return remote_addr

    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if not forwarded_for:
        return remote_addr

    first_hop = forwarded_for.split(',')[0].strip()
    return _parse_ip(first_hop) or remote_addr