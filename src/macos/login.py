from __future__ import annotations

import sys
import ServiceManagement as SM


def status() -> int:
    return int(SM.SMAppService.mainAppService().status())


def enabled() -> bool:
    return status() == SM.SMAppServiceStatusEnabled


def set_enabled(value: bool) -> None:
    if not getattr(sys, 'frozen', False):
        raise ValueError('请在独立应用包中设置登录启动')
    service = SM.SMAppService.mainAppService()
    success, error = service.registerAndReturnError_(None) if value else service.unregisterAndReturnError_(None)
    if not success:
        raise ValueError(f'无法更新登录项：{error}')
    if value and status() == SM.SMAppServiceStatusRequiresApproval:
        raise ValueError('请在系统设置的登录项中允许 Neuro Pet')
