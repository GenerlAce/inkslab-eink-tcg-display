#!/usr/bin/python3
"""Shared utilities for InkSlab download scripts."""

import os
import shutil
import requests

MIN_FREE_SPACE_MB = 50


def check_disk_space(path):
    """Return True if there is enough free disk space to continue downloading."""
    try:
        st = shutil.disk_usage(path)
        return (st.free // (1024 * 1024)) >= MIN_FREE_SPACE_MB
    except Exception:
        return True


def download_file(url, filepath, headers, timeout=15):
    """Download a file, skipping if it already exists. Writes to a temp file first."""
    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        return "EXISTS"
    tmp = filepath + ".tmp"
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code == 200:
            with open(tmp, 'wb') as f:
                f.write(r.content)
            if os.path.getsize(tmp) > 0:
                os.rename(tmp, filepath)
                return "DOWNLOADED"
            os.remove(tmp)
            return "FAIL: empty response"
        return f"HTTP {r.status_code}"
    except Exception as e:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass
        return f"FAIL: {e}"
