"""
Custom Trip Modifications parser for GTFS-RT experimental extension.

The TripModifications message is an experimental GTFS-RT extension that isn't
included in the standard google.transit.gtfs_realtime_pb2. This module provides
a manual parser for the extension format.

Based on: https://github.com/google/transit/blob/master/gtfs-realtime/spec/en/trip-modifications.md
"""

from typing import Any
import struct


def decode_varint(data: bytes, pos: int) -> tuple[int, int]:
    """Decode a varint from bytes starting at pos, return (value, new_pos)"""
    result = 0
    shift = 0
    while True:
        if pos >= len(data):
            raise ValueError("Unexpected end of data while decoding varint")
        b = data[pos]
        result |= (b & 0x7F) << shift
        pos += 1
        if not (b & 0x80):
            break
        shift += 7
    return result, pos


def decode_string(data: bytes, pos: int) -> tuple[str, int]:
    """Decode a length-delimited string from bytes, return (string, new_pos)"""
    length, pos = decode_varint(data, pos)
    end = pos + length
    if end > len(data):
        raise ValueError("String extends beyond data")
    return data[pos:end].decode('utf-8', errors='replace'), end


def decode_bytes(data: bytes, pos: int) -> tuple[bytes, int]:
    """Decode a length-delimited bytes field, return (bytes, new_pos)"""
    length, pos = decode_varint(data, pos)
    end = pos + length
    if end > len(data):
        raise ValueError("Bytes field extends beyond data")
    return data[pos:end], end


def parse_field(data: bytes, pos: int) -> tuple[int, int, Any, int]:
    """Parse a single protobuf field, return (field_num, wire_type, value, new_pos)"""
    if pos >= len(data):
        return None, None, None, pos

    tag, pos = decode_varint(data, pos)
    field_num = tag >> 3
    wire_type = tag & 0x07

    if wire_type == 0:  # Varint
        value, pos = decode_varint(data, pos)
    elif wire_type == 1:  # 64-bit
        value = struct.unpack('<Q', data[pos:pos+8])[0]
        pos += 8
    elif wire_type == 2:  # Length-delimited
        length, pos = decode_varint(data, pos)
        value = data[pos:pos+length]
        pos += length
    elif wire_type == 5:  # 32-bit
        value = struct.unpack('<I', data[pos:pos+4])[0]
        pos += 4
    else:
        raise ValueError(f"Unknown wire type: {wire_type}")

    return field_num, wire_type, value, pos


def parse_message(data: bytes) -> dict[int, list[Any]]:
    """Parse all fields from a protobuf message into a dict"""
    fields = {}
    pos = 0
    while pos < len(data):
        field_num, wire_type, value, pos = parse_field(data, pos)
        if field_num is None:
            break
        if field_num not in fields:
            fields[field_num] = []
        fields[field_num].append((wire_type, value))
    return fields


def parse_selected_trips(data: bytes) -> dict[str, Any]:
    """
    Parse SelectedTrips message:
    - field 1: trip_ids (repeated string)
    - field 2: shape_id (optional string)
    """
    fields = parse_message(data)
    result = {'trip_ids': [], 'shape_id': None}

    # Field 1: trip_ids (repeated)
    if 1 in fields:
        for wire_type, value in fields[1]:
            if wire_type == 2:  # Length-delimited (string)
                result['trip_ids'].append(value.decode('utf-8', errors='replace'))

    # Field 2: shape_id
    if 2 in fields:
        wire_type, value = fields[2][0]
        if wire_type == 2:
            result['shape_id'] = value.decode('utf-8', errors='replace')

    return result


def parse_stop_selector(data: bytes) -> dict[str, Any]:
    """
    Parse StopSelector message:
    - field 1: stop_sequence (uint32)
    - field 2: stop_id (string)
    """
    fields = parse_message(data)
    result = {'stop_sequence': None, 'stop_id': None}

    if 1 in fields:
        wire_type, value = fields[1][0]
        if wire_type == 0:
            result['stop_sequence'] = value

    if 2 in fields:
        wire_type, value = fields[2][0]
        if wire_type == 2:
            result['stop_id'] = value.decode('utf-8', errors='replace')

    return result


def parse_replacement_stop(data: bytes) -> dict[str, Any]:
    """
    Parse ReplacementStop message:
    - field 1: travel_time_to_stop (int32)
    - field 2: stop_id (string)
    """
    fields = parse_message(data)
    result = {'travel_time': None, 'stop_id': None}

    if 1 in fields:
        wire_type, value = fields[1][0]
        if wire_type == 0:
            result['travel_time'] = value

    if 2 in fields:
        wire_type, value = fields[2][0]
        if wire_type == 2:
            result['stop_id'] = value.decode('utf-8', errors='replace')

    return result


