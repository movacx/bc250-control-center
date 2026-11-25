"""Sidebar sections, in the order the desktop application lists them."""

from __future__ import annotations

from .about import AboutPage
from .base import Page
from .blackbox import BlackBoxPage
from .compute_units import ComputeUnitsPage
from .cpu import CpuPage
from .dashboard import DashboardPage
from .extras import AdditionalSettingsPage
from .fans import FansPage
from .firmware import FirmwarePage
from .gpu import GpuPage
from .performance import PerformancePage
from .processes import ProcessesPage
from .remote import RemoteAccessPage
from .report import ReportPage
from .settings import SettingsPage
from .support import SupportPage


def build_pages() -> dict[str, Page]:
    pages = [
        DashboardPage(), CpuPage(), GpuPage(), AdditionalSettingsPage(), ComputeUnitsPage(),
        PerformancePage(), FansPage(), ProcessesPage(), BlackBoxPage(), FirmwarePage(), RemoteAccessPage(), ReportPage(), SupportPage(), SettingsPage(),
        AboutPage(),
    ]
    return {page.key: page for page in pages}


__all__ = ["Page", "build_pages"]
