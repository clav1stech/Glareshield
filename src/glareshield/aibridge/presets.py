"""Known aircraft LVars that can be added to the private AI Bridge settings in one step."""
from __future__ import annotations

from .config import AIBridgeSettings, LVarEntry

ON_OFF = {'0': 'éteint', '1': 'allumé'}
OBSERVED = 'Observé sur Fenix A320 2.4.0.4720 (MSFS 2024, octobre 2026)'
IN_FLIGHT = OBSERVED+' au sol uniquement ; à confirmer en vol.'


def lvar(key, name, label, values, note, level='essential'):
    return LVarEntry(key=key, name=name, label=label, values=values, note=note, level=level,
                     interval_ms=2000, max_age_s=8)


# Names come from the Fenix package behaviour files; meanings were checked against the cockpit.
# Each user still validates them on their own installation: validated stays False.
PRESETS = {
    'fenix-a320': {
        'label': 'Fenix A320',
        'lvars': [
            lvar('fcu_ap1', 'I_FCU_AP1', 'Voyant AP1', ON_OFF, IN_FLIGHT),
            lvar('fcu_ap2', 'I_FCU_AP2', 'Voyant AP2', ON_OFF, IN_FLIGHT),
            lvar('fcu_athr', 'I_FCU_ATHR', 'Voyant A/THR', ON_OFF, IN_FLIGHT),
            lvar('fcu_loc', 'I_FCU_LOC', 'Voyant LOC', ON_OFF, IN_FLIGHT),
            lvar('fcu_appr', 'I_FCU_APPR', 'Voyant APPR', ON_OFF, IN_FLIGHT),
            lvar('fcu_exped', 'I_FCU_EXPED', 'Voyant EXPED', ON_OFF, IN_FLIGHT),
            lvar('efis1_fd', 'I_FCU_EFIS1_FD', 'Directeur de vol (FD) CDB', ON_OFF, OBSERVED+'.'),
            lvar('efis1_ls', 'I_FCU_EFIS1_LS', 'Voyant LS CDB', ON_OFF, IN_FLIGHT),
            lvar('efis1_baro_std', 'S_FCU_EFIS1_BARO_STD', 'Calage altimétrique CDB',
                 {'0': 'QNH', '1': 'STD'}, OBSERVED+'.'),
            lvar('speedbrake_lever', 'A_FC_SPEEDBRAKE', 'Levier d’aérofreins (position)',
                 {'1': 'rentré', '0': 'armé'}, OBSERVED+' une fois ; échelle complète à confirmer.'),
            lvar('master_warning', 'I_MIP_MASTER_WARNING_CAPT', 'Voyant MASTER WARNING CDB', ON_OFF, OBSERVED+'.'),
            lvar('master_caution', 'I_MIP_MASTER_CAUTION_CAPT', 'Voyant MASTER CAUTION CDB', ON_OFF, OBSERVED+'.'),
        ],
        # Standard SimVars that do not follow the Fenix cockpit.
        'disable': ['flaps_handle_index', 'spoilers_armed'],
    },
}


def apply_preset(settings: AIBridgeSettings, preset_id: str) -> tuple[AIBridgeSettings, int]:
    """Add the preset LVars that are not configured yet; existing entries are kept unchanged."""
    if preset_id not in PRESETS:
        raise ValueError('Préréglage inconnu.')
    preset = PRESETS[preset_id]
    data = settings.model_dump(mode='json')
    keys = {item['key'] for item in data['lvars']}
    names = {item['name'].removeprefix('L:') for item in data['lvars']}
    added = [item.model_dump(mode='json') for item in preset['lvars']
             if item.key not in keys and item.name.removeprefix('L:') not in names]
    data['lvars'] += added
    data['disabled'] = sorted(set(data['disabled']) | set(preset['disable']))
    return AIBridgeSettings.model_validate(data), len(added)
