"""Public installation data, kept separate from supplier secrets and manual overrides."""
from decimal import Decimal, InvalidOperation
import re

COORDINATE_TYPES = {'WGS84', 'GCJ02', 'BD09'}


def coordinate_type(value):
    if not isinstance(value, str):
        return ''
    value = value.upper().replace('-', '').replace('_', '').replace(' ', '')
    return value if value in COORDINATE_TYPES else ''


def coordinate_pair(latitude, longitude):
    values = []
    for raw, limit in ((latitude, 90), (longitude, 180)):
        if isinstance(raw, bool) or not isinstance(raw, (str, int, float)) or len(str(raw)) > 40:
            raise ValueError('invalid-coordinate')
        if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', str(raw).strip(), flags=re.ASCII):
            raise ValueError('invalid-coordinate')
        try:
            value = Decimal(str(raw))
            if not value.is_finite() or not -limit <= value <= limit:
                raise ValueError('invalid-coordinate')
        except InvalidOperation:
            raise ValueError('invalid-coordinate') from None
        values.append(str(raw).strip())
    return {'latitude': values[0], 'longitude': values[1]}


def device_coordinates(device):
    profile = device.provider_profile
    if profile.get('coordinate_error'):
        return None
    raw = profile.get('coordinates', {})
    try:
        pair = coordinate_pair(raw.get('latitude'), raw.get('longitude'))
    except (ValueError, AttributeError):
        return None
    supplied = raw.get('coordinate_type', '')
    confirmed = device.supplier_coordinate_type
    # An explicit supplier type must never be overwritten by a local assumption.
    if supplied and (not coordinate_type(supplied) or confirmed and supplied != confirmed):
        return None
    kind = supplied or confirmed
    # Public coordinate contracts are WGS84 only. Other source types stay in the
    # admin snapshot until a separately verified normalization path exists.
    if kind != 'WGS84':
        return None
    return {**pair, 'coordinate_type': kind,
            'observed_at': raw.get('observed_at'),
            'source': 'supplier' if supplied else 'device_configuration'}


def display_identity(device):
    profile = device.provider_profile
    name = (profile.get('device_name') or profile.get('device_num') or device.name) if device.name_source == 'supplier' else device.name
    address = profile.get('address', '') if device.location_source == 'supplier' else device.location_note
    return {'name': name, 'location': ' · '.join(v for v in (address, device.installation_note) if v),
            'coordinates': device_coordinates(device)}
