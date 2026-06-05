"""
API Router — Quản lý License Key.
Endpoints: POST /license/activate, POST /license/check
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.database import get_async_session
from server.models import LicenseKey, LicenseStatus, User
from server.schemas import (
    LicenseActivateRequest,
    LicenseActivateResponse,
    LicenseCheckRequest,
    LicenseCheckResponse,
)
from server.utils.helpers import calculate_expiry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/license", tags=["License"])


@router.post("/activate", response_model=LicenseActivateResponse)
async def activate_license(
    request: LicenseActivateRequest,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Kích hoạt License Key — khóa chặt với Device ID (HWID).
    Logic:
    - Key AVAILABLE → ACTIVATED, gán device_id, tính expired_at
    - Key ACTIVATED + device_id khớp → thành công (kích hoạt lại)
    - Key ACTIVATED + device_id KHÔNG khớp → từ chối
    """
    # Tìm key
    result = await session.execute(
        select(LicenseKey).where(
            LicenseKey.key_code == request.license_key.upper().strip()
        )
    )
    license_key = result.scalar_one_or_none()

    if not license_key:
        raise HTTPException(
            status_code=404,
            detail="License Key không tồn tại."
        )

    # Kiểm tra trạng thái
    if license_key.status == LicenseStatus.EXPIRED:
        raise HTTPException(
            status_code=403,
            detail="License Key đã hết hạn."
        )

    if license_key.status == LicenseStatus.AVAILABLE:
        # Key chưa kích hoạt → tiến hành kích hoạt
        expired_at = calculate_expiry(license_key.duration_days)

        license_key.status = LicenseStatus.ACTIVATED
        license_key.device_id = request.device_id
        license_key.activated_at = datetime.utcnow()
        license_key.expired_at = expired_at

        # Gán user nếu có telegram_id
        if request.telegram_id:
            user_result = await session.execute(
                select(User).where(User.telegram_id == request.telegram_id)
            )
            user = user_result.scalar_one_or_none()
            if user:
                license_key.user_id = user.id

        await session.commit()

        remaining = (expired_at - datetime.utcnow()).days
        remaining_secs = (expired_at - datetime.utcnow()).total_seconds()
        remaining_hours = int(remaining_secs // 3600) if remaining_secs > 0 else 0
        logger.info(
            f"🔑 Key {request.license_key[:8]}... activated "
            f"for device {request.device_id[:16]}..."
        )

        return LicenseActivateResponse(
            success=True,
            message="Kích hoạt License Key thành công!",
            expired_at=expired_at,
            remaining_days=max(remaining, 0),
            remaining_hours=remaining_hours,
        )

    elif license_key.status == LicenseStatus.ACTIVATED:
        # Key đã kích hoạt → kiểm tra device_id
        if license_key.device_id != request.device_id:
            # Sai device — từ chối
            logger.warning(
                f"⚠️ Device mismatch! Key: {request.license_key[:8]}... "
                f"Expected: {license_key.device_id[:16]}... "
                f"Got: {request.device_id[:16]}..."
            )
            raise HTTPException(
                status_code=403,
                detail=(
                    "License Key này đã được kích hoạt trên thiết bị khác. "
                    "Vui lòng liên hệ Admin để được hỗ trợ."
                )
            )

        # Device khớp — kiểm tra hết hạn
        if license_key.expired_at and license_key.expired_at < datetime.utcnow():
            license_key.status = LicenseStatus.EXPIRED
            await session.commit()
            raise HTTPException(
                status_code=403,
                detail="License Key đã hết hạn. Vui lòng gia hạn."
            )

        # Thành công
        remaining = (license_key.expired_at - datetime.utcnow()).days
        secs = (license_key.expired_at - datetime.utcnow()).total_seconds()
        return LicenseActivateResponse(
            success=True,
            message="License Key hợp lệ.",
            expired_at=license_key.expired_at,
            remaining_days=max(remaining, 0),
            remaining_hours=max(int(secs // 3600), 0),
        )


@router.post("/check", response_model=LicenseCheckResponse)
async def check_license(
    request: LicenseCheckRequest,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Kiểm tra License Key còn hạn không.
    Gọi endpoint này mỗi khi khởi động app hoặc trước khi dịch.
    """
    result = await session.execute(
        select(LicenseKey).where(
            LicenseKey.key_code == request.license_key.upper().strip()
        )
    )
    license_key = result.scalar_one_or_none()

    if not license_key:
        return LicenseCheckResponse(
            valid=False,
            message="License Key không tồn tại."
        )

    if license_key.status == LicenseStatus.AVAILABLE:
        return LicenseCheckResponse(
            valid=False,
            message="License Key chưa được kích hoạt."
        )

    if license_key.status == LicenseStatus.EXPIRED:
        return LicenseCheckResponse(
            valid=False,
            message="License Key đã hết hạn. Vui lòng gia hạn."
        )

    if license_key.status == LicenseStatus.ACTIVATED:
        # Kiểm tra device
        if license_key.device_id != request.device_id:
            return LicenseCheckResponse(
                valid=False,
                message="License Key không khớp với thiết bị này."
            )

        # Kiểm tra hết hạn
        if license_key.expired_at and license_key.expired_at < datetime.utcnow():
            # Tự động cập nhật status → EXPIRED
            license_key.status = LicenseStatus.EXPIRED
            await session.commit()
            return LicenseCheckResponse(
                valid=False,
                message="License Key đã hết hạn. Vui lòng gia hạn."
            )

        remaining = (license_key.expired_at - datetime.utcnow()).days
        secs = (license_key.expired_at - datetime.utcnow()).total_seconds()
        return LicenseCheckResponse(
            valid=True,
            message="License Key hợp lệ.",
            expired_at=license_key.expired_at,
            remaining_days=max(remaining, 0),
            remaining_hours=max(int(secs // 3600), 0),
        )
