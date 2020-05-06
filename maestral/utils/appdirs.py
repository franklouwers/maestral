# -*- coding: utf-8 -*-
"""
@author: Sam Schott  (ss2151@cam.ac.uk)

(c) Sam Schott; This work is licensed under the MIT licence.

This module contains functions to retrieve platform dependent locations to store app data.
It supports macOS and Linux.

"""

# system imports
import os
import os.path as osp
import platform
import tempfile

# local imports
from maestral.config.base import get_home_dir, get_conf_path, get_data_path, _to_full_path


__all__ = [
    'get_home_dir', 'get_conf_path', 'get_data_path', 'get_log_path',
    'get_cache_path', 'get_autostart_path', 'get_runtime_path'
]

_home_dir = get_home_dir()


def get_cache_path(subfolder=None, filename=None, create=True):
    """
    Returns the default cache path for the platform. This will be:

        - macOS: '~/Library/Application Support/SUBFOLDER/FILENAME'
        - Linux: '$XDG_CACHE_HOME/SUBFOLDER/FILENAME'
        - fallback: '$HOME/.cache/SUBFOLDER/FILENAME'

    :param Optional[str] subfolder: The subfolder for the app.
    :param Optional[str] filename: The filename to append for the app.
    :param bool create: If ``True``, the folder '<subfolder>' will be created on-demand.
    """
    if platform.system() == 'Darwin':
        cache_path = get_conf_path(create=False)
    elif platform.system() == 'Linux':
        fallback = osp.join(_home_dir, '.cache')
        cache_path = os.environ.get('XDG_CACHE_HOME', fallback)
    else:
        raise RuntimeError('Platform not supported')

    return _to_full_path(cache_path, subfolder, filename, create)


def get_log_path(subfolder=None, filename=None, create=True):
    """
    Returns the default log path for the platform. This will be:

        - macOS: '~/Library/Logs/SUBFOLDER/FILENAME'
        - Linux: '$XDG_CACHE_HOME/SUBFOLDER/FILENAME'
        - fallback: '$HOME/.cache/SUBFOLDER/FILENAME'

    :param Optional[str] subfolder: The subfolder for the app.
    :param Optional[str] filename: The filename to append for the app.
    :param bool create: If ``True``, the folder '<subfolder>' will be created on-demand.
    """

    if platform.system() == 'Darwin':
        log_path = osp.join(_home_dir, 'Library', 'Logs')
    elif platform.system() == 'Linux':
        log_path = get_cache_path(create=False)
    else:
        raise RuntimeError('Platform not supported')

    return _to_full_path(log_path, subfolder, filename, create)


def get_autostart_path(filename=None, create=True):
    """
    Returns the default path for login items for the platform. This will be:

        - macOS: '~/Library/LaunchAgents/FILENAME'
        - Linux: '$XDG_CONFIG_HOME/autostart/FILENAME'
        - fallback: '$HOME/.config/autostart/FILENAME'

    :param Optional[str] filename: The filename to append for the app.
    :param bool create: If ``True``, the folder '<subfolder>' will be created on-demand.
    """
    if platform.system() == 'Darwin':
        autostart_path = osp.join(_home_dir, 'Library', 'LaunchAgents')
    elif platform.system() == 'Linux':
        autostart_path = get_conf_path('autostart', create=create)
    else:
        raise RuntimeError('Platform not supported')

    if filename:
        autostart_path = osp.join(autostart_path, filename)

    return autostart_path


def get_runtime_path(subfolder=None, filename=None, create=True):
    """
    Returns the default runtime path for the platform. This will be:

        - macOS: '~/Library/Application Support/SUBFOLDER/FILENAME'
        - Linux: '$XDG_RUNTIME_DIR/SUBFOLDER/FILENAME'
        - fallback: '$HOME/.cache/SUBFOLDER/FILENAME'

    :param Optional[str] subfolder: The subfolder for the app.
    :param Optional[str] filename: The filename to append for the app.
    :param bool create: If ``True``, the folder '<subfolder>' will be created on-demand.
    """

    if platform.system() == 'Darwin':
        runtime_path = get_conf_path(create=False)
    elif platform.system() == 'Linux':
        fallback = get_cache_path(create=False)
        runtime_path = os.environ.get('XDG_RUNTIME_DIR', fallback)
    else:
        raise RuntimeError('Platform not supported')

    return _to_full_path(runtime_path, subfolder, filename, create)


def get_old_runtime_path(subfolder=None, filename=None, create=True):
    """
    Returns the default runtime path for the platform. This will be:

        - macOS: tempfile.gettempdir() + 'SUBFOLDER/FILENAME'
        - Linux: '$XDG_RUNTIME_DIR/SUBFOLDER/FILENAME'
        - fallback: '$HOME/.cache/SUBFOLDER/FILENAME'

    :param Optional[str] subfolder: The subfolder for the app.
    :param Optional[str] filename: The filename to append for the app.
    :param bool create: If ``True``, the folder '<subfolder>' will be created on-demand.
    """

    if platform.system() == 'Darwin':
        runtime_path = tempfile.gettempdir()
    elif platform.system() == 'Linux':
        fallback = get_cache_path(create=False)
        runtime_path = os.environ.get('XDG_RUNTIME_DIR', fallback)
    else:
        raise RuntimeError('Platform not supported')

    return _to_full_path(runtime_path, subfolder, filename, create)