def parse_modification(data: bytes) -> dict[str, Any]:
    """
    Parse Modification message:
    - field 1: start_stop_selector (StopSelector)
    - field 2: end_stop_selector (StopSelector)
    - field 3: propagated_modification_delay (int32)
    - field 4: replacement_stops (repeated ReplacementStop)
    - field 5: service_alert_id (string)
    - field 6: last_modified_time (uint64)
    """
    fields = parse_message(data)
    result = {
        'start_stop': None,
        'end_stop': None,
        'propagated_delay': None,
        'replacement_stops': [],
        'service_alert_id': None,
        'last_modified_time': None,
    }

    if 1 in fields:
        wire_type, value = fields[1][0]
        if wire_type == 2:
            result['start_stop'] = parse_stop_selector(value)

    if 2 in fields:
        wire_type, value = fields[2][0]
        if wire_type == 2:
            result['end_stop'] = parse_stop_selector(value)

    if 3 in fields:
        wire_type, value = fields[3][0]
        if wire_type == 0:
            result['propagated_delay'] = value

    if 4 in fields:
        for wire_type, value in fields[4]:
            if wire_type == 2:
                result['replacement_stops'].append(parse_replacement_stop(value))

    if 5 in fields:
        wire_type, value = fields[5][0]
        if wire_type == 2:
            result['service_alert_id'] = value.decode('utf-8', errors='replace')

    if 6 in fields:
        wire_type, value = fields[6][0]
        if wire_type == 0:
            result['last_modified_time'] = value

    return result


def parse_trip_modifications(data: bytes) -> dict[str, Any]:
    """
    Parse TripModifications message (field 8 in FeedEntity):
    - field 1: selected_trips (repeated SelectedTrips)
    - field 2: start_times (repeated string)
    - field 3: service_dates (repeated string - YYYYMMDD format)
    - field 4: modifications (repeated Modification)
    """
    fields = parse_message(data)
    result = {
        'selected_trips': [],
        'start_times': [],
        'service_dates': [],
        'modifications': [],
    }

    # Field 1: selected_trips
    if 1 in fields:
        for wire_type, value in fields[1]:
            if wire_type == 2:
                result['selected_trips'].append(parse_selected_trips(value))

    # Field 2: start_times
    if 2 in fields:
        for wire_type, value in fields[2]:
            if wire_type == 2:
                result['start_times'].append(value.decode('utf-8', errors='replace'))

    # Field 3: service_dates
    if 3 in fields:
        for wire_type, value in fields[3]:
            if wire_type == 2:
                result['service_dates'].append(value.decode('utf-8', errors='replace'))

    # Field 4: modifications
    if 4 in fields:
        for wire_type, value in fields[4]:
            if wire_type == 2:
                result['modifications'].append(parse_modification(value))

    return result


def parse_feed_entity(data: bytes) -> dict[str, Any]:
    """
    Parse FeedEntity looking for trip_modifications (field 8 in some implementations,
    or extension field 12 in the official spec).

    Standard FeedEntity fields:
    - field 1: id (string)
    - field 2: is_deleted (bool)
    - field 3: trip_update
    - field 4: vehicle
    - field 5: alert
    - field 6: shape (experimental)
    - field 7: stop (experimental)
    - field 8: trip_modifications (some implementations)
    - field 12: trip_modifications (official experimental extension)
    """
    fields = parse_message(data)
    result = {
        'id': None,
        'trip_modifications': None,
    }

    # Field 1: id
    if 1 in fields:
        wire_type, value = fields[1][0]
        if wire_type == 2:
            result['id'] = value.decode('utf-8', errors='replace')

    # Check field 8 (some implementations) and field 12 (official extension)
    for field_num in [8, 12]:
        if field_num in fields:
            wire_type, value = fields[field_num][0]
            if wire_type == 2:
                result['trip_modifications'] = parse_trip_modifications(value)
                break

    return result


def parse_gtfs_rt_trip_modifications_feed(content: bytes) -> list[dict[str, Any]]:
    """
    Parse a complete GTFS-RT feed looking for trip modifications.

    Returns a list of trip modification objects.
    """
    modifications = []

    try:
        # Parse the FeedMessage
        fields = parse_message(content)

        # Field 2 contains FeedEntity messages
        if 2 in fields:
            for wire_type, entity_data in fields[2]:
                if wire_type == 2:
                    entity = parse_feed_entity(entity_data)
                    if entity.get('trip_modifications'):
                        tm = entity['trip_modifications']

                        # Build a unified modification object
                        affected_stops = []
                        replacement_stops_list = []

                        for mod in tm.get('modifications', []):
                            if mod.get('start_stop', {}).get('stop_id'):
                                affected_stops.append(mod['start_stop']['stop_id'])
                            if mod.get('end_stop', {}).get('stop_id'):
                                affected_stops.append(mod['end_stop']['stop_id'])
                            for rs in mod.get('replacement_stops', []):
                                if rs.get('stop_id'):
                                    replacement_stops_list.append(rs)

                        mod_data = {
                            'id': entity['id'],
                            'modification_id': entity['id'],
                            'selected_trips': tm.get('selected_trips', []),
                            'start_times': tm.get('start_times', []),
                            'service_dates': tm.get('service_dates', []),
                            'modifications': tm.get('modifications', []),
                            'affected_stop_ids': list(set(affected_stops)) if affected_stops else None,
                            'replacement_stops': replacement_stops_list if replacement_stops_list else None,
                        }

                        # Extract route_id from first trip if available
                        if tm.get('selected_trips') and tm['selected_trips'][0].get('trip_ids'):
                            mod_data['trip_id'] = tm['selected_trips'][0]['trip_ids'][0]

                        modifications.append(mod_data)

    except Exception as e:
        # Log the error but don't fail completely
        print(f"Error parsing trip modifications: {e}")

    return modifications
