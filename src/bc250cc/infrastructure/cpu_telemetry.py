from __future__ import annotations

import platform
from pathlib import Path


def parse_cpuinfo(text):
    """Parse /proc/cpuinfo without depending on field order or blank values."""
    records = []
    current = {}
    for raw_line in str(text or '').splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                records.append(current)
                current = {}
            continue
        if ':' not in raw_line:
            continue
        key, value = raw_line.split(':', 1)
        current[key.strip()] = value.strip()
    if current:
        records.append(current)
    return records


def _read_text(path):
    try:
        return Path(path).read_text(encoding='utf-8', errors='replace').strip()
    except OSError:
        return ''


def _compact_cache_size(value):
    raw = str(value or '').strip().upper()
    if raw.endswith('K'):
        try:
            kib = int(raw[:-1])
        except ValueError:
            return raw
        if kib >= 1024 and kib % 1024 == 0:
            return f'{kib // 1024}M'
    return raw


def _cpu_cache_summary(cpu_root=Path('/sys/devices/system/cpu')):
    cpu_root = Path(cpu_root)
    try:
        indexes = sorted(cpu_root.glob('cpu[0-9]*/cache/index*'))
    except OSError:
        indexes = []
    unique_caches = set()
    grouped = {}
    for index in indexes:
        level = _read_text(index / 'level')
        cache_type = _read_text(index / 'type')
        size = _read_text(index / 'size')
        if not (level and size):
            continue
        shared = _read_text(index / 'shared_cpu_list') or str(index)
        identity = (level, cache_type, size, shared)
        if identity in unique_caches:
            continue
        unique_caches.add(identity)
        suffix = {'Data': 'D', 'Instruction': 'I'}.get(cache_type, '')
        key = (int(level) if level.isdigit() else 99, suffix, _compact_cache_size(size))
        grouped[key] = grouped.get(key, 0) + 1
    entries = []
    for (level, suffix, size), count in sorted(grouped.items()):
        quantity = f'{count}×' if count > 1 else ''
        entries.append(f'L{level}{suffix} {quantity}{size}')
    return ' · '.join(entries)


def _bounded_float(value, *, minimum=0.0, maximum=None):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return float(minimum)
    result = max(float(minimum), result)
    return min(float(maximum), result) if maximum is not None else result


def _group_cpu_records(records, usage_by_thread):
    usage = list(usage_by_thread or ())
    grouped = {}
    for fallback_index, record in enumerate(records):
        try:
            processor = int(record.get('processor', fallback_index))
        except (TypeError, ValueError):
            processor = fallback_index
        key = (
            record.get('physical id', '0'),
            record.get('core id', str(processor)),
        )
        item = grouped.setdefault(key, {'threads': [], 'frequencies': [], 'usage': []})
        item['threads'].append(processor)
        mhz = _bounded_float(record.get('cpu MHz', 0))
        if mhz > 0:
            item['frequencies'].append(mhz)
        if 0 <= processor < len(usage):
            item['usage'].append(_bounded_float(usage[processor], maximum=100.0))
    return grouped


def _core_telemetry(grouped):
    cores = []
    ordered = sorted(grouped.items(), key=lambda pair: min(pair[1]['threads']))
    for display_index, (_key, values) in enumerate(ordered):
        frequencies = values['frequencies']
        loads = values['usage']
        cores.append({
            'index': display_index,
            'threads': tuple(sorted(values['threads'])),
            'frequency_mhz': sum(frequencies) / len(frequencies) if frequencies else 0.0,
            'usage_percent': sum(loads) / len(loads) if loads else 0.0,
            'online': True,
        })
    return cores


def _platform_process(first):
    try:
        family = int(first.get('cpu family', -1))
        model = int(first.get('model', -1))
    except (TypeError, ValueError):
        return 'Not exposed'
    model_name = str(first.get('model name') or '').lower()
    if 'bc-250' in model_name and family == 23 and model == 71:
        return 'Zen 2 · TSMC N7FF'
    return 'Not exposed'


def _total_usage(cores):
    weighted = [
        float(core.get('usage_percent') or 0.0)
        for core in cores
        for _thread in core.get('threads') or ()
    ]
    return sum(weighted) / len(weighted) if weighted else 0.0


def _processor_identity(first, cores, logical, cpu_root):
    flags = set(str(first.get('flags') or '').split())
    selected_features = [
        feature.upper()
        for feature in ('avx2', 'aes', 'sha_ni', 'svm')
        if feature in flags
    ]
    return {
        'model_name': first.get('model name') or 'Not detected',
        'vendor': first.get('vendor_id') or 'Not detected',
        'architecture': platform.machine() or 'Not detected',
        'family_model_stepping': (
            f"{first.get('cpu family', '?')} / {first.get('model', '?')} / {first.get('stepping', '?')}"
        ),
        'platform_process': _platform_process(first),
        'microcode': first.get('microcode') or 'Not exposed',
        'topology': f'{len(cores)} cores / {logical} threads',
        'cache': _cpu_cache_summary(cpu_root) or 'Not exposed',
        'features': ' · '.join(selected_features) or 'Not exposed',
        'total_usage_percent': _total_usage(cores),
    }


def build_cpu_telemetry(cpuinfo_text, usage_by_thread=None, cpu_root=Path('/sys/devices/system/cpu')):
    """Build stable CPU-Z-like data from kernel interfaces only."""
    records = parse_cpuinfo(cpuinfo_text)
    if not records:
        return {'processor': {}, 'cores': []}
    cores = _core_telemetry(_group_cpu_records(records, usage_by_thread))
    return {
        'processor': _processor_identity(records[0], cores, len(records), cpu_root),
        'cores': cores,
    }
